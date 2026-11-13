# 28. Prior art

This file lists the tools and systems that podswarm is compared with. They are grouped by the face of podswarm that they touch: one command with the caller's files, a process tree over many machines, many commands, protection from the host, and agent interfaces. Each entry has a link, what it does in one line, and what podswarm takes from it or does differently. File 01 has the first use case that the entries are measured against. File 06 (view), file 07 (spread), file 13 (shield) and file 17 (extending) own the designs that borrow from these tools. File 20 has the HyperShell feature list.

The links go to a home page or a repository. This file gives no star counts. A fact that a reader can doubt carries an `[EV-nnn]` tag (resolved in `evidence/facts.md`). A statement with no tag is a design position of podswarm, or common knowledge about the tool that section 7 lists as not read.

## 1. One command on another machine with the caller's files (the `run` face)

The first use case of file 01 has five needs. A tool that meets one of them and fails another does not cover the case by itself.

| Short name | Need |
| --- | --- |
| N-one | works for any command, not for one tool |
| N-root | needs no root and no daemon on the far machine |
| N-lazy | moves only the files that the command reads |
| N-host | protects the run from other root users of the far machine |
| N-many | the same interface reaches one machine and later many |

### 1.1 Live view of the caller's files

| Tool | What it does | Why it does not cover the case alone | What podswarm keeps or changes |
| --- | --- | --- | --- |
| [Plan 9 `cpu`](https://9p.io/magic/man2html/1/cpu) | A remote shell sees the terminal's name space at `/mnt/term`. [EV-127] | Needs Plan 9 name spaces and 9P in the kernel. One machine. No host protection. | The model: the caller serves the files, the far process asks. The view of file 06 (D-25, D-27). |
| [u-root `cpu`](https://github.com/u-root/cpu) | The same model for Linux over ssh: the client is the 9P server and the far side mounts it. [EV-128] | The far side mounts 9P, which needs real root (9p has no user-namespace mount flag). Its docker example runs `--privileged`. One machine. | The client is the file server, and no inbound port. podswarm adds FUSE in a user namespace, a trap rung and a sync rung for hosts with no root, and a deny list (file 06; D-30). |
| [outrun](https://github.com/Overv/outrun) | Runs a local command on another Linux machine with the caller's whole root file system through FUSE and chroot. [EV-129] | Needs root on the far side and Python. Exports the whole `/`. One command, one machine, no protection from the host. | Prefetch of the program's input set, a persistent cache, the same-architecture rule. podswarm exports one root and not `/` (file 06). |
| [sshfs](https://github.com/libfuse/sshfs) | Mounts a far directory locally over sftp. With a reverse mount the far machine can see a local directory. | A file system and not a run: no process start, no terminal, no exit code. A reverse mount exports whatever the sftp server reaches. | The idea that the transport is the ssh the user already has. podswarm adds the run, the export rules and the write-back rules. |
| [mirrord](https://github.com/metalbear-co/mirrord) | Runs a local process against a live Kubernetes cluster: traffic, files and environment come from a target pod. [EV-130] | The direction is the reverse of the first use case: the process stays local and borrows the cluster's context. Needs a cluster. | It is the same layer trick (file calls of a process answered by another machine), pointed the other way. podswarm answers file calls from the caller. |
| SunOS `on` | Ran a command on a remote host in the caller's environment, with the working directory reached over NFS. | Needs NFS and trusted hosts. One machine. No host protection. | The oldest form of "run there, files from here". podswarm does it with no mount on the far side that the host admin must allow. |

### 1.2 Send the tree, run, fetch the result

| Tool | What it does | Why it does not cover the case alone | What podswarm keeps or changes |
| --- | --- | --- | --- |
| [errand](https://github.com/lydakis/errand) | Sends the working tree with uncommitted edits to another machine of the user, streams logs, returns the exit code. [EV-131] | Installs a runner service on the far side (N-root). Moves the tree before the run (N-lazy). Git-ignored directories do not travel. No host protection. One machine. | The fetch with a conflict check. podswarm is the sync rung of file 06, behind a live view, and it leaves no service. |
| [kran](https://github.com/hafencity-dev/kran) | Runs heavy jobs on whichever of the user's machines has room, over ssh, with the same output and exit codes. [EV-132] | Moves a file set (git-listed) per job. No live view. No host protection. | The manifest with a stat-keyed hash cache, the same absolute path, an environment deny list. podswarm adds the live view first and lazy fetch by directory (file 06). |
| [rch](https://github.com/Dicklesworthstone/remote_compilation_helper) | A hook of a coding agent that recognises build and test commands and runs them on remote workers with rsync over ssh. [EV-133] | Knows named build tools (N-one fails). Moves the tree. No host protection. | The rule that a command that is unsafe to move runs locally. podswarm has no list of tools. |
| [cargo-remote](https://github.com/portlandhodl/cargo-remote) | Builds a Rust project on a server over a built-in ssh client with an in-process rsync delta, and copies the binaries back. | One tool (cargo). Moves the tree. No host protection. | Delta transfer of changed files, for the sync rung. |
| [crunch](https://github.com/liamaharon/crunch) | A `cargo` replacement that sends Rust compilation to a remote server named by an ssh host entry. | One tool (cargo). One machine. | Use of the user's ssh host entries. podswarm reads `~/.ssh/config` only when the user imports it (file 08). |
| [remote-runner](https://github.com/npp-zep/remote-runner) | Builds a project with a remote toolchain: rsync of the sources, a remote build command, live output, a pull of the products. | A build wrapper. Moves the tree. One machine. | The live output and the pull of products as one command for a user with a weak device. |
| [mutagen](https://mutagen.io/) | A continuous two-way file sync between machines. [EV-134] | A sync and not a run. It keeps a copy of the whole tree on both sides, and it has an agent on the far side. | The conflict rule (keep both, lose no data) for the write-back log of file 06 (D-29). |

### 1.3 Build farms with a content-addressed input root

| Tool | What it does | Why it does not cover the case alone | What podswarm keeps or changes |
| --- | --- | --- | --- |
| [Nix remote builders](https://nixos.org/manual/nix/stable/advanced-topics/distributed-builds) | Build a derivation on another machine over ssh after the inputs are copied to its store. | Needs Nix on both sides and a derivation. One tool. The builder must be trusted. | The ssh road and the idea of copying only the inputs that the far side lacks. |
| [Bazel Remote Execution API](https://github.com/bazelbuild/remote-apis) | An action names an input root as a Merkle tree of canonical `Directory` messages. The service runs it with a content-addressed store. [EV-135] | Needs a build system that declares its inputs. The service is a daemon. No view of the caller's live tree. | The Merkle directory index and the missing-blob query. The id is BLAKE3 (file 15; D-80). podswarm does not need a declared input list: the view finds the inputs by access. |
| [EdenFS](https://github.com/facebook/sapling/blob/main/eden/fs/docs/Overview.md) and [bb_clientd](https://github.com/buildbarn/bb-clientd) | Lazy loading of a large tree by FUSE on Linux, NFS on macOS, ProjFS on Windows (EdenFS). Lazy loading of content-addressed directories (bb_clientd). [EV-136] | They serve a stored tree and not a live local tree. Daemons. | Lazy listing, content hashes served without a read, a later macOS and Windows plan. |

### 1.4 What the tools of this section share

* No tool of this section protects the run from the far machine. Outrun and u-root `cpu` warn the user to use only machines that the user trusts. [EV-137]
* The tools that need a daemon or root on the far side fail the owner's own host: other users have root there, and a service of one user is not wanted.
* The tools that move the whole tree fail on a large tree over a slow link. A build directory of ignored files stays on the far side in podswarm (file 06; D-28).
* The first release of podswarm (D-07) is one command on one machine over ssh, so the five needs apply to that case only. The same command line later reaches a pool (file 08) and spreads (file 07).

## 2. A process tree over many machines (the spread face)

### 2.1 Compile farms and build helpers

These tools spread one kind of work. File 01 excludes a compiler helper as a goal. podswarm borrows ideas only.

| Tool | What it does | What podswarm takes or does differently |
| --- | --- | --- |
| [distcc](https://github.com/distcc/distcc) and [icecream](https://github.com/icecc/icecream) | Spread C and C++ compiles. A wrapper is named for the compiler. icecream prefers the local machine when it is free. [EV-138] | The local-preference rule: a process moves only when its expected finish time on a member is under 0.8 of the local one (file 07; D-34). No wrapper by name: the exec is caught for any program. |
| [sccache](https://github.com/mozilla/sccache) with distributed mode | A compiler cache with an icecream-style scheduler, build servers and clients (docs/Distributed.md in the repository). | The token mode shares one secret, so podswarm gives each worker its own key (file 16; D-89, D-90). A build server can return bad output, so results of workers are data and not trusted (file 16). |
| [reclient](https://github.com/bazelbuild/reclient) | A client that sends compile actions to a Remote Execution API service. | Needs a declared action and a service. podswarm needs neither. |
| [opticc](https://github.com/ShowMeTheStack/opticc), [nocc](https://github.com/VKCOM/nocc), [Wuild](https://github.com/mapron/Wuild) | Distributed C and C++ compilers in the manner of distcc. opticc ships only the headers that a worker lacks. | Ship only what the far side lacks (file 06). Each is one tool. |
| [Brokkr](https://github.com/jackthepunished/brokkr) | A Rust build and compute grid that speaks the Remote Execution API, with leases and per-tenant fair queuing. | podswarm defines its own wire (file 05). The lease and fair-queue ideas are in files 09 and 10. |
| [gg](https://www.usenix.org/conference/atc19/presentation/fouladi) | Thunks in a content-addressed store, with PATH stubs that are model programs per tool. Inkscape in 87 s on Lambda against 7 minutes with icecc on 384 cores. [EV-139] | Content-addressed inputs and the warning about the serial tail (link and archive). podswarm rejects a model per tool. |
| [firebuild](https://github.com/firebuild/firebuild) | Caches any command of a process tree with an LD_PRELOAD interposer. [EV-140] | The cost class of interception. podswarm copies no code from it. |
| [GNU make jobserver](https://www.gnu.org/software/make/manual/html_node/POSIX-Jobserver.html) | Shares a job count between `make` processes through a pipe or a fifo (`R,W` and `fifo:PATH`). | podswarm replaces the jobserver by a fresh one on each member, and answers a CPU-count query with the pooled core count (file 07; D-33, D-36). |

### 2.2 Single system image systems

| System | What it achieved | Why it ended or lasted | What podswarm takes |
| --- | --- | --- | --- |
| Sprite (1980s to 1990s) | Transparent process migration. `pmake` ran compiles on idle hosts. Speed-ups of two or three, up to five or six. [EV-141] | A small team could not follow Unix changes. The authors saw too few applications other than `pmake`. | Move a process at exec time: it is cheap. The home keeps the identity. |
| MOSIX and openMosix | Migration with a home node and a deputy that forwards system calls. MOSIX 4 runs in user space with 1.1 percent measured slowdown. [EV-142] | openMosix ended in 2008. The stated cause is less need for single system image clusters as multi-core CPUs became cheap. [EV-143] | Forwarding every call suits compute-bound work only. podswarm forwards stdio and signals and serves files by the view. |
| Kerrighed and OpenSSI | Kernel single system image with distributed shared memory and migration. | Ended with their kernel versions. | A kernel patch is not an option: there is no root. |
| [Popcorn Linux](https://www.popcornlinux.org/) | Migration across instruction sets in a replicated kernel. | Research. Needs compiler support for migration points. | podswarm does not migrate across instruction sets. A move needs the same CPU architecture and operating system. |
| Condor standard universe | Remote system calls to a shadow process at the submit host and transparent checkpoints. | The package ended with HTCondor 8.9.7: it needed a relink of each program. [EV-144] | No relink and no per-program setup. |
| Incredibuild | Exec-level spreading on Windows: it intercepts process creation, runs the child on a helper and virtualizes its file calls. [EV-145] | A commercial product that lasts. It needs an installed agent. | The closest product to step 1 of the ladder. It shows that exec-level spreading with a virtual file view works at scale. |

Five lessons bind file 07 (D-32, D-37). Kernel single system image systems ended with their kernels, so only user space lasts. The exec is the cheap moment to place a process. Per-tool knowledge is what users reject. A serial tail caps the gain. The systems that last intercept process creation and virtualize files. They do not move memory.

### 2.3 Checkpoint tools for the later steps

| Tool | What it does | What podswarm takes |
| --- | --- | --- |
| [CRIU](https://criu.org/) | Checkpoint and restore of a process tree in the kernel. It needs `CAP_CHECKPOINT_RESTORE` or a user namespace that the caller owns. | The second rung of step 2 for a process that podswarm started inside its own user namespace (file 07). |
| [DMTCP](https://github.com/dmtcp/dmtcp) | Checkpoint of process trees in user space with LD_PRELOAD. | A candidate for a program that CRIU cannot hold. Its licence needs a check before use. |

## 3. Many commands (the batch face)

### 3.1 Peers by group

HyperShell is the reference of the batch face (file 20). podswarm differs from each peer in one stated way.

| Tool | What it does | What podswarm takes or does differently |
| --- | --- | --- |
| [HyperShell](https://github.com/hypershell/hypershell) | A Python utility for shell commands over a distributed queue, with SQLite or PostgreSQL. Its workers can pull since 2.9. [EV-146] | The same one-liners, in Rust, as one file (D-106). The differences are outbound-only workers, a static binary, and leases with fencing. |
| [HyperQueue](https://github.com/It4innovations/hyperqueue) | A Rust server, worker and CLI in one static binary for HPC. Task arrays with a shared template, worker time limit read from Slurm or PBS, an idle timeout, an event journal. [EV-147] | Arrays with a shared template, a worker time limit and an idle exit, a journal for recovery on one machine (files 09 and 10). Its workers must reach the server port, and podswarm workers dial out on 443. |
| [GNU parallel](https://www.gnu.org/software/parallel/) | A Perl job runner with `--sshloginfile`, `--joblog`, `--resume` and `--retries`. [EV-148] | The joblog and resume ideas (D-108). podswarm avoids the `:::` mini-language and any `eval` in templates (D-107). |
| [xargs](https://www.gnu.org/software/findutils/) | Builds command lines from input, with `-P` for local parallelism. | The baseline of speed for local fan-out. |
| [rust-parallel](https://github.com/aaronriekenberg/rust-parallel) | A Rust local job runner. [EV-149] | The local mode of `podswarm x` must be at least as fast. |
| [rush](https://github.com/shenwei356/rush) | A Go job runner with retry, a record file for continue, and a timeout that kills the child tree. | Resume from a record file with no database. |
| [pueue](https://github.com/Nukesor/pueue) | A Rust daemon and CLI for a persistent queue on one machine, with groups, pause, `wait` and a callback. | A persistent single-host queue needs `wait`, groups and a callback. They are cheap. |
| [Slurm](https://slurm.schedmd.com/) job arrays | One job record with an index and a `%N` throttle. [EV-150] | A per-run cap of running tasks like `%N`. A scheduler for batch jobs is three orders of magnitude below a pull queue. |
| [HTCondor](https://htcondor.org/) | Matchmaking with glideins: pilot jobs start workers that report to the pool. A broker or port ranges serve firewalls. | A worker is a pilot with a lifetime and an idle exit. podswarm needs no broker, because a worker dials out. |
| [BOINC](https://boinc.berkeley.edu/) | Volunteer computing: pull, replicated results, a validator. | Replication costs more than it gives on trusted machines. A verify hook is a later item (file 24). |
| [Work Queue and TaskVine](https://cctools.readthedocs.io/) | A manager, workers that connect to it, files cached on workers by name. | A cache by hash with LRU. Peer transfers are not taken: they need inbound reach. |
| [Parsl](https://parsl-project.org/) and [Globus Compute](https://www.globus.org/compute) | Python function executors. Globus Compute endpoints use outbound HTTPS and AMQPS on 443. [EV-151] | The design of workers that dial out. podswarm ships commands and not Python functions. |
| [Dask](https://distributed.dask.org/), [Ray](https://www.ray.io/) | Python task schedulers. | Not taken: code changes. A task of under about 100 ms does not gain from a remote start, which is why `local_under_ms` exists (file 08). |
| [Celery](https://docs.celeryq.dev/), [RQ](https://python-rq.org/), [Faktory](https://github.com/contribsys/faktory) | Brokers and workers. RQ has a `--burst` worker that exits when the queue is empty. Faktory reserves a job for 30 minutes and requeues it if it is not acknowledged. | The burst worker is the model of a worker for a throwaway run. A long reservation default is acceptable to users. |
| [Nomad](https://developer.hashicorp.com/nomad) | Batch, system and sysbatch jobs. sysbatch runs a command on every client that meets the constraints. | `podswarm each` is the form of sysbatch (file 09, file 18). |
| [Temporal](https://temporal.io/) | Workers poll task queues, and poll only when they have spare capacity. | The credit rule of the pull (file 10; D-51). |
| [NATS JetStream](https://docs.nats.io/nats-concepts/jetstream) | Pull consumers with explicit ack, `ack_wait` and `max_ack_pending`. | The ack and redelivery model. podswarm does not act as a broker. |
| [GitHub Actions runner](https://github.com/actions/runner) and [Buildkite agent](https://buildkite.com/docs/agent) | Agents that poll an HTTPS API with labels, with an ephemeral mode of one job. | Tags with a queue, and the ephemeral worker. |
| [K3s](https://k3s.io/) and [Mender](https://mender.io/) | An agent registers over a WebSocket that it opens (K3s). A client polls the server (Mender). | The pattern of an agent that dials out. |
| [dispy](https://dispy.org/) and [parallel-ssh](https://github.com/ParallelSSH/parallel-ssh) | A Python scheduler with node servers. An async ssh client for very many hosts. | The result journal for a client that crashed. parallel-ssh is the baseline for a parallel bootstrap. |
| [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) | Indexed jobs with `backoffLimitPerIndex` and `podFailurePolicy`. | A failure policy that names exit codes which do not retry. |

### 3.2 Comparison table

Columns: model, transport, store, static binary, reach (outbound-only or road-based), throughput claim with its conditions, licence. "n/s" means the project states no figure. "(not read)" means the licence comes from common knowledge.

| Tool | Model | Transport | Store | Static binary | Reach | Throughput claim and conditions | Licence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HyperShell 2.8.7 and 2.9.0a7 | server pulls from a database; clients ask for work (2.9) or the server pushes (2.8) | TCP with Python managers, TLS since 2.8.0, shared key | SQLite, PostgreSQL, Timescale, memory | no (Python 3.11 or later) | no: the server port 50001 must be reachable; a relay exists in 2.9 | 129 tasks/s at bundle size 1 with 256 clients, TLS, SQLite, 16 CPU, 2.8.3 [EV-152] | Apache-2.0 |
| HyperQueue 0.27.0 | server with work stealing, workers | TCP, encrypted with a secret file | journal file, no database | yes, Linux only | no: workers connect to the server host and port | about 0.1 ms of overhead per task (FAQ) | MIT |
| GNU parallel | local scheduler with ssh fan-out | ssh | joblog file | no (Perl) | ssh from the submitter | 3 to 10 ms per job; `--fast` about 0.1 ms, local only | GPL-3.0-or-later (not read) |
| xargs -P | local | none | none | yes | local | 49.0 ms for 100 echo, -P8, M2 | GPL (not read) |
| rust-parallel 1.24.0 | local | none | none | yes | local | 28.4 ms for 100 echo, M2 | MIT |
| rush | local | none | record file | yes (Go) | local | n/s | MIT |
| pueue | daemon and CLI, one machine, groups | Unix socket or TCP | state file | yes | local | n/s | Apache-2.0 |
| Slurm | central controller, job arrays | munge | accounting database | no | inbound to nodes | 500 simple jobs/s sustained, tuned, admin guide | GPL (not read) |
| HTCondor | matchmaking, glideins | TCP, broker for firewalls | job queue log | no | partly: broker or port ranges | n/s | Apache-2.0 |
| BOINC | pull, replication, validator | HTTP | MySQL | client no | yes: client polls | n/s | LGPL-3.0 |
| Work Queue and TaskVine | manager, workers, file cache | TCP | memory | no | no: manager must be reachable | n/s | GPL-2.0 (not read) |
| Parsl HTEX | Python executor | ZeroMQ | none | no | no | 1,181 tasks/s with 50,000 no-op tasks; 65,536 workers on 2,048 nodes (2019) [EV-153] | Apache-2.0 |
| Globus Compute | cloud service and endpoints | HTTPS and AMQPS on 443 | cloud | no | yes: outbound 443 | n/s | Apache-2.0 |
| Dask distributed | scheduler, workers | TCP | memory | no | no | about 1 ms per task | BSD-3-Clause |
| Ray | distributed scheduling | gRPC | GCS | no | no | 100,000 tasks of 0.1 ms took 27.46 s remote against 13.37 s sequential (Ray documentation) | Apache-2.0 |
| Celery and RQ | broker and worker | AMQP or Redis | broker | no | broker reachable from workers | n/s | BSD (not read) |
| Faktory | work server | TCP | RocksDB | yes (Go) | no | n/s | open core, no SPDX id |
| Nomad | server and clients; batch, sysbatch | RPC, clients dial the servers | Raft | yes (Go) | clients dial out; servers need inbound | n/s | BUSL-1.1 since 2023 (not read) |
| Temporal | task queues, long poll | gRPC | database | server no | yes: worker polls | n/s | MIT |
| GitHub runner and Buildkite agent | long poll of an HTTPS API | HTTPS | cloud | yes (Go agent) | yes | n/s | MIT |
| NATS JetStream | pull consumers | NATS | file or memory | yes | clients dial out | n/s | Apache-2.0 |
| K3s agent and Mender client | agent registers over a WebSocket; client polls | WebSocket, HTTPS | etcd or SQLite; cloud | yes (K3s) | yes | n/s | Apache-2.0 for K3s |
| dispy | Python scheduler, node servers | TCP, optional SSL | none | no | no | n/s | no SPDX id |
| parallel-ssh | async ssh client | ssh (libssh2) | none | no | ssh inbound | "hundreds to hundreds of thousands" of hosts, no rate | LGPL-2.1 |
| podswarm | authority (home or coordinator), pull workers, leases | ssh, `exec:` roads, or WebSocket over TLS 1.3 | SQLite WAL (swarm); memory (session) | yes on musl | yes: only a way in, or outbound 443 | [T] at least 20,000 tasks/s at `strict` (A-01, file 23) | 0BSD |

The comparison for a reader who knows HyperShell 2.9 is one sentence. Where HyperShell 2.9 has a feature already (client-requested bundles, zones, relay, `--from-json`, TLS), the difference of podswarm is outbound-only reach, a static binary, and leases with fencing.

### 3.3 The name check

`podswarm` has no entry on crates.io, PyPI, npm or Repology, and no GitHub repository with that name. The alias `psw` is taken on crates.io, PyPI, npm and in Nixpkgs by unrelated tools. [EV-087] File 18 owns the rule: the docs and the scripts use the full name.

## 4. Protection from the host

| System | What it does | What podswarm takes or does differently |
| --- | --- | --- |
| AMD SEV-SNP | Encrypts guest memory, protects its integrity, and signs an attestation report. [EV-155] | The first backend of shield `sealed` (file 13). The caller attests the guest before it sends a file or a key. |
| Intel TDX | A confidential guest with a quote from a quoting enclave. [EV-156] | The second backend of `sealed`. It needs a quote generation service on the host, so it follows SNP. |
| Arm CCA | A confidential realm on Arm. | Not usable: the KVM host support is still a patch series. [EV-157] |
| Enclaves (SGX with Gramine or Occlum) | A process inside an enclave. | Not a rung: a build starts a process per crate, and each costs a new enclave. Gramine emulates `fork` by checkpoint and restore into a new enclave. [EV-158] |
| Cloud confidential VMs | A confidential guest that a cloud provider runs. | A rented cloud VM does not launch its own confidential guest in general: AWS and GCP give no nested virtualization on their confidential types. [EV-159] A cloud confidential VM can be a `sealed` host when the user is its only root (a later mode). |
| [podvm](https://github.com/PodUtils/podvm) | A VM guest with no root on the host, with rungs from supervise to emulate. | Shield `guest` (file 13). |
| `ssh` with `ForwardAgent` and a shared home | The user's credentials on a shared host. | A rule at every shield level: no agent forwarding, no credential file served by the view, no secret variable passed (file 13; D-75). |

None of the peers in sections 1, 2 and 3 protects the task from the host. Each assumes a trusted machine, a trusted cluster, or (BOINC) a replicated result. podswarm states, for each level of shield, what it stops and what it does not (file 13; D-70, D-73, D-74). One sentence of file 13 holds: `private` and `guest` protect against curiosity and leftovers, and only `sealed` protects against a root user who wants the data.

## 5. Agent and plugin interfaces

| Mechanism | What it is | What podswarm takes |
| --- | --- | --- |
| [Model Context Protocol](https://modelcontextprotocol.io/) | JSON-RPC 2.0 with two standard transports: stdio and Streamable HTTP. Tools have an `inputSchema` and results have `structuredContent`. [EV-160] | `podswarm mcp` over stdio only, with a capability profile (file 17; D-97). No HTTP transport in the core. |
| `SKILL.md` and `llms.txt` | A skill is a Markdown file with front matter `name` and `description`. `llms.txt` is an index for models. A quick card gives a first call, failures with a retry class, headers, a version and a not-for list. [EV-161] | `podswarm skill` prints a `SKILL.md` generated from the same tables as the CLI, with the exit-code table and a version hash. A golden-file test keeps it equal (file 17). |
| Git and cargo external subcommands | `git foo` runs `git-foo` found on `PATH`. `cargo foo` runs `cargo-foo`. | `podswarm NAME` runs `podswarm-NAME` (file 17). |
| [kubectl plugins](https://kubernetes.io/docs/tasks/extend-kubectl/kubectl-plugins/) | An executable named `kubectl-NAME` on `PATH`. `kubectl plugin list` walks `PATH`. | `podswarm plugin ls`, and no install command. |
| Docker CLI plugins, Terraform providers, Nomad task drivers | A plugin is a separate process. Docker asks it for metadata. Terraform and Nomad speak RPC to it after a handshake. | Out-of-process plugins over JSON lines on stdio, not gRPC (file 17; D-100). |
| Signed webhooks and event streams | The platform signs a POST with a key that the receiver fetches. A client can also pull events from a sequence number. [EV-162] | Both push and pull of events. The signed-document form is the `{doc, key, sig}` form of `pod-relay` (file 16). |
| A hosted agent platform | Federated Git hosting with captured agent sessions as checkpoints, runners with a per-run identity, and regional cells. | podswarm has no built-in agent or prompt system. It gives checkpoints with content ids (file 15), cells and organisation statements (files 08 and 16), a run identity token (file 17; D-98), and the interface above, so that an agent can use podswarm (D-06). |
| [HTCondor self-checkpointing](https://htcondor.readthedocs.io/en/latest/users-manual/self-checkpointing-applications.html), Slurm `--signal`, Kubernetes `preStop`, AWS Spot notice | A program exits with a chosen code, or gets a signal before its end, and saves state. [EV-163] | The three triggers of a checkpoint: an exit code, a call, and a signal with a grace period (file 15; D-85). A two minute spot notice caps the grace. |

## 6. Papers

| Paper | Use in this spec |
| --- | --- |
| Geoffrey Lentner and Lev Gorenstein. The HyperShell paper on distributed task execution for HPC. PEARC '22, 2022. [10.1145/3491418.3535138](https://doi.org/10.1145/3491418.3535138) | The batch face: overhead of a pull queue, and why sites do not allow many small jobs. |
| Sadjad Fouladi and others. From Laptop to Lambda: Outsourcing Everyday Jobs to Thousands of Transient Functional Containers (`gg`). USENIX ATC 2019. [page](https://www.usenix.org/conference/atc19/presentation/fouladi) | Content-addressed inputs. The serial tail. Model programs per tool as a design to avoid. |
| Jeffrey Dean and Sanjay Ghemawat. MapReduce: Simplified Data Processing on Large Clusters. OSDI 2004. | Backup tasks for stragglers. The base of speculation (file 24; D-101). |
| Fred Douglis and John Ousterhout. Transparent Process Migration: Design Alternatives and the Sprite Implementation. Software: Practice and Experience, 1991. | Exec-time migration is cheap. The home keeps the identity. The NASA report in section 2.2 gives the numbers. |
| Amnon Barak and others. The MOSIX white paper. | A home node and system call forwarding in user space. |

The first two papers have pages that the reports read. The MapReduce, Sprite and MOSIX entries come from citations on pages that the reports read.

## 7. What this file does not establish

* The reports read each repository at the start of its README, with searches for terms. The file claims no feature, maturity or speed beyond the passages cited.
* The classes in section 1 are positions of this spec. They are not checked against the source code of each tool.
* Described from common knowledge and not read on 2026-11-12: SunOS `on`, sshfs, Nix remote builders, distcc, reclient, xargs, DMTCP licence, CRIU limits, the licences marked "(not read)", the Nomad licence change, Docker CLI plugins, Terraform and Nomad plugin RPC, the citation details of the MapReduce, Sprite and MOSIX papers.
* Throughput figures of different tools use different tasks, machines and years. The table does not rank them. A figure of podswarm is a target `[T]` until the benchmarks of file 23 run.
* The hosted agent platform is known from an archive of its public surface. No live service is read.
* The Repology route of the forge service and the Debian source API gave no answer to the name check. Other package systems are not checked.
