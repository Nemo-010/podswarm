# 12. Execution: how a worker runs an attempt

This file defines what a worker does between the time it holds an attempt and the time it has the exit report of that attempt: the processes, the containment of the process tree, limits, output, environment, shell, directories, the journal, the cost per attempt, and the boundary `confined`.
The attempt itself (shape, lifecycle on the wire, attached I/O, the fence, outcomes) is in file 05. The view is in file 06, spreading in file 07, the two protection axes (boundary and shield) and the credential deny list in file 13, the network policy in file 14, staging of files and checkpoints in file 15. Directories (state, cache, runtime) are defined in file 19.
The crate `pod-proc` carries the process code of this file (file 21 has its API, ask P-1).

## 1. Life of an attempt on a worker

An attempt on a worker is in one of five steps. The column `hb` gives the holding state that the worker reports (file 05).

| Step | `hb` | What the worker does |
| --- | --- | --- |
| queued | `q` | Holds the attempt in its local queue. Checks the `needs` against free capacity. Nothing runs. A `cancel{unstarted}` removes it. |
| starting | `r` | Makes `TASK_DIR` (section 12), stages files (file 15), expands the template, builds argv and the environment, writes the `spawn` record (section 14), sends `Spawn` to the spawner. |
| running | `r` | The payload runs. The worker drains the output (section 9), polls limits (section 7), and checks the timeout and the fence on a 1 s tick. |
| ending | `r` | The payload exited, or the kill ladder runs (section 5). The keeper kills what is left of the tree and counts `residual`. |
| done | `d` | The worker has the exit report. It writes the `result` record, sends the result (file 05), and keeps the attempt until `ack`. Removal of `TASK_DIR` waits for idle time. |

Once the worker sends `Spawn`, the attempt is not unstarted: a `cancel{unstarted}` does not touch it. A spawn failure (bad argv, refused confinement, policy, input) ends the attempt as `spawn_failed` with the reason of file 05. The payload reports a failure before `execve` on a pipe with `O_CLOEXEC`: it writes the step and the `errno`, then exits 127. The keeper reads that pipe; end of file with no data means the `execve` succeeded.

## 2. Process model on Unix

### 2.1 Start order of the worker

`main` does these steps in this order, before the async runtime and before any thread exists:
1. `prctl(PR_SET_DUMPABLE, 0)` and `RLIMIT_CORE` 0. A same-uid process then cannot `ptrace` the worker or read its `/proc/<pid>/mem` and `environ`. Every podswarm process that holds a key (home, worker, coordinator) does this step.
2. `close_range(3, ~0U, CLOSE_RANGE_CLOEXEC)` (Linux 5.11), else a loop over the open descriptors. Descriptors that ssh or a service manager left open never reach a payload.
3. Handle the probe child flag, then read or make the probe cache (section 15).
4. `PR_SET_CHILD_SUBREAPER` on the worker itself.
5. Fork the **spawner**.
6. Start the runtime.

After step 5 the worker forks only to exec at once (a new spawner, the probe of `psw doctor`).

### 2.2 Spawner

The spawner is single threaded. It calls `PR_SET_CHILD_SUBREAPER`, `setpgid(0, 0)` (its own process group) and `PR_SET_NAME` `psw-spawn`. It talks to the worker over an unnamed `socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC)`. It owns every keeper: it waits with `wait4(-1)` and routes each pid through its own table (a keeper pid maps to an attempt; any other pid is an orphan that reparented to the spawner, which it kills and reaps). The worker never waits for a process of an attempt.

The spawner uses `fork`, and the keeper uses `fork` and `execve`. `posix_spawn` and `pre_exec` are not used. The spawner is small and single threaded, so its fork copies few page tables and every call between fork and exec is allowed.

### 2.3 Messages between worker and spawner

| Direction | Message | Content |
| --- | --- | --- |
| worker to spawner | `Spawn` | attempt id, the plan (argv, exact environment, `cwd`, umask, limits, scheduling, confine spec, pty request), and by `SCM_RIGHTS` the stdin source and the write ends of the output pipes |
| worker to spawner | `Signal` | attempt id, `polite` or `kill` |
| worker to spawner | `Fence` | the kill time `t_ok + silence_s + kill_grace_s` on the fence clock (file 05) |
| spawner to worker | `Running` | attempt id, keeper pid, payload pid (also its session id and group id), payload start time in clock ticks since boot; a pty master by `SCM_RIGHTS` when asked |
| spawner to worker | `Ended` | attempt id, the exit report (section 2.6) |

A plan larger than 64 KiB goes in a sealed `memfd` (Linux) or in an unlinked file of the state directory (other Unix), passed by `SCM_RIGHTS`. The encoding is internal to the crate.

### 2.4 Keeper

For each `Spawn` the spawner makes a socketpair for the keeper and forks the **keeper**. The keeper does not exec. It:
1. calls `PR_SET_CHILD_SUBREAPER` and `PR_SET_PDEATHSIG(SIGTERM)`. Its parent is the one thread of the spawner, so the thread rule of the parent-death signal holds;
2. on the `pidns` rung, is made by `clone(CLONE_NEWPID)` and is PID 1 of the new PID namespace (section 4);
3. compiles the confine spec when the boundary is `confined` (section 17);
4. forks the payload, which applies the child state (section 2.5) and calls `execve`;
5. stays as the parent. It waits with `wait4(-1)` for the payload and for every orphan of the tree, polls memory once per second (section 7), and obeys `polite` and `kill` from the spawner;
6. when the payload ends, sends `SIGKILL` to each remaining descendant, waits up to 5 s, counts the rest as `residual`, sends the report, and exits.

A `SIGTERM` that reaches the keeper (the spawner died) makes it kill its tree at once and exit. `PR_SET_PDEATHSIG` is set only in a process whose parent is single threaded, and never on the payload. The keeper reuses the tree walk and the 5 s bound of the `pod-supervise` launcher [EV-046].

### 2.5 Child state

The payload child applies this list between fork and exec, in this order:
1. empty signal mask; every signal from 1 to 64 set to `SIG_DFL`;
2. `setsid()`: a new session and group with no controlling terminal, so a program that opens `/dev/tty` fails at once with `ENXIO` (an attached attempt with `pty` gets a terminal: section 18.1);
3. the umask that the worker had at start;
4. on the `cgroup` rung, `0` written to `cgroup.procs` of the attempt cgroup;
5. resource limits: soft `RLIMIT_NOFILE` `min(1024, hard)` unless `limits.nofile` is set, hard unchanged; `RLIMIT_CORE` 0 unless `limits.core` is true (file 05); the limits of section 7;
6. scheduling: `oom_score_adj` +500, and the values of section 8;
7. `chdir` to the effective `cwd` (section 12);
8. descriptors: 0, 1 and 2 from the plan, then `close_range(3, ~0U, 0)` (Linux 5.9), else a loop;
9. on `confined`, `pod_confine::apply` (section 17); in a spread session, then the exec filter (section 18.3);
10. `execve` of the absolute program path with the exact environment of section 10.

### 2.6 Exit report

The keeper reports: the wait status of the payload; tree CPU time from `getrusage(RUSAGE_CHILDREN)` after the whole tree is reaped (it includes every descendant); peak memory (section 7); `residual`; the limit that ended the attempt, if any; the payload start time. The worker maps the report to the result row of file 05.

### 2.7 End of file in both directions

* End of file on the spawner side of the socket means the worker died, by any cause. The spawner sends `SIGTERM` to each keeper (each keeper then kills its tree), waits `kill_grace_s`, kills each keeper tree that is left, kills each process that reparented to the spawner, and exits.
* End of file on the worker side means the spawner died. The worker kills each process of its own subtree (it is a subreaper, so the orphans of the spawner and the keepers come to it), reaps them, writes a result `killed` with reason `orphan_cleanup` for each attempt that ran, and starts a new spawner: a fork followed at once by an exec of its own binary with the internal spawner flag and the new socket. A fork followed at once by exec is safe in a process with threads.

### 2.8 The spawner holds the fence too

The worker sends `Fence` after each `hback` that renews `t_ok` (file 05). The spawner reads the fence clock (file 05) on a 1 s tick. At the kill time it sends `SIGKILL` to every keeper tree that is still running, whether or not the worker acted, and reports each such attempt as `killed`, reason `self_fence`. The fence then holds when the worker is stopped, stalled or dead. A same-uid payload can stop the spawner too (`SIGSTOP`); on `confined` with feature `confine_scope` the signal scope blocks that (file 16 lists what a task can do to its worker).

### 2.9 `--lite`

`--lite` makes no keeper. The spawner forks the payload and is the subreaper of all attempts. It attributes a process to an attempt by its session id. A process that left its session is killed when no attempt runs, or at worker exit. The worker reports containment `session`. Use it on a host where a second fork per attempt costs too much.

## 3. Windows process model

There is no spawner. The worker creates each payload with `CreateProcessW` and:
* `PROC_THREAD_ATTRIBUTE_JOB_LIST` with a new Job Object of the attempt, so the payload is in the job before its first instruction;
* `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` with the stdin source and the output pipe ends only;
* `CREATE_NEW_PROCESS_GROUP` and `CREATE_UNICODE_ENVIRONMENT`.

The job has `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `ACTIVE_PROCESS` from `limits.pids`, `JOB_MEMORY` from `limits.mem_mib`, and no `BREAKAWAY_OK` or `SILENT_BREAKAWAY_OK`. Its handle has `bInheritHandle = FALSE`. When the worker dies, the last handle closes and the kernel ends every process of the job. Minimum: Windows 10 or Server 2016.

Polite signal: `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, group)`. It reaches only a group that shares the console of the caller [EV-047]. A worker with no console calls `AllocConsole` at start and hides its window. A GUI program ignores console events; the ladder then reaches `TerminateJobObject`.

No second process holds the fence on Windows. A worker that is suspended but alive keeps its attempts alive (risk K-13).

## 4. Containment rungs per OS

The worker advertises its rung in `caps.containment`. The rung decides what the tree kill finds.

| Rung | Where | Mechanism | Guarantee | What escapes |
| --- | --- | --- | --- | --- |
| `cgroup` | Linux, the worker runs in a delegated cgroup2 subtree (a systemd user service with `Delegate=yes`, a container with a writable cgroup namespace) | the worker moves itself, the spawner and the keepers to the leaf `<own>/worker`, enables `memory pids cpu` in `<own>/cgroup.subtree_control`, and puts each payload in `<own>/a-<task_id>.<attempt_no>`. Kill: `cgroup.kill` (Linux 5.14), else freeze and `SIGKILL` each pid until `cgroup.events` says `populated 0` | every process of the attempt, whatever it did with sessions, groups or environment; tree accounting (`cpu.stat`, `memory.peak` from Linux 5.19); enforced `memory.max` and `pids.max` | a process that another daemon starts on request (D-Bus activation, `at`, a running `tmux` server) |
| `pidns` | Linux, unprivileged user namespaces allowed, and `clone(CLONE_NEWUSER)` then `CLONE_NEWPID` succeeds | the spawner enters a new user namespace once at start and maps its uid to itself; each keeper is PID 1 of a new PID namespace | when the keeper exits, the kernel kills every process of the namespace; no escape by `setsid` or double fork | as `cgroup`. A set-user-ID program gains nothing inside (`sudo` fails); `ps` shows host pids |
| `subreaper` | Linux 3.4 and later, always | the keeper is the subreaper; kill by the walk of section 2.4 until `ECHILD` | every descendant reparents to the keeper, also after `setsid` or a double fork; exact `residual`; worker death is handled by the spawner | as `cgroup`; an outside `SIGKILL` of worker, spawner and keeper at the same time |
| `reaper` | FreeBSD | the keeper calls `procctl(PROC_REAP_ACQUIRE)` and `PROC_PDEATHSIG_CTL`; kill with `PROC_REAP_KILL` and `REAPER_KILL_SUBTREE`; `residual` from `PROC_REAP_GETPIDS` | as `subreaper` | as `subreaper` |
| `job` | Windows 10 and later | section 3 | every process that a process of the job creates; worker death ends the job; job accounting and limits | a process that another service creates on request (WMI, Task Scheduler, a COM local server) |
| `session` | macOS, OpenBSD, NetBSD, `--lite` | the payload is in a new session; kill the groups of the session; on macOS also scan the processes of the uid (`sysctl KERN_PROC_UID`) for that session id or the tag `PODSWARM_ATTEMPT=<task_id>.<attempt_no>` in the environment | processes that stay in the session or keep the tag | `setsid` plus a cleared environment; orphans reparent to `launchd` or `init` |

Order on Linux: `cgroup` when `/proc/self/cgroup` names a cgroup2 directory whose `cgroup.procs` and `cgroup.subtree_control` the worker can write; else `pidns` when the combined clone probe passes; else `subreaper`. The worker flag `--containment RUNG` caps the rung (default: the best that the probe finds). The `pidns` rung is refused by default on Ubuntu 24.04, on Android, under the default seccomp profile of docker, and where `user.max_user_namespaces` is 0 [EV-048].

File 09 says which delivery contract needs which rung. M0 has the rungs `subreaper` (Linux), `session` (macOS) and `job` (Windows); `reaper`, `pidns` and `cgroup` follow (file 22).

## 5. Kill ladder and `residual`

A timeout (`timeout_s`), a `cancel{kill}`, the polite time of the fence, a drain or lifetime end, a limit, a `revoked` answer and worker exit start the ladder:
1. Polite signal: `SIGTERM` to every process of the attempt (on `cgroup` to each pid of `cgroup.procs`; on `subreaper`, `pidns` and `reaper` to each descendant of the keeper; on `session` to each group of the session); `CTRL_BREAK_EVENT` on Windows.
2. Wait `kill_grace_s` (shape field; its default and range are in file 05).
3. Kill the tree by the mechanism of the rung (table of section 4); `TerminateJobObject` on Windows.
4. Wait up to 5 s, the bound of the `pod-supervise` tree walk (section 2.4). Count the processes that are left as `residual`.

When the 1 s tick finds the fence kill time already past (after a suspend), the worker and the spawner skip steps 1 and 2. Once the polite signal of the fence is sent, the attempt ends as `killed`, reason `self_fence`, whatever its exit status (file 05). A process in uninterruptible sleep can outlive `SIGKILL`; it is counted in `residual`.

`residual` is a `pod_job::Residual`: a count on every rung except `session`, where it is the count of the processes that the scan finds. The authority shows a nonzero `residual` as a warning on the attempt.

## 6. Restart sweep

The sweep matters only when the worker, the spawner and the keepers all died together. At start, before `hello`, the worker reads the attempts of its journal that have a `spawn` record and no `result`. For each it kills a live process only when all three hold:
* its session id or group id is the recorded payload pid;
* its start time (field 22 of `/proc/<pid>/stat`) lies between the recorded attempt start and the start of this worker;
* the recorded boot id equals `/proc/sys/kernel/random/boot_id`.

On `cgroup` the worker also writes `cgroup.kill` of each leftover `a-*` cgroup and removes it. On macOS the tag is a fourth match. Then the worker writes a result `killed`, reason `orphan_cleanup`, for each such attempt.

## 7. Limits and accounting

Each limit has one mode per rung. The worker reports the modes in `caps.limits`. The vocabulary is `enforced` (the kernel stops it), `polled` (the keeper measures and kills), `reported` (measured, not stopped), `none`. `polled` is a podswarm value beside `pod_job::LimitMode` until ask P-8 (file 21) adds it [EV-049].

| Limit | `cgroup` | `pidns`, `subreaper`, `reaper` | `job` | `session` |
| --- | --- | --- | --- | --- |
| `mem_mib` | `enforced` (`memory.max`) | `polled` | `enforced` (commit) | `polled` |
| `cpu_s` | `polled` (`cpu.stat`) | `polled` | `enforced` (job time) | `polled` |
| `pids` | `enforced` (`pids.max`) | `none` | `enforced` (active processes) | `none` |
| `fsize_mib` | `enforced` per file | `enforced` per file | `none` | `enforced` per file |
| `as_mib` | `enforced` per process | `enforced` per process | `none` | `enforced` per process |
| disk | `polled` | `polled` | `polled` | `polled` |

* Memory. The keeper sums `RssAnon + RssFile` of every process of the tree from `/proc/<pid>/status` once per second, and kills the tree above `mem_mib`. On `cgroup` a rise of `oom_kill` in `memory.events` is the same event. The result has outcome `signaled` with reason `mem_exceeded`. `RLIMIT_AS` is set only from `limits.as_mib`: Go, the JVM, V8 and sanitizers reserve much more address space than they use, and fail at start under an address cap. On Windows the job memory limit is a commit limit: an allocation fails, nothing is killed.
* CPU. The keeper sums `utime + stime` of the live tree and the reaped children once per second, and kills above `cpu_s` (reason `cpu_exceeded`). `RLIMIT_CPU` is also set per process as a guard. Reported CPU time is the tree total.
* File size. `RLIMIT_FSIZE` from `fsize_mib`, per file.
* Core files. `core`: boolean, default false: true lets the payload write a core file (`RLIMIT_CORE` at its hard limit).
* Disk. The worker reads `statvfs` of each task file system once per second while attempts run. Below the reserve (the larger of 5 percent and 512 MiB, worker setting `disk_reserve`) it walks the running task directories once, kills the attempt whose directory grew most since the last check (reason `disk_full`), returns the queued attempts of the worker as `not_started`, and pulls no work until the free space is above the reserve. The journal and the key stay writable because the worker stops before the reserve is gone.
* Peak memory in the result is the largest single process (`ru_maxrss`), except `memory.peak` on `cgroup` and the job peak on `job`.
* A name in `needs.limits_required` matches a worker whose mode for that limit is `enforced` or `polled`.

A kill for `mem_exceeded`, `cpu_exceeded` or `disk_full` is outcome `signaled` with that reason, so it counts as a failure and uses `retries` (D-22). These are not reasons of `killed` (file 05).

## 8. Scheduling class, OOM score and CPU slots

* Every payload gets `oom_score_adj` +500, so the kernel picks a task before the worker (score 0).
* `--background`: the payload gets `SCHED_IDLE`, I/O class idle and `oom_score_adj` 1000; on macOS `PRIO_DARWIN_BG`; on Windows `IDLE_PRIORITY_CLASS`. Off by default.
* `--nice N`: `setpriority` of the payload to N (0 to 19). Default 0.
* `--pin-slots`: the worker splits its own allowed CPU mask (`sched_getaffinity`, which already reflects Slurm or `taskset`) into one list per slot; the payload calls `sched_setaffinity` and sees `TASK_CPUS`, for example `2,3`. Off by default.

## 9. Output

* Two pipes, stdout and stderr. The shape field `merge` (file 05, CLI `--merge`) gives one pipe for both, so the order between them is exact; the result then has one stream `out`.
* The worker always drains every pipe. A payload never blocks because the worker stopped reading, except in the two cases below (a full spill file, an attached attempt).
* Capture. The result keeps a head and a tail of each stream: the head is the first `capture_max / 2` bytes, the tail the last `capture_max / 2` bytes. A stream not longer than `capture_max` is sent whole as the head. `len` counts every byte; `trunc` is true when bytes were dropped. Each part is UTF-8 text when it is valid UTF-8, else base64; the field `enc` of the stream is `utf8` when both parts are UTF-8, else `base64` for both. The shape field `capture_max` has its default and its maximum in file 05, which also shows that a result at the maximum fits one control message. A whole stream goes to a blob when the shape sets `capture_blob` (file 15).
* Live stream. Each stream of an attempt that has a subscriber is one `io` bulk stream (`ch` `stdout` or `stderr`, file 05), with its own credit (the stream window of the link, file 04). The worker keeps no copy of bytes it sent. A subscriber that attaches late gets the bytes from that time on, and the head and tail in the result. With no subscriber nothing is streamed.
* Spill file. When a stream has no credit, the worker appends its bytes to `<root>/<task_id>.<attempt_no>.out/<stream>`, beside `TASK_DIR` on the same file system (section 12), and sends them in order when credit returns. Limit `spill_max`: 64 MiB per attempt, and 25 percent of the free space of that file system for all attempts. Only when the spill file is full does the worker stop reading that one pipe: that payload blocks, no other.
* An attached attempt (file 05) has no spill file: a stream with no credit stops the read of its pipe, and the payload blocks as it does under ssh.
* Output is untrusted text. The worker passes the bytes unchanged. The CLI shows control characters as escapes (file 18).

## 10. Environment

The worker builds the exact environment of the payload. Nothing is inherited past this rule (D-67). The credential deny list of variable names is in file 13, section 5; the policy key `deny_env` (file 16) extends it.
* The local worker of a session (on the caller's machine) passes its own environment minus the rows of the deny list that file 13 marks for every worker.
* An attached command of `podswarm run` on a remote worker: the home puts the caller's environment, minus the whole deny list, into the shape `env`. The worker then sets `PATH`, `HOME` and `TMPDIR` for its own machine. An absolute path value passes only under the rule of file 06 (section 14).
* An attempt of a queued task on a remote worker gets only this allowlist from the worker's own environment: `PATH`, `LANG`, `LC_*`, `TZ`, `USER`, `LOGNAME`, `HOME`, `SHELL`, and the names of the policy key `env_pass` (file 16). On Windows also `SystemRoot`, `SystemDrive`, `windir`, `ComSpec`, `PATHEXT`, `USERPROFILE`. A forwarded agent, Kerberos caches and cloud credentials of the worker host never reach a task by default. Reason: such a worker can serve other submitters.
* The shape field `inherit_env` (file 05) is true by default on the local worker and false on a remote worker. When it is true, the worker passes its own environment minus the deny list in place of the allowlist.
* Then, in this order, each overriding the previous: the shape `env`; the `TASK_*` set (section 13); `TMPDIR` (and `TEMP`, `TMP` on Windows) set to `$TASK_DIR/tmp`.
* `HOME` is the real home on boundary `none`, and `TASK_DIR` on `confined` and above.
* A deny-listed name reaches a task only when the submitter names it: `--env NAME=VALUE`, or `--env-allow NAME` (file 13). Names compare without case on Windows.
* The worker computes the filtered base environment once at start, not per attempt.

## 11. Shell

* Resolution at worker start: `--shell PATH`; else `sh` on the worker `PATH`; else `/bin/sh`; else `/system/bin/sh` (Android). The worker then runs `sh -c 'echo "${BASH_VERSION:-}${ZSH_VERSION:-}"'` and `sh -c true` once, and advertises `caps.shell{path, kind, start_us}` with `kind` one of `dash`, `bash`, `ash`, `mksh`, `zsh`, `unknown`.
* `needs.shell` names a kind. `psw x --shell bash` runs `bash -c` and adds that need (file 18).
* A host needs a POSIX `sh` (busybox `ash` is enough) only for `shell` tasks. `argv` tasks need nothing.
* Auto-argv: when a `shell` command, after expansion, holds none of `` $ ` \ " ' | & ; < > ( ) [ ] * ? ~ # { } `` and no newline or tab, the worker splits it on spaces and runs it as `argv`. The result equals `sh -c` for such a string, and it saves one exec and one shell start. The shape field `shell_always` (bool, default false, CLI `--shell-always`) turns it off (D-69).
* The worker resolves the program of an `argv` task against the effective `PATH` itself and calls `execve` with an absolute path.
* Windows: shell mode is `cmd.exe /d /s /c "<command>"`, built as a raw command line with exactly one outer pair of quotes. With `--shell pwsh` it is `pwsh -NoLogo -NoProfile -NonInteractive -EncodedCommand <base64 of UTF-16LE>`, which needs no quoting.

## 12. Directories

* `TASK_DIR` is `<root>/<task_id>.<attempt_no>`, mode 0700, unique per attempt. Directories are never reused across attempts: a reused directory leaks the data of one submitter to the next, and a `mkdir` on tmpfs costs tens of microseconds.
* `<root>` is `$XDG_RUNTIME_DIR/podswarm/tasks` (a per-user tmpfs) when it exists, the task stages no file, declares no output and has `needs.disk_mib` under 64. Else it is `<state>/tasks`. This keeps the writes of short tasks off an SD card. At shield `private` and above, `<root>`, `TMPDIR`, the spill files and the journal are in the work area of file 13 (section 6.2).
* `TMPDIR` is `$TASK_DIR/tmp`. Many hosts have a small `/tmp`.
* Effective `cwd`: with a view, the caller's absolute path inside the view (file 06); without a view, a relative `cwd` under `TASK_DIR` (the path rule of file 16), or `TASK_DIR` itself. The local worker of a session uses the caller's directory. Without a view, a remote worker accepts an absolute `cwd` only with `shared_fs` and the policy key `allow_abs_cwd` (file 16), else `spawn_failed`, reason `policy`.
* Removal: after the result is sent and outputs are uploaded, the worker renames `TASK_DIR` to `<root>/.trash/<seq>` and removes the trash when no attempt is starting. It removes at once when the trash holds more than 1,000 entries or the disk is under the reserve.
* Worker state directory: `S/worker-<hostname>`, with `S` the state directory of file 19. When `SLURM_JOB_ID`, `PBS_JOBID` or `LSB_JOBID` is set: `${TMPDIR:-/tmp}/podswarm-<uid>-<jobid>-<hostname>`, node-local, removed at exit. A worker that a home starts over a road uses the directory that file 04 gives; these rules apply to it too.
* The worker refuses a state directory on NFS, SMB, Lustre, GPFS or CephFS (`statfs` `f_type`) unless `--state-on-network-fs`. A shared home on a cluster otherwise gives two workers one key, one journal and one task tree.
* The confine profile never grants the state directory (section 17).

## 13. `TASK_*` variables

| Name | Value |
| --- | --- |
| `TASK_ID` | `task_id`, decimal |
| `TASK_ARGS` | the input line (equal to `{}`) |
| `TASK_COMMAND` | the expanded command |
| `TASK_CWD` | the effective working directory |
| `TASK_RUN` | `run_id` |
| `TASK_ATTEMPT` | `attempt_no` |
| `TASK_PREVIOUS_ATTEMPT` | the `attempt_no` of the previous attempt; absent on the first |
| `TASK_INDEX` | `idx` |
| `TASK_GROUP` | the group; absent when none |
| `TASK_KEY` | the `key`; absent when none |
| `TASK_WORKER` | the `wid`, or the worker name in a session |
| `TASK_DIR` | section 12 |
| `TASK_SLOT`, `TASK_SLOT_COUNT` | the 0-based slot and the slot count |
| `TASK_START_TIME` | Unix seconds at the start of the attempt |
| `TASK_TAG_<K>` | one per tag `K:V` of the task, value `V` |
| `TASK_CPUS` | with `--pin-slots`, the CPU list of the slot |
| `TASK_RES_<NAME>` | the count of named resource NAME that the task needs (file 08) |
| `TASK_SOCK` | the Unix socket of the worker for `checkpoint save` and `key token` (files 15, 17) |
| `TASK_RESUMED`, `TASK_CHECKPOINT_SEQ`, `TASK_CHECKPOINT_DIR` | the restore of a checkpoint (file 15) |

The set lets a program make its own side effects idempotent.

## 14. Journal

* The journal is a directory of append-only segment files in the state directory. Records: `hold` (an attempt the worker accepted), `spawn` (written before `Spawn`; it holds the attempt start time and the boot id), `pids` (the payload pid and start ticks from `Running`), `result`.
* The worker uses `write(2)` only and never `fsync`, except one: the `spawn` record of an `at_most_once` attempt is synced before `Spawn` is sent. The page cache survives a link cut and a crash of the worker process; a power loss re-runs `at_least_once` tasks, which their contract allows.
* A segment is deleted when every attempt in it has its `ack`. A restarted worker sends the results of its journal again; a duplicate gets `recorded` or `dropped` (file 05).
* Cap: 10,000 records or 64 MiB. At the cap the worker pulls no new work until a segment is deleted.
* A worker whose stored `gen` differs from the authority's deletes its journal (file 05).

## 15. Probe, runtime, allocator

* At start the worker runs a targeted probe of six rows in one child (a re-exec of its own binary): Landlock ABI (`pod_confine::check`), seccomp, child subreaper, pidfd, the combined user and PID namespace clone, cgroup2 delegation. It caches the answer in the state directory, keyed by kernel release, boot id and the BLAKE3 hash of the binary. `psw doctor` runs the full probe of `pod-hostprobe`. [EV-050] The two missing rows are ask P-6 (file 21).
* Runtime: the current-thread runtime on the worker. The worker learns of process events from the spawner socket only.
* Allocator: mimalloc on musl builds. The musl allocator is slow for allocation-heavy Rust code.

## 16. Cost per attempt

A-05 counts the CPU of the worker process and the bookkeeping of the spawner for one `argv` task that runs `true` with no capture subscriber. The forks and the exec are the start cost; A-06 bounds the whole. Each row is a target share [T]; test B-03 of file 23 measures it.

| Item | x86_64 us | Cortex-A53 us |
| --- | --- | --- |
| offer decode, share of a bundle of 100 | 1 | 5 |
| template expansion, argv and envp (base environment made once) | 3 | 15 |
| `mkdir` of `TASK_DIR` and `tmp` on tmpfs | 6 | 30 |
| `Spawn` message, two `pipe2`, `SCM_RIGHTS` | 6 | 30 |
| `Running` and `Ended` messages | 4 | 20 |
| pipe reads to end of file, capture copy | 4 | 20 |
| result encode, share of a batch | 1 | 5 |
| journal `write(2)`, three records | 4 | 20 |
| rename and later removal of `TASK_DIR` | 6 | 30 |
| **A-05 total** | **35** (target 60) | **175** (target 300) |
| keeper fork | 30 to 60 | 150 to 300 |
| child state and payload fork | 30 to 60 | 150 to 300 |
| Landlock and seccomp in the child (`confined` only) | 20 to 50 | 100 to 250 |
| exec and exit of `true` (static; dynamic adds the loader) | 150 to 700 | 300 to 1,500 |
| `sh -c` for a `shell` task (dash; bash is 3 to 5 times more) | 700 | 3,000 |

What dominates: the exec of the payload, then the two forks; for a `shell` task the shell start, which auto-argv removes for plain commands. The p99 depends on blocking writes to slow flash, which tmpfs task directories and a journal with no `fsync` keep off the path. [EV-051]

A-06: one 4-core Cortex-A53 worker runs at least 400 `true` tasks per second [T]. That is 10 ms of core time per task; the sum of the table is under 2 ms.

## 17. Boundary `confined`

File 13 owns the boundary axis and the promise of each boundary. This section says how the worker makes `confined`. It is Linux only.

### 17.1 What the crate gives

`pod_confine::Spec` gives Landlock path rules (read, write, execute), TCP `connect` and `bind` port lists, the Landlock scopes (signals and abstract Unix sockets), a closed UDP, a seccomp deny list, `no_new_privs`, and a capability mask. The work has three steps: `check` before the fork (the probe of section 15), `Spec::compile` before the fork (in the keeper: each path opens as `O_PATH`, the BPF program is built), and `apply` in the payload child with no allocation. There is no unconfined way through: a refused call stops the exec. The default deny list makes `ptrace`, `process_vm_*`, the mount calls, namespace creation, `bpf`, `keyctl` and `io_uring_*` fail. podswarm uses `Spec::no_caps()`.

### 17.2 Features by Landlock ABI

The worker advertises `confined` only when `check` returns ABI 3 or more, and lists its features in `caps.confine`:

| Feature | Needs | Gives |
| --- | --- | --- |
| `confine_fs` | ABI 3 (Linux 6.2) | path rules, `truncate` |
| `confine_tcp` | ABI 4 (Linux 6.7) | TCP port lists |
| `confine_scope` | ABI 6 (Linux 6.12) | no signal and no abstract socket out of the domain |
| `confine_unix` | ABI 9 | a connect to a pathname Unix socket made outside the domain needs a write rule |
| `confine_udp` | ABI 10, or the seccomp rule where the target allows it | closed UDP |

[EV-052]

A shape field that needs a feature matches only a worker that has it (file 08): `confine.connect` or `confine.bind` needs `confine_tcp`; `confine.udp = false` needs `confine_udp`.

### 17.3 Default profile

| Path | Access |
| --- | --- |
| `/usr`, `/bin`, `/sbin`, `/lib`, `/lib32`, `/lib64`, `/opt` | read, execute |
| `/etc`, `/proc`, `/sys` | read |
| `/dev/null`, `/dev/zero`, `/dev/full`, `/dev/random`, `/dev/urandom` | read, write |
| `TASK_DIR` | read, write, execute |
| the shell of `caps.shell` and its directory | read, execute |
| `$PREFIX` on Termux | read, execute |

A path that does not exist on the host is left out before the compile. TCP and UDP are free unless the shape closes them. The scopes are on where the ABI has them. The profile never grants the worker state directory, the blob cache or another `TASK_DIR`. A read of `/proc/<worker pid>/environ` fails: Landlock gives ptrace-class access only to a process in a sub-domain, and the worker is not dumpable.

### 17.4 Fields

The shape `confine` object (file 05 holds the shape):

| Field | Type | Effect |
| --- | --- | --- |
| `read`, `write`, `exec` | list of at most 64 paths of at most 1,024 bytes | a rule on top of the default profile |
| `connect`, `bind` | list of ports, or absent | absent: free; a list: only those ports; empty: none |
| `udp` | bool, default true | false closes UDP |
| `unix` | bool, default false | true keeps `socket(AF_UNIX)` below ABI 9 |

An absolute path in `read`, `write` or `exec` outside the policy keys `confine_allow_read`, `confine_allow_write`, `confine_allow_exec` (file 16) is refused with `policy`. A relative path is under `TASK_DIR`.

### 17.5 `AF_UNIX` below ABI 9

Below ABI 9 Landlock does not check a connect to a pathname Unix socket. There the profile adds a seccomp rule: `socket(2)` with domain `AF_UNIX` fails with `EACCES`, unless the shape sets `confine.unix` and the policy key `allow_unix` (file 16) allows it. `socketpair(2)` stays free: an unnamed pair reaches nobody. This stops a confined task from driving the local admin socket of a coordinator of the same uid. On i686, s390x and powerpc64 a seccomp rule cannot see the domain of a socket, so there the worker advertises `confined` only with ABI 9 or more. [EV-053]

### 17.6 Where it is applied

The keeper compiles the spec after its fork from the spawner and before it forks the payload. The payload calls `pod_confine::apply` as the last step before `execve` (section 2.5). The worker process itself is never confined.

## 18. Hooks to other files

### 18.1 Terminal
An attempt with `io = attached` and `pty` gets a pty. The keeper opens it, and the payload child makes the slave its controlling terminal (`TIOCSCTTY` after `setsid`) and fds 0, 1, 2. The master goes to the worker in `Running`. Window size and signals arrive as messages (file 05).

### 18.2 View
Before exec, the keeper enters the mount namespace or installs the filter that the view rung needs, and the child sets `cwd` inside the view (file 06).

### 18.3 Spreading
The keeper is the exec supervisor of file 07. The payload child installs the exec filter as its last step before `execve`, after confinement, and passes the listener to the keeper by `SCM_RIGHTS`. A `confined` exec grant includes the stub binary of file 07. The kernel takes one seccomp listener per filter chain, so a spread session uses neither the view rung `trap` (file 06) nor the network hold `notify` (file 14).

### 18.4 Shield, `sandbox` and `vm`
At shield `guest` and `sealed` the payload runs inside a guest that runs its own worker, and the rules of this file apply inside the guest (file 13, section 7.3). At boundary `sandbox` or `vm` with a lower shield, this worker drives podvm and the keeper holds the podvm process (file 24).

### 18.5 Network
The network policy of the attempt is applied to its process tree before exec (file 14).
