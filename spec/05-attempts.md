# 5. Attempts: the process protocol

An attempt is one process tree on a worker. An authority starts it: the home of a session or the coordinator of a swarm. This file defines the shape (what to run and how), the messages that carry attempts over a link, attached and captured I/O, the terminal, reconciliation, the fence, limits and error codes. File 04 defines the link under these messages. File 09 defines the durable task above an attempt. File 10 defines how many attempts an authority offers and when. File 12 defines what the worker does with an attempt.

The same messages run in both directions of dialling. A worker that the home started over ssh and a worker that dialled a coordinator speak the same protocol.

## 1. The shape

A shape holds what many tasks share. A task adds its own input (file 09). A shape is one strict JSON object: an unknown field is an error, and a duplicate key is an error. The first field is `"schema": 1`. A shape has at most 65,536 bytes.

| Field | Type, default | Meaning |
| --- | --- | --- |
| `tmpl` | 0 or 1, default 1 | 0: no substitution. 1: the token grammar of file 18. The worker expands tokens with the task input. |
| `argv` | array of strings | Run with no shell. Exactly one of `argv` and `shell` is set. |
| `shell` | string | Run by the shell of the worker (file 12). |
| `env` | map | Extra environment variables. |
| `inherit_env` | boolean | Default by worker kind (file 12). |
| `cwd` | string | A relative path is inside the task directory or inside the view. An absolute path needs a view or `shared_fs`. |
| `io` | `capture` or `attached`, default `capture` | `capture`: the result carries a head and a tail of the output. `attached`: stdin, stdout and stderr are live streams to the caller (section 5). |
| `pty` | boolean, default false | With `attached`: the process runs on a terminal. |
| `merge` | boolean, default false | stderr goes to the stdout pipe. |
| `stdin` | null, `{"inline": text}` or `{"blob": id}` | Input for `capture`. Null means the null device. |
| `view` | object or null | The file view of the attempt (file 06). |
| `shared_fs` | boolean, default false | The path of `cwd` exists on the worker. Nothing is staged. |
| `files`, `outputs` | arrays | Staged inputs and returned outputs (file 15). |
| `needs` | object | What the task requires from a worker (section 2). |
| `limits` | object | `cpu_s`, `mem_mib`, `as_mib`, `fsize_mib`, `nofile`, `pids` (integers), `core` (boolean, default false: true lets the payload write a core file) (file 12). |
| `confine` | object | Grants of the `confined` boundary: `read`, `write`, `exec`, `connect`, `bind`, `udp`, `unix` (file 12). |
| `shell_always` | boolean, default false | Run a `shell` command by the shell also when it has no shell metacharacter (file 12). |
| `net` | string, default `pool` | The network policy (file 14). |
| `spread` | boolean, default false | Each process that the attempt starts can run on another machine (file 07). |
| `checkpoint` | object or null | Checkpoint and resume (file 15, section 11.2). |
| `capture_blob` | boolean, default false | The full output streams go to the content store as blobs (file 15). |
| `timeout_s` | integer or null | Wall limit of one attempt. |
| `kill_grace_s` | integer, default 10, range 0 to 600 | Time between the polite signal and the kill. |
| `silence_s` | integer, default 30, range 30 to 86,400 | The silence budget (section 8). |
| `ok_codes` | array of integers, default `[0]` | Exit codes that count as success. |
| `capture_max` | integer, default 16,384, at most 65,536 | Bytes kept per stream in a result. |

File 09 owns the queue fields of a shape: `retries`, `retry_delay_s`, `max_lost`, `delivery`, `priority`, `no_retry_codes`, `tags`. These names are reserved for later features and are refused with `unsupported` until their feature is negotiated: `secrets`, `sig`, `verify`, `speculate`, `image`, `after` (file 24).

An authority stores a shape once and gives it a `shape_id`. It sends a shape once per link. A worker keeps the shapes of a link in memory, at most 256 shapes or 4 MiB. When a worker does not hold a shape that an offer names, it answers the attempt with outcome `spawn_failed`, reason `shape`, and the authority sends the shape again with the next offer.

## 2. Needs

| Field | Meaning |
| --- | --- |
| `cores_m` | Millicores. Default 1000. |
| `mem_mib`, `disk_mib` | Default 0, which means not tracked. |
| `res` | Map of a resource name to a count, for example `{"gpu": 1}`. A worker declares what it has. |
| `tags_all`, `tags_any` | Worker tags. |
| `os`, `arch` | Lists of allowed values. |
| `shell`, `interp` | A shell kind, and an interpreter path that must exist (file 15). |
| `boundary` | `none`, `confined`, `sandbox` or `vm` (file 13). Default `none`. |
| `shield` | `none`, `private`, `guest` or `sealed` (file 13). Default: from the `trust` of the pool entry (file 08), by the table of file 13. |
| `exclusive` | The attempt takes the whole worker. |
| `limits_required` | Limits that the worker must enforce, not only report. |
| `worker` | A worker number. Set only by `podswarm each`. |
| `time_s` | Expected run time, for workers with a lifetime. Default `timeout_s`. |

Matching is in file 08 for one command and in file 10 for batches. A worker never runs an attempt whose needs it cannot meet. It answers `spawn_failed` with reason `isolation_refused` or `policy`.

## 3. Messages

Every message is one JSON object with a string field `t`. File 04 defines the frame around it. Hot messages carry positional rows: JSON arrays with a fixed order and an optional last object for rare fields. A receiver ignores an object field that it does not know and a trailing row element that it does not know. Numbers are integers. Time is a duration, except a field whose name ends in `_unix`.

| `t` | From | Fields |
| --- | --- | --- |
| `pull` | worker | `free{slots, cores_m, mem_mib, disk_mib, res}`, `unstarted`, `seen`, `rtt_ms?` |
| `offer` | authority | `no`, `shapes[{id, spec}]`, `tasks[row]`, `refill` (u32: the `unstarted` count at which the worker pulls again, file 10) |
| `hb` | worker | `seq`, `seen`, `hold[[task_id, attempt_no, st]]`, `load?{busy_m, own_m, mem_avail_mib, disk_free_mib}` (file 08), `blobs?` (at most 64 ids, file 15), `lifetime_s?` |
| `hback` | authority | `re`: the `seq` of the `hb` that it answers |
| `result` | worker | `batch[row]` |
| `ack` | authority | `items[[task_id, attempt_no, verdict]]` |
| `cancel` | authority | `items[[task_id, attempt_no]]`, `mode` |
| `signal` | authority | `task_id`, `attempt_no`, `sig` |
| `resize` | authority | `task_id`, `attempt_no`, `rows`, `cols` |
| `id_req` | worker | `task_id`, `attempt_no`, `aud`: a run identity token for a live attempt (file 17) |
| `id_rep` | authority | `task_id`, `attempt_no`, and `token` or `err` (an error code of section 11) |
| `ckpt_req`, `ckpt_commit`, `ckpt_ack` | authority; worker; authority | checkpoints (file 15, section 11.5) |
| `ckpt_key_req`, `ckpt_key` | worker; authority | the data key of a run with `encrypt = "run"`, sealed to the link key of the worker (file 15, section 11.10, D-126) |
| `bye` | both | `reason`: `home_exit`, `drain`, `lifetime`, `idle` or `done` |
| `err` | both | `code`, `text`, `fatal?` (default false), `id?` (the `req` it answers, section 9), `retry_after_ms?`, `items?`, `limit?`, `used?`, `scope?`, `reason?`, `asked?`, `max?`, `field?`, `cell?` (section 11) |

Rows:

* An `offer` task row is `[task_id, attempt_no, shape_id, idx, input, extra?]`. `extra` can hold `fields`, `tags`, `group`, `key`, `slot` (u32, the slot from 0, `TASK_SLOT` of file 12), `vepoch` (the view epoch, file 06), `ckpt` (the checkpoint to restore, file 15), `secrets` (file 24), and for an attached attempt `tty{rows, cols, term}` (`rows` and `cols` 1 to 65,535).
* A `result` row is `[task_id, attempt_no, outcome, code, signal, wall_ms, user_ms, sys_ms, rss_kib, extra?]`. `code` is the exit code (0 to 255) or null. `signal` is the number of the signal that ended the process (1 to 127), or null. `extra` can hold `reason`, `out` and `err` (each `{len, trunc, enc, head?, tail?, id?}`), `outputs[{path, id, size}]`, `boundary`, `shield` (the report of file 13), `view` (the rung, file 06), `residual`, `started_unix`.
* A `hold` row is `[task_id, attempt_no, st]` with `st` one of `q` (queued, not started), `r` (running), `d` (done, result not acknowledged).

Outcomes: `exited`, `signaled`, `timeout`, `spawn_failed`, `killed`, `cancelled`, `not_started`, `checkpointed` (file 15). File 09 maps each outcome and reason to a transition. Reasons of `exited`: `output_failed`, `output_rejected`, `ckpt_failed` (each a failure, file 15). Reasons of `signaled`: `mem_exceeded`, `cpu_exceeded`, `disk_full`, `area_full` (file 13) (a limit kill is a failure, D-22). Reasons of `not_started`: `disk` (file 15, section 3), `needs_key` (file 15, section 11.10); a `not_started` result may have no reason. Reasons of `killed`: `self_fence`, `drain`, `orphan_cleanup`, `lifetime`. Reasons of `spawn_failed`: `bad_argv`, `isolation_refused`, `policy`, `input`, `shape`, `other`.

Rules:

* `pull` reports the free capacity of the worker, the count of attempts it holds and did not start, and `seen`: the count of `offer` messages that the worker received on this link when it sent the `pull`. A link has one standing `pull` state, not a request and answer pair: each `pull` replaces the one before (D-51). The authority may send offers at any time, up to the capacity of the newest `pull` minus the tasks of each offer that it sent after offer number `seen` of that `pull` (D-125). An offer in flight when the worker wrote the `pull` is not in its free count, so without `seen` the authority offers one slot two times. So an authority starts a command at once on a worker that it dialled. How much it offers is in file 10.
* `offer.no` rises by one per offer on a link, from 1. An empty offer is legal. An offer has no `more` field. A worker that gets an attempt it already holds keeps the one it holds. When the rows do not fit one message, the authority sends several offers.
* Frame order: frames to one worker leave in the order in which the authority decided them. When an offer waits for its commit (file 11), a later frame that names one of its attempts waits behind it (D-20).
* `result` is self-clocked. A worker has at most one `result` that is not acknowledged. With none in flight it sends a finished attempt at once. With one in flight it collects rows up to `result_rows_max` and `result_bytes_max` (file 10), within the limits of section 10.
* `ack` goes out after the authority made the result durable at the level of the run (file 11). Verdicts: `accepted` (this result decided the task), `recorded` (stored, the task was decided before or it is a failure), `dropped` (the attempt is not known to the authority). The worker deletes the journal record of each row in an `ack`.
* `cancel` has mode `kill` (end the attempt with the kill ladder of file 12) or `unstarted` (give back the attempt only if it did not start). It is idempotent. The worker answers a `kill` with a result of outcome `cancelled`, and a cancel of an attempt that it did not start with outcome `not_started`. It ignores a cancel of an attempt that it does not hold.
* `signal` delivers a signal by name (`INT`, `TERM`, `HUP`, `QUIT`, `USR1`, `USR2`, `TSTP`, `CONT`, `WINCH`) to the foreground process group of an attached attempt. It is not part of the kill ladder.
* `bye` ends a link in order. A worker sends its results before it sends `bye`.

## 4. Life of an attempt on a link

1. The authority sends the attempt in an `offer`. Its row is `offered`. The worker lists it with `q`.
2. The worker starts it (file 12) and lists it with `r` in the next `hb`. The authority marks it `running`. No separate message reports a start. A worker may send an `hb` at once after a start when the attempt is attached.
3. The process tree ends. The worker writes the result to its journal, lists the attempt with `d`, and sends the `result`.
4. The authority records the result and sends `ack`. The worker forgets the attempt.

When the authority decides that a live attempt must end (a cancel, a success of another attempt, a wall deadline), the row is `stopping`: the authority sends `cancel{kill}` and waits until the row is known dead (file 09). A worker that does not confirm within `kill_grace_s + 2 * hb_s` is disconnected and marked `suspect`.

## 5. Attached I/O and the terminal

An attempt with `io = attached` has live streams. Each is one bulk stream of the link (section 7) with the header `{"t":"io","task_id":N,"attempt_no":N,"ch":C,"offset":N}`. `ch` is `stdin`, `stdout`, `stderr` or `tty`.

* The authority opens the `stdin` stream when it sends the offer. It closes its write side at end of input. The worker closes the stdin of the process then.
* The worker opens `stdout` and `stderr`, or one `tty` stream that carries both directions, when it starts the attempt. A stream ends when the process tree closed that descriptor.
* The credit window of each stream is the flow control. A caller that does not read stops that one process, as a local pipe does. Nothing is written to a spill file for an attached attempt while the link is up.
* With `pty` the worker runs the process on a terminal (file 12). The offer carries `tty{rows, cols, term}`. The caller sets its own terminal to raw mode and passes bytes through. Keys such as Ctrl-C become signals on the worker, by the terminal there. `resize` carries each change of the window size.
* Without `pty` the caller forwards the signals it receives (`INT`, `TERM`, `HUP`, `QUIT`) with `signal`.
* The exit status reaches the caller in the `result` row. File 18 maps it to the exit code of `podswarm run`.

Reattach. After a link cut the attempt keeps running until its fence (section 8). The worker keeps the output that it could not send, up to `spill_max` (file 12), and then stops reading the pipes. When the link is back (file 04), each side opens its streams again with the `offset` of the first byte that the other side did not confirm. The caller sees no gap and no repeated byte. A cut shorter than the silence budget does not end the command.

`io = capture` needs no stream. A reader that wants the output of a captured attempt while it runs asks with `logs` (section 9), and the authority asks the worker to open `stdout` and `stderr` streams with `offset` 0. That reader gets a spill file on the worker when it is slow, so it never stops the process.

## 6. Reconciliation

Each `hb` carries the full list of the attempts that the worker holds. The authority compares it with its rows for that worker. This one rule replaces separate messages for a start, a release, a resume after a cut, and a confirmation of a cancel.

For each row of this worker that is `offered`, `running` or `stopping`:

| The `hb` shows | Action |
| --- | --- |
| present, `q` | none |
| present, `r` | the row becomes `running` (T5 of file 09) |
| present, `d` | none: the result is on its way |
| present, and the row is `stopping` | send `cancel{kill}` again |
| absent, and the row's `offer.no` is at most `seen`, or the row is older than this link | an `offered` row was not started (T9); a `running` row is lost (T8); a `stopping` row becomes `ended` |
| absent, and the row's `offer.no` is above `seen` | none: the offer is in flight |

For each entry of `hold` that matches no such row of this worker, the authority sends `cancel{kill}`. This covers an attempt whose lease the store lost in a crash (file 11) and an attempt of an older store generation.

`seen` is the highest `offer.no` that the worker received on this link; offers are numbered from 1 with no gap, so it is the same count as `pull.seen`, read at the time of the `hb`. The first frame of a worker on a new link is an `hb`. The authority sends no offer on a link before it processed that `hb`. A resume after a cut and a restart of the authority need no other step.

An `hb` has at most 8,192 `hold` rows. A worker that holds more stops pulling.

## 7. Bulk streams

Every stream of the link other than the control stream carries one transfer. It starts with one JSON line of at most 4,096 bytes, ended by a newline, and then carries raw bytes. A close of the write side is the end of data.

| `t` of the header | Opened by | Content |
| --- | --- | --- |
| `io` | section 5 | a stream of an attached or followed attempt |
| `blob_put`, `blob_get` | either side | one blob. `blob_put`: `id` (`b3:`), `size`, `offset`, `enc` (`raw` or `zstd`). `blob_get`: `id`, `offset`, `len?`, `enc` (file 15, section 2) |
| `view` | either side | the file view protocol, with `ws`, `ch`, `prio` (file 06) |
| `net` | worker; the authority toward a member worker (D-79) | one network flow of an attempt, with `task_id`, `attempt_no`, `proto`, `dst`, `member` (file 14) |
| `exec` | either side; the authority relays it to the member | one moved process of a spread session, with `sess` (u64), `proc` (u64), `role` (`stub` or `member`), `rx`, `tx` (file 07) |

A transfer that a cut ended starts again on a new stream with an `offset`. The link gives each stream its own credit window (file 04), so a large transfer does not delay a control message by more than one frame of data.

## 8. The fence

A worker must not keep an attempt alive when its authority cannot know about it. The authority must not start a second attempt while the first can still run. Two timers on two clocks give that order, and the clocks are never compared.

Worker side. `t_ok` is the time at which the worker sent the newest `hb` whose `hback` arrived. For each attempt the worker sends the polite signal at `t_ok + silence_s` and kills the tree at `t_ok + silence_s + kill_grace_s`. Only an answered `hb` moves `t_ok`. `ready` does not move it: the first frame after `ready` is an `hb` (section 6), and the authority answers it from memory, so `t_ok` moves one round trip after `ready`. An attempt whose fence ends inside that round trip ends as `self_fence`. The worker sends `hb` every `hb_s` and never skips one. After the polite signal of the fence the attempt ends with outcome `killed`, reason `self_fence`, whatever arrives later. The worker gives each new `t_ok` to its spawner, and the spawner kills each tree at the same deadline by itself (file 12). So the fence holds when the worker is stopped or stalled.

Authority side. `last_rx` is the time at which the authority read the newest frame of that worker from the socket. A connection task stamps it at the read, before any queue. The attempt deadline is `last_rx + silence_s + kill_grace_s + grace_eff`, with `grace_eff = grace_s + ceil(e_max * (silence_s + kill_grace_s))`. At the deadline the row is known dead. The reaper reads `last_rx` again before it ends a row. `hback` is answered from memory and never waits for the store. After a start of the authority, `last_rx` of every worker is the start time, so each worker has a full budget to come back.

Why the order holds. The authority read the answered `hb` after the worker sent it, so `last_rx` is not before `t_ok` in real time. The worker kills at `t_ok + silence_s + kill_grace_s` by its clock. The authority waits `grace_eff` longer by its clock. With a clock rate error under `e_max` the gap is at least `grace_s` minus the time a kill takes.

| Setting | Default | Range | Set by |
| --- | --- | --- | --- |
| `hb_s` | 10 | 2 to 60 | authority, in `ready` |
| `silence_s` | 30; 300 for a task of a service job | 30 to 86,400 | shape |
| `kill_grace_s` | 10 | 0 to 600 | shape |
| `grace_s` | 10 | 1 to 60 | authority |
| `e_max` | 1 percent | 0.01 to 5 percent | authority |
| `rtt_max` | 5 s | 1 to 30 s | authority |

An authority refuses a shape with `silence_s < 2 * (hb_s + rtt_max)`.

The fence clock counts the time that the machine is asleep. A clock that stops in suspend lets a laptop worker wake with its deadline still ahead while the authority gave the task away.

| System | Fence clock |
| --- | --- |
| Linux, Android | `CLOCK_BOOTTIME` |
| macOS | `CLOCK_MONOTONIC` |
| Windows | `QueryInterruptTimePrecise` |
| FreeBSD | `CLOCK_MONOTONIC`, and all fences expire when the wall clock jumps ahead of it by more than 2 s |

The worker checks its deadlines on a tick of 1 s that reads this clock. It does not use a sleep timer of the async runtime for the fence. The authority can use any monotonic clock: a clock that stops makes it wait longer, which is safe.

Residual: a process in an uninterruptible wait can outlive a kill. A worker on containment rung `session` cannot promise that the whole tree is dead (file 12). A queued `at_most_once` task is offered only to a rung that can (D-49). An attached command of `podswarm run` is exempt: its caller watches it, and it is never offered again.

## 9. Operations of a submitter

A submitter (the CLI, a script, an agent) talks to a coordinator with requests on the control stream. In a session the CLI calls the home in the same process or through the socket of the holder (file 04), with the same operations. A worker uses the same `req` and `rep` form on its link for `blob_have` (file 15).

* A request is `req{id, op, ...}`. `id` is a u64 that the client chooses, unique on the link while the request is open.
* A success is `rep{id, ok, ...}` with `ok` always true. A failure is `err{id, code, text, ...}` with the fields of section 3. A field marked `?` is optional; an absent reply field is empty.
* A subscription sends `event{sub, ev}`: `sub` is the `id` of the `watch` request, and `ev` is one event document of file 17, section 1. `err{id, code: "busy"}` with that `id` ends the subscription (section 10).
* `sel` is a selector object, the wire form of the selector of file 18: `ids?` (task ids), `run?` (a run id or a run name), `tags?` (`K:V` strings), `where?` (`FIELD OP VALUE` strings), `state?`, `group?` (u32), `worker?` (a `wid`), `all?` (boolean). Its parts combine with AND. `cancel`, `retry` and `update` refuse an empty selector without `all` with `bad_request`.
* Run fields (`submit`, `run_new`): `name?`, `weight?`, `priority?`, `max_running?` (file 09, section 19), and `halt?{n?, pct?, mode?}`: halt at `n` failed or lost tasks, or at `pct` percent (1 to 100), never both; `mode` is `drain` (default) or `now`.
* `dry_run?` (boolean) on `cancel`, `retry` and `update` changes nothing and answers `count` and `ids`.

| `op` | Request fields | Reply fields | Scope |
| --- | --- | --- | --- |
| `submit` | `run_id?` (an open run; absent: a new run with the run fields), `shapes[]`, `tasks[[shape_ref, idx, input, extra?]]` | `run_id`, `first_task_id`, `dup[[pos, task_id]]` | `submit` |
| `run_new` | run fields | `run_id` | `submit` |
| `run_close` | `run_id` | none | `submit` |
| `ls` | `what` (`tasks`, `runs` or `workers`), `sel?`, `fields?[]`, `limit?` (1 to 1,000, default 1,000), `cursor?` | `rows[]` (one object per row with the asked fields), `cursor?` (absent at the end) | `read` |
| `show` | `task_id` | `task` (the task fields and state fields of file 09, section 3.2), `attempts[]` (the attempt rows of file 09, section 6), `result` (the `run.result` document of file 17, section 1, or null) | `read` |
| `cancel` | `sel` | `count` | `submit` |
| `retry` | `sel`, `only?` (`failed`, `lost` or `cancelled`), `fresh?`, `force?` | `count` | `submit` |
| `update` | `sel`, `action` (`hold`, `release`, `tag`, `untag`, `priority`, `pause`, `unpause`, `pin`, `unpin` or `purge`), `value?` (`K:V` for `tag`, `K` for `untag`, an i32 for `priority`) | `count` | `submit` |
| `watch` | `sel?`, `since?` (u64, an event sequence) | none; then `event` messages of tasks, runs and workers | `read` |
| `logs` | `task_id`, `attempt_no?` (default the newest), `stream` (`stdout` or `stderr`), `offset?` (default 0), `follow?` (default false) | none; then one `io` stream (section 5) | `read` |
| `attach` | `task_id` of a task with `io = attached` | none; then the `io` streams of section 5 and the `view` streams of the attempt (file 08, section 9), relayed | `submit` |
| `ckpt_save` | `task_id`, `label?`, `pin?` | `name`, after `ckpt_ack` (the authority sends `ckpt_req`, file 15) | `submit` |
| `ckpt_ls` | `task_id` | `rows[]` (the checkpoint rows of file 15, section 11) | `read` |
| `ckpt_show` | `name` | `row` (one checkpoint row with its `manifest`) | `read` |
| `ckpt_pin` | `name`, `pin` (boolean: pin or unpin) | none | `submit` |
| `ckpt_rm` | `name` | none | `submit` |
| `ckpt_export` | `name` | `manifest`, `ids[]` (the blob ids to fetch with `blob_get`) | `submit` |
| `ckpt_import` | `task_id` (the task that resumes from it), `manifest`; the blobs are sent first with `blob_put` | `name` (D-88) | `submit` |
| `usage` | `since?` (u64 event sequence), `since_unix?`, `by?` (`submitter`, `run`, `tag:K` or `boundary`) | `rows[]` (file 17, section 9), `next` (the sequence to ask next) | `read`; every run with `admin` |
| `blob_have` | `ids[]` (`b3:` ids, at most 10,000) | `have[]` (the ids that the owner holds) | `read` |
| `blob_put`, `blob_get` | no `req`: a bulk stream of section 7 | the answer line of file 15, section 2 | `submit`; `read` |
| `invite_new` | `uses?`, `ttl_s?`, `tags?[]`, `max_cores?`, `max_slots?`, `max_boundary?`, `approve?`, `worker_ttl_s?`, `ephemeral?` (file 16, section 7.3) | `invite_id`, `token` (the `psw1.` string) | `admin` |
| `invite_ls` | none | `rows[]` (`invite_id`, `uses`, `expires_unix` and the rules) | `admin` |
| `invite_revoke` | `invite_id`, `cascade?` | `count` (workers revoked) | `admin` |
| `worker_drain`, `worker_undrain`, `worker_revoke`, `worker_approve` | `wid` or `sel` | `count` | `admin` |
| `worker_tag` | `wid` or `sel`, `add?[]`, `remove?[]` (tags) | `count` | `admin` |
| `submitter_add` | `key` (a public key in hex or a `SHA256:` fingerprint), `name?`, `scopes?[]`, `routes?[]`, `quota?` (map of a quota name of file 16, section 8.3, to a u64), `id_aud?[]` | `fingerprint`, `connect` (the `psw1s.` string) | `admin` |
| `submitter_ls` | none | `rows[]` | `admin` |
| `submitter_rm` | `fingerprint` | none | `admin` |
| `org_add` | `key` (hex), `name`, `max_scopes[]`, `routes[]`, `max_life_s`, `allow_admin?` (file 16, section 9.4) | none | `admin` |
| `org_ls` | none | `rows[]` (trust entries) | `admin` |
| `org_rm` | `key` | none | `admin` |
| `org_revoke` | `member` (a `SHA256:` fingerprint) | none | `admin` |
| `status` | none | `counters` (map of a counter name to a u64) | `read` |
| `gc` | none | `counts` (map of a kind to the count removed) | `admin` |
| `version` | none | `sw`, `proto`, `features[]` (file 04, section 9) | `read` |

`shape_ref` is an index from 0 into `shapes[]` of the same message, or the `b3:` id of a shape that the owner stored (file 09). A `dup` entry names the position in `tasks[]` of a row whose `(run, key)` exists, and the `task_id` of the existing task (file 09, section 14). The new tasks take consecutive ids from `first_task_id` in the order of `tasks[]`, without the `dup` rows. `submit` has at most 4 MiB per message. The reply goes out after the commit.

`podswarm run` with a coordinator as its authority sends `submit` with one task of `io = attached`, then `attach` on that task. The coordinator relays the `io` streams, and the caller serves the `view` streams of the attempt. In a session the home opens the streams of section 5 itself.

The scope column is the scope of file 16, section 8.2, for the key's own runs. Admin operations also take the local socket of the coordinator. There is no operation that runs SQL (file 11).

## 10. Limits

| Item | Limit |
| --- | --- |
| Control message before `ready` | 4,096 bytes |
| Control message after `ready` | 1 MiB; 4 MiB after inflation |
| Shape | 65,536 bytes |
| Task record (`input`, `fields`, `tags`) | 16,384 bytes |
| Rows in one `offer` | 1,000 |
| Rows in one `result` | 1,000 or 256 KiB |
| Rows in one `hb` | 8,192 |
| `submit` message | 4 MiB |
| Header line of a bulk stream | 4,096 bytes |
| Head and tail of one output stream in a result | `capture_max`, at most 65,536 bytes |
| Tag key or value | 120 characters of `[A-Za-z0-9_.+-]` |
| Reason text | 200 bytes, control characters escaped |

A result with both streams at the largest `capture_max` is under 400 KiB as base64, so one result always fits one message.

State that an authority or a worker holds for one peer has a cap. This is the one list; the home of each cap is in the last column.

| State | Cap | At the cap | Home |
| --- | --- | --- | --- |
| standing `pull` | one per link; a new `pull` replaces it | none | section 3 |
| shapes held by a worker | 256 shapes or 4 MiB per link | `spawn_failed`, reason `shape` | section 1 |
| `result` not acknowledged | one message per link | rows wait in the journal | section 3 |
| attempts held by a worker | 8,192 `hold` rows | the worker stops pulling | section 6 |
| worker journal | records of the attempts held; a `gen` change deletes it | as the row above | file 12, section 14 |
| bulk streams | `max_streams` per link | a new stream waits | file 04, section 7.2 |
| blob transfers | 2 per direction of a worker; 2 partial files and 8 GiB of partial data per link | a transfer waits | file 15, section 2 |
| subscriptions (`watch`, `logs` with follow) | 16 per link, 4,096 queued events each | `err{busy}` ends the subscription; the client subscribes again with `since` | this section |
| attempts of one task | 1,000 | `failed`, reason `attempt_cap` | file 09, section 7 |
| live classes, live shapes | 4,096 and 65,536 per owner | `too_large` or `quota` | file 09, section 3.4 |
| audit rows of `dropped` results | one per worker and minute, with a count | rows merge | file 09, section 10 |
| connections, handshakes | `max_conns`; per prefix | `busy`; a ban | files 10, 16 |

A cancel for a worker with no session is not queued: the next `hb` that lists the row gets it (section 6).

`ready.limits` (file 04) gives these limits by name: `msg`, `inflate`, `offer_rows`, `result_rows`, `hb_rows`, and the size limits `blob_max_mib` (file 15), `max_blob_mib`, `max_ckpt_mib`, `max_spec_bytes` and `max_output_bytes` (the quotas of the key, file 16, section 8.3). Each value is a non-negative integer. A setting of file 10 that sizes offers or result batches never passes a limit of this table.

## 11. Error codes

The class is the `pod_core::Class` that gives the exit code of the CLI (file 19).

| Code | Meaning | Class |
| --- | --- | --- |
| `bad_request` | a message or a field is not valid | Usage |
| `bad_state` | a command that the state of the task refuses | Usage |
| `attempt_live` | `retry` while an attempt is live or stopping | TempFail |
| `unauthorized` | the key is not known, or an enrol failed for any reason | Refused |
| `revoked` | the worker or the key was revoked | Revoked |
| `duplicate_identity` | another live process uses this worker identity | Refused |
| `unsupported` | a protocol number, a feature or a reserved field | Unsupported |
| `busy` | too many connections, a full queue or a class bound that is reached; `retry_after_ms` says when | TempFail |
| `too_large` | a message or a field over its limit | Protocol |
| `policy` | a worker policy or a submitter scope refused | Policy |
| `needs_unsatisfiable` | no worker of the pool can ever meet the needs | Policy |
| `shield_unavailable` | the machine cannot give the asked shield; fields `asked`, `max`, `reason`, `field?` (file 13) | Policy |
| `no_cell` | a cell selector matches no cell (file 08) | Policy |
| `wrong_cell` | the work belongs to another cell; field `cell` names it, and the client looks it up in its own pool file (file 08) | Usage |
| `quota` | a quota of the submitter is spent; `limit`, `used`, `scope` say which | Refused |
| `not_found` | a task, a run, a worker or a blob that does not exist or is not yours | NotFound |
| `internal` | a defect | exit 70 |
