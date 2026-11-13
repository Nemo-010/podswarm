# 6. View: the caller's files on another machine

This file defines the view: how a process on a worker sees the caller's directory tree at the same path, how reads come from the caller on demand, how writes land on the caller's machine, and the sync rung that is the fallback. File 05 defines the attempt and the `view` field of its shape, file 07 spreads processes over several machines, file 12 defines the keeper that enters the view, file 13 defines the shield and the credential rules, file 15 defines the content store that the worker cache shares.

## 1. What a view is

A **view** is the directory tree that an attempt on a worker sees in place of the caller's tree. The caller's disk holds the truth. The worker holds a cache, a write layer and the directories that git ignores.

| Role | Process | Does |
| --- | --- | --- |
| file server | the **home** (file 04) | owns the export root on the caller's disk, keeps the index, watches for changes, serves records and content, applies writes |
| view server | one process per (home, workspace) on each worker | holds the mount (or the trap supervisor, or the replica), the worker cache, the upper layer and the write-back log; serves every attempt of that workspace on that worker |
| keeper | one per attempt (file 12) | enters the namespace of the view server, or installs the filter, then sets `cwd` and calls `exec` |

* The spawner forks the view server on the request of the worker (file 12). The view server lives while a session uses the workspace on that worker and ends with the worker. Its private mount namespace ends with it, so a crash leaves no mount on the host.
* A **workspace** is one export root of one home. Its id is `wsid = BLAKE3(fingerprint of the caller's key (file 16) || export root as the home spells it)`, written `b3:<64 hex>`. The `wsid` names the warm state on a worker.
* The worker names a home file for a read by a **node id** (`nid`) that the home handed out in a directory record, never by a path. `nid` = the low 63 bits of `BLAKE3(wsid || relative path)`. Both sides compute it, so it is not sent, and it is stable across sessions with no stored state. The view shows it as `st_ino`. The home keeps the set of `nid`s it issued in the session; when two paths give one `nid`, the second path takes `BLAKE3(wsid || path || 0x01)` and the record carries that `nid` in its rare-field object.
* Writes carry a path relative to the export root. The home checks each one (section 16).

Why ids and not paths: a worker can read only what the home listed to it, so the read side is safe by construction, and stable ids give stable inode numbers, which git and caches compare.

The shape field `view` (file 05) holds: `ws` (the `wsid`), `root` (the absolute path of the export root as the worker shows it), `cwd` (relative to `root`, default the root), `mode` (`auto`, `fuse`, `fuse-userns`, `trap`, `sync` or `none`: the values of `--view`, section 18), `with` (array of extra projected paths, section 14, default empty). `ws`, `root` and `mode` are required. The start of an attempt carries the view epoch (section 12) in `extra.vepoch` of its offer row.

## 2. What is projected

* **Export root.** Default: the nearest ancestor of the working directory that holds `.git` (a directory or a file), else the nearest that holds `.podswarm.toml`, else the working directory. `--root DIR` sets it. The home refuses `/`, the caller's home directory itself, and a path under the caller's podswarm cache directory as a root. A cargo workspace member needs the `Cargo.toml` of a parent directory, so the working directory alone is too small.
* **Projected:** every path under the export root, except the three classes below. Projected files are read from the home on demand.
* **Owned by the worker:** each directory that the ignore rules match as a whole (section 10.4). It is a native directory on the worker, it is not read from the home, and it does not cross the link. Examples: `target/`, `node_modules/`, `.venv/`, `build/`.
* **Never projected:** a path of the credential deny list of file 13 (it is absent from the record, so it reads as absent); a path outside the export root and outside every `--with` path; `.git/config` in its true form (the view serves a filtered copy, section 16).
* **Tool directories** (`~/.cargo`, `~/.rustup`, a compiler prefix) are not projected by default. The worker uses its own. Section 14 gives `--with` and the rule for a caller of the same os and arch.
* `$HOME`, `/proc`, `/dev`, `/sys` and the system directories are the worker's own. `/tmp` is a private directory of the session (section 13).

## 3. Rungs

A **rung** is the mechanism that makes the view on one worker. The worker probes once per (kernel release, boot id, binary hash), caches the result as file 12 caches probes, and takes the first rung whose probe passes, in the order of the table.

| Rung | Who gets it | Mechanism | Kernel floor | Probe (in a child) | Same path | Laziness |
| --- | --- | --- | --- | --- | --- | --- |
| `fuse` | root on the worker | private mount namespace; FUSE mount by `mount(2)` with `fd=`, no `fusermount3`; owned directories bind-mounted over the view | Linux 4.18 | `unshare(CLONE_NEWNS)`, `open("/dev/fuse")`, a FUSE mount on a scratch directory | yes | metadata and content |
| `fuse-userns` | a normal user with unprivileged user namespaces and a `/dev/fuse` that opens | `unshare(CLONE_NEWUSER\|CLONE_NEWNS)`, uid map `U U 1`, then as `fuse` | Linux 4.18 | the same three steps inside a new user namespace | yes | metadata and content |
| `trap` | any user with seccomp user notification and `CONTINUE` | a local replica of the whole tree with placeholder files; a seccomp filter traps `open`, `openat`, `openat2`, `execve`, `execveat`; the view server fills a placeholder, then lets the call continue | Linux 5.5 | `seccomp(SECCOMP_SET_MODE_FILTER, NEW_LISTENER)` and one `CONTINUE` round trip | when a mount namespace can be made, else no | content only |
| `sync` | anyone | a local replica, filled in full before `exec` (section 15) | any | none | when a mount namespace can be made, else no | none |

[EV-012]

Which rung each kind of host gets:

| Host | Rung |
| --- | --- |
| root on any Linux 4.18 or later | `fuse` |
| normal user on Debian 11 and later, Fedora, RHEL 8 and later, Arch, Alpine with the `fuse` module loaded | `fuse-userns` |
| normal user on Ubuntu 24.04 and later (AppArmor stops a mount in a new user namespace for a program with no profile) | `trap` |
| normal user in a Docker container (no `/dev/fuse`; the default profile denies `mount`) | `trap` |
| Termux on Android (no `/dev/fuse` without real root; the app policy blocks `openat2`) | `trap` on kernel 5.5 and later, else `sync` |
| Linux before 5.5 with no FUSE rung (RHEL 7) | `sync` |
| macOS, Windows, FreeBSD as a worker | `sync` |

[EV-013] [EV-014] [EV-015]

Cost of one operation:

| Rung | Lookup, stat, readdir | Open and read of a cached file | Write | Owned directory |
| --- | --- | --- | --- | --- |
| `fuse`, `fuse-userns` | one FUSE request the first time, then the kernel cache (section 8.2) | one FUSE `OPEN`; reads from the page cache | to the upper layer through FUSE, batched by the kernel write-back cache | native |
| `trap` | native | one trapped call per `open` and `execve`: 5.7 us on the same core, 34 to 58 us across cores; native after the fill | native | native |
| `sync` | native | native | native | native |

[EV-016] [EV-017]

What each rung cannot do:
* `fuse`: extended attributes on projected files (`ENOTSUP`).
* `fuse-userns`: the same; a set-user-ID program in the view gains nothing; every projected file shows the uid of the attempt.
* `trap`: it needs the metadata of the whole tree before `exec` (a full walk on a cold workspace); a program that opens files through `io_uring` is not seen, so the filter makes `io_uring_setup` fail with `ENOSYS` and the program falls back to plain calls. `CONTINUE` has a time-of-check race; the rung uses it only to fill content, never to enforce a rule. Without a mount namespace the path differs.
* `sync`: section 15.

Rules:
* `--view` takes `auto`, `fuse`, `fuse-userns`, `trap`, `sync` or `none`. `run` and `x` default to `auto`, because their authority is the caller's home, which serves the files; `submit` defaults to `none`, because the home can leave. `--view fuse` takes `fuse` or `fuse-userns`, `--view fuse-userns` forces `fuse-userns`, `--view trap` takes `trap`, and `--view sync` forces `sync`. A forced rung that fails its probe refuses by name with the probe rows. It never falls through to another rung. `--view none` gives the attempt no view: the command runs in the directory that the worker gives it, its `TASK_DIR` (file 12).
* `--view auto` takes the first rung that passes. It takes `sync` when the measured round trip of the link is over `view_sync_rtt_ms` and the workspace has a warm replica on that worker. The default of `view_sync_rtt_ms` is 250. One pipelined transfer beats many demand round trips on such a link (D-26).
* `auto` makes no view, and the attempt runs in the caller's directory, on a worker that is the caller's machine, and on a worker that has the caller's directory itself at the same path: the directory is on a network file system (NFS, SMB, Lustre, GPFS, CephFS, BeeGFS), the mount source and the path inside the mount are equal on both machines, a sample of up to 8 entries has equal size and modification time, and one small file has an equal BLAKE3 id. A forced rung makes a view there too. From M2 (D-127).
* The rung is always reported: in the banner, in `PODSWARM_VIEW`, in `result.extra.view` and in the run report. `podswarm doctor HOST` prints the probe rows and the chosen rung.
* Not used, with the reason: overlayfs (an owned directory as a bind mount gives a native upper, and overlay forbids changes to the lower layer while mounted, which breaks live invalidation); 9p (not mountable in a user namespace); a ptrace rung (the same cost as user notification, and only kernels before 5.0 lack the latter); fanotify pre-content (needs `CAP_SYS_ADMIN` and fires on every read).

## 4. The same path and the mount namespace

1. In the namespace rungs the view appears at the caller's absolute path. In the private mount namespace of the view server, let A be the deepest ancestor of that path that exists on the worker.
   * A is not `/`: clone the tree of A (`open_tree(OPEN_TREE_CLONE|AT_RECURSIVE)` on Linux 5.2 and later, else recursive bind mounts to a staging directory), mount a tmpfs over A, bind each child of the clone back, create the missing components, mount the view on the leaf.
   * A is `/` (a macOS path such as `/Users/...` on a Linux worker): build a tmpfs root, bind each top-level entry of the old root into it, add the new path, call `pivot_root`.
   * The path exists on the worker with other content: mount over it. Nothing outside the namespace sees the change.
2. A Windows caller path `C:\Users\me\proj` shows as `/mnt/c/Users/me/proj`. The drive letter is lower case. Many tools know this form.
3. With no mount namespace (`trap` or `sync` as a normal user with no user namespaces) the tree is at `<cache>/ws/<wsid>/tree/<relative path>`. The banner says `path differs` once. `PWD` is that path. `PODSWARM_HOME_PATH` holds the caller's path in every rung.
4. The keeper of each attempt joins the view: it calls `setns` into the user and mount namespaces of the view server with the descriptors that the view server gave to the spawner, then `chdir` to `root`/`cwd`. In `trap` it installs the filter and passes the listener descriptor to the view server. File 12 owns the keeper; a join costs a few microseconds, and the mount exists once per workspace, not once per command.
5. Owned directories are bind-mounted over their paths in the view. `/tmp` is a private directory of the session bind-mounted on `/tmp`; it is removed at the end of the session.

Why the same path: build tools write absolute paths into dep-info files, debug info and error messages. A different path makes a warm build cold and makes messages point to paths the caller does not have.

## 5. The index on the home

### 5.1 Directory records
The tree is a set of **directory records**. A record is the sorted list of the entries of one directory.

| Field | Form | Meaning |
| --- | --- | --- |
| `name` | bytes | the name; a Windows name as WTF-8 |
| `kind` | byte | `f` file, `x` executable file, `d` directory, `l` symlink (with `target`), `s` socket, `p` FIFO, `o` owned by the worker |
| `mode` | u16 | 12 permission bits |
| `size` | varint | bytes |
| `mtime_ns` | i64 | the home clock |
| `ver` | u64 | the home's hash of (dev, ino or FileId, size, mtime_ns, ctime_ns) |
| `h` | 32 bytes, optional | BLAKE3 of the content, when the home knows it |

* `dv`, the version of a directory, is BLAKE3 of its encoded record without the `h` fields. The `dv` of the root names the state of the tree. Content hashes are not part of `dv`, so the home never hashes a file to build one.
* A record is at most 1 MiB. A larger directory is sent in pages.
* Records are encoded binary (varints) and compressed per message with zstd level 3.

### 5.2 Lazy validation
* The home does not walk the whole tree. A directory is **valid** for the session after the home set its watch, listed it and statted its entries, in that order. A change between the stat and the watch is otherwise lost.
* The worker blocks a lookup in a directory that is not valid and sends `validate` for it at demand priority.
* At `vopen` the worker sends the trace directories (section 8) with the `dv` it holds. The home validates them first and answers `same` or the new record. This takes one round trip.
* `trap` and `sync` need the whole tree before `exec`: the home validates every directory in one walk.

### 5.3 The on-disk index
The home keeps one index file per export root in the caller's podswarm cache directory: `relpath -> (dev, ino or FileId, size, mtime_ns, ctime_ns, h, hashed_at)`. The holder (file 04) keeps it in memory between commands.
* A cached `h` is trusted when the five stat values match and `mtime_ns` is older than `hashed_at - 2 s`. A write within the time granularity of the hash is invisible to stat.
* The home hashes a file only while it reads it to send it, over the bytes it sends. A weak caller machine never hashes a file that it does not ship.

### 5.4 Walk and watcher per system

| System | List one directory | Watcher | Overflow |
| --- | --- | --- | --- |
| Linux | `getdents64` and `statx(AT_STATX_DONT_SYNC)` | inotify, one watch per valid directory | `IN_Q_OVERFLOW` |
| macOS | `getattrlistbulk` | one FSEvents stream with file events on the export root | `kFSEventStreamEventFlagMustScanSubDirs` |
| Windows | `NtQueryDirectoryFile` with `FileIdExtdDirectoryInformation` (name, size, times, attributes, 128-bit FileId; no open per file) | one `ReadDirectoryChangesExW` handle, recursive | buffer overflow |

An overflow makes every valid directory under the reported root not valid. The home sends `inval` for them, and the worker validates again on demand. The inotify watch count is bounded by the directories the command touched, not by the tree.

### 5.5 Sizes
Measured on a tree of 97,637 entries: 37 bytes per entry raw and 17 bytes per entry compressed without `h`; 63 and 44 bytes with `h`. [EV-018]

| Entries | Full manifest, no `h` | Full manifest, with `h` | Warm lazy start |
| --- | --- | --- | --- |
| 10,000 | 0.17 MB | 0.44 MB | a few KB |
| 100,000 | 1.7 MB | 4.3 MB | a few KB |
| 1,000,000 | 17 MB | 44 MB | a few KB |

So `h` goes only with traced files and on demand. A full manifest of 100,000 entries takes about 1.4 s at 10 Mbit/s; the live rungs never send one.

## 6. The view protocol

### 6.1 Streams and frames
* One `view` bulk stream (file 05) per (workspace, worker) carries the control frames of the view. Header line: `{"t":"view","ws":"b3:...","ch":"ctl"}`. Content travels on further `view` streams with `"ch":"data"` and `"prio":"demand"`, `"prefetch"` or `"wb"`. The link serves them in that priority order (stream priority, file 04).
* The feature `view.1` (file 04) gives this protocol; `vapplied`, `vlock` and `append` come with `spread.1`.
* A frame is `u32` length (big endian), `u8` op, then a body of varint fields. Compression is per frame: a flag bit in the op byte marks a zstd body. A frame is at most 1 MiB, 4 MiB after inflation.
* Direction: W is worker to home, H is home to worker. In a spread session a member's view server speaks the same protocol to the anchor, which takes the part of H (section 12.2).
* With a coordinator as the authority, the coordinator relays the `view` streams between the worker and the caller (file 08, section 9). The coordinator can read the bytes that it relays.

| Op | Dir | Fields | Answer |
| --- | --- | --- | --- |
| `vopen` | W | `wsid`, `root`, `trace_key`, `have[(nid, dv)]` of the trace directories, `wb_acked`, `cache_caps` | `vready` |
| `vready` | H | `export_root`, `case_insensitive`, `clock{home_ns, rtt_ns}`, `root{dv, record}`, `rules` (a digest of the ignore, deny and protect rules), `epoch` | none |
| `validate` | W | `[nid]`, `prio` | `dirs` |
| `dirs` | H | `[(nid, dv, same \| record)]`, `epoch` | none |
| `inval` | H | `epoch`, `[(nid, dv, record \| gone)]`, from the watcher | none |
| `want` | W | `[(nid, ver, off?, len?)]`, `prio` | content on a data stream |
| `get` | W | `[(h, off?, len?)]`: a known hash that the cache lost | content on a data stream |
| content | H | header `(nid, ver, size, comp)`, the bytes, trailer `(h)`; or `has(nid, h)`; or `stale(nid)` | none |
| `push` | H | the same frame as content, not asked for (prefetch) | none |
| `wb` | W | `seq`, `[op]` (section 10.2); the bytes of a `put` follow on a `wb` data stream unless the home has `h` | `wback` |
| `wback` | H | `seq_applied`, `[(seq, ok \| conflict(kept_as) \| held(reason) \| refused(reason))]` | none |
| `verr` | H | `op`, `nid?`, `code` | none |
| `vapplied` | W | `epoch`: the epoch that the view applied; spread sessions only, as the answer to each `inval` | none |
| `vlock` | W | `nid`, `kind` (`flock` or `fcntl` with a byte range), `op` (`lock`, `try`, `unlock`), `holder`; spread sessions only | `vlocked` |
| `vlocked` | H | `ok` or `busy` | none |
| `vclose` | W | `wb_last` | `vclosed` when the home applied every op up to `wb_last` |

### 6.2 Rules
* There is no `lookup`, `getattr`, `readdir` or `readlink` on the wire. The view server answers them from valid records. `vapplied` and `vlock` exist only in a spread session (section 12).
* `has` instead of bytes: the home sends it only when `h` is in its set of hashes that this worker acknowledged. The set is exact, because only this home fills this cache for this workspace. An evicted hash costs one `get`.
* `stale`: the home stats the file again after it read it. When size, mtime or ctime changed during the read, it drops the bytes, sends `stale`, then an `inval` with the new record.
* `epoch` is a u64. It rises by one with each `dirs` and each `inval` that changed a record.
* Batching: the worker sends a `validate` or `want` at once when fewer than 8 of its kind are in flight, else it collects entries until one is answered, up to 1,024 entries per message. A `want` at demand priority never waits behind prefetch.
* Errors (`verr` codes): `not_found` (a `nid` that the home did not issue in the current session, or a path that is gone), `too_large` (a frame or a list over its limit), `busy` (an in-flight cap is reached; the worker waits for an answer), `bad_request` (a frame that does not decode). After 1,000 `not_found` or one `bad_request` in a session, the home closes the view with `err{policy}` and the run fails with class Policy.
* Limits per session: 64 MiB of demand bytes and 64 MiB of prefetch bytes in flight; 1,024 entries per `validate`, `want` or `get`; 1,024 ops per `wb`.

### 6.3 Round trips of a warm build
A warm `cargo build` of a mid-size workspace on `fuse-userns`, nothing changed: `vopen` and `vready` with the trace directories: 1 round trip; the attempt start rides with it: 0; content: 0 (all `has` or cache hits); write-back: 0 (`target/` is owned); exit and `vclose`: 1. Total: 2 round trips plus the terminal output. One edited file adds no round trip: the `dirs` answer carries its new record, the worker sends `want` at once, and the bytes arrive while cargo starts.

## 7. Content

### 7.1 Ids, ranges and compression
* A content id is BLAKE3, 32 bytes, written `b3:<64 hex>`. It is the one content hash of the product (file 15). The `blake3` crate needs no C for a static build.
* A file up to 4 MiB is one object. A read of a larger file fetches by `(nid, ver, offset, len)` in aligned windows of 4 MiB into a sparse partial file. The file enters the content store when it is complete.
* Later: FastCDC chunks for files over 4 MiB (minimum 256 KiB, average 1 MiB, maximum 4 MiB), so an edit of a large asset ships one or two chunks. The average is large because each chunk costs an index entry and a request on a slow link.
* zstd for every body. Per object the sender compresses the first 64 KiB at level 1; when that shrinks it by less than 5 percent, the object goes raw. Level by the link estimate: over 200 Mbit/s level 1; 20 to 200 Mbit/s level 3; under 20 Mbit/s level 7 on the home and level 9 on the worker. Records and `wb` frames: level 3. The zstd window is at most 2^27 bytes.

### 7.2 The worker cache
Layout under the cache directory of the worker (`$XDG_CACHE_HOME/podswarm`, mode 0700, per Unix user):

```
blobs/<2 hex>/<62 hex>      the content store of file 15
ws/<wsid>/records           directory records by nid with dv; the last root dv; the rules digest
ws/<wsid>/own/<relpath>     owned directories (section 10.4)
ws/<wsid>/upper/            files written in projected paths, kept until the home acknowledged them
ws/<wsid>/wblog/            segments of the write-back log
ws/<wsid>/trace/<key>       access traces (section 8)
ws/<wsid>/tree/             the replica (trap and sync)
```

* Sharing: `blobs/` is shared by every session and every workspace of the same Unix user on that worker. It is never shared across Unix users. `ws/<wsid>/` belongs to one workspace and is used by one view server at a time (a lock file held with `flock`).
* The FUSE rungs read a cached object from `blobs/` in place. A replica file is a reflink of the object where the file system has one, else a copy. It is never a hard link: a write to it would change the shared object.
* A cached object is used when its `(dev, ino, size, mtime, ctime)` is the one recorded at write, else it is hashed again. The worker never hashes on read.
* Eviction of `blobs/` follows file 15; an object that a live view server holds open is pinned. A `ws/<wsid>/` that no session used for `view_ws_keep_d` days is removed, `own/` included.
* A cache directory on NFS, SMB, Lustre, GPFS or CephFS (`statfs` `f_type`) is not used: the worker takes `/var/tmp/podswarm-<uid>/cache` (mode 0700) instead. A shared home of a cluster otherwise gives many workers one cache and one lock.
* The shield (file 13) seals the cache. At shield `none` the layout above is plain files. At `private` the cache, the owned directories and the upper layer are in the work area of the session (the memory-backed area of file 13) while it runs, and between sessions they are kept only as ciphertext under a key that the caller holds; plaintext of the view is only in the work area and the page cache. An owned directory that does not fit in its share of the memory area is in the sealed store on disk, and the view server serves it through FUSE (file 13, section 6.2, setting `area`). Its reads and writes then pass through FUSE and the seal, so target A-21 (section 19) holds only for the memory rung. At `guest` and `sealed` the view server runs inside the guest and the cache is decrypted only there. File 13 owns the format, the keys, the area and the wipe. `--no-cache` (pool key `cache = false`, file 13) keeps no warm state.

## 8. Prefetch and kernel caching

### 8.1 Access traces
1. The view server records, per attempt tree, the order of first access: directory validations, opens for read, `exec` calls. An entry is a relative path. A trace has at most 50,000 entries.
2. Trace key = `BLAKE3(wsid || basename(argv[0]) || the first argument that does not start with "-")`. `cargo build` and `cargo build --release` share a key; `cargo test` has its own. When no trace has the key, the worker takes the trace of `argv[0]` alone, then the newest trace of the workspace.
3. A trace keeps the entries seen in at least one of the last three runs, in the order of first access in the newest run.
4. At `vopen` the worker sends the trace directories with its `dv`s. Then it sends `want` for traced files whose content it lacks, in trace order, at prefetch priority. The command starts at once. A demand miss goes before every prefetch.
5. A cold miss with no trace: when the worker fetches a file of directory D on demand, the home also pushes the other files of D under 64 KiB, up to 1 MiB per directory. With a round trip over 100 ms, the push takes the subdirectories of D one level down too.
podswarm records the trace itself, so it needs no knowledge of a tool.

### 8.2 Negative lookups and FUSE settings
* A lookup of a name that a valid record does not hold gets an answer at once: a reply with `nodeid = 0` and an entry timeout. The kernel caches it as a negative entry. Build tools probe many absent paths (include paths, configuration files); with complete records no probe reaches the home. [EV-019]
* Entry and attribute timeouts: 1 hour. The view server invalidates by itself: `FUSE_NOTIFY_INVAL_ENTRY` for a name, `FUSE_NOTIFY_INVAL_INODE` for content, at each `inval`.
* `INIT` flags: `FUSE_DO_READDIRPLUS`, `FUSE_CACHE_SYMLINKS`, `FUSE_WRITEBACK_CACHE`, `FUSE_PARALLEL_DIROPS`. `FUSE_POSIX_LOCKS` and `FUSE_FLOCK_LOCKS` only in a spread session (section 12.3). An open reply sets `FOPEN_KEEP_CACHE` when the `ver` did not change.
* Mount options: `default_permissions` (the kernel checks modes with no request), no `allow_other`, `nosuid`, `nodev`.
* Reader threads: `min(4, cores)` on cloned session descriptors.

## 9. Times

Projected sources carry caller mtimes, and outputs in owned directories carry worker mtimes. Build tools that compare them (cargo, make) skip a rebuild when the worker clock is ahead of the caller's clock: a source saved after the last build looks older than the output. A worker clock behind the caller's only causes extra rebuilds.

1. At `vready` the home sends its clock. The worker computes `offset = worker_now - home_ns - rtt_ns / 2`.
2. The view shows `mtime + offset` for every projected entry. A write-back carries `mtime - offset`.
3. The offset is fixed for the session; a changing offset makes unchanged files look changed. Each new session measures it again.
4. When `|offset|` is under 50 ms it is 0. Hosts synced by NTP then show exact mtimes.
5. The banner warns when `|offset|` is over 2 s.

## 10. Writes

### 10.1 The upper layer
* A create or a write of a projected path goes to `ws/<wsid>/upper/` at once. An open for write of a projected file first copies it there from `blobs/`. Reads of that path then come from `upper/`.
* At the last close (FUSE `RELEASE`, or the inotify close event in a replica) the view server hashes the file, appends a `put` to the log, and the sender ships it in the background at `wb` priority. `mkdir`, `rename`, `unlink`, `rmdir`, `symlink`, `link` and `setattr` append to the log at once.
* `fsync` in the view syncs `upper/` only. It does not wait for the home.
* An owned directory takes writes natively and is never in the log.

### 10.2 The write-back log
* One log per workspace on a worker, one order. Ops: `put(path, base_ver?, h, size, mode, mtime)`, `append(path, base_size, h, size)` (spread sessions: the new bytes of a file opened with `O_APPEND`, section 12.2), `mkdir(path, mode)`, `symlink(path, target)`, `link(path, existing)`, `rename(from, to, noreplace)`, `unlink(path)`, `rmdir(path)`, `setattr(path, mode?, mtime?, size?)`. `seq` rises by one per op.
* The home applies ops in `seq` order and acknowledges by `seq`. Order across paths is kept, so "write the data, then rename a marker" keeps its meaning on the caller's disk.
* The home applies a `put` so: create `.<name>.psw-<8 random hex>` in the parent, write, set mode and mtime, rename over the target. A reader on the caller's machine never sees a half file. The home does not call `fsync` per file; a local build does not either.
* An entry of `upper/` is removed when its last op is acknowledged.

### 10.3 What the caller sees
While the command runs, the caller's disk shows each projected file a short time after its last close on the worker. It shows no file of an owned directory. At exit, `podswarm run` waits until every op of the log is acknowledged, then prints held items and exits with the code of the command (file 18). With a cut link it waits until the fence decides.

### 10.4 The default split: what git would see comes back
**Owned rule.** A directory D under the export root is owned by the worker when both hold:
1. The ignore rules match D itself as a directory: the `.gitignore` files from the root down to the parent of D, `.git/info/exclude`, the file of `core.excludesFile` (default `$XDG_CONFIG_HOME/git/ignore`), then the `.podswarmignore` files, in the order and with the pattern grammar of git, the last match winning. A rule that matches only files inside D does not make D owned.
2. No path under D is in the git index. The home reads `.git/index` (versions 2 to 4) itself; it does not run git. Without a repository, rule 2 is true.

Then:
* An owned directory starts empty on a worker, stays warm across runs (section 11), and is not read from the home. A copy of it on the caller's disk is not visible on the worker.
* An ignored **file** in a projected directory is projected read only: a write to it stays in `upper/` and is not written back. Example: an ignored `config.local.toml` that the build reads.
* Every other path that the worker changed comes back, except held items (section 10.6).
* **`.podswarmignore`**: a file in any directory of the workspace, git ignore syntax. A pattern adds owned directories and kept files. A `!pattern` takes a path out of the ignored set, so it is projected and written back: `!vendor/bin/` projects an ignored directory that the build needs from the caller.
* The decision for a directory is made when its parent is first validated, and is stored with the `rules` digest in `ws/<wsid>/records`. When the digest changes at `vopen`, the worker decides again: an owned directory that is no longer owned is removed on the worker and projected; a projected directory that is now owned starts empty.
* `--pull GLOB` (repeatable; `pull` in `.podswarm.toml` `[view]`) copies matching files of owned directories to the caller at exit, with the rules of a `put`. Example: `--pull target/release/mytool`. A build product in an owned directory does not appear on the caller's machine without it.
* `podswarm pull [HOST] PATH...` (file 18) does the same after the run: it copies each PATH (a path or a glob, relative to the export root) from the warm workspace on HOST to the caller's tree, with the rules of a `put`. With no HOST it takes the machine of the newest run of this workspace. A PATH that is not in the warm workspace gets `not_found`.
* At the end of a run that kept paths in owned directories, `podswarm run` prints one line that names them and their size.
* `--keep GLOB` (repeatable; `keep` in `[view]`) keeps writes to matching projected paths on the worker for this run.
* `--clean` empties the owned directories of the workspace on that worker before the command.

Why: a build writes gigabytes of intermediate files. None of them should cross the link or pass through FUSE, and the ignore rules already name them in almost every repository.

### 10.5 Size thresholds

| Setting | Default | Effect |
| --- | --- | --- |
| `view_put_max_mib` | 256 | a new or changed file above it is held; `--pull` takes it |
| `view_wb_max_mib` | 2,048 | write-back bytes of one run above it are held |
| `view_del_max` | 1,000 | deletes of one run above it, or above `view_del_max_pct` of the projected files, are held |
| `view_del_max_pct` | 10 | see above |
| `view_ops_max` | 100,000 | ops of one run above it are held |

### 10.6 Held changes
A held op stays in the log and in `upper/`. It is never applied without the user. Held:
* a path of the protect list: `.git/**` (git state changes come from git on the caller's machine), `.podswarm.toml`, `.podswarmignore`, `.envrc`, `.vscode/**`, `.idea/**`, a path of the credential deny list (file 13), and the `protect` globs of `[view]`;
* a file, a run total, a delete count or an op count above section 10.5;
* a new name that differs only in case from an existing name on a case-insensitive caller file system;
* a symlink that the caller's system cannot create (section 13).
How the user applies them: at exit on a terminal, `podswarm run` lists the held items by class and asks once per class (`apply 1,532 deletes? [y/N]`). With no terminal, the items stay in the log and the next run of that workspace on a terminal asks first. `--pull PATH` applies one held file. `--clean` and `podswarm forget HOST` drop held items after one confirmation.

### 10.7 Conflicts
Before the rename of a `put`, `unlink` or `rename`, the home stats the target again. When its `ver` is not the `base_ver` of the op (the user changed it during the run), the home keeps its own file, writes the worker's version as `<name>.psw-conflict-<run>` beside it, and reports `conflict(kept_as)`. A delete of a changed file is dropped and reported. No data of either side is lost.

### 10.8 A link cut in the middle
* The command keeps running. Cache hits are served. A demand miss blocks until the link returns or the fence (file 05) ends the attempt; there is no second timer.
* Writes keep going to `upper/` and the log. After reattach (file 04) the sender resumes at `wb_acked + 1`; the home ignores a `seq` that it applied.
* When the home does not return, the log and `upper/` stay for `view_log_keep_d` days. The next session of the same workspace on that worker applies them first, with the conflict check.

## 11. Warm state

* Kept on a worker per workspace: the records, the owned directories, the traces, the log until it is applied, and the shared `blobs/`. At shield `private` they are kept sealed (section 7.2).
* Kept for `view_ws_keep_d` days after the last use. `podswarm forget HOST` removes all of it. `--no-cache` and the pool key `cache` (file 13) keep nothing.
* The next run finds it by `wsid`: `vopen` sends the `dv`s it holds, and the home answers `same` for each unchanged directory. Placement prefers the machine that holds a warm view of the workspace (file 08).
* The home keeps its index and its set of acknowledged hashes per worker in the holder (file 04) and in the index file.

## 12. Consistency

### 12.1 One machine
* The home is the authority of metadata. A change on the caller's disk reaches the view by `inval`, after the watcher latency and one one-way delay.
* An attempt started after the home applied a change sees it: the start carries the home `epoch` (`extra.vepoch`), and the keeper waits until the view server applied that epoch before `exec`.
* A change made on the worker is visible at once to every process of that workspace on that worker: one kernel, one mount.
* Within one run the view is not frozen: a file that the user saves during a build appears during the build, as in a local build.

### 12.2 Several machines
File 07 spreads processes. The view rule for them:
* The **origin** is the caller's machine: it holds the truth of the workspace and serves the lower layer. The **anchor** is the machine that runs the root process of the command: it holds the owned directories and the upper layer, and it is the authority for files that members write. With `podswarm run --spread -- CMD` the anchor is the caller's machine; with `podswarm run HOST --spread -- CMD` it is HOST. A member's view server uses the anchor as its file server, with the protocol of section 6.
* **Close-to-open with spawn causality.** A member sends its writes to the anchor as its write-back log (section 10.2), numbered by `seq`. Frames of a moved process carry `pub`, the newest `seq` before them (file 07). The anchor sends `inval` to each member view that holds the path; a member answers with `vapplied` and the epoch it applied. A move request carries the newest epoch of the anchor (`vepoch`); the target keeper waits until its view applied it, then calls `exec`. So every file closed before `make` or `cargo` spawned a child is visible to that child.
* Two whole-file writers of one path on two members: the last publish at the anchor wins, with no conflict copy. Appenders (`append`): every append, in the order of arrival. A change by the caller during the run keeps the conflict rule of section 10.7.
* A member uses a FUSE rung or `sync`. A worker with only the rung `trap` is neither the anchor nor a member: the exec filter of file 07 takes the one seccomp listener of the process.

### 12.3 Locks
* On one machine, `flock` and `fcntl` locks are local to the worker: the view sets no FUSE lock flag, so the kernel of the worker keeps them. They are not shared with the caller's machine.
* In a spread session a member's view sets `FUSE_FLOCK_LOCKS` and `FUSE_POSIX_LOCKS` and forwards each lock call to the anchor with `vlock`. The anchor takes the real lock for the remote holder, so processes on the anchor and on members exclude each other (`target/debug/.cargo-lock`). A lock is released when its holder exits or its member is lost.

### 12.4 Directory listings
A listing on a worker is the record at the epoch that its view applied, plus the entries of `upper/` and the owned directories. A listing never waits for the home, except for a directory that is not valid yet.

## 13. File kinds and semantics

| Item | Rule |
| --- | --- |
| Rename | atomic in the view; written back as `rename(2)`, `renameat2(RENAME_NOREPLACE)` when `noreplace`, `MoveFileExW(MOVEFILE_REPLACE_EXISTING)` on Windows |
| Hard links | a link made on the worker shares one node during the run; written back as a hard link when both paths are in the log and the caller's file system has links, else as two copies; hard links on the caller's disk show as separate files with `nlink` 1 |
| Symlinks | served as symlinks with the caller's text; the home never follows one to serve a file; a link that points out of the tree resolves on the worker's own file system; a symlink made on the worker is written back as a symlink (Windows: `SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE`; held when that fails) |
| Ownership | projected files show the uid and gid of the attempt; `fuse-userns` maps `U U 1`, so `id -u` and file owners look normal; mode bits come from the caller |
| Executable bit from a Windows caller | `x` when the git index lists the path as `100755`, else when the file starts with `#!` or `\x7fELF`; an exec bit written back to Windows is dropped |
| Case | a case-insensitive caller (Windows, default macOS) sets `case_insensitive`; the view answers lookups without regard to case and shows the caller's spelling; owned directories stay case-sensitive; replica rungs create the caller's spelling only |
| mmap | shared writable mmap works on the page cache; dirty pages reach the view server at `msync`, `munmap` or close; the write-back starts at the last close |
| Sockets, FIFOs | shown with their kind; a `connect` or an `open` of one from the caller fails (the peer is on another machine); one made on the worker is never written back |
| Extended attributes | `ENOTSUP` on projected files; native in owned directories |
| Times | `atime` and `ctime` equal `mtime` on projected files |
| `statfs` | the worker file system of `upper/` |
| `/proc`, `/dev`, `/sys` | the worker's |
| `/tmp` | a private directory of the session, bind-mounted on `/tmp` in the namespace rungs; `TMPDIR` points to it in all rungs; at shield `private` it is in the area (file 13) |
| `$HOME` | the worker's own home; the caller's home is not projected |

## 14. Paths outside the workspace and tools

1. Only the export root is projected by default. The tools, `HOME` and the caches are the worker's own. The remote machine must have the tools that the command runs, or get them from an image through podvm (file 24).
2. `--with PATH` (repeatable) projects one more path of the caller at the same absolute path, read from the home. Writes under it stay on the worker and are never written back. The deny list and the export rules apply to it as to the root.
3. A caller of the same os and arch can project its toolchain: `podswarm run --with ~/.cargo --with ~/.rustup HOST -- cargo build`. The `bin` directories of `--with` paths go in front of `PATH`. An environment variable whose value is an absolute path passes only when the path is under the export root or a `--with` path; the rest of the environment rule is in file 13.
4. Mismatch: at start, when the caller's os or arch differs from the worker's and `--with` is given, the banner warns once. When a projected executable is passed to `exec` and its ELF machine (or its Mach-O or PE header) does not match the worker, the view server makes the `execve` fail with `ENOEXEC`, and the run prints one line that names both machines.

## 15. The sync rung

* **What is sent:** at `vopen` the home validates the whole tree (one walk) and sends the records that differ from the `dv`s that the worker holds. The worker sends `want` for each file whose `ver` changed and whose content it lacks; the home sends `has` for content that the cache holds. All of it goes on one pipelined data stream.
* **The warm copy:** the replica `ws/<wsid>/tree/` stays on the worker between runs. Unchanged files cost nothing. Owned directories are real directories in the replica.
* **The start:** `exec` waits until the replica is complete. With a mount namespace the replica is bind-mounted at the caller's path; without one the path differs (section 4).
* **During the run:** changes of the caller's disk are applied into the replica as `inval` arrives. Writes on the worker are found by inotify on the replica when it works (each close is a `put`), else by a scan at exit that compares each file with its record.
* **What comes back:** the same ops, the same split, guards, conflicts and held items as section 10.
* **When it is chosen:** a worker with no other rung; `--view sync`; `--view auto` on a slow round trip with a warm replica (section 3).
* **What differs for the user:** the first run sends the whole tree; a cold start of a large tree waits for it; the path can differ; without inotify, files come back only at exit; a home change during the run is seen only after it is applied into the replica.

## 16. Security of the export

A hostile worker can read every served file of the export root and of the `--with` paths, keep copies, send any write op, flood requests and lie about what it writes. The rules:
1. **Fixed root.** The export root is fixed at session start. A read names a `nid` that the home issued in the current session; any other gets `not_found`.
2. **No symlink follow.** Every open on the home resolves beneath the root with no symlink: Linux `openat2(RESOLVE_BENEATH|RESOLVE_NO_SYMLINKS|RESOLVE_NO_MAGICLINKS)` on 5.6 and later, else a walk of `openat(O_NOFOLLOW|O_DIRECTORY)` per component; macOS per component with `O_NOFOLLOW` (`O_NOFOLLOW_ANY` on 11 and later); Windows per component relative to the parent handle with `FILE_FLAG_OPEN_REPARSE_POINT`, and a reparse point is refused.
3. **Deny list.** File 13 owns the list of credential files and its rules. The view applies it before every other rule: a denied path is absent from the record, so it reads as absent and its name is not sent. Only the user's own configuration or `--allow GLOB` (for one run; the CLI prints the path once) opens an entry. A workspace file cannot.
4. **`.git/config`** is served as a filtered copy: `[credential]` sections, `http.*.extraheader` lines, `url.*.insteadOf` values with a user part, and user information in `remote.*.url` are removed. The file on the caller's disk is not changed. `git describe` and version stamps of build scripts still work.
5. **Write confinement.** A write path passes the path rule of file 16, without its first-segment clause; on a caller that is not Windows the bytes `: * ? " < > |` and a trailing dot or space are allowed. The parent resolves beneath the root with no symlink; the last component opens with `O_NOFOLLOW` (`O_CREAT|O_EXCL` for the temporary name). A write never leaves the tree. A `put` sets `mode & 0o777`: never set-user-ID, set-group-ID or sticky. The protect list and the guards of section 10 apply. Writes under a `--with` path are refused.
6. **Limits and rates:** the in-flight caps and the error budget of section 6.2; the thresholds of section 10.5.
7. **What a hostile worker cannot get:** a file outside the root and the `--with` paths, a denied file, the true `.git/config`, a write outside the tree, a write to a protected path or a mass delete without the user, a set-user-ID file on the caller's disk.
8. **What it can do:** read and keep every served file; change any result that it writes back (a written file is untrusted input on the caller's machine, as a download is). On a host with other root users, those users can do the same. The shield levels of file 13 say what each level stops.

## 17. What each machine needs

| Caller system | Needs | Notes |
| --- | --- | --- |
| Linux | nothing installed, no root | inotify; `openat2` on 5.6 and later, else the per-component walk; the inotify watch limit bounds the directories one session can hold valid |
| macOS | nothing installed, no root | FSEvents, `getattrlistbulk`; the default file system is case-insensitive; the path shows as `/Users/...` on the worker |
| Windows | nothing installed, no administrator | `ReadDirectoryChangesExW`, `NtQueryDirectoryFile`; the path maps to `/mnt/<drive>/...`; names as WTF-8; the exec bit from the git index; symlinks need developer mode or the privilege, else they are held |

The worker needs Linux for the rungs `fuse`, `fuse-userns` and `trap`. Every worker system has `sync`.

## 18. Flags and settings

Flags of `podswarm run` that the view owns (file 18 lists all flags):

| Flag | Meaning |
| --- | --- |
| `--view auto\|fuse\|fuse-userns\|trap\|sync\|none` | rung choice (section 3); default `auto` for `run` and `x`, `none` for `submit` |
| `--root DIR` | the export root |
| `--with PATH` | one more projected path, read only to the caller |
| `--allow GLOB` | open one entry of the deny list for this run |
| `--pull GLOB` | copy matching owned files, or a held file, to the caller at exit |
| `--keep GLOB` | keep writes to matching projected paths on the worker |
| `--clean` | empty the owned directories first |
| `--no-cache` | keep no warm state on the worker (pool key `cache`, file 13) |

`.podswarm.toml` `[view]` holds `pull`, `keep` and `protect` (lists of globs), and the five thresholds of section 10.5. A workspace file can only add globs and lower a threshold; a higher threshold is ignored with a warning. File 19 lists every setting with scope, type and range.

| Setting | Default |
| --- | --- |
| `view` | `auto` for `run` and `x`; `none` for `submit` |
| `view_sync_rtt_ms` | 250 |
| `view_ws_keep_d` | 30 |
| `view_log_keep_d` | 7 |
| `view_put_max_mib`, `view_wb_max_mib`, `view_del_max`, `view_del_max_pct`, `view_ops_max` | section 10.5 |

## 19. Targets

File 23 holds each target with its conditions. What the view gives each:

| Id | Target | The view's part |
| --- | --- | --- |
| A-20 | `podswarm run HOST -- true` over an open road adds at most 30 ms to the round trip | the view server and the mount exist once per workspace; the keeper joins by `setns`; the start rides with `vready` [T] |
| A-21 | a warm build through the live view within 10 percent of the same build on the remote machine | owned directories are native (at shield `private`: in the memory rung, file 13, section 6.2); sources are read once through FUSE; sub-targets: `fuse` 3 percent, `fuse-userns` 5 percent, `trap` 8 percent [T] |
| A-22 | an edit of one file and a new build send under 64 KiB before the compiler starts | one changed record, one compressed object, start and exit frames [T] |
| A-23 | the first run on a machine with no podswarm reaches the command in under 5 s on a 20 Mbit/s link | lazy validation: only the root record and the chain to `cwd` before `exec` on a FUSE rung [T] |

More view targets of file 23: A-25 (a warm start of a 100,000-entry tree), A-26 (a cold start on a FUSE rung), A-27 (caller CPU of a warm run), A-28 (`sync` cold); bench B-25 to B-27. Fault tests: F-40 (link cut during write-back), F-41 (caller edit during the run), F-42 (watcher overflow), F-43 (worker crash with a log), F-44 (clock skew), F-45 (`rm -rf src` on the worker), F-46 (hostile worker).

## 20. Milestones

Milestones are those of file 22.

M1 (one command, one machine, live view):
* rungs `fuse`, `fuse-userns`, `sync`; probes; the same path;
* the home index, walk and watcher on Linux, macOS and Windows; lazy validation;
* the protocol of section 6 for one worker; BLAKE3; zstd; whole objects and ranged reads;
* owned directories from the ignore rules and `.podswarmignore`; the write-back log; guards, held items, conflict copies; the deny and protect lists; the filtered `.git/config`;
* trace prefetch and the directory push; negative entries; explicit invalidation;
* the clock offset;
* the shield `private` hooks of file 13 for the cache;
* targets A-20 to A-23 measured in CI.

M2: the `trap` rung (normal users on Ubuntu 24.04, containers, Termux); inotify tracking for the replica rungs.

M3: several machines (anchor, spawn causality, `append`, `vapplied`, `vlock`; file 07).

Later: FastCDC chunks; FUSE passthrough for cached files as root (Linux 6.9, `CAP_SYS_ADMIN` in the initial namespace); a `fuse-helper` rung through a set-user-ID `fusermount3`; FUSE over io_uring; a live view on a macOS worker (NFSv3) or a Windows worker (ProjFS) (M10).
