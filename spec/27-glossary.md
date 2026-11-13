# 27. Glossary

This file lists the terms that a reader meets in more than one file of the tree, with a short meaning and the home file that holds the rules. A meaning here is a pointer, not a rule: where this file and a home file differ, the home file is right. File 00 gives the overview, and the README gives the conventions of the ids.

## 1. Symbols and ids

| Term | Meaning | Home |
| --- | --- | --- |
| `[T]` | A target: a number that no benchmark of podswarm code backs yet. | file 23 |
| `[EV-nnn]` | An evidence tag: a checked fact that the text relies on, resolved in `evidence/facts.md`. | `evidence/facts.md` |
| `b3:` | The prefix of a content id: `b3:` and 64 hex digits of the BLAKE3 hash of the bytes. | file 15 |
| `b3k:` | The prefix of the id of an encrypted object: the keyed BLAKE3 hash of the plain bytes under a data key or a store key. | file 15 |
| `SHA256:` | The prefix of a key fingerprint of `pod-identity`: base64 of the SHA-256 of the 32-byte Ed25519 key. SHA-256 is not a content id. | file 16 |
| `psw`, `pswx` | Short aliases of `podswarm` and `podswarm x`, made only by `self install-aliases`. | file 18 |
| `psw1.`, `psw1s.` | The prefixes of an invite token and of a submitter connect string. | file 16 |
| A-nn | A target id, for example A-20. | file 23 |
| B-nn | A benchmark id. | file 23 |
| D-nn | A decision id, D-01 to D-129. | file 25 |
| E-nn | An environment test id (real hosts, VMs, live roads). | file 23 |
| EV-nnn | An evidence id. | `evidence/facts.md` |
| F-nn | A fault test id (real binaries with faults). | file 23 |
| G-nn | A guard id (a rule of the repository that a script checks). G1 to G14 with no hyphen are the goals of file 01. | file 23 |
| I1 to I7 | The invariants of the queue: no lost task, one accepted result, rising numbers, one open row, the worker self-fence, durable before acknowledged, budgets only rise. | file 09 |
| K-nn | A risk id. | file 26 |
| M-nn | A simulation test id. M0 to M10 with no hyphen are the milestones of file 22. | file 23 |
| N-nn | An ask to podnet. N1 to N14 with no hyphen are the non-goals of file 01. | file 21 |
| P-nn | An ask to podcrates. | file 21 |
| R-nn | A ruling that the owner gave or that is still asked. R1 to R4 with no hyphen are attackers of file 13. | file 26 |
| S-nn | A soak test id. | file 23 |
| T1 to T11 | The transitions of a task. T4s is the second row of speculation. | file 09 (T4s: file 24) |
| U1 to U9 | The use cases. `U-name` (with a hyphen and a word) is a unit, case or conformance test of file 23. | file 01 |
| V-nn | An ask to podvm. | file 21 |
| W1 to W7 | The transitions of a worker record. | file 09 |
| X-nn | An attack id of the attack table. | file 16 |

## 2. A to B

| Term | Meaning | Home |
| --- | --- | --- |
| admission policy | A plugin kind (`podswarm-admit-NAME`) that a coordinator asks at `submit`; a refusal is `policy`. | file 17 |
| aggregation | The use of several uplinks by one flow. podnet balances per flow only, and the report says `aggregation: per_flow`. | file 14 |
| anchor | The machine that runs the root process of a command (D-123). It holds the owned directories and the upper layer and is the file authority for the files that members write. With `run --spread -- CMD` it is the caller's machine; with `run HOST --spread -- CMD` it is HOST. | files 06, 07 |
| area | See work area. | file 13 |
| `area` (pool key) | Where the owned directories live at shield `private`: `auto` (default), `memory` or `sealed`; `--area` for one run. | file 13 |
| array | One task per index from A to B (`submit --array A:B[:S]`); the index is the task input and `TASK_INDEX`. | file 09 |
| `at_least_once`, `at_most_once` | The two values of the shape field `delivery`. See delivery contract. | file 09 |
| attach secret | A 32-byte random secret that a far worker sends on its link; a reattach must send it in its first frame. | file 16 |
| attempt | One try of a task: one process tree on one worker, numbered by `attempt_no`. | file 05 |
| attestation | The proof of shield `sealed`: the caller verifies an SEV-SNP report (chain, measurement, report data, TCB) before it sends a file or a key. | file 13 |
| authority | The party that offers attempts, answers `hb` and holds the deadlines: the home of a session or the coordinator of a swarm. | file 03 |
| auto (view) | `--view auto`: the first view rung that passes; `sync` on a slow link with a warm copy; no view on the caller's machine or on a worker that has the caller's directory on the same network file system at the same path (D-127, from M2). | file 06 |
| `batched` | See durability level. | file 11 |
| blob | A byte string in the content store, named by its content id. | file 15 |
| bootstrap | The copy of the podswarm binary to a far machine through the road, its hash check and its start. Also the verb `podswarm bootstrap`, which installs a worker that dials out. | file 04 |
| boundary | The protection axis of the host from the task: `none < confined < sandbox < vm`, in `needs.boundary`. | file 13 |
| bulk stream | A stream of the link other than the control stream; it carries one transfer (`io`, `blob_put`, `blob_get`, `view`, `net`, `exec`) after a JSON header line. | file 05 |
| bundle | The task rows of one offer, at most `bundle_max`. | file 10 |

## 3. C to E

| Term | Meaning | Home |
| --- | --- | --- |
| `cache` (pool key) | A bool of a machine, default true; false (or `--no-cache` for one run) keeps no warm state on the machine. | file 13 |
| `caps` | The capacity and capabilities that a worker reports in `hello`: cores, memory, the speed scores `speed` and `speed_all`, boundary, shield, view rungs, network, containment. | file 08 |
| cell | One authority and its machines, with the labels `region` and `juris` (jurisdiction). A session cell has the home as its authority; a swarm cell has a coordinator. | file 08 |
| checkpoint | The saved state of a task: a tree manifest plus its blobs, named `<cell>/<run_id>/<task_id>/<seq>`. In file 11 the word also names a WAL checkpoint of SQLite. | file 15 |
| checkpoint sink | A plugin kind (`podswarm-ckpt-NAME`) that keeps an extra copy of a checkpoint, for example in Git. | file 17 |
| checkpointer | The trait `Checkpointer` that saves and restores task checkpoints (files 17, 21). The thread of a coordinator that runs SQLite WAL checkpoints is the WAL checkpointer. | file 17 |
| class | The hash of the rounded needs and the priority of a shape. Tasks of one class are interchangeable for matching. | file 10 |
| `confined` | The boundary made by Landlock, a seccomp deny list and `no_new_privs`. Linux only. | file 12 |
| containment rung | The mechanism that finds every process of an attempt for the tree kill: `cgroup`, `pidns`, `subreaper`, `reaper`, `job`, `session`. | file 12 |
| content cache | The blobs and per-workspace state that a worker keeps warm; sealed at shield `private`. | file 06 |
| content id | The id of a blob: `b3:` and the BLAKE3 hash. One hash serves blobs, shapes, the view cache and checkpoints. | file 15 |
| content store | The one store of blobs, layout `<root>/blobs/<2 hex>/<62 hex>`, on a coordinator, a worker and a home. | file 15 |
| control stream | Stream 1 of the link; it carries the JSON control messages. | file 04 |
| coordinator | The optional long-lived authority of a swarm, with the durable store (`podswarm coord`). | file 03 |
| credential rules | The rules at every shield level: no agent forwarding, no credential file served by the view, no secret-looking variable passed. | file 13 |
| data key | The one symmetric key of a run with `checkpoint.encrypt = "run"`; it stays with the submitter. A worker asks for it with `ckpt_key_req`, and a connected home of the submitter (or the coordinator with escrow) answers `ckpt_key` (D-126). | file 15 |
| delivery contract | Queued work runs at least once and is recorded at most once; `at_most_once` never starts a task twice by podswarm's own act. | file 09 |
| deny list | The credential files that the view never serves, and the variable names that never pass. | file 13 |
| door | A local endpoint of a worker that serves the network policy of the flows of a hold. | file 14 |
| durability level | `strict` (each commit syncs), `batched` (no sync at commit, the WAL checkpointer syncs at least once a second) or `memory` (no store). | file 11 |
| each | `podswarm each`: one command on each machine of a selection; in a swarm one pinned task per worker. | file 08 |
| epoch | The view epoch: a number that rises with each change of a record. A start waits until its view has the epoch of the offer (`extra.vepoch`). | file 06 |
| escrow | `--key-escrow`: the coordinator keeps the data key of a run in its secret store (`secrets.1`) and answers key requests, so no home of the submitter needs to be connected. | file 16 |
| exec supervisor | The keeper of a spread session: it holds the seccomp listener, decides each exec and does the takeover. | file 07 |
| exit | A named place where flows leave (`[exit.NAME]` of the pool file); the policy `exit:NAME`. | file 14 |
| export root | The directory that the view projects: the nearest ancestor with `.git`, else with `.podswarm.toml`, else the working directory. | file 06 |

## 4. F to H

| Term | Meaning | Home |
| --- | --- | --- |
| feature name | A wire feature in the form `name.N` (`zstd.1`, `view.1`, `ckpt.1`, `jobs.1`); on only when both sides list it. | file 04 |
| fence | The rule that a worker ends each attempt at `t_ok + silence_s + kill_grace_s` and the authority waits longer, so two copies never run past a known margin. | file 05 |
| fence clock | The clock of the fence that counts sleep (`CLOCK_BOOTTIME` on Linux). | file 05 |
| generation | `gen`: a random id of a store, new after a restore; a worker with another `gen` drops its journal and attempts. | file 11 |
| grant | The time a member of a spread session may use a directory or a file that it validated with no round trip (`spread_grant_s`). | file 07 |
| group | The stage number of a task in a run; group n+1 opens when group n succeeded. | file 09 |
| `guest` | The shield level where the run is inside a VM guest that runs its own worker. | file 13 |
| `hb`, `hback` | The heartbeat of a worker with its full holding, and its answer; only an answered `hb` moves `t_ok`. | file 05 |
| `held` | A task state: a person holds the task, or it waits for a data key (reason `needs_key`: no home of the submitter answered `ckpt_key_req` and the key is not in escrow). | file 09 |
| held (late result) | The condition for a result to count: the same generation, worker and link, and the row did not end on a report of that worker. | file 09 |
| held item | A write-back op that waits for the user: a protected path, a large delete, a file over a size threshold. | file 06 |
| `hello`, `ready` | The first message of the dialer of a link and the answer of the listener. | file 04 |
| hold (network) | A mechanism that catches the socket calls of an attempt tree: hold rungs `guest`, `netns`, `notify`, `deny`, `env`. | file 14 |
| `hold` rows | The list of attempts that a worker holds, in each `hb`, with state `q`, `r` or `d`. | file 05 |
| holder | The background process of a user that is the home of the session; it ends after `hold_s` with no work. | file 04 |
| home | The authority of a session: the caller's own process, kept by the holder. | file 03 |
| `home` (network) | The network policy where each flow leaves from the caller's machine; `home=PORTS` reaches loopback ports of the caller. | file 14 |
| hook | A command that runs for one event type, from the user or coordinator config. | file 17 |
| hub | An optional relay of TLS streams for a coordinator that cannot listen (`hub.1`, later). The word names only this relay. | file 24 |

## 5. I to L

| Term | Meaning | Home |
| --- | --- | --- |
| invite | A token `psw1.` with the coordinator pin and a secret, with rules for uses, expiry, tags and approval. | file 16 |
| job | A service (keep N tasks alive) or a periodic task of the jobs extension (`jobs.1`); also the id `job_id`. | file 24 |
| journal | The append-only record of a worker: `hold`, `spawn`, `pids`, `result`. | file 12 |
| keeper | One process per attempt, forked by the spawner; the subreaper of the attempt. | file 12 |
| kill ladder | The polite signal, a wait of `kill_grace_s`, the tree kill, and the `residual` count. | file 12 |
| learned table | The per-user record of run time, CPU and memory per program, used by placement; it never leaves the caller. The exec table of spreading is separate. | file 08 |
| leftovers | The pool key that says what may stay on a machine after a session: `bin` or `none` (`--no-trace`). | file 13 |
| lease record | The store row of one offer (`leases`), deleted when each of its attempts has an attempt record. | file 11 |
| `leased` | A task state: offered to a worker, not known to run. | file 09 |
| link | `pod-link` over a road: a control stream and bulk streams with credit windows. | file 04 |
| live view | The view rungs that serve files on demand (`fuse`, `fuse-userns`, `trap`), against `sync`. | file 06 |
| local | The road and the pool name of the caller's own machine: a worker in the caller's process. | file 04 |
| `lost` | A terminal task state of an `at_most_once` task whose attempt ended with no result; also the `end_kind` of a row known dead with no result. | file 09 |
| lower layer, upper layer | The lower layer is the tree that the origin serves. The upper layer (`upper/`) holds the files that the run wrote, until the home acknowledges them. | file 06 |

## 6. M to O

| Term | Meaning | Home |
| --- | --- | --- |
| manifest | The text of a tree: one line per entry (`F`, `D`, `L`, `C`, `H`), first line `podswarm-tree/1`; itself a blob. | file 15 |
| member | A pooled machine that runs moved processes of a spread session. Also a machine that serves flows of a `pool` network policy, and a key admitted by an organisation statement. | file 07 |
| `memory` | See durability level. | file 11 |
| milestone | M0 to M10; M1 is the first usable release. | file 22 |
| moved process | A process of a spread session that runs on a member as an attempt of that member, keyed by `proc`. | file 07 |
| needs | The part of a shape that selects a worker: cores, memory, resources, tags, os, boundary, shield. | file 09 |
| `net` | The shape field of the network policy: `host`, `pool` (the default), `exit:NAME`, `home`, `none`, with `;KEY=VALUE` modifiers. | file 14 |
| node id | `nid`: the id by which a worker asks the home for a file, never a path. | file 06 |
| `none` | The lowest level of each axis. Boundary `none`: the task runs as the worker's uid. Shield `none`: the host is trusted; the credential rules still hold. Also the network policy with no network (file 14) and `--view none`. | file 13 |
| offer | A message of the authority with attempts for a worker, numbered by `offer.no`. | file 05 |
| open row | An attempt row that is `offered`, `running` or `stopping`. A task has at most one (I4). | file 09 |
| organisation statement | A member statement `{doc, key, sig}` that an organisation key signs; it makes a key valid in each cell that trusts that organisation key. | file 16 |
| origin | The caller's machine: the truth of the workspace; it serves the lower layer of the view. | file 06 |
| outcome | The end of an attempt as the worker reports it: `exited`, `signaled`, `timeout`, `spawn_failed`, `killed`, `cancelled`, `not_started`, `checkpointed`. File 09 maps each to a transition. | file 05 |
| owned directory | A directory that git ignores as a whole and that holds no tracked path; native on the worker, warm across runs, never crosses the link. | file 06 |
| owned path | See owned directory. | file 06 |

## 7. P to R

| Term | Meaning | Home |
| --- | --- | --- |
| pin | The expected Ed25519 key of the other end of a `wss` road (each end pins the other): a `pod_identity::KeyName`, written as its `SHA256:` fingerprint in files, tokens and connect strings (field `k`), and in the display form for a person (D-129). | file 16 |
| placement | The choice of the machine for one command: the candidate filter, then the lowest estimated time to the end. | file 08 |
| plugin kinds | The three out-of-process kinds: the `exec:` road, the checkpoint sink and the admission policy. | file 17 |
| `podswarm pull` | The verb `podswarm pull [HOST] PATH...`: it copies paths that stayed in the warm workspace of a machine to the caller's tree, after the run. | files 06, 18 |
| pool | The machines that a user can use. Also the default network policy `pool`, which balances flows over pooled uplinks (file 14). | file 08 |
| pool file | `pool.toml` in the user config directory: machines, groups, cells, exits, residency rules. | file 08 |
| `private` | The shield level of a memory-backed work area, warm state as ciphertext, no key on the host, removal at exit. The default of a remote machine. | file 13 |
| profile | The capability profile of `podswarm mcp` (`[mcp.profile.NAME]`): workspace, cells, floors, limits. | file 17 |
| projected path | A path under the export root that the worker reads from the home on demand. | file 06 |
| pull | The message by which a worker reports its free capacity, its unstarted count and `seen`. | file 05 |
| pull rule | A path that always comes back at the end of a run: `[view] pull` or `--pull GLOB`; `podswarm pull` fetches one later. | file 06 |
| reattach | The repair of a cut road: the home starts `podswarm worker --attach`, which joins the stream to the worker's private socket; the first `hb` reconciles. | file 04 |
| reconciliation | The comparison of the holding in each `hb` with the rows of the authority. | file 05 |
| residency rule | A rule (`[residency]`) that can only restrict the cells, regions, jurisdictions and floors of a run. | file 08 |
| result | The message of a worker with the outcome, code, usage and output of ended attempts. | file 05 |
| `retain` | The checkpoint field that says how many complete checkpoints of a task stay, 1 to 100 (default 2); pinned ones stay as well. | file 15 |
| road | A way to get one ordered byte stream to a podswarm process on a far machine, and to start it: `ssh`, `local`, `podssh`, `exec:`, `wss`, reverse roads. | file 04 |
| run | A set of tasks of one owner with a weight, a priority, `max_running` and a halt policy. | file 09 |
| run identity | A short JWT for one attempt and one audience that a run shows to an outside service. | file 17 |
| rung | One mechanism of a ladder of choices. The tree has view rungs (file 06), exec rungs (file 07), containment rungs (file 12), area rungs of the work area (file 13) and hold rungs (file 14). | file 06 |

## 8. S

| Term | Meaning | Home |
| --- | --- | --- |
| `sandbox` | The boundary where a user-space kernel (gVisor through podvm) serves the system calls of the attempt (later). | file 24 |
| `sealed` | The shield level of a confidential VM that the caller attests before it sends anything. | file 13 |
| sealed store | The store of warm state at shield `private`: objects sealed under a key that only the caller holds, on the disk of the host. It also serves an owned directory that does not fit in memory, through FUSE. | file 13 |
| `seen` | The field of `pull` and `hb`: the count of `offer` messages that the worker received on the link when it sent the message (D-125). | file 05 |
| service | A job of kind `service` that keeps N tasks alive. | file 24 |
| session | The way of work whose authority is the home: nothing durable, nothing listens. | file 03 |
| shape | What many tasks share: what runs and how, its needs and its limits, stored once with a `shape_id`. | file 05 |
| shield | The protection axis of the task and the caller from the host: `none < private < guest < sealed`, in `needs.shield`. | file 13 |
| slot | One attempt that a worker may run at one time; `slots`, `TASK_SLOT`. | file 08 |
| spawner | The single-threaded process that a worker forks before any thread; it forks the keepers and also holds the fence. | file 12 |
| `speed`, `speed_all` | The speed scores of a worker in `caps`, from the CPU calibration: `speed` for one thread (1,000 is one core of the reference machine), `speed_all` for all cores. | file 08 |
| `speed_w` | The speed estimate of a worker that the engine learns from wall times, per mille (1,000 is the median worker); it is not the `caps` score. | file 10 |
| spread session | One root command of `--spread` and all its descendants, over the members. | file 07 |
| spreading | Step 1 of the single system image ladder: each new process of a program can run on another machine. | file 07 |
| standing pull | The newest `pull` of a link; it replaces the one before and is not a request that waits for one answer. The authority may offer its capacity minus the tasks of each offer sent after offer number `seen` (D-125). | file 10 |
| store | The durable store of a coordinator (`SqliteStore`) or the memory store of a session (`MemStore`). The content store (file 15) and the sealed store of warm state (file 13) are other stores. | file 11 |
| `strict` | See durability level. | file 11 |
| stream | One ordered channel of a link, with its own credit window; stream 1 is the control stream, the others are bulk streams. | file 04 |
| stub | The image that a moved process becomes on the machine where it called `execve`; it keeps the pid and forwards stdio, signals and the exit. | file 07 |
| submitter | A party that asks a coordinator for work with a key of the `submitters` table: the CLI, a script, an agent. | file 16 |
| swarm | The way of work whose authority is a coordinator with a durable store. | file 03 |
| sync | The view rung that sends changed files, runs on a warm copy and fetches changes; the fallback of the live view. | file 06 |

## 9. T to Z

| Term | Meaning | Home |
| --- | --- | --- |
| tail reclaim | The authority takes back unstarted tasks of a busy worker for an idle one (`cancel{unstarted}`). | file 10 |
| takeover | The step that makes a moved process exec the stub after its real exec, so the pid stays. | file 07 |
| task | The durable intent "run this": a shape plus its own input, with a state. | file 09 |
| task states | `held`, `waiting`, `ready`, `leased`, `running`; terminal `succeeded`, `failed`, `cancelled`, `lost`. | file 09 |
| `TASK_*` | The variables of an attempt (`TASK_ID`, `TASK_ATTEMPT`, `TASK_DIR`, `TASK_RESUMED` and more). | file 12 |
| `TASK_DIR` | The private directory of one attempt, never reused. | file 12 |
| template | The token grammar of `x` and `submit` (`{}`, `{/-}`, `{N}`, `{q}`), with no eval. | file 18 |
| trace | The access trace of a workspace and a command: the order of first access, which drives prefetch. | file 06 |
| trap | The view rung that traps `open` and `execve` with seccomp notification over a local replica. | file 06 |
| trust (`own`, `shared`) | A pool key that states a fact about a machine and sets its default shield: `own` gives `none`, `shared` (the default) gives `private`. | file 08 |
| uplink | A pool key: the machine lends its network to the `pool` policy. | file 08 |
| view | The directory tree that an attempt sees in place of the caller's tree. | file 06 |
| `--view` | The rung choice: `auto`, `fuse`, `fuse-userns`, `trap`, `sync`, `none`. `run` and `x` default to `auto`; `submit` defaults to `none` (the command runs in the directory that the worker gives it). | file 06 |
| view server | One process per home and workspace on a worker; it holds the mount, the cache and the write-back log. | file 06 |
| `vm` | The boundary where the attempt runs under a separate guest kernel (later). It does not give shield `guest`. | file 24 |
| `--wait-timeout` | The bound of a wait on `wait` and `submit --wait`; when it ends first, the command exits 124 and the run goes on. `--timeout` exists only on `x` and `join`. | file 18 |
| WAL checkpointer | The thread of a coordinator with its own connection that runs the SQLite WAL checkpoints: PASSIVE above 4,096 pages, TRUNCATE when idle, and at `batched` at least once a second. | file 11 |
| webhook | A signed POST of events from a coordinator to a URL (`psw-hook+jwt`). | file 17 |
| work area | The memory-backed directory of a session at shield `private` and above; it holds `TASK_DIR`, `TMPDIR`, spill files, the journal and the owned directories that fit in 75 percent of `area_max`. | file 13 |
| worker | The role that runs attempts on a machine: started over a road, or `podswarm join` that dials out. | file 03 |
| workspace | One export root of one home, named by `wsid`. | file 06 |
| workspace file | `.podswarm.toml` in the working directory or a parent: `[defaults]`, `[residency]` and `[view]`, which can only restrict or add. | file 16 |
| write-back log | The ordered log of the writes of a workspace on a worker, applied on the home by atomic renames, with conflict copies and held items. | file 06 |
