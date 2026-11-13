# 9. Queue: durable work

This file defines the durable work model: identifiers, the task record, task states, attempts as the queue sees
them, the transitions T1 to T11, the invariants I1 to I7, the delivery contract, retry, cancel, groups, arrays,
runs and workers. File 05 owns the shape fields that describe how a process runs, the messages, the fence and
the clocks. File 10 drives workers from this model. File 11 maps the records to the store.

## 1. Scope

The authority (file 03) is the only writer of these records. In a swarm the authority is the coordinator and the
records live in its store. In a session the authority is the home and the records live in its memory.

A command of `podswarm run` is a task of this model: one shape, one task, one attempt with attached I/O,
`delivery = at_most_once` and `retries = 0`. The home keeps the record in memory, and the record ends with the
session. The rules of this file apply to it. The store rules (lease commit, `strict`) apply only to an authority
with a store. File 05 gives the attached attempt and the rules of this file that an attached task does not use.

## 2. Identifiers

| Name | Type | Rule |
| --- | --- | --- |
| `run_id`, `task_id`, `job_id` | u64 | Made by the authority. They rise and are never reused, also after a purge. The tasks of one submit message get contiguous ids. `job_id` is for the jobs extension (file 24). |
| `attempt_no` | u32 | Starts at 1 for each task. Rises by 1 at each offer (T4). |
| `shape_id` | u32 | One per stored shape of an owner. |
| `wid` | u32 | Worker number. Made at enrol in a swarm (file 16), and by the home from 1 in a session (file 04). |
| worker key | Ed25519 public key | The identity of a worker. Fingerprint: `SHA256:` plus base64 of the SHA-256 of the key, the format that `pod-identity` defines. A person compares the display form of `pod_identity::DisplayFingerprint`. |
| `gen` | 16 lowercase hex characters | The generation of the store (file 11). |
| `offer_no` | u64 | Per link of a worker, from 1 (file 05). |
| `key` | string | Optional. 1 to 128 characters of `[A-Za-z0-9._-]`, not `.` and not `..`. Unique in its run. |

At a new generation the next `task_id`, `run_id` and `job_id` rise by 2^32. A result of an old generation then
cannot name a task of the new one. An identifier is never a path component, except a decimal number.

## 3. Shape and task

A **shape** holds what many tasks share. A **task** is a shape plus its own input. The authority stores each
shape once per owner, found by its content id (`b3:`, file 15), and each task as a small record that names its
shape. File 05 owns every other shape field (what runs and how), the template rules and the shape size limit.

### 3.1 Queue fields of the shape

| Field | Type | Default | Rule |
| --- | --- | --- | --- |
| `retries` | u32, 0 to 1,000 | 0 | Failures allowed after the first attempt (section 15). |
| `retry_delay_s` | u32, 0 to 3,600 | 2 | Base of the retry delay (section 15). 0 retries at once. |
| `max_lost` | u32, 0 to 1,000 | 5 | Losses allowed (T8). |
| `delivery` | `at_least_once` or `at_most_once` | `at_least_once` | Section 11. |
| `priority` | i32, -100 to 100 | the run priority | Higher runs first (section 17). |
| `no_retry_codes` | list of exit codes | `[]` | An `exited` result with such a code ends the task `failed`. |
| `tags` | map name to value | `{}` | Section 3.3. |
| `needs` | object | section 4 | What a worker must have. |

`ok_codes` (file 05) selects success: an `exited` result with a code in `ok_codes` is a success. A submit with a
code in both `ok_codes` and `no_retry_codes` gets `bad_request`. A submit with `delivery = at_most_once` and
`retries > 0` gets `bad_request`. The class of a shape is `hash(needs, priority)`. It is stored with the shape.

The extension fields `secrets`, `sig`, `verify`, `speculate`, `image` and `after` are reserved. A submit that
sets one gets `unsupported` until its feature is negotiated (file 24). The task fields `kind`, `verifies`, `avoid`,
`up_task` and `up_attempt` are reserved in the same way for the extensions of file 24.

### 3.2 Task fields

| Field | Type | Rule |
| --- | --- | --- |
| `shape` | `shape_id` | The shape of the task. |
| `idx` | u32 | Position of the task in its run, from 0. A retry keeps it. |
| `input` | string | The input line. For an array task, the array index in decimal. |
| `fields` | object | The `--from-json` keys and the trailer keys (file 18). |
| `tags` | map | Tags of this task. They add to the shape tags and win on the same name. |
| `group` | u32, default 0 | Stage number (section 18). |
| `key` | string or absent | Idempotency key (section 14). |
| `not_before_unix` | unix seconds or absent | The task stays `waiting` until this time. |
| `deadline_unix` | unix seconds or absent | A task that has not started by this time is cancelled with reason `expired` (T10). |

The authority adds the state fields: `run_id`, `state`, `attempts` (the last `attempt_no`), `failures`, `losses`,
`reason` (why a terminal state holds), `result_no` (the attempt of the deciding result), `late_ok`, the creation
time and the end time. Both unix fields use the wall clock of the authority.

### 3.3 Tags

A tag name and a tag value are each 1 to 120 characters of `[A-Za-z0-9_.+-]`. A tag with no value is a name
alone; on the wire it has the empty string as its value. The CLI writes a tag as `K:V`. The worker exports each tag as `TASK_TAG_<name>` (file 12). Selectors of
`ls`, `cancel`, `retry` and `update` match tags (file 18).

### 3.4 Limits

A task record is at most 16,384 bytes. An authority holds at most 4,096 live classes and 65,536 live shapes per
owner. A submit over a limit gets `too_large` or `quota`. A class or a shape is live while a non-terminal task
uses it.

## 4. Needs and named resources

`needs` is the part of the shape that selects a worker. Files 08 and 10 do the matching. A task states:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `cores_m` | u32 | 1000 | Millicores reserved while the attempt is open. The CLI accepts `2` and `0.25`. |
| `mem_mib`, `disk_mib` | u32 | 0 | Memory and disk reserved. 0 means not tracked. |
| `res` | map name to u32, 1 to 1,000,000, at most 16 names | `{}` | Named countable resources, for example `gpu: 1`. A name follows file 08, section 5. |
| `tags_all`, `tags_any` | list of tags | `[]` | The worker has every tag of `tags_all` and one of `tags_any`. |
| `os`, `arch` | list of strings | any | Allowed values. `arch` takes the values of `caps.arch` (file 08, section 2.1); the CLI maps `uname -m` names to them. |
| `shell`, `interp` | string | any | Shell kind and program interpreter the worker must have. |
| `boundary` | `none`, `confined`, `sandbox`, `vm` | `none` | The weakest boundary the task accepts (file 13). |
| `shield` | `none`, `private`, `guest`, `sealed` | from the pool `trust` of the machine (files 08, 13) | The weakest shield the task accepts (file 13). |
| `exclusive` | bool | false | The task takes the whole worker. |
| `limits_required` | list of limit names | `[]` | Refuse a worker that only reports these limits. |
| `worker` | `wid` | absent | Set only by `podswarm each` (file 10). |
| `time_s` | u32 | `timeout_s` | Expected run time, for lifetime matching (file 08). |

A worker never runs a task on a weaker boundary than `needs.boundary` or a weaker shield than `needs.shield`. Accounting is declared: the task states
its needs, and the authority reserves them. File 08 says when a submit gets `needs_unsatisfiable`.

## 5. Task states

| State | Terminal | Meaning |
| --- | --- | --- |
| `held` | no | A person holds it, or it waits for a data key (reason `needs_key`). The scheduler skips it. |
| `waiting` | no | Blocked by its group, `not_before_unix` or a retry delay. |
| `ready` | no | In the ready queue of its class. |
| `leased` | no | Offered to a worker. Not known to run. |
| `running` | no | A heartbeat showed the attempt running. |
| `succeeded` | yes | A success is accepted. |
| `failed` | yes | A failure that does not retry, or a budget is spent. |
| `cancelled` | yes | A person, a run cancel, a halt or `deadline_unix` ended it. |
| `lost` | yes | An `at_most_once` task whose attempt ended with no result. It needs a person. |

A terminal state is final. Only the `retry` command (T11) leaves it. No result changes a terminal state.
The store holds `ready` for a `leased` or `running` task, and the lease record names its attempt. The authority
answers `ls` with the live state from memory.

## 6. Attempts as the queue sees them

An attempt is one try of a task: one process tree on one worker (file 12). In memory each attempt row has one of
four states:

| Row state | Meaning |
| --- | --- |
| `offered` | The offer went to the worker. No heartbeat showed it running. |
| `running` | A heartbeat showed it running. |
| `stopping` | The authority decided that the attempt is over and waits until the row is known dead (section 9). |
| `ended` | The row is known dead. The end is recorded. |

An **open row** is a row that is `offered`, `running` or `stopping`. An open row keeps its worker capacity
reserved. The core has no second open row per task (I4), so it has no sibling rows. The speculation extension
(file 24) adds rows and the sibling rules: the task state after one row ends, and a failure of any row decides.

`end_kind` of an ended row:

| `end_kind` | Set when |
| --- | --- |
| `exited`, `signaled`, `timeout`, `spawn_failed`, `killed`, `cancelled`, `not_started`, `checkpointed` | the worker reports that outcome |
| `lost` | the row is known dead with no result: its attempt deadline passed, or the holding of its worker lacks a `running` row |
| `superseded` | a stopping row of a task that another attempt made `succeeded` ends |

`killed` reasons: `self_fence`, `drain`, `orphan_cleanup`, `lifetime`. `spawn_failed` reasons: `bad_argv`,
`isolation_refused`, `policy`, `input`, `shape`, `other`. A `lost` row carries reason `attempt_deadline`, `absent` or
`wall_deadline`.

What the store holds: one lease record per offer, which lists its attempts, and one attempt record per ended
attempt, written when the attempt ends. A late result of an attempt that ended as `lost` updates that record once
(file 11). The record holds `wid`, `end_kind`, reason, `code`, `signal`, `wall_ms`, `user_ms`,
`sys_ms`, `rss_kib`, the output summary (file 15) and `accepted`. The row states `offered`, `running` and
`stopping`, the time a heartbeat first showed the row running, and the offer number live in memory only.

## 7. Transitions

T4 is the only transition that makes an attempt row. Its guard "no open row" keeps I4 by itself. The other
transitions make no row, so I4 holds through them. T11 refuses early so that a `ready` task can always take T4.

| # | From to | Trigger | Guard | Effect |
| --- | --- | --- | --- | --- |
| T1 | none to `held`, `waiting` or `ready` | `submit` | The task is valid; its `(run, key)` is new; the run is open. | Insert the task. Start state: `held` when the submit asks for it; else `waiting` when the group is above the active group (section 18) or `not_before_unix` is in the future; else `ready`. Durable before `submitted` (I6). |
| T2 | `waiting` to `ready` | a timer passes (`not_before_unix`, retry delay), or the group gate opens | Every timer of the task passed; the group is at or below the active group; the run is not halted. | Into the ready queue of its class. |
| T3 | `waiting` or `ready` to `held`; `held` to `waiting` or `ready` | the `hold` command; the `release` command | none | `hold` takes the task out of the ready queue. `release` picks the state by the rule of T1. |
| T4 | `ready` to `leased` | the scheduler offers the task to a worker (file 10) | The task has no open row; the run is not paused and not halted; the open rows of the run are fewer than `max_running`; the worker is `active` and fits (files 08, 10). For `at_most_once`: the worker is not `suspect`, and its containment rung is not `session`. | `attempts + 1`; a row `offered` with the new `attempt_no` for that worker; the lease record. For `at_most_once` the lease commit comes before the offer frame (section 11). |
| T5 | `leased` to `running` | a heartbeat of the holder shows the row `r` (file 05) | The row is `offered`. | Row `running`; note the time for the wall deadline. Memory only. |
| T6 | any non-terminal state to `succeeded` | a success result (section 8) for attempt `a` | The task is not terminal; the sending worker held attempt `a` (section 10). | Row `a` ends with `accepted = 1`; `result_no = a`. Another open row becomes `stopping` and gets `cancel{kill}`. The task leaves the ready queue and the timers. Group gate and halt policy are checked. |
| T7 | `leased` or `running` to `waiting` or `failed` | a failure result (section 8) for the open row | The row is `offered` or `running`. | Row ends; `failures + 1`. To `waiting` with the retry delay when the outcome allows a retry and `failures <= retries`; else `failed`, reason `retries` or `no_retry`. |
| T8 | `leased` or `running` (a new generation: any non-terminal state) to `waiting`, `failed` or `lost` | loss of the open row: known dead with no result (section 9), a loss result (section 8), any non-success result for a row that is `stopping` by the wall deadline, or a new generation for an `at_most_once` task | The task is not terminal. | Row ends. `at_least_once`: `losses + 1` unless the reason is `drain` or `lifetime`; to `waiting` with delay 0 while `losses <= max_lost`, else `failed`, reason `lost_budget`. `at_most_once`: to `lost`. |
| T9 | `leased` or `running` to `ready` | not started: a `not_started` result (or `spawn_failed`, reason `shape`) for the row, or the holding of its worker lacks the `offered` row (section 9); or a `checkpointed` result for the open row (file 15) | For not started: no heartbeat showed the row running. | Row ends with the reported outcome, or `not_started` for an absent row. No budget changes. For `at_most_once` see section 11. |
| T10 | any non-terminal state to `cancelled` | the `cancel` command, a run cancel, a halt, `deadline_unix`, the end of the worker of a pinned task (reason `worker_gone`, file 10) | The task is not terminal. `deadline_unix` acts only in `held`, `waiting`, `ready` and `leased`. | The task leaves the ready queue and the timers. An open row becomes `stopping` and gets `cancel{kill}`; a row that is `stopping` gets `cancel{kill}` again. |
| T11 | `failed`, `lost` or `cancelled` to `ready` or `waiting` | the `retry` command | No open row, else `err{attempt_live}`. `attempts` is below 1,000, else `err{bad_state}`. | `failures = 0`, `losses = 0`, `reason`, `result_no` and `late_ok` cleared. The state follows the rule of T1. A halted run is no longer halted. |

Shared rules:
* Attempt cap: a task has at most 1,000 attempts. When T7, T8 or T9 would return a task with 1,000 attempts to
  `waiting` or `ready`, the task goes to `failed` with reason `attempt_cap`.
* Reason `needs_key` (D-126, file 15, section 11.10): an attempt of a run with `encrypt = "run"` that ends
  `not_started` because no home of the submitter answered `ckpt_key_req` takes T9 to `held` with that reason, not
  to `ready`. When a home of the submitter connects, or the key is in escrow, each such task leaves `held` by the
  rule of T1. `release` also ends the hold.
* A refused command gets `err{bad_state}` and changes nothing.
* A task of a halted run that reaches `held`, `waiting` or `ready` by T7, T8, T9 or T11 takes T10 with reason
  `halt` when the halt mode is `now`; with mode `drain` it stays and T2 and T4 do not fire for it.
* T5 to T9 act only on a row of the current link of the worker (file 05). A frame of a closed link is discarded.

## 8. Outcome table

The outcome and the reason of a result select the class. The class selects the transition for an open row that
is `offered` or `running`.

| Outcome | Reason or code | Class | Transition |
| --- | --- | --- | --- |
| `exited` | code in `ok_codes` | success | T6 |
| `exited` | code in `no_retry_codes` | failure, no retry | T7 to `failed` |
| `exited` | other code | failure | T7 |
| `exited` | reason `output_failed` or `ckpt_failed` (file 15), any code | failure | T7 |
| `checkpointed` | any code | checkpoint, spends nothing | T9 |
| `signaled` | any, also a limit kill of the keeper (`mem_exceeded`, `cpu_exceeded`, `disk_full`, file 12) | failure | T7 |
| `timeout` | none | failure | T7 |
| `spawn_failed` | `bad_argv`, `isolation_refused`, `policy`, `input` | failure, no retry | T7 to `failed` |
| `spawn_failed` | `shape` (the worker lacks the shape, file 05) | not started | T9 |
| `spawn_failed` | `other` | failure | T7 |
| `killed` | `self_fence`, `orphan_cleanup` | loss, spends `max_lost` | T8 |
| `killed` | `drain`, `lifetime` | loss, spends nothing | T8 |
| `cancelled` | none | loss | T8 |
| `not_started` | none | not started | T9 for an `offered` row; T8 for a `running` row |

A `checkpointed` result ends the row, sends the task to `ready` with no delay, and spends neither `retries` nor
`max_lost`. Its attempt counts toward the attempt cap. The next attempt restores the checkpoint (file 15).

A kill that podswarm does for its own reasons is never a failure of the task. After the polite signal of the
fence the attempt ends as `killed`, reason `self_fence`, whatever its exit status (file 05). The authority sends
`cancel` only for a `stopping` row, so `cancelled` for an `offered` or `running` row shows that the two sides
disagree; it is a loss, which keeps I1. A `not_started` for a row that a heartbeat showed running is a loss for
the same reason.

For a `stopping` row the authority already decided the end:
* A success: T6 when the task is not terminal. When the task is terminal, the result is recorded with
  `accepted = 0`, and `late_ok` is set.
* Any other result: the row ends with the reported `end_kind`. A terminal task stays as it is. A non-terminal task
  (the wall deadline) takes T9 for a `not_started` result of a row never shown running, else T8 with reason
  `wall_deadline`.

## 9. Known dead, stopping and the wall deadline

A row is **known dead** when one of these holds:
1. Its worker sends a result for it.
2. A heartbeat of its worker on the current link lacks it, and its `offer_no` is at most the `seen` of that
   heartbeat, or the offer went out on an earlier link of the worker (file 05). A row that the authority
   rebuilt from the store at its start counts as offered on an earlier link.
3. Its attempt deadline passes: `last_rx + silence_s + kill_grace_s + grace_eff` (file 05). The reaper reads
   `last_rx` of the worker again before it ends the row.

Nothing else makes a row known dead: not a closed connection, not a revoke, not the wall deadline, not a cancel.
The fence (I5) makes rule 3 safe: the worker kills the attempt before the authority passes the deadline.

When the authority wants an open row to end (T6 for another attempt, T10, the wall deadline), the row becomes
`stopping`. While the worker has a link, the authority sends `cancel{kill}`. A `stopping` row ends when it is known
dead. A heartbeat that still lists a `stopping` row gets `cancel{kill}` again. A worker that does not end a
`stopping` row within `kill_grace_s + 2 * hb_s` of the first `cancel` is disconnected and marked `suspect`; its
row then ends by rule 2 on its next link or by rule 3.

The **attempt wall deadline** bounds an attempt on a worker that sends heartbeats and never ends it:
* A `running` row: `timeout_s + kill_grace_s + grace_eff` after the first heartbeat that showed it running, when
  the shape sets `timeout_s`; else `max_attempt_s` after that heartbeat.
* An `offered` row: `max_attempt_s` after the offer, or after the start of the authority for a rebuilt row.
* `max_attempt_s`: authority setting, default 604,800 s, range 3,600 to 31,536,000.
* The tasks of a service job have no wall deadline (file 24).
At the wall deadline the row becomes `stopping` and the authority records `wall_deadline` against the worker.
The task keeps its state until the row is known dead, then takes T8 (or T9, section 8).

## 10. The late-result rule

The authority accepts one success per task: the first success, from any attempt the sending worker held, while
the task is not terminal (T6). A terminal state is final.

The sending worker **held** attempt `(task_id, a)` when all of these hold:
1. The authority has a row for `(task_id, a)` in memory or in the store, in its current generation.
2. The offer of that row went to the sending worker (`wid`), and the result arrives on the current link of
   that worker.
3. The row did not end on a report of that worker: no stored result, no `not_started`, no absence in its
   holding. A row that ended by its attempt deadline or that is `stopping` qualifies.

What a result does:

| Case | Verdict | Effect |
| --- | --- | --- |
| Success, held, task not terminal | `accepted` | T6 |
| Another result for the open row, task not terminal | `recorded` | T7, T8 or T9 by section 8 |
| Non-success, held, row already ended (by its attempt deadline) | `recorded` | Stored with `accepted = 0`. No state or budget change. |
| Any result, held, task terminal | `recorded` | Stored with `accepted = 0`. A success sets `late_ok`. |
| A copy of a result already stored for that attempt | the verdict of the first copy | Nothing. |
| Any other result | `dropped` | Nothing. An audit row, at most one per worker and minute, with a count. |

`podswarm show` prints `late_ok` with the attempt number. A `retry` of a task with `late_ok` needs `--force` (file 18).
The cost of a late success is already paid, so the rule keeps finished work. When the task is terminal, the late
success stays a record: a halt, an exit code or a group gate never moves back.

## 11. `at_most_once`

`at_most_once` trades completion for safety: podswarm never starts a task twice by its own act.
* `retries` is 0 (section 3.1). A failure ends the task `failed`.
* An authority with a store syncs every commit that touches an `at_most_once` task, as at `strict` (file 11). The
  lease commit of T4 comes before the offer frame (I6). A restarted authority therefore knows every offer.
* The worker writes and syncs a spawn record before it starts the attempt (file 12). The worker key and the
  journal live in one state directory (file 12).
* T9 differs by delivery. For `at_least_once`, T9 trusts the holding of the worker: a worker host that loses its
  journal can make a started attempt look absent, and the task runs again with no budget spent (the attempt cap
  bounds it). For `at_most_once`, the spawn record makes absence exact: a holding that lacks the row, or a
  `not_started` result, means the attempt never started. A worker that restarts with a spawn record and no
  result reports the attempt as `killed`, reason `orphan_cleanup`, so the task goes to `lost`.
* Every end of a started attempt that is not a worker result is T8 to `lost`, also `drain` and `lifetime`.
* A new generation (file 11) moves each non-terminal `at_most_once` task to `lost` with reason `generation`.
* `--resume` (file 18) runs a `lost` task again only with `--retry-lost`.
* A queued `at_most_once` task needs a worker whose containment rung (file 12) is not `session` and that is not
  `suspect`. What a task can do to a worker that shares its uid is in file 16.
* Only a person moves a `lost` task on, with `retry`. The CLI prints the risk (file 18).

## 12. Invariants

The state machine keeps these for every order of events, crashes and link cuts. File 23 checks each in the
simulation and in the fault tests.

* **I1 no lost task.** Each non-terminal task is `held`, `waiting` or `ready`, or has an open row with an
  attempt deadline in the reaper. After the last start of the authority, a dead worker moves each of its tasks
  on within `silence_s + kill_grace_s + grace_eff` of its last frame.
* **I2 one accepted result.** A task has at most one result with `accepted = 1`, and it is a success. The store
  refuses a second accept (file 11).
* **I3 rising numbers.** `attempt_no` rises per task. `task_id`, `run_id` and `job_id` are never reused.
* **I4 one open row.** A task has at most one row that is `offered`, `running` or `stopping`.
* **I5 worker self-fence.** No attempt runs past `t_ok + silence_s + kill_grace_s` on the fence clock. The worker
  and its spawner enforce it (files 05, 12).
* **I6 durable before acknowledged.** `submitted` and `ack` wait for their commit. Commands do not wait, except
  an offer that holds an `at_most_once` task. Frames to one session leave in the order of their transitions
  (file 05).
* **I7 budgets only rise.** `failures` and `losses` never fall, except by T11.

I5 bounds an overlap; it does not remove it. Two copies of an `at_least_once` task can overlap for at most the
margin that file 05 derives.

## 13. State by event

Cells: a transition; `stop` (the row becomes `stopping` and gets `cancel`); `cancel` (send `cancel{kill}`
again, no state change); `row` (the row ends, the task state stays); `rec` (record with `accepted = 0`, no
change); `late` (as `rec`, and set `late_ok`); `drop` (verdict `dropped`); `refuse` (`err{bad_state}`);
`live` (`err{attempt_live}`); `no-op`; `n/a` (the pair cannot exist). A `waiting`, `ready` or `held` task, and a
`failed` or `lost` task, never has an open row.

| Event | held | waiting | ready | leased | running | succeeded | failed | cancelled | lost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| submit, `(run, key)` exists | no-op | no-op | no-op | no-op | no-op | no-op | no-op | no-op | no-op |
| timer passes or group gate opens | no-op | T2 | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| `hold` command | no-op | T3 | T3 | refuse | refuse | refuse | refuse | refuse | refuse |
| `release` command | T3 | refuse | refuse | refuse | refuse | refuse | refuse | refuse | refuse |
| offer by the scheduler | n/a | n/a | T4 | n/a | n/a | n/a | n/a | n/a | n/a |
| hb lists the open row as `r` | n/a | n/a | n/a | T5, or `cancel` if `stopping` | no-op, or `cancel` if `stopping` | `cancel` | n/a | `cancel` | n/a |
| hb lists the open row as `q` or `d` | n/a | n/a | n/a | no-op, or `cancel` if `stopping` | no-op, or `cancel` if `stopping` | `cancel` | n/a | `cancel` | n/a |
| hb lacks the open row, offer seen | n/a | n/a | n/a | T9 | T8 | `row` | n/a | `row` | n/a |
| hb lacks the open row, offer not seen | n/a | n/a | n/a | no-op | n/a | no-op | n/a | no-op | n/a |
| hb lists an attempt that is not an open row of this worker | `cancel` | `cancel` | `cancel` | `cancel` | `cancel` | `cancel` | `cancel` | `cancel` | `cancel` |
| success, open row | n/a | n/a | n/a | T6 | T6 | `late` | n/a | `late` | n/a |
| success, ended row, held | T6 | T6 | T6 | T6 | T6 | `rec` | `late` | `late` | `late` |
| failure, open row not `stopping` | n/a | n/a | n/a | T7 | T7 | n/a | n/a | n/a | n/a |
| `killed` or `cancelled`, open row not `stopping` | n/a | n/a | n/a | T8 | T8 | n/a | n/a | n/a | n/a |
| `not_started` or reason `shape`, open row not `stopping` | n/a | n/a | n/a | T9 | T8 | n/a | n/a | n/a | n/a |
| `checkpointed`, open row not `stopping` | n/a | n/a | n/a | T9 | T9 | n/a | n/a | n/a | n/a |
| non-success, `stopping` row | n/a | n/a | n/a | T9 or T8 | T8 | `row` | n/a | `row` | n/a |
| non-success, ended row, held | `rec` | `rec` | `rec` | `rec` | `rec` | `rec` | `rec` | `rec` | `rec` |
| result, not held | `drop` | `drop` | `drop` | `drop` | `drop` | `drop` | `drop` | `drop` | `drop` |
| attempt deadline of the open row | n/a | n/a | n/a | T8 | T8 | `row` | n/a | `row` | n/a |
| wall deadline of the open row | n/a | n/a | n/a | `stop` | `stop` | n/a | n/a | n/a | n/a |
| `cancel` command | T10 | T10 | T10 | T10 | T10 | refuse | refuse | no-op | refuse |
| run cancel, halt with mode `now` | T10 | T10 | T10 | T10 | T10 | no-op | no-op | no-op | no-op |
| `deadline_unix` passes | T10 | T10 | T10 | T10 | no-op | n/a | n/a | n/a | n/a |
| `retry` command | refuse | refuse | refuse | refuse | refuse | refuse | T11 | T11, or `live` with a `stopping` row | T11 |
| link closes, worker revoked | no-op | no-op | no-op | no-op | no-op | no-op | no-op | no-op | no-op |
| new generation, `at_most_once` | T8 | T8 | T8 | T8 | T8 | no-op | no-op | no-op | no-op |

Notes:
* "Offer seen" is the condition of rule 2 of section 9. An offer not seen is in flight, and the row stays.
* In `leased` a non-success for a `stopping` row is T9 when it is `not_started`, else T8.
* A closed link and a revoke end no row by themselves. The rows reach their attempt deadline (section 9).
* In `held`, `waiting` and `ready` the new generation applies T8 with no row: the task goes to `lost`.

## 14. The delivery contract

podswarm gives at-least-once execution and at-most-once recording. It does not give exactly-once execution: no
protocol on a lossy link gives both ends certainty. As a user reads it:
1. A task can run more than once: a link cut after the exit and before the `ack`, a worker taken as dead that
   still runs inside the fence margin, a host that loses the journal of the worker.
2. The result of a task is recorded once. The first success that section 10 accepts wins.
3. Each attempt gets `TASK_ID`, `TASK_RUN`, `TASK_ATTEMPT`, `TASK_PREVIOUS_ATTEMPT` and `TASK_KEY` (file 12).
   A program uses them to make its effects idempotent: name an external write by `TASK_ID`, write to a
   temporary name and rename it, check `TASK_PREVIOUS_ATTEMPT` before a step that must not repeat. The staging
   of declared `outputs` does this for files (file 15).
4. podswarm cannot make the external effects of a command idempotent, and it does not claim to.
5. `delivery = at_most_once` never starts a task twice by podswarm's own act. After a loss the task is `lost`
   and waits for a person. A job of the jobs extension that restarts makes a new task, which can repeat the
   effect of the old one (file 24).
6. `submit` is idempotent by `(run, key)`: a task whose `(run, key)` exists is not made again, and the reply
   gives the existing `task_id`, whatever the rest of the task holds. A submitter can repeat a submit after a
   timeout.

## 15. Retry and backoff

* Delay after the n-th failure: `min(cap, retry_delay_s * 2^(n-1))`, times a random factor in `[0.8, 1.2]`.
  `cap` is 300 s, or `retry_delay_s` when that is larger. `retry_delay_s = 0` retries at once with no factor.
* A loss (T8) uses delay 0. The worker is the suspect, not the task. The scheduler avoids that worker for the
  next attempt when another worker fits (file 10).
* T9 uses no delay and spends nothing.
* One task keeps all its attempts. The `task_id` and `idx` stay. A retry goes back to its place in the order of
  its run. `--retry-first` (file 10) puts retries first.
* Failures that never retry, whatever `retries` says: an `exited` code in `no_retry_codes`, and `spawn_failed`
  with reason `bad_argv`, `isolation_refused`, `policy` or `input`. They end `failed` with reason `no_retry`.
* `retries` counts failures; `max_lost` counts losses. The causes differ: a failure is the fault of the task, a
  loss is the fault of a worker or a link.

## 16. Cancellation

* `psw cancel` (task, selector or run) applies T10. The task is `cancelled` when the command is applied in memory;
  the commit follows (I6).
* An open row becomes `stopping`. While the worker has a link, the authority sends `cancel{items, mode: kill}`
  (file 05). With no link the next heartbeat of the worker gets the `cancel`, or the attempt deadline ends the row.
* The worker ends the attempt with the kill ladder (file 12) and sends a result, normally `cancelled`. An
  attempt that never started gives `not_started`. The row ends; the task stays `cancelled`.
* A run cancel cancels each non-terminal task of the run. `succeeded`, `failed` and `lost` tasks stay.
* `cancel{mode: unstarted}` is tail reclaim (file 10). It is not a cancel of the task: the worker answers
  `not_started`, and the task takes T9.
* While a `stopping` row is open, `retry` gets `err{attempt_live}` (T11).

## 17. Priorities and fairness

`priority` orders classes: a ready task of a higher priority is offered before a ready task of a lower priority
that fits the same worker. Between runs of one priority the scheduler shares by `weight`. Inside a run the order
is `(group, idx)`. File 10 owns the policy: strict priority, deficit round robin, `max_running`, reservation and
tail reclaim. Aging is off: a steady stream of high priority tasks can starve lower ones.

## 18. Groups and arrays

* The **active group** of a run is the lowest group that holds a task that is not `succeeded`. With
  `--continue-groups` it is the lowest group that holds a non-terminal task. A task can be `ready` only when its
  group is at or below the active group (T1, T2).
* Group n+1 therefore opens when every task of group n succeeded, or, with `--continue-groups`, when every task
  of group n is terminal.
* When every task of the active group is terminal and one is not `succeeded`, and the run has no
  `--continue-groups`, the run is halted with reason `group`. A `retry` of the failed task clears the halt (T11).
* `--array A:B[:S]` makes one task per index from A to B with step S (default 1, at least 1). The `input` of each
  task is its index in decimal, and `TASK_INDEX` is the index (file 12).
* There is no task graph. The shape field `after` is reserved and gets `unsupported`. Groups cover the
  build, process and gather stages.

## 19. Runs

| Field | Rule |
| --- | --- |
| `run_id`, `name` | Name: 1 to 64 characters of `[A-Za-z0-9._-]`, unique per owner among open runs. |
| `owner` | The submitter key (file 16), or the user of a session. |
| `weight` | 1 to 100, default 1 (section 17). |
| `priority` | -100 to 100, default 0. The default priority of the shapes of the run. |
| `max_running` | Maximum open rows of the run at one time. Default: no limit. T4 checks it. |
| halt policy | `--halt-on-fail N` or `--halt-on-fail P%`, mode `drain` (default) or `now`. Default: no halt. |
| `active_grp` | Section 18. Derived, kept in memory. |
| `paused` | While set, T4 offers no task of the run. Set and cleared by `update` (file 18). |
| `halted` | Set with a reason (`fail`, `group`). Cleared by T11 of a task of the run. |
| `closed` | Set by `run_close`. A closed run accepts no submit. |
| counters | Tasks per state. Derived and rebuilt from the tasks at start. |

Halt policy: the run halts when its tasks in `failed` or `lost` reach N, or reach P percent of its submitted tasks
(rounded up). Mode `drain`: no new offer for the run; open attempts run to their end; each task that is `held`,
`waiting` or `ready` takes T10 with reason `halt` when no open row of the run is left. Mode `now`: each
non-terminal task of the run takes T10 with reason `halt` at once.

## 20. Workers

The authority stores a worker record: `wid`, `key`, `name` (1 to 64 characters), `tags`, `caps` (file 08),
`speed_w`, `invite_id`, `enrolled_at`, `last_seen`, `lifetime_s`, `state` and the flag `suspect`. `last_rx` lives in
memory only.

| # | From to | Trigger |
| --- | --- | --- |
| W1 | none to `pending` | enrol with an invite that has `approve` (file 16) |
| W2 | none or `retired` to `active` | enrol with another invite, or a new link of a `retired` worker |
| W3 | `pending` to `active` | `psw workers approve` |
| W4 | `active` to `draining` | `psw workers drain`, or the worker starts its lifetime drain (file 08) |
| W5 | `draining` to `retired` | the worker ends its drain with no open row and closes its link |
| W6 | any to `revoked` | `psw workers revoke`, `invite revoke --cascade`, the end of the run that started the worker, `worker_ttl`, or the end of an `ephemeral` worker (file 16) |
| W7 | `draining` to `active` | `psw workers undrain` |

* `pending` and `draining` workers get no offer. A `draining` worker finishes or returns its attempts.
* `revoked` is final. The authority refuses each link of a revoked key and closes its open link. The open
  rows of that worker end at their attempt deadline (section 9).
* `suspect` changes no state. It is set by a duplicate identity (file 04) and by a `stopping` row that the worker
  does not end in time (section 9). A `suspect` worker gets no `at_most_once` task. `psw workers approve` clears
  the flag.
* `speed_w` is the speed estimate of file 10, per mille (1,000 is the median), not the `caps` score `speed`.

## 21. What is stored and what is not

Stored, at these points: T1 writes the tasks (before `submitted`); T4 writes the lease record (before the offer
for `at_most_once`); T6 to T9 write one attempt record and one task update; T2, T3, T10 and T11 write one task
update. A lease record goes when each of its attempts has an attempt record. T5 writes nothing.

Not stored:
* Heartbeats, the row states `offered`, `running` and `stopping`, `last_rx`, `offer_no`, `seen`, and the time a
  heartbeat first showed a row running. At start the authority rebuilds each open row from the lease records as
  `offered`, sets `last_rx` of each worker to the start time, and lets the first heartbeat of each worker
  reconcile the rows (file 05).
* The ready queues, the timers and the deadline heaps. A start rebuilds them from the tasks of open runs.
* Output beyond the inline capture. It lives in blobs (file 15).
