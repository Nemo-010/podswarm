# 8. Pool: machines, capacity and placement

This file defines the pool: the machines that a user can use, what each worker reports about itself, the placement of one command on the best machine, the learned table, named resources, worker lifetime, cells and regions, and the limits of a pool. File 04 defines the roads and the holder that keeps them open. File 10 defines how a queue of many tasks drives the workers that this file chooses. File 13 defines the shield and the boundary that placement matches. File 14 defines the network policy.

## 1. The pool file

The pool file `pool.toml` is in the user configuration directory (file 19). A system file with the same form can add machines. A file in the workspace never adds, changes or removes a machine. Nothing is read from the ssh configuration unless the user imports it (section 1.4). A pool holds at most `pool_max` (1,024) machines.

### 1.1 Machine entries
Each machine is a table `[host.NAME]`. A name is 1 to 32 characters of `[a-z0-9_-]` and starts with a letter or a digit. The name `local` is the caller's own machine: it exists without an entry, and an entry `[host.local]` can only set `tags`, `slots`, `res`, `auto` and `uplink`. A name that starts with `@` is a group (section 1.2).

| Key | Type, default | Meaning |
| --- | --- | --- |
| `road` | string, required | The road of file 04: `HOST`, `user@host`, `ssh://...`, `podssh://...`, `exec:CMD`. A `wss://` road is not a machine: it names a coordinator in a `[cell.NAME]` entry (section 8). |
| `tags` | list of strings, `[]` | Tags of file 09 (`K:V` or a bare word). The worker reports them as its own. |
| `trust` | `own` or `shared`, default `shared` | A fact about the machine that the user states. It sets the default shield (file 13). |
| `shield`, `shield_require`, `cache`, `leftovers`, `guest_tcg`, `seal_smt`, `seal_chip`, `area_max` | file 13 | Shield keys of one machine. |
| `slots` | integer, the cores of the machine | Attempts that may run at one time. |
| `res` | table of name to count, `{}` | Named resources that the machine declares (section 5). |
| `cell` | cell name, none | The cell of the machine (section 8). |
| `region`, `juris` | label, none | Labels of a machine with no `cell`. Lowercase `[a-z0-9-]`, at most 32 characters. |
| `time_limit` | duration, none | Passed to the worker as `--time-limit` (section 6). |
| `uplink` | boolean, false | The machine lends its network to the pooled network policy (file 14). |
| `auto` | boolean, true | false: the machine is used only when a command names it (`run NAME`, `--on`). Placement and `pool probe` without a name skip it. |
| `source` | string, none | Written by `pool import-ssh`. Information only. |
| `linger_s`, `ssh.max_sessions`, `ssh_args`, `jump`, `remote_exe` | file 04 | Road keys of one machine. |

### 1.2 Groups, defaults and other tables
* `[group.NAME] members = ["big", "lab1", "tag:gpu"]` names a set of machines. A member is a machine name, another group as `@NAME`, or `tag:T` for each machine with tag `T`. A command names a group as `@NAME`. A cycle of groups is a config error.
* `[defaults]` holds the settings of section 12 that a user can set in the pool file: `on`, `cell`, `local`, `local_under_ms`, `place_wait_ms`, `net` (file 14), and the shield default of file 13.
* `[cell.NAME]` defines a cell (section 8). `[exit.NAME]` defines an exit of the network (file 14). `[residency.path."PREFIX"]` holds a residency rule for a directory (section 8.4).

### 1.3 Example
```toml
[defaults]
local_under_ms = 150

[host.bigbox]
road = "ssh://dev@bigbox.example"
trust = "shared"
tags = ["fast"]
cell = "eu"

[host.lab1]
road = "lab1"                # an alias of the user's ssh configuration
trust = "own"
res = { gpu = 2 }
uplink = true

[host.pi4]
road = "ssh://pi@10.0.0.14"
slots = 3
time_limit = "8h"

[group.build]
members = ["bigbox", "lab1"]

[cell.eu]
region = "eu-central"
juris = "eu"
```

### 1.4 Commands
`podswarm pool` edits and reads the pool file. It keeps the comments and the order of the file.

| Command | Effect |
| --- | --- |
| `pool add NAME ROAD [--tag T] [--trust own\|shared] [--cell C] [--slots N] [--res K=N] [--no-auto]` | Adds an entry. An existing name is an error. It does not dial the machine. A `wss://` or `psw1s.` ROAD writes a `[cell.NAME]` entry (a swarm cell, section 8) instead of a machine. |
| `pool ls [SEL] [--json]` | Lists the entries with the last known state: reachable, `caps` summary, free cores, time of the last report, warm workspaces. It does not dial. |
| `pool rm NAME` | Removes the entry. The holder closes its road. The far cache stays until `podswarm forget NAME` (file 04). |
| `pool probe [SEL] [--no-copy]` | Opens the road of each selected machine, at most `dial_max` at one time, copies the binary when it is absent (file 04), and records `caps`. `--no-copy` runs only the `uname -sm` probe of file 04. A machine that answers with no shell greeting (a forge that prints a banner and exits) is marked `not_a_shell`. |
| `pool import-ssh [--include GLOB] [--exclude GLOB] [--file PATH]` | Reads the `Host` lines of the user's ssh configuration and the files of its `Include` lines. It skips a pattern with `*`, `?` or `!`, and a name that the pool has. It writes one entry per name with `road = "NAME"`, `auto = false` and `source = "ssh-config"`. It never dials. |

Reason for `auto = false` on import: an ssh configuration holds bastions, forges and machines with hardware keys that ask for a touch. The user turns on each machine that placement may use.

## 2. What a worker reports

### 2.1 `caps`
A worker sends `caps` in `hello` (file 04). It sends `caps` again only when a value changes, as a new `hello` after reattach. The authority stores it in the worker record (file 09). `caps` is one JSON object of at most 3,072 bytes, so that `hello` fits its limit (file 05).

| Field | Type | Meaning |
| --- | --- | --- |
| `os` | string | `linux`, `android`, `macos`, `windows`, `freebsd`, `openbsd`, `netbsd` |
| `arch` | string | `x86_64`, `aarch64`, `armv7`, `arm` (ARMv6, `armv6l`), `i686`, `riscv64`, `loongarch64`, `s390x`, `powerpc64le`. `needs.arch` takes these values; the CLI maps the `uname -m` names to them. |
| `target` | string | The target triple of the running binary |
| `cores` | u32 | Logical processors that the worker may use: the CPU affinity mask, lowered by a cgroup `cpu.max` quota |
| `mem_mib` | u64 | Physical memory, lowered by a cgroup `memory.max` |
| `disk_mib` | u64 | Free space of the task file system at start |
| `res` | object | Named resources: name to count (section 5) |
| `slots` | u32 | Attempts at one time; default `cores` |
| `speed`, `speed_all` | u32, u32 | Speed scores (section 2.3) |
| `shell` | object | `{path, kind, start_us}` (file 12) |
| `interp` | list of strings | Paths of the program interpreters (`ld-*` files of `/lib` and `/lib64`) that exist, for `needs.interp` |
| `boundary` | list of strings | Boundaries that the worker probed and that its policy allows (file 13) |
| `confine` | list of strings | Features of `confined` (file 12) |
| `limits` | object | Mode of each limit (file 12) |
| `containment` | string | The containment rung (file 12) |
| `shield` | object | The shield rows; `shield.max` is the strongest level now (file 13) |
| `view` | list of strings | View rungs that work: `fuse`, `fuse-userns`, `trap`, `sync` (file 06) |
| `net` | object | Network policies and hold rungs (file 14) |
| `pty` | boolean | A usable `/dev/ptmx` (file 12) |
| `features` | list of strings | Wire feature names of file 05 |

The remaining lifetime is not a field of `caps`. It travels as `lifetime_s` in `hello` and `hb` (file 10), because it changes.

### 2.2 Load
Each `hb` carries `load` (file 05): `{busy_m, own_m, mem_avail_mib, disk_free_mib}`.
* `busy_m`: the processor time that all processes of the machine used in the last `hb_s`, in millicores. Linux reads `/proc/stat`, macOS `host_statistics`, Windows `GetSystemTimes`, FreeBSD `kern.cp_time`.
* `own_m`: the part of `busy_m` that attempts of this worker used.
* `mem_avail_mib`: `MemAvailable` on Linux, the free and inactive pages elsewhere, lowered by the cgroup memory headroom.
* `disk_free_mib`: free space of the task file system.

Two numbers of free capacity exist, and placement uses the smaller one. The **declared** free capacity is the capacity of `caps` minus the needs of the attempts that this authority holds there (`pull.free`, file 05). The **measured** free capacity is `cores * 1000 - busy_m` and `mem_avail_mib`. The measured one sees the work of other users and other homes on the machine.

### 2.3 Speed score
At start the worker measures two scores. It runs a fixed kernel that is part of the binary: a portable SHA-256 with no processor extension over 256 KiB, an LZ77 match search over 1 MiB of generated text, and a sort of 262,144 `u32` keys. It counts the rounds of the kernel in `calib_ms` (100) of thread processor time.
* `speed`: one thread. `speed = 1000 * rounds / rounds_ref`. `rounds_ref` is a constant of the binary, so a score of 1,000 is one core of the reference machine.
* `speed_all`: one thread on each core of the affinity mask at the same time; the sum of the scores. It shows shared caches, simultaneous threads and thermal limits.

The worker keeps both scores in the probe cache of file 12, under the same key (kernel release, boot id, binary hash). When `busy_m` at the measure is above half of the cores, it marks the scores `busy` and measures again at its next start. The queue engine learns its own speed per worker from task times (file 10); the scores of this section serve placement of one command and the first estimate.

## 3. Placement of one command

### 3.1 The forms
| Form | Rule |
| --- | --- |
| `podswarm run NAME -- CMD` | That machine. NAME is a pool name or a road. No estimate. The filters of section 3.2 still apply: a machine that fails one is refused with the reason, and the command does not go elsewhere. |
| `podswarm run -- CMD` | The best candidate of the pool by section 3.3. |
| `--on SEL` | The candidates are only SEL: a comma list of names, `@GROUP`, `tag:T`. |
| `--local` | The caller's machine only. |
| `[defaults] on` | The candidate set when a command gives no `--on`. |

A machine with `auto = false` is a candidate only when SEL or NAME names it.

### 3.2 The candidate filter
A machine is a candidate when each check passes. The checks run in this order, and `-v` names the first check that failed for each machine.

| Check | Rule |
| --- | --- |
| cell | The machine is in a cell that the selectors and the residency rule allow (section 8) |
| reach | The road is open, or the holder has cached `caps` for it, or it answers within `place_wait_ms` (section 3.5) |
| os, arch, interp | `needs.os`, `needs.arch`, `needs.interp` match `caps` |
| boundary | `caps.boundary` holds a level at least `needs.boundary` (file 13) |
| shield | `caps.shield.max` is at least the shield of the run (file 13) |
| view | `caps.view` holds a rung that the run accepts (file 06) |
| net | `caps.net` can serve the network policy of the run (file 14) |
| pty | `caps.pty` when the run needs a terminal |
| capacity | The free capacity (section 2.2) covers `needs.cores_m`, `needs.mem_mib`, `needs.disk_mib` and each count of `needs.res`. With no `needs.mem_mib`, the learned peak memory of the program (section 4) must be under `mem_avail_mib` |
| lifetime | The remaining lifetime covers the time need of the command (section 6) |

The caller's machine is a candidate unless `[defaults] local = false`. It meets every shield level (file 13).

### 3.3 The estimate
Placement picks the candidate with the lowest estimated time to the end of the command, `T(m)`. The terms come from the learned entry of the program (section 4) and from the reports of section 2.
```
par      = cpu_ms / wall_ms of the learned entry, clamped to [1, 1024]
           (no learned entry: par = 1024 and work = assume_cpu_ms)
work     = learned processor time in reference milliseconds (section 4)
free(m)  = min(declared free cores, measured free cores), at least 0.25
cap(m)   = min(par * speed(m), speed_all(m) * free(m) / cores(m))       reference cores of speed
run(m)   = work * 1000 / cap(m)
T(m)     = run(m) + dial(m) + boot(m) + view(m) + rtt(m) * (place_rtts + pty * place_tty_rtts)
```
| Term | Value |
| --- | --- |
| `dial(m)` | 0 when the road is open; else the last measured open time of that road; else `dial_default_ms` (800) |
| `boot(m)` | 0 when the far cache holds this binary (file 04); else the binary size divided by the measured link rate; else `boot_default_ms` (4,000) |
| `view(m)` | 0 when `m` holds a warm view of this workspace (file 06); else the learned bytes that the program read through the view divided by the link rate; else `view_cold_ms` (1,000) |
| `rtt(m)` | The round trip of the link (file 10, `R`); 0 for the caller's machine |
| `pty` | 1 when the run has a terminal, else 0 |

For the caller's machine `dial`, `boot`, `view` and `rtt` are 0.

Reason for `par = 1024` on an unknown program: a command with no history is placed as if it uses every free core. The first case of file 01 is a build on a strong machine, and a wrong guess costs one run, after which the learned entry corrects it.

Reason for the terminal weight: each key of an interactive command costs a round trip, so a terminal command prefers a near machine.

### 3.4 Short commands stay local
When the learned entry exists and its estimate on the caller's machine, `run(local)`, is under `local_under_ms` (150), the command runs on the caller's machine. No road is dialled and no estimate of other machines is made. `--on` and NAME turn this rule off.

### 3.5 A cold pool
The pool is cold when the holder has no open road to a candidate. Then the holder:
1. computes `T(m)` from the cached `caps` and load of each machine, from the last session;
2. opens the roads of the candidates with `auto = true` in parallel, at most `dial_max` (16) at one time, in the order of `T(m)`;
3. waits until each road answered with `ready` and its first `hb`, or until `place_wait_ms` (300) passed;
4. decides among the machines that answered (fresh reports), the machines with cached reports whose road is still opening (their `dial(m)` is the time that remains), and the caller's machine.

A machine with no cached report that did not answer in time is not a candidate for this command. A road that opens after the decision stays open for the next command (section 10). The first command after a cold start can wait for the road of the machine that it chose; it does not wait for the others.

### 3.6 Ties and the warm view
Two candidates tie when their `T(m)` differ by at most `place_tie_pct` (10) percent of the lower one. A tie goes to the first machine of this order: a machine with a warm view of this workspace; the machine of the last command in this workspace; the lower `rtt`; the order of the pool file. The caller's machine comes last among equal candidates, so a tie sends work away from the weak machine of file 01.

### 3.7 What the user sees
With no flag nothing is printed about placement. With `-v` the CLI prints two lines on stderr before the command starts:
```
podswarm: place bigbox  est 9.2 s  (local 38.0 s, lab1 14.1 s, pi4 no: arch)
podswarm: bigbox: free 15.5 cores, speed 1310, view warm, rtt 11 ms; learned cargo build: cpu 210 s, par 7.8, n 12
```
With `-vv` it prints one line per candidate with each term of section 3.3. `podswarm run --dry-run --json` gives the same data in the action `place` (file 17). The run record keeps the chosen machine and `T(m)` (file 17).

## 4. The learned table

The learned table holds what the home knows about programs that ran. It is a file `learned` in the user state directory (file 19), mode 0600. The holder reads it at start, keeps it in memory, and writes it at most once in 10 s and at exit. It never leaves the caller's machine.

**Key.** `(workspace, program, arg1)`. `workspace` is the root of the view (file 06), or none. `program` is the absolute path of `argv[0]` after the search of `PATH` on the caller's machine; for a `shell` command it is the first word. `arg1` is the first argument when it does not start with `-` and has at most 64 bytes, else empty. A lookup tries the full key, then `(workspace, program)`, then `(any, program)`. Reason: the first argument often selects the work (`build`, `test`), and no rule for a tool is needed to see it.

**Values per entry.** `n`; the mean and the spread of `wall_ms`, of `cpu_ms` in reference milliseconds, and of `par`; the peak memory `rss_kib`; the bytes read and written through the view; `last_unix`; the last machine.

**Update.** An attempt that ends `exited`, with any exit code and a wall time of at least 1 ms, updates its entry and the two wider entries. Processor time is made relative to the reference core: `cpu_ref_ms = cpu_ms * sc / 1000`, with `sc = cap(m) / min(par, free(m))` of the machine that ran it. A mean moves by `learn_alpha` (0.3) toward the new value. The spread is the same smoothed mean of the absolute difference. The peak memory is the smoothed mean of the peaks.

**Decay.** An entry not used for `learn_ttl_days` (30) is removed. The table holds at most `learn_max` (4,096) entries; the entry used least recently goes first.

**Readers.** Placement of one command (section 3) and `run --dry-run`. Spreading (file 07) keeps its own exec table and reads this table only to seed a new program; it reuses `learn_alpha` and `learn_ttl_days`. A coordinator does not read this table. It uses the histograms of its classes (file 10).

## 5. Needs and named resources

The pool sees the `needs` of a shape (file 05) as declared amounts. podswarm does not measure what an attempt uses against `needs`; it subtracts the declared amounts from the capacity of the machine while the attempt is open. The limits of file 12 are a separate thing: they stop an attempt that uses more.

A named resource is a countable thing that the machine owner declares: GPUs, licences, a USB device, a share of a disk.
* Worker flag `--resource NAME=N`, repeatable; pool key `res`. NAME is `[a-z][a-z0-9_]` of at most 32 characters and not `cores`, `mem`, `disk` or `time`. N is 1 to 1,000,000. At most 16 names per machine.
* Needs: `--needs gpu=1` on `run`, `x` and `submit` sets `needs.res.gpu`. A key of `--needs` that is not `cores`, `mem`, `disk` or `time` is a named resource.
* The authority counts. An attempt that needs `gpu=1` goes only to a machine with a free count of at least 1, and the count is free again when the attempt ends.
* The attempt gets `TASK_RES_<NAME>=<count>` in its environment. podswarm does not bind a device to an attempt. A machine with 2 GPUs and 2 attempts of `gpu=1` leaves the choice of the device to the program, for example by a variable that the owner sets per slot with `TASK_SLOT` (file 12).
* Declared accounting sees only the attempts of one authority. Two homes that use one machine can both count its GPUs. Cores and memory are also checked against the measured load (section 2.2); a named resource cannot be measured. A user who shares named resources between several callers uses one coordinator.

## 6. Worker lifetime

A worker that will end at a known time states its remaining lifetime.
* `--time-limit D` on the worker; pool key `time_limit`, which the home passes to a worker it starts.
* Batch variables, read when no flag is given: `SLURM_JOB_END_TIME`, `PBS_WALLTIME`. The order of the sources, the drain margin and the matching of queued tasks are in file 10.
* The worker reports `lifetime_s` in `hello` and in each `hb`. `pool ls` shows the time that remains.

For one command the time need is `needs.time_s`, else `timeout_s`, else the learned `wall_ms` mean plus three spreads on that machine (section 4), else `assume_time_s` (file 10). A machine whose remaining lifetime minus the drain margin of file 10 is below the time need is not a candidate.

## 7. `podswarm each`

`podswarm each [--on SEL] -- CMD` runs CMD once on each machine of the selection. In a session the home opens the roads of the selection, at most `dial_max` at one time, and starts one attached attempt on each machine as it becomes ready. The output of each machine is labelled with its name. The command exits 0 when each attempt exited with a code in `ok_codes`, else 1. A machine whose road fails counts as a failure with reason `road`, and `--json` gives one row per machine. In a swarm each active worker gets one task pinned to it; the queue rule is in file 10.

## 8. Cells and regions

### 8.1 What a user names
A **cell** is one authority and its machines: a failure domain and a trust domain. There are two kinds.
* A **session cell** has the home as its authority. Its machines are `[host.NAME]` entries. `[cell.NAME]` with no `road` gives a set of machines its labels; a machine joins it with `cell = "NAME"`. The machines with no `cell` form the cell `home`, with the labels of `[cell.home]` when that entry exists.
* A **swarm cell** has a coordinator as its authority: `[cell.NAME]` with `road` set to a `wss://` road with a pin or a connect string `psw1s.` (file 16). Its machines are the workers of that coordinator.

Keys of `[cell.NAME]`: `road` (swarm cell only), `region`, `juris`, `trust` (the trust of every machine of the cell that sets none). The labels are claims of the user about the cell. A machine in a cell takes the labels of the cell; a machine entry that sets other labels is a config error.

A coordinator states its own labels in `ready` as `cell{name, region, juris}` (file 04, D-42). The home refuses a swarm cell whose stated labels differ from the labels in the pool file, and does not send it a byte of the run. The workers of a swarm get their labels from their invite as the reserved tags `@region:` and `@juris:` (file 16), so a worker cannot state its own labels.

### 8.2 Placement rules
* Selectors: `--cell NAME`, `--region R`, `--juris J`, and the shield of the run. They intersect.
* With no selector, a run uses the session cells. A swarm cell gets a run only when `--cell` or `[defaults] cell` names it. Reason: a run must not go to a shared coordinator by accident.
* A run of a swarm lives in exactly one cell. Its global name is `cell/run_id`. A run of a session may use the machines of each session cell that passes its selectors, because the home is the one authority of all of them.
* A selector that matches no cell refuses the run with `no_cell` (class Policy; `wrong_cell` is class Usage; both in file 05, D-42). podswarm never falls back to another cell.

### 8.3 The no-redirect rule
When a coordinator answers `err{code: wrong_cell, cell: NAME}`, the client looks NAME up in its own pool file. It never dials a host, a road or an address that came in an answer. Reason: an address in an answer lets any party that answers send the client and its data elsewhere. The key of the client does not move to another host, so a member statement (file 16) is useless to a host that does not hold the member key.

### 8.4 The residency rule
A residency rule says where the data of a directory may go. It can live in a workspace file, `.podswarm.toml`, in the table `[residency]`. This is safe because the rule can only restrict: a hostile file can make a run fail, visibly, but it cannot send data to a place that the user did not allow. File 16 allows a workspace file to set `[defaults]`, `[residency]` and `[view]`; `[view]` can only add globs and lower thresholds (file 06, section 18).

Keys: `allow_cell`, `deny_cell`, `allow_region`, `allow_juris` (lists), `shield_min`, `boundary_min` (levels of file 13).

The four conditions that make the rule safe:
1. **It only intersects.** The keys above are the only keys. A rule never names a road, a key, a coordinator, an address or a path outside the workspace. A cell named in a rule must exist in the pool file; an unknown name refuses the run.
2. **Every file counts.** The set of allowed cells is the pool file, intersected with each `.podswarm.toml` from the working directory up to the file-system root, intersected with the user rule `[residency.path."PREFIX"]` of each prefix of the working directory, intersected with the command line. An empty set refuses the run with `no_cell`. A nearer file cannot widen a farther one.
3. **The command line cannot widen it silently.** The only way to widen is `--ignore-workspace-rules`. It prints `podswarm: workspace rule ignored: FILE` on stderr. The MCP profile cannot pass it (file 17).
4. **Floors only rise.** `shield_min` and `boundary_min` raise the floor of the run. A value below the floor that the user set elsewhere is ignored with a warning. A key that is not known, or a value that would widen a set or lower a floor, is a hard error that names the key, so a typo does not drop a rule.

A user rule `[residency.path."~/work/client-a"]` in the pool file applies to a directory also when the workspace file is absent, for example in a copy.

### 8.5 What "data stays" means
The home checks the rule before it sends the first byte of a run: before the view starts, before a sync, before `blob_put`. Then:
* **Sent data** (view reads, synced files, blobs, `files[]`, checkpoints, outputs, logs) goes only to the authority and the workers of the cells that pass.
* **The view cache** on a worker (file 06) holds only files of workspaces whose runs that worker ran. The shield of file 13 decides whether the cache is sealed or wiped.
* **Blobs** go to the content store of the authority of the cell (file 15). A worker cache holds only blobs of runs of its own cell.
* **Checkpoints** stay with the authority of the cell: the coordinator store of a swarm cell, the home of a session cell. A restore uses a machine of the same cell. `checkpoint export` to another cell needs that cell to pass the rule (file 15).
* **The caller's machine** is not restricted: the rule limits where data goes from the caller.
* **The network** of the run is not controlled by the rule, except that the members of a pooled network policy must pass it (file 14).

### 8.6 Consistency between cells
A cell is the single authority of its runs. No state is copied between cells, so there is no replication lag and no conflict to resolve. A client of several cells keeps `cell/run_id` pairs and never merges their state. Reason: one authority per run removes the consistency traps of a replicated control plane.

### 8.7 Cells with ssh only
A session cell needs no coordinator: `podswarm run HOST -- CMD` starts the worker over ssh (file 04). sshd decides who gets in, so no organisation statement is needed there. The labels, the selectors and the residency rule of the pool file still apply. Cells are flat; a hierarchy of coordinators is the sub-coordinator extension (file 24).

## 9. A coordinator in a pool

A swarm cell (section 8.1) is how a coordinator appears in a pool. When a command selects it:
* The home does not place. It submits the command as a task with `io = attached` (file 05). The coordinator applies the filter of section 3.2 and the estimate of section 3.3 to its own workers, with the class histogram of file 10 in place of the learned table.
* The caller relays the view through the coordinator. The worker opens its `view` streams to the coordinator, and the coordinator relays them on the link of the caller, which serves the files (file 06). The `io` streams of the terminal take the same path (`attach`, file 05).
* The coordinator is in the path of the files. Its cell labels must pass the residency rule. Its view of the bytes is the subject of files 06 and 13.

## 10. Limits of a pool

* **Roads.** The holder keeps at most `roads_max` (64) roads open. It closes a road that carried no attempt for `road_idle_s` (300). When a new road would pass `roads_max`, it closes the road that is idle longest; a road with an open attempt is never closed for this.
* **Descriptors.** One ssh road costs the holder 4 descriptors per lane (the pipes of stdin, stdout and stderr, and a pidfd or a wait handle), and a road has at most 2 lanes (file 04). So a road costs at most 8. At start the holder raises its soft `RLIMIT_NOFILE` to the hard limit. It lowers `roads_max` to `(limit - 64) / 8` when that is smaller, and logs the value.
* **Processes.** On the caller's machine one ssh road is a client process plus one shared master process per machine (file 04). On the far machine it is the worker and its spawner while the road is open.
* **Dials.** At most `dial_max` (16) roads open at one time. More wait in turn.
* **Machines.** At most `pool_max` (1,024) entries. A pool that is larger uses a coordinator, which has its own connection limits (file 10).

## 11. Targets

| Target | Test (file 23) |
| --- | --- |
| Placement of one command over 100 machines with open roads takes at most 1 ms of CPU [T] | U-place-cpu (A-36) |
| On a cold pool of 10 machines with cached reports, the command starts on the chosen machine at most `place_wait_ms` after the open of its road [T] | M-40 (A-37) |
| The second run of a program whose wall time is under `local_under_ms` runs on the caller's machine and dials nothing [T] | U-place-local |
| `podswarm run -- cargo build` with no history goes to the machine with the largest `speed_all * free / cores` [T] | M-41 |
| The speed calibration takes at most 150 ms of wall time at a cold start and none when cached [T] | U-calib (A-38) |
| A residency rule refuses a run before any byte of the workspace leaves the caller [T] | M-42 |
| A swarm cell whose `ready.cell` labels differ from the pool file gets no byte of the run [T] | M-43 |

## 12. Settings of this file

| Name | Default | Range | Meaning |
| --- | --- | --- | --- |
| `pool_max` | 1,024 | fixed | machine entries in a pool |
| `trust` | `shared` | `own`, `shared`, per machine or cell | what the user states about the machine; the shield it gives is in file 13 |
| `local` | true | bool | the caller's machine is a candidate |
| `on` | all machines with `auto = true` | selector | the candidate set when a command gives no `--on` |
| `cell` | none | cell name | the cell of a run that gives no selector |
| `auto` | true | bool, per machine | placement may choose the machine |
| `uplink` | false | bool, per machine | the machine lends its network (file 14) |
| `local_under_ms` | 150 | 0 to 10,000 | learned wall time under which a command stays local |
| `place_wait_ms` | 300 | 0 to 10,000 | wait for reports of a cold pool |
| `place_rtts` | 2 | 0 to 100 | round trips that a command costs, in `T(m)` |
| `place_tty_rtts` | 20 | 0 to 1,000 | extra round trips of a command with a terminal |
| `place_tie_pct` | 10 | 0 to 50 | difference of `T(m)` that counts as a tie |
| `assume_cpu_ms` | 60,000 | 1 to 86,400,000 | processor time of a program with no learned entry |
| `dial_default_ms` | 800 | 1 to 60,000 | open time of a road with no measure |
| `boot_default_ms` | 4,000 | 1 to 600,000 | copy time of the binary with no measured link rate |
| `view_cold_ms` | 1,000 | 0 to 600,000 | cost of a cold view with no learned read volume |
| `dial_max` | 16 | 1 to 256 | roads that open at one time |
| `roads_max` | 64 | 1 to 1,024 | open roads of one holder |
| `road_idle_s` | 300 | 0 to 86,400 | idle time before the holder closes a road |
| `calib_ms` | 100 | 20 to 2,000 | processor time of one speed measure |
| `learn_alpha` | 0.3 | 0.01 to 1 | smoothing of the learned table |
| `learn_ttl_days` | 30 | 1 to 3,650 | age at which an unused entry is removed |
| `learn_max` | 4,096 | 64 to 1,000,000 | entries of the learned table |
| `--resource`, pool `res` | none | 16 names, counts 1 to 1,000,000 | named resources of a machine |
| `--time-limit`, pool `time_limit` | none | 1 s to 365 days | lifetime of a worker |
| `--ignore-workspace-rules` | off | flag | widen past the workspace residency rule |
