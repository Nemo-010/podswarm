# 3. Architecture

This file is the map of the design: the layers, the roles of the one binary, the two ways to work, walk-throughs of the main commands, the processes and threads, the limits of one authority, the deployment shapes, the reading of "no daemon", and the failure domains. File 01 states the requirements that this design answers. Each part points to the file that owns its rules and numbers; this file repeats no rule of another file.

## 1. The idea

podswarm is to compute what `ssh` is to a login. One binary and one protocol give the use of the processors, the memory and the network of any machine that the user can reach. The user names a machine, or lets podswarm pick one, and a command runs there with the caller's files, terminal, signals and exit code. podswarm copies itself to the far machine on first use, runs there while a session needs it, and leaves no service behind. The same core runs one command now (`podswarm run`), many commands over a pool (`podswarm x`, the HyperShell face), every new process of a build over a pool (spreading), and durable queued work under a coordinator. No part of the design knows a tool: a build gets faster because its processes run on more cores, not because podswarm understands the build.

## 2. The layers

```
  queue      durable tasks, retries, batches, a coordinator
  spread     each new process of a program can run on another machine
  pool       machines, capacity, placement, cells
  network    the policy of the traffic of an attempt
  view       the caller's directory tree on the worker
  attempt    one process tree on a worker, attached or captured
  link       pod-link streams over the road; hello, ready, reattach
  road       one ordered byte stream to a podswarm process on a far machine
  ------------------------------------------------------------------------
  boundary   protects the host from the task        (axis across all layers)
  shield     protects the task and the caller from the host
```

| Layer | One sentence | File |
| --- | --- | --- |
| road | A road gives one ordered byte stream to a podswarm process on a far machine and can start that process: `ssh`, `local`, `podssh`, `exec:`, `wss`, and the reverse roads of `pod-relay`. | 04 |
| link | `pod-link` carries a control stream and bulk streams over the road, with `hello` and `ready` at the start and reattach after a cut. | 04 |
| attempt | An attempt is one process tree on a worker, started by an authority, with attached I/O (terminal, stdin, signals) or captured output, the fence and reconciliation. | 05, 12 |
| view | The process on the worker sees the caller's directory at the same path; reads come from the caller on demand and writes land on the caller's disk; sync is the fallback. | 06 |
| network | The traffic of an attempt follows a policy that podnet serves: pooled uplinks by default, an exit on demand. | 14 |
| pool | The pool lists the machines of a user, their capacity and labels, and places one command on the best machine; cells group machines by authority and region. | 08 |
| spread | An exec supervisor catches each `execve` of a program and runs the new process on a pooled machine with the same files, environment, pipes, signals and exit code. | 07 |
| queue | Tasks are durable intents with states, retries, groups and runs; the engine drives workers at high rate; a store keeps them. | 09, 10, 11 |
| boundary | `none < confined < sandbox < vm`: what the task cannot do to the host. | 13, 12, 24 |
| shield | `none < private < guest < sealed`: what the host cannot do to the task and the caller's data. | 13 |

Parts that cross the layers: the content store, staging, outputs and checkpoints (file 15); identity, admission and limits (file 16); the machine interface, hooks, plugins and the run identity (file 17); the commands (file 18).

## 3. The roles of the one binary

`podswarm` is one file per target. The role is a subcommand. The alias `psw` is the same file. A party that asks a coordinator for work and reads its state (the CLI, a script, an agent) is a **submitter**; it is a client, not a role that owns state.

| Role | Command | Owns | Does not own | Starts | Ends |
| --- | --- | --- | --- | --- | --- |
| **home**, kept by the **holder** | `podswarm run`, `x`, `each`; the holder is `podswarm holder` (internal) | the authority of a session: the in-memory queue, placement, the files and index of the view, the terminal, the roads and links, the learned table | durable state, a TCP listener, any key on a far machine | the first command of a user starts the holder; `--no-hold` makes the command itself the home | the holder exits after `hold_s` with no command, no attempt and no queued task, and sends `bye` on each link (file 04) |
| **worker** | `podswarm worker --stdio` (started over a road); `podswarm join` (dials out); a worker in the caller's process (`local`) | its run directory, the spawner and keepers, the view server, the journal, the content cache, the attempts in hand, the fence | scheduling, task state, the truth of the caller's files | by the home over a road; by the user for `join` (or `autostart`) | a road worker ends after `bye`, or after the reattach window and `linger_s`; a `join` worker ends when it is revoked, at the end of a drain or of its lifetime, or after `idle_exit_s` (files 04, 10) |
| **coordinator** | `podswarm coord` | the store, the durable queue, workers, invites, submitters, the blob store, the listener and the local socket | execution; the caller's files (it relays a view, file 08) | the user runs it in the foreground, with `--detach` or `autostart` as options | `podswarm coord stop` or a signal; running attempts survive a short stop (section 11) |
| **hub** (relay only; M9) | `podswarm hub` | open streams and the allowlist of coordinator names | task data in clear text, any key of a worker or a coordinator | the operator | the operator (file 24) |

Two words name the files of a session. The **origin** is the caller's machine: it holds the truth of the workspace and serves the lower layer of the view. The **anchor** is the machine that runs the root process of the command: it holds the upper layer and is the file authority for the files that members write (files 06, 07). With `podswarm run -- CMD` the anchor is the caller's machine. With `podswarm run HOST -- CMD` the anchor is HOST. The word "hub" names only the relay.

## 4. Two ways to work

A **session** has the home as its authority. Nothing is durable unless `--db FILE` is given, and nothing listens on a TCP port unless the user asks with `--listen` on `x` (file 18): the home dials each far machine over a road and starts the worker there. A **swarm** has a coordinator as its authority. Its store is durable, it serves many submitters, and its workers dial it.

| Aspect | Session | Swarm |
| --- | --- | --- |
| Authority | the home (the holder, or the command with `--no-hold`) | the coordinator |
| Store | `MemStore`, level `memory`; `--db FILE` gives a SQLite store (file 11) | `SqliteStore`, `strict` or `batched` (file 11) |
| Who dials | the home dials the worker over a road and starts it | the worker dials the coordinator (`join`); a submitter dials too |
| Identity | the road authenticates both ends (ssh); no TLS and no podswarm keys on the link; the home gives the worker number | mutual TLS 1.3 with Ed25519 keys, invites, pins and the `submitters` table (files 04, 16) |
| Machines | the pool file of the user (file 08) | the enrolled workers; a coordinator appears in a pool as a swarm cell (file 08) |
| Files | the home serves the view | the coordinator relays the view of a caller, or staging moves blobs (files 08, 15) |
| A loss of the authority | ends the session; far attempts end at their fence | the coordinator restarts from its store; attempts inside the fence keep running |
| Same in both | the attempt protocol and its messages (file 05), the fence and reconciliation, the queue model (file 09) and the engine (file 10), the worker and its execution (file 12), the view protocol (file 06), the shield and the boundary (file 13) | the same |

The same engine runs in both. A session is the engine with the writer stage absent. A command of `podswarm run` is a task with one attempt, attached I/O, `delivery = at_most_once` and `retries = 0` (file 09).

## 5. Walk-throughs

### 5.1 `podswarm run bigbox -- cargo build`, the first time, on a machine with no podswarm

1. The command finds no holder on the holder socket. It starts `podswarm holder` and connects to it (file 04, the holder).
2. `bigbox` is a pool entry or an ssh host name. A named machine gets no estimate, but the candidate filter applies: os, arch, shield, view, capacity (file 08, placement).
3. No ssh master runs for `bigbox`. The command has the terminal, so it starts the master with prompts allowed; ssh asks its questions once. Every later session uses the master with `BatchMode=yes` (file 04, the first connection).
4. The holder runs the probe step over the road: `uname -sm`, the cache directory, the runtime directory, the cached binaries. It maps the answer to a static target (file 04, bootstrap).
5. No binary of this version is in the far cache. The holder sends its own binary for that target, compressed, through the same road. The far side writes a part file, the binary checks its own hash (`self verify`), and an atomic rename puts it in the cache (file 04, bootstrap; file 16, release checks).
6. The holder starts `podswarm worker --stdio` with a new `sid` and nonce. The worker re-executes from a memory file, makes its private run directory, forks its spawner before any thread exists, writes the road preface, and sends `hello` with its `caps`: cores, speed score, boundary, shield, view rungs, network policies (files 04, 08, 12).
7. `bigbox` has no `trust` key, so its default shield is `private`. The CLI prints one line about it. The worker makes a memory-backed work area and keeps its keys out of reach of a dump (file 13, shield `private`).
8. The home answers `ready`. The worker sends its first `hb` and a standing `pull` (files 04, 05).
9. The home builds the shape: `argv` from the command, `io = attached`, `pty` when stdin and stdout are both terminals, the `view` object, the network policy, the shield of the run. The caller's environment passes, minus the credential deny list (files 05, 13).
10. The view opens. The export root is the nearest ancestor with `.git`. The spawner on `bigbox` forks the view server, which takes the first rung that its probe passes and shows the tree at the caller's absolute path in a private mount namespace. `target/` is git-ignored, so it stays on the anchor (`bigbox`): it is native there and does not cross the link. Credential files read as absent (file 06).
11. The home offers the attempt on the standing `pull`. The spawner forks a keeper. The keeper joins the namespace of the view server, opens the terminal, and runs `cargo build` (files 05, 12).
12. The caller's terminal goes to raw mode. Keys, window size changes and signals cross on the `tty` stream and the `resize` and `signal` messages (file 05, attached I/O).
13. `cargo` reads sources by node id on demand; the worker cache keeps them, sealed at shield `private`. Its writes to `target/` stay on `bigbox`. A write to a path that git would see (for example `Cargo.lock`) goes to the write-back log and lands on the caller's disk by an atomic rename. A kept path, such as the built program, comes back only through a pull rule: `[view] pull` in the workspace file or `--pull PATH` names `target/release/NAME`. At the end of a run that kept paths, the command prints one line with their names and size (file 06, writes).
14. `cargo` exits. The result row carries the code. `podswarm run` exits with that code, 128 plus the signal number for a signal, and 255 for a failure of podswarm itself (file 18).
15. The holder keeps the road, the worker, the view server and the work area warm. After `hold_s` with no command, it sends `bye`; the worker ends, removes its run directory and the work area, and exits. On `bigbox` stay the binary in the cache, the probe cache, and the content cache as ciphertext under a key that the caller holds. `podswarm forget bigbox` removes them; `--no-trace` keeps none of them (files 04, 13).

### 5.2 The same command, the second time

1. The command connects to the holder socket. The holder lives, the road is open, and the worker waits with its standing `pull` (file 04).
2. The home revalidates the view: the worker sends the directory versions that it holds, the home answers `same` for each unchanged directory, and the access trace of this command drives prefetch. Only the records of modified files cross the link (file 06, warm state).
3. The offer goes out on the standing `pull`, and the keeper execs at once: no ssh session, no bootstrap, no mount. Target A-20 bounds the added time (file 01).
4. `target/` is warm on `bigbox`, so `cargo` rebuilds only the units whose sources differ.
5. Without a holder (it exited), the road opens again and the far cache holds the binary, so step 5 of section 5.1 does not run. A worker kept by `linger_s` is found by the probe and attached. A new holder is a new generation for each far worker (file 04).
6. The learned table of `cargo build` now has a run time and a parallelism. `podswarm run -- cargo build` with no host uses it to pick the machine (file 08, the learned table).

### 5.3 `podswarm run --spread -- make -j64` over a pool

1. With no host, the root of the tree runs on the caller's machine, which is the origin, the home and the anchor of the session. The holder opens the roads of the pool in parallel (files 07, 08).
2. The local worker starts `make` under the exec supervisor: a seccomp user notification filter on `execve` and `execveat`, inherited by every descendant. A query of the CPU count answers with the pooled core count (file 07).
3. `make` forks and execs `cc`. The supervisor reads the path and the arguments and decides: an ordered rule list, then the learned table per program. The process moves only when its expected finish time on a member is well under the local one. A process that inherits a descriptor other than stdio and the jobserver stays local (file 07).
4. An exec that stays local continues at once. For an exec that moves, the supervisor seizes the thread, lets the real exec run, stops the new program before its first instruction, and makes it exec the stub. The pid, the parent and the process group stay on the caller's machine (file 07).
5. The stub asks a member on an `exec` stream. The member has the same CPU architecture and operating system. It reads the `cc` binary and the sources from the caller through the view, waits until its view has the epoch that the request carries, and runs `cc` under its own supervisor, so that children of `cc` can move too. A fresh jobserver replaces the one of `make` on the member (files 05, 06, 07).
6. stdin, stdout and stderr cross through the stub. `cc` writes `foo.o`. Its writes reach the home before its exit status, its output bytes or any other event of it that others can see: causal close-to-open (file 07).
7. The stub exits with the code of `cc`. `make` sees the exit and finds `foo.o` on the caller's disk.
8. The link step runs where the rules place it. `make` exits, and `podswarm run` exits with its code.
9. A slow link at the caller's machine: `podswarm run HOST --spread -- make -j64` runs the root on HOST, which is the anchor: it holds the upper layer and is the file authority for the members, and it reads the caller's tree (the origin) through the view (file 07).

### 5.4 `ls *.mp4 | podswarm x 'ffmpeg -i {} {/-}.webm'` over three machines reached by ssh

1. `x` reads the lines of stdin. It makes one shape with the template and one task per line. A bad token exits 64 before a task is queued (files 09, 18).
2. The holder is the authority. Its queue is in memory, and the engine of file 10 runs with no writer stage.
3. The candidates are the caller's machine and the pool machines that `x` selects (file 08). The holder opens the three roads in parallel; a machine with no binary goes through the bootstrap of section 5.1. Each machine with no `trust` key gets shield `private`.
4. Each worker sends a `pull` with its free slots. The engine sizes each offer by the depth rule, so a worker holds enough unstarted tasks to cover the round trip (file 10).
5. The worker expands `{}` and `{/-}`. The command has no shell metacharacter, so `ffmpeg` runs with no shell (file 12).
6. The tasks carry the view of the caller's working directory (`x` defaults to `--view auto`; a worker with the same shared file system at the same path runs in the mount, D-127): `ffmpeg` reads each `.mp4` from the caller on demand, and each `.webm` lands on the caller's disk through the write-back log (file 06). `--stage-each` sends each input as a blob instead (file 15).
7. Results come back self-clocked; the full output streams to the terminal, and the record keeps a head and a tail (files 05, 12).
8. A failed task runs again inside its retry budget; a task of a lost worker runs again inside its loss budget (file 09). Near the end, tail reclaim moves unstarted tasks from a busy worker to an idle one (file 10).
9. `x` exits 0 when every task succeeded, else 1. The holder keeps the three workers warm for the next command.

### 5.5 A queued run on a swarm with workers that dial out, through a coordinator restart

1. The operator runs `podswarm coord --listen ADDR` and makes invites. Each worker machine runs `podswarm join wss://...` with the token on stdin. The worker enrols with its Ed25519 key in the TLS handshake and gets a worker row (files 04, 16).
2. A submitter sends `submit` over `wss` with its key, or over the local socket. The coordinator commits the tasks before it answers `submitted` (files 05, 11).
3. Workers pull. An offer of `at_least_once` tasks leaves before its lease row commits; an offer with an `at_most_once` task waits for the commit (file 11). Workers run attempts, send `hb` every `hb_s`, and send results; each `ack` follows the commit of its result.
4. The coordinator process dies. Each worker sees its link end, keeps its attempts, and keeps finished results in its journal. Its fence runs on: with no answered `hb`, each attempt gets the polite signal at `t_ok + silence_s` and the kill a grace period later (file 05, the fence).
5. Workers redial: a first delay uniform in `[0, reconnect_jitter_ms]` from the last `ready`, then full jitter (file 04).
6. The coordinator starts. It takes its lock, checks the database, loads the open runs, rebuilds the queues and the open rows from the lease rows, sets `last_rx` of each worker to now, and opens its listener (file 11, recovery). Under a burst it answers `busy` with a retry time (file 10).
7. Each worker sends `hello`, gets `ready` with the same generation, and sends an `hb` with its full holding. Reconciliation marks running rows, returns unstarted ones, and cancels attempts that the store does not know (file 05).
8. Workers send the results of their journals. The coordinator records each once; a result for a decided task is kept with `accepted = 0` (file 09).
9. A restart shorter than the silence budget is not seen by a running attempt. A longer one ends attempts as `killed` with reason `self_fence`: an `at_least_once` task runs again inside its loss budget, an `at_most_once` task becomes `lost` (file 09).
10. `podswarm wait` exits 0 when every task succeeded, else 1.

### 5.6 A long run that checkpoints and resumes on another machine

1. The shape has the field `checkpoint` (exit code, signal, grace, timer). The task runs on machine A (file 15).
2. The program writes its state to `TASK_CHECKPOINT_DIR` and runs `podswarm checkpoint save`, or it exits with the checkpoint exit code, or it saves on the signal. The worker builds a manifest, uploads the blobs that the store lacks, and sends `ckpt_commit` (file 15).
3. The authority accepts a commit only from the live attempt and only with a newer sequence number, writes the checkpoint row, and answers `ckpt_ack` after the commit (files 11, 15).
4. Machine A drains, reaches the end of its lifetime, or gets a preemption notice. Each asks for a checkpoint first. The attempt ends with outcome `checkpointed`, and the task is `ready` again with no use of a budget (files 10, 15). When machine A dies instead, the task is lost and runs again inside its loss budget, and at most the work since the last checkpoint is lost (file 09).
5. The engine offers the task to machine B with the checkpoint in the offer row. Before the exec, machine B puts the tree into `TASK_CHECKPOINT_DIR` from its cache and by `blob_get` (file 15).
6. The program starts with `TASK_RESUMED=1`, reads its state, and goes on. A late commit of the old attempt on A is `stale` and moves nothing.
7. A checkpoint stays in the cell of its run. `checkpoint export` to another cell needs the residency rule of that cell to pass (file 08).

## 6. Processes on each machine

```
 caller's machine                               far machine (ssh road)
 +----------------------------------+           +-----------------------------------------------+
 | podswarm run ... (the command)   |           | sshd                                          |
 |    | unix socket, mode 0600      |           |  +- sh -c '...'                               |
 |    v                             |           |      +- podswarm worker --stdio               |
 | holder (home of the session)     |  ssh      |         current-thread runtime, link, journal |
 |    roads, links, view index,     |  master   |         | socketpair                          |
 |    in-memory queue, placement    |=========> |         +- spawner (one thread, subreaper)    |
 |    +- ssh client per lane        |  one TCP  |              +- view server (one per home and |
 |    +- local worker (in process)  |  conn.,   |              |  workspace; mount namespace)   |
 |       +- spawner, keepers        |  pod-link |              +- keeper (one per attempt)      |
 |       +- exec supervisor         |  inside   |              |   +- exec supervisor (spread)  |
 |          (root of a spread run)  |           |              |       +- payload               |
 +----------------------------------+           |              +- keeper ... +- payload         |
                                                | run directory: attach.sock, lock, area        |
                                                |  <- podswarm worker --attach (reattach only)  |
                                                +-----------------------------------------------+
```

* The command and the holder talk over the holder socket. The holder runs the ssh clients; the ssh master carries every session to one host (file 04).
* The worker forks the spawner before any thread exists. The spawner forks the view server and one keeper per attempt. The keeper is the subreaper of its attempt and holds the fence with the spawner (file 12).
* With `--spread`, the keeper starts the payload under the exec supervisor. A moved process is a stub on the machine that called `execve` (the anchor for a child of the root) and a payload on the member (file 07).
* At shield `guest` and `sealed`, the worker on the host is a relay: it starts the guest and splices bytes, and the guest runs its own worker (file 13).
* A worker that dials out (`join`) has the same processes under its own parent, with a state directory in place of a run directory (file 12).

## 7. Threads and engines

| Process | Threads and tasks | File |
| --- | --- | --- |
| coordinator | one I/O runtime with a connection task per link (decode, stamp `last_rx`, encode); one scheduler actor thread that owns all scheduling state and never touches JSON; one store writer thread with natural group commit; one WAL checkpointer thread with its own connection; reader connections for `ls`, `show` and `logs` | 10, 11 |
| home (holder) | the same actor and connection tasks; no writer stage with `MemStore`, a writer and a WAL checkpointer with `--db FILE` | 10, 11 |
| worker | one current-thread runtime; the fence on a 1 s tick of the fence clock; the spawner, the keepers and the view server are processes, not threads | 12 |

## 8. Limits of one authority

These limits bind a coordinator in this order as the worker count rises. The measurements come from one 8 vCPU x86_64 virtual machine on loopback; file 10 gives the full table and the benchmark cells that measure the real build.

1. **Descriptors.** Each connection costs one descriptor. [EV-003] A soft limit of 1,024 stops a coordinator near 1,000 workers. The coordinator raises its soft limit to the hard limit at start and refuses connections above `max_conns` with `busy` (file 10).
2. **Memory per connection.** [EV-004] This is a floor: worker records, open rows and buffers come on top. Target A-15 bounds the total per idle worker (file 23). On the connection term alone a machine with 1 GiB fits more connections than its descriptor limit, so descriptors bind first.
3. **The reconnect storm.** After a restart each worker redials at once. [EV-005] A real network and a full `hello` with its holding cost more. `reconnect_jitter_ms` spreads the first redial and accept pacing answers `busy`, so the storm ends well inside the silence budget (file 10).
4. **Heartbeats.** `W / hb_s` messages per second. [EV-006] Parked pulls carry idle workers. This is not a limit below the descriptor limit.
5. **The writer.** [EV-007] The writer is the first CPU stage, and the store bound with natural batching is the last limit; file 10 gives the model and file 11 the disk guard.

A session has other limits: the holder keeps at most `roads_max` roads, and each road costs a few descriptors on the caller's machine (file 08, limits of a pool).

**Why there is no fan-in layer.** A process that merges heartbeats and acknowledgements of many workers into fewer messages would cut connection CPU, and it would add a component that must be tested for loss and order. The numbers above give no reason for it: heartbeats of 10,000 workers cost a few percent of one core, and the binding limits are descriptors and the reconnect storm, which the hub and `reconnect_jitter_ms` address. Three parts cover the cases that remain: a hub removes the descriptor limit and the need for a reachable address (file 24); a sub-coordinator serves a site with a slow link (file 24); independent cells scale out with one authority each (file 08). Reopen the question when a swarm needs more than 10,000 workers, when a benchmark of file 23 shows connection handling above half of the coordinator CPU, or when the hard descriptor limit of the coordinator host is below the worker count and cannot change. (D-116)

## 9. Deployment shapes

| Shape | Road | Authority | Milestone (file 22) |
| --- | --- | --- | --- |
| A laptop alone | `local` | the home | M0 |
| A laptop and machines reached by ssh | `ssh` | the home | M1 (one machine); M2 (pool) |
| A rented server with other root users | `ssh`; shield `private` by default (file 13) | the home | M1 |
| A pool with spreading | `ssh`; the anchor is the file authority (file 07) | the home | M3 |
| A swarm on a VM with a public name | `wss`; workers dial out; a pinned key in the invite | the coordinator | M4 (public listener M5) |
| A swarm on a LAN | `wss` with a LAN address in the invite | the coordinator | M4 |
| An HPC allocation | `ssh://node?jump=login` or `exec:srun ...` for a session; `srun podswarm join wss://...` for a swarm; node-local state, lifetime from the batch system (files 04, 10) | the home or the coordinator; a sub-coordinator per site later (file 24) | M2 (`exec` road); M5 (`join`) |
| A board and phone farm that dials out | `podswarm join wss://...` under Termux or `autostart`; later `relay://NAME` for a session | the coordinator | M5 (reverse roads later) |
| A host with HTTPS-only egress | `join wss://...` through `pod-proxy` to a coordinator on port 443; a hub when the coordinator cannot listen (file 24) | the coordinator | M4 (hub M9) |
| Several cells | each cell has its own road and authority; selectors and residency rules choose the cell (file 08); one identity across cells by organisation statements (file 16) | one authority per cell | M9 |

A non-root process cannot bind a port below 1024 on a default Linux host. A coordinator binds a higher port, and the host redirects 443 to it or grants the capability (file 19).

## 10. How "no daemon" fits

The org rule is "No root, no daemon. Built for hosts where you get a shell and little else." File 02 gives its scope. podswarm reads it in three parts.

**The holder.** The holder is a per-user process that ends by itself, as an ssh control master does. The first command starts it, it listens only on a Unix socket of mode 0600 with a peer uid check, it has no boot start and no unit file, and it exits after `hold_s` with no command, no attempt and no queued task. `--no-hold` removes it: the command itself is then the home (file 04).

**The far worker.** A worker that a road started lives while a session uses it. After `bye`, or after a cut and its reattach window, it ends its attempts, removes its run directory and exits. What stays is a cache in the user's directory, which `podswarm forget` removes (file 04). A worker that dials out and stays (`podswarm join`) exists only for a machine that nobody can dial; the user starts it, and `autostart` is a separate command that the user runs.

**The coordinator.** The coordinator is optional. It is a foreground process that the user starts, as `podnet` and `podssh node` are. `--detach` makes a supervised copy in the background. `podswarm autostart` writes a user-level unit, a `crontab @reboot` line, a launch agent or a logon task, with no root (file 18). It listens on TCP only with `--listen`; with no address it uses a hub (file 24).

**Owner ruling.** Default taken: a coordinator is a long-lived foreground process of the user and is not a daemon in the sense of the rule. If the owner reads "no daemon" as "no long-lived server process", only sessions remain, and queued work, many users and workers that dial out lose their authority. The rulings are R-01 and R-04 (file 26).

## 11. Failure domains

| Failure | Effect | Recovery | Rule in |
| --- | --- | --- | --- |
| The road cuts | The worker keeps its attempts and listens on its attach socket; the fence runs on. The home declares the road dead and redials. | `worker --attach` joins the new stream to the worker; the first `hb` reconciles; streams go on at their offsets. A cut shorter than the silence budget is not seen by the command. | 04, 05 |
| The far worker dies | The spawner sees end of file and kills every keeper tree; the attach step finds no worker. | The home counts each open attempt as lost and starts a new worker. An attached command exits 255 and prints the class; a queued `at_least_once` task runs again. A non-empty write-back log is applied first in the next session. | 04, 06, 09, 12 |
| The far machine reboots | The processes, the run directory and the memory-backed work area are gone. | As above. A `join` worker with `autostart` comes back; its first `hb` shows its attempts absent. The sealed cache and the binary stay. | 04, 09, 13 |
| The holder dies | Each far worker sees a cut and keeps its attempts until the fence, then ends. The command loses its session. | The next command starts a new holder, which is a new generation for each far worker. | 04, 05 |
| The caller's machine sleeps | No `hb` gets an answer, so far attempts reach their fence; a road worker then ends. A worker on the sleeping machine counts the sleep on its fence clock. | A sleep shorter than the silence budget is not seen. For longer sleeps, raise `silence_s` on the shape or submit to a swarm. | 05 |
| A member of a spread session dies | The stubs of its processes lose their member. | A process with no visible effect yet runs again on another member or locally; else its stub exits with TempFail and the build tool sees a failed step. The member leaves the session. | 07 |
| A coordinator dies | No scheduling. Workers keep running to their fence and keep results in their journals. | Restart: recovery from the store, paced reconnects, reconciliation, results sent again. | 05, 10, 11 |
| A coordinator disk is full | The disk guard refuses new submits with `busy`; running tasks finish and their results commit while space lasts. | Free space; a WAL that grows is the usual cause and raises an alarm. | 11 |
| A coordinator machine is lost | The swarm stops. | Restore a backup on another machine; a new generation protects the fence; an invite can list more than one address. | 11, 16 |
| A hub dies | The workers behind it lose their links and redial with jitter. | Restart the hub, or a second hub address in the invite. | 24 |
| A clock jumps | Fences and deadlines use monotonic clocks that count sleep, so they do not move. Fields that end in `_unix`, `not_before_unix`, `deadline_unix` and periodic jobs follow the wall clock and shift. | View times use the clock offset fixed at session start. On FreeBSD a forward jump of the wall clock expires the fences. | 05, 06, 09, 24 |

## 12. What the design does not have

* No kernel module, no kernel patch and no root on any machine.
* No cluster file system: the view ends with its session, and the content store is a cache with quotas.
* No consensus and no second writer: one authority per run, one cell per swarm run.
* No agent system, no prompt handling and no model calls: agents use podswarm through file 17.
* No code that knows a tool: no compiler wrapper, no build cache, no rule for a program.
* No service that must run before first use: a road and the binary are enough.
