# 10. Queue engine: how the queue drives workers

This file defines how an authority turns ready tasks into offers at high throughput: classes and matching, the depth of the local queue of a worker, result batching, backpressure, fairness, tail reclaim, reservation, time-aware offers, `podswarm each`, the structures of the scheduler, connection storms, and the throughput model. The authority is the home of a session (an in-memory queue) or the coordinator of a swarm. Tasks, states and transitions are in file 09. The messages, reconciliation and the fence are in file 05. The road, `hello`, `ready` and reattach are in file 04. The store is in file 11. Placement of one attached command (`podswarm run`) on the best machine of a pool is in file 08.

## 1. The model

Workers pull. A `pull` (file 05) reports the free capacity of the worker and the count of attempts that it holds and did not begin. A link has one standing pull state: the newest `pull` replaces the one before it, and it is not a request that waits for one answer. The authority may send offers at any time, up to the capacity of the newest `pull` plus the queue part of section 4, minus what it offered since that `pull`. When no ready task fits, the pull is parked (section 4.4). The authority never sends more than the newest `pull` allows.

One scheduler actor owns all scheduling state in memory. It writes to the store only the changes that must survive a crash (file 11). A session with no `--db` has no store: the same engine runs with the writer stage absent.

Reason: pull works when the worker can dial the authority and when the authority starts the worker over a road. A worker never needs to accept a connection.

## 2. Classes and matching

### 2.1 The class
The class of a shape is `hash(needs, priority)` (file 09). The key uses the needs after rounding: `cores_m` is rounded up to a multiple of 250, `mem_mib` up to a multiple of 64, `disk_mib` up to a multiple of 1,024. The worker accounts the rounded needs. The key excludes `needs.worker` (section 13). Tasks of one class are interchangeable for matching.

Reason: rounding makes near-equal needs share a class, and the class count bounds the cost of a pull.

`class_max` is 4,096 live classes. A class is live while it has a task that is not terminal. A submit that makes a new class above the bound fails with `busy` and the text `class_max`. The class frees when its last task is terminal.

### 2.2 `fit`
`fit(worker, class)` is true when all of these hold:

| Check | Rule |
| --- | --- |
| State | the worker is `active`, not `draining`, not `suspect` |
| OS and arch | the worker's `os` and `arch` are in `needs.os` and `needs.arch` when they are set |
| Tags | the worker has each tag of `tags_all` and at least one of `tags_any` |
| Boundary | the best boundary of the worker is at least `needs.boundary` (file 13) |
| Limits | each limit in `limits_required` has the mode `enforced` on the worker (file 12) |
| Shell and interp | `needs.shell` and `needs.interp` match `caps.shell` and the worker's interpreters |
| Capacity | the total capacity covers `cores_m`, `mem_mib`, `disk_mib` and each named resource of `res` |
| Lifetime | section 12 |
| Pin | `needs.worker`, when set, is this worker (section 13) |

The checks from State to Capacity are static: they change only when the worker's state, `caps` or tags change, or when a class is made. The engine keeps them as a bitset (section 14). Lifetime and free capacity are checked at each pull.

### 2.3 `needs_unsatisfiable` at submit
At submit the authority checks each new class against every known worker (enrolled, not `revoked`, not `retired`; in a session, the machines of the pool, file 08). If at least one worker is known and none passes the static checks, the submit fails with `needs_unsatisfiable`, and the text names the first check that failed on the most workers. With no known worker the submit succeeds, and `ls` shows the class with no fitting worker.

## 3. Estimates

### 3.1 Task time `d`
Each class has a log histogram of the wall time of its ended attempts (`exited` only): 4 buckets per doubling from 1 ms to 2^27 ms, 108 counters of `u32`, 432 bytes. An update costs one `leading_zeros` and one add. After every 1,000 samples the engine halves each counter, so the histogram follows a change of the workload.

For a worker `w` and a class `c`: `d = max(1 ms, median_c * 1000 / speed_w)`. `d` is unknown while the histogram of `c` is empty.

Reason: a median resists a heavy tail; a mean does not.

### 3.2 Worker speed
`speed_w` is a u32 in per mille (1,000 is the median worker) and starts at 1,000. At each ended attempt of a class with at least 20 samples, the engine moves `speed_w` toward `1000 * median_c / wall` with smoothing 0.2, and clamps it to [100, 10,000]. The worker record stores it (file 09). The speed scores of `caps` (file 08) serve placement of one command; this engine does not use them.

### 3.3 Round trip `R`
`R` is the `rtt_ms` of the latest `pull`. The worker measures it on `hb` and `hback` pairs and on `pull` and `offer` pairs that the authority did not park (file 05). With no `rtt_ms`, `R` is the smoothed RTT of the socket from `TCP_INFO` where the road is a TCP socket of the authority, else `rtt_default_ms` (100). The embedded worker of a session has `R = 0`.

## 4. Queue depth and the offer

### 4.1 Terms
For a worker and a class `c`:

| Term | Meaning |
| --- | --- |
| `slots_c` | `min(slots, floor(cap.cores_m / cores_m), floor(cap.mem_mib / mem_mib), floor(cap.disk_mib / disk_mib), floor(cap.res[k] / res[k]) for each k)`; a need of 0 adds no term |
| `free_slots_c` | the same, with the free capacity of the `pull` in place of the total capacity |
| `unstarted` | the count from the `pull`: attempts that the worker holds and did not begin |
| `T_q` | `clamp(4 * R + 0.05 s, depth_min_s, depth_max_s)`; defaults 1 s and 10 s |
| `u` | the target of unstarted tasks: `slots_c * floor(T_q / d)`, and at least `slots_c` (one queued task per slot) when `R` is more than 2 percent of `d` |
| `Q` | ready tasks of `c` |
| `W` | active workers whose fit bit for `c` is set |

### 4.2 The offer size
```
n = free_slots_c + u - unstarted
n = max(n, free_slots_c)                      when c has ready tasks
n = min(n, max(free_slots_c, ceil(Q / (2 * W))), bundle_max)
unknown d:  n = free_slots_c
refill = floor(u / 2)
```
Further caps:
* `hold_max_s` (60): the unstarted work that the worker holds after the offer, `sum(unstarted_k * d_k) / slots`, is at most 60 s.
* `offer_bytes_max` (512 KiB): when the rows and the shapes pass this size, the authority sends several offers back to back. An offer has no `more` field (D-51): the worker counts what it holds, and its next `pull` states it.
* Section 12: the lifetime of the worker.

Reason for `ceil(Q / (2 * W))`: when the queue is short, small offers spread the last tasks over all fitting workers (guided self-scheduling). Reason for `T_q >= 4 * R`: the refill mark then covers two round trips of work.

The offer carries `refill`. The worker sends a new `pull` when one of these holds:
* `unstarted <= refill`;
* free capacity exists that no queued attempt fits;
* an attempt ended, so its capacity is free.

A `pull` is small, and the authority sizes each offer from the newest one, so an extra `pull` costs one message and never a duplicate task.

### 4.3 Order inside one offer
The engine takes classes in the order of section 9 (priority, then deficit round robin). The first class with a known `d` gets the full `n` of section 4.2. Each later class in the same offer gets only its `free_slots_c`, computed on the capacity that the classes before it left. `refill` comes from the first class.

Reason: the queue part of an offer belongs to one class, so a worker that fits many classes does not hold `T_q` of work for each.

### 4.4 Parked pulls
A pull with no fitting ready task is parked. The authority sends an offer:
* at once when a fitting task becomes ready (submit, T2, T9, T11, section 10);
* with no rows after `park_s` (20), so that the worker knows that the authority is alive. The pull state stays. The worker sends a new `pull` only by the rules of section 4.2.

On a class whose ready bit goes from 0 to 1, the actor tests that bit in the fit set of each parked worker, oldest park first. A parked pull does not replace `hb`. The worker sends `hb` every `hb_s` in all states (file 05).

### 4.5 The standing pull
The newest `pull` of a link is its pull state. A new `pull` sets it again. The capacity that the authority may still offer is the free capacity of that `pull` minus the tasks of each offer whose `no` is above `pull.seen` (D-125, file 05). An offer in flight when the worker wrote the `pull` is in that sum, so the authority never offers twice for one free slot. The tasks of those offers also count as `unstarted` (section 4.1).

The worker starts queued attempts in the order of the offers. It starts a later attempt first only when the attempt before it does not fit the free capacity. The authority treats the newest `unstarted` rows of the worker as the unstarted ones. Reason: the per-class count is then exact while the order holds.

## 5. The depth rule checked with numbers

Inputs: 4 slots, one core per task, `d = 10 ms`, `R = 100 ms`, a long queue.

| Quantity | Value |
| --- | --- |
| `T_q` | `clamp(4 * 0.1 + 0.05, 1, 10)` = 1 s |
| `u` | `4 * floor(1 / 0.01)` = 400 tasks (1 s of work for each slot) |
| `refill` | 200 tasks |
| first offer | `4 + 400 - 0` = 404 tasks |
| run rate | 4 slots / 10 ms = 400 tasks/s |
| next pull | when 200 tasks remain, 0.5 s after the offer lands |
| low point | the offer lands `R` later; 40 more tasks began; 160 tasks remain (0.4 s of work) |
| offer in steady state | `0 + 400 - 200` = 200 tasks |
| pulls | 2 per second, each followed by an offer of 200 tasks |
| result messages | one in flight per `R`, so about 40 rows each and 10 messages per second |
| margin | a slot idles only when an offer takes more than 0.5 s, which is 5 `R` |

The local queue never runs dry, so the only loss is the per-task cost `o` of the worker: utilisation is `d / (d + o)`. With `o` at the bound of A-05 (300 us on Cortex-A53, 60 us on x86_64), utilisation is 97 percent and 99.4 percent. Target A-08: at least 95 percent for 10 ms tasks at 100 ms round trip [T].

For `d >= T_q`, `floor(T_q / d)` is 0, and the floor of one queued task per slot applies when `R` is more than 2 percent of `d`. Each slot then starts its next task with no round trip, and tail reclaim (section 10) moves a queued long task to a worker that idles at the end of a run. With `R` at most 2 percent of `d`, `u = 0` costs at most 2 percent of utilisation. Reason: one round trip of idle time per long task costs up to 20 percent on a slow link, and tail reclaim takes back a queued task that waits behind a long one.

## 6. Edge cases

* **Unknown `d`.** `n = free_slots_c`: one task for each free slot, no queue. The histogram is per class, so the first ended attempt on any worker sets `d` for all workers.
* **`d` under 1 ms.** The clamp makes `u` cover less than `T_q` of real work. `bundle_max` bounds the offer, and the worker pulls again at once while `unstarted <= refill`. A user with sub-millisecond tasks gets more throughput when one task runs many items.
* **One worker.** `W = 1` and the tail cap is `ceil(Q / 2)`. The cap adds pulls near the end and changes nothing else.
* **Mixed needs.** Section 4.3. `hold_max_s` bounds the sum over classes.
* **A class whose tasks take 4 cores.** On an 8-core worker with 8 slots, `slots_c = 2` and `free_slots_c = floor(free cores / 4)`. With `d = 2 s` and `T_q = 1 s`, `u = 0`: the worker pulls when 4 cores are free. With `d = 100 ms`, `u = 2 * 10 = 20`.
* **A worker that fits nothing ready.** Its pull parks (section 4.4).
* **A worker whose offer is lost.** The link breaks; reattach and reconciliation (files 04 and 05) settle the offered rows.

## 7. Result batching and slot credit

Results are the flow control of the other direction. The rule is self-clocked:
* The worker keeps at most one `result` message unacknowledged.
* When none is in flight, the worker sends a finished result at once.
* While one is in flight, the worker collects finished results. When the `ack` arrives, it sends them in one message of at most `result_rows_max` (1,000) rows or `result_bytes_max` (256 KiB). Rows above the cap wait in the journal (file 12) for the next message.

No timer delays a result. Reason: a timer adds latency when the link is idle and adds no throughput when it is busy.

The authority frees the capacity of an attempt in its view of the worker when the `result` arrives, before the commit. The commit gates only the `ack` (file 11). The free capacity of the next `pull` comes from the worker in any case.

With offers of `n` rows and results of `B` rows, the link carries about `2 / n + 2 / B` control messages per task, plus `hb` and `hback`.

## 8. Backpressure from the store

The store writer takes what queued while its last commit ran (file 11). When the store is slow, the actor delays two kinds of messages:
* new offers: a pull that arrives is parked, and a parked pull stays parked;
* `ack` of results.

It also stops reading `submit` frames of submitter links. The delay starts when the oldest queued store command is older than `backpressure_age_ms` (250), or when the queue holds more than `backpressure_events` (16,384) events. It ends when both values are under half of their limits. It never delays `hback`, `cancel` or `err`. It keeps reading the frames of worker links, so that `hb` keeps `last_rx` fresh. It drops no frame. A worker with unacknowledged results keeps them in its journal and keeps sending `hb`. A delayed `ack` slows the results of each worker by the rule of section 7, and a delayed offer slows new leases; both cut the inflow of store events.

Reason: an age measures the delay that a worker sees; a count of events does not.

A session with no store has no backpressure. An offer goes out before the commit of its `leases` row, except an offer that holds an `at_most_once` task (I6, file 09).

## 9. Fairness

* **Priority.** Strict between levels, from 100 down to -100. A pull takes tasks of the highest level that has a fitting ready task first.
* **Runs of one level.** Deficit round robin. Each run with fitting ready tasks gets `weight * drr_quantum` (default 100) credits at each round. A run sends tasks while its credit is positive, one credit per task. A run with no ready task loses its remaining credit. Reason: a unit of one task treats a run of small tasks and a run of large tasks equally by count, as a HyperShell user expects.
* **One offer, many runs.** An offer may hold tasks of several runs.
* **`max_running`.** A run whose `offered`, `running` and `stopping` rows reach `max_running` is skipped (guard of T4, file 09). It returns to the rotation when a row ends.
* **Halt.** The halt policy and its modes are in file 09, section 19. A halted run leaves the candidate sets at once.
* **Retries first.** Inside a run the order is `(group, idx)`. With `retry_first` (`--retry-first`, run, bool, default false) a task that returns to `ready` after a failure or a loss goes before each task of its group that never had an attempt.
* **Start rate.** `rate` (`--rate N`, a run setting: an integer count of task starts per second, 1 and up, default none, which is no limit) bounds how fast the authority starts the tasks of one run. A token bucket of depth N refills at N per second, and T4 for the run takes one token per task. A run with `rate` gets no queue part (`u = 0`), so an offer is a start within one round trip. The bound is per run; there is no global rate.
* **Scale hook.** `coord --scale-hook` is the hook `scale.tick` of file 17. Its inputs from this engine are the ready count of each class, the fitting worker count of each class (section 14.2) and `eta_s`: the ready work of a class, `Q * median_c`, divided by the slots of its fitting workers.

## 10. Tail reclaim

The engine does not steal running work. It takes back tasks that wait in the local queue of one worker while another worker idles.

Condition, checked when a pull parks and at each `park_s` tick of a parked pull:
* a parked worker `P` fits class `c`;
* `c` has no ready task;
* another worker `H` holds unstarted tasks of `c` that it got more than `max(T_q, 2 * d)` ago.

Action: the authority sends `cancel{items, mode: unstarted}` to `H` for `ceil(k / 2)` of its `k` such tasks, the newest first. `H` answers each one that it did not begin with a `not_started` result (file 05). The task takes T9 to `ready`, with no budget use, and the parked pull of `P` wakes. A task that `H` began in the meantime runs on. One reclaim per `(H, c)` is in flight at a time. The holder with the most unstarted work of `c` goes first.

Pinned tasks (section 13) are never reclaimed.

## 11. Reservation for a big task

A big task can starve while small tasks fill each slot that frees. When the head task of a class is skipped for `reserve_after_s` (30), the engine makes a reservation:
* "Skipped" means: the task is the first candidate of a pull and does not fit the free capacity of the pulling worker, while its static fit holds.
* The reservation takes the fitting worker with the most free capacity of the needed kind. That worker gets no task of an equal or lower priority until the reserved task fits its free capacity and is offered to it.
* A task of a higher priority may still go to it (section 9).
* A class has at most one reservation; a worker holds at most one.
* The reservation ends when the task is offered, becomes terminal, or the worker leaves `active`. The engine then picks again if the head task still waits.

A reservation uses no duration estimate. An `exclusive` task uses the same rule with "the worker holds no attempt" as its fit. Backfill by duration estimate is an extension (file 24).

## 12. Time-aware offers

### 12.1 Lifetime
A worker that will end at a known time sends `lifetime_s` in `hello` (file 04): the seconds that remain. Sources, first match: `--time-limit D`; `SLURM_JOB_END_TIME` minus the time now; `PBS_WALLTIME` minus the time that the job ran. The authority sets `end_w` to the arrival time of `hello` plus `lifetime_s`, on its own monotonic clock. A worker with no lifetime has no `end_w`.

### 12.2 The check
For a class, `time_need` is `needs.time_s` (default `timeout_s`). A class with neither has no `time_need`.
* A worker with an `end_w` fits a class only when `time_need + kill_grace_s <= end_w - now - drain_margin_s`.
* A class with no `time_need` fits a worker with an `end_w` only when `assume_time_s` (3,600) passes the same check. It fits a worker with no lifetime.
* For the queue part of an offer the engine adds the wait in the local queue: a task goes into the queue only while `unstarted work ahead / slots_c + time_need + kill_grace_s` fits.

### 12.3 The drain before the end
At `end_w - drain_margin_s` (60 s) the worker enters drain. For a task with `checkpoint`, file 15 raises the margin to cover the upload, and the drain asks for a checkpoint first (file 15). In drain the worker sends no pull, returns each queued attempt as a `not_started` result (T9, no budget), and lets running attempts run. The authority stops offers to that worker at the same time on its own clock. At `end_w - kill_grace_s` the worker runs the kill ladder (file 12) on each remaining attempt. Such an attempt ends `killed` with reason `lifetime`. That loss takes T8 with no use of the loss budget (file 09). The worker then exits 0 with `bye{lifetime}`.

Reason: the end of an allocation is a planned event, not a fault of the task.

### 12.4 Idle exit
A worker with `idle_exit_s` above 0 exits 0 with `bye{idle}` when it held no attempt and got only offers with no rows for `idle_exit_s`. Default: 300 for a worker that joins with an invite that has the rule `ephemeral` (file 16), 0 (off) otherwise. A worker that a home launched over a road ends with its session (file 04).

## 13. `podswarm each`

`podswarm each [--tag K:V] -- CMD` (file 18) makes one task for each worker that is `active`, connected, and passes the static fit of the shape at submit time. Each task gets `needs.worker` set to the `wid` of its worker.

* A pinned task is not in a class queue. It goes into the pinned queue of its worker. A pull of that worker takes its pinned tasks first at their priority level. The class of a pinned task, for its histogram and for `class_max`, is the class of its needs without `worker`.
* A pinned task waits while its worker is disconnected. When the worker becomes `revoked` or `retired`, the task takes T10 with reason `worker_gone` (D-50).
* Lifetime (section 12) applies. Tail reclaim and reservation do not move a pinned task.

Reason: one class for each worker would spend the class bound on a fleet command.

When the inputs of tasks are large blobs, the engine prefers, as a tie-break among tasks of equal turn, a worker whose `hb.blobs` lists them; the rule is in file 15. A worker that returns an attempt as `not_started` with reason `disk` (file 15) gives T9. The engine then does not offer that task to that worker while the `disk_free_mib` of its newest `hb` is below the size of the inputs of the task.

## 14. Scheduler structures

### 14.1 Threads and tasks
* **Actor.** One scheduler actor on its own thread owns all scheduling state: tasks in memory, runs, classes, workers, attempt rows, queues, bitsets, histograms, timers. It reads one input queue of typed events: decoded messages, writer completions, submitter requests, timer ticks. A step takes up to 1,024 events, applies them, and hands the outbound messages to the connections. The actor blocks only on its input queue. It never spins and never touches JSON or shape bytes.
* **Connection tasks.** One task for each link, on the I/O runtime (`n_io` threads). It decodes frames into typed messages (a shape strictly, file 05), stamps `last_rx` of the worker (an atomic that the reaper reads, file 05), and forwards. It encodes outbound messages. It keeps the set of shape ids that it sent on the link and adds a shape to an offer only the first time. Shape bytes come from a shared read-only table.
* **Store writer.** One thread (file 11). The actor sends store commands with a rising sequence number on the writer queue. The writer reports the highest committed number. The actor then sends the replies that wait for a commit: `ack`, `submitted`, and offers that hold an `at_most_once` task.

### 14.2 Data structures
| Structure | Form | Size and cost |
| --- | --- | --- |
| Fit set of a worker | 4,096-bit bitset over class ids | 512 bytes; 5 MB at 10,000 workers |
| Ready set of a priority level | 4,096-bit bitset: classes with a ready task | 512 bytes for each level in use |
| Ready set of a run | 4,096-bit bitset | 512 bytes for each open run |
| Class queue | ordered map (B-tree) keyed `(run, group, idx)` to `task_id` | the head of a run is a range lookup |
| Class histogram | section 3.1 | 432 bytes; 1.7 MB at 4,096 classes |
| Fitting worker count | a counter for each class | updated when a fit bit changes |
| Pinned queue | FIFO for each worker | section 13 |
| Parked list | FIFO of parked workers | section 4.4 |
| Timer heap | min-heap of `(time, kind, id)` | lazy, below |

A pull computes its candidates as `fit AND ready(level)`, 64 machine words, then for the run that deficit round robin picks, `AND ready(run)`. It then tests lifetime, reservation and free capacity on each set bit. The cost is about 100 ns plus the tasks taken.

### 14.3 The lazy timer heap
All timed events share one heap: attempt deadlines, retry delays and `not_before_unix` (T2), `park_s`, `reserve_after_s`, lifetime marks. An entry is never removed when its object changes. At pop the actor checks the entry against the object: a deadline whose `last_rx` moved is pushed again with the new time; an entry for an ended row is dropped. The actor handles at most `expiries_per_step` (1,000) expiries in one step and yields. The store batches the rest like any other events.

Reason: a switch failure can expire 10,000 attempts in one tick; a bounded step keeps `hback` latency bounded.

### 14.4 Rebuild
A coordinator start fills the class queues from the id ranges of the open runs (file 11). A session starts empty.

## 15. Connections and reconnect storms

### 15.1 Connection count
At start the coordinator raises its soft `RLIMIT_NOFILE` to the hard limit and logs the result. `max_conns` is that limit minus 64. Above it, a new connection gets `err{busy, retry_after_ms}` and is closed. Pre-auth limits are in file 16.

### 15.2 After a coordinator restart
Each worker loses its link at the same time.
* `ready` carries `reconnect_jitter_ms` (file 04). The coordinator sets `reconnect_jitter_ms = clamp(1000 * W / accept_rate, 1000, silence_s * 1000 / 3)`. `W` is the count of enrolled workers that are not `revoked` or `retired`. `accept_rate` starts at 2,000 per second and follows the measured rate of complete handshakes.
* The worker stores `reconnect_jitter_ms`. After a link loss its first retry is uniform in `[0, reconnect_jitter_ms]`. Later retries use full jitter up to 30 s (file 04).
* Accept pacing: when the queue of connections that wait for their handshake, `hello` and first `hb` holds more than one second of `accept_rate`, the coordinator answers a new session with `err{busy, retry_after_ms}`, with `retry_after_ms` uniform in `[t, 2 * t]` and `t` the time to empty the queue at `accept_rate`.
* The first `hb` of each worker brings its full holding (file 05). The actor handles holdings within its step bound.

Reason: a storm that lasts longer than `silence_s` makes workers fence themselves (file 05). The upper bound of `reconnect_jitter_ms` keeps the storm inside `silence_s / 3`.

## 16. Throughput model

### 16.1 Symbols
| Symbol | Meaning |
| --- | --- |
| `t_sched` | actor CPU per task |
| `t_w` | writer CPU per task, without the fsync |
| `t_io`, `t_msg` | connection CPU per task row and per message (TLS, framing, decode, encode) |
| `n_io` | threads of the I/O runtime |
| `F` | fsyncs per second of the store disk |
| `B` | task rows per message (offer or result) |
| `m` | events in one commit |
| `bw`, `b_task` | link bytes per second; bytes on the link per task, both directions |
| `W`, `s`, `d`, `o` | workers, slots per worker, task time, worker cost per task |

### 16.2 Stages in series
A task passes each stage once. The stages run at the same time, so the slowest one sets the rate:
```
lambda = min(1 / t_sched,  1 / t_writer,  n_io / (t_io + t_msg / B),  bw / b_task)
```
The writer stage with natural batching: each task needs two store events (lease and end) of `B` tasks each, and each commit holds `m` events and costs one fsync:
```
lambda_store = 1 / ((2 / (m * B)) / F + t_w)
```
`m` grows with load, because the writer takes what queued during the last commit. At high load the fsync term vanishes and `lambda_store` tends to `1 / t_w`. At `batched` the commit holds no fsync and the bound is `1 / t_w` at each load. A session with no store has no writer stage.

Demand of the workers and the point where the authority becomes the limit:
```
lambda_demand = W * s / (d + o)
W_star        = lambda * (d + o) / s
```

### 16.3 The store bound with numbers
With `F = 300` (3.3 ms fsync) and `t_w = 16 us`:

| `m * B` | `lambda_store` |
| --- | --- |
| 1 (one idle worker, one task per offer) | 150 tasks/s |
| 200 | 20,300 tasks/s |
| 1,000 | 44,100 tasks/s |
| no limit | 62,500 tasks/s |

### 16.4 The link bound
The positional rows of file 05 carry about 40 bytes for an offered task and about 50 for a result row. With `pull`, `ack` and framing the budget is `b_task` = 100 bytes [T]. A 10 Mbit/s link then carries 12,500 tasks/s, and 1 Mbit/s carries 1,250. A large `input`, inline output or `extra` fields change `b_task` at once.

### 16.5 Worked examples for tiny workers
Worker: 4-core Cortex-A53, `s = 4`. Target A-06 gives at least 400 `true` tasks per second for one such worker, so `o` is at most 10 ms per slot for a `true` task [T].

| Case | Demand | Limit |
| --- | --- | --- |
| 100 workers, `d = 1 s` | `100 * 4 / 1.01` = 396 tasks/s | far below each bound; a Raspberry Pi coordinator (A-04, 2,000 tasks/s) serves `W_star = 2,000 * 1.01 / 4` = 505 such workers |
| 100 workers, `d = 10 ms` | `100 * 4 / 0.02` = 20,000 tasks/s | equal to A-01 on an x86_64 coordinator; a Pi coordinator saturates at 10 workers |
| link of the 100-worker case | 20,000 tasks/s * 100 bytes = 2 MB/s | 16 Mbit/s at the coordinator, 20 KB/s for each worker |
| 10,000 idle workers | `hb` at 1,000 messages/s | about 0.06 of one core [EV-006] |

For short tasks the authority is the limit long before the connection count. A user with tasks under 10 ms gets more from one task that runs many items than from more workers.

## 17. What the measurements support

The prototype coordinator ran a store schema with more row writes per task than file 11, with simulated workers on loopback, on one 8 vCPU host. Its numbers bound the stages of section 16. They do not measure this engine end to end.

| Measurement | Supports |
| --- | --- |
| Writer CPU 13 to 16 us per task with offers of 100 to 1,000 tasks; 74 us with one task per offer and 10 workers; actor CPU 3 to 7 us per task [EV-007] | `t_w` and `t_sched` in section 16; one actor is enough to about 140,000 tasks/s; the writer is the first CPU stage |
| The prototype throughput at `strict` (file 11, section 2) | A-01 (20,000 tasks/s at `strict`) is reachable with the store as the last limit |
| 10,000 TLS 1.3 and WebSocket connections in 2.24 s at a peak of 1.155 cores; handshake p50 409 ms, p99 2,051 ms; 194.3 MiB RSS and 10,011 descriptors [EV-026] | `accept_rate` of 2,000 per second as a start value; about 19.4 KiB per bare connection as a floor of A-15; one descriptor for each connection |
| A 50 ms commit timer (`batched`) against one commit for each fsync (`strict`): 95 against 680 tasks/s (10 workers, one task per offer), 919 against 6,052 (10 workers, offers of 10), 1,761 against 9,981 (200 workers, one task per offer) [EV-027] | no timer on any batching path: natural batching in the store (file 11) and self-clocked results (section 7) |
| A cap of 256 events per commit held throughput at 17,174 to 17,866 tasks/s at 1,000 and 10,000 workers with one task per offer, with `events_per_commit=256.0` [EV-028] | a commit cap well above the events of one fsync time (8,192, file 11) |
| An offer sent before its lease commit: 14,818 against 9,981 tasks/s, pull latency p50 0.21 ms against 8.99 ms (200 workers, one task per offer) [EV-029] | the I6 rule of section 8: only `at_most_once` offers wait for the commit |
| 10 workers with one task per offer reached 643 to 768 tasks/s, pull p50 about 6 ms | a small swarm with one task per offer is bound by latency; the depth rule of section 4 removes that bound |
| With the coordinator pinned to one CPU (`taskset -c 0`), the runs with offers of 10 and of 100 did not end before the timeout (`exit=124`) [EV-030] | nothing about one-core throughput; the cause is not known. It becomes a benchmark cell |

Benchmark cells that this file needs:
* B-15: coordinator pinned to one CPU, 200 simulated workers, offers of 1, 10 and 100. The actor and the writer block on their queues and never spin, so a single CPU serves both.
* B-05: utilisation of one worker with 4 slots through the shaping proxy (A-08).
* B-16 and M-35: 1,000 workers reconnect after a coordinator restart; no `self_fence`, each worker `ready` within `silence_s / 3`.
* M-24: tail reclaim returns `ceil(k / 2)` tasks to a parked pull.

## 18. Settings of this file

| Name | Default | Range | Meaning |
| --- | --- | --- | --- |
| `class_max` | 4,096 | fixed | live classes |
| `depth_min_s` | 1 | 0.1 to 10 | lower clamp of `T_q` |
| `depth_max_s` | 10 | 1 to 60 | upper clamp of `T_q` |
| `bundle_max` | 1,000 | 1 to 1,000 | task rows in one offer; 1,000 is the row limit of one message (file 05) |
| `offer_bytes_max` | 512 KiB | 16 KiB to 1 MiB | body of one offer |
| `hold_max_s` | 60 | 1 to 3,600 | unstarted work held by one worker, per slot |
| `park_s` | 20 | 1 to 60 | longest wait of a parked pull |
| `rtt_default_ms` | 100 | 1 to 10,000 | `R` with no measurement |
| `result_rows_max` | 1,000 | 1 to 1,000 | rows in one `result`; 1,000 is the row limit of one message (file 05) |
| `result_bytes_max` | 256 KiB | 4 KiB to 1 MiB | body of one `result` |
| `backpressure_age_ms` | 250 | 10 to 10,000 | age of the oldest store command that delays offers and acks |
| `backpressure_events` | 16,384 | 1,024 to 1,048,576 | queued store events that delay offers and acks |
| `drr_quantum` | 100 | 1 to 10,000 | credits for each unit of run weight at each round |
| `reserve_after_s` | 30 | 1 to 3,600 | skip time before a reservation |
| `drain_margin_s` | 60 | 0 to 3,600 | drain before the lifetime end |
| `assume_time_s` | 3,600 | 1 to 604,800 | `time_need` of a class with no `time_s` and no `timeout_s` |
| `idle_exit_s` | 300 with `ephemeral`, else 0 | 0 to 604,800 | idle time before a worker exits; 0 is off |
| `expiries_per_step` | 1,000 | 100 to 100,000 | timer expiries in one actor step |
| `accept_rate` | 2,000 per s, then measured | 10 to 100,000 | handshakes per second for `reconnect_jitter_ms` and pacing |
| `max_conns` | soft `RLIMIT_NOFILE` minus 64 | 64 to the limit | open connections |
| `rate` (`--rate`) | none | 1 and up, integer | task starts per second of one run |
| `retry_first` (`--retry-first`) | false | bool | retries go before new tasks of their group |
