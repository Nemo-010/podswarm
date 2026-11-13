# 7. Spread: the single system image ladder

This file is the home of the owner's requirement that the pooled machines behave "as if the whole system behaved as a whole". It defines step 1 of the ladder of file 01 in full (exec-level spreading: each process that a program starts can run on another machine) and states steps 2 and 3 (move a running process, pooled memory) as goals with their limits. File 05 holds the attempt and the `exec` stream header, file 06 the view, file 08 the pool and the placement score, file 12 the keeper, file 13 the shield, file 14 the network policy, file 15 checkpoints.

## 1. The ladder

| Step | What it gives | State |
| --- | --- | --- |
| 1 | Every `execve` of a program (each compiler that `make` or `cargo` starts, each command of a script) can run on another pooled machine with the same files, environment, pipes, signals and exit code, with no per-tool setup. | designed here; milestone M3 (section 17, file 22) |
| 2 | A running process moves to another machine. | stated goal, section 19 |
| 3 | The memory of the pool is one resource. | stated goal, section 20 |

One process lives on one machine at a time. A process tree may span machines.

## 2. The model of step 1

| Term | Definition |
| --- | --- |
| spread session | One root command of `podswarm run --spread` (or one attempt of `podswarm x --spread`) and all its descendants. It has one id, one session cookie (32 random bits), one file view, one exec table snapshot and one set of members. |
| origin | The caller's machine: the truth of the workspace; it serves the lower layer of the view (file 06). |
| anchor | The machine that runs the root process, and the authority of the files of the spread session: it holds the upper layer, and the writes of members reach it first (section 9). With `podswarm run --spread -- CMD` it is the caller's machine. With `podswarm run HOST --spread -- CMD` it is HOST. The word "hub" means only the relay of file 24. |
| member | A pooled machine that runs moved processes. The anchor is also a member for placement. |
| supervisor | The keeper of file 12 on the anchor, which starts the root under the exec filter. It is the child subreaper of the tree, holds the seccomp listener, decides each exec and does the takeover. Each member runs a member supervisor (the keeper of each moved process) with the same filter, so the children of a moved process can spread again. |
| stub | The image that a moved process becomes on the machine where it called `execve`. It is the podswarm binary with an internal flag. It keeps the pid, the parent, the process group, the session, the controlling terminal and the inherited descriptors. It forwards stdio and signals and exits with the remote status. |
| moved process | The real program, run by a member. On the member it is an attempt of that member's worker (section 8). |

What "the same" means for a moved process: the parent sees the same pid, the same stdio bytes in the same order, the same signals, the same job control and the same exit status as for a local child. The moved process sees the same argv, environment, working directory, file paths and file contents. It does not see the same pid, the same `/proc` or the same uid (sections 5 and 10).

Why exec time: a new image has no memory to carry. Kernel single system images that moved memory did not survive their kernel ports; user space and exec time are the durable layer.

## 3. How an exec is caught

### 3.1 Rungs

| Rung | Systems | Catches | Misses | Default |
| --- | --- | --- | --- | --- |
| `seccomp` | Linux 5.5 and later, Yama `ptrace_scope` 0 or 1 | every `execve` and `execveat` of every binary: static, Go, a raw system call | the power of set-user-ID and file-capability programs (section 3.5) | yes |
| `shim` | Linux, macOS, FreeBSD | an exec that searches `PATH` by name | an exec by absolute path (a `rustc` of a toolchain, `/usr/bin/cc` in a Makefile) | macOS; Linux when `seccomp` fails its probe |
| none | Windows | the root command only | every child | Windows |

* `shim`: a session directory of links to the stub binary is first in `PATH`. A link execs the stub, which decides as the supervisor does and execs the real program by the rest of `PATH` when it stays local. On macOS, `DYLD_INSERT_LIBRARIES` is not a rung: System Integrity Protection purges it at the first protected program such as `/bin/sh`.
* Windows: a caller on Windows spreads by running the root on a Linux member: `podswarm run HOST --spread`.
* Not used: `ptrace` of every process (it costs 500 times per system call and stops debuggers in the session); an `LD_PRELOAD` interposer (it misses static and Go programs; later fallback for hosts with Yama 2).
* The supervisor names the rung it entered in `-v` output and in the run report (section 14).

### 3.2 The `seccomp` rung, step by step

1. **Filter.** The payload child of the keeper sets `PR_SET_NO_NEW_PRIVS` and installs one filter with `SECCOMP_FILTER_FLAG_NEW_LISTENER` as the last step before its `execve` (file 12, child state). The filter returns `SECCOMP_RET_USER_NOTIF` for `execve` and `execveat`, and for `sched_getaffinity` and `sched_setaffinity` (section 11), except an `execve` whose fourth argument register (low 32 bits) equals the session cookie. Every other call is allowed. The child sends the listener to the keeper by `SCM_RIGHTS` and closes it. Every descendant inherits the filter, also through `setsid`, a double fork and `vfork`.
2. **Notification.** The supervisor reads the request, then the path and, when the decision needs it, argv from the memory of the calling thread (`pod_hold::mem`).
3. **Decision.** The supervisor runs section 6 with no network call.
4. **Local.** It answers `SECCOMP_USER_NOTIF_FLAG_CONTINUE`. The kernel runs the exec. Cost: section 4.
5. **Move: seize.** It calls `PTRACE_SEIZE` on the calling thread with `PTRACE_O_TRACEEXEC`, marks that thread `armed`, then answers `CONTINUE`. The kernel runs the real exec, with the real path search, `#!` handling and permission checks.
6. **Errors of a failed exec.** When the exec fails (`ENOENT`, `EACCES`, `ENOEXEC`), the caller gets the error of the kernel unchanged. `execvp` tries the next `PATH` entry, which notifies again for the same thread; the supervisor keeps the seize and answers `CONTINUE`. An armed thread with no exec stop within 1 s is interrupted (`PTRACE_INTERRUPT`) and detached. An armed thread that exits is forgotten.
7. **Exec stop.** At `PTRACE_EVENT_EXEC` the new image exists and has run no instruction. In a process with threads the stop arrives on the thread group leader; `PTRACE_GETEVENTMSG` gives the former thread id. The supervisor reads the final argv and environment from `/proc/PID/cmdline` and `/proc/PID/environ` (they hold the kernel's `#!` rewrite) and the resolved program from `/proc/PID/exe`.
8. **Takeover.** The supervisor writes a trampoline at the entry point (`mov eax, 59; syscall` on x86_64; `mov x8, 221; svc #0` on aarch64), writes the stub path and the stub argv below the stack pointer, sets the argument registers (path, argv, the original `envp`) and the cookie in the fourth argument register (`r10` on x86_64, `x3` on aarch64), and continues the thread. The trampoline exists because the kernel writes the return value of the first exec into the register that holds the system call number after the event stop.
9. **Marker.** The stub's own `execve` carries the cookie, so the filter allows it and the supervisor gets no notification for it. Without the cookie the supervisor waits on its own notification and the tree hangs. The cookie is not a secret. A program that puts the cookie in that register by chance runs local, which is correct.
10. **Detach.** At the second exec stop (the stub), the supervisor calls `PTRACE_DETACH`. The pid did not change. When the stub exec fails, the supervisor kills the process with `SIGKILL` and the run report names the cause.
11. **States.** The supervisor is event driven: one state per armed thread, with the events exec stop, new notification of the same thread, signal stop (passed on with `PTRACE_CONT` and the signal), and exit.

The time-of-check race of `CONTINUE` does not matter here: the decision is a placement choice, not a security check.

### 3.3 Kernel floors and the probe

| Leg | Floor |
| --- | --- |
| seccomp filter with `NEW_LISTENER` | Linux 5.0 |
| `SECCOMP_USER_NOTIF_FLAG_CONTINUE` | Linux 5.5 |
| `PTRACE_SEIZE` of a descendant: Yama `ptrace_scope` 0 or 1 (the keeper is the ancestor of each process of the tree, because it is the subreaper) | Linux 3.4 |
| x86_64 or aarch64 for the trampoline | |

A probe leg of `pod-hostprobe` checks each row once per (kernel release, boot id, binary hash), in the probe cache of file 12. When a leg fails, the session prints `podswarm: spread: seccomp rung not available: <leg>` and takes `shim`.

### 3.4 One listener per process

The kernel refuses a second filter with a listener in one filter chain (`EBUSY`). [EV-020] The view rung `trap` (file 06) and the network hold rung `notify` (file 14) also use a listener. Rules:
* A member uses a FUSE rung or `sync` of file 06; a machine with only the view rung `trap` is not a member. The anchor uses the real file system or a FUSE rung.
* Until one combined filter serves exec, `open` and `connect` from one keeper, a spread session takes the network hold `netns` or `env` (file 14). When the policy needs `notify` and the host has no `netns`, the session runs with no spreading and `-v` says `spread: off: listener in use by net`.
* A program in the session that installs its own listener (a sandbox, a container tool) gets `EBUSY`. A podswarm command inside a spread session does not install a second filter; it runs under the outer session.

### 3.5 What a host without it gets

* `PR_SET_NO_NEW_PRIVS` is set for the whole tree: a set-user-ID or file-capability program runs with no privilege (`sudo` fails). The CLI states this in the help of `--spread`.
* Yama 2 or 3: rung `shim`, then none. Linux before 5.5: `shim`. With no rung the command runs on one machine (file 08) and `-v` says why.

## 4. Measured cost

Costs on one machine: a 4-vCPU guest, x86_64 at 2.3 GHz, Linux 6.18; 5,000 iterations, two runs; static and dynamic `true`.

| Case | Cost per exec | Share |
| --- | --- | --- |
| bare fork, exec, wait | 626 to 1,084 us over two runs (the host load differs) | |
| `seccomp` rung, exec stays local | +30 to +130 us | 5 to 12 percent |
| other system calls under the filter | 87 to 132 ns against 78 to 105 ns bare | +7 to +30 ns |
| `seccomp` rung, exec moves (seize, real exec, takeover, stub exec), before the network | +140 to +520 us over a direct exec of the stub | |
| `shim` rung, one extra exec | +500 to +700 us | about 70 percent |
| `ptrace` of every call | 1,519 to 3,066 us per exec; 40 to 50 us per `getppid` | not used |

[EV-021] It shows the cost of each way to catch an exec. It does not show the decision, the takeover, the network or a machine with many busy cores.

[EV-022] It shows the mechanism of section 3.2 on x86_64 with `/bin/sh` as the stub. It does not show aarch64, a caller with threads, a `#!` script, the real stub or a member.

[EV-023] It shows the cost of one extra exec. It does not show what a `PATH` rung misses or the cost on macOS.

## 5. What crosses an exec

"Local" means the process does not move; the reason goes to the decision record (section 14).

| State | Rule |
| --- | --- |
| argv, environment | Cross as read at the exec stop, after `#!` handling. The variable rule of file 13 (section 5) applies when the member is not the caller's machine. |
| working directory | Crosses as a path of the view. |
| umask, nice, resource limits | Cross. A hard limit above the member's hard limit is lowered to it, and `-vv` logs it. |
| signal mask, ignored signals | Cross (`SigBlk`, `SigIgn` of `/proc/PID/status`). `nohup` works. |
| parent-death signal | Crosses. When the stub dies, the member sends that signal. |
| uid, gid, groups | Do not cross. The process runs as the member account. The view shows file owners as the attempt's uid (file 06). |
| pid, parent pid, group, session, controlling terminal | Stay with the stub (section 10). |
| fd 0, 1, 2: pipe, socket pair, FIFO, regular file | The stub copies the bytes through its own descriptor. Shared offsets and `O_APPEND` stay correct, because the stub reads and writes the same open file description. |
| fd 0 that is the same open file description as fd 0 of the parent (`kcmp KCMP_FILE`), and is not a terminal and not `/dev/null` | Local. The stub reads ahead, which takes input from the next reader (`while read l; do cmd; done < f`). |
| fd 0, 1, 2: terminal | The member gives the process a pty with the termios and window size of the anchor's terminal, without `OPOST`, so the anchor's terminal does the output processing. `SIGWINCH` is forwarded. The stub forwards terminal input only when it is the root or the leader of the foreground process group; other stubs do not read the terminal. |
| fd 0, 1, 2: `/dev/null` | Opened again on the member. |
| jobserver of `MAKEFLAGS`, `MFLAGS`, `CARGO_MAKEFLAGS` (`--jobserver-auth=R,W`, `--jobserver-fds=R,W`, `fifo:PATH`) | Replaced. The member makes a new jobserver with (granted cores minus 1) tokens and rewrites the auth string. The anchor's tokens stay with the parent. make, cargo, rustc and ninja share this protocol, so no tool rule is needed. |
| any other inherited descriptor (fd 3 and up without `O_CLOEXEC`): a file, a pipe, a socket, an eventfd, an epoll, a signalfd, a memfd, a pidfd, a terminal, a device | Local, by default. With `spread_unknown_fds = drop` the process moves and gets `/dev/null` at that number. |
| agent sockets named in the environment (`SSH_AUTH_SOCK`, `GPG_AGENT_INFO`, `DISPLAY`, `WAYLAND_DISPLAY`, `DBUS_SESSION_BUS_ADDRESS`) and loopback TCP services | They are not inherited descriptors, so they do not keep a process local. A connect on the member fails. A loopback port of the caller is reachable through `home=PORTS` of file 14. An agent socket never follows. |
| SysV and POSIX shared memory, shared mappings, ptrace relations | Do not cross. An exec drops mappings, so only a name (`shm_open`) breaks: it resolves on the member. |
| CPU count | Section 11. |
| clock | The member clock. File times are moved by the measured offset (section 9.6). |

## 6. Which exec moves

### 6.1 The rules

The supervisor applies the rules in this order. The first rule that answers wins.
1. Spreading is off for the session, or the program matches `--local-only PATTERN` (a basename or a path glob): local.
2. The program file is set-user-ID or set-group-ID, or has file capabilities: local.
3. An inherited descriptor is not movable (section 5): local.
4. The program matches `--remote-only PATTERN`: move; wait for a free member.
5. No member can run the binary natively (section 7): local.
6. Look up the exec table (section 6.2).
7. Unknown program: local when the anchor has a free core, else move when a member has a free core. A wrong guess costs one move while the anchor is full.
8. Known program with predicted CPU `c` under `spread_min_cpu_ms`: local.
9. Compare finish times (section 6.3). Move to the best member M when `t_M < 0.8 * t_L`.
10. Later: when no member is free and the anchor is full, hold the notification up to `spread_hold_ms`, then run local. Only programs with `c >= spread_min_cpu_ms` are held; a shell or `sed` never is. This gives global admission with no `-j` of the tool.

Why 0.8: a move must win by a margin that covers the error of the estimate, as other exec spreaders prefer the local machine near equal speed.

### 6.2 The exec table

* Key: (program identity, option set). Program identity: path, size and mtime of the resolved file; no hash on the hot path. Option set: the hash of the sorted set of distinct option names. An option name is an argument that starts with `-`, cut at the first `=`, and cut to 2 characters when it is one dash, a letter and more characters (`-O2` and `-I/usr/include` give `-O` and `-I`). A lookup falls back to the entry of the program when the option set is new.
* Values: smoothed means of CPU time in reference milliseconds (file 08, speed score), wall time, peak memory, output bytes; the content ids of the 64 first inputs of the last run.
* Update: each exit of a moved or local process in a spread session, with the smoothing `learn_alpha` and the decay `learn_ttl_days` of file 08. At most `spread_table_max` entries; the entry used least recently goes first.
* Place: one file `exec-table` per user in the state directory of the caller's machine. When the anchor is a remote HOST, the caller sends the entries of this workspace at session start; HOST keeps them in memory only and sends the updates back at the end. The table of file 08 (per command) seeds rule 7: a program with an entry there is not unknown.
* Read with no lock: the supervisor maps a read-only snapshot. The home writes the snapshot and a member summary (free cores, speed, round trip, bandwidth, cache summary) to shared memory at most once per 100 ms. The supervisor reads argv only when the program has more than one option set in the table.

### 6.3 The decision

```
s_X   = speed score of X / 1000                       (file 08, section 2.3)
t_L   = q_L + c / s_anchor       q_L = 0 when the anchor has a free core
                                 (cores minus spread_anchor_reserve), else infinite
t_M   = q_M + o_M + c / s_M      q_M = 0 when M has a free core, else infinite
o_M   = rtt_M * (2 + misses) + miss_bytes / bw_M + out_bytes / bw_anchor(M) + 5 ms
```
`misses` and `miss_bytes`: the input ids of the entry that the cache summary of M lacks, and their sizes. `out_bytes`: the learned output bytes. `bw_anchor(M)`: the bandwidth from M to the anchor.

Cost targets of one decision [T]: rules 1 to 6 with a lookup by program only, under 10 us median; with argv read and the option set hashed (argv up to 128 KiB), under 50 us at p99. Target A-29, test U-spread-decide (file 23).

## 7. Placement of a moved exec

* Which member: the lowest `t_M` among the members that pass the filters of file 08 (section 3.2: cell, shield, boundary, capacity, lifetime) and the gate below. Ties: the member with more of the input set warm, then the order of file 08 (section 3.6). A child of a moved process prefers the member of its parent, so the pipes between them stay on one machine.
* Memory gate: the learned peak memory must fit the member's `mem_avail_mib` (file 08) with a margin of 10 percent.
* Architecture and operating system gate: the member must run the ELF machine type of the program and of its interpreter natively, on Linux: x86_64 on x86_64, i386 on x86_64 when the kernel allows it, aarch64 on aarch64. Another architecture stays local. An emulator is not a spreading rung: it is 5 to 10 times slower.
* Where the binary comes from: from the anchor, through the view. A member of a spread session projects every path that a moved process opens outside the export root from the anchor, read only, as a `--with` path of file 06, except `/proc`, `/dev`, `/sys`, `/tmp` (section 9.5) and the credential deny list of file 13. So the compiler, its libraries and its headers are the ones that the root sees. Fast path: when the member's own file at that path has the same content id, the member uses it.
* Prefetch: the move request carries the 64 input ids of the entry, the program and its `DT_NEEDED` closure. The member fetches the missing ones in one batch before it starts the process. The member records each file that the process reads and sends the set with the exit frame. No tool knowledge is needed.
* `spread_tools = member` uses the member's own tools by path. It is allowed only when the anchor is a remote HOST, so that all members and the root use one installation; a different compiler version makes incompatible objects.
* The granted cores of a moved process: 1, or the learned parallelism (`cpu / wall`, rounded up) when it is higher and the member has the cores free.

## 8. The `exec` stream

Each moved process has one `exec` bulk stream (file 05 owns the header). The side whose supervisor moved the process opens it toward the authority of the session, and the authority relays it to the member. This file needs these header fields: `sess` (the spread session id, a u64 that the authority gives), `proc` (the process id in the session, a u64), `role` (`stub` or `member`), and `rx`, `tx` (frame offsets for a resume). Either side may open an `exec` stream, and the authority relays it (file 05, section 7) (D-117).

The feature `spread.1` (file 04) gives the `exec` stream and the view operations of file 06 that a spread session needs. After the header the stream carries frames: `u32` length (big endian), `u8` kind, a body. One stream keeps one order for output, exit and publish numbers, which section 9 needs.

| Kind | Direction | Body |
| --- | --- | --- |
| `req` | stub side to member | one zstd frame of one JSON object; fields below |
| `in`, `in_end` | to member | stdin bytes; end of input |
| `out`, `err` | to stub | bytes, with `pub` (the member's newest write-back sequence of file 06 that precedes them) |
| `sig` | to member | signal number; target `proc` or `group` |
| `stopped`, `cont` | to stub | the process stopped with a signal; it continued |
| `winch` | to member | rows, cols |
| `exit` | to stub | code or signal, `cpu_ms`, `wall_ms`, `rss_kib`, output bytes, the input set, `pub` |
| `lost` | authority to stub | the member is lost; `retry` true or false (section 12) |

Fields of the `req` body (a receiver ignores a field that it does not know):

| Field | Type | Meaning |
| --- | --- | --- |
| `argv`, `env`, `cwd` | array of strings; map; string | The exec arguments, the full environment, the absolute working directory |
| `umask`, `nice` | u32; integer | Inherited values |
| `rlimits` | map of a limit name of file 12 to `[soft, hard]`, null for no limit | Inherited resource limits |
| `sigmask`, `sigign` | arrays of signal numbers | Blocked and ignored signals |
| `pdeathsig` | signal number or null | The parent-death signal |
| `fds` | array of 3 strings: `pipe`, `file`, `tty` or `null` | Kinds of fd 0 to 2 (section 5); `pipe` also covers a socket pair and a FIFO |
| `termios`, `winsize` | object; `{rows, cols}`; only with a `tty` fd | The terminal state of the anchor |
| `jobserver` | `none`, `pipe` or `fifo` | The jobserver kind (section 5) |
| `cores` | u32 | Granted cores (section 7) |
| `vepoch` | u64 | The view epoch (file 06) |
| `prefetch` | array of `b3:` ids, at most 64 | Input ids to fetch before the start (section 7) |
| `prog` | `{path, size, mtime}` | Program identity: absolute path, size in bytes, modification time in nanoseconds |

On the member the moved process is an attempt of its worker for the fence, reconciliation, containment and limits of files 05 and 12. Its `hold` row uses `task_id = proc` with the top bit set. Its request, I/O, signals and exit travel on its `exec` stream, not in `offer`, `io` or `result`. A moved process is a member attempt keyed by `proc`, and its exit travels on its `exec` stream (D-117).

## 9. Files across machines

### 9.1 The anchor

The anchor is the machine that runs the root process. There is no anchor election.
* Anchor = the caller's machine (mode `eager`): processes on the caller read its disk directly. A publish of a member lands the bytes on the caller's disk before it completes.
* Anchor = a remote HOST (mode `lazy`): the root runs on HOST in the view of file 06, and HOST is the anchor in the sense of file 06 (section 12.2 there). A publish moves metadata and the content id to the anchor; bytes move on demand from the member that holds them, through the authority. Projected paths go on to the caller by the write-back of file 06; owned paths stay on HOST.
* The slow-caller case: when the caller's machine is the anchor and its link is slow, each output of a member crosses it in mode `eager`. The user runs the root remote: `podswarm run HOST --spread -- CMD`. HOST is then the anchor and the authority of the members: it opens the roads to the members with its own means (an ssh key of the user's account on HOST, a podssh road). podswarm does not forward the caller's agent for this. A member that HOST cannot reach is not used, and `-v` says why. The caller's machine only serves the view and the terminal.

A member's view server uses the anchor as its file server with the protocol of file 06.

### 9.2 Rule: causal close-to-open

The writes of a moved process (data, create, unlink, rename, mkdir, chmod, utimens) reach the anchor before any event of that process, or of its descendants on the same member, that another process can see:
* a byte of forwarded output;
* the exit status;
* a signal that it sends to a process on another machine;
* the return of `fsync`, `fdatasync`, `syncfs` or `msync`;
* the release of a lock.

In any case a write reaches the anchor within `spread_publish_max_ms` after its close. The mechanism: the member's write-back log to the anchor (file 06, section 10.2) numbers each op. Each `out`, `err` and `exit` frame and each lock release carries `pub`, the newest sequence before it. The stub on the anchor acts only after the anchor applied `pub`. An `fsync` on the member returns after the anchor acknowledged its sequence. So "the compiler exited, so `foo.o` exists" holds for `make`, as on one machine.

A move request carries the anchor epoch at dispatch (`vepoch`). The target view waits until it applied that epoch before `exec`, as file 06 (section 12.1) states for one machine.

### 9.3 What a publish holds

* A file written by the process publishes as a whole at its last close, in close order. A file that the process created and removed before its publish point never crosses (compiler temporaries): the member drops the `put` of a path that it unlinks before the `put` leaves.
* A file opened with `O_APPEND` publishes as an append of the new bytes, so a log that several members append to keeps every line. The write-back log of file 06 has the op `append` for this (D-118).
* Two writers of one whole file: the last publish at the anchor wins. Appenders: every append, in the order of arrival at the anchor. A change by the caller during the run keeps the conflict rule of file 06 (section 10.7).
* Implicit mtime and ctime are moved by the clock offset of the member to the anchor (file 06, section 9). An explicit `utimensat` value passes unchanged.

### 9.4 Reads and grants

* A member keeps the directories and files that it validated under a grant of `spread_grant_s`, renewed while used. An open under a valid grant costs no round trip. A miss costs one round trip to the anchor plus the data.
* Negative entries (`ENOENT`) live under the grant of their directory. Compilers probe many absent headers.
* Invalidation: a publish that changes a path sends `inval` to each member that holds a grant on it. The publish completes, and the causal barrier opens, only after those members answered with the epoch they applied. In a spread session a member answers each `inval` with `vapplied` and its applied epoch (file 06) (D-118). Cost: one round trip, in parallel, only when another member holds a grant.
* Writes on the anchor in mode `eager`: the anchor watches the granted directories with inotify. Before it sends a move request, it drains the inotify queue and sends the invalidations first, on the same ordered link. A write that came before the exec (a writer exited, make waited, make called exec) is in the queue, so causality holds with no extra round trip. A directory beyond `max_user_watches` gets no grant: each open there costs one round trip.

### 9.5 Locks, `/tmp`, listings

* `flock` and `fcntl` locks on a view file of a member go to the anchor, which takes the real lock on the anchor's file for the remote holder. So processes on the anchor and on members exclude each other (`target/debug/.cargo-lock`). The view of a member in a spread session sets `FUSE_FLOCK_LOCKS` and `FUSE_POSIX_LOCKS` for this and sends `vlock` (file 06, section 12.3). Cost: one round trip per lock call. A lock is released when its holder exits or its member is lost.
* `/tmp` on a member: the lower layer is the anchor's `/tmp` (served by path, only files that a process opens); the upper layer is private to the session on the member; the publish rule applies. A parent on A writes `/tmp/x.rsp` and a child on B reads it. Temporaries made and removed on B never cross. `TMPDIR` is not rewritten.
* A directory listing on a member is the anchor's record at the epoch that the member applied, plus the member's own upper entries.
* Writes of a moved process outside the export root and outside `/tmp` stay on the member and end with the session.

### 9.6 Round trips

| Operation | Round trips to the anchor |
| --- | --- |
| open under a grant, read, close | 0 |
| open miss | 1, plus the data |
| exit or first output after writes | 1 plus the upload (`eager`), or 1 (`lazy`); plus 1 when another member holds a grant |
| `fsync` | 1 |
| lock, unlock | 1 |
| move request | 1, plus one prefetch batch |

Not covered: causality through a network socket between two moved processes. A program that needs it calls `fsync`.

## 10. Process identity

* Anchor side: the stub has the pid. `wait`, `kill`, process groups, job control and `ps` work. `wait4` usage shows the small usage of the stub, not the remote CPU, so `time make` shows less user time; the run report gives the pooled CPU.
* Member side, M3: the moved process has a member pid. `getppid()` is the member launcher, which lives as long as the stub, so `kill -0 $PPID` works. A pid file written on a member holds a member pid; a process on the anchor that signals it hits the wrong process. `/proc/self` is the member's.
* Member side, later, where unprivileged user namespaces work: the launcher makes a user and PID namespace and uses `clone3` with `set_tid` to give the parent placeholder the parent's pid and the process the stub's pid. Then `getpid()`, `getppid()` and pid files match the anchor, and a signal to the placeholder is forwarded. This namespace is also the precondition of step 2.
* Signals: a catchable signal to the stub goes to the moved process, or to its member-side process group when the signal went to the group. `SIGTSTP`: the stub forwards it, waits for `stopped`, then stops itself, so the shell sees `WIFSTOPPED`. `SIGCONT`: the stub continues and forwards it. `SIGKILL` of the stub: the stream closes and the member kills the process.
* Exit: code `n` makes the stub exit `n`. Death by signal `S`: the stub sets `RLIMIT_CORE` to 0, sets `S` to its default action and raises `S`, so the parent sees `WIFSIGNALED` with `S`. A core file stays on the member in the session directory.

## 11. The CPU count

`cargo`, `make -j$(nproc)`, `ninja` and language runtimes size their parallelism from the CPU count. A count of the weak anchor would run 4 compilers on a pool of 64 cores. "No per-tool setup" excludes writing `CARGO_BUILD_JOBS`.

* With `spread_cpus = pooled` (the default when spreading), the supervisor answers `sched_getaffinity` with a mask of N bits: N = the cores of the anchor plus the free cores of the reachable members (file 08, section 2.2) at the time of the call, at most 1,024.
* `sched_setaffinity` with bits beyond the real CPUs is cut to the real CPUs and returns success.
* On a member the answer is the granted cores of that process.
* Limits: readers of `/proc/cpuinfo`, `/sys/devices/system/cpu/online` and cgroup `cpu.max` see the real count of the anchor; a program that takes the smaller of the quota and the mask uses the quota. A multithreaded program that stays on the anchor (a linker) can start more threads than the anchor has cores. podswarm does not rewrite `MAKEFLAGS` or `CARGO_BUILD_JOBS`: `make -j N` stays the user's number.

## 12. Failure

* A cut link is not a lost member. The `exec` streams resume at their offsets on a new link (file 04, reattach). The member keeps the process running while the fence of file 05 holds. Nothing is lost and nothing runs twice.
* A member is lost when the fence ends or the member reports its own failure. For each process on it, a silent re-run (on another member, else local) is safe, and runs once, when all hold: the stub forwarded no output byte, no publish of the process completed, the process sent no signal to another machine and took no lock, and its fd 0 is `/dev/null`, a terminal with no forwarded input, or not read. Writes in the dead member's upper layer that never reached the anchor are dropped.
* Otherwise the stub writes one line to its stderr, `podswarm: member NAME lost while PROGRAM ran; not re-run: output already sent`, and exits 75. The build tool reports a failed step. The member is not used again in the session.
* Network side effects of a lost process are not visible to podswarm. With `spread_retry = auto` a process that used the network can run twice. `spread_retry = never` turns re-runs off.
* Loss of the anchor ends the session: each member kills the processes of the session at its fence.

## 13. Shield, network and queue

* **Shield (file 13).** The shield of a spread session is the shield of the root command. Every member must meet it: placement filters by `shield.max >= session shield`. A machine below it is not used; it is never used with a warning. A moved process's upper layer, `/tmp` layer and core files are in the member's work area at `private` and above.
* **Boundary (file 13).** A moved process runs at the boundary of the root. With `confined` the exec grant includes the stub binary.
* **Network (file 14).** A moved process runs under the network policy of the session, applied by the member's worker. Its flows leave from the member's door, so a later move of the process can re-anchor them (section 19.2). The hold rung follows section 3.4.
* **Queue.** A queued task can spread: `podswarm x --spread`, or the shape field `spread` (boolean, default false, file 05) (D-36). In a session the home places the moved processes of each attempt over the session pool and counts them against each member's free capacity as it counts its own attempts. In a swarm, an attempt spreads only over the cores of the worker that runs the attempt, within its `needs.cores_m`; spreading over other workers of a coordinator needs a grant message and comes later. An attempt with `delivery = at_most_once` runs with `spread_retry = never`. The fence of the attempt ends its stubs, and the members then kill the moved processes. A lost member that ends a step with exit 75 fails the attempt; the retry rules of file 09 apply.

## 14. User interface

```
podswarm run [HOST] --spread[=SEL] [--local-only PATTERN]... [--remote-only PATTERN]... -- CMD [ARGS]
podswarm x --spread[=SEL] ...
```
* `HOST` absent: the caller's machine is the anchor. `SEL` absent: the candidate set of file 08 (`[defaults] on`).
* Pool default: `[defaults] spread = "on"` spreads every `run` and `x` with no flag; `--no-spread` turns it off for one command. The default of `spread` is `off`; `on` follows field data.
* `-v` prints at start `podswarm: spread on: rung seccomp, members bigbox lab1 (40 cores), anchor local (eager)` and at exit one summary line: execs seen, moved, kept local by rule, re-run, bytes published, pooled CPU time.
* `-vv` prints one line per decision: `podswarm: cc: moved to bigbox, t_L 2.1 s, t_M 0.6 s` or `podswarm: make: local, rule 3: fd 4 pipe`.
* The run report holds a `spread` object: rung, mode, members, the counts of the summary, and the last 1,000 decisions with rule and numbers.

## 15. Targets and when spreading pays

Model: `T_N = S + (W - S) / P + n_moved * o / P + B_out / bw_anchor`, with `S` the critical path, `W` the total CPU, `P` the pooled sum of core speeds, `o` the overhead of one moved exec, `B_out` the bytes that must reach the anchor.

Example: 1,000 C files of 2 s CPU each on a member core; an anchor of 4 cores at half speed; link of the final binary 20 s. Anchor only: about 1,040 s. With one 32-core member: about 59 s of compile, 2 s of moves, 1 s of publish on a 1 Gbit/s LAN, 40 s of link at the anchor: about 100 s. With the root on the member (`run HOST --spread`): about 80 s. A Rust workspace of 400 crates with 1,200 s of CPU and a critical path of 90 s: 32 cores give about 100 to 130 s, 64 cores about 95 to 110 s. Spreading pays for wide graphs; a deep crate graph is bound by its critical path.

Spreading loses when the CPU per exec is under 3 times `o`, when the outputs cannot cross the anchor link in less time than the compute saved, when the anchor is idle and as fast as the member, and when the program is bound by exec rate (shell scripts).

| Target [T] (file 23) | Condition | Test |
| --- | --- | --- |
| A-24: a build of 1,000 compile steps on 8 pooled machines of equal speed is at least 5 times faster than on one | independent steps of at least 1 s CPU each; round trip under 1 ms; at least 1 Gbit/s; serial tail under 5 percent | B-24 |
| A-30: local exec: interception plus decision under 80 us, and under 10 percent of a bare fork, exec and wait | rung `seccomp` | B-28 |
| A-31: other system calls: under 20 ns extra | rung `seccomp` | B-28 |
| A-32: moved exec overhead `o`: under 2 round trips plus 5 ms warm; under 3 round trips plus 5 ms plus the missing bytes divided by the bandwidth cold | prefetch on | B-28 |
| A-33: a configure-like script (10,000 execs of `sh`, `sed`, `cc -E` under 20 ms each) is at most 10 percent slower than with no spreading | rule 8 | B-28 |
| A-34: efficiency `T_1 / (N * T_N)` at least 0.8 for N up to 4 equal members | at least 500 independent steps of at least 1 s; round trip under 1 ms; at least 1 Gbit/s | B-24 |
| A-35: efficiency at least 0.6 for N up to 4 | round trip 30 ms, 100 Mbit/s; the anchor is a remote HOST in the site of the members | B-24, with a link emulator |
| A-19: a spread session is never slower than 1.1 times the run with no spreading | any build | B-24 |

Tests of behaviour (file 23): U-spread-takeover, U-spread-fds (each row of section 5), U-spread-causal, U-spread-append, U-spread-lock, U-spread-signals, F-50 (a member dies before and after its first output).

## 16. What does not spread

* Threads: one process lives on one machine. A multithreaded program uses the cores of its member.
* Shared memory between processes on two machines, and a process that inherits a descriptor that section 5 does not move.
* A program for another architecture or another operating system than the members.
* Windows callers, except by `run HOST --spread` with a Linux HOST.
* Set-user-ID power inside the session (section 3.5).
* Pids, `/proc` and `wait4` usage across machines (section 10), and the CPU count of `/proc` and `/sys` (section 11).
* Causality through sockets (section 9.6), and writes outside the export root and `/tmp` (section 9.5).
* A program that installs its own seccomp listener (section 3.4).

## 17. Milestones of step 1

M3 (file 22):
* Linux anchors and Linux members of the same architecture; rungs `seccomp` (with takeover) and `shim`.
* The anchor runs the root: mode `eager` on the caller's machine, mode `lazy` on a remote HOST.
* Movable descriptors: 0, 1, 2 as pipes, files, terminals and `/dev/null`; the jobserver rewrite.
* Rules 1 to 9; the exec table; `-v`, `-vv` and the run report.
* Causal close-to-open with grants and invalidation; locks through the anchor; `/tmp` layered.
* The re-run rule of section 12 over reattachable links; `spread_cpus = pooled`.

Later: rule 10 (holding); member pids that match the anchor; one combined filter for exec, view and network; relays of named sockets (opt-in, never for credential agents); an `LD_PRELOAD` rung for Yama 2; member-to-member data in mode `eager`; macOS anchors by `shim` (needs a macOS view); Windows; spreading over the workers of a coordinator.

## 18. Settings of this file

Scope: home, or `[defaults]` of the pool file. File 19 lists the scope and the type of each.

| Name | Default | Range | Effect |
| --- | --- | --- | --- |
| `spread` (`[defaults]`) | `off` | `off`, `on` | spread every `run` and `x` |
| `spread_min_cpu_ms` | 50 | 0 to 60,000 | a known program under it stays local |
| `spread_anchor_reserve` | 1 | 0 to the cores of the anchor | cores of the anchor not counted as free |
| `spread_hold_ms` | 2,000 | 0 to 60,000 | the hold of rule 10 (later) |
| `spread_unknown_fds` | `local` | `local`, `drop` | the rule for a descriptor that does not move |
| `spread_cpus` | `pooled` | `pooled`, `anchor` | the CPU count answer: the pooled cores, or the real count of the anchor |
| `spread_publish_max_ms` | 1,000 | 10 to 60,000 | upper bound from a close to its publish |
| `spread_grant_s` | 30 | 1 to 3,600 | grant of a member on a directory or a file |
| `spread_retry` | `auto` | `auto`, `never` | a silent re-run |
| `spread_tools` | `anchor` | `anchor`, `member` | where the tools come from (section 7) |
| `spread_table_max` | 65,536 | 1,024 to 1,000,000 | entries of the exec table |

The margin 0.8 of rule 9 and the 1 s arm time of section 3.2 are constants.

## 19. Step 2: move a running process

### 19.1 The ladder

1. **A checkpoint that the program writes** (all systems; file 15). The program writes its state to `TASK_CHECKPOINT_DIR`; podswarm stores it as a manifest in the content store and starts the same argv on another machine with `TASK_RESUMED=1`. It is portable and cheap, and it needs the program's help.
2. **A process checkpoint with CRIU** (Linux, opt-in). Only for a process tree that started inside a user, PID and mount namespace that podswarm owns (section 10, later), so that CRIU has `CAP_CHECKPOINT_RESTORE` over it (Linux 5.9) and pids restore with `set_tid`. It needs: the same kernel features on both machines, CPUs that pass `--cpu-cap`, the same view paths, no TCP connection to outside (or a network namespace of its own with TCP repair), terminals handled as external, no GPU, no `io_uring`, no mapped deleted file. CRIU is a separate static helper program that podswarm fetches and runs; it is not linked into podswarm (GPL-2.0). The dump is pre-copy; a post-copy restore with lazy pages runs where `userfaultfd` is allowed. The checkpoint is a manifest of file 15 with `kind = process`.
3. **The migration of a guest** (Linux members with the podvm machine rung). A run inside a guest moves by QEMU live migration. It needs the same QEMU version and a baseline CPU model on both machines. Everything inside moves. The manifest has `kind = guest`.

The stub of step 1 hides each rung from the parent: the stub stays, and only the member behind it changes.

### 19.2 What step 1 keeps stable now

1. Every message names a moved process by session and `proc`, never by a member pid.
2. stdio and signals pass only through the stub.
3. The view is the same on every member: the same paths.
4. All session data is content addressed.
5. The member launcher owns the namespaces of a moved process when it can make them, and records whether it did. A process outside its own namespaces is never offered to rung 2.
6. The network of a moved process leaves through its member's door (file 14), so a move can re-anchor it.

### 19.3 The limit

A running process moves only by one of the three rungs and their conditions. A process that holds an outside TCP connection, a device, a GPU or a descriptor of another process does not move; it ends and restarts from its last checkpoint, or it stays.

## 20. Step 3: pooled memory

What is realistic:
1. **Placement by free memory** (step 1): rule 9 and the memory gate of section 7 use the learned peak memory and the free memory of each member.
2. **Paging a migrated process from its old machine**: a process restored by rung 2 with lazy pages reads missing pages from its old machine for at most `migrate_postcopy_max_s` (later setting); then the old machine is released.
3. **An opt-in far heap**: a library (`podswarm-farmem`: allocate, pin and release objects by handle, backed by the memory of a member over the link). Only a program that links it uses it.

Non-goal: shared memory between machines that a program does not know about. Page-based distributed shared memory exists in research and in kernel single system images, and those died with their kernels; far-memory systems that work need kernel, compiler or library support; remote paging needs root and RDMA.

The limit: podswarm does not give one process more memory than one machine has. It pools memory by placing work where memory is free, by paging a migrated process from its old machine for a bounded time, and by a far heap for programs that use its library. A page fetched over a network costs 10 to 100 us against about 100 ns for local memory, so transparent shared memory between machines is a non-goal. CXL memory pooling is hardware; podswarm uses it only as the memory of one machine.
