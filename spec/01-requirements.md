# 1. Requirements

This file states what podswarm must do and must not do, in the owner's words first. It gives the use cases, the goals, the non-goals, the single system image ladder and the headline targets. File 03 gives the architecture that answers them. File 26 lists the questions that stay with the owner.

## 1. The owner's words

The first statement:

> "do what hypershell does but in rust, and be machine agnostic, serve for both one-off random/throwaway job/script/tool & also for long running persistent jobs and also for dividing/using compute from a cluster of tiny low spec machines to achieve very high throughput; it will not be a generic yet another sccache or compiler helper, it will be a general purpose true distributed compute"

The frame:

> "podutils has solved networking, it is also solving vms/containers, cicd etc. what is lacking here and tbh elsewhere is a general tool that can do parallel/distributed computing. think: anywhere i can access via ssh or whatever that podutils allow, and any resources i can use (cpu, network, memory etc) should be able to be shared/used/pooled seamlessly for any cmd/tasks/scripts as if the whole system behaved as a whole"

> "i want podswarm and related crates to serve as true parallel/distributed computes that don't require per tool setup or complex daemons/hpc systems, and can be used like `ssh` is, a system, a protocol, a single binary or a few, that allow remote access, but in our case the access is compute itself"

The first case to serve. A developer has a weak PC and a strong server. Other people have root on that server. They are not hostile, but the developer does not want to depend on that. The developer works on the PC and wants a command such as `cargo build` to use the processors of the server, while the files and the tools of the work stay on the PC. A port forward, a remote editor or a codespace is not the answer, because it moves the work to the server. The command must run in a way that the other users of the server cannot easily watch or change. Later the same command must spread over several machines to build a larger program.

## 2. What podswarm is

podswarm is to compute what `ssh` is to a login: one binary and one protocol that give the use of the processors, the memory and the network of any machine the user can reach. The user does not install a cluster. The user does not adapt a tool. A command runs on other machines as if they were part of the user's own.

It has three faces on one core:

| Face | Command | What it is for |
| --- | --- | --- |
| One command | `podswarm run [HOST] -- CMD` | Run a command now on a better machine, with the caller's files, terminal and exit code. |
| Many commands | `podswarm x`, `podswarm submit` | Run a list of commands over a pool. This is the HyperShell face. |
| Long work | queued runs, services, checkpoints | Work that outlives the caller: a coordinator keeps it, and it resumes after a loss. |

## 3. Use cases

| Id | Who | Case | Needs most |
| --- | --- | --- | --- |
| U1 | The owner | `podswarm run bigbox -- cargo build` from a weak PC on a rented server where other people have root. The files stay on the PC. | a live view of the directory, the terminal, shields, nothing left on the server |
| U2 | A developer | The same build spreads over several machines: each compiler that `cargo` or `make` starts runs where a core is free. | exec-level spreading with no change to the build tool |
| U3 | A researcher | `ls *.mp4 \| podswarm x 'ffmpeg -i {} {/-}.webm'` on a laptop and three machines reached by ssh. | zero setup, HyperShell one-liners, exit codes that scripts can use |
| U4 | A homelab owner | 30 small boards and old phones run short tasks at a high rate. Many cannot be dialled. | a small worker, low cost per task, weak links, workers that dial out |
| U5 | A team | 40 desktops share queued sweeps and nightly work. | a coordinator, a durable store, priorities, quotas, backup |
| U6 | A data engineer | 200 crawlers must stay alive for weeks. | service jobs, restart rules, survival of a coordinator restart |
| U7 | An agent | A coding agent offloads its own commands and long runs to a pool, saves checkpoints, and resumes on another machine. | a machine interface, checkpoints and resume, a run identity |
| U8 | An organisation | Pools in several regions. Data of a project stays in one jurisdiction. One identity works in each pool. | cells, placement rules, organisation statements |
| U9 | A user on a locked-down host | Only HTTPS leaves the host. There is no root and no listener. | roads through proxies, outbound only |

## 4. Goals

* **G1, compute access like ssh.** If the user can reach a machine with ssh or a PodUtils road, podswarm can use it. It copies its own binary there on first use, runs it while a session needs it, and leaves no service behind. A long-lived worker exists only for a machine that nobody can dial.
* **G2, no per-tool setup.** podswarm knows nothing about compilers, build systems or any other tool. Every feature works for any command.
* **G3, as if local.** A remote command sees the caller's directory at the same path, reads files from the caller on demand, and its writes land on the caller's machine. What git ignores (`target/`, `node_modules/`) stays on the machine that runs the command, and a pull rule brings a kept path back (file 06). The terminal, the signals and the exit code behave as with a local command. A sync mode is the fallback where a live view cannot be made.
* **G4, the system behaves as a whole.** The pool is one resource. podswarm picks the machine. The single system image ladder of section 6 is a goal of the design.
* **G5, one self-contained file per target.** Rust, edition 2024, 0BSD. A Linux musl build is a static executable. A macOS or Windows build is one file that links only system libraries. A Linux glibc build is not called static.
* **G6, machine agnostic.** Linux, macOS and Windows can be the caller's machine and can run attempts on boundary `none`. The live view, spreading and the stronger boundaries are Linux features first. The file for each feature says what each system gets.
* **G7, the three kinds of work of the first statement.** Throwaway runs with nothing left behind; long-running persistent work; high throughput on many tiny machines.
* **G8, HyperShell parity for the batch face.** A HyperShell user types the same one-liner and gets the same effect. File 20 has a verdict for each feature.
* **G9, a delivery contract.** Queued work runs at least once and is recorded at most once. No task is lost. A late result changes nothing that was decided. An attached command runs at most once.
* **G10, two honest axes: boundary and shield.** A boundary protects the host from the task. A shield protects the task and the caller from the host. Each level of each axis says in one sentence what it stops. A request is never met by a weaker level.
* **G11, the network is pooled.** The traffic of a run follows a policy that podnet serves. The default is the pooled uplinks, balanced and aggregated. An exit node is chosen on demand.
* **G12, extendable.** Agents and other programs use podswarm through a stable machine interface. podswarm carries no agent and no prompt system.
* **G13, belongs to the org.** It uses `pod-*` crates where they fit, and its generic mechanisms become `pod-*` crates that other PodUtils projects can use.
* **G14, operable by a person and a script.** JSON for every report, exit codes from the org table, no secret in argv, a built-in `doctor`.

## 5. Non-goals

* **N1, no knowledge of a tool.** podswarm has no compiler wrapper, no build cache and no rule for any program. A build gets faster because its processes run on more cores, not because podswarm understands the build.
* **N2, not a CI runner.** podrunner is that product.
* **N3, not a workflow engine.** No DAG. Groups and arrays give stages and sweeps.
* **N4, not a container orchestrator.** No service discovery, no ingress, no rolling deploy.
* **N5, not a message broker.**
* **N6, no high availability of one coordinator.** One writer, restore from a backup. Cells give independence, not failover.
* **N7, not a boundary between hostile tenants on one worker with boundary `none`.**
* **N8, not exactly-once for queued work.** It cannot be.
* **N9, not a distributed file system for its own sake.** The view of a session ends with the session. The content store is a cache with quotas.
* **N10, not a remote desktop, an editor host or a codespace.** The user's tools and files stay on the user's machine.
* **N11, not a replacement for Slurm on an HPC system.** podswarm can run inside an allocation.
* **N12, no agent, no prompt handling, no model calls.**
* **N13, no billing.** It records what a run used.
* **N14, no GUI.**

## 6. The single system image ladder

"The whole system behaves as a whole" has three steps. One process lives on one machine at a time.

| Step | What it gives | Place in the design |
| --- | --- | --- |
| 0 | A command runs on the best machine of the pool. | file 08, first releases |
| 1 | Every new process that a program starts can run on another machine, with the same files, environment, pipes, signals and exit code. A `make -j64` on a laptop uses 64 cores of the pool. | file 07, part of the main design |
| 2 | A running process moves to another machine: by a checkpoint that the program writes, by a checkpoint of the process, or by the migration of a guest. | files 15 and 07, a stated goal with its limits |
| 3 | The memory of the pool is one resource. | file 07, a stated goal with its limits |

## 7. Headline targets

Each is a target `[T]`. File 23 gives the conditions and the test for each, and the full list.

| Id | Subject | Target |
| --- | --- | --- |
| A-20 | one remote command | `podswarm run HOST -- true` adds at most 30 ms to the round trip |
| A-21 | live view | a warm build through the live view within 10 percent of the build on the machine; `fuse` 3, `fuse-userns` 5, `trap` 8 percent |
| A-22 | live view | under 64 KiB sent before the compiler starts |
| A-23 | first use | the first run reaches the command in under 5 s |
| A-24 | spreading | at least 5 times faster on 8 machines than on one |
| A-01 | coordinator | at least 20,000 tasks/s |
| A-05 | worker | worker CPU per task at most 300 us on Cortex-A53, 60 us on x86_64 |
| A-07 | one-liner | at most 35 ms; at most 0.5 ms overhead per task for 100,000 |
| A-09 | binary | at most 10,000,000 bytes |
| A-10 | delivery | zero lost tasks, zero duplicate accepted results |

## 8. What success looks like

* The owner types `podswarm run bigbox -- cargo build` on the weak PC. The build uses the server. The build products stay warm on the server, and one `pull` rule in the workspace file (`[view] pull`, or `--pull`) brings `target/release/NAME` back to the PC; the command prints one line that names the kept paths. When the command ends, the server holds no file in the clear and no process of the session.
* The same command with three more hosts in the pool file is several times faster, with no flag for cargo.
* A researcher replaces `hsx` with `pswx` in a script, and the exit code now says that a task failed.
* A homelab owner adds 30 boards with one line each and loses no task when a board loses power.
* An agent runs `podswarm run --json -- pytest` and reads one result document.
