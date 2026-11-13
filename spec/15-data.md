# 15. Data: content store, staging, outputs and checkpoints

This file defines how bytes move in podswarm: the content store, the transfers on `blob_put` and `blob_get` streams, the staging of inputs for queued tasks (a queued task has no live view), outputs and results, and checkpoints with resume. File 05 owns the shape fields and the bulk stream table. File 06 owns the live view: its index, its protocol and the per-workspace directories of a worker. This file owns the content store, its layout, its cap and its eviction, which the view cache uses. Directories (`S`, `K`, `R`) are defined in file 19. File 09 owns the task rows, file 11 the tables, file 12 `TASK_DIR` and the capture rule, file 13 the shield and the keys, file 16 the path rule and the policy keys, file 17 the checkpoint sink plugin.

An attached command of `podswarm run` needs none of the staging in this file: its files come through the view (file 06), and section 7.1 says what comes back. A queued task, a batch task and a task on a machine with no view use staging.

## 1. The content store

### 1.1 Ids and trees
* A **blob** is a byte string. Its id is `b3:<64 hex>`: the BLAKE3 hash of its bytes. One hash serves the whole product: blobs, shapes, the view cache and checkpoints (file 06). SHA-256 stays only as an outside check on a URL input (section 3.5) and in release checksums (file 16).
* A **tree** is a blob that holds a manifest. The manifest lists paths, modes, sizes and ids. A directory input (`--dir`), a checkpoint and a directory of the view cache use this one format.
* Manifest text: UTF-8, one entry per line, sorted by path bytes, a final newline, at most 8 MiB and 100,000 entries (the cap counts `F`, `D`, `L` and `C` lines, not `H` lines). The first line is `podswarm-tree/1`. A reader refuses an unknown first line with `unsupported`.

```
podswarm-tree/1
D 0755 bin
F 0644 1048 3a7bd3e2360a3d29eea436fcfb7e44c735d117c42d1c1835420b6b9942dd4f1b data/in.csv
F 0755 9122 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08 bin/tool
L ../data/in.csv link-name
C 0644 536870912 4194304 big/state.bin
H 2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae
```

| Line | Fields |
| --- | --- |
| `F` | mode (octal), size, id (hex), path |
| `D` | mode, path |
| `L` | target, path. The target holds no space and no newline. A link is restored only where the path rule allows it (file 16): on a `confined` boundary or higher a link is refused. |
| `C` | mode, size, chunk size, path. One `H` line per chunk follows: the id of one chunk. |
| path | The last field of a line. It may hold spaces. The path rule of file 16 bars a newline. |

* The mode is `mode & 0o755`. A path follows the path rule of file 16. Two paths of one tree that are equal after Unicode NFC and case folding are a refusal.
* A file is one blob. A file over `ckpt_chunk_over` (64 MiB) is a `C` entry with fixed chunks of 4 MiB, each chunk one blob. Fixed chunks dedupe an appended file and an array that a program rewrites in place. They do not dedupe an insertion. An encrypted tree uses chunks of 1 MiB for each file over 1 MiB (section 11.10). The id of the tree is the hash of the exact manifest bytes, so no canonical form is needed.
* The header may carry flags after the version: `podswarm-tree/1 enc=b3k`. File 13 and section 11.10 give the meaning.

### 1.2 Layout
One layout holds blobs everywhere: `<root>/blobs/<first two hex>/<rest>`, where `<rest>` is the 62 other hex digits of the id.

| Place | `<root>` | File mode | Other files |
| --- | --- | --- | --- |
| Coordinator | the state directory (file 19) | 0600 | `blobs/.partial/`, the tables `blobs` and `blob_owners` (file 11) |
| Worker | `K` of file 19, per Unix user; `/var/tmp/podswarm-<uid>/cache` when `K` is on a network file system | 0444 (0555 for a file staged by `--bin`) | `blobs/.partial/`, the last-use journal `blobs/.journal` |
| Home | `K` of file 19 | 0444 | the view index (file 06) |

A cache file is written to a temporary name and renamed after the hash check. At shield `private` or above, the worker cache is in the work area (file 13). The coordinator holds no blob of a session: in a session the home is the store, and it keeps its tables in memory unless `--db FILE` is set (file 11).

### 1.3 Who owns a blob
* A submitter owns the blobs it uploaded. A run owner owns the blobs that workers upload for its attempts. The home of a session is the one owner.
* `blob_have` answers `have` only for blobs that the asker owns. A blob that another owner holds is uploaded again in full, and the receiver adds the owner when the hash verifies. So a hash that someone knows gives no read access, and no dedupe across owners leaks that a blob exists. [EV-073]
* One error, `not_found`, answers for a blob that is absent and for a blob that is not yours (file 05). A task `files` entry that names a blob the submitter does not own fails at `submit` with `not_found`.
* A worker may fetch a blob only when an offer that it holds names it: a `files` entry, a stdin blob, the manifest of a restore and the blobs of that manifest. For an encrypted checkpoint (section 11.10) the authority cannot read the manifest, so the worker may fetch any `b3k:` blob of the run owner while it holds the attempt. A worker may put a blob only while it holds an attempt whose shape has `outputs`, `capture_blob` or `checkpoint` (sections 6, 8 and 11).
* A submitter reads a blob when it owns it or when a run that it owns names it in a result.

### 1.4 References and the sweep
* A task row that names a blob holds a reference in `blobs.refs`. An accepted result holds one for each output. A checkpoint row holds one for its manifest and for each blob it lists. A reference drops when the row is purged.
* The submit transaction runs in the writer thread (file 11). It checks the ownership of each named blob and adds to `refs` in the same transaction. The sweep runs in the same thread. It deletes a row only when `refs = 0 AND pinned = 0 AND last_used < cutoff`, and it unlinks the files after the commit. So a submit and the sweep cannot interleave into a dangling reference. A positive `blob_have` sets `last_used`.
* The cutoff is `blob_ttl_days` (file 11), and a blob whose `last_used` is less than 24 hours old is never deleted. The guard protects blobs of a checkpoint that is not committed yet (section 11.5).
* A blob that a submitter pinned (`podswarm update RUN --pin`, or `--pin-outputs` at submit, file 18) stays. A late result and a refused checkpoint leave blobs with no reference. The sweep removes them.

### 1.5 Quotas and the largest blob
* Each owner pays the full size of each blob it owns, also when two owners hold the same blob.
* The limit of a submitter is `max_blob_mib` (file 16, table `submitters` of file 11). The limit of the store is `max_blob_bytes`. A put that passes the limit of a submitter fails with `quota`. A put that passes the limit of the store fails with `busy`. Each error carries `limit`, `used` and `scope` (file 05). The coordinator also gives its limits in `ready.limits` (file 04), and a client checks them before it sends a byte.
* The largest blob is `blob_max_mib`. A larger input goes by a URL input (section 3.5), by `--shared-fs`, or by chunks (section 1.1). A put of a larger blob fails with `too_large` and `limit`.
* The cache of a worker or a home has the cap `cache_max`: default the smaller of 20 GiB and 10 percent of the free space of its file system at first use. Above the cap the owner of the cache evicts by last use until the cache is at 80 percent of the cap. Last use is in `blobs/.journal`, not in the access time, which many mounts do not keep. A worker never evicts a blob that it needs for a held offer or that a live view server holds open: those blobs are pinned until the attempt or the view ends.

### 1.6 The view cache and the content store are one store
The home serves the content of the live view from the same blobs and the same ids (file 06). A file that a view fetched is a blob in `K/blobs/` and can stage a task, and a staged blob can serve a view. A blob for a view is fetched by ranges into a partial file and enters the store when complete (file 06). The index of file 06 maps a path of the home to its id with the `(dev, ino, size, mtime, ctime)` record. The store never keeps a second copy under another id form.

## 2. Transfers

A transfer is one bulk stream of the link (file 05, section 7). The stream starts with one JSON line, then carries raw bytes. Offsets count bytes of the blob, never bytes on the wire.

```
{"t":"blob_put","id":"b3:...","size":N,"offset":N,"enc":"raw"}
{"t":"blob_get","id":"b3:...","offset":N,"len":N,"enc":"zstd"}
```

| Field | Meaning |
| --- | --- |
| `id`, `size` | The id and the full size of the blob. `size` is at most `blob_max_mib`. |
| `offset` | Put: the first byte that the sender will send. Get: the first byte that the receiver wants. |
| `len` | Get only, optional. The range length. Without it the range goes to the end. |
| `enc` | `raw` or `zstd`. `zstd`: the stream is one zstd frame of the range. The window of the frame is at most 2^27 bytes. The id and the size are always those of the plain bytes. |

* The receiver answers with one JSON line before data. Put: `{"ok":true,"have":N}` when its partial file holds `N` bytes, `{"ok":true,"done":true}` when the owner already holds the blob, or `{"ok":false,"code":C,...}` with the error codes of file 05. A put with an `offset` that is not `have` is answered `{"ok":false,"code":"bad_request","have":N}` and the sender opens again with `offset` set to `N`. Get: `{"ok":true,"size":N,"len":M,"enc":E}` or an error, then `M` bytes.
* The receiver writes to `blobs/.partial/<link id>-<id hex>`, never shared between links. It hashes while it writes. On resume it reads the partial file once to restore the hash state, then continues. It renames to the final name only when the size and the hash match. A mismatch deletes the partial file and answers `{"ok":false,"code":"bad_request","reason":"hash"}` at the end of the stream. A chunk is accepted only when its offset equals the bytes held. So a chunk at offset 2^40 is refused and makes no sparse file.
* A link may hold at most 2 partial files and 8 GiB of partial data. A partial file is kept for 1 hour after a cut and is removed at the end of the session, unless the same worker identity resumes it within that hour (`partial_keep_s`, fixed). A transfer that a cut ended opens again with the `have` of the receiver.
* Compression. The sender samples the first 64 KiB of the blob. When zstd level 1 shrinks the sample by less than 5 percent, it sends `raw`. Else it uses the level by the link estimate (file 04): above 200 Mbit/s level 1, from 20 to 200 Mbit/s level 3, below 20 Mbit/s level 7 on the home and level 9 on a worker. Stored blobs are always plain, so a reflink and a hard link work on them. A blob that is already compressed (an archive) shows no gain in the sample and goes `raw`.
* A worker has at most 2 transfers at one time in each direction (`blob_streams_worker`, fixed). The link keeps control frames ahead of data and gives each transfer its own window (file 04).
* A worker fetches the blobs of an offered attempt that is queued, while other attempts run. The fetch starts at the offer, not at the start of the attempt.
* An authority serves at most `blob_streams_max` downloads at one time. More wait in a queue in the order of their requests.
* A worker may ask `blob_have{ids[]}` for its run owner with up to 10,000 ids in one request on its link; the answer is `rep{have[]}`, the ids that the owner holds. It uses the same `req` and `rep` form as a submitter (file 05, section 9).

## 3. Staging for queued tasks

A task of a batch or of a queue has no live view. The shape field `files` lists what the worker puts in `TASK_DIR` before the start (file 12, state `starting`). The entries:

```
{"id":"b3:...","path":"data.csv","mode":"0644"}
{"tree":"b3:...","path":"inputs"}
{"url":"https://...","sha256":"...","size":N,"path":"model.bin","unpack":"tar.zst"}
```

`mode` defaults to the mode of the source with `& 0o755`. `unpack` is allowed on an `id` entry and on a `url` entry. Each `path` follows the path rule of file 16 and is relative to `TASK_DIR`.

### 3.1 Inline data
Arguments, `env`, `stdin.inline` and the task `input` travel inline in the task record (at most 16,384 bytes, file 05). A larger stdin is `{"blob": id}`. The result carries a capped head and tail of the output (section 8).

### 3.2 Files and programs
* `podswarm x --file SRC:DST CMD` uploads `SRC` once for the run and stages it as `DST` in each task directory.
* `--bin PATH` ships a program. The worker stages it with mode 0755, and the `bin` directory of `TASK_DIR` is first in `PATH`. The submitter reads the file header and adds needs:

| Header | Needs added |
| --- | --- |
| ELF | `needs.arch` from `EI_CLASS` and `e_machine`; `needs.os = linux`; `needs.interp = <path>` from `PT_INTERP` when the file has one |
| Mach-O | `needs.os = macos`; `needs.arch` from `cputype` |
| PE | `needs.os = windows`; `needs.arch` from `Machine` |
| `#!` script | a warning only; the interpreter name is `needs.shell` when it is a known shell |
| other | a warning; the user sets `--arch` |

A worker checks that `needs.interp` exists before the start. A missing interpreter ends the attempt as `spawn_failed`, reason `input`, text `interpreter <path> missing`. The task is not retried on that worker. The reason: a dynamic glibc program on a musl or NixOS machine otherwise fails with "No such file or directory".

### 3.3 Directories and per-task files
* `--dir DIR` uploads `DIR` as a tree: one manifest blob and one blob for each file (section 1.1). It stages the tree at `path`. Whole-file dedupe sends a file that two runs share once.
* `--stage-each` makes each input line of `podswarm x` a local path. The submitter hashes it, uploads it and puts its id in the task input. The worker stages it as `in/<basename>`, and `{}` expands to that staged name. `{/}` and `{/-}` keep naming the original (file 18).
* A tree has at most 100,000 entries. For more files, use an archive and `unpack`.

### 3.4 Shared file system
`--shared-fs` stages nothing. The paths exist on the workers. The submitter adds a tag to route the task (a worker tag such as `fs:projects`). The task `cwd` is the path of the submitter, and the worker policy `allow_abs_cwd` must allow it (file 16). A missing path fails the task like any other failure.

### 3.5 URL inputs
For public data and for any input that goes to more than 100 workers.
* `size` and `sha256` are mandatory. The worker stops at `size` bytes and checks the SHA-256 while it writes. The hash is an outside check: it is the hash that the publisher of the file gives. The worker also computes the id of the bytes, stores them in its cache, and keeps a map from `sha256` to id, so a later task that names the same URL input finds the blob in the cache and fetches nothing (D-83).
* A mismatch of size or hash ends the attempt as `spawn_failed`, reason `input`, text `input hash mismatch`. It is not retried.
* The worker fetches. The coordinator never sees the bytes. The fetch runs outside the `confine` of the task and under the worker policy `net_allow` (file 16). By default only public addresses pass: no loopback, link-local or private range, checked after DNS and again at the connect. The `url` is an `https://` URL, and at most 3 redirects follow, all HTTPS. A fetch takes at most `url_fetch_s`. An error text and `podswarm show` print the host and the path, never the query.
* A presigned URL is stored in clear in the task record. Private data uses `--shared-fs` or a public URL.

### 3.6 Unpack
`unpack` accepts `tar`, `tar.gz` and `tar.zst`. The rules:
* The unpacker accepts only regular files and directories. A link, a device, a FIFO, an absolute name or a `..` segment is a refusal, and so is a duplicate name.
* The mode is `entry_mode & 0o755`: no setuid, setgid or sticky bit.
* The path rule of file 16 applies after PAX and GNU long-name processing.
* At most 100,000 entries, depth 32, and expanded bytes at most `needs.disk_mib` (4 GiB when it is not set). The zstd window is at most 2^27 bytes.
* Each file opens with `openat2` and `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS` with `O_EXCL` on Linux; elsewhere the unpacker checks each component with `lstat`.
A refusal ends the attempt as `spawn_failed`, reason `input`.

## 4. A cached blob in a task directory

* A cache file is read-only. The worker places it in `TASK_DIR` by reflink (`FICLONE`) where the file system has one. Else it makes a hard link on boundary `none`, and a copy on `confined` or higher (the task must not reach the shared inode). A file that the task may write (a staged mode with a write bit) is never a hard link.
* At write the worker records `(size, mtime, ctime, inode)` of each cache file. Before each use it compares the record. When one value differs, it deletes the file and fetches the blob again. A `chmod` or a write through a hard link sets a new `ctime`, so the next use detects it.
* The worker never hashes a cached file on read. It hashes only while it writes. [EV-074] A hash of a 200 MB input on each read would cost seconds on such a core.
* A change that keeps all four values (root can restore times) is not detected. File 13 states this limit for a host with other root users.
* Before it fetches, the worker checks the free space of the cache file system. When the input does not fit, it returns the attempt that has not started as `not_started`, reason `disk`. File 10 gives what the engine does next.

## 5. The fan-out budget

* At submit the CLI computes `cost = size * eligible workers` for each blob input. Above `fanout_warn` it prints the estimate for the measured uplink. Above `fanout_max` it refuses with exit 64 and names URL inputs, `--shared-fs` and a tag selector for fewer workers.
* The authority serves at most `blob_streams_max` downloads (section 2).
* `hb` carries `blobs`: the ids in the worker cache that ready tasks name, at most 64 (file 05). For a task whose input holds a blob over 16 MiB, the engine prefers a worker that holds it among tasks of equal turn (file 10, fairness).
* Peer fetch (a worker serves its verified cache to workers that the authority names) is later work (file 24). The hash makes it safe. NAT makes it hard.

## 6. Outputs

* The shape field `outputs` lists globs. After the exit, the worker matches them inside `TASK_DIR`. A glob that starts with `/`, has a `..` segment, or fails the path rule of file 16 is refused at submit. The directories `.psw` and `tmp` never match: the worker owns them.
* The worker resolves each match with a descriptor of `TASK_DIR`: `openat2` with `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS` on Linux, and `lstat` with a refusal of links elsewhere. It accepts a regular file with link count 1. It never opens a FIFO, a socket or a device. It reads at most `limits.fsize_mib` per file and at most 256 files per task. A refused match ends the attempt as a failure, reason `output_rejected`.
* The worker hashes each accepted file and uploads it as a blob (section 2). The result lists `outputs[{path, id, size}]` (file 05).
* A blob enters the store of the authority only by a rename after its hash check (section 1.2), so no reader sees part of an output. The worker sends the result only after all uploads end. A failed upload makes the attempt a failure with reason `output_failed`, whatever the exit code: the task did not deliver (D-84).
* **What the authority checks at accept.** For each `outputs[].path` the authority applies the path rule of file 16 and matches a declared glob. It checks that each named blob exists, is owned by the run owner and has the stated size. A result that fails a check is refused with `bad_request`. The worker is not trusted: it could report `../../.bashrc`. The accept transaction adds a reference to each blob (file 11), so a reader of an accepted result can read every blob it names.
* **Late results.** The blobs of an accepted result get references. The blobs of a late result of another attempt do not, and the sweep removes them (section 1.4).

## 7. Results at the client: `--results DIR` and `podswarm get`

* What lands: `DIR/<index>/stdout`, `DIR/<index>/stderr`, `DIR/<index>/status.json` for captured output, and `DIR/<index>/out/<path>` for output blobs. `status.json` is the `run.result` document of file 17, section 1, of that task. `--flat` writes blobs to `DIR/<basename>`. A basename that is `.`, `..` or fails the path rule is an error, and so is a collision.
* **Atomic publish.** The client writes `DIR/.partial/<index>.<random>/` (stdout, stderr, `out/`), writes `status.json` last, then renames the directory to `DIR/<index>`. When `DIR/<index>` exists (a retry, or `--resume`), the client first renames it to `DIR/.old/<index>.<n>`. A reader treats a directory with `status.json` as complete. There is no `fsync` unless `--durable-results`.
* **Nested layout.** Above 10,000 tasks the layout is `DIR/<index / 1000>/<index>`. Three files for each of 100,000 tasks would otherwise make one huge directory.
* **What the client checks at write.** Every output path comes from a worker. The client applies the path rule of file 16 again. On Linux it writes with `openat2` and `RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS` on `DIR`, `O_CREAT | O_EXCL | O_NOFOLLOW`. Elsewhere it checks each component and refuses a link.
* `--results-pack FILE` (one packed file for many results) is later work (file 24).
* `podswarm logs TASK -f` streams the output of a running task (file 05, `logs`).

### 7.1 What comes back from an attached command
This holds on every view rung, `sync` included. File 06 has the mechanism.
* What git would see comes back to the origin (the caller's machine).
* What git ignores (`target/`, `node_modules/`) stays on the anchor, warm for the next run. A build product does not appear on the caller's machine by itself.
* `[view] pull = [...]` in a workspace file and `--pull GLOB` name paths that always come back. A kept path comes back later with `--pull` on the next run.
* At the end of a run that kept paths, the command prints one line that names them and their size.

## 8. Captured output

* The result carries a head and a tail of each stream, at most `capture_max` bytes (file 05 has the limit, file 12 section 9 has the rule: head, tail, `len`, `trunc`).
* A shape with `capture_blob = true` keeps the whole stream. The worker writes each stream to a file beside `TASK_DIR` (like a spill file, file 12) and uploads it as a blob after the exit, at most `limits.fsize_mib` per stream. The result `out` and `err` entries carry the blob in `id`. The shape field `capture_blob` is a boolean, default false (D-84).
* A live stream of a running task is not a blob (file 05, section 5).

## 9. Slow links

* The link gives each transfer its own window, and the link keeps control frames ahead of data (file 04). A transfer cannot delay `hb` by more than one frame.
* `podswarm join --max-kbps N` limits blob traffic of that worker. Control frames do not count, so the silence budget holds.
* A worker that holds a blob never fetches it (section 4). Most sweeps use one tool and one set of reference data for all tasks.
* Compression follows section 2. There is no delta of a modified file: a modified 200 MB file is sent whole. Chunks (section 1.1) cover a large file that grows or changes in place.
* One stream for each blob is the cost of many small files. A tree of 100,000 small files needs many streams, so it is slow on a link with a long round trip (risk K-18). A pack form is a later change.
* The coordinator is not a file server. Its disk is a buffer. A job that moves tens of gigabytes uses a shared file system, an object store, or URL inputs and writes its results to its own sink.

## 10. Retention

* Blobs: `blob_ttl_days` after the last use, then the sweep (section 1.4). Terminal tasks and inline outputs: the retention of file 11.
* `--pin-outputs` at submit, or `podswarm update RUN --pin`, pins the output blobs of a run (file 18).
* Checkpoints: section 11.9.

## 11. Checkpoints and resume

A long run saves its state and resumes after a loss, a drain or a move to another machine. The core stores state as files in the content store. It holds no Git code and no model of what the files mean.

### 11.1 What a checkpoint is
* A checkpoint is a tree manifest (section 1.1) plus the blobs that it lists, under the name `(task, sequence)`. The name is `<cell>/<run_id>/<task_id>/<seq>` (`eu1/12/345/7`). In a session with no cell, the cell part is absent. `seq` is a u32 from 1, strictly increasing for one task across all attempts. The name is never a path component.
* The program writes its state to `TASK_CHECKPOINT_DIR`, which is `$TASK_DIR/ckpt` on the file system of the task directory (cheap reflinks and hard links). podswarm does not read the files. The program must keep the directory consistent at the moment of the checkpoint.
* The checkpoint row has: `task_id`, `seq`, `attempt_no`, `manifest`, `bytes`, `files`, `created_unix`, `label`, `kind`, `key_id`, `external_ref`, `pinned`, state `complete`. `kind` is `files`. File 11 owns the table `checkpoints`.
* The store is the one of section 1. In a session, the checkpoint lives in the blob store of the home and in its in-memory table. It survives the holder only with `--db FILE` (file 11).

### 11.2 The shape field
`checkpoint` is a shape field (file 05):

| Sub-field | Meaning | Default |
| --- | --- | --- |
| `exit_code` | 1 to 255: an exit code that means "checkpointed, run me again". Not in `ok_codes`: a shape that sets both is refused with `bad_request`. | none |
| `signal` | The signal that asks the program for a checkpoint. | `USR1` |
| `grace_s` | Time the program has to save after a request. 1 to 600. | 30 |
| `every_s` | 60 to 604,800: a timer that asks for a checkpoint. Absent or null is off. | off |
| `retain` | 1 to 100: checkpoints kept for the task (section 11.9). | 2 |
| `max_mib` | 1 to `max_ckpt_mib`: size limit of one checkpoint (section 11.8). | 1,024 |
| `encrypt` | `run`: the checkpoint is encrypted under a caller key (section 11.10). Absent or null is off. | off |
| `sink` | The name of a checkpoint sink plugin (section 11.12). | none |
| `mode` | `explicit`, or `dir_at_end`: when a request ends the attempt with no save, the worker copies the directory as it is. A half-written file can result. `dir_at_end` is unsafe. | `explicit` |
| `partial_ok` | The task may match a worker whose lifetime is shorter than `grace_s` (section 11.7). | false |

Feature `ckpt.1` is negotiated in `hello` (file 04). A shape with `checkpoint` is refused with `unsupported` by a peer that lacks the feature.

### 11.3 Three ways to take one
All three use the one commit of section 11.5.
1. **Exit code.** The program writes its files, then exits with `checkpoint.exit_code`. The worker commits the directory, then sends a result with outcome `checkpointed` and the exit code. The queue runs the task again (section 11.7). The program needs only a loop that tests its own state at start. This is the way to use with a program that cannot call podswarm. [EV-075]
2. **Call.** The program runs `podswarm checkpoint save [--label L]` from inside the run. The command talks to its worker through the Unix socket in `TASK_SOCK`. It returns the name of the checkpoint after the commit, or a non-zero exit and an error. The program keeps running. A call may repeat: a repeated save is a new checkpoint.
3. **Signal, then grace.** The worker sends `checkpoint.signal` to the root process of the tree and waits `grace_s` for the program to call `save` or to exit with `exit_code`. A program that runs under a shell uses `exec`, so the signal reaches it. When the time ends with no commit, the worker applies the kill ladder (file 12). The task then restores the previous checkpoint. A request with `mode = dir_at_end` makes the worker commit the directory at that point.

A request has these causes (section 11.4). When the cause is a drain, a lifetime end or a notice, the attempt ends after the commit: the worker applies the kill ladder and the result has outcome `checkpointed`. A request by a user or by `every_s` leaves the attempt running.

### 11.4 What asks for a checkpoint
| Cause | Who knows | How it arrives |
| --- | --- | --- |
| `user`: `podswarm checkpoint save TASK` | the authority | `ckpt_req` |
| `every_s` | the worker | local; no message |
| `drain`: `worker_drain` (file 10) | the authority | `ckpt_req` for each checkpointing attempt of that worker |
| `lifetime`: the worker is within the drain margin of its end (file 10) | the worker | local |
| `notice`: a preemption notice | the worker only | local; the authority learns that the worker drains for `notice` |

* A worker option `--notice aws-spot|file:PATH|signal:SIG` turns a notice into a request. `aws-spot` polls the instance metadata for an interruption action. The grace is `min(grace_s, remaining time)`. [EV-076] `signal:SIG` covers a scheduler that signals before the end of a job. [EV-077]
* The drain margin of file 10 is `max(drain_margin_s, grace_s + upload estimate)` for a checkpointing task. The upload estimate is the size of the last checkpoint divided by the measured link rate.

### 11.5 Messages and the commit
These messages are in addition to those of file 05.

| `t` | From | Fields |
| --- | --- | --- |
| `ckpt_req` | authority | `items[[task_id, attempt_no]]`, `cause`, `grace_s`, `stop` (the attempt ends after the commit) |
| `ckpt_commit` | worker | `task_id`, `attempt_no`, `seq`, `manifest`, `bytes`, `files`, `kind`, `label?`, `key_id?`, `external_ref?`, `skipped?` |
| `ckpt_ack` | authority | `task_id`, `attempt_no`, `seq`, `verdict` (`accepted`, `stale`, `refused`), `err?` |
| `ckpt_key_req` | worker; the coordinator relays it to a home of the submitter | `task_id`, `attempt_no`, `key_id`, `shield` (the report of file 13 that the run needs) |
| `ckpt_key` | a home of the submitter, or the coordinator with `--key-escrow`; the coordinator relays it | `task_id`, `attempt_no`, `key_id`, `sealed` (the data key sealed to the link key of the worker, base64url with no padding) |

The commit has two phases. The pattern is: stage and verify, then one compare-and-swap. [EV-078]
1. **Stage.** The worker builds the manifest from `TASK_CHECKPOINT_DIR`. It reuses the id of a file whose `(size, mtime, ctime, inode)` equals its record from the last checkpoint of this attempt, except a file that it modified less than 2 seconds before the hash (the racy case). It asks `blob_have` for the ids, uploads the missing blobs and then the manifest (section 2), and runs the sink if there is one (section 11.12).
2. **Commit.** The worker sends `ckpt_commit`. The authority checks:
   * (a) The attempt is held by the sending worker and is `running` or `stopping` (the term "held" is in file 09). A checkpoint counts only from the live attempt. A late commit of an attempt that ended or is lost is `stale`.
   * (b) `seq` is greater than the newest committed `seq` of the task, else `stale`. The worker then deletes nothing: the blobs stay for the sweep.
   * (c) The manifest blob exists and parses; each blob it lists exists (one indexed query for each entry, at most 100,000). The authority skips this check of the listing for an encrypted manifest and checks that the manifest blob exists.
   * (d) `bytes` is within `checkpoint.max_mib` and the quotas (section 11.8).
   * (e) The last commit of this task is at least `ckpt_min_interval_s` old and no commit of this task is in flight. Else the answer is `err{code:"busy", retry_after_ms}`.
   Then one transaction in the writer thread inserts the checkpoint row, adds the references, and the authority sends `ckpt_ack` with verdict `accepted` after the commit is durable at the level of the run (file 11).
A checkpoint is visible to `checkpoint ls`, to restore and to events only after the `ckpt_ack`. A crash between the phases leaves blobs with no reference, and the sweep removes them. A zombie attempt cannot move the pointer: attempt 1 on worker A is cut off, the task runs again as attempt 2 on worker B, which restores `seq` 3 and writes `seq` 4. When A reconnects and commits `seq` 4 with other content, check (a) refuses it.

A call by `podswarm checkpoint save` returns after the `ckpt_ack`. For the exit code way, the worker sends the `result` after the `ckpt_ack`. When the commit fails (`stale`, `refused`, `too_large`), the result has outcome `exited` with the exit code and reason `ckpt_failed`: a failure, and the error text states the limit.

### 11.6 Restore
* The authority offers an attempt of a task that has a complete checkpoint with `extra.ckpt = {seq, manifest, bytes, files, key_id?, ref?}` in the offer row (file 05).
* In state `starting` (file 12), before the exec, the worker materializes the tree into `TASK_CHECKPOINT_DIR`: blobs from the cache first (section 4), the others by `blob_get`. Prefetch starts at the offer (section 2).
* The environment of the program has `TASK_RESUMED=1`, `TASK_CHECKPOINT_SEQ=<n>` and `TASK_CHECKPOINT_DIR`. `TASK_SOCK` is always set. A program that finds `TASK_RESUMED` unset starts from zero. The program decides what to read.
* A blob that is missing or does not verify ends the attempt as `spawn_failed`, reason `input`, text `checkpoint`. The authority marks that checkpoint `damaged`, emits `checkpoint.damaged` (file 17), and offers the next older complete one. When none remains the task starts from zero with `TASK_RESUMED` unset.
* A restore needs the blob cache or the link. When the blob copy is gone but the row has `external_ref`, the offer carries `ref` and the worker calls the sink `get` (section 11.12).

### 11.7 What the queue does with a checkpoint
* The pointer is the newest complete `seq` of the task. A retry, a re-offer after a loss (T8) and a manual `retry` attach it to the new offer. The user sets nothing: a shape with `checkpoint` restores by itself. `retry --fresh` ignores the pointer.
* A loss still counts against `max_lost`. The new attempt does not start from zero: at most the work since the last checkpoint is lost.
* A result with outcome `checkpointed` makes the task `ready` again, spends no retry and no `max_lost`, and raises `attempt_no`. The cap of 1,000 attempts counts it (file 09). A drain, a lifetime end and a notice ask for a checkpoint first (section 11.4), so a drain does not start work from zero.
* A task with `checkpoint` is not matched to a worker whose remaining lifetime is under `grace_s` (file 10, lifetime matching) unless `partial_ok` is set.
* The engine prefers, as a tie-break only, a worker that holds the blobs of the manifest, because a restart on the same machine costs nothing (file 10). It is never a filter.
* A task lives in one cell (file 08). A checkpoint leaves its cell only by `checkpoint export`, and only when the residency rule of the destination allows it. `checkpoint export` writes a manifest and its blobs to a directory, and `checkpoint import DIR TASK` reads them into a task of another cell, which resumes from it (D-88). `checkpoint show`, `pin`, `unpin` and `rm` read a checkpoint row, set or clear `pinned`, and remove a checkpoint (section 11.9).

### 11.8 Size limits
* One checkpoint has at most `checkpoint.max_mib`. A submitter has `max_ckpt_mib`: the sum of the bytes of the complete checkpoints that the submitter owns, each owner paying the full size; default 10,240 MiB, range 0 and up, 0 refuses every checkpoint; a column of the table `submitters` (file 11). A commit over it gets the verdict `refused` with `err{code:"quota", limit, used, scope}`. The coordinator has `blob_max_mib` for one blob and the quotas of section 1.5.
* The authority states each limit in `ready.limits` and in the error: `err{code:"too_large", limit, used, scope}`. The worker checks the sizes against `ready.limits` before it uploads. [EV-079] A client that hardcodes a limit is wrong when the server changes.
* A checkpoint reader fails loudly at its limits: a manifest over 8 MiB or 100,000 entries is a refusal, not a cut list.

### 11.9 Retention
* The newest `retain` complete checkpoints of a task stay, and so does each pinned one (`checkpoint pin`, or `checkpoint save --pin`).
* After a task ends `succeeded`, its checkpoints go after `ckpt_after_end_days`. After `failed` or `cancelled`, they go after `ckpt_after_fail_days`, so a person can restart from the last one. The blobs follow by the references and the sweep (section 1.4).
* A person lists and edits checkpoints with `podswarm checkpoint ls|show|pin|rm` (file 18). The MCP tool `checkpoint` of file 17 has `save` and `ls`. The event `checkpoint.saved` is in file 17.

### 11.10 Encryption under a caller key
* `checkpoint.encrypt = "run"`: the caller makes a data key for the run. A tree under this mode uses the sealed object format of file 13 (section 6.4), with the data key in place of the machine key. The id of an object is `b3k:<64 hex>`: the keyed BLAKE3 hash of the plain bytes under the data key. Equal content has equal ids inside one run, so dedupe works, and ids of two runs never match. The manifest is an object too. Its header has `enc=b3k`.
* A file over 1 MiB is split into objects of 1 MiB (`C` entries). A receiver cannot check a `b3k:` id. It checks the size, and the party that decrypts checks the tag and the id.
* The authority stores ciphertext and an opaque `key_id` (the first 8 bytes of the BLAKE3 hash of the data key). It cannot read names, modes or sizes beyond rounded lengths.
* The key stays with the caller. In a session the home sends it to the worker over the link; the shield rules and the restore rules (a restore goes to a machine at the shield of the attempt or higher) are in file 13. At shield `private` or above the worker holds the key in memory only.
* **The key in a swarm** (D-126). The key stays with the submitter. A worker that starts an attempt with `encrypt = "run"`, to write or to restore a checkpoint, sends `ckpt_key_req` in the state `starting` (file 12). The coordinator relays it to a connected home of the submitter. The home checks the shield report that the run needs (file 13) and answers `ckpt_key`, sealed to the link key of the worker. With `--key-escrow` the coordinator holds the key in its secret store and answers itself (file 16, section 18.1). When no home of the submitter is connected and there is no escrow, the attempt ends `not_started` with no retry spent, and the task is `held` with the reason `needs_key` (file 09) until a home of the submitter connects. So an encrypted run in a swarm needs a connected home of the submitter at each start of an attempt, or escrow.
* **Scope.** This protects the stored checkpoint, the caches of other workers, backups and a coordinator that the caller does not trust. It does not protect against the machine that runs the attempt: that machine holds the plain bytes and the key. Host protection is the shield (file 13).
* Without `encrypt`, a checkpoint is plain at rest. `podswarm doctor` prints `checkpoints are not encrypted` when the coordinator is another machine than the submitter and the boundary is below `vm`.
* `encrypt` and `sink` exclude each other: a sink reads a plain directory.
* A workspace file can add `encrypt` and lower `max_mib`. It cannot remove `encrypt`. A setting that lowers protection comes only from a file that the user owns.

### 11.11 What a checkpoint of a working tree leaks
A checkpoint of a working tree is a full copy of the files, and it is as readable as the host that holds it. [EV-080]
* The worker applies the credential deny list of file 13 when it builds a manifest. A file whose name is on the list is not put in the checkpoint. The commit carries `skipped` with the paths, and the event `checkpoint.saved` shows them. A filter is a partial defense and does not make a tree safe.
* A checkpoint on a worker, and the copy in the blob cache, stay in the work area at shield `private` or above and are removed at exit (file 13).
* Redaction is not a core feature. A sink plugin can redact before it pushes.

### 11.12 The Git sink and other sinks
Core holds no Git code and no Git credential. `checkpoint.sink = "NAME"` makes the worker run the plugin `podswarm-ckpt-NAME` (file 17). The worker runs `put` after it builds the manifest and before `ckpt_commit`, with `dir` set to the directory on the worker. The `ref` that the plugin returns goes into `ckpt_commit.external_ref`. A failure of the sink does not fail the checkpoint: the commit goes without `external_ref`, and the event says so. The blob-store copy is the one that restore uses (D-87). A checkpoint may hold both a blob-store copy for speed and an external ref for history.

| Use the blob store (default) | Use a Git sink |
| --- | --- |
| large or binary state; no forge account on the host; encrypted checkpoints; a cell with a residency rule | small text state; history that people read with Git tools; the access control, backup and signed commits of the forge |

A sink holds the push credential and gets it from the user. A platform gets the checkpoint model of a Git forge with no feature in core.

### 11.13 Later rungs
A checkpoint of a process (the image of a running process) and the migration of a guest use the same manifest and the same commit, with `kind` `process` or `guest`. The mechanism and its limits are in file 07.

## 12. Settings defined here

| Name | Scope | Type | Range | Home |
| --- | --- | --- | --- | --- |
| `blob_max_mib` | coordinator | MiB | 1 and up; default 4,096. The largest single blob; not the quota `max_blob_mib` of file 16 | section 1.5 |
| `cache_max` | worker, home | bytes | 1 GiB and up; default the smaller of 20 GiB and 10 percent of free space at first use | section 1.5 |
| `max_ckpt_mib` | submitter | MiB | 0 and up; default 10,240 | section 11.8 |
| `max_blob_bytes` | coordinator | bytes | default 50 percent of the free space at start | section 1.5 |
| `blob_streams_max` | authority | count | 1 to 1,024; default 32 | section 2 |
| `fanout_warn`, `fanout_max` | submitter | bytes | defaults 10 GiB and 100 GiB | section 5 |
| `url_fetch_s` | worker | seconds | 10 to 86,400; default 600 | section 3.5 |
| `--max-kbps` | `join` flag | kilobits per second | 0 (off) and up; default 0 | section 9 |
| `ckpt_chunk_over` | worker | MiB | 8 to 4,096; default 64 | section 1.1 |
| `ckpt_min_interval_s` | authority | seconds | 0 to 3,600; default 10 | section 11.5 |
| `ckpt_after_end_days` | coordinator | days | 0 to 3,650; default 1 | section 11.9 |
| `ckpt_after_fail_days` | coordinator | days | 0 to 3,650; default 7 | section 11.9 |
| `--notice` | `join` flag | `aws-spot`, `file:PATH`, `signal:SIG` | none by default | section 11.4 |
| `checkpoint.*`, `capture_blob`, `files`, `outputs` | shape | file 05 | see sections 3, 6, 8, 11.2 | file 05 |

Fixed values, not settings: 2 transfers for each worker in each direction; 2 partial files and 8 GiB of partial data for each link; partial files kept 1 hour; 256 output files for each task; 100,000 entries for a tree, an unpack and a manifest; 8 MiB for a manifest; 24 hours of guard in the sweep; 3 redirects for a URL input.
