# 0. Summary

This file is the one page for the owner. It says what podswarm is, how the first use case runs, what each layer does, what ships in which milestone, and which questions only the owner can answer. Each part points to the file that holds the rules; this file holds no default, no limit and no wire field.

## 1. What podswarm is

podswarm is "ssh, but what you get is compute". One binary and one protocol give the processors, the memory and the network of any machine that the user can reach with ssh or a PodUtils road. podswarm copies itself to the far machine on first use, runs there while a session needs it, and leaves no service behind. It knows no tool: a build gets faster because its processes run on more cores. It has three faces on one core (file 01 section 2):

| Face | Command | For |
| --- | --- | --- |
| One command | `podswarm run [HOST] -- CMD` | one command now on a better machine, with the caller's files, terminal, signals and exit code |
| Many commands | `podswarm x`, `podswarm submit` | a list of commands over a pool: the HyperShell face (file 20) |
| Long work | `podswarm submit` to a coordinator, `podswarm checkpoint` | work that outlives the caller and resumes after a loss (files 09, 15) |

## 2. The first use case

A developer has a weak PC and a strong rented server where other people have root (file 01 section 1). The developer types one line on the PC:

```
podswarm run bigbox -- cargo build
```

| Where | What happens | File |
| --- | --- | --- |
| PC | The command finds no holder, so it starts `podswarm holder`, which keeps the home of the session. ssh asks its questions once on the terminal; later sessions use the ssh master with `BatchMode=yes`. | 04 |
| PC to server | The holder probes `uname -sm` and the cache directories, sends its own static binary for that target, compressed, into the user cache of the server, and starts `podswarm worker --stdio` over the ssh road. | 04 |
| Server | The worker sends `hello` with its `caps` (cores, speed score, boundary, shield, view rungs, network policies); the home answers `ready`, and the worker sends a standing `pull`. | 04, 05, 08 |
| Server | The machine has no `trust` key, so its shield is `private`: the CLI prints one line, and the worker makes a memory-backed work area and keeps its keys out of reach of a dump. | 13 |
| Server | The view shows the caller's directory (the export root is the nearest ancestor with `.git`) at the same absolute path in a private mount namespace. `cargo` reads sources from the PC on demand. Credential files read as absent. | 06 |
| Server | `target/` is ignored by git, so it is a native directory on the server and does not cross the link; at shield `private` a build directory that does not fit in memory lives in the sealed store on disk (file 13, section 6.2). A write to a path that git would see (for example `Cargo.lock`) goes back to the PC by an ordered write-back log. | 06 |
| PC | Keys, window size and signals pass through. `podswarm run` exits with the exit code of `cargo`, 128 plus the number of a signal, or 255 for a failure of podswarm. | 05, 18 |

What comes back (ruling R-16, file 15 section 7.1): what git would see comes back to the caller's machine; what git ignores stays on the server, warm for the next run. A pull rule (`[view] pull`, or `--pull GLOB` for one run) brings a kept path such as the built program back at the end of a run, and `podswarm pull [HOST] PATH...` brings it back later. The run prints one line that names the kept paths and their size (file 06 section 10.4).


What is left on the server after the session: the binary in the user cache, the probe cache, and the warm content cache as ciphertext under a key that only the caller holds. No process, no service, no key and no log stays. `podswarm forget bigbox` removes the rest; `--no-trace` leaves nothing (files 04, 13). The second run reuses the warm road, worker and view, so only the changed records cross the link (file 03 section 5.2).

## 3. Layers and roles

| Layer | What it does | File |
| --- | --- | --- |
| road | gives one ordered byte stream to a podswarm process on a far machine and can start it (`ssh`, `local`, `podssh`, `exec:`, `wss`). On a `wss` road each end has an Ed25519 `pod-identity` key and pins the key of the other by its `SHA256:` fingerprint (D-129) | 04, 16 |
| link | carries a control stream and bulk streams over the road; `hello`, `ready`, reattach after a cut | 04 |
| attempt | one process tree on a worker, with attached I/O or captured output, the fence and reconciliation | 05, 12 |
| view | the caller's directory on the worker at the same path; reads on demand, writes back; `sync` as the fallback. `--view` is `auto`, `fuse`, `fuse-userns`, `trap`, `sync` or `none`; `run` and `x` default to `auto`, `submit` to `none`. `auto` makes no view on a worker that has the caller's directory on the same shared file system at the same path (D-127) | 06 |
| network | the traffic of an attempt follows a policy that podnet serves | 14 |
| pool | the machines of a user, their capacity, the placement of one command, cells | 08 |
| spread | each new process of a program can run on another machine | 07 |
| queue | durable tasks, retries, groups, runs; the engine and the store | 09, 10, 11 |
| boundary and shield | the two protection axes across all layers | 13 |

| Role or word | Meaning | File |
| --- | --- | --- |
| home | the authority of a session: the caller's own process | 03 |
| holder | the background process that keeps the home between commands, as an ssh control master does | 04 |
| worker | runs attempts on a machine; started over a road, or `podswarm join` for a machine that dials out | 04, 12 |
| coordinator | an optional long-lived authority with a durable store | 03, 11 |
| hub | an optional relay of TLS streams (later) | 24 |
| session | the way of work whose authority is the home; nothing durable, nothing listens | 03 |
| swarm | the way of work whose authority is a coordinator | 03 |

## 4. The single system image ladder

| Step | What it gives | State in the design | File |
| --- | --- | --- | --- |
| 0 | a command runs on the best machine of the pool | designed; one named machine in M1, placement over a pool in M2 | 08 |
| 1 | every new process that a program starts can run on another machine, with the same files, environment, pipes, signals and exit code | designed in full (seccomp exec supervisor, takeover, stub, causal close-to-open); M3 | 07 |
| 2 | a running process moves to another machine | stated goal with limits; the checkpoint that a program writes ships in M6; CRIU and guest migration have no milestone | 07, 15 |
| 3 | the memory of the pool is one resource | stated goal with limits; placement by free memory is part of step 1; paging and a far heap have no milestone | 07 |

One process lives on one machine at a time. Shared memory that a program does not know about is a non-goal (file 07 section 20).

## 5. The two protection axes

A request is never met by a weaker level, and a machine that cannot give the level refuses by name (file 13).

| Boundary (protects the host from the task) | What it stops |
| --- | --- |
| `none` | nothing beyond the wall timeout and the tree kill; the task runs as the worker's uid |
| `confined` | file, exec and port access outside the grants, `ptrace`, mounts, new namespaces (Landlock and seccomp, Linux, M7) |
| `sandbox` | direct system calls to the host kernel: a user-space kernel serves them (gVisor through podvm, M8) |
| `vm` | any host file that is not shared: a separate guest kernel (M8) |

| Shield (protects the task and the caller from the host) | What it stops |
| --- | --- |
| `none` | nothing; the credential rules still hold (no agent forwarding, no credential file served, no secret variable passed) |
| `private` | leftovers and other users: a memory-backed work area, warm state only as ciphertext, no key on the host, removal at exit; a root user who tries can still read the process (default for each remote machine, M1) |
| `guest` | root users with ordinary tools: the run is inside a VM guest and no file, name or argv of it is on the host; root can still read guest memory (M8) |
| `sealed` | a root user who wants the data: a confidential VM (SEV-SNP first) that the caller attests before it sends a file or a key; side channels and a stop remain (M8) |

## 6. The delivery contract

Queued work runs at least once and is recorded at most once: no task is lost, and the first valid result wins. A task can run more than once after a cut or a crash, so a program uses `TASK_ID` and `TASK_ATTEMPT` to make its effects idempotent. A late result is stored and never changes a decided state. With `delivery = at_most_once`, and for each command of `podswarm run`, podswarm never starts a task twice by its own act, and a lost task waits for a person (file 09 section 14).

## 7. What ships when

The milestones are those of file 22 section 2. Each release is a beta on GitHub; M1 (`v0.1.0-beta.1`) is the first usable release.

| Id | Name | What the user can do after it |
| --- | --- | --- |
| M0 | Local | `podswarm x` and `podswarm run --local` on the caller's machine, with the HyperShell face |
| M1 | One remote machine (first usable release) | `podswarm run HOST -- CMD` over ssh with a live view, the terminal, the exit code, shield `private`, and `podswarm pull` |
| M2 | Pool | a pool file, placement of one command, `x` over the pool, the `trap` view rung, `--view auto` on a shared file system, the `exec:` and `podssh://` roads |
| M3 | Spread | `podswarm run --spread -- make -j64`: each compiler runs where a core is free |
| M4 | Swarm | a coordinator with a durable store, the `wss` road with pinned keys, invites, workers that dial out, queued runs, `x --listen` |
| M5 | Fleet and throughput | `bootstrap` and `autostart` for many machines, worker lifetime, `each`, the full pre-auth limits |
| M6 | Data and checkpoints | staged files and outputs for queued tasks, checkpoints and resume, the data key of a run in a swarm (D-126), the MCP server, hooks, plugins, the run identity |
| M7 | Isolation and network | boundary `confined`, the worker policy, network policies served by podnet |
| M8 | Guests | shield `guest`, boundaries `sandbox` and `vm`, shield `sealed` on SEV-SNP |
| M9 | Cells, jobs, hub and the rest of file 24 | regional cells, organisation statements, jobs, the hub and other later items |
| M10 | Windows and macOS as far machines | far machines that are not Linux |

## 8. Targets and measured facts

The numbers below are targets `[T]` of file 01 section 7. No benchmark of podswarm code backs them yet; file 23 section 14 gives the conditions and the test of each.

| Id | Target |
| --- | --- |
| A-20 | `podswarm run HOST -- true` adds at most 30 ms to the round trip |
| A-21 | a warm build through the live view within 10 percent of the build on the machine |
| A-22 | under 64 KiB sent before the compiler starts after an edit |
| A-23 | the first run reaches the command in under 5 s |
| A-24 | spreading is at least 5 times faster on 8 machines than on one |
| A-01 | a coordinator does at least 20,000 tasks/s |
| A-05 | worker CPU per task at most 300 us on Cortex-A53, 60 us on x86_64 |
| A-07 | `seq 100 \| podswarm x echo {}` in at most 35 ms |
| A-09 | the binary has at most 10,000,000 bytes |
| A-10 | zero lost tasks and zero duplicate accepted results |

Measured already, on prototypes and probes:
* An exec that the spread supervisor keeps local costs 30 to 130 us more than a bare fork, exec and wait over two runs, and the takeover keeps the pid (file 07 section 4, EV-021, EV-022).
* A coordinator prototype with one writer thread at `strict` ran 28,290 to 37,211 tasks/s at 200 workers, with 13 to 17 us of writer CPU per task (file 11 section 2, EV-032).
* One TLS 1.3 and WebSocket connection costs about 19.4 KiB, and 10,000 clients connected in 2.24 s (file 03 section 8, EV-004, EV-005).

## 9. What podswarm asks of the organisation

The pin is podcrates `v0.34.0` with 38 crates (file 21 section 1). File 21 section 7 holds 33 asks: 20 to podcrates (P-1 to P-21 without P-7), 8 to podvm (V-1 to V-8) and 5 to podnet (N-1 to N-5). P-7 is in the list of asks that are not made (file 21 section 8): the pin has `pod_tls::peer::peer_key`. Each ask has a fallback inside the podswarm repository, so no milestone waits for one. podswarm gives 7 new `pod-*` crates to podcrates (`pod-proc`, `pod-tty`, `pod-fuse`, `pod-cas`, `pod-view`, `pod-attest`, `pod-ssh`; file 21 section 6). The three most important:
* P-1: the crate `pod-proc` (spawner, keeper, containment rungs, tree kill, the exec takeover), for M0.
* P-16: the crate `pod-fuse` (a FUSE server with no libfuse), for the live view of M1.
* P-15: the growth of `pod-hold` for the view rung `trap` (M2) and the exec rung of spreading (M3).

## 10. Questions for the owner

File 26 section 4 holds 16 rulings that only the owner can give (R-01 to R-16). Each has a recommendation and the design assumes it until the answer. R-16 (what comes back from a run) is the rule of section 2 of this file. The three with the largest effect:
* R-01: does "no daemon" forbid a long-lived coordinator and the holder? Against: only sessions remain, with no durable queue and no workers that dial out.
* R-02: may the repository `PodUtils/podswarm` and a session for it exist? Against: the tree stays a spec and no code is written.
* R-04: may a coordinator listen on TCP when the user gives `--listen`? Against: a swarm needs a hub host that can listen.
