# 24. Later features

This file defines the features that are designed and are not in the core. Each has a wire feature name, rules, a hook in the core files, limits, and the condition that moves it into a milestone (file 22 holds the milestones). A feature is on when both sides list its name in `features` of `hello` and `ready` (file 04). A reserved field of a feature is refused with `unsupported` until then (files 05 and 09). Checkpoints, cells, the agent face and plugins are core (files 15, 08, 17). Process migration and pooled memory are in file 07.

| Section | Feature | Wire name | Core hook |
| --- | --- | --- | --- |
| 1 | Jobs: service and periodic | `jobs.1` | files 09, 11 |
| 2 | Speculation | `speculate.1` | files 09, 10 |
| 3 | Estimate-based backfill | none | file 10 |
| 4 | Hub | `hub.1` | files 04, 16 |
| 5 | Sub-coordinator | `upstream.1` | files 05, 10 |
| 6 | Signed shapes | `sig.1` | files 05, 16 |
| 7 | Secrets | `secrets.1` | files 05, 11, 12 |
| 8 | Replication and sampling of results | `verify.1` | files 09, 10 |
| 9 | Boundaries `sandbox` and `vm`, image view | `podvm.1`, `incus.1` | files 12, 13 |
| 10 | Audit hash chain | `audit-chain.1` | file 11 |
| 11 | Worker key rotation | field of `hello` | file 04 |
| 12 | Second transport, packed results | none | files 04, 15 |
| 13 | Coordinator listener with a certificate of a public CA | none | file 16 |

## 1. Jobs (`jobs.1`)

**For.** Work that has no end (a `service`: keep N tasks alive) and work that repeats on a clock (a `periodic` job: cron). A job needs a coordinator. A session keeps nothing between commands, so it has no jobs.

**Record.** The store table `jobs` (file 11, by migration) holds one row for each job. The controller is a loop inside the coordinator. It runs once each second and at each task end. It makes tasks from the job's shape. The tasks belong to one open run named `job/NAME`, and each carries `job_id`.

| Field | Meaning and default |
| --- | --- |
| `name` | 1 to 64 characters of `[a-z0-9._-]`, unique |
| `kind` | `service` or `periodic` |
| `spec` | the shape that each task uses (file 05). A signed job holds an envelope (section 6) |
| `replicas` | `service`: tasks that must be alive. Default 1 |
| `restart` | `service`: `never`, `on_failure` or `always`. Default `on_failure`. `periodic` accepts `never` only |
| `backoff` | `{base_s 2, cap_s 300, reset_after_s 600}` |
| `crashloop` | `{n 5, window_s 60}` |
| `schedule`, `tz` | `periodic`: five cron fields; an IANA zone name, default UTC |
| `overlap` | `periodic`: `skip` (default) or `allow` |
| `catch_up` | `periodic`: default `false` |
| `state` | `active`, `paused`, `stopped` |

**Service rules.**
* While `state = active` and the job has fewer than `replicas` non-terminal tasks, the controller makes a task. The task has `retries = 0` and `max_lost = 0`: the controller owns the restart, and the retry of file 09 does not.
* A task of a service has `silence_s` 300 and no attempt wall deadline (files 05 and 09). The flag `--silence` of `job add` has the same default.
* After a task ends, the controller makes a replacement after a delay. `always` replaces any end. `on_failure` replaces `failed` and `lost`, not `succeeded` or `cancelled`. `never` replaces none.
* Delay: `min(cap_s, base_s * 2^(k-1))` times a factor in [0.8, 1.2], with `k` the count of ends in a row that came sooner than `reset_after_s` after the start. A task that lives `reset_after_s` resets `k`.
* Crash loop guard: when `n` tasks end within `window_s`, the job goes `paused` with reason `crashloop` and an event `job.pause`. A person runs `job resume`.
* A job whose shape has `delivery = at_most_once` and `restart = always` makes a new task after a `lost` task. The new task can repeat the effect of the lost one (file 09, section 14). With `on_failure` a `lost` task of such a job waits for a person. `exclusive_placement` does not exist: each reason for `lost` already shows that the old copy is dead.

**Periodic rules.**
* When the cron expression fires, the controller applies `overlap`. `skip` makes no task while a task of the job is not terminal. `allow` makes the task. `queue` does not exist: it holds a backlog that nobody asked for.
* The task gets `key = f<fire time in unix seconds>`. A repeat of a fire after a controller restart makes no second task (`(run, key)` is unique, file 09).
* The fire time uses the wall clock of the coordinator. It is the only decision of the coordinator that does. A local time that does not exist (a clock moves forward) fires at the next valid minute. A local time that happens twice fires once, at the first. The binary embeds the IANA zone data.
* `catch_up = true`: at coordinator start, one missed fire runs, however many passed. `false`: missed fires are skipped.

**Surface.** `podswarm job add|ls|show|pause|resume|stop|rm|logs`; file 18 gains it with this item. `add` takes the shape options of `submit` (file 18) and the flags `--kind service|periodic`, `--replicas N`, `--restart`, `--schedule CRON`, `--tz ZONE`, `--overlap`, `--catch-up` and `--silence`, one for each field of the record; file 18 gains them with this item. A queue option that has no meaning for a job is refused with exit 64. `pause` stops new tasks and lets live tasks run. `stop` also cancels them (T10). `logs` merges the lines of all tasks in arrival order; `--prefix` adds `[task ID worker NAME]`. The submitter ops are `job_add`, `job_ls`, `job_pause`, `job_resume`, `job_stop`, `job_rm`.

**Hook.** File 09 reserves `job_id` and the note about service tasks. File 11 adds the table `jobs` and `next_job_id` in `meta`. `pod-supervise` is not needed: a service task is an ordinary attempt under the keeper (file 12).

**Limits.** A task of a service survives a coordinator restart only while its fence holds (`silence_s` 300). A longer outage kills it by the fence; the controller then replaces it. No dependency between jobs. A job does not move a running task.

**Moves into a milestone** when a user runs a service or a nightly job without an external scheduler, and the test of a 1,000-replica job with a crashing shape shows the guard pauses it within `window_s`.

## 2. Speculation (`speculate.1`)

**For.** One slow task at the end of a run delays the whole run. A second attempt of that task on an idle worker cuts the tail. The first valid result wins.

**Shape field.** `speculate` (bool, default false). `--speculate` on `x` and `submit`. A task with `delivery = at_most_once`, a task of a job of kind `service`, and an attached command never speculate: a second copy repeats side effects.

**A second row starts (T4s) only when all of these hold.**
1. No ready task of any class fits an idle worker. Speculation never competes with real work.
2. A worker with a parked `pull` fits the class of the task, is not the worker of the live row, and has `speed_w` (file 10) of at least `speculate_min_speed`.
3. The task is `running`, has `speculate`, has `delivery = at_least_once` and has exactly one open row.
4. The class has at least `speculate_min_done` finished tasks.
5. The task ran longer than `theta = max(speculate_theta * p95_class, speculate_min_s)`. `p95_class` comes from the log histogram of the class (file 10).
6. The open speculative rows are fewer than `max(1, speculate_share_pct percent of active workers)`.
7. The run is under `max_running` (the guard of T4).

A task has at most `spec_max` speculative rows (default 1). T4s uses the fit, the `shield` and the residency rule of T4 (files 08, 10, 13).

**How it relaxes I4.** I4 says a task has at most one open row (file 09). With the feature, a task with `speculate` has at most `1 + spec_max` open rows, and every extra row has `spec = 1`. No other invariant changes: I1 holds because each open row has its own deadline, I2 holds because T6 accepts one success, I5 acts on each row.

**Transitions that change** (file 09, section 7). The state of the task is `running` while an open row runs, and `leased` when no open row runs but one is offered. A task never stays `running` with no copy anywhere.
* T4s: `running` to `running`. Makes row `offered`, `spec = 1`, for another worker. It is the only way to a second open row. It counts for `attempts`.
* T5: as in file 09, row by row.
* T6: as in file 09. A success of any open row of the task that its worker held is accepted. Each other open row becomes `stopping` and gets `cancel{kill}`; it ends `superseded`. Its outputs are dropped.
* T7: the row ends and `failures` rises by one for the set. With another open row, the task keeps its state and waits. When the last open row ends with no success, the task takes T7 if any row of the set failed (the stored failing result is the result of the task), else T8. A task that fails every time with `speculate` does not run extra times.
* T8: a row that is lost while another is open ends with no use of the loss budget. The budget acts when the last open row ends, as above.
* T9: a speculative row that ends `not_started` (a drain, a cancel of unstarted) ends with no change. The task takes T9 only when it has no other open row.
* T10: each open row becomes `stopping`.
* Late result: a result of a `superseded` row is recorded with `accepted = 0` (file 09, section 8).

**Settings** (authority): `spec_max` 1 (0 to 3), `speculate_theta` 2 (1.5 to 10), `speculate_min_s` 30, `speculate_min_done` 20, `speculate_min_speed` 500 (per mille, 100 to 10,000), `speculate_share_pct` 5 (1 to 50).

**Hook.** File 09 names the reserved field `speculate` and the single open row of the core. File 10 adds T4s to the idle-worker path, after tail reclaim. File 11 adds the column `spec` to `attempts` by migration.

**Limits.** The tail gets shorter by a second copy, and the cost is the compute of that copy. The estimate needs 20 finished tasks, so a run with fewer never speculates.

**Moves into a milestone** when a run of 1,000 or more tasks shows a last 5 percent of tasks that take over 20 percent of the wall time, and users ask for the option.

## 3. Estimate-based backfill

**For.** The reservation of file 10 holds a worker for a big task and uses no duration estimate, so the worker idles until the big task fits. The estimate lets small tasks use the wait.

**Rules.**
* The reserved worker `W` keeps the reservation of file 10. The engine may offer `W` a task `t` of another class when `now + est(t) + backfill_margin <= free_at(W)`.
* `free_at(W)` is the earliest time at which the free capacity of `W` plus the capacity of its open rows that end by then covers `needs` of the head task. A row ends at `start + d_c` (the median of its class on this worker, file 10). A row already past `d_c` ends at never for this sum.
* `est(t)` is `needs.time_s` when the shape sets it, else `d` of the class on `W`. A task with neither is not used for backfill. `backfill_margin` is 20 percent of `est(t)`.
* The engine never kills a backfilled task for the head task. An overrun delays the head task, and the counter `backfill_overrun` in `status` shows it.
* An `exclusive` task uses the rule with "the worker holds no row" as the fit.

**Hook.** File 10, sections 11 and 12: the engine computes `free_at` from the `d` table and the time checks of section 12. No wire change, so no feature name.

**Limits.** Estimates come from classes with a known `d`; a cold class does not backfill. The median can be wrong for a bimodal class.

**Moves into a milestone** when a test of mixed big and small tasks shows more than 10 percent idle slot time under the plain reservation.

## 4. Hub (`hub.1`)

**For.** A coordinator that cannot listen: behind NAT, behind a firewall, or on a host that denies `listen`. The hub is a relay that both sides dial. It does not read the traffic.

**Rules.**
* The coordinator dials `wss://HUB/v1/h` and holds one WebSocket. It authenticates with an Ed25519 key that is in the allowlist of the hub (`pod-identity` allowlist). Each key line binds one hub name (`name=`). Two coordinators cannot claim one name.
* A worker dials `wss://HUB/v1/w/NAME`. Inside that WebSocket the worker runs TLS with the coordinator as the peer (file 04, identity in the handshake). The worker pins the coordinator key, not the key of the hub. The hub sees ciphertext only.
* The hub multiplexes the worker connections on the coordinator WebSocket with `pod-link`: one stream for each worker connection, a credit window per stream and per link. The opening line of a stream is one JSON object: the hub name and `peer`, the address that the hub saw. The worker side has no `pod-link`: the hub copies the bytes of the worker WebSocket to its stream and back. [EV-002]
* The coordinator applies the pre-auth limits of file 16 for each `peer`. A `peer` is an advisory field. A ban by `peer` is a rate limit and never an audit row against that address. The address of the hub itself is never banned.
* Hub settings (all finite): sessions per name 4,096; sessions in the hub 16,384; bytes per session 64 GiB per day; new sessions per peer address per minute 600; WebSocket handshake 5 s; an idle session before its first payload byte 15 s; an idle session 10 minutes.
* What the hub learns: worker addresses, connection times, byte counts, the coordinator name. A hostile hub can only refuse service.
* The hub is the role `podswarm hub` of the one binary. It forwards bytes and schedules nothing.

**The reverse roads of `pod-relay`.** They are the other way to reach a machine that can only dial out, and they serve a session. The road `relay://NAME` reaches a long-lived `podswarm worker --node NAME --pair FILE` that embeds `pod_relay::reverse::run`; the pair gives Noise end to end (file 04). A public relay caps a hop at 64 MiB and a pair lives 72 hours, so bulk data uses a self-hosted relay. The hub serves a swarm: a coordinator that cannot listen. The two do not share a wire. The hub does not speak the relay contract because podcrates v0.34.0 has no relay server and `pod-link` already gives the multiplexer and the flow control. [EV-122]

**Hook.** File 04 lists the road kind `wss` and the path `/v1/h`. File 16 holds the pre-auth limits per `peer` and the allowlist form. The invite token (file 16) lists the hub address as the coordinator address. The server loop comes from the `serve` module that file 21 asks of `pod-ws` (P-2).

**Limits.** One hub is one point of failure for the workers that use it; they reconnect with jitter. The path has two hops. A coordinator that accepts connections needs no hub.

**Moves into a milestone** when a user runs a swarm whose coordinator has no reachable address and the `pod-ws` `serve` module exists (the fallback is `podswarm-net/accept.rs`).

## 5. Sub-coordinator (`upstream.1`)

**For.** A site with its own workers, a slow link to the main coordinator and often its own launcher (a batch system). A coordinator that is a worker upstream and a coordinator at the site. This is the match for the HyperShell `relay`: upstream it is an ordinary client; at the site it runs its own server, schedules the tasks that it receives to workers that it launches, and returns the results upstream. [EV-123]

**Rules.**
* `podswarm coord --upstream URL --invite TOKEN` makes the coordinator also a worker of the upstream coordinator. It enrols with an invite and has a worker row upstream. Its invite rules (cores, slots, boundary) bound the whole site.
* Capacity upstream: `slots`, `cores_m` and `res` are the sums over the active site workers. `mem_mib` and `disk_mib` are the largest value of one worker, because a task runs on one worker. `os`, `arch` and `tags` are the unions. `caps.site = true`. The depth rule of file 10 then fills a deep local queue over the slow link.
* An attempt that arrives becomes a local task in a local run with the owner `upstream` and the fields `up_task`, `up_attempt`. The local store is the store of the site (file 11), so the attempt survives an outage of the upstream link.
* The site coordinator schedules the local task to its workers with the engine of file 10 and the retry rules of the shape. It sends the `result` upstream when the local task is terminal. After a reconnect the first `hb` carries the whole holding (file 05), so no result is lost.
* A task with `delivery = at_most_once` goes to a site only when its store is `strict`.
* Fence: the site coordinator obeys I5 for the upstream fence. At `t_ok + silence_s` of the upstream link it sends `cancel{kill}` to the site workers that run upstream attempts. The kill at `t_ok + silence_s + kill_grace_s` ends them as `killed`, reason `self_fence`.
* An upstream `cancel` becomes a local cancel. An upstream `cancel{unstarted}` returns the local tasks that did not start.
* Blobs: the site coordinator fetches each input blob once from upstream and serves its workers from its own content store (file 15).
* Launcher: `--launcher CMD` and `--size N`. When the local queue is deeper than the free slots, the site coordinator runs CMD (an argv, no shell) to start site workers, up to N. CMD finds a site invite in the file named by `PODSWARM_SITE_INVITE_FILE` (mode 0600). A site worker that is idle for `idle_exit_s` leaves (file 10).
* A task that does not fit any site worker ends `not_started` with reason `no_fit` and no budget use.
* One level only. A site worker cannot be a sub-coordinator. (D-102)

**Hook.** File 05: `hello.caps` carries `site`. File 09: a task has an owner (`upstream` for a task from the upstream coordinator). File 10: the bundle cap and the depth rule apply to a site as to a worker.

**Limits.** Output of a task goes upstream only as head and tail unless a person asks for `logs`, which the site relays. The site cannot make a task run longer than the upstream fence allows.

**Moves into a milestone** when a user has a site with a slow link and a launcher, and the content store of file 15 exists.

## 6. Signed shapes (`sig.1`)

**For.** A worker owner (or a hostile coordinator case) wants a worker to run only shapes that a named key signed.

**Envelope.** A signed shape travels as `{"spec": TEXT, "sig": {"key": "SHA256:...", "exp_unix": N, "sig": "BASE64"}}`. `spec` is the exact JSON text of the shape, held as a string. `sig` is never inside `spec`. The signed bytes are `"podswarm-shape-1" 0x00 || aud || 0x00 || decimal(exp_unix) || 0x00 || spec`. `aud` is the swarm id in a swarm and the empty string in a session. A shape signed for one swarm does not verify in another. The signed bytes are the exact text of `spec`; nothing is parsed and encoded again before the check. The worker verifies the bytes it received, then parses the same text with duplicate keys and unknown fields refused. [EV-083]

The authority stores the envelope in `shapes.spec` and `shapes.sig` and sends it once per session, as for any shape (file 05). The worker verifies a shape once per session and keeps the verdict by shape id, so the cost is one Ed25519 verify for many tasks. `exp_unix` is required.

**What a signature covers.** The shape: `argv` or `shell` with its tokens, `env`, `files` and their hashes, `image` digest, `needs` (boundary and shield), `confine`, `limits`, the names in `secrets`, `tmpl`, and the expiry. **Not covered:** the inputs of a task (`input`, `fields`, task tags, `idx`), the run, the values of secrets, and the choice of worker. The worker expands the template (file 18), so a signed shape with a loose token lets a coordinator choose the command. Two rules close that:
* A worker with `require_signed_by` accepts a signed `shell` shape only when every token that takes task data is quoted, with `{q}` or the suffix `|q`. The tokens `{#}`, `{%}`, `{slot}` and `{slot_count}` hold digits only and need no quote.
* It accepts a signed `argv` shape only when no token stands in element 0 (the program), and refuses a token anywhere else that file 18 does not allow.

A shape with `tmpl = 0` has no token and passes. A refusal is `spawn_failed`, reason `policy`, and never retries on that worker.

**Worker policy keys** (the file of file 16; the other keys are core):

| Key | Type, default | Effect |
| --- | --- | --- |
| `require_signed_by` | list of fingerprints, empty | non-empty: the worker runs a shape only if `sig` verifies with a listed key. It also refuses every shape when `sig.1` is absent from `ready.features`, and closes the session |
| `max_spec_age_s` | seconds, 86,400 | refuse when `exp_unix` minus the time now is above this value (a cap on the validity window). The lower bound has a skew allowance of 300 s |
| `unsigned_boundary_min` | boundary name, `none` | when `require_signed_by` is empty, an unsigned shape needs at least this boundary |

**Expiry.** The worker checks `exp_unix` when the offer arrives, on its wall clock, and never during the run. A worker whose clock differs by more than 300 s refuses with `policy`; `doctor` reports the clock. The authority refuses an expired envelope at submit.

**Jobs.** A job template that is signed carries one envelope. The controller makes no task after `exp_unix`: the job goes `paused` with reason `sig_expired`. A submitter replaces the envelope to continue. A worker with `require_signed_by` refuses the tasks of an unsigned job.

**Tags.** Task tags are inputs and are not covered. The tags of the shape are covered and cannot change.

**What it stops:** a hostile coordinator cannot create or change a shape. **What it does not stop:** replay of a signed shape, with any input, on any fitting worker until `exp_unix`; and a change of the value of a secret of the same name (section 7). A worker that wants at-most-once replay protection keeps the hashes of the shapes it ran until `exp_unix`. [T]

**Hook.** File 05 reserves the field `sig` of a shape entry in `submit` and in `offer`. File 16 holds the policy file and the fingerprint form. File 11 adds `shapes.sig` by migration.

**Moves into a milestone** with the first worker owner who asks to limit a worker to the shapes of one key.

## 7. Secrets (`secrets.1`)

**For.** A task needs a credential that the caller does not want in argv, in a shape or in a file of the task directory.

**Store.** The coordinator keeps the values in the table `secrets` (file 11). Each value is sealed at rest with ChaCha20-Poly1305 under a master key, with a random 96-bit nonce and the name as associated data. The master key is a file of mode 0600 outside the state directory (`master.key` in the configuration directory of the `pod_core::files::Places` chain, or `--master-key FILE`). A backup never holds it (file 11). Sealing at rest protects a leaked database or backup. It does not protect against a reader of the master key. A session has no store, so it has no secrets.

**Record.** `{name, owner, allowed[], scope[], version, created_unix}`. The name matches `^[A-Za-z0-9_][A-Za-z0-9._-]{0,63}$`. `owner` is the submitter key that made it. `allowed` is a list of submitter keys, default the owner only. `scope` is a list of worker tags.
* `set` and `delete` of an existing name need the owner or an admin. A change of `scope` or `allowed` writes an audit row. A new `set` makes a new `version`. A running attempt keeps its value.
* A submit that names a secret whose `allowed` lacks the submitter gets `err{unauthorized}` and the audit event `policy_refusal`. The local admin socket may name any secret.
* The CLI takes a value from `--file FILE` or from standard input, never from argv. It never prints one. `--env NAME=@FILE` and `--env NAME=-` for a name of the deny list are refused, with the hint to use `--secret` (file 12).

**Delivery.** A shape lists `secrets: [names]` (at most 16). At offer time the authority checks that the chosen worker has each tag of `scope`; else the task stays `ready`. The value goes in the offer row, in `extra.secrets` (a map of name to base64, at most 64 KiB each), inside the link: the TLS channel of a `wss` road or the authenticated stream of a road such as ssh. There is no per-worker sealing and no `dh` key. A frame with a secret is never logged and never stored. The worker writes each value to a file in a memory-backed directory, `$XDG_RUNTIME_DIR/podswarm/secrets/<task_id>.<attempt_no>/NAME`, directory mode 0700, file mode 0600, and sets `TASK_SECRETS` to the directory. There is no delivery by environment variable. A worker with no memory-backed directory does not advertise `caps.secrets` and gets no task that names a secret. At worker start, before `hello`, the worker removes every leftover directory under `secrets/`. At the end of the attempt it removes the directory. The view never serves it (file 06), and the path rule keeps the name `.secrets` out of task paths (file 16).

A secret value is never in argv, an event, a log line, an error, a URL, an audit row or a backup. The audit event `secret_sent` (name and worker) is aggregated for each run, worker, secret and minute.

**Failure.** A missing master key after a restore makes the task fail with `spawn_failed`, reason `input`.

**Hook.** File 09 reserves the field `secrets`. File 05 adds the submitter ops `secret_set`, `secret_ls`, `secret_rm` and the offer field `extra.secrets`. File 11 adds the table. File 12 owns the memory-backed directory rules.

**The run key.** With `--key-escrow` the submitter stores the data key of an encrypted run in this store, and the coordinator answers the key requests of workers (D-126; files 15, 16).

**Limits.** The owner of the worker can read the value, and so can the task. On `none`, a same-uid task of another run can read the directories of concurrent attempts: use `confined` or a worker tag that only trusted runs have (the Landlock profile of `confined` grants only its own directory). A hostile coordinator can substitute the value of a name. A worker on macOS or Windows has no memory-backed directory in this form. The master key sits in a file; an in-memory agent such as `podkey` could hold it later.

**Moves into a milestone** with the first submitter who shares a swarm with others and needs a credential for a task.

## 8. Replication and sampling of results (`verify.1`)

**For.** A result is as trustworthy as its worker. Replication runs a task on several workers and compares. Sampling re-runs a fraction of the accepted tasks.

**Model.** Each replica is its own task. It names the task it verifies in the task field `verifies`. It has `delivery = at_least_once`, `kind = verify` and the placement field `avoid`: the `wid` values and the `invite_id` values of the earlier replicas. The original task follows T1 to T11 as in file 09. No transition leaves `succeeded`. I4 holds: each task has one open row.

**Modes** (shape field `verify`, default none):
* `{mode: "replicate", n: 2}`: at submit the authority makes `n` minus 1 replica tasks beside the original. All run at once.
* `{mode: "sample", per_mille: 50}`: when the original is accepted, the authority makes one replica task if `BLAKE3(task_id || gen)` read as a number, modulo 1,000, is below `per_mille`.

**Digest.** The worker adds `extra.digest` to the result of a task with `verify`. It is the BLAKE3 of these lines: `exit <code>`, `out b3:<hex>`, `err b3:<hex>`, then `file <path> b3:<hex>` for each output sorted by path bytes, each line ending with a line feed, after the label `podswarm-digest-1` and a zero byte. The worker hashes the whole of each stream while it drains the pipes. A replica reports hashes and uploads no blob.

**Verifier step.** When the original and its replicas are terminal, the authority compares digests. All equal: `verified = yes`. A strict majority: `verified = yes` and the minority workers are blamed. A mismatch with no majority after one more replica on a third worker: `verified = no_quorum`. A replica that cannot find a worker of a different `invite_id` within `replica_wait_s` (600) gives `verified = no_diverse_workers`. The verdict is a field of the original's result row. It is not a task state. `show` prints it, `ls --select verified=no` lists it, and a run with any verdict `no`, `no_quorum` or `no_diverse_workers` exits 1.

**Blame.** Only a strict majority blames, and only the minority. A mismatch counts against a worker only when it happens for tasks of at least 2 runs of at least 2 submitters, so one submitter cannot drain honest workers with a task that is not deterministic. Blame writes the event `verify.blame` and raises a counter of the worker. It does not change the worker state; the operator decides to drain.

**Rules.** Replication works for deterministic tasks only. The submitter declares it. A key may set `verify` only with the scope `verify` (file 16). Replicas count in `max_cores` and `max_queued` of the submitter and are hidden from `ls` and from the exit code of the run, except through the verdict. Cost is `n` times the compute. Replication does not defeat an attacker who holds the majority of the workers of one invite or of several.

**`run --check-on HOST`** (named in file 13; file 18 gains it with this item) is one replica of a deterministic attached command on a second machine, compared by digest. It needs a session with two machines.

**Hook.** File 09: reserved field `verify`, task fields `verifies`, `kind`, `avoid`. File 10: the fit excludes the workers and invites in `avoid`. File 05: `extra.digest`. File 11: `verified` in the result row.

**Moves into a milestone** with the first user who runs on workers that they do not own.

## 9. Boundaries `sandbox` and `vm` and the image view (`podvm.1`, `incus.1`)

**For.** A task from a submitter that the worker owner does not trust, and a task that needs a root file system of an image. podvm gives both on hosts with no root. The order of boundaries is `none < confined < sandbox < vm` (file 13). The image is a separate field: `shape.image = "NAME@sha256:..."`.

**What each gives.**
* `sandbox`: the system calls of the attempt go to a user-space kernel (gVisor `runsc` through podvm). A host path that is not mounted is not reachable. It needs user namespaces on the host. `runsc` refuses `--timeout`, so the kill ladder of file 12 kills it. It runs in the foreground only.
* `vm`: a separate guest kernel. The podvm machine rung runs one QEMU guest for each attempt, with KVM where `/dev/kvm` opens, else TCG. Under TCG the emulator process is the boundary, not the hardware. The incus rung talks to an `incusd` that root prepared once (`pod-incus`).
* Image view: the root file system and `/etc/os-release` of the attempt are those of the image. On the rootless rungs (chroot, userland, interposer) it is a view and no boundary. It does not raise `boundary`.
* The worker reports the rung that podvm really enters (`podvm system info`) and advertises a boundary only for a rung that the probe proved. It never guesses. A worker never runs an attempt on a weaker boundary than asked.
* Boundary `vm` does not give shield `guest`. The machine rung shares host files with the guest. Shield `guest` uses its own guest plan, and the guest runs its own worker (file 13).

**Costs.** [EV-125] The machine rung costs about 0.6 s per attempt under KVM and 2.9 s under TCG, and TCG compute is 3 to 21 times slower by class. The incus rung costs 0.36 to 0.49 s for an instance and 45 ms for each `exec`.

**Warm sandbox for each slot.** A worker keeps one warm sandbox for each slot, keyed by `(image digest, run id)`. It runs `podvm create` once, then `podvm exec` for each attempt. For incus it keeps one instance for each slot and runs `exec` for each attempt. A sandbox is never reused across runs. The tasks of one run share its writable root. The sandbox ends when the last attempt of the run leaves the slot, after `sandbox_idle_s` (60) with no attempt, or at worker exit. The machine rung has no warm form, so each attempt boots a guest. Memory for a slot is `needs.mem_mib` plus 256 MiB for a guest.

**Image delivery.** The image is an OCI layout tar in the content store (file 15). The worker loads it with `podvm load` and runs with `--pull never`. The digest is checked before use.

**What podvm gives now and the asks.** podvm has a CLI and no library. `run --report PATH` and `run --label` exist, and the aarch64 interposer is shipped. [EV-126] cgroup flags are refused by name, so memory and CPU limits stay `polled` (file 12). Asks (file 21): a library call for `run`; the probe cache read in `run`; cgroup limits; a foreground payload that dies with podvm; a read-only root with a tmpfs upper layer so `run` does not copy the image; a warm `exec` into a booted machine guest.

**Hook.** File 05 and 09: `needs.boundary` and `shape.image` (the field `image` is reserved). File 12, section 18.4: the worker drives podvm. File 13: shield levels and the order.

**Limits.** QEMU is outside the static binary promise: it must be on `PATH` of the host. Tiny machines usually lack `/dev/kvm` and memory, so `vm` is a last resort there. incus needs a root setup once. No Windows host.

**Moves into a milestone** with a user who runs untrusted submitters, or with shield `guest` (file 13), which needs the same podvm work.

## 10. Audit hash chain (`audit-chain.1`)

**For.** Evidence that the `events` table (file 11) lost no row and altered none, with a head that leaves the host.

**Rules.**
* Each row of `events` gets `prev` and `hash` by migration. `hash = BLAKE3("podswarm-audit-1" 0x00 || prev || seq || type || time_unix || body)` over the stored bytes. The writer thread computes it after the order of the rows is fixed (file 11).
* `podswarm audit head` prints `seq` and `hash`. `podswarm audit verify` walks the chain and exits 76 when a link breaks. `audit verify --anchor SEQ:HASH` also fails with `cut` when the tail is removed. Without an anchor a cut tail is not detected.
* The event `audit.head` fires every `audit_head_s` (60) with the head. A hook or webhook of file 17 ships it off the host. Without that, the chain detects accidental corruption only.
* A purge by retention (file 11) writes `meta.audit_base = {seq, hash}` of the last purged row. `verify` starts from the base.
* The events of high rate are aggregated for each source and minute before the chain (file 16), so a flood does not fill the chain.

**Hook.** File 11 holds the table and the purge. File 17 holds the hook.

**Limits.** A root user on the coordinator host can rewrite the chain and the anchor. The claim is tamper evidence only for an anchor kept elsewhere.

**Moves into a milestone** when the head can go off the host by a hook, and a user needs audit evidence.

## 11. Worker key rotation

**For.** A worker owner replaces the key of a worker.

**Rules.** Rotation is only for a worker that is `draining` with no open row. The worker sends `hello.rotate = {new_key, sig}`; `sig` is made by the old key over `"podswarm-rotate-1" 0x00 || swarm_id || old fingerprint || new_key` (the 32 bytes of the new Ed25519 key). The authority replaces `workers.key`, writes the audit event `key_rotate`, and with an invite rule `approve` sets the worker to `pending`. A worker that is not draining gets `err{unauthorized}`. There is no `prev_id`. The reason: a thief with the old key cannot drain a worker, so the thief cannot rotate it. The field `rotate` is refused with `unsupported` until the authority accepts it (file 04).

**Moves into a milestone** when revoke and a new invite cost too much for a user who rotates keys on a schedule.

## 12. A second transport and packed results

**A second transport.** The core uses one connection for each worker; `pod-link` gives each bulk transfer its own stream with priority for control frames (file 04). A second connection for blobs, with HTTP `Range` on `GET /v1/blob/<id>`, with `id` a `b3:` content id (file 15) and a token bound to the session, is a candidate if the test of target A-18 shows control latency above 1 s during a bulk transfer. A second connection costs a descriptor, a TLS handshake and a second authentication path. QUIC is not planned: UDP is often blocked on target hosts, QUIC costs more CPU for each byte on boards with no segmentation offload, and the org has no QUIC NAT path. Reopen it if phone workers show reconnect cost or NAT rebinding as the main loss.

**Packed results.** `--results DIR` makes three files for each task (`stdout`, `stderr`, `status.json`), and a run of 1,000,000 tasks makes 3,000,000 inodes. `--results-pack FILE` writes one append-only file of records and an index file `FILE.idx`. A record is `u32 length`, `u32 task index`, `u32 status length`, the status JSON, `u32 stdout length`, the stdout bytes, `u32 stderr length`, the stderr bytes, all big endian. The index maps task index to offset. `podswarm get --pack FILE DIR` writes the `DIR/<index>` layout of file 15. `podswarm get --pack FILE --index N` prints one record. File 18 gains `--results-pack FILE` and both forms of `get --pack` with this item. A pack is complete when the last record is followed by a record with index `0xFFFFFFFF`. It moves into a milestone when a user runs 100,000 tasks or more against a network file system.

## 13. A coordinator listener with a certificate of a public CA (`--webpki`)

**For.** A coordinator at a public name, with a certificate of a public CA. A client then connects with no pin: the chain and the host name are the proof of the coordinator. The same listener can serve the two files of the run identity issuer (file 17).

**Rules.** `podswarm coord --webpki` presents the chain of a public CA and its key, in place of its Ed25519 certificate. A client with `--webpki` and no pin checks the chain against the WebPKI roots and the host name at each connection, and stores no pin. A token or a connect string then has no field `k`. The client still presents its Ed25519 key, and the coordinator checks it by the rules of file 16, section 4.3. The coordinator loads a renewed certificate while it runs. File 18 gains `--webpki` on `coord`, `join`, `invite new` and the commands that take a coordinator address with this item.

**Hook.** File 16, section 4: the pin set, the field `k` and the attack row X-02. The TLS layer needs a verifier pair that `pod-tls` does not have: a server chain checked against the WebPKI roots, together with Ed25519 client keys that the coordinator pins or enrols. `pod_tls::peer` takes Ed25519 keys only on both sides (D-129), so this item makes an ask to `pod-tls` (file 21).

**Limits.** A CA that issues a certificate for the name can act as the coordinator to a client with no pin. A client that holds a pin keeps the pinned check.

**Moves into a milestone** when a user needs clients that hold no pin, for example a public swarm with a published address, and the ask to `pod-tls` is done.
