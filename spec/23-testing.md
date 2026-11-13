# 23. Testing, benchmarks and targets

This file defines the test layers, the deterministic simulation, the guards, the fault tests, the tests of the view, of spreading, of the shield levels and of roads, the benchmarks with their method, and the full table of targets. Each test has an input, an action and an expected observation. File 22 names the tests that close each milestone. File 21 names the traits whose conformance suites are here.

## 1. Rules

* A test uses loopback only. A test that needs a real remote host, a VM or special hardware is a live test: it is `#[ignore]` and runs in the live workflow, never in the gate of a push.
* A test never sets a process variable. Tests share no state. Time comes from a `Clock`. No sleep is a proof.
* Each guard and each conformance suite has a plant: a defect that must make it fail. CI runs each plant and requires the failure. A check that never failed under its plant is not trusted.
* Each test file starts with a comment that names the plant or the defect that breaks it.
* A fix comes with a test that fails before the fix.
* Case tables live in `tests/cases/*.tsv` with the columns input, action, expected.

## 2. Layers

| Layer | Id | Tool | What it proves |
| --- | --- | --- | --- |
| Unit, property, conformance | `U-name` | `cargo test`, `proptest`, the suites of file 21 section 9 | one function or one trait against its rules |
| Simulation | `M-nn` | `podswarm-sim` | invariants I1 to I7 over interleavings, crashes and faults, on the real engines |
| Guard | `G-nn` | scripts in `scripts/` | a rule of the repository cannot break silently |
| Fault | `F-nn` | the real binaries on loopback with a faulting link, store and process tree | the invariants and the recovery on real processes and real SQLite |
| Environment | `E-nn` | real hosts, VMs, shaped links, `qemu-user`, live roads | behaviour on other systems, kernels and links |
| Soak | `S-nn` | long runs on a dedicated host | no leak, no drift |
| Benchmark | `B-nn` | `podswarm-bench` and the load generator | numbers with their conditions |

## 3. Deterministic simulation

### 3.1 The contract
1. **One seeded scheduler.** Every concurrent task of a simulated run is a cooperative task on one thread. The scheduler picks the next runnable task with `ChaCha8Rng(seed)`. The same seed gives the same trace. A failure prints the seed and the command that replays it: `PSW_SEED=0x1a2b cargo test -p podswarm-sim -- NAME --exact`.
2. **Every source of nondeterminism is behind a trait** that the real binary implements with the system: `Clock` (monotonic, fence and wall), `Net` (roads and links), `Disk` (the `Store` trait, the journal, blob files), `Rng`, `Spawn` (the executor), `Timer`. The layered crates call none of these directly (guard G-08).
3. **Fake clock.** Time moves only when every task is blocked (a jump to the next timer) or when the scheduler injects a step. Each node has its own clock with a rate offset of up to 1 percent and a jump for a suspend.
4. **Fake network.** One link per pair with a script from the seed: latency, jitter, bandwidth, drop, duplicate, reorder, cut and restore, a half-open link. A fault budget per run (at most 5 cuts) lets a run finish.
5. **Fake disk.** A crash at a random step of a commit (before, during, after the sync), a sync error, a full disk. A crash drops all memory of one node and restarts it from its committed rows and its journal.
6. **Real engines.** The real `podswarm-core`, `podswarm-coord` and `podswarm-worker` run in the simulation. The executor is a simulated process: an exit code after `d` ms, a tree with children that can outlive a worker kill.
7. **Oracle.** After each step the oracle checks I1 to I7 on the committed store and the memory of each node. A run ends when every task is terminal or after the step budget (200,000 steps). A stuck run (not terminal, no timer, no event) is a failure.
8. **Shrinking.** The run records `(seed, [(step, event)])`. On a failure, delta debugging drops events until the failure goes away; the minimal log goes to `tests/regress/` and replays with no scheduler.
9. **Budgets.** 1,000 seeds per property on each push; 1,000,000 seeds each night; every log in `tests/regress/` on each push.
10. **Mutation plants** (section 3.3) run each night. Each must fail within the per-push seed budget.
11. **Limits.** The simulation does not check: the clock arithmetic of `grace_eff` on real clocks (F-05), TLS, the behaviour of SQLite and of the file system (F-01, F-07), real process trees (F-19, F-20), the kernel parts of the view and of spreading (sections 7 and 8).
`loom` checks the three lock-free places: the in-process pipe, the writer queue, the inbox of the actor.

### 3.2 Properties

| Id | Checked after every step |
| --- | --- |
| M-01 (I1) | each non-terminal task is `held`, `waiting` or `ready`, or has an open row with a deadline |
| M-02 (I2) | the committed store holds at most one accepted result per task, and it is a success |
| M-03 (I3) | `attempt_no` rises per task, also across a restore |
| M-04 (I4) | at most one open row per task, except the rows of T4s with `speculate` (file 24) |
| M-05 (I5) | no attempt runs past `t_ok + silence_s + kill_grace_s` on the fence clock of its worker |
| M-06 (I6) | no client saw `submitted` or `ack` for data that a crash removed |
| M-07 (I7) | `failures` and `losses` never fall, except by `retry` |
| M-08 | the state-by-event table of file 09 is generated from the transition code; no cell is undefined and every cell matches the code |

### 3.3 Mutation plants
Each plant removes one guard in the real code. The named property must fail.

| Plant | Fails |
| --- | --- |
| drop `WHERE state < 5` from the terminal update | M-02 |
| accept a result from a worker that does not hold the attempt | M-02 |
| send `ack` before the commit | M-06 |
| let the worker skip the fence, or drop the `Fence` message to the spawner | M-05 |
| use `grace_s` where the rule needs `grace_eff` (`silence_s` 600, 1 percent skew) | M-05 |
| count a loss as a failure, or forget the cap of `max_lost` | M-07 |
| skip the deadline timer of an `offered` row | M-01 |
| reuse an `attempt_no` after a restore | M-03 |
| let T11 ignore a `stopping` row | M-04 |
| send a `cancel` before the offer that waits for its commit | M-04 (M-16) |

### 3.4 Scenarios
Fixed scenarios with a seed list. Each passes when the oracle stays green and the stated observation holds.

| Id | Input and action | Expected observation |
| --- | --- | --- |
| M-10 | the attempt wall deadline passes while the worker sends `hb` | the old row gets `cancel{kill}`; no second attempt starts before the row is known dead |
| M-11 | store backpressure for 30 s while results flow | `hback` is never delayed; no `self_fence` |
| M-12 | a worker host suspends for 10 min during an attempt | the attempt ends at its fence time on wake, before the worker sends a frame; one copy at a time |
| M-13 | restore of an older backup; a worker holds results of the old generation | the worker kills its attempts and starts empty; no old result is accepted for another task |
| M-14 | cancel and supersede of rows that hold capacity | the capacity returns; no slot leaks over 10,000 tasks |
| M-15 | `retry` during the kill ladder of a cancelled task | `err{attempt_live}`; no second copy runs |
| M-16 | an `at_most_once` offer waits for its commit; a cancel of it follows | the cancel leaves after the offer |
| M-17 | frames arrive from a connection that the authority replaced | they are dropped; no attempt of the new session is killed |
| M-18 | two processes with one worker key and another `inst` | `duplicate_identity`, the worker is `suspect`, no second copy of an `at_most_once` task |
| M-19 | worker crash between the sync of the spawn record and the exec, `at_most_once` | the task ends `lost`; it is never offered again |
| M-20 | the polite signal of the fence, then a renewal arrives | the attempt ends `killed`, reason `self_fence`; the loss budget is spent, not `retries` |
| M-21 | the authority restarts 3 times in 600 s | the crash loop alarm is set; open rows still end by their deadlines |
| M-22 | `ready` arrives and no `hb` is answered | the fence is not renewed by `ready` |
| M-23 | cancel while a success is in flight; the cancel reaches a worker that no longer holds the attempt | the row ends on the success; `late_ok` is set; no capacity leak |
| M-24 | a parked worker fits a class; another worker holds `k` unstarted tasks of it | tail reclaim returns `ceil(k / 2)` tasks and the parked pull gets them |
| M-25 | a late result for an attempt that ended `lost` | the attempt record is updated once; the task state does not change |
| M-26 | `speculate`: the two rows end in each order, with each mix of success, failure and loss; a release of the offered row while the other runs | a success ends the other row `superseded`; with no success the task takes T7 when any row failed, else T8; the task is `running` while a row runs and `leased` while a row is only offered, never `running` with no copy (file 24, D-128) |
| M-27 | `--halt-on-fail 2` with mode `drain`; then `--continue-groups` | no new start after the second failure; with the flag the next group opens when all are terminal |
| M-28 | two priority levels, a full queue at the higher level | the lower level gets no offer until the higher is empty |
| M-29 | two runs with weights 1 and 3 | the ratio of delivered tasks over 10,000 is within 10 percent of 1:3 (A-41) |
| M-30 | a submit with needs that no known worker fits; a submit past `class_max` | `needs_unsatisfiable`; `busy` with the text `class_max` |
| M-31 | a worker with a lifetime that ends during a run | drain at `end_w - drain_margin_s`; `killed` reason `lifetime` spends no loss budget |
| M-32 | a zombie attempt commits `seq` 4 after attempt 2 committed 4 | the commit is refused; the stored checkpoint is the one of attempt 2 |
| M-33 | a drain asks for a checkpoint | outcome `checkpointed`; the next attempt has `TASK_RESUMED=1`; no retry is spent |
| M-34 | the worker of a pinned `each` task is revoked | the task ends `cancelled`, reason `worker_gone` |
| M-35 | a reconnect of 1,000 simulated workers after an authority restart | each worker is `ready` within `silence_s / 3`; no `self_fence` |
| M-40 | a cold pool of 10 roads with delays of 50 to 2,000 ms | the command starts on the chosen machine at most `place_wait_ms` after its road opened |
| M-41 | the caller has 4 cores, a remote machine 32; no history | the remote machine is chosen |
| M-42 | a residency rule `allow_juris = ["eu"]` and only a `us` cell | exit 79; no `view` or `blob_put` stream opened |
| M-43 | a coordinator states `juris = us` where the pool file says `eu` | refused before any byte of the run |
| M-44 | `pool` asked on a worker with no podnet | the run gets `host`; the record has `asked: pool, got: host`; one stderr line per session |
| M-45 | `none` and `exit:x` on a worker with no enforced rung and no podnet | both refused with `needs_unsatisfiable`; no attempt starts |
| M-46 | a task asks `boundary = confined`; one worker reports `none` | the task is never offered to that worker |
| M-47 | a task asks `sandbox` on a pool with no podvm | `needs_unsatisfiable` |
| M-48 | `--shield private` on a remote macOS machine with `trust = "shared"` | `shield_unavailable`, exit 79 |
| M-49 | an offer is in flight when the worker writes a `pull` with its free capacity; the `pull` arrives after the authority sent the offer | the authority subtracts the tasks of each offer after `pull.seen`; the worker never holds more unstarted tasks than the depth rule allows; no slot is offered two times (D-125) |
| M-50 | a swarm run with `checkpoint.encrypt = "run"`: a first attempt starts with no home of the submitter connected; then the home connects; the worker dies and the resume finds no home; again with `--key-escrow` and no home | each start with no answer leaves the task `held` with reason `needs_key`; the attempt starts, or resumes from the checkpoint, when the home answers `ckpt_key_req`; with escrow the coordinator answers and the task resumes at once; no key reaches a worker that fails the shield proof (D-126) |

## 4. Guards

| Id | Rule | Plant | Good input |
| --- | --- | --- | --- |
| G-01 | the bundled SQLite is at least 3.51.3; an older one refuses to open a store with exit 70 | a stub `sqlite3_libversion_number()` of 3051002 | the real build |
| G-02 | no source file over 500 lines | a 501-line file | the tree |
| G-03 | a Linux musl binary has no `NEEDED` entry and no interpreter | a dynamic link | the musl builds |
| G-04 | an Apple or Windows binary imports only system libraries | a non-system DLL | the real builds |
| G-05 | documents have no em dash, no ` - ` or ` -- ` as a dash, no absolute machine path | one line of each | the tree |
| G-06 | the checked-in schemas equal the generated ones | a hand edit of one schema | untouched |
| G-07 | a canary (invite, key file, a secret of `secrets.1`, a deny-list variable) is absent from logs, `/proc/*/cmdline`, `/proc/*/environ` of tasks, the store and the audit rows | a task that logs the canary | a clean run |
| G-08 | the layer rule of file 21; no `Instant::now`, `SystemTime::now`, `thread::spawn`, `tokio::spawn` or `HashMap` iteration in a decision in the layered crates | `use tokio` in core | the tree |
| G-09 | each wire field has a limit in `limits.rs` | a new string field with no limit | the tree |
| G-10 | no field, flag or message is named for a compiler, toolchain or cache key (N1) | a `--compiler` flag | the tree |
| G-11 | the create refuses a store whose `auto_vacuum` is not 2; exit 70 | `auto_vacuum` after the first table | the DDL of file 11 |
| G-12 | a coordinator refuses `coord.db` at mode 0644 with exit 77 | mode 0644 | mode 0600 starts |
| G-13 | the stripped static x86_64 musl binary has at most 10,000,000 bytes (A-09) | a binary padded past the bound | the real build |
| G-14 | `cargo deny` passes with the allow list of file 21; `THIRD-PARTY-NOTICES` holds SQLite, zstd, mimalloc and BLAKE3 | a dependency under GPL-3.0; a notice removed | the release tree |
| G-15 | the worker with feature `sealed` and `sev` (`crypto_nossl`) links static on x86_64 musl | a build with the OpenSSL backend | the real build |
| G-16 | one hash and one compressor: no `sha256:` content id and no gzip codec in proto, store or view | a `sha256:` id constant | the tree |
| G-17 | each conformance suite fails on its planted bad implementation | a suite with its plant removed | the suites |
| G-18 | `SKILL.md`, `llms.txt` and the state-by-event table equal their generated form | a hand edit | generated |

## 5. Unit, case and conformance tests

| Id | Input and action | Expected observation |
| --- | --- | --- |
| U-tmpl | the cases of `tests/cases/tmpl.tsv`: every token, `{{`, `}}`, `\|q`, a bare `#`, a bad token | the expected expansion; a bad token exits 64 before a task is queued |
| U-gnu | the cases of `tests/cases/gnu.tsv` against GNU parallel and xargs: line handling, quoting, exit codes, empty input, last newline | the recorded output and exit code |
| U-parity | each KEEP row of file 20, as a command against HyperShell 2.8.7 and 2.9.0a7 and against podswarm | the same effect (A-17) |
| U-recipes | each recipe of file 19 with `--dry-run` through the real parser | exit 0 and the expected plan |
| U-sel | a 20-task fixture; `cancel` with tag and expression selectors; then `--dry-run` | exactly the matching tasks change; `--dry-run` changes none |
| U-exit | each exit code of file 19 forced by a fixture | the code and the class word |
| U-run-exit | `podswarm run` over a fake road: a command that exits 0, 7, by `SIGTERM`, past `--task-timeout`, not executable, not found; then a road that fails | exit 0, 7, 143, 124, 126, 127; then 255 with the class on stderr; `--json` gives both |
| U-run-tty | `run` with stdin and stdout terminals; with stdout a pipe; a window change; Ctrl-C; `~.` after a newline | a pty only in the first case; the far side sees the new size; the command gets `SIGINT`; `~.` ends `run` with 255 |
| U-limits | each size limit of file 05 at the limit and one byte over | accepted, then `too_large` |
| U-config | config precedence; a workspace `.podswarm.toml` with `coordinator` or a widening residency key | the precedence holds; an error names the key |
| U-env | a queued task on a worker that serves other submitters; a `podswarm run` with deny-list variables in the caller's environment | the task gets only the allowlist of file 12; the run gets the caller's environment minus the deny list of file 13 section 5 |
| U-retention | a store with runs past `retain_days`, output past `retain_output_days`, blobs past `blob_ttl_days`, and a blob under 24 h old | the sweep removes the old rows and blobs; the young blob stays |
| U-escape | output with control characters through `logs`, `show` and the log file | each control character shown as an escape |
| U-statement | statement checks 1 to 7 of file 16, each broken once | `unauthorized` for each |
| U-skill | generate `SKILL.md` and `llms.txt` from the tables | equal bytes with the golden files |
| U-verify | `verify.1`: the digest of fixed results with outputs | equal to the vectors of file 24 |
| U-audit | `audit-chain.1`: a chain walk; a chain with a cut tail; a chain from `meta.audit_base` | the first passes; the cut is found at its row; the walk from the anchor passes |
| U-member | a run at `guest` with a `shared` exit; then `trust = "own"` | refused; then served |
| U-place-cpu | 100 machines with reports and a learned table | median decision time at most 1 ms on x86_64 (A-36) |
| U-place-local | a learned entry of 40 ms | the run stays local; no road opens |
| U-calib | the start of a worker on x86_64 and Cortex-A53 | calibration at most 150 ms cold, none when cached (A-38) |
| U-store-readonly | `sqlite3 -readonly` on the store of a running coordinator | the task counts; exit 0 |
| U-attest | a recorded valid SNP report and chain (the test vector of file 21, section 6.6); each of measurement, report data, policy debug, VMPL, TCB, signature and chain with one bit flipped; a valid report for another nonce; one for another guest key; the measurement of the release guest set for 1, 2, 4, 16 vCPUs | the valid one passes; each other one fails with its named field; the measurements equal the golden values |
| U-conf-road | the `Road` suite on `mem`, `unix`, a local sshd and an `exec` loop | section 10 |
| U-conf-view | the `ViewRung` suite on `fuse`, `fuse-userns`, `trap`, `sync` | section 7 |
| U-conf-exec | the `Executor` suite on each rung of the host | the kill ladder, the residual count, the limit modes and the outcomes of file 12 |
| U-conf-store | the `Store` suite on `MemStore` and `SqliteStore` | each command acknowledged after it is durable at its level; I2 enforced by the store |
| U-conf-ckpt | the `Checkpointer` suite on the blob store and one sink plugin | save, restore, a missing blob falls back to the older checkpoint |
| U-conf-place | the `Placement` suite on the in-tree policy | the filter and the scores of file 08 |
| U-conf-admit | the admission suite on the in-tree policy and one `admit` plugin | allow, refuse, timeout with `admit.on_error` |

## 6. Fault tests

The real binaries run on loopback. The faults come from a seed. Each row runs the stated count.

| Id | Input and action | Expected observation |
| --- | --- | --- |
| F-01 | `kill -9` of the coordinator at a random point; 1,000 runs of 10,000 tasks | after restart every acknowledged submit is present; no task is lost; at most one accepted result per task; every task ends terminal |
| F-02 | `kill -9` of a random worker with a task tree; variant: the task starts a `setsid` child; 1,000 runs | tasks run again within their budgets; residual 0; each tree is dead within `kill_grace_s + 2 s` of the kill |
| F-03 | a link cut of a random length inside and outside the silence budget; 1,000 runs | a shorter cut gives zero re-runs (A-14); after a longer cut the worker kills before the authority offers again |
| F-04 | duplicate, reorder and delay of frames; 1,000 runs | the oracle of section 3 run on the real engines returns Ok; a duplicate `result` changes nothing |
| F-05 | a clock rate skew of 1 percent between worker and authority; 200 runs, at the defaults and at `silence_s` 600 | the gap between the kill on the worker and the new offer is at least `grace_s - 1 s` in each run; the smallest gap is printed; a shape with `silence_s < 2 * (hb_s + rtt_max)` is refused |
| F-06 | the state directory of the coordinator at 95 percent full | submits get `busy`; running tasks end `succeeded`; work goes on when space returns |
| F-07 | `SIGKILL` of the writer in the middle of a transaction; 500 runs | the store opens; `integrity_check` is `ok`; every acknowledged submit is present |
| F-08 | the fault store fails a sync, then a write | the coordinator sends no `ack` after the error and exits 70 |
| F-09 | a hostile worker sends a result for an attempt it does not hold, and an output path `../../x` and `CON` | `dropped`; the paths refused with `bad_request`; nothing written outside the target |
| F-10 | restore of an older backup | a new generation; workers with the old `gen` kill their attempts; a task whose input blob is missing fails `spawn_failed`, reason `input`; a worker key with no row must enrol again |
| F-11 | a server with the real coordinator certificate that signs with another key; a TLS 1.2 only client; an Ed25519 client certificate | the first fails the handshake; the second is refused; the third is accepted and mapped to its row |
| F-12 | an enrol of a key that has a worker row under another invite | `unauthorized` and one `enrol_refused` event |
| F-13 | a second session of a worker: the same `inst`; another `inst` while the old one is live; another `inst` after `2 * hb_s` of silence | replaced at once; `duplicate_identity` and `suspect`; replaced |
| F-14 | a 5 KiB `hello` before `ready`; a slow client; 10,000 connections from one prefix on a 1 GiB machine | the `hello` is refused; the slow client is cut at its stage deadline; enrolled workers keep their sessions; RSS stays under 64 MiB over the base |
| F-15 | a worker sends `hb` and never ends an attempt | the attempt ends at `max_attempt_s` by T8 |
| F-16 | a `confined` task plants a symlink to the worker key and names it in `outputs` | `output_rejected`; no key byte uploaded |
| F-17 | an enrol cut before `ready`; a second `join` with the same state directory | the use count of the invite is unchanged in both |
| F-18 | `ulimit -n 256`, then 300 workers connect | a named error and `busy` with `retry_after_ms`; no crash |
| F-19 | `SIGKILL` of the worker, of the spawner, of a keeper, alone and together | each attempt process, a `setsid env -i sleep` grandchild included, is dead within `kill_grace_s + 2 s` |
| F-20 | two attempts at once; one leaks a `setsid` child | both exit codes and both residual counts are right; only that tree is killed |
| F-21 | coordinator certificate: start, restart with the same pin, rotation; `ready.pins` with one pin only | after rotation both pins pass, then one; the client keeps the old pin until it saw the other key and 24 h passed |
| F-22 | a `confined` task reads `/proc/<worker>/environ` and `/proc/<worker>/mem`; it opens `socket(AF_UNIX)` under Landlock ABI 9 | each read fails; the worker environment holds no canary; the socket call fails |
| F-23 | a worker that starts with `SIGINT` ignored and umask 077 | the task sees `SIG_DFL` for `SIGINT` and umask 077 |
| F-24 | 1 MiB of random output on each stream | an accepted result; head and tail of `capture_max`; `len` right; `trunc` true |
| F-25 | a subscriber paused on slot 1 | slot 2 keeps running; slot 1 spills up to `spill_max` |
| F-26 | `kill -9` of a worker after a partial blob upload | the next upload resumes at the `have` offset; the id matches |
| F-27 | tar inputs with `..`, an absolute name, a hard link, a symlink, a device, 100,001 entries, a compression bomb | each refused; nothing written outside `TASK_DIR` |
| F-28 | a `chmod` of a cached blob file that a task holds as a link | the worker fetches the blob again before the next use |
| F-29 | a task exits with `checkpoint.exit_code` and the commit fails | outcome `exited`, reason `ckpt_failed`, a failure |
| F-30 | `kill -9` of a worker between the sync of an `at_most_once` spawn record and the exec | the task ends `lost`; never offered again |
| F-31 | `self fetch` with a bad signature; with a bad hash | the binary cache is unchanged |
| F-32 | a process of another uid, and one of the same uid without the attach secret, connect to the reattach socket | both refused |
| F-33 | a task over `limits.mem_mib` on a `polled` worker; a task that fills the disk under the reserve | outcome `signaled`, reasons `mem_exceeded` and `disk_full`; `retries` spent |
| F-34 | `sig.1`: an unsigned shape on a worker with `require_signed_by`; a signed `shell` shape with an unquoted token | both refused with `policy` |
| F-35 | `secrets.1`: submitter B names the secret of submitter A | `unauthorized`; no worker gets the secret |
| F-36 | `jobs.1`: a job of 1,000 replicas that crash at start | the job pauses within `crashloop.window_s` |
| F-37 | a run asks an identity token for an audience not in `id.audiences`; a hook names a command from a workspace file | the token is refused; the hook is ignored |
| F-38 | a worker asks `blob_get` of a blob of another owner, and of a blob that no attempt it holds names | `not_found` for both; no byte sent |

## 7. Tests of the view

| Id | Input and action | Expected observation |
| --- | --- | --- |
| F-40 | a link cut during write-back | each op applied once, in order |
| F-41 | the caller edits a file during the run | a conflict copy; no change lost |
| F-42 | the watcher of the caller overflows | the view revalidates; no stale read |
| F-43 | the worker crashes with a non-empty write-back log | the next session applies the log first |
| F-44 | a clock skew of plus and minus 30 s, with `cargo` and `make` | no stale output; no rebuild of an unchanged file |
| F-45 | `rm -rf src` on the worker | the deletes are held for the user |
| F-46 | a hostile worker asks a `nid` that the home did not issue, writes through a symlink, writes `.git/hooks/x`, sends 1,000 `not_found` asks | each refused or held; the home closes the view with `err{policy}` |
| F-47 | the workspace holds deny-list files and a `.git/config` with an `extraheader` canary | each denied path is absent (`ENOENT`); `.git/config` has no canary |
| U-view-back | `run HOST -- cargo build` with `target/` ignored by git and a tracked file changed by the build; then `[view] pull = ["target/debug/app"]`; then `podswarm pull target/debug/app` | the tracked change is on the origin; `target/` is absent on the origin and the end line names it and its size; with the rule or the verb the file arrives with the same id |

`U-conf-view` runs one suite on each rung: lookup, read, write, rename, unlink, `fsync`, the same absolute path, the clock offset, a placeholder fill on `trap`, and the sync round trip. Targets A-20 to A-23 and A-25 to A-28 have benchmarks B-20 to B-27.

## 8. Tests of spreading

| Id | Input and action | Expected observation |
| --- | --- | --- |
| U-spread-takeover | the four takeover cases (a `fork` plus `execve` that moves, a `posix_spawnp` that moves, a local exec that stays, a failed exec that returns `ENOENT`; file 21, section 6.1), a caller with threads, a `#!` script, on x86_64 and aarch64 | the same pid; the same exit status as a local run |
| U-spread-fds | each row of the table "What crosses an exec" of file 07 | the rule of the row holds |
| U-spread-causal | a writer on member B exits; a reader on member C opens; 10,000 rounds | zero stale reads |
| U-spread-append | three members append to one log | no line lost |
| U-spread-lock | `flock` on the anchor and on a member | they exclude each other |
| U-spread-signals | Ctrl-C, Ctrl-Z, `fg`, `SIGKILL` of the stub | the shell sees the result of a local run |
| U-spread-cpus | `nproc` and `available_parallelism` in a spread session | the pooled core count |
| U-spread-arch | an exec of another architecture than the members | it stays local |
| U-spread-decide | a decision on a warm table of 4,096 entries, argv 128 KiB | median and p99 within A-29 |
| F-50 | a member dies before its first output, then one dies after it | the first exec runs again once; the second exits 75 with the one line of file 07 |
| F-51 | a link cut shorter than the reattach window during a moved compile | nothing runs again; the output is whole |

## 9. Tests of the shield levels

Each test plants a canary: 32 random bytes in hex, in a file name, a file body, a variable and an argv element of the caller. They are live tests.

| Id | Input and action | Expected observation |
| --- | --- | --- |
| E-10 | `private`: a session writes the canary into 1,000 files and a 1 GiB file and ends; as root, `grep -r` over each disk-backed mount and the store directory | zero hits |
| E-11 | as E-10, with `kill -9` of worker, spawner and payload at once during the write, then any podswarm command of the user | zero hits; no area directory |
| E-12 | the ssh connection drops by a firewall rule | after the reattach window plus 5 s no process of the session lives and the area is gone |
| E-13 | deny-list files with canaries in the workspace; `AWS_SECRET_ACCESS_KEY`, `GITHUB_TOKEN` and a live `SSH_AUTH_SOCK` with `ForwardAgent yes` in the ssh config | as root: no canary in any file, `/proc/*/environ` or `/proc/*/cmdline`; no agent socket; each denied path gives `ENOENT` |
| E-14 | a VM with 1 GiB of RAM and 4 GiB of swap; the area and the heap filled with canary pages; a second process takes 2 GiB | no canary on the swap device when the report says `locked`; the report says `possible` on `tmpfs-ns` with no cgroup control |
| E-15 | after a session that kept state; then one object with a flipped byte; then an older manifest put back | no canary and no file name in the store; each change gives `store: discarded` and a correct build |
| E-16 | during a session, where the kernel has `memfd_secret` | `/proc/<worker>/maps` shows `secretmem`; a root read of that range fails |
| E-17 | during and after a session | no file under the user's home or `/var/log` differs, except the sshd lines and the binary cache |
| E-18 | user namespaces off, no `$XDG_RUNTIME_DIR`, no `/dev/shm`; `run --shield private` | exit 79, reason `no_memory_area` |
| E-19 | `guest`: E-10 to E-17 at `guest`, and as root during the run `ps -eo args`, `/proc/*/environ`, `/proc/*/fd` link names, `ss -xap`, `tcpdump -i any -A`, `strings` over the disk file | no canary |
| E-20 | `guest` on a host with no `/dev/kvm` and no `guest_tcg` | `shield_unavailable`, reason `no_kvm` |
| E-21 | `ip link` in the guest | no network card |
| E-22 | `sealed`: a real launch on an SNP host | attestation passes; the run ends with its exit code |
| E-23 | the host replaces the initramfs with one byte flipped | `attestation_failed`, field `measurement`; no file or key sent |
| E-24 | the host launches plain KVM and answers with a recorded old report | `attestation_failed`; no file or key sent |
| E-25 | as root during the run, reads of guest RAM through `/proc/<qemu>/mem` | no canary |
| E-26 | `run --shield sealed` on a host with no SNP | `shield_unavailable`, reason `no_snp` |
| E-36 | `private`, `area = "auto"`, a FUSE view, `area_max` of 2 GiB; a build writes 3 GiB into the owned `target/`; then the same build again | the first run ends with reason `area_full` and one CLI line with the cause and the way out; the second session serves `target/` from the sealed store and the build passes; no canary on disk in plaintext |
| E-37 | `run --shield private --area sealed` with the view rung `sync` | exit 79, `shield_unavailable`, reason `no_sealed_area` |

`U-attest` (section 5) and G-15 (section 4) are the unit and build tests of `sealed`.

## 10. Tests of roads

| Id | Input and action | Expected observation |
| --- | --- | --- |
| U-conf-road | the `Road` suite on `mem`, `unix`, a local sshd and an `exec` loop: a 1 GiB binary, half close, kill of the child, the stderr ring, exit status 0, 7 and 255 | each row equal on each road; the binary has the same hash |
| U-road-rc | a `.bashrc` that prints 70 KiB, one that prints 1 KiB, one that reads stdin; login shells `bash`, `dash`, `csh`, `fish` | the 1 KiB and stdin cases link; 70 KiB fails with the ring shown; no byte of the link lost |
| E-06 | bootstrap on a fake road, an Alpine busybox host, a Dropbear server, a `noexec` home, a home on NFS with 8 hosts at once | each host runs the binary with the right hash; no `.part` file stays |
| E-07 | a firewall cut of 10 s during `podswarm run HOST -- sh -c 'sleep 60; echo ok'` | prints `ok`, exits 0; no output byte lost or repeated |
| E-08 | `MaxSessions 1` on the server | one connection per session; the run succeeds |

B-29 measures the throughput of the roads.

## 11. Environment tests

| Id | Input and action | Expected observation |
| --- | --- | --- |
| E-01 | a worker under `ulimit -v`, `taskset` to one core, `nice 19`, and a cgroup with `MemoryMax=64M` and `CPUQuota=25%` | the worker test suite passes; RSS stays under the limit |
| E-02 | 50 workers on loopback through the shaping proxy (100 ms, 1 percent loss), 100,000 `true` tasks | all succeed; no duplicate accepted result; exit 0 |
| E-03 | the worker test suite under `qemu-user` for armv7, aarch64, riscv64, i686 | all tests pass; no timing is reported |
| E-04 | a VM with a 5.x kernel and no Landlock | the worker reports no `confined` and the reason |
| E-05 | a host with no `/etc/resolv.conf` (a Termux layout) | the worker resolves and connects in under 1 s |
| E-09 | `hub.1`: coordinator, hub and 500 workers as processes on one host | 50,000 tasks end; the hub holds no key (a planted key in its memory makes the test fail) |
| E-27 | a `netns` hold under the `pidns` containment rung | the namespaces nest; the tree kill ends each process; the command sees only the door |
| E-28 | a static Go program that ignores proxy variables; `exit:x` on the `notify` rung | the exit sees each connection; the worker interface shows none to the destination |
| E-29 | `none` on the `netns` and `deny` rungs | TCP connect, UDP send and a raw socket fail; a Unix socket outside the grants fails |
| E-30 | `home=5432` | the attempt reaches the caller's loopback port; no socket listens on the worker host for that port |
| E-31 | `exit:x` on a podssh exit and a UDP send | the send fails; `udp_refused` counts it |
| E-32 | `podswarm x` over two real machines, one remote, a 10,000-task sweep | all succeed; recorded by hand with the output |
| E-33 | the worker and road tests on a hosted Windows runner over OpenSSH | all pass |
| E-34 | the worker and road tests on a hosted macOS runner | all pass |
| E-35 | `podswarm x` with the default `--view auto` from a directory on an NFS export; worker 1 mounts the same export at the same path; worker 2 mounts it at another path; worker 3 has a copy where one sampled file differs | worker 1 runs in the mount with no view; workers 2 and 3 get a view; the outputs are equal (D-127) |

## 12. Soak

| Id | Input and action | Expected observation |
| --- | --- | --- |
| S-01 | 1,000 simulated workers, tasks of 10 ms to 60 s, worker churn, 72 h of real time | coordinator RSS grows under 5 percent after the first hour; the WAL stays under the alarm of file 11; every task terminal |
| S-02 | one worker, 10,000,000 `true` tasks | worker RSS flat within 2 MiB; no descriptor growth; no task directory left |

## 13. Benchmarks

### 13.1 Method
* Each run records: the host (CPU model, cores, RAM, kernel, file system and mount options, disk model, governor, turbo), the build (commit, `rustc -V`, target, features, profile, binary size, SQLite version), every parameter and seed.
* Procedure: 10 s warm-up, 60 s measure, at least 5 repetitions (3 for runs over 10 minutes), variants in alternating order. Result: median, p10, p90 and the raw samples, as one JSON document of schema `bench.1`.
* One benchmark at a time per machine. CPU pinned where stated. The benchmark process and the system under test are separate processes.
* Measure from outside: a throughput counts the results that the load generator receives, and a check after the run compares it with the row count of the store. Resource use comes from `getrusage` and `/proc`, read by the harness.
* A comparison "X is faster than Y" runs both on one host in one session. Numbers from two hosts never share a table without the host columns. An emulated run is never reported as a timing.

### 13.2 The load generator
`podswarm bench load` is part of the binary. It runs N simulated workers that speak the real protocol over the in-process pipe, a Unix socket or loopback `wss`, with a null executor that reports success after a duration `d` from a distribution. It runs M simulated submitters at a set rate. It can route each link through the shaping proxy of `podswarm-sim` (latency, jitter, bandwidth, cuts). It prints `bench.1` documents.

### 13.3 List

| Id | What | Target |
| --- | --- | --- |
| B-01 | fsync loop of 512 bytes; the schema of file 11 with bundles 1, 10, 100, 1,000 at FULL and NORMAL, on SSD, SD card, eMMC, tmpfs | the store bound of file 10 |
| B-02 | coordinator throughput: W in 10, 100, 1,000, 5,000; `d` in 0, 10 ms, 1 s; levels `strict`, `batched`, `memory`; in-process pipe and loopback `wss` | A-01, A-02, A-03 |
| B-03 | worker CPU per task (`getrusage(RUSAGE_SELF)` delta over tasks, children excluded), `argv` `true`, each row of the cost table of file 12 within 1.5 times its share | A-05 |
| B-04 | one 4-core Cortex-A53 worker, local coordinator on another host; idle RSS | A-06, A-16 |
| B-05 | one worker with 4 slots, `d` 10 ms and 1 s, round trip 20, 100, 500 ms through the proxy | A-08 |
| B-06 | 1,000 to 20,000 idle connections from several load processes | A-15 |
| B-07 | `true` through boundaries `none`, `confined`, `sandbox`, `vm` on one host | recorded |
| B-08 | a real sweep of 10,000 tasks of a real tool on 2 or 3 machines | recorded |
| B-09 | 100,000 no-op tasks on one machine: podswarm, HyperShell 2.8.7 and 2.9.0a7, HyperQueue, GNU parallel | recorded |
| B-10 | one `x` shape on no-op, a C compile and a 100 MB copy; G-10 green | recorded; one code path |
| B-11 | time from `join` to the first running task at 100 ms round trip | A-11 |
| B-12 | coordinator restart to `ready` with 100,000 and 1,000,000 tasks | A-12 |
| B-13 | 100 emulated machines enrolled and running from the walk-through of file 19 | A-13 |
| B-14 | `hback` latency during a 100 MB blob transfer at 1 Mbit/s and 100 ms | A-18 |
| B-15 | coordinator pinned to one CPU, 200 workers, offers of 1, 10, 100, `strict` | each run ends; no stall of the actor or the writer over 1 s |
| B-16 | 1,000 workers reconnect after a coordinator restart | each `ready` within `silence_s / 3` |
| B-17 | the WAL checkpointer on its own connection against the writer, SSD and SD card | throughput and peak WAL size recorded |
| B-18 | 1,000,000 `true` tasks at `strict` | A-39 |
| B-19 | `seq 100 \| podswarm x echo {}`; 100,000 tasks | A-07 |
| B-20 | `podswarm run HOST -- true` on an open road; then with no live worker | A-20, A-42 |
| B-21 | warm incremental build of a mid-size Rust workspace through each live rung against the same build on the machine | A-21 |
| B-22 | edit one 10 KB source file and build again; bytes on the link before the compiler starts | A-22 |
| B-23 | first run on a machine with no podswarm at 20 Mbit/s | A-23 |
| B-24 | a wide C build and a cargo workspace on 1, 2, 4, 8 members, LAN and an emulated WAN | A-19, A-24, A-34, A-35 |
| B-25 | warm and cold start of a 100,000-entry tree | A-25, A-26 |
| B-26 | caller CPU of a warm run on a 4-core PC with no SHA instructions | A-27 |
| B-27 | `sync` cold: 10,000 files, 100 MB at 10 Mbit/s | A-28 |
| B-28 | exec bench of each spread rung; 1,000 moved `cc -c`; a configure script with and without `--spread` | A-30 to A-33 |
| B-29 | 1 GiB through `nc`, `ssh cat` (`chacha20-poly1305`, `aes128-gcm`), `podssh`, `blob_get` on each, loopback and one WAN pair | MB/s and CPU recorded; the window values of file 04 checked |
| B-30 | placement over 100 machines; a cold pool | A-36, A-37, A-38 |
| B-31 | a Raspberry Pi 4 or 5 coordinator, 200 workers on another host, LAN | A-04 |
| B-32 | wire bytes per task of `true` at steady state | A-40 |
| B-33 | `pool` with a remote member (`uplink = true`): one 1 GiB transfer and 100 parallel flows through the member, with the authority on a 10 Mbit/s link and on a LAN | the rate of each flow and the bytes and CPU on the authority are recorded (K-17) |

## 14. Targets

Each row is a target `[T]` until a benchmark has run on a recorded host and the owner agreed the number. The conditions are part of the target.

| Id | Target | Conditions | Test |
| --- | --- | --- | --- |
| A-01 | at least 20,000 tasks/s | `strict`, x86_64 8 cores, SSD with fsync under 3 ms, 1,000 simulated workers, auto offers, loopback `wss`, `d = 0` | B-02 |
| A-02 | at least 50,000 tasks/s | as A-01 at `batched` | B-02 |
| A-03 | at least 50,000 tasks/s | embedded `x`, `memory`, in-process pipe | B-02 |
| A-04 | at least 2,000 tasks/s on an SD card, 8,000 on NVMe | Raspberry Pi 4 or 5 coordinator, `strict` | B-31 |
| A-05 | worker CPU per task at most 300 us on Cortex-A53, 60 us on x86_64 | `argv` `true`, boundary `none`, no subscriber | B-03 |
| A-06 | at least 400 `true` tasks/s | one 4-core Cortex-A53 worker | B-04 |
| A-07 | at most 35 ms; at most 0.5 ms overhead per task for 100,000 | `seq 100 \| podswarm x echo {}`, x86_64 | B-19 |
| A-08 | utilisation at least 95 percent | `d` 10 ms, round trip 100 ms | B-05 |
| A-09 | at most 10,000,000 bytes | stripped static x86_64 musl binary, default features | G-13 |
| A-10 | zero lost tasks, zero duplicate accepted results | F-01 to F-05 | F-01 to F-05 |
| A-11 | at most 5 s from `join` to the first running task | round trip 100 ms, idle coordinator | B-11 |
| A-12 | restart to ready: 5 s for 100,000 tasks, 10 s for 1,000,000 | SSD | B-12 |
| A-13 | 100 machines enrolled and running in under 300 s | emulated fleet; no download time | B-13 |
| A-14 | zero re-runs | a link cut shorter than the silence budget | F-03, E-07 |
| A-15 | at most 64 KiB per idle worker connection; 5,000 idle workers under 5 percent of one core | x86_64 coordinator | B-06 |
| A-16 | idle worker RSS at most 8 MiB | musl build | B-04 |
| A-17 | a HyperShell one-liner of the parity list runs unchanged | file 20 | U-parity |
| A-18 | `hback` p99 under 1 s | 100 MB blob at 1 Mbit/s, round trip 100 ms | B-14 |
| A-19 | a spread session is never slower than 1.1 times the run with no spreading | any build of B-24 | B-24 |
| A-20 | `podswarm run HOST -- true` adds at most 30 ms to the round trip | open road, live worker, warm view | B-20 |
| A-21 | a warm build through the live view within 10 percent of the build on the machine; `fuse` 3, `fuse-userns` 5, `trap` 8 percent | mid-size Rust workspace, owned `target/`; at shield `private` it holds for the memory rung, not for an owned directory in the sealed store (file 13, section 6.2) | B-21 |
| A-22 | under 64 KiB sent before the compiler starts | edit of one 10 KB file, warm view | B-22 |
| A-23 | the first run reaches the command in under 5 s | 20 Mbit/s, no podswarm on the machine, zstd copy of the binary | B-23 |
| A-24 | at least 5 times faster on 8 machines than on one | 1,000 independent compile steps of at least 1 s CPU; round trip under 1 ms; at least 1 Gbit/s; serial tail under 5 percent | B-24 |
| A-25 | `exec` within 2 round trips plus 50 ms (Linux caller), plus 300 ms (Windows caller) | warm start, 100,000 entries, unchanged, trace present, p50 | B-25 |
| A-26 | first `exec` within 2 round trips plus 100 ms | cold start, 100,000 entries, FUSE rung | B-25 |
| A-27 | caller CPU at most 50 ms | warm run, 4-core PC with no SHA instructions | B-26 |
| A-28 | at most 1.3 times the bytes divided by the bandwidth | `sync` cold, 10,000 files, 100 MB, 10 Mbit/s | B-27 |
| A-29 | a decision under 10 us median, under 50 us p99 | rules of file 07, warm table, argv up to 128 KiB | U-spread-decide |
| A-30 | interception plus decision under 80 us, and under 10 percent of a bare fork, exec and wait | local exec, rung `seccomp` | B-28 |
| A-31 | other system calls under 20 ns extra | rung `seccomp` | B-28 |
| A-32 | moved exec overhead under 2 round trips plus 5 ms warm; under 3 round trips plus 5 ms plus the missing bytes over the bandwidth cold | prefetch on | B-28 |
| A-33 | at most 10 percent slower than with no spreading | configure-like script, 10,000 execs under 20 ms each | B-28 |
| A-34 | efficiency at least 0.8 for up to 4 equal members | 500 steps of at least 1 s; round trip under 1 ms; 1 Gbit/s | B-24 |
| A-35 | efficiency at least 0.6 for up to 4 members | round trip 30 ms, 100 Mbit/s, the anchor in the site of the members | B-24 |
| A-36 | placement over 100 machines at most 1 ms of CPU | open roads, x86_64 | U-place-cpu, B-30 |
| A-37 | the command starts at most `place_wait_ms` after its road opened | cold pool of 10 machines with cached reports | M-40, B-30 |
| A-38 | calibration at most 150 ms cold, none when cached | x86_64 and Cortex-A53 | U-calib, B-30 |
| A-39 | at most 300 bytes of store and 1,000 bytes of WAL per task | 1,000,000 `true` tasks at `strict` | B-18 |
| A-40 | at most 100 bytes on the wire per task | `true`, positional rows, steady state | B-32 |
| A-41 | delivered ratio within 10 percent of the weights | weights 1:3 over 10,000 tasks | M-29 |
| A-42 | ssh connect plus 1 round trip plus 30 ms | `run HOST -- true` with no live worker, binary present | B-20 |

## 15. What a green run does not prove

* Durability of `strict` after a power loss: F-07 kills a process, not the power. A claim needs a VM power cut without a guest sync.
* Speed on real tiny hardware: `qemu-user` and resource caps check function and memory, not time.
* Real TCP loss on a WAN: the shaping proxy works above TCP; `tc netem` needs a network namespace with `CAP_NET_ADMIN`.
* Safety of shield `private` against a root user who tries: the tests show that no canary is left behind; they do not show that root cannot read a live process.
* Safety of `sealed` on hosts outside the test: the SNP tests run by hand on one host; no CI runner has SNP.
* The fence on Windows when the worker process is suspended: Windows has no second holder of the fence (file 26).
* Spreading of programs outside the test set: the rules of file 07 are tested on make, cargo, a C build and a configure script.
* The truth of a probe report on a hostile host: a report below `sealed` is a claim.
* Behaviour on kernels, FUSE versions and seccomp profiles outside the E matrix.
* Parity with HyperShell beyond the cases of U-parity.
* A throughput number on another host than the recorded one.
