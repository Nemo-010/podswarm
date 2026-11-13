# 25. Decisions

This file is the log of the decisions of the tree: one short entry for each, grouped by topic. An entry says what is decided, the reason (or the owner's words, marked `Owner:`), the choice that it rejects where one was on the table (`Rejected:`), the file that owns the rule, and the one condition that reopens it. Ids are never reused, and a new entry takes the next free id at the end of the file. File 26 holds the risks and the questions that stay with the owner.

## 1. Product and names
**D-01 Compute access like ssh.** Decision: podswarm is one binary and one protocol that give the compute of any machine the user can reach. It needs no per-tool setup and no cluster software, and it leaves no service behind.  
Owner: "can be used like `ssh` is ... the access is compute itself" (2026-11-12). Home: file 01. Reopen when: the owner narrows the product to a task farm.

**D-02 Three faces on one core.** Decision: `run` runs one command now with the caller's files and terminal, and `x` and `submit` run many commands (the HyperShell face). Queued long work covers services and checkpoints.  
Why: The first statement names one-off, persistent and cluster work, and one core serves all three. Home: file 01. Reopen when: a face needs a protocol rule that the others cannot share.

**D-03 No knowledge of a tool.** Decision: podswarm has no compiler wrapper, no build cache and no rule for any program. A build tool gets fan-out when it uses `podswarm run` as its wrapper, or through spreading.  
Owner: "it will not be a generic yet another sccache or compiler helper" (the first statement). Home: file 01. Reopen when: the owner asks for a feature that is specific to one tool.

**D-04 Session and swarm.** Decision: A session has the home as its authority and keeps nothing durable, and a swarm has a coordinator with a durable store. One binary has four roles (home, worker, coordinator, hub), and both ways share the attempt protocol and the engines.  
Why: One code path for embedded and remote work removes a class of bugs where the two disagree. Home: file 03. Reopen when: one way needs a message that the other cannot carry.

**D-05 No service left behind.** Decision: Nothing that podswarm installs runs as a system service: the holder ends when idle, a far worker ends with its link, and a coordinator is a foreground process that an operator starts. `autostart` is a separate command.  
Why: "No root, no daemon" is a rule of the org. Home: file 03. Reopen when: R-01 is answered against a long-lived coordinator or holder.

**D-06 No built-in agent.** Decision: podswarm has no agent, no prompt handling and no model call. Agents use podswarm through its machine interface.  
Owner: "pluggable and extendable, so that agents can use podswarm themselves" (2026-11-12). Home: file 17. Reopen when: the owner asks for a built-in agent.

**D-07 First usable release.** Decision: The first release ships `podswarm run HOST -- CMD`: one command on one machine that the user can ssh to, with a live view of the directory, the terminal and the exit code. Pools, batches and spreading follow.  
Owner: "one command, remote" is the first usable release (2026-11-12). Home: file 22. Reopen when: the owner reorders the milestones.

**D-08 Names.** Decision: The binary is `podswarm`. The short alias `psw` exists only when the user makes it with `self install-aliases`.  
Why: `psw` collides with small tools in package registries. Home: file 18. Reopen when: R-07 is answered against the alias.

**D-09 The static promise.** Decision: A Linux musl build is one static executable with no `NEEDED` entry. A macOS or Windows build is one file that links only system libraries. The view, spreading and the strong boundaries are Linux features first.  
Owner: "everything must be statically compiled", with C, zig and modern Rust allowed (2026-11-05). Home: file 01. Reopen when: a target of file 21 cannot link as promised.

## 2. Roads, links and identity
**D-10 A road is only a way in.** Decision: A road gives one ordered byte stream to a podswarm worker on the far machine and can start that worker. The kinds are `ssh`, `podssh`, `exec:CMD` (any command whose stdin and stdout reach a worker), `local`, `wss` and later the reverse roads.  
Owner: Remote setup is only a way in: if the user can reach a machine with ssh or any PodUtils road, it works (2026-11-12). Home: file 04. Reopen when: a class of machine appears that no road kind reaches.

**D-11 Bootstrap by copy.** Decision: The home asks for `uname -sm` and sends the binary of its own version through the road to `~/.cache/podswarm/bin/podswarm-<version>-<hash16>`, compressed with a tool that the far machine has: `zstd`, else `gzip`, else raw. The far side checks the hash and renames the file. This is the one use of gzip, and it is the far machine's tool, not a codec of podswarm.  
Owner: "copies its own binary there on first use, runs it while needed, and leaves no service behind" (2026-11-12). Rejected: zstd only (a far machine with no `zstd` gets a raw copy and misses A-23). Home: file 04. Reopen when: A-23 (first run under 5 s at 20 Mbit/s) fails.

**D-12 The system ssh as a subprocess.** Decision: The `ssh` command runs with `-T -e none -o BatchMode=yes` and the user's own configuration, and the first connection with a terminal may prompt once. Each end writes the `PSWROAD` preface first, and each far command has the form `sh -c 'script' WORD...`.  
Why: The user's keys and jump hosts work unchanged, and a start file that prints text cannot corrupt the stream. Home: file 04. Reopen when: a target has no system `ssh` client.

**D-13 The road authenticates, not podswarm.** Decision: A road that authenticates both ends (`ssh`, `podssh`, `exec`, `local`) has no TLS and no podswarm key exchange; a `wss` road uses mutual TLS. At shield `guest` and `sealed` an inner TLS channel ends inside the guest. No road uses a pinned TLS client with no client certificate.  
Why: A second handshake adds cost and no proof. Rejected: a pinned client with no client certificate on `wss` (the server could not map the client to a row). Home: file 16. Reopen when: a road kind authenticates only one end.

**D-14 The holder.** Decision: The first `podswarm` command starts a background process, the home of the session, that serves later commands on a Unix socket (mode 0600, peer uid checked). It ends after `hold_s` (file 04) with no command and no attempt, and `--no-hold` makes the command the home.  
Why: It is the pattern of an ssh control master, and it keeps roads, links and the view index warm with no service. Home: file 04. Reopen when: R-01 is answered against a holder.

**D-15 The far worker leaves nothing.** Decision: A far worker lives while its link is used, then removes its runtime files and exits; `linger_s` (file 04) keeps it longer. Only the binary and the content cache stay, and `podswarm forget HOST` or `--no-trace` removes both.  
Why: The owner's rule is no service left behind. Home: file 04. Reopen when: A-23 shows that cold starts dominate real use.

**D-16 Reattach after a cut.** Decision: After a cut road the far worker keeps running and listens on a private Unix socket, and the home dials again and starts `worker --attach ID`. The socket needs a 32-byte attach secret in its first frame.  
Why: A cut shorter than the silence budget stays invisible, and another process of the same uid can reach the socket but cannot read the worker's memory. Home: file 04 (secret: file 16). Reopen when: A-14 (no re-run after a short cut) fails.

**D-17 Windows follow the round trip.** Decision: `stream_window` is `clamp(2*bdp, 64 KiB, 8 MiB)` and `link_window` is `clamp(4*bdp, 256 KiB, 8 MiB)`, from the measured round trip.  
Why: A small window on a slow link keeps control frames from waiting behind bulk data (A-18). Home: file 04. Reopen when: a link needs a window change that `pod-link` cannot make.

## 3. Attempts and the fence
**D-18 The attempt is the unit.** Decision: A command of `podswarm run` is a task with one attempt, attached I/O, `at_most_once` delivery and `retries = 0`. A queued task uses the same attempt protocol with captured I/O.  
Why: One protocol serves a terminal command and a batch. Home: file 05. Reopen when: an attached command needs a message that a queued task cannot use.

**D-19 Flat shape fields, one owner.** Decision: A shape has flat field names, and file 05 owns each of them. `needs` holds the boundary and the shield, and `confine` has the sub-fields `read`, `write`, `exec`, `connect`, `bind`, `udp` and `unix`.  
Why: One owner for each name stops drift between files. Home: file 05. Reopen when: a field needs a nested form.

**D-20 Frame order.** Decision: Frames to one worker leave in the order in which the authority decided them. A frame that names an attempt of an offer that waits for its commit waits behind that offer.  
Why: A `cancel` must not overtake an `at_most_once` offer. Home: file 05. Reopen when: a message type needs to bypass the order.

**D-21 The fence.** Decision: A worker ends its attempts at `t_ok + silence_s + kill_grace_s` on a monotonic clock, where `t_ok` is the send time of the newest `hb` whose `hback` arrived. Each `hb` is reconciled against the rows of the authority.  
Why: This bound makes a re-offer safe with no consensus. Home: file 05. Reopen when: a target has no clock that counts during suspend.

**D-22 A limit kill is a failure.** Decision: A kill for `mem_exceeded`, `cpu_exceeded` or `disk_full` ends the attempt as `signaled` with that reason. It counts as a failure and uses `retries`.  
Why: The task caused it, so the loss budget must not absorb it. Home: file 05. Reopen when: users need a limit kill that retries free.

**D-23 Control framing and feature names.** Decision: A control message is a `u32` length, a codec byte (`0x00` JSON, `0x01` zstd) and a body, with positional rows for hot messages. A feature name has one form, `name.N` (`io.1`, `view.1`, `zstd.1`, `jobs.1`).  
Why: One form is easy to parse and to read in a trace. Rejected: the `.vN` form beside it. Home: file 05. Reopen when: A-01 is missed because of the JSON cost.

**D-24 Errors name the bound.** Decision: A class bound that is reached answers `busy`. An `err` message carries `limit`, `used`, `scope` and `reason`.  
Why: One TempFail code lets a sender back off and still name the bound. Home: file 05. Reopen when: a bound needs its own error class.

## 4. The view
**D-25 Live view first.** Decision: From the first release a remote process sees the caller's directory through the link: reads come from the caller on demand and writes land on the caller's machine. Sync is the fallback.  
Owner: "both, live view first" (2026-11-12). Home: file 06. Reopen when: A-21 (within 10 percent of a build on the remote machine) fails.

**D-26 Rungs in a fixed order.** Decision: The rungs are `fuse` (root), `fuse-userns`, `trap` (seccomp interception over a local copy) and `sync`. `--view auto` takes `sync` above the round trip `view_sync_rtt_ms` (file 06) when a warm copy exists.  
Why: One pipelined transfer beats many demand round trips on a slow link. Home: file 06. Reopen when: the measured crossover differs from the default of `view_sync_rtt_ms`.

**D-27 The home serves, the worker asks by node id.** Decision: A worker asks for a file by a node id that the home handed out, never by path. A node id is the low 63 bits of BLAKE3 of the workspace id and the path.  
Why: A worker can read only what the home gave it. Home: file 06. Reopen when: a use case needs a request by path.

**D-28 What comes back.** Decision: What git would see comes back to the origin. A directory that git ignores as a whole and that holds no tracked path is native on the anchor, stays there warm for the next run and does not cross the link. A workspace names paths that always come back (`[view] pull = [...]`, `--pull GLOB` for one run), `podswarm pull [HOST] PATH...` fetches a kept path after the run, and the end of a run that kept paths prints one line with their names and size.  
Why: `target/` and `node_modules/` would swamp the link. Rejected: bring every written file back, so a build product appears on the caller's machine by itself (R-16). Home: file 06. Reopen when: A-22 shows a case where an owned directory must cross.

**D-29 Ordered write-back.** Decision: Writes land through one ordered write-back log with atomic renames on the home. Conflicts become copies, and protected paths and large deletes wait for the user.  
Why: A wrong or hostile worker cannot destroy the caller's files silently. Home: file 06. Reopen when: held operations block real runs too often.

**D-30 Export rules.** Decision: The export root is fixed at session start, nothing follows a symlink out of it, credential files read as absent and `.git/config` is served with credentials removed. Only `--allow` or the user's own configuration un-denies a path, never a workspace file.  
Why: A cloned repository must not open the caller's secrets. Home: file 06. Reopen when: a legitimate flow needs a workspace-level allow.

**D-31 The caller's path and clock.** Decision: With a view the working directory is the caller's absolute path in a private mount namespace, and modification times shift by the clock offset measured at session start.  
Why: Absolute paths in build output stay valid, and `make` and `cargo` compare times correctly. Home: file 06. Reopen when: a target cannot make the mount namespace that this needs.

## 5. Spreading
**D-32 Exec-level spreading in user space.** Decision: A seccomp user-notification filter catches each `execve` and `execveat`. A moving exec is taken over with `PTRACE_SEIZE` and a stub, so the pid stays and no root is needed, and the `shim` rung (a `PATH` directory of launchers) serves macOS and hosts with no notification.  
Why: A local exec costs 30 to 130 microseconds more, where full ptrace costs 500 times more for each system call. Home: file 07. Reopen when: the prototype fails on a common kernel or container setup.

**D-33 What crosses an exec.** Decision: Argv, environment, working directory, the view, stdin, stdout and stderr cross. A make or cargo jobserver is replaced by a fresh one on the member, and a process with any other open descriptor stays local.  
Why: A moved process with a descriptor that podswarm cannot carry would change meaning. Home: file 07. Reopen when: a common tool needs another descriptor kind to cross.

**D-34 Which exec moves.** Decision: An exec moves when its expected finish time on a member is under 0.8 of the local time, by an ordered rule list and then a table learned per program and option names. The member must have the same CPU architecture and operating system, and binaries come from the caller through the view.  
Why: Spreading loses for short processes, and another architecture cannot run the same binary. Home: file 07. Reopen when: A-24 (5 times faster on 8 machines) fails on wide builds.

**D-35 Causal close-to-open.** Decision: The writes of a moved process reach the anchor (D-123) before anything of that process that others can see (output bytes, exit status, a signal, an fsync, a lock release). A spread session forwards locks to the anchor. For a slow link at the caller the user runs `podswarm run HOST --spread -- CMD`, so the anchor is HOST.  
Why: "The compiler exited, so foo.o exists" holds at the price of one round trip for each exit. Rejected: an election of the file authority among the members. Home: file 07. Reopen when: the round trip per exit dominates real builds.

**D-36 Pooled core count.** Decision: A query of the CPU count inside a spread session answers with the pooled core count. `--spread` on `run` and `x`, the shape field `spread` (default false) or a pool default turns spreading on.  
Why: `make -j$(nproc)` then fills the pool with no flag. Home: file 07. Reopen when: a program breaks on a count above the local cores.

**D-37 The ladder to a single system image.** Decision: Step 1 is exec-level spreading. Step 2 moves a running process: a checkpoint that the program writes, then CRIU in a user namespace that podswarm owns, then guest migration. Step 3 places work where memory is free, pages a migrated process from its old machine and offers an opt-in far heap.  
Owner: "a true single system image is a stated goal" on this ladder; one process lives on one machine at a time (2026-11-12). Shared memory that a program does not know about is a non-goal. Home: file 07. Reopen when: a step 2 rung is proven in a prototype, or transparent shared memory proves affordable.

## 6. Pool and placement
**D-38 The pool file.** Decision: `pool.toml` in the user's configuration directory lists the machines: name, road, tags, `trust`, `slots` and cell labels. Nothing is read from `~/.ssh/config` unless the user runs `pool import-ssh`, which writes entries with `auto = false`.  
Why: No machine gets work that the user did not list. Home: file 08. Reopen when: users ask for ssh-config discovery by default.

**D-39 Placement by estimated finish time.** Decision: Placement picks the machine with the lowest estimated finish time among those that meet the needs, the shield and the residency rule. A command whose learned run time is under `local_under_ms` (file 08) stays on the caller's machine.  
Why: A short command loses its time to the round trip. Home: file 08. Reopen when: an unknown program placed as fully parallel misplaces common builds.

**D-40 The learned table stays with the user.** Decision: The learned table keeps run time, CPU time and memory per program, keyed by workspace, program and first argument, and never leaves the caller, and a start calibration gives two speed scores. A coordinator uses its class histograms instead.  
Why: How long a user's commands run is private, and it differs per machine. Home: file 08. Reopen when: placement at scale needs a shared table.

**D-41 Named resources are counts.** Decision: Named resources are declared counts (`gpu=2`), at most 16 names, with no device binding. `caps` is at most 3,072 bytes, so `hello` stays under the 4,096-byte limit before `ready`.  
Why: podswarm counts, and the host binds. Home: file 08. Reopen when: users need device binding.

**D-42 Cells.** Decision: A cell is a `[cell.NAME]` table of `pool.toml`. A session cell has no road and the home is its authority, and a swarm cell has a `wss` road to a coordinator; `ready` carries `cell{name, region, juris}`, and the codes `no_cell` (Policy) and `wrong_cell` (Usage) report a missing or wrong cell.  
Owner: "regions and placement": independent pools by region or jurisdiction, with rules that keep data and runs in one (2026-11-12). Home: file 08. Reopen when: a cell needs a label that the two sides cannot check.

**D-43 Residency can only restrict.** Decision: A residency rule may live in a workspace `.podswarm.toml` (`allow_cell`, `deny_cell`, `allow_region`, `allow_juris`, `shield_min`, `boundary_min`). A rule never names a road, a key or a cell definition.  
Why: A cloned repository can tighten but never widen where data may go. Home: file 08. Reopen when: a team needs a workspace rule that widens.

## 7. The queue and delivery
**D-44 The delivery contract.** Decision: Queued work runs at least once and is recorded at most once, and the first valid result wins. `at_most_once` is opt-in and needs `retries = 0`.  
Why: Exactly once cannot be built with a worker that can die. Home: file 09. Reopen when: a store that the worker can commit with its result exists.

**D-45 Terminal states are final.** Decision: The states are `held`, `waiting`, `ready`, `leased` and `running`; the terminal states are `succeeded`, `failed`, `cancelled` and `lost`. Only `retry` leaves a terminal state, and `deadline_unix` acts only on a task that did not start.  
Why: A decided answer must not move after the caller saw it. Home: file 09. Reopen when: a use case needs a task to leave a terminal state by itself.

**D-46 One open row.** Decision: An open row is `offered`, `running` or `stopping`. The offer (T4) is the only transition that makes a row, and its guard (no open row) keeps at most one.  
Why: One guard in one place is easier to prove than a check in each caller. Home: file 09. Reopen when: an extension needs a second open row for every task.

**D-47 Two budgets and a cap.** Decision: `retries` counts failures and `max_lost` counts losses; a non-success result of a `stopping` row spends neither, and at most 1,000 attempts return a task to `waiting` or `ready` (reason `attempt_cap`). The retry delay is `min(cap, base * 2^(n-1))` with a factor in [0.8, 1.2].  
Why: A host crash is not the task's fault, and the cap bounds a crash loop. Home: file 09. Reopen when: a legitimate workload passes the cap.

**D-48 The late result.** Decision: A result for a terminal task is stored with `accepted = 0`, a late success sets `late_ok`, and no result changes a decided state. A result counts only when it is held: the same generation, the same worker number, the current link, and the row did not end on a report of that worker.  
Why: The delivery contract must not move after an answer. Home: file 09. Reopen when: the owner wants a late success to win over `failed` or `lost`.

**D-49 `at_most_once` placement.** Decision: A queued `at_most_once` task goes only to a worker whose containment rung is not `session` and that is not `suspect`; `workers approve` clears `suspect`. An attached `podswarm run` command is exempt because its caller watches it.  
Why: A rung that cannot find every process cannot promise no duplicate. Home: file 09. Reopen when: macOS workers need queued `at_most_once` tasks.

**D-50 Groups and arrays, no DAG.** Decision: The active group is the lowest group with a task not `succeeded`, and `--halt-on-fail N|P%` drains by default. A pinned task of `podswarm each` whose worker is gone is cancelled with reason `worker_gone`.  
Why: Stages and sweeps cover the cases users show, and a DAG needs a planner. Home: file 09. Reopen when: users show that groups cannot express a common workflow.

## 8. The queue engine
**D-51 Pulls report, offers answer.** Decision: A `pull` reports free capacity and the unstarted count, and a link has one standing pull state. The authority may offer at any time, up to the capacity of the newest `pull` minus what it offered since, and an offer has no `more` field.  
Why: No request and answer pair is needed. Rejected: a `more: 1` flag on each offer but the last of an answer. Home: file 10 (wire: file 05). Reopen when: a worker needs to know where an answer ends.

**D-52 Deep local queues.** Decision: The target of unstarted tasks is `u = slots_c * floor(T_q / d)` with `T_q = clamp(4R + 0.05 s, 1 s, 10 s)`, and at least one queued task per slot when the round trip is over 2 percent of `d`.  
Why: A deep local queue hides the round trip, and tail reclaim restores balance at the end. Rejected: a depth of zero for long tasks (a slot idles for one round trip after each task). Home: file 10. Reopen when: A-08 (95 percent for 10 ms tasks at 100 ms) fails.

**D-53 Tail reclaim, not work stealing.** Decision: A parked worker makes the authority take back half of the unstarted tasks of a holder (`cancel{unstarted}`), newest first.  
Why: Only the authority sees all queues, and stealing needs links between workers. Home: file 10. Reopen when: workers get direct links.

**D-54 Classes and fairness.** Decision: A class is the hash of the rounded needs (cores to 250 millicores, memory to 64 MiB, disk to 1,024 MiB) and the priority. Priority is strict between levels, runs of one level share by deficit round robin, and `max_running` bounds a run.  
Why: A class makes matching one bit test for each worker. Home: file 10. Reopen when: the class count makes matching slow.

**D-55 Reservation and lifetime.** Decision: The head task of a class that `reserve_after_s` (file 10) has skipped reserves the fitting worker with the most free capacity. A worker with a lifetime drains `drain_margin_s` before its end, from `--time-limit`, `SLURM_JOB_END_TIME` or `PBS_WALLTIME`.  
Why: Large tasks must not starve behind small ones, and a batch-launched worker ends by the clock of its scheduler. Home: file 10. Reopen when: reservation idles capacity in a test.

**D-56 One scheduler actor.** Decision: One scheduler actor owns all scheduling state, and the scheduler never touches JSON. The store queue delays `ack` and `offer`, never `hback`, when its oldest command is older than 250 ms or it holds over 16,384 events.  
Why: One owner needs no lock, and the delay turns overload into backpressure. Home: file 10. Reopen when: A-01 shows the actor as the bottleneck.

## 9. Storage
**D-57 SQLite, one writer.** Decision: The coordinator store is SQLite in WAL mode, bundled, with one writer thread, no consensus and no high availability. A failed coordinator is restored from a backup.  
Why: One writer meets the targets and leaves no consensus to prove. Home: file 11. Reopen when: B-01 stays under 1,500 tasks per second, or the static build of SQLite fails on a target (then a `Store` implementation such as redb takes over).

**D-58 Natural group commit.** Decision: The writer takes what queued during the last commit, at most 8,192 events or 4 MiB, in one transaction with no timer. Durability is `strict`, `batched` or `memory`: `podswarm coord` takes `strict` (default) or `batched`, `x --db` uses `batched`, and `x` uses `memory`.  
Why: The batch grows with the load and adds no latency floor. Home: file 11. Reopen when: a timer window measures faster on slow disks.

**D-59 Offer order and the hot path.** Decision: An `at_least_once` offer may leave before its lease commit, and an `at_most_once` offer waits for it, with a spawn record that the worker syncs before it starts. The hot path writes one `attempts` insert and one `tasks` update at the end, and nothing at offer or start.  
Why: Two writes for each task make A-01 reachable. Home: file 11. Reopen when: a crash test shows a duplicate that this order allows.

**D-60 A divergence stops the coordinator.** Decision: The attempt record is written when the attempt ends, and a late result of an attempt that ended as `lost` updates that record once. A guarded update that changes no row aborts the batch, and the coordinator exits 70.  
Why: A silent divergence between memory and store is worse than a stop. Home: file 11. Reopen when: a legitimate path changes no row.

**D-61 Generation after a restore.** Decision: A restore makes a new generation (`meta.gen`): the next task, run and job ids rise by 2^32, each non-terminal `at_most_once` task becomes `lost` with reason `generation`, and a task whose input blob is missing fails with `spawn_failed`, reason `input`. A raw file copy is not supported.  
Why: A restored store has rows that workers may still hold under old ids. Home: file 11. Reopen when: an online replica of the store exists.

**D-62 Retention and the disk guard.** Decision: Tasks, inline output, events and blobs have a retention period each, and a blob counts from its last use (defaults: file 11). The disk guard `max_db_bytes` refuses a submit with `busy`.  
Why: A store that fills its disk stops all work. Home: file 11. Reopen when: a user needs longer history without cost.

## 10. Execution
**D-63 Spawner and keeper.** Decision: The worker forks a single-threaded spawner before the runtime starts, and the spawner forks one keeper for each attempt; the keeper is the subreaper of that attempt. A dead spawner is replaced by a fork that execs the worker's own binary with an internal flag.  
Why: The trees stay killable when the worker dies, and a threaded process forks only to exec. Home: file 12. Reopen when: a target cannot run this process model.

**D-64 Containment rungs.** Decision: The rungs are `cgroup`, `pidns`, `subreaper`, `reaper`, `job` and `session`. On Linux the worker takes the first that works, in that order, and reports it. Windows has a Job Object and no second holder of the fence.  
Why: Each rung says what it can kill and what escapes. Home: file 12. Reopen when: a rung escapes in a test.

**D-65 Limit modes.** Decision: Each limit has a mode `enforced`, `polled`, `reported` or `none`, and `limits_required` matches `enforced` or `polled`. Memory is polled once a second where no cgroup or job exists.  
Why: A limit that a host cannot enforce must say so. Home: file 12. Reopen when: `pod-job` adds the `polled` mode (file 21).

**D-66 Output never blocks a task.** Decision: The worker always drains both pipes, and the result carries a head and a tail of each stream (`capture_max`, file 05). A live `out` stream has its own credit, and a spill file takes up to 64 MiB for each attempt except an attached one.  
Why: A slow reader blocks only at a full spill file. Home: file 12. Reopen when: live logs need replay beyond the spill file.

**D-67 Environment.** Decision: A queued task on a remote worker gets an allowlist of environment names. A `run` passes the caller's environment minus the variable deny list of file 13 section 5 (`PODSWARM_*`, `*_TOKEN`, `*_SECRET`, `SSH_AUTH_SOCK` and more), with `PATH`, `HOME` and `TMPDIR` set for the worker.  
Why: A `run` is the user's own command, and a queued task may serve other submitters. Home: file 12 (deny list: file 13 section 5). Reopen when: a common tool needs a variable on the deny list.

**D-68 Task directory and journal.** Decision: `TASK_DIR` is `<root>/<task_id>.<attempt_no>` with mode 0700, on tmpfs when the task stages nothing and needs under 64 MiB. The journal is append-only and is synced only for the spawn record of an `at_most_once` attempt.  
Why: An fsync is costly on small disks, and only that record needs it. Home: file 12. Reopen when: a crash test shows a lost record.

**D-69 Automatic argv.** Decision: A `shell` command with no shell metacharacter after expansion runs with no shell, and the shape field `shell_always` (default false) turns that off.  
Why: It saves a fork and avoids differences between shells. Home: file 12. Reopen when: a parity case differs.

## 11. Trust: boundary and shield
**D-70 Two axes.** Decision: `boundary` (`none < confined < sandbox < vm`) protects the host from the task, and `shield` (`none < private < guest < sealed`) protects the task and the caller from the host. A request is never met by a weaker level, and `guest` and `sealed` also give boundary `vm`. The fields are `needs.boundary` and `needs.shield`.  
Owner: "three levels, each with an honest statement of what it stops" (2026-11-12). Rejected: one field `needs.trust` with a "host trust level" (it mixed the two directions of protection). Home: file 13. Reopen when: a case needs a third axis.

**D-71 The default shield.** Decision: A pool entry has `trust = own | shared`. `own` gives shield `none`, `shared` gives `private`, and a machine with no key is `shared`, so the default shield of every remote machine is `private`.  
Why: A rented host may have other root users, and `private` costs a memory-backed work area. Home: file 13. Reopen when: R-10 is answered against the default.

**D-72 Refuse by name.** Decision: A machine that cannot give the asked shield refuses with `shield_unavailable` (class Policy), and a remote machine that is not Linux gives only `none`. A host's report of `private` or `guest` is a claim, and `sealed` is proven by attestation.  
Why: A silent downgrade breaks the promise that the user asked for. Home: file 13. Reopen when: a probe is found that proves more than a claim.

**D-73 What `private` stops.** Decision: `private` is a memory-backed work area that does not reach swap, a warm cache kept only as ciphertext under a key that the caller holds, no long-lived key on the host and removal at exit. A root user who tries can still read the process.  
Why: The statement says what it stops (leftovers) and what it does not (a live attacker). Home: file 13. Reopen when: the swap test shows that the area reaches swap.

**D-74 `guest` and `sealed`.** Decision: `guest` runs the attempt in a podvm VM guest, so host tools see no file and no process of it, and `sealed` is a confidential VM (SEV-SNP first, TDX later) that the caller attests before it sends a file or a key. The first release has `private`, and `guest` and `sealed` follow.  
Why: Each level costs more and needs more of the host. Home: file 13. Reopen when: podvm cannot give a library call for the guest plan.

**D-75 Credential rules at every level.** Decision: At every level, `none` included, agent forwarding is off and no flag turns it on, credential files are not served by the view, and secret-looking variables are not passed.  
Why: A rule that depends on the level fails at the level that the user forgot. Home: file 13. Reopen when: a user needs agent forwarding where no other route exists.

**D-76 The caller's own machine.** Decision: The caller's own machine meets every shield level for placement and never runs a guest for the shield.  
Why: The host is the caller. Home: file 13. Reopen when: the caller's machine is shared with other users.

## 12. Network
**D-77 The network is a policy.** Decision: The network of a run is a policy string (`host`, `pool`, `exit:NAME`, `home`, `none`) with `;KEY=VALUE` modifiers, served by podnet, and the default is `pool`. A workspace file cannot set `home`, `exit:` or a lower `require`.  
Owner: "by default network should be multi wan load balanced + aggregated"; an exit node is chosen on demand (2026-11-12). Home: file 14. Reopen when: podnet cannot serve a pooled default.

**D-78 Steering with no root.** Decision: A held process tree is steered through the rungs `guest`, `netns`, `notify`, `deny` and `env` (a door on a loopback port). The first release refuses `none`, `exit:` and `home` with reason `not_built`.  
Why: Each rung says what it enforces, and the report names the rung. Home: file 14. Reopen when: a rung leaks a flow in a test.

**D-79 Member check by shield.** Decision: Runs at shield `none` and `private` may use any member of a pooled policy; `guest` and `sealed` use only the caller and `trust = own` members. The authority may open a `net` stream toward a member.  
Why: Traffic of a shielded run must not leave through a machine that the user does not own. Home: file 14. Reopen when: a member needs a pool `trust` value between `own` and `shared`.

## 13. Data and checkpoints
**D-80 One hash.** Decision: The content hash is BLAKE3, and a content id is `b3:<64 hex>` for blobs, shapes, the cache and checkpoints. SHA-256 stays only for outside checks (a URL input's `sha256`, `SHA256SUMS`), and the field name is `id`.  
Why: One hash is fast on small CPUs and leaves one id form. Rejected: `sha256:` ids beside `b3:` ids. Home: file 15. Reopen when: a compliance rule demands SHA-256 for blobs.

**D-81 One compressor.** Decision: The compressor is zstd (codec `0x01`, feature `zstd.1`), and there is no gzip.  
Why: One library gives a better ratio and speed. Rejected: gzip as a second codec; the bootstrap copy may use the far machine's `gzip` tool (D-11). Home: file 05. Reopen when: the bundled C of zstd fails a static build on a target.

**D-82 The content store.** Decision: The layout is `<root>/blobs/<2 hex>/<62 hex>` with plain blobs, whole-blob dedupe by owner, access by owner and not by hash, and one error `not_found` for a blob that is absent or not yours. A blob under 24 hours old is never swept.  
Why: A hash must not be a capability, and the guard protects uncommitted checkpoint blobs. Home: file 15. Reopen when: a shared store across owners is needed.

**D-83 Staging and fan-out.** Decision: A cached blob reaches a task directory by reflink, else by hard link on boundary `none` and by copy on `confined`; a fan-out over `fanout_warn` prints an estimate, and over `fanout_max` it refuses and names URL inputs (both: file 15). A worker keeps a map from the SHA-256 of a URL input to the id of the cached blob.  
Why: Cost must show before a submit sends many gigabytes to each of many workers. Home: file 15. Reopen when: users need a larger fan-out without a warning.

**D-84 Outputs.** Decision: Outputs are globs under the task directory, and the authority checks each reported path with the path rule. A successful exit with a failed output upload is a failure (`output_failed`), and `capture_blob` (default false) stores the whole stream as a blob.  
Why: A result without its outputs is not a success. Home: file 15. Reopen when: a task needs success with partial outputs.

**D-85 Checkpoints.** Decision: A checkpoint is a manifest blob plus file blobs in the content store, taken by an exit code, by `podswarm checkpoint save`, or by a signal and then a grace period.  
Owner: checkpoints and resume: a long run saves its state in the content store and resumes on another machine (2026-11-12). Home: file 15. Reopen when: a program needs a checkpoint that this form cannot hold.

**D-86 Restore and commit rules.** Decision: Restore runs before a start with `TASK_RESUMED=1` and `TASK_CHECKPOINT_DIR`. A `ckpt_commit` counts only from the live attempt with a newer sequence number, a drain, a lifetime end or a preemption notice asks for a checkpoint first, and a damaged checkpoint falls back to the next older one.  
Why: A stale or late commit must not replace newer state. Home: file 15. Reopen when: a commit path shows a lost checkpoint in a fault test.

**D-87 Encrypted checkpoints.** Decision: An encrypted checkpoint uses keyed BLAKE3 ids (`b3k:`), and `encrypt` and `sink` exclude each other. A failed sink does not fail the checkpoint, and restore uses the blob-store copy.  
Why: The authority cannot parse an encrypted manifest, and a sink is only a copy. Home: file 15. Reopen when: a sink must be the only copy.

**D-88 Checkpoints cross cells.** Decision: `checkpoint export` writes a manifest and its blobs to a directory, and `checkpoint import` reads them in another cell, where the destination passes the residency rule first.  
Why: A move across cells needs a file form that a rule can check. Home: file 15. Reopen when: a cell pair needs a direct transfer.

## 14. Security
**D-89 Identity in the handshake.** Decision: A worker and a submitter present an Ed25519 key as a self-signed certificate in the TLS 1.3 handshake. The dialer checks the coordinator key against a pin set; the key type and the pin form are those of D-129.  
Why: Mutual TLS already proves the key, so no in-band exchange is needed. Home: file 16. Reopen when: `pod-tls` stops reporting the key of the peer (`pod_tls::peer::peer_key`; file 21).

**D-90 Invites and enrolment.** Decision: An invite token (`psw1.` plus an Ed25519 verifier) carries rules for tags, cores, slots, boundary, `approve`, `worker_ttl` and `ephemeral`. A key under another invite is refused and every failure answers `unauthorized`; `approve` is off by default, and `worker_ttl` and `ephemeral` end in `revoked`.  
Why: Approval by default blocks the bootstrap of 100 hosts (A-13). Home: file 16. Reopen when: a stolen-token case shows that approval must be on by default.

**D-91 Submitters live in the store.** Decision: The store table `submitters` is the truth. `podswarm submitter add|ls|rm` edits it through the local socket of the coordinator, and there is no `submitters.toml`.  
Why: One source cannot disagree with itself. Home: file 16. Reopen when: users need a file form for review.

**D-92 Organisation statements.** Decision: An organisation key signs a member statement in the `{doc, key, sig}` form of at most 2,048 bytes. `hello.stmt` carries it, trust entries live in the store, and `org revoke` raises a per-member serial floor.  
Owner: "an identity that is valid across them" (2026-11-12). Home: file 16. Reopen when: cells need an identity that a statement cannot give.

**D-93 Configuration and the path rule.** Decision: Configuration comes from the user and system files, and a workspace file may set `[defaults]`, `[residency]` and `[view]` only; `[view]` can only add globs and lower the five view thresholds (file 06). One path rule covers `files[].path`, outputs, `cwd`, unpack entries and checkpoint entries.  
Why: A cloned repository must not widen a boundary or a policy. Home: file 16. Reopen when: a team needs a shared policy file in the repository.

**D-94 Signed releases.** Decision: `SHA256SUMS` is signed with an offline Ed25519 key (label `podswarm-release/1`), the binary embeds a primary and a backup public key, and `self fetch` and bootstrap verify the signature.  
Why: The binary runs on other people's machines. Home: file 16. Reopen when: a key is lost or leaked.

**D-95 The worker policy.** Decision: A coordinator can start code on every worker, so `worker.toml` bounds it: boundaries, shell, cores, memory, environment names, `net_allow` and submitters.  
Why: A stolen coordinator key must not give unlimited reach. Home: file 16. Reopen when: a fleet needs a policy that a file cannot express.

## 15. Extending
**D-96 One document for each result.** Decision: Each verb with `--json` writes one document with a `schema` field. `run --json` forces captured I/O so that stdout carries the document, and an error document has a `retry` class (`no`, `fix`, `backoff`, `wait`).  
Why: An agent reads one result and knows what to do. Home: file 17. Reopen when: an agent needs a streaming form.

**D-97 The agent face.** Decision: `podswarm mcp` is a stdio MCP server with a capability profile, and `podswarm skill` prints the text that an agent reads once.  
Why: Agents use podswarm through a stable interface, and podswarm carries no agent. Home: file 17. Reopen when: a profile cannot express a needed limit.

**D-98 Run identity.** Decision: A worker asks the authority for an ES256 JWT for an attempt with `id_req` and `id_rep`, and a run can show it to an outside service.  
Why: A run needs an identity that an outside service can check. Home: file 17. Reopen when: a target service accepts only another algorithm.

**D-99 Hooks and webhooks.** Decision: Hooks run a command on an event and drop the oldest event above 256 queued, and webhooks are signed JWTs (`psw-hook+jwt`) with retries and the verb `coord resend`. An external subcommand `podswarm-NAME` adds a verb. `coord --scale-hook` is the hook `scale.tick`; podswarm has no autoscaler of its own.  
Why: Integrators watch runs with no polling. Home: file 17. Reopen when: a hook needs a delivery guarantee.

**D-100 Plugins and seams.** Decision: Three plugin kinds speak JSON lines over stdio: the `exec:` road, a checkpoint sink and an admission policy. A placement policy is not a kind. Each seam (`Store`, `Executor`, `Road`, `View`) is a trait with a conformance suite.  
Why: A small set of stable seams costs less than a plugin API for every internal. Home: file 17. Reopen when: a user needs a placement plugin.

**D-101 Speculation is off.** Decision: Speculation is off by default, including for `x`, and needs `--speculate`. It adds a row T4s and relaxes the single open row only for those tasks.  
Why: A shell template often has side effects that a second copy repeats. Home: file 24. Reopen when: users ask for speculation as the default.

**D-102 The hub and the sub-coordinator.** Decision: A hub forwards bytes, and TLS stays end to end. A sub-coordinator joins an upstream coordinator as one worker, with depth one.  
Why: The hub must not see data, and the fence of a chain needs a nested proof that no test covers. Home: file 24. Reopen when: a test covers nested fences.

**D-103 Extensions behind feature names.** Decision: Jobs (`overlap` is `skip` or `allow`), estimate backfill, signed shapes, secrets, replication and sampling, the podvm boundaries and the audit hash chain have wire feature names and a section in file 24. A reserved field is refused with `unsupported` until its feature is negotiated.  
Why: The core stays small. Home: file 24. Reopen when: a milestone moves one of them into the core.

## 16. The command line
**D-104 `run` exits like ssh.** Decision: `podswarm run` exits with the exit code of the command (128 plus the signal number for a signal), 124 on a task timeout, 126 or 127 when the program cannot run or is not found. A failure of podswarm itself exits 255 and prints its class, and `--json` gives both. `run` gets a pty only when stdin and stdout are both terminals. `x`, `submit --wait` and `wait` exit 0 when each task succeeded, 1 when one did not, 124 when the wait ends first (`--wait-timeout` of `wait` and `submit --wait`, `--run-timeout` of `x`) and 130 on an interrupt (file 18). A long flag has one meaning: `--timeout` exists only on `x` and `join`, as the HyperShell alias of `--idle-exit`.  
Why: A script that wraps a command needs its code. Rejected: exit 0 or 1 for `run`, as for a batch. Home: file 18. Reopen when: R-08 is answered against exit 1.

**D-105 A short verb list.** Decision: File 18 owns the verb list and keeps it short. File 18, section 3, holds the list.  
Why: The verbs are the public surface, and each one has a cost. Home: file 18. Reopen when: a feature has no home in the verbs.

**D-106 HyperShell's option split.** Decision: `-t` is the template on `x` and a tag on other verbs, and the first positional of `x` is FILE when it names an existing regular file with no white space and no token, else TEMPLATE. `-N` is the slot count and defaults to the core count.  
Why: A HyperShell one-liner must run unchanged (A-17). Home: file 18. Reopen when: R-09 is answered against the default of `-N`.

**D-107 Templates have no eval.** Decision: A template has a fixed token grammar, and the submitter expands it before queueing, so a bad token exits 64. `{.}` is always the directory name, and `--exit-status` is dropped.  
Why: A template that runs code is an injection path. Home: file 18. Reopen when: the parity tests find a HyperShell example that this breaks.

**D-108 Resume and the coordinator address.** Decision: Resume uses `--db FILE --resume` or `--joblog FILE --resume` with a stable task key. `--coordinator ADDR` or `PODSWARM_COORDINATOR` sends a verb to a coordinator; file 18, section 2.1, gives the order of the sources.  
Why: An environment variable must not change where a batch runs. Home: file 18. Reopen when: users need a default coordinator for `x`.

## 17. Crates and the org
**D-109 Repository, crates and the pin.** Decision: podswarm has its own repository `PodUtils/podswarm`, crates named `podswarm-*`, and one git tag of podcrates that only file 21 names.  
Why: It follows the delivery rule of the org. Home: file 21. Reopen when: R-02 is answered against the repository.

**D-110 No compatibility promise.** Decision: The wire has a protocol number and feature names, and a name, a format or an API can change in any version.  
Owner: "no backwards compat" (2026-11-05). Home: file 02. Reopen when: the owner asks for a compatibility window.

**D-111 Generic mechanisms go back.** Decision: A mechanism that other projects can use becomes a `pod-*` crate in podcrates (candidates `pod-fuse`, `pod-view`, `pod-cas`, `pod-proc`), and each ask has a fallback inside the podswarm repository.  
Why: podswarm cannot depend on the time of another project. Home: file 21. Reopen when: R-03 is answered against the crate names.

**D-112 Listener rule.** Decision: A session listens on no TCP port unless the user asks with `x --listen` or `x --launcher` (HyperShell parity, from M4), and a coordinator listens only with `--listen`. A coordinator that cannot listen dials out to a hub. No hosted relay is a default.  
Why: The listener clause belongs to the asks of one tracker, so podswarm keeps it as a default and not as a rule. Home: file 02. Reopen when: R-04 is answered against a TCP listener.

**D-113 Leave podssh alone.** Decision: podswarm never copies podssh code. It runs `podssh` as a road and leaves `podssh each`, `run` and `job` as they are.  
Why: One owner for each tool avoids two tools that drift. Home: file 02. Reopen when: R-12 is answered in favour of taking over `each`.

**D-114 License and limits.** Decision: The license is 0BSD. C is allowed (bundled SQLite and zstd) under the static rule; a source file has at most 500 lines, and betas go out on GitHub, not on crates.io.  
Why: These are rules of the org. Home: file 02. Reopen when: R-05 finds a licence conflict.

**D-115 Tests run the real code.** Decision: Fault and model tests run the real transition code and the real stores, not a copy.  
Why: A model that is not the code proves nothing about the code. Home: file 23. Reopen when: a test needs a mock that the real code cannot take.

## 18. Other decisions
**D-116 No fan-in layer.** Decision: Workers connect to the authority with no process that merges their messages.  
Why: One authority meets the targets of file 23 up to 10,000 workers. Rejected: a fan-in layer between workers and coordinator. Home: file 03. Reopen when: a swarm needs more than 10,000 workers, a benchmark shows connection handling above half of the coordinator CPU, or the hard descriptor limit is below the worker count.

**D-117 A moved process is a member attempt.** Decision: A moved process is an attempt of the member, keyed by `proc`, on an `exec` stream that either side may open (header `sess`, `proc`, `role`, `rx`, `tx`); the authority relays it, and the exit travels on that stream.  
Why: The attempt protocol already carries I/O, signals and the exit. Rejected: a second protocol for moved processes. Home: file 07 (wire: file 05). Reopen when: a moved process needs a message that an attempt cannot carry.

**D-118 View operations for spreading.** Decision: The write-back log has an `append` operation, and in a spread session a member answers each `inval` with the epoch that it applied.  
Why: Appends from several members must not overwrite each other, and the anchor must know when a member sees a write. Rejected: whole-file writes for appends. Home: file 06. Reopen when: a common tool needs another operation to cross.

**D-119 One multicall binary unwinds.** Decision: The release profile has `panic = "unwind"`. A panic ends one link session, a panic that reaches `main` exits 70, and the spawner and each keeper abort on panic.  
Why: One binary holds every role, and a coordinator must not end with one session; the spawner and the keeper run between `fork` and `exec`. Rejected: `panic = "abort"` for the whole binary. Home: file 21. Reopen when: unwind costs a target of file 23.

**D-120 The trap grows `pod-hold`.** Decision: The seccomp trap of the view, of spreading and of the network hold is a growth of `pod-hold`, and the ptrace exec takeover is a module of `pod-proc`. There is no crate `pod-trap`.  
Why: `pod-hold` already has the filter, the listener, the memory access and the replies. Rejected: a new crate `pod-trap`. Home: file 21. Reopen when: podcrates refuses the growth of `pod-hold`.

**D-121 Release tags.** Decision: The release of milestone MN is `v0.N.0-beta.1`. M0 is `v0.1.0-alpha.1`, and M1, the first usable release, is `v0.1.0-beta.1`.  
Why: The tag says the milestone, and the first usable release is the first beta. Home: file 22. Reopen when: the owner asks for another scheme.

**D-122 Reconnect jitter.** Decision: The setting that spreads the reconnects of workers after a restart of the authority is `reconnect_jitter_ms`.  
Why: The word "spread" names exec-level spreading. Rejected: the name `spread_ms`. Home: file 10. Reopen when: spreading no longer uses the word "spread".

**D-123 Origin and anchor.** Decision: The origin is the caller's machine: it is the truth of the workspace and serves the lower layer of the view. The anchor is the machine that runs the root process of the command: it holds the upper layer and is the authority for files that members write. With `podswarm run -- CMD` and `--spread` the anchor is the caller's machine; with `podswarm run HOST -- CMD` it is HOST. The word "hub" means only the relay of file 24.  
Why: Two roles of files need two words, and "hub" already names the relay. Rejected: "hub" or "home" for the file authority. Home: file 06. Reopen when: a session needs a third file role.

**D-124 One seccomp listener.** Decision: The keeper is the exec supervisor. Spreading does not run beside the view rung `trap` or the network hold by notification: a member of a spread session uses a FUSE rung or `sync`, and the network hold by namespace or by variables.  
Why: The kernel takes one seccomp listener for each filter chain. Rejected: two listeners in one chain. Home: file 07. Reopen when: one combined filter for exec, view and network exists (file 07, later).

**D-125 `pull.seen`.** Decision: The message `pull` carries `seen`, the count of `offer` messages that the worker received on this link when it sent the `pull`. The authority may offer up to the capacity of the newest `pull` minus the tasks of each offer that it sent after offer number `seen`.  
Why: An offer in flight when the worker wrote the `pull` is not in its free count, so without `seen` the authority offers one slot two times. Rejected: credit increments (a lost or repeated increment after a reattach drifts, and an absolute state heals). Home: file 10 (wire: file 05). Reopen when: a worker needs to report capacity per class.

**D-126 The data key of a run in a swarm.** Decision: The data key of a run with `checkpoint.encrypt = "run"` is one symmetric key for the run, and the ids of its objects are keyed, so equal content dedupes across the checkpoints of the run. The key stays with the submitter. A worker that starts an attempt of such a run, to write or to restore a checkpoint, sends `ckpt_key_req`; a connected home of the submitter answers `ckpt_key`, sealed to the link key of the worker, after it checks the shield proof that the run needs. With `--key-escrow` the coordinator holds the key in its secret store (`secrets.1`) and answers. Until an answer comes, the task is `held` with the reason `needs_key`. So an encrypted run in a swarm needs a connected home at each start of an attempt, or escrow.  
Why: A coordinator on a shared host must not read each checkpoint, and escrow is a choice of the submitter. Rejected: the coordinator always holds the key (a coordinator on a shared host then reads each checkpoint); one key for each checkpoint (no dedupe across the checkpoints of a run). Home: file 15 (escrow: file 16). Reopen when: users need an encrypted run with no home connected and no escrow.

**D-127 `auto` and a shared file system.** Decision: `--view auto` makes no view on a worker that is the caller's machine, and on a worker that has the caller's directory itself at the same path: the directory is on a network file system (NFS, SMB, Lustre, GPFS, CephFS, BeeGFS), the mount source and the path inside the mount are equal on both machines, a sample of up to 8 entries has equal size and modification time, and one small file has an equal BLAKE3 id. The attempt then runs in that directory. `--view fuse` (or another rung) forces a view. From M2.  
Why: On a cluster with a shared home, a HyperShell one-liner keeps its speed and its meaning. Rejected: always a view (slower than the mount that is there); a flag (a setup for each cluster). Home: file 06. Reopen when: a shared file system passes the sample check and serves a different tree.

**D-128 One row decides the task.** Decision: The core has no sibling rows: a task has at most one open row (I4), so a task fails, is lost or succeeds on the result of that row only. Sibling rows exist only with speculation, and file 24 gives their rules: the task is `running` while a row runs and `leased` while a row is only offered, and a failure of any row of the set is the outcome when no row succeeds.  
Why: One open row keeps the transitions and their proof small, and a lost copy must not hide a failure or leave a task with no copy. Rejected: the sibling rule of the reviewed design in the core (a lost sibling masked a failure, and a release under `running` left a task with no copy). Home: file 09 (speculation: file 24). Reopen when: a core feature needs two open rows for one task.

**D-129 One key type on a `wss` road.** Decision: The TLS key of a coordinator is an Ed25519 `pod-identity` key, as the key of each worker and each submitter is. Both ends use `pod_tls::peer` (TLS 1.3 only, Ed25519 only, no resumption, each side pins the key of the other, a key set that changes while the server runs, `peer_key` reports the key). A pin is a `pod_identity::KeyName`: the `SHA256:` fingerprint in files, tokens and connect strings (field `k`), and the display form (`DisplayFingerprint`) for a person. Ask P-3 is only the enrolment mode of `peer`. The enrolment binding signs the 32 bytes of the client key. A listener with a certificate of a public CA (`--webpki`) is a later item (file 24); the ES256 key of the run identity is a separate P-256 key for tokens only (file 17).  
Why: One module, one key type and one pin form; the crate that exists does it. Rejected: a P-256 coordinator key with a `sha256/` SPKI pin (a second verifier that mixes key types, which `pod-tls` does not have). Home: file 16. Reopen when: a coordinator needs a key that a public CA certifies, or `pod_tls::peer` drops Ed25519.

**D-130 A build directory that does not fit in memory.** Decision: At shield `private`, an owned directory of the view is in the memory rung of the work area when its estimate fits, and in the sealed store on disk, served by the view server through FUSE, when it does not. The estimate is the size that the sealed manifest recorded at the last session end times 1.5, or 1 GiB with no record; memory takes directories while the sum stays under 75 percent of `area_max`. A write past `area_max` ends with `area_full`, and the next session starts that directory in the sealed store. The setting `area` takes `auto`, `memory` or `sealed`; `sealed` with no FUSE rung is refused with `no_sealed_area`. From M2.  
Why: Speed when it fits (A-21 holds for the memory rung), and no loop of failures when it does not. Rejected: always memory (a large build fails each time on a host with little free memory); always the sealed store (each write of a build pays FUSE and a seal); a plain disk directory (breaks `private`); a move of a directory while processes hold its files. Home: file 13. Reopen when: a kernel gives an unprivileged encrypted disk area that is faster than FUSE with the seal.
