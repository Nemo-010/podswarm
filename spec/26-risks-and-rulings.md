# 26. Risks, rulings and known gaps

This file ranks the risks of podswarm, lists what is unknown and how to settle each unknown, and holds the rulings of the owner: the ones given and the ones still asked. It also says what would change the plan and lists the known gaps. File 25 holds the decisions, file 23 holds the tests and targets (`A-nn`), and file 22 holds the milestones.

## 1. Ranked risks

Rank is impact times likelihood. Impact: H stops the project or breaks a promise, M costs rework, L is a nuisance. Likelihood is a judgment `[T]`, not a measurement. The last column names the test or benchmark that settles the risk.

| Id | Risk | Impact | Likelihood | What limits it | What settles it |
| --- | --- | --- | --- | --- | --- |
| K-01 | A flaw in leases, the fence or reconciliation loses or duplicates work. | H | M | The model and fault tests run the real transition code (D-115); the fence is enforced by the worker and by its spawner; late results never move a decided state. | Fault tests with 1,000 runs, the clock skew test, target A-10 (zero lost, zero duplicate accepted). |
| K-02 | The live view is too slow: FUSE overhead, one round trip for each cold file, a warm build more than 10 percent slower than a build on the remote machine. | H | M | Access trace and prefetch, native ignored directories (D-28), the `sync` rung for slow links (D-26). | Benchmark of a warm `cargo build` and a `make` build per rung against the same build on the remote machine (A-21, A-22); a cold start with 100,000 entries. |
| K-03 | Exec takeover (seccomp notification plus `PTRACE_SEIZE`) fails on some kernels, containers or security modules (Docker default profile, Ubuntu AppArmor rules on user namespaces, `ptrace_scope`, Android). | H | M | The `shim` rung and local execution are the fallbacks; the probe reports the rung (D-32). | A prototype matrix over kernels, Docker, Podman, Ubuntu 24.04 and Android; `doctor` rows for each. |
| K-04 | Users read `confined`, `sandbox` or `private` as stronger than it is. `none` runs as the worker's uid. | H | M | Each level has a one-sentence statement of what it stops (D-70, D-73); a machine refuses by name (D-72); the report names the level that ran. | Check of the first sentence of each doc and help text; a test that each refusal names the level; `doctor --shield` output check. |
| K-05 | podswarm gets no repository and no session, so asks to podcrates wait. No ruling names podswarm, and the watcher reads only the title `(to podcrates)`, `(to all)` or the label `podcrates`. | H | M | Each ask has a fallback inside the podswarm repository (D-111); asks go as plain issues in `PodUtils/podcrates` until R-02 is answered. | R-02 answered; a first ask issue read by the watcher. |
| K-06 | The default shield `private` keeps owned directories such as `target/` in the work area (file 13), which is in memory, so a large build runs out of memory. The area is at most 50 percent of `MemAvailable`. | M | H | The area cap, a refusal by name, `trust = "own"` per machine, `--shield none` per run (D-71); from M2 the sealed store for a directory that does not fit (D-130, K-36). | A large Rust build and a large C build under `private` on an 8 GiB host; R-10. |
| K-07 | Spreading gives little speed-up on deep dependency graphs. A second member gives at most about 1.2 times on a typical `cargo build`; wide graphs gain close to linearly. | M | H | The 0.8 rule moves only a profitable exec (D-34); the documents promise no speed-up for every build. | Target A-24 on a wide C build; a `cargo build` with 2, 4 and 8 members; a report of the share of execs that moved. |
| K-08 | `sealed` is rarely available: few rented servers have SNP on in the BIOS, and no CI runner has SNP, so its live tests are manual. | M | H | `sealed` refuses by name; `private` and `guest` carry the first releases (D-74). | A manual attestation test on an SNP host before the milestone; a list of hosts that pass. |
| K-09 | `guest` under TCG (no KVM) is 3 to 21 times slower, and most rented virtual servers have no nested KVM. | M | H | The probe says whether KVM exists; `guest` refuses by name when the user forbids TCG (`--allow-tcg`). | A boot and build benchmark of `guest` with KVM and with TCG. |
| K-10 | The coordinator does not reach its throughput targets with the real wire, TLS and JSON cost. File 11, section 2, gives the throughput that the writer alone measured in a prototype. | M | M | Offers and results are batched; the store sits behind a `Store` trait (D-57). | Benchmarks B-01 and B-02 with the real schema and 1,000 simulated workers (A-01 to A-04). |
| K-11 | Numbers for tiny machines are unknown: idle memory, CPU for each task, binary size, fsync on SD cards. | M | H | Worker-only feature flags; the targets A-05, A-06, A-09 and A-16. | The same benchmarks on a Raspberry Pi 4 or 5 and a Cortex-A53 board. |
| K-12 | The first run on a machine with no podswarm is slow or fails: the binary is 10 MB, the home directory may be `noexec`, no directory may be writable. | M | M | Compressed copy, a ladder of install places, the probe step (D-11). | Target A-23 on a 20 Mbit/s link; Alpine busybox, Dropbear, a `noexec` home and an NFS home with 8 hosts. |
| K-13 | A Windows worker has no second holder of the fence: a suspended worker process does not end its attempts at the fence time. | M | M | A Job Object ends attempts when the worker exits; `at_most_once` needs a rung other than `session`. | A Windows test that suspends the worker for longer than the silence budget. |
| K-14 | A host with `KillUserProcesses=yes` in logind and no linger kills the far worker when the last login ends, so a cut road ends the session. | M | M | A `doctor` row; `systemd-run --user --scope` can escape it. | A live test on such a host. |
| K-15 | The coordinator needs a TCP listener, and some hosts deny `listen`. The listener clause is a rule of the asks of one tracker (podcrates issue 35) and does not bind podswarm by itself. | M | M | A session listens on nothing; `--listen` is explicit; the hub lets a coordinator dial out (D-112). | R-04 answered; a swarm test through a hub. |
| K-16 | One flow uses one uplink. "Aggregated" is per flow only until podnet plans bonding. | M | H | The policy names the member for each flow; the report says what carried a flow. | A throughput test of one large transfer and of many flows over two uplinks. |
| K-17 | A remote member of the `pool` policy sends flows through the authority, which costs two link hops and authority bandwidth. | M | M | Member check by shield (D-79); direct members first. | A transfer test through a remote member with the authority on a slow link. |
| K-18 | A tree with very many small files is slow on a link with a long round trip, because each blob has its own stream and a worker has 2 streams at once. | M | M | The view serves small files in batches; a pack form is a later change. | A benchmark of 100,000 small files at 100 ms round trip. |
| K-19 | HyperShell parity subtleties (token semantics, line handling, exit codes) make a user script behave differently. | M | M | The parity table (file 20); `{.}` and the exit rules are written down (D-107). | U-parity and U-gnu in M0 and M2 (A-17). |
| K-20 | podvm flags and behaviour change at any beta, and `guest` depends on it. The aarch64 interposer shipped in podvm `v0.2.0-beta.6`, so ARM is no longer a risk. cgroup flags stay refused. | M | M | A version range check; podvm runs as a program with a fallback in `podswarm-exec`. | A parity test of the `podvm probe` report at each podvm tag; podvm S23 (cgroup limits). |
| K-21 | Scale above 5,000 workers for one coordinator is not modelled, and descriptor limits may be 4,096. | M | M | `max_conns`, accept pacing, the hub multiplexes descriptors. | Benchmark B-06 with 5,000 and 10,000 idle connections (A-15). |
| K-22 | A fleet behind one NAT address trips the per-address pre-auth limits. | M | M | The limits count unauthenticated connections only, and they are settings. | A test with 500 workers behind one address. |
| K-23 | The disk of a tiny worker fills with outputs and task directories. | M | M | Caps, deferred cleanup, the disk reserve, `not_started` with reason `disk`. | A disk-full fault test on a worker. |
| K-24 | The claim that `memory.swap.max = 0` keeps tmpfs pages and zswap write-back out of swap is inferred. | M | M | `private` states that a root user who tries can still read the process. | The swap test: fill the area, apply pressure, read the swap device. |
| K-25 | New SNP attacks below the TCB floor make `sealed` unsafe, so the floor table needs an update for each release. | M | M | `shield_unavailable` with reason `tcb_below_floor`; `--seal-tcb-floor`. | A check of the floor table at each release; a watch on published attacks. |
| K-26 | The first release cannot do isolation, a pooled network, spreading or cells, so users with those needs bounce off. | M | M | The README states the scope; each later milestone is named. | The exit criteria of M1 and M2 (file 22). |
| K-27 | The coordinator is remote code execution on every worker by design. A stolen coordinator key owns the swarm. | H | L | Worker policy (D-95), per-worker keys, signed shapes later, the audit chain later. | The attack table X-nn tests (file 16); a test that a worker refuses a shape outside its policy. |
| K-28 | A hostile worker abuses the view: node id guessing, a write through a symlink, a write to `.git/hooks`. | H | L | Node ids as capabilities, no symlink follow, held writes (D-27, D-29, D-30). | The hostile-worker suite of file 23: each case is refused or held. |
| K-29 | Bundled C (SQLite, zstd) does not link static on every target (armv7, riscv64, i686, loongarch64, powerpc64le). | M | L | A `Store` fallback (redb); a static guard in CI for each target. | The static build guard on each target (R-05 for licences). |
| K-30 | The 1 percent clock drift margin and the prompt-kill assumption fail on some machines. | M | L | `grace_eff` is derived from `grace_s` and the drift bound; uninterruptible sleep is a stated residual. | The clock skew fault test with real clocks. |
| K-31 | ssh variants break the road: Dropbear and busybox allow one session per connection, `MaxSessions 1`, long macOS control paths. | L | M | Fallback to `ControlPath=none`; a short control path rule (D-12). | Live tests with `MaxSessions 1`, Dropbear and a macOS caller. |
| K-32 | Declared counts of named resources are not shared between two homes on one machine, so two homes oversubscribe it. | L | M | A coordinator keeps the counts for a swarm; a session says so in the report. | A test with two homes and one `gpu=1` machine. |
| K-33 | A stub repository of the org becomes a real project that overlaps (`podmesh`, `podcat`). | L | M | podswarm depends on none of them (file 02). | A read of the org repository list at each milestone. |
| K-34 | `pod-cas` and `pod-view` have no proven second consumer, so podcrates may keep them out. | L | M | The code stays in `podswarm-*` crates (P-12, P-17 fallbacks). | A consumer names a need; the ask is filed when M1 or M2 code shows the API. |
| K-35 | From M4 to M5 a coordinator listener has only the stage deadlines and the size cap before `ready`, so a flood can hurt it. | M | L | The M4 release notes state that a listener belongs on a trusted network; the full pre-auth limits ship in M5. | F-14 in M5. |
| K-36 | Under `private` a large build pays memory or FUSE speed: an owned directory that fits is in memory, and one that does not is served from the sealed store through FUSE with a seal on each write. | M | H | D-130 puts each owned directory where it fits and moves it after one `area_full`; `trust = "own"` (shield `none`) on a machine that only the user controls has neither cost. | E-36; B-21 with `target/` in the sealed store against the memory rung. |

## 2. Unknowns and how to settle each

| Unknown | Why it matters | How to settle it |
| --- | --- | --- |
| fsync rate and latency of SD cards and eMMC | durability defaults on small coordinators | B-01 on the device |
| coordinator CPU for each task and message with the real wire | A-01 to A-04 | B-02 profile |
| bytes for each idle worker connection, and the cost of a handshake storm after a restart | A-15, restart behaviour | B-06 |
| the overhead of a seccomp notification on tiny CPUs and old kernels | A-05, spreading | the exec benchmark of the prototype on a Cortex-A53 |
| how GNU make, cargo, ninja and a shell script behave with a fresh jobserver on a member | D-33 | a build test of each tool (A-24) |
| the share of target machines with Landlock ABI 3 or more | value of `confined` | `doctor` data from a real fleet |
| whether `pod-link` can change a window on a live link | D-17, ask P-4 | an experiment; the fallback sets windows at link start |
| whether the `sev` crate links static on musl with `crypto_nossl` | `sealed` | a CI link test |
| whether a SIGKILL of a foreground `podvm run` leaves the payload | `guest` and the `vm` boundary | a test with a sleeping payload |
| whether podvm gets a library call to boot the guest plan | D-74 | podvm ask; fallback: podswarm builds the QEMU arguments itself |
| whether `pod-ws` gets a `serve` module | `wss` roads, ask P-2 | the asks of file 21; fallback in `podswarm-net` |
| HyperShell and HyperQueue throughput on one machine | claims against peers | B-09 |
| how many users need a DAG | D-50 | feedback after M4 |
| how a Windows machine works as a far machine (`cmd.exe` probe, no `sh`) | platform order, R-06 | M10 with a Windows runner (E-33) |
| whether podvm has a call interceptor (syscall user dispatch or other) that the view or spreading can share | the trap of file 21 section 6.5; a view rung through podvm (file 06) | a read of the podvm source; until then no file relies on it |
| whether podcrates takes `pod-cas` and `pod-view` with no proven second consumer | asks P-12 and P-17 | the asks of file 21; K-34 |
| podcrates asks for `polled` limits and two probe rows | D-65 | file 21 asks; fallback in `podswarm-exec` |

## 3. Rulings that the owner gave

| Ruling | Content | Date |
| --- | --- | --- |
| Framing | podswarm and its crates serve as true parallel and distributed compute with no per-tool setup and no complex daemons, "used like `ssh` is": a system, a protocol, a single binary or a few. | 2026-11-12 |
| Answer 1, remote setup | Only a way in. If the user can reach a machine with ssh or any PodUtils road, it works. podswarm copies its binary on first use, runs it while needed and leaves no service. A long-lived agent is an option for machines that only dial out. | 2026-11-12 |
| Answer 2, file model | Both, live view first. The remote process sees the caller's directory through the link. Sync is the fallback for slow links and for hosts with no live view. | 2026-11-12 |
| Answer 3, pooling | A true single system image is a stated goal, on a ladder: exec-level spreading (main design, early), then a moving process, then pooled memory. One process lives on one machine at a time. | 2026-11-12 |
| Answer 4, protection from the host | Three levels, each with an honest statement of what it stops: leave little behind, a VM guest through podvm, a confidential VM with attestation. The tree names them `private`, `guest` and `sealed`. | 2026-11-12 |
| Answer 5, extending | No built-in "prompt plus agent" system. podswarm is pluggable so that agents use it themselves. It covers checkpoints and resume, and regions and placement with an identity valid across cells. | 2026-11-12 |
| Answer 6, network | The network of a run is a policy that podnet serves. The default is pooled, balanced and aggregated uplinks. An exit node is chosen on demand. | 2026-11-12 |
| Answer 7, first release | One command, remote: `podswarm run HOST -- cmd`, with a live view, the terminal and the exit code. Pools, batches and spreading follow. | 2026-11-12 |
| Static rule, toolchain, no compatibility (org) | Everything is statically compiled. C, zig and modern stable Rust are allowed, with edition 2024. A name, an API or a wire format can change in any version. | 2026-11-05 |

## 4. Rulings still asked

Each row has the question, the recommendation, what the design assumes until the owner answers, and what changes if the answer differs from the recommendation.

| Id | Question | Recommendation | Assumed until the answer | If the answer differs |
| --- | --- | --- | --- | --- |
| R-01 | Does the rule "no daemon" forbid a long-lived coordinator and the holder? | No: neither is a system service. | The coordinator is a foreground process that an operator starts. The holder ends after `hold_s` with no command and no attempt, as an ssh control master does (D-05, D-14). | Without a coordinator, only sessions exist: no durable queue, no workers that dial out. Without the holder, each command is its own home (`--no-hold` always), so roads and view indexes start cold and A-20 is at risk. |
| R-02 | May the repository `PodUtils/podswarm` and a session for it exist? | Yes: every ask of file 21 needs it. | Until the repository exists, each ask is a plain issue in `PodUtils/podcrates` in the form that podcrates uses for a new crate or a change (title `CRATE: what`; file 21, section 7). After it exists, a session of podswarm writes `COORD-NNN: subject (to podcrates)` in its own repository (file 02). | The tree stays a spec. No code is written, and the generic crates wait for one of the four consumers to need them. |
| R-03 | May the new crate names of file 21 (`pod-proc`, `pod-tty`, `pod-fuse`, `pod-cas`, `pod-view`, `pod-attest`, `pod-ssh`) be reserved in podcrates? | Yes: a second project can use each (file 21 section 6). | The code lives in `podswarm-*` crates until a name is accepted (ask P-21). | The code stays in `podswarm-*` for good, other projects cannot share it, and the asks of file 21 are cut. |
| R-04 | May a coordinator listen on TCP when the user gives `--listen`? | Yes, only on request. | A session listens on no TCP port unless the user gives `x --listen` or `x --launcher` (D-112), and a worker never listens. The listener clause belongs to the asks of one tracker and does not bind podswarm by itself. | The coordinator only dials out to a hub (file 24), so a swarm needs a hub host that can listen. A swarm on a LAN needs a relay, and `x --listen` goes. |
| R-05 | Are the licences of the bundled C code (SQLite, zstd, mimalloc, BLAKE3) and of the crypto provider acceptable under 0BSD and the static rule? | Yes: the static ruling allows C. | `cargo deny` and guard G-14 check the tree. | SQLite is replaced by a Rust store behind the `Store` trait (D-57), zstd by a pure Rust decoder at a speed cost, and the provider by the one the owner names. |
| R-06 | What is the platform order? | Linux first (musl), then macOS, then Windows. | The BSDs are best effort with no test. Far machines other than Linux come in M10. | The milestones of file 22 reorder. The first release scope changes if macOS or Windows comes first. |
| R-07 | The short alias `psw` collides with small tools on crates.io, PyPI, npm and nixpkgs. Keep it? | Keep it only as a user choice. | It exists only when the user makes it (D-08). The documents use `podswarm`. | Another alias or none. The examples of file 19 change. |
| R-08 | A batch with failed tasks exits 1, unlike HyperShell. Accept? | Yes: a script sees the failure. | `x`, `submit --wait` and `wait` exit 1 when a task did not succeed (D-104; the full table is in file 18). A script that needs 0 uses `|| true`. | `x` exits 0 for failed tasks, as HyperShell does, and a script reads the report. File 20 changes the verdict. |
| R-09 | `-N` defaults to the core count, unlike HyperShell. Accept? | Yes: a pool has more cores than one slot. | D-106. | `-N` takes the HyperShell default that file 20 names. |
| R-10 | Is the default shield `private` for every remote machine right? | Yes: a rented host may have other root users. | D-71. | The default shield is `none`, and the user asks for `private` for each machine or each run. A rented host with other root users has no protection until the user asks. |
| R-11 | May `podswarm run` with no HOST pick the caller's own machine? | Yes: a short command is faster at home. | The caller's machine is a candidate, and `--on` and `--local` force a choice (D-39). | `run` with no HOST needs a remote candidate and otherwise refuses with `needs_unsatisfiable`. |
| R-12 | Does podswarm take over `podssh each`? | No: one owner for each tool. | D-113. | `each` becomes a call of `podswarm x`, podssh keeps its road role, and files 02 and 20 change. |
| R-13 | Is the release flow acceptable: betas on GitHub releases of `PodUtils/podswarm`, a signed `SHA256SUMS`, no crates.io? | Yes: it is the flow of the org. | D-94, D-114, D-121. | Publishing on crates.io needs name reservation, and the git tag rule of the consumers changes for podswarm. |
| R-14 | May a hosted relay of the owner be a default road? | No: the user names a hub. | No relay is a default (D-112). | The default road list gains the relay, and the privacy statement of file 16 changes. |
| R-15 | Are asks of podswarm served before the work of podvm, podnet, podssh and podrunner? | No: each ask has a fallback. | No ask is on a critical path (file 21 section 7). | Asks move to the work order of podcrates once the owner adds podswarm to the consumers of its rules. |
| R-16 | What comes back from a remote run? | What git would see comes back; what git ignores stays on the anchor. | Paths that git ignores (`target/`, `node_modules/`) stay on the worker or the anchor, warm for the next run. A pull rule (`[view] pull`, or `--pull GLOB` for one run) brings one back at the end of the run, the verb `podswarm pull [HOST] PATH...` brings one back later, and the run prints one line that names the kept paths and their size (D-28). So `target/` does not appear on the caller's machine by itself. | Every written file comes back: the link carries build trees (A-22 and K-02 at risk), and files 01, 06 and 22 change. Or nothing comes back by itself: every result needs a pull rule. |

## 5. What would change the plan

* R-01 or R-04 answered against: the plan loses its coordinator or its listener. The design moves to a dial-out coordinator and a mandatory hub.
* B-02 below 1,500 tasks per second after tuning: replace the store behind the `Store` trait, or change the actor design, before M6.
* The exec prototype fails on common hosts (K-03): spreading becomes a Linux feature with the `shim` rung only, and the ladder claims shrink.
* The warm view misses A-21 on every rung (K-02): `sync` becomes the default rung and the live view moves to a later milestone.
* Landlock is missing on most target machines: `confined` is rare, and the `vm` boundary is the only strong boundary.
* podvm gets a library call: bring `guest` forward and drop the CLI spawn.
* podnet gets bonding: the policy `pool` gives true aggregation for one flow (K-16).
* An org relay role appears: drop the hub of file 24. A stub repository delivers `podnode`: the worker becomes a unit of it behind the enrolment seam.

## 6. Known gaps

Each line says what is not built, not measured or not checked, and what closes it.

* Nothing of podswarm is built. Every behaviour in files 04 to 24 is design. Milestones M0 to M2 of file 22 close it.
* No target number of file 23 is measured on podswarm code. The coordinator numbers come from a prototype of the writer thread with no wire cost; each `A-nn` closes with its benchmark.
* The cost of exec takeover is measured in a prototype on one 4-vCPU VM only. The exec benchmark on a Cortex-A53 and an older kernel closes it.
* The FUSE overhead range (0 to 83 percent) is from outside measurements. The warm-build benchmark of A-21 closes it.
* The view, the spreading protocol and the stub exist only as design and prototype sources. The milestones of file 22 close each.
* The stated goals of step 2 and step 3 of the ladder (CRIU, guest migration, far heap) have no prototype. One experiment for each, before the milestone of file 22.
* `sealed` has no live test. A manual attestation test on an SNP host closes it.
* The `sev` crate on musl is not linked. A CI link test closes it.
* The swap behaviour of the `private` work area is inferred. The swap test of K-24 closes it.
* The `pod-ws` `serve` module, the `polled` limit mode and the probe rows are asks, not code. File 21 holds each with its fallback.
* podvm cgroup flags stay refused and the probe schema waits for podcrates T-107. The podvm asks of file 21 close them.
* A Windows far machine and a Windows second fence holder are not designed (K-13). M10 closes them.
* macOS has the `session` rung only and the `shim` rung for spreading. A macOS runner and its tests close it.
* The reverse roads of `pod-relay` are named but not designed in detail. M5 and M9 close it.
* The placement of one command uses an estimate with a default for unknown programs. The placement benchmark of file 23 closes it.
* The aggregation of one flow over several uplinks is not built in podnet (K-16). A podnet ask closes it.
* No pack form exists for many small files (K-18). A later change closes it.
* The licences of the bundled C code and of the dependency tree are not checked. `cargo deny` in CI and R-05 close it.
* The simulation of file 23 does not model time arithmetic (`grace_eff`, `rtt_max`). The clock skew fault test closes it.
