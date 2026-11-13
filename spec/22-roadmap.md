# 22. Roadmap

This file defines the milestones M0 to M10: the scope of each, its exit criteria, what it depends on, the asks it uses and its release tag. The order follows the owner: the first usable release is one command on one remote machine. The tests and targets that the exit criteria name are in file 23. The asks and their fallbacks are in file 21.

## 1. Rules

* Each milestone leaves the tree green and releasable. Its release is a beta on GitHub with static binaries for the targets of file 21. No release goes to crates.io. The tag of MN is `v0.N.0-beta.1`; M0 is `v0.1.0-alpha.1` and M1, the first usable release, is `v0.1.0-beta.1` (D-121).
* An exit criterion is a test id of file 23 or a target `A-nn` with its test. A milestone has at most 6 exit criteria. A criterion that a test cannot check is not an exit criterion.
* Each ask of file 21 has a fallback in the podswarm repository. No milestone waits for an ask. When an ask lands before its milestone, the milestone uses it and drops the fallback.
* At the start of each milestone the pin of file 21 moves to the newest tags (refresh rule, file 21 section 1).
* A later milestone does not change the behaviour of an earlier one except by a recorded decision. The owner's rule "no backwards compat" lets the wire and the store format change between betas; each change has an entry in file 25.
* A feature of file 24 moves into M9 only when its condition in file 24 holds.

## 2. The ladder

| M | Name | Release | Depends on |
| --- | --- | --- | --- |
| M0 | Local | `v0.1.0-alpha.1` | none |
| M1 | One remote machine (first usable release) | `v0.1.0-beta.1` | M0 |
| M2 | Pool | `v0.2.0-beta.1` | M1 |
| M3 | Spread | `v0.3.0-beta.1` | M2 |
| M4 | Swarm | `v0.4.0-beta.1` | M1 (M2 for `x` over a pool) |
| M5 | Fleet and throughput | `v0.5.0-beta.1` | M4 |
| M6 | Data and checkpoints | `v0.6.0-beta.1` | M4 |
| M7 | Isolation and network | `v0.7.0-beta.1` | M2, M4 |
| M8 | Guests | `v0.8.0-beta.1` | M7 |
| M9 | Cells, jobs, hub and the rest of file 24 | `v0.9.0-beta.1` | M5, M6 |
| M10 | Windows and macOS as far machines | `v0.10.0-beta.1` | M2 |

M3 and M4 can run in parallel after M2. M6 and M7 can run in parallel after M4.

## 3. M0: local

Scope:
* The repository, the crates and the layer rule of file 21; the gate and the guards G-01 to G-14, G-16 to G-18 of file 23.
* `podswarm-core`: records, transitions T1 to T11, invariants I1 to I7 as checks, the scheduler step (file 09, file 10).
* `podswarm-proto`: messages, codec with zstd, limits, error codes (file 05).
* `podswarm-tmpl`: the template language (file 18).
* `podswarm-store`: `MemStore`; `SqliteStore` for `x --db FILE` at `batched` (file 11).
* `podswarm-sim`: the simulation contract of file 23 section 3, with the oracle and the plants.
* The worker engine and the executor with the spawner and the keeper, rungs `subreaper` (Linux), `session` (macOS), `job` (Windows); boundary `none`; output capture; limits in `polled` mode (file 12).
* `podswarm x` with the HyperShell face of file 20; `podswarm run --local -- CMD` with attached I/O and a terminal; exit codes of file 19.
Exit criteria:
1. M-01 to M-08 pass at the per-commit budget, and each mutation plant of file 23 section 3 fails within it.
2. U-tmpl, U-gnu and the rows of U-parity that need no remote machine pass.
3. F-19 and F-20 (tree kill and attribution) pass on Linux; F-23 and F-24 pass.
4. A-07 (`seq 100 | podswarm x echo {}` in at most 35 ms), test B-19.
5. G-03, G-04 and G-13 pass on each target that CI builds.
Asks used: P-1, P-8, P-9, P-21; fallbacks in `podswarm-exec` and `podswarm-proto`.

## 4. M1: one remote machine (first usable release)

The owner's first release: `podswarm run HOST -- cmd` on one machine the user can reach with ssh, with a live view of the directory, the terminal and the exit code.
Scope:
* The `ssh` and `local` roads, the road preface, bootstrap of the binary with the compressed copy (the far machine's `zstd`, else `gzip`, else raw), the link on `pod-link`, the holder, reattach, `podswarm forget`, `--no-trace` (file 04).
* The attempt with attached I/O, a terminal when stdin and stdout are terminals, signals, window size, the exit code of the command, 124, 126, 127, and 255 for a failure of podswarm (files 05, 18).
* The view with the rungs `fuse`, `fuse-userns` and `sync`; the home index and watcher on Linux, macOS and Windows; owned directories, write-back, held items, conflict copies, the deny list, the filtered `.git/config`, the clock offset, trace prefetch (file 06). What comes back: what git would see comes back to the origin; what git ignores stays on the anchor; `[view] pull` and `--pull GLOB` bring a kept path back at the end of a run, the verb `podswarm pull [HOST] PATH...` brings it back after the run, and the run prints one line that names the kept paths (files 06, 18).
* Shield `private` with the rungs `ramfs-ns`, `tmpfs-noswap` and `runtime`; keys in `memfd_secret`; removal at exit and the start sweep; the credential rules at every shield level; `shield_unavailable`; default `private` for remote machines (file 13). Known limit of M1: each owned directory is in memory, so a build directory larger than its share of `area_max` fails with `area_full` (file 13, section 6.2).
* The network policy `host` only; `pool` served as `host` with the one report line; other values refused with `not_built` (file 14).
* Far machines: Linux. Callers: Linux, macOS, Windows.
Exit criteria:
1. A-20 and A-23 (B-20, B-23) on the CI pair of machines; A-21 and A-22 (B-21, B-22) for a warm build of a mid-size Rust workspace.
2. U-run-exit and U-run-tty pass: the exit code, the terminal and the signals of `run`.
3. The view fault set F-40 to F-47 and U-view-back pass.
4. The shield set E-10 to E-18 passes on a Linux host with other root access emulated by the test.
5. U-conf-road and U-road-rc pass; E-06, E-07 and E-08 pass in the live workflow.
6. A-14 for an attached command: E-07 cuts the road for 10 s and the command ends with its own exit code and whole output.
Asks used: P-4, P-5, P-6, P-10, P-11, P-16; fallbacks in `podswarm-net`, `podswarm-worker`, `podswarm-cli` and `podswarm-view`.

## 5. M2: pool

Scope:
* The pool file, `pool add|ls|rm|probe|import-ssh`, the worker report, the speed score, placement of one command, the learned table, `local_under_ms` (file 08).
* `podswarm x` over the machines of the pool through the session; the queue engine with offers, pulls, deep queues, tail reclaim and reservation (file 10).
* The view rung `trap`; inotify tracking for the replica rungs; `--view auto` with no view on a worker that has the caller's directory on the same shared file system at the same path (file 06, D-127).
* Shield `private` across sessions: the sealed store, the mismatch check, the swap and store tests; the `sealed-fuse` rung; owned directories that do not fit in memory in the sealed store, and the setting `area` (file 13, section 6.2).
* The `exec:` and `podssh://` roads (file 04).
Exit criteria:
1. A-36, A-37 and A-38 (B-30); M-40 to M-43 pass.
2. A-08 (B-05) on a shaped link between the home and one worker.
3. U-parity passes in full against 2.8.7 and 2.9.0a7 with the workers of a pool (A-17).
4. F-02 to F-05 pass with the home as the authority and three far workers.
5. U-conf-view passes on the four rungs `fuse`, `fuse-userns`, `trap`, `sync`.
6. M-49 passes: an offer in flight during a `pull` gives no second offer for one slot (D-125); E-35 passes (D-127).
7. E-36 and E-37 pass: a build directory past `area_max` moves to the sealed store (D-130).
Asks used: P-15 (trap), P-17 filed after this milestone; fallbacks in `podswarm-exec/src/trap/` and `podswarm-view`.

## 6. M3: spread

Scope (file 07, section 17):
* Linux anchors and Linux members of the same architecture; the exec rungs `seccomp` with the takeover and `shim`.
* The anchor is the file authority: the caller's machine for `run --spread -- CMD`, HOST for `run HOST --spread -- CMD`; causal close-to-open; locks through the anchor; `/tmp` layered.
* What crosses an exec: descriptors 0, 1, 2 as pipes, files, terminals and `/dev/null`; the jobserver rewrite.
* The decision rules 1 to 9, the exec table, the run report; the pooled CPU count; `--spread` on `run` and `x`.
* The re-run rule of a lost member over reattachable links.
Exit criteria:
1. A-24 (B-24) and A-34 on a LAN of 8 equal machines.
2. A-19: no spread session is slower than 1.1 times the run with no spreading (B-24).
3. A-29 to A-33 (U-spread-decide, B-28).
4. U-spread-takeover, U-spread-fds, U-spread-causal, U-spread-append, U-spread-lock, U-spread-signals and U-spread-cpus pass on x86_64 and aarch64.
5. F-50 and F-51 pass.
Asks used: P-1 (`takeover`), P-6 (the seize row), P-15; fallbacks in `podswarm-exec` and `podswarm-spread`.

## 7. M4: swarm

Scope:
* `podswarm coord` with `SqliteStore` at `strict` and `batched`, the writer thread, the WAL checkpointer, generation, backup, restore, retention (file 11).
* The `wss` road with mutual TLS, pins and their rotation; invites and enrol; the `submitters` table and scopes; the local socket (file 16).
* Queued runs: submit, `ls`, `show`, `logs`, `cancel`, `retry`, `wait`, `update`, groups, arrays, halt policies, `--resume` (files 09, 18).
* `podswarm join` for a worker that dials out; `podswarm workers drain|undrain|revoke|approve`.
* `x --listen` and `x --launcher` for HyperShell parity: the home listens for one run only when asked (file 18).
* The pre-auth stage deadlines and the size cap before `ready` (file 16). The caps per prefix, the ban and the global budget come in M5. Until M5 the release notes state that a listener belongs on a trusted network.
Exit criteria:
1. F-01, F-07 and F-10 pass at the counts of file 23.
2. F-11, F-12, F-13 and F-21 pass.
3. A-01, A-02 (B-02) and A-12 (B-12) on the reference host.
4. A-10: zero lost tasks and zero duplicate accepted results over F-01 to F-05 on the coordinator.
5. U-conf-store passes on `MemStore` and `SqliteStore`; G-11 and G-12 pass.
Asks used: P-2, P-3; `pod_tls::peer::peer_key` reports the key of the peer (D-129); fallbacks in `podswarm-net`.

## 8. M5: fleet and throughput

Scope:
* Workers that dial out at scale: `join` with a lifetime, `bootstrap` over ssh with `--join`, `autostart` per system, `each` (files 08, 10, 16).
* The full pre-auth limits: caps per prefix, the ban, the global budget, accept pacing (files 10, 16).
* Worker lifetime and drain with `SLURM_JOB_END_TIME` and `PBS_WALLTIME`; `idle_exit_s`.
* The built-in load generator and the benchmark set B-01 to B-19 of file 23; the target table A-01 to A-18 measured on recorded hosts.
Exit criteria:
1. A-13 (B-13): 100 machines enrolled and running in under 300 s.
2. A-15 and A-16 (B-06, B-04).
3. A-04 (B-31) on a Raspberry Pi 4 or 5 coordinator, A-05 and A-06 (B-03, B-04) on a Cortex-A53 worker.
4. F-14 and F-18 pass.
5. A-11 (B-11) and A-18 (B-14).
6. S-01 and S-02 run and their results are in the record.
Asks used: none new.

## 9. M6: data and checkpoints

Scope:
* Blobs for queued tasks: `files`, `--bin`, `--dir`, URL inputs, unpack, the fan-out budget, the worker cache, outputs, `--results DIR`, `podswarm get` (file 15).
* Checkpoints and resume: the shape field `checkpoint`, the three ways to take one, `ckpt_commit`, restore with `TASK_RESUMED`, drain and lifetime asking for a checkpoint, encryption under a caller key, sinks (file 15).
* The data key of a run in a swarm (D-126): the key request through the coordinator, the answer of a connected home, the state `held` with reason `needs_key`, and `--key-escrow`, which brings the `secrets` table and the master key of `secrets.1` (file 24, section 7) into M6 for the run key only (files 15, 16).
* The agent face and plugins: `podswarm mcp`, `podswarm skill`, external subcommands, hooks, signed webhooks, the run identity token, the plugin kinds `exec:` road, checkpoint sink and admission policy (file 17).
Exit criteria:
1. F-26, F-27, F-28 and F-29 pass.
2. M-32 and M-33 (checkpoint commit and resume) pass.
3. A-18 (B-14) with a 100 MB blob at 1 Mbit/s.
4. U-skill and U-conf-ckpt pass; U-conf-admit passes on the in-tree policy and one plugin.
5. F-37 passes.
6. M-50 passes: an attempt of an encrypted run with no home connected waits as `held` (`needs_key`), then starts or resumes by the home or by escrow (D-126).
Asks used: P-12 filed when the API is stable; fallback `podswarm-store/src/cas/`.

## 10. M7: isolation and network

Scope:
* Boundary `confined` through `pod-confine`, with the features by Landlock ABI and the Unix socket rule (files 12, 13).
* The worker policy `worker.toml` and the path rule on every path that crosses a link (file 16).
* The network policy served by podnet: `none`, `pool` over the uplinks, then `home`, `home=PORTS` and `exit:NAME`; the hold rungs `deny`, `netns`, `notify`; the member check (file 14).
* `pool` with members on other machines: pool machines with `uplink = true` and the caller's machine, each flow relayed through the authority (file 14 section 2).
* Shields and boundaries keep their order: no request is met by a weaker level.
Exit criteria:
1. F-16, F-22 and F-33 pass.
2. E-27 to E-31 pass in the live workflow.
3. M-44 and M-45 pass; U-member passes.
4. A task that asks `boundary = confined` is never offered to a worker that reports `none` (M-46).
5. B-33 records the cost of a remote member of `pool` (K-17).
Asks used: P-14, N-1 to N-5; fallbacks: the shim, a router per change, `psw net-exit`.

## 11. M8: guests

Scope:
* Shield `guest` with the guest plan, the inner channel and the relay worker (file 13).
* Boundaries `sandbox` and `vm` and the image view through podvm and incus (file 24 section 9).
* Shield `sealed` on SEV-SNP with attestation, the TCB floor and the guest set; then TDX (file 13).
Exit criteria:
1. E-19, E-20 and E-21 pass on a host with KVM.
2. U-attest passes; G-15 passes.
3. E-22 to E-26 pass on an SNP host, run by hand and recorded.
4. B-07 records the cost of each boundary per task.
5. A task that asks `sandbox` or `vm` on a worker with no podvm fails with `needs_unsatisfiable` (M-47).
Asks used: P-18, P-19, V-1 to V-8; fallbacks: QEMU argv in `podswarm-exec`, the CLI of podvm, the `sev` crate.

## 12. M9: cells, jobs, hub and the rest of file 24

Scope: cells, regions and residency rules across swarm cells (file 08); organisation statements (file 16); and the features of file 24 whose condition holds: jobs, speculation, estimate-based backfill, the hub, the sub-coordinator, signed shapes, secrets, verify, the audit chain, worker key rotation, a second transport and packed results.
Exit criteria (each feature that ships adds its own row in file 23 and one criterion here, at most 6):
1. M-42 and M-43 pass with two swarm cells.
2. U-statement passes; an identity of one organisation key enrols in two cells.
3. F-34, F-35 and F-36 pass for the features that ship.
4. M-26 passes when speculation ships.
5. E-09 passes when the hub ships.
Asks used: P-2 for the hub.

## 13. M10: Windows and macOS as far machines

Scope:
* Windows far machines over ssh: `cmd.exe` as the default shell, the `job` rung, the view through ProjFS (file 06, later).
* macOS far machines: the `session` rung, the view through NFSv3 (file 06, later), the spread rung `shim`.
* `pod-ssh` as a library on Windows callers when ask P-13 lands.
Exit criteria:
1. U-conf-road passes against a Windows OpenSSH server and a macOS sshd.
2. E-33 and E-34 pass on hosted Windows and macOS runners.
3. A remote machine that is not Linux refuses shield `private` with `shield_unavailable` unless `trust = "own"` (M-48).
4. U-conf-exec passes on the `job` and `session` rungs.
Asks used: P-13; fallback: the system `ssh`.

## 14. Stated goals with no milestone

| Goal | Where | Why no milestone |
| --- | --- | --- |
| Step 2 of the ladder: move a running process with CRIU, or by the migration of a guest | file 07 section 19 | the checkpoint that a program writes ships in M6; the process rungs need a namespace that podswarm owns and a CRIU helper |
| Step 3 of the ladder: pooled memory beyond placement by free memory | file 07 section 20 | paging from an old machine needs step 2; a far heap needs a library that programs link |
| Integrations with the stub repositories (`podnode`, `podinit`, `pods`, `podkey`, `podlog`, `podstat`, `podrepl`, `podsnap`, `podinfo`) | file 02 section 3 | they hold no code |

## 15. What runs from which milestone

Walk-throughs of file 03 section 5, recipes of file 19 and deployment shapes of file 03 section 9.

| Item | Kind | Runs from | Note |
| --- | --- | --- | --- |
| `podswarm run bigbox -- cargo build`, first and second time | walk-through 5.1, 5.2 | M1 | |
| `podswarm run --spread -- make -j64` over a pool | walk-through 5.3 | M3 | |
| `ls *.mp4 \| podswarm x 'ffmpeg ...'` over three ssh machines | walk-through 5.4 | M2 | the view gives the inputs; no blobs needed |
| A queued run through a coordinator restart | walk-through 5.5 | M4 | |
| A long run that checkpoints and resumes on another machine | walk-through 5.6 | M6 | |
| Parameter sweep | recipe | M2 in a session; M6 on a swarm | a swarm needs `--bin` and outputs as blobs |
| Bulk media transcode | recipe | M2 in a session; M6 on a swarm | |
| Test sharding | recipe | M2 | |
| Fleet upgrade (`each`) | recipe | M5 | |
| Raspberry Pi or old phone farm | recipe | M5 | dial-out workers and lifetime |
| CI matrix | recipe | M6; a Windows row from M10 | |
| Scraping fleet, cron-like job | recipe | M9 | jobs |
| Agent offload with checkpoints | recipe | M6 | |
| Regional cells | recipe | M9 | |
| A laptop alone | shape | M0 | |
| A laptop and machines reached by ssh | shape | M1 for one machine; M2 for a pool | |
| A rented server with other root users | shape | M1 | shield `private` |
| A pool with spreading | shape | M3 | |
| A swarm on a VM with a public name; a swarm on a LAN | shape | M4 | public listener: M5 |
| An HPC allocation | shape | M2 with the `exec:` road; M5 for `join` with a lifetime | sub-coordinator: M9 |
| A board and phone farm that dials out | shape | M5 | `relay://` later |
| A host with HTTPS-only egress | shape | M4 through `pod-proxy`; M9 with a hub | |
| Several cells | shape | M9 | |
