# 21. Crates and asks

This file defines the repository of podswarm, its crates, the build rules, the crates that podswarm takes from podcrates, the generic mechanisms that podswarm gives to podcrates as `pod-*` crates, the asks to podcrates, podvm and podnet, and the traits with conformance suites. File 02 gives the rules of the org and the role of each repository. File 22 places each ask in a milestone. File 23 holds the suites and the guards.

## 1. The pin

The pin lives in this file only. Other files name a crate, never a tag.

| Project | Version | Note |
| --- | --- | --- |
| podcrates | `v0.34.0`, commit `ee514e7`, 38 crates | the tag in `Cargo.toml` of podswarm; Rust 1.99, edition 2024 [EV-117] |
| podvm | `v0.2.0-beta.6` | run as a program for boundaries `sandbox` and `vm` and shield `guest` |
| podnet | `v0.4.0-beta.6` | run as a program for the network policy (file 14) |
| podssh | `v1.1.0-beta.3` (takes podcrates `v0.31.0`) | run as a program for the `podssh://` road (file 04) |
| podrunner | `v0.1.0-beta.1` (takes podcrates `v0.32.0`) | a sibling; no dependency |
| HyperShell | `2.8.7` (master), `2.9.0a7` (develop) | the parity tests of file 20 run against both |

Refresh rule. At the start of each milestone of file 22 the podswarm session moves the pin to the newest podcrates tag and to the newest release of each program in the table. It runs the full gate (file 23), reads the rows of sections 5 and 7 again against the new tags, and writes the new pin, the rows that differ and the closed asks in one commit. podswarm moves its toolchain to the toolchain of the new podcrates tag in the same commit. A milestone does not close on an older pin than the one read at its start.

## 2. The repository

`PodUtils/podswarm`. The owner creates it. Licence 0BSD.

```
podswarm/
  Cargo.toml  Cargo.lock  rust-toolchain.toml  .cargo/config.toml  deny.toml  rustfmt.toml
  AGENTS.md  README.md  SECURITY.md  LICENSE  THIRD-PARTY-NOTICES
  TODO/            the work record, checked by `cargo todo` (podswarm-todo)
  docs/            what is true now: design, wire, decisions
  schemas/         JSON Schemas generated from podswarm-proto
  scripts/         check-static.sh, check-size.py, check-layers.py, lint-docs.py, plants/
  tests/cases/     case files: input, template, expected (file 23)
  tests/regress/   shrunk event logs of the simulation (file 23)
  crates/          the crates of section 3
```

## 3. Crates

| Crate | Holds | I/O |
| --- | --- | --- |
| `podswarm` | the binary: `main.rs` only; one multicall binary for every role (`psw` by `argv[0]`) | yes |
| `podswarm-cli` | argument parsing, config files, output formats, exit codes, the agent face (`mcp`, `skill`), the plugin host | yes |
| `podswarm-proto` | messages, codec (JSON, zstd), limits, error codes and classes, feature names, schema generation | no |
| `podswarm-core` | task and attempt records, transitions T1 to T11, invariants I1 to I7 as checks, the scheduler step, placement scores, the learned table, `Clock` | no |
| `podswarm-store` | the `Store` trait, `SqliteStore`, `MemStore`, backup, migration; the content store until `pod-cas` exists | yes |
| `podswarm-coord` | the authority engine for a home and a coordinator: link sessions, the actor loop, the writer thread, the reaper, invites, submitters, the local socket | yes |
| `podswarm-worker` | the worker engine: the link, the holding, the journal, the probe cache, the blob cache, the start of the view server | yes |
| `podswarm-exec` | the executor: spawner and keeper on top of `pod-proc`, containment rungs, limits, `confined`, the terminal, the guest relay | yes |
| `podswarm-tmpl` | the template language: parser, expander, tokens | no |
| `podswarm-net` | roads, bootstrap of the binary, the link setup, the holder socket, reattach, `wss` with TLS, the hub | yes |
| `podswarm-view` | the view: the home index and watcher, the view server, the rungs, write-back, the sync rung | yes |
| `podswarm-spread` | exec-level spreading: the exec supervisor, the stub, the decision rules, the causal publish (file 07) | yes |
| `podswarm-sim` | the deterministic simulation: scheduler, fake clock, fake network, fake disk, oracle, shrinker; the shaping proxy for live tests | fake only |
| `podswarm-bench` | the benchmarks and the load generator of file 23 | yes |
| `podswarm-todo` | a wrapper of `pod-todo`, as `podrunner-todo` | yes |

Layer rule, checked by `scripts/check-layers.py` (guard G-08 of file 23):
* `podswarm-proto`, `podswarm-core` and `podswarm-tmpl` depend on no I/O crate, no tokio and no other `podswarm-*` crate except `podswarm-proto`. They call no `Instant::now`, `SystemTime::now`, `thread::spawn` or `tokio::spawn`, and no decision iterates a `HashMap`. Time comes from `Clock`, randomness from an `Rng` argument.
* `podswarm-store` depends on core and proto types only, plus SQLite.
* `podswarm-coord`, `podswarm-worker`, `podswarm-view` and `podswarm-spread` reach the network, the disk, the clock and processes only through the traits of section 9 and `Clock`, so that `podswarm-sim` runs them.
* `podswarm-cli` depends on the engines. The binary depends on all.
Reason: the state machine and the engines run under the fake clock and the fake network of the simulation.

## 4. Build rules

* Toolchain: the `rust-toolchain.toml` of the pinned podcrates tag. Edition 2024. Nightly only where an entry needs it, with the gain it measured.
* Targets: the 14 targets of podcrates `docs/design.md` section 7: eight `*-linux-musl*`, two `*-linux-gnu`, two `*-apple-darwin`, two `*-windows-msvc`. A musl build is a static executable with no `NEEDED` entry and no interpreter (guard G-03). An Apple or Windows build links system libraries only (G-04). A gnu build is not called static.
* Profile `release`: `lto = "fat"`, `codegen-units = 1`, `strip = true`, `panic = "unwind"`. A panic in one link session ends that session only. A panic that reaches `main` exits 70. The spawner and each keeper install a panic hook that calls `abort`, because they run between `fork` and `exec` (D-119).
* Size: a stripped x86_64 musl binary with default features has at most 10,000,000 bytes (target A-09, guard G-13).
* Allocator: `mimalloc` (C, built by `cc`, linked static) as the global allocator on musl targets; the system allocator elsewhere.
* Hash: the `blake3` crate. Its assembly and C paths build by `cc` for each target; a target where they do not build uses the feature `pure`. CI records the choice per target.
* Compression: the `zstd` crate with the bundled C library (`zstd-sys`, static). No gzip anywhere.
* Store: `rusqlite` with feature `bundled`; the SQLite amalgamation is at least 3.51.3 (G-01).
* TLS: `rustls` through `pod-tls` with the `ring` provider, as podcrates prefers on targets where `aws-lc-sys` is not proven.
* Attestation: the `sev` crate with `default-features = false, features = ["snp", "crypto_nossl"]`, behind the cargo feature `sealed` (file 13), until `pod-attest` exists.
* Licences: `deny.toml` copies the allow list of podcrates (0BSD, Apache-2.0, BSD-2-Clause, BSD-3-Clause, CDLA-Permissive-2.0, ISC, MIT, Unicode-3.0, Zlib) and allows the git source of podcrates. [EV-118]
* Notices: `cargo deny` sees no C source. The release job generates `THIRD-PARTY-NOTICES` from the crate tree (`cargo about`) and appends the notices of the C code that the binary links: SQLite (public domain), zstd (BSD-3-Clause), mimalloc (MIT), BLAKE3 C (Apache-2.0). The file ships beside each binary. Guard G-14 fails when one of the four is absent.
* Gate on each push: `cargo fmt --all --check`, `cargo clippy --workspace --all-targets --all-features -- -D warnings`, `cargo test --workspace --all-features`, `cargo todo check`, and the guards of file 23.
* A source file has at most 500 lines (G-02).

## 5. What podswarm takes from podcrates

File 02 gives the role of each crate. This table gives the items that podswarm calls.

| Crate | For | Items |
| --- | --- | --- |
| `pod-core` | failures, dials, files, backoff | `Failure`, `Stage`, `Class`, `Dial`, `Resolve`, the exit code table, private files, state places, `backoff` |
| `pod-identity` | keys and fingerprints | `Identity::{from_seed, public, sign}`, `PublicKey::{fingerprint, verifies, parse}`, `file::load`, `DisplayFingerprint`, pins |
| `pod-tls` | TLS on `wss` roads | `peer::{client_config, server_config, Keys, peer_key, refusal}` only: Ed25519 keys pinned on both sides as `pod_identity::KeyName`, TLS 1.3 only, no resumption, a key set that changes while the server runs (D-129; P-3 adds the enrolment mode) |
| `pod-proxy` | the dialer of a worker that dials out; the child process of the `ssh` and `exec:` roads | `Dialer` with `lowat: Some(16384)`, `http::request::read_request`, `stream::ChildIo` (P-10) |
| `pod-dns` | names on a worker with no resolver file | the resolver with its fallback list |
| `pod-ws` | WebSocket client and server | `url::dial`, `server::{check_upgrade, switching, session}`, `RelaySession` (P-2); the key of the peer comes from the TLS connection before the upgrade (`pod_tls::peer::peer_key`) |
| `pod-link` | the link of every road | `Link::{new, open, accept, rtt}`, `Settings`, `Stream`, `Carrier` (`memory`, `unix`), `BoxIo` (P-4) |
| `pod-confine` | boundary `confined` | `Spec`, `check` (Landlock ABI), `apply` |
| `pod-hostprobe` | the probe rows and process primitives | `probes`, `sys::{set_child_subreaper, reap_any, set_rlimit}` (P-5, P-6) |
| `pod-job` | shared spellings | `LimitMode`, `Boundary`, `Residual` (P-8) |
| `pod-hold` | the network hold; later `trap` and the exec supervisor | `filter::{Calls, install}`, `listen::Listener`, `mem::Memory`, `reply::{respond, proceed, addfd_send}`, `netns` (P-14, P-15) |
| `pod-netstack` | the user-mode stack of the hold rung `netns` in its linked form and of the guest (files 13, 14) | the stack and its device, from M7 |
| `pod-incus` | the incus rung of boundary `vm` (`incus.1`, file 24 section 9) | the REST client on the Unix socket of `incusd`, from M8 |
| `pod-term` | a worker host with no pty | `echo::Discipline`, `passthrough`, `window` |
| `pod-enter` | the FUSE wire until `pod-fuse` exists | `fuse` (P-16) |
| `pod-relay` | the `relay://` road | the reverse node and operator |
| `pod-guest` | the guest plan of shield `guest` | `plan::argv` (P-18) |
| `pod-todo`, `pod-testkit` | the record; loopback stand-ins and guards in tests | `cargo todo`; the testkit guards |

Not taken, with the reason in file 02: `pod-session`, `pod-e2e`, `pod-quic`, `pod-wg`, `pod-warp`, `pod-netlab`, `pod-oci`, `pod-extract`, `pod-rootfs`, `pod-actions-expr`, `pod-actions-workflow`, `pod-services`, `pod-services-watch`, `pod-gsr`, `pod-supervise` (through `pod-proc` only), `pod-broker`, `pod-devtunnel`, `pod-turn`, `pod-wormhole`. The feature `tcp` of `pod-link` (a TCP carrier with TLS 1.3 and pinned Ed25519 keys) is not taken: the `wss` road crosses HTTP proxies and relays, and a plain TCP road adds a second listener path. The 19 crates of the table above and these 19 make the 38 crates of the pin.

## 6. What podswarm gives to podcrates

The owner asked for "podswarm and related crates". A mechanism that a second PodUtils project can use goes to podcrates as a `pod-*` crate, through the procedure of podcrates `docs/design.md` section 8: import, tests with the loopback guards, a fuzz target per parser, a plant per guard, the static probe on the 14 targets, an adoption trial for each consumer. Each crate reads no variable, prints nothing and keeps no global. Until a crate is released, its code lives in the fallback named here, and podswarm moves to the crate on the day of its release.

The acceptance of an ask is what the target repository runs by itself: unit, loopback and fuzz tests of the crate, and its own adoption trials. A suite of podswarm (section 9, file 23) that runs on the crate is the adoption trial of podswarm, not acceptance.

| Crate | Ask | Spec file | Consumers besides podswarm | Milestone |
| --- | --- | --- | --- | --- |
| `pod-proc` | P-1 | 12, 07 (takeover) | `pod-supervise`, podvm, podrunner | M0 |
| `pod-tty` | P-11 | 18 | podssh | M1 |
| `pod-fuse` | P-16 | 06 | `pod-enter` (podvm) | M1 |
| `pod-cas` | P-12 | 15 | podssh `run HOST:DIR`, podrunner (candidates) | M6 |
| `pod-view` | P-17 | 06 | podssh `run HOST:DIR`, podrunner (candidates) | after M2 |
| `pod-attest` | P-19 | 13 | podvm (confidential guests) | M8 |
| `pod-ssh` | P-13 | 04 | podssh (its own client) | M10 |
The growth of `pod-hold` (P-15, files 06, 07, 14) is M2 for `trap` and M3 for spreading. No other new crate is asked; `pod-trap` is not a crate (6.5).

### 6.1 `pod-proc`: process control (ask P-1)

Holds the spawner, the keeper, the containment rungs (`cgroup`, `pidns`, `subreaper`, `reaper`, `job`, `session`), the kill ladder and the residual count, limits with their modes, the terminal of an attempt (`openpty` on Unix, ConPTY on Windows), and the exec takeover of spreading. It moves `launcher/tree.rs` out of `pod-supervise`, which then depends on `pod-proc`; it moves `pod_enter::limits::{Resource, Limit}` the same way. Builds on every target. No tokio.

```rust
pub fn start(opts: Options) -> io::Result<Spawner>;  // call before any thread exists
pub struct Options { pub keeper: bool, pub containment: Want }      // Want::Best | Want::AtMost(Rung)
pub enum Rung { Cgroup, Pidns, Subreaper, Reaper, Job, Session }
impl Spawner {
    pub fn rung(&self) -> Rung;
    pub fn spawn(&self, plan: Plan) -> io::Result<AttemptId>;
    pub fn signal(&self, id: AttemptId, how: How) -> io::Result<()>;   // Polite | KillTree
    pub fn fence(&self, kill_at: FenceTime) -> io::Result<()>;          // the spawner kills each tree at this time
    pub fn event_fd(&self) -> RawFdOrHandle;                            // readable when an event waits
    pub fn next_event(&self) -> io::Result<Option<Event>>;              // Running { id, pid } | Ended { id, exit }
}
pub struct Plan { pub argv: Vec<OsString>, pub env: Vec<(OsString, OsString)>, pub cwd: PathBuf,
                  pub stdio: Stdio /* Pipes | Merge | Pty(WinSize) | Null */, pub limits: Vec<Limit>,
                  pub sched: Sched, pub umask: u32, pub setns: Vec<OwnedFd> /* Linux */,
                  pub confine: Option<pod_confine::Compiled> /* Linux */ }
pub struct Exit { pub status: Status, pub usage: Usage, pub residual: pod_job::Residual, pub peak_mem_kib: Option<u64> }
pub mod tree;      // moved from pod-supervise; TREE_KILL_MS = 5,000
#[cfg(all(target_os = "linux", any(target_arch = "x86_64", target_arch = "aarch64")))]
pub mod takeover;  // PTRACE_SEIZE, stop at the exec, exec the stub, detach (file 07); on the pod-hold items of 6.5
```
Second consumer: `pod-supervise`, and through it podvm and podrunner. Fallback: `podswarm-exec/src/proc/`.

Acceptance of P-1:
* Two attempts at once; one leaks a `setsid env -i sleep` grandchild. Both exit codes and both residual counts are right; only the tree of that attempt is killed (F-20 of file 23).
* `SIGKILL` of the caller, of the spawner and of a keeper, alone and together: each attempt process, the grandchild included, is dead within the kill grace plus 2 s (F-19). With no `/proc` the residual count is `unknown`, never 0.
* A fence time that passes while the caller is stopped (`SIGSTOP`) kills each tree. `Stdio::Pty` gives the child a terminal, and a window change reaches it.
* `takeover` on x86_64 and aarch64, with a stub of the test: the four cases of the prototype of file 07 (a `fork` plus `execve` that moves; a `posix_spawnp` with `CLONE_VM | CLONE_VFORK` that moves; a local exec that stays and runs untouched; a failed exec whose caller sees the `ENOENT` of the kernel), then a caller with threads and a `#!` script. A moved process keeps its pid and the exit status of a local run (U-spread-takeover).
* The tests of `pod-supervise` and `pod-enter` pass with no change; the static probe builds on the 14 targets; the adoption trials of podvm and podrunner pass.

### 6.2 `pod-cas`: content store (ask P-12)

Holds BLAKE3 ids (`b3:` and keyed `b3k:`), the layout `<root>/blobs/<2 hex>/<62 hex>`, a writer that hashes while it writes, ranged reads, placement into a directory (reflink, else copy), the sweep with an age guard, tree manifests with chunks, and the transfer header with resume at an offset. Formats and numbers: file 15.

```rust
pub struct Id([u8; 32]);                       // Display and FromStr: "b3:<64 hex>"
pub enum Obj { Plain(Id), Keyed(Id) }          // "b3k:" for an encrypted object
impl Store {
    pub fn open(root: &Path, cap: Cap) -> Result<Store, Failure>;
    pub fn has(&self, id: &Id) -> Option<u64>;                          // size
    pub fn writer(&self, size: u64, at: u64) -> Result<Writer, Failure>; // resumes a partial file
    pub fn read_range(&self, id: &Id, off: u64, len: u32) -> Result<Vec<u8>, Failure>;
    pub fn place(&self, id: &Id, dst: &Path, how: Place) -> Result<(), Failure>;  // Reflink | Copy
    pub fn sweep(&self, live: &dyn Fn(&Id) -> bool, min_age: Duration) -> Result<Swept, Failure>;
}
pub struct Manifest { pub entries: Vec<Entry> } // path, mode, size, id or chunk ids; itself a blob
pub fn missing(have: &dyn Fn(&Id) -> bool, want: &Manifest) -> Vec<Id>;
pub mod transfer;                               // header {id, size, offset, len, enc}; answer have | done | err
```
Second consumer: podssh `run HOST:DIR` (send only the files that differ), podrunner (job inputs and artifacts). Both are candidates; the ask is filed when M1 code shows the API. Fallback: module `cas` in `podswarm-store`.

### 6.3 `pod-fuse`: a FUSE server with no libfuse (ask P-16)

Takes the wire and the mount out of `pod-enter` `fuse.rs` and `fuse/wire.rs`, and adds the write opcodes, `READDIRPLUS`, the invalidation notices and cloned session descriptors. The server runs in a forked single-thread child, as in `pod-enter`. [EV-119]

```rust
pub fn mount(at: &Path, opts: &MountOpts) -> Result<Session, Failure>;  // fd=, nosuid, nodev; no fusermount3
pub trait Fs {
    fn lookup(&mut self, parent: Ino, name: &OsStr) -> Reply<Entry>;
    fn getattr(&mut self, ino: Ino) -> Reply<Attr>;
    fn readdirplus(&mut self, ino: Ino, off: u64, out: &mut DirSink) -> Reply<()>;
    fn read(&mut self, ino: Ino, fh: Fh, off: u64, len: u32) -> Reply<Bytes>;
    fn write(&mut self, ino: Ino, fh: Fh, off: u64, data: &[u8]) -> Reply<u32>;
    // open, create, mkdir, unlink, rmdir, rename, setattr, symlink, link, fsync, release: same form
}
pub fn serve(session: Session, fs: &mut dyn Fs) -> Result<(), Failure>;
impl Session { pub fn notifier(&self) -> Notifier; } // inval_entry, inval_inode
```
Second consumer: `pod-enter`, whose read-only rung moves onto it (podvm). Fallback: `podswarm-view/src/fuse/`, a copy of the `pod-enter` wire under 0BSD.

Acceptance of P-16:
* One test for each write opcode over a socket pair (`create`, `write`, `fsync`, `rename`, `unlink`, `mkdir`, `rmdir`, `symlink`, `link`, `setattr`, `release`): it checks the reply bytes and the call on an `Fs` of the test. `READDIRPLUS` gives each entry with its attributes in one reply. `inval_entry` and `inval_inode` write the notice bytes of the kernel ABI.
* A real mount of an in-memory `Fs` of the test, as root and in a new user namespace, on a host where `/dev/fuse` opens (else the test prints `skipping, REASON`): a shell copies a tree in, renames, deletes and calls `fsync`, and the result equals the same steps on a `tmpfs`. Two readers on cloned descriptors serve one mount.
* The fuzz target of the request parser runs in CI. The tests of `pod-enter` pass with no change. The static probe builds on the 14 targets.
* Adoption trials: podvm through `pod-enter`; U-conf-view of podswarm on the rungs `fuse` and `fuse-userns`.

### 6.4 `pod-view`: the view (ask P-17)

Holds the stat-based directory records and lazy validation, the frame codec of the view protocol (no transport), the worker cache on `pod-cas`, the upper layer, the ordered write-back log with conflict copies and held items, the clock offset of mtimes, and the `ViewRung` trait of section 9. The rules are in file 06.

```rust
pub struct Index { /* records of one export root; watcher input */ }
impl Index { pub fn open(root: &Path, rules: &Rules) -> Result<Index, Failure>;
             pub fn record(&mut self, nid: Nid) -> Result<Record, Failure>;   // validates lazily
             pub fn apply(&mut self, op: &WriteOp) -> Result<Applied, Failure>; }
pub mod frame;       // ops: lookup, record, want, validate, put, verr ...
pub mod writeback;   // Log, Op, Held, Conflict
pub trait ViewRung { /* the trait of section 9, as it is */ }
pub mod conformance; // the ViewRung suite, public, so that each rung runs it
```
Second consumer: podssh `run HOST:DIR` as a live view in place of the copy; podrunner job workspaces. Both are candidates. Fallback: the crate `podswarm-view`. The ask is filed after M2, when `fuse`, `fuse-userns`, `trap` and `sync` share one API.

Acceptance of P-17: loopback tests in the crate, with a temporary directory as the home, a temporary directory as the upper layer of the far side, and the frames on an in-memory pipe.
* The pipe is cut during write-back: after a new session each op is applied once, in `seq` order (the crate part of F-40 of file 23).
* The home file changes after `base_ver`: a conflict copy exists and both contents are kept (F-41). A watcher overflow given to `Index`: the next `record` validates again and gives the new `ver` (F-42). A log with ops that have no `wback`: the next session applies it first (F-43).
* A far clock at plus and minus 30 s: each mtime on the home equals the far mtime minus the offset of file 06, section 9 (the crate part of F-44).
* The unlink of more entries than the threshold of file 06, section 10.5 is held (F-45). A `nid` that the home did not issue, a write through a symlink and a write of `.git/hooks/x` are refused or held (F-46). A path of the deny list gives no record (F-47).
* The `conformance` suite runs against a rung of the tests that serves the view in a temporary directory, and against one planted bad rung, which fails it.
* The fuzz targets of the frame codec and of the record decoder run in CI. The static probe builds on the 14 targets.
* Adoption trial: F-40 to F-47 and U-conf-view of podswarm, with `cargo` and `make` on the four rungs.

### 6.5 The exec and file trap: a growth of `pod-hold`, not a new crate (asks P-15, P-14)

The view rung `trap`, the exec rung `seccomp` of spreading (file 07) and the network hold (file 14) share one mechanism: a seccomp filter that returns `SECCOMP_RET_USER_NOTIF` for a list of calls, a supervisor that reads the memory of the stopped task and answers with an error, a `CONTINUE` or a new descriptor. `pod-hold` has this mechanism today: `Calls::of(&[nr])` builds a filter for any call list, `listen::Listener` takes the notifications, `mem::Memory` reads and writes the task, `reply::proceed` is `CONTINUE` and `reply::addfd_send` injects a descriptor. [EV-120] So the shared trap is a growth of `pod-hold` (D-120). A crate `pod-trap` is not asked. Whether podvm has a call interceptor to share is an unknown of file 26.

The exec takeover of spreading is not in `pod-hold`. The module `takeover` of `pod-proc` (6.1, ask P-1) owns `PTRACE_SEIZE`, the exec stop, the trampoline, the stub exec and the detach (file 07, section 3.2), and its acceptance holds the four takeover cases. `pod-hold` gives the parts under it: the filter with the marker, the listener, the memory reads of the stopped task, and the replies (`reply::proceed` is `CONTINUE`; `reply::respond` gives an errno).

```rust
impl Calls {   // ask P-15
    pub fn with_marker(self, nr: c_long, arg: u8, value: u32) -> Calls; // no notice for `nr` when the low 32 bits of args[arg] (0 to 5) equal value
    pub fn enosys(self, nrs: &[c_long]) -> Calls;                      // ENOSYS and no notice: io_uring_setup and friends
}
// filter::install exists: it installs on the calling thread, which is the whole process in the
// single-thread payload child of a keeper. The child sends the descriptor by SCM_RIGHTS. No new call.
impl Memory { pub fn read_cstr(&self, addr: u64, max: usize) -> Result<CString, Failure>;        // max: bytes with the NUL
              pub fn read_argv(&self, addr: u64, max: usize) -> Result<Vec<CString>, Failure>; } // max: all bytes; a NULL pointer ends it
pub struct PreExec {                           // ask P-14; made before the fork, applied by the child with no allocation
    pub setsid: bool, pub umask: Option<u32>,  // after a reset of the signal mask and of each handler
    pub setns: Vec<OwnedFd>,                   // namespaces to enter, in this order
    pub rlimits: Vec<(c_int, libc::rlimit)>, pub cwd: Option<CString>,
    pub fds: Vec<(OwnedFd, c_int)>,            // each moved to its number; then each other descriptor from 3 up is closed
    pub confine: Option<pod_confine::Compiled>, // pod_confine::apply, the last step before execve
}
impl Program { pub fn with_plan(self, plan: PreExec) -> Program; }   // one fork for the hold and the keeper
```
A step of `PreExec` that fails makes the child write the step and the errno to a close-on-exec pipe and exit 127 with no exec; `spawn::start` then returns a `Failure` that names the step.

Acceptance of P-15: an `execve` with the marker value in its argument register runs with no notice, and with another value it notifies; a call of the `enosys` list fails with `ENOSYS` and gives no notice; a single-thread child calls `filter::install` and sends the descriptor, and a `Listener` of the parent reads its notices; `read_cstr` and `read_argv` read the path and argv of a stopped `execve`, refuse a string longer than `max` by name and refuse an address outside the task; a fuzz target runs `read_argv` over `Memory::of_fd`. Acceptance of P-14: a held child sees each step of the plan before `execve` (a limit, the `cwd`, the descriptor numbers, a namespace by its inode, a Landlock rule), and a failed step is named with no exec. Both: the tests of `podnet pod` pass with no change, and the adoption trial of podnet passes.

Consumers: podnet (`podnet pod`, today) and podswarm. Fallback: `podswarm-exec/src/trap/` on top of `pod-hold` as it is, with a shim process (file 14).

### 6.6 `pod-attest`: attestation of a confidential guest (ask P-19, later)

Holds the check of an SEV-SNP report (chain from the pinned AMD roots, signature, measurement, report data, policy, TCB floor) and later of a TDX quote, and the expected measurement of a guest set. Rules: file 13 section 8.

```rust
pub enum Platform { SevSnp, Tdx }
pub struct Policy { pub measurement: [u8; 48], pub tcb_floor: TcbFloor, pub smt: bool, pub chip: Option<ChipId> }
pub fn verify(p: Platform, report: &[u8], certs: &Certs, data: &[u8; 64], pol: &Policy) -> Result<Verdict, Refusal>;
pub fn expected_measurement(set: &GuestSet, vcpus: u32) -> [u8; 48];
```
Second consumer: podvm, for confidential guests. Fallback: `podswarm-exec/src/attest/` on the `sev` crate.

What `verify` checks, in this order, each failure named by its field (file 13, section 8.3): `chain` (the embedded ARK of the product signs the ASK or ASVK, which signs the VCEK or VLEK of `certs`; a CRL of `certs` is checked when present), `signature` (ECDSA P-384 of the report by that VCEK or VLEK), `measurement`, `report_data` (equal to `data`), `policy` (debug off, migration agent off, SMT only when `smt`), `vmpl` (0), `tcb` (each component of `REPORTED_TCB` at or above `tcb_floor`; the refusal names the component), `chip` (when `chip` is set). The crate fetches nothing.

Test vectors. A valid report cannot be made up: its chain must end at the real ARK. The vector is a report with its VCEK, ASK and ARK from a public source: the sample of the vendor, the test data of the `sev` crate (Apache-2.0), or a report recorded on a real SNP host with a report data of public values. It holds no secret. Its source and licence are stored beside it.

Acceptance of P-19 (U-attest of file 23 at the crate level):
* The vector passes `verify` with its own measurement, report data and chip.
* The vector with one bit flipped in the measurement, the report data, the policy debug bit, the VMPL, the reported TCB, the signature and a certificate of the chain fails, and the refusal names that field. The same report with another `data` (another nonce, another guest key) fails on `report_data`. A floor above the reported TCB fails on `tcb` with the component.
* `expected_measurement` of a fixed test guest set (an OVMF build, and a kernel, an initramfs and a command line hashed by `kernel-hashes=on`), stored with the tests or fetched by its id in CI, for 1, 2, 4 and 16 vCPUs equals golden values made by the `measurement` module of the `sev` crate. When the source of the vector names its guest set, the value for that set equals the measurement of the vector.
* The fuzz target of the report and certificate parsers runs in CI. The crate links static on x86_64 musl with no OpenSSL. The static probe builds on the 14 targets.
* Adoption trial: E-22 to E-24 of podswarm on a real SNP host, with the guest set of the release.

### 6.7 `pod-tty`: the terminal of the caller (ask P-11)

Cut from podssh `podssh-ssh` modules `terminal/` (raw mode, size, signals) and `escape.rs`. The parts that need `russh` (pty modes, `signal INT` on a channel) stay in podssh. The crate keeps two globals: the saved terminal state and the raw flag, because the panic hook and the console handler must reach them; its documentation names them.

```rust
pub struct Size { pub cols: u32, pub rows: u32, pub px_width: u32, pub px_height: u32 } // cells() -> pod_term::window::Size
pub fn is_terminal(s: Std) -> bool;                 // Std::{In, Out, Err}
pub fn size() -> Option<Size>;                      // the terminal of the process; None with no terminal
#[cfg(unix)] pub fn size_of_fd(fd: BorrowedFd<'_>) -> Option<Size>;
pub struct RawMode(());                             // one at a time; restores at drop and from a panic hook
impl RawMode { pub fn enter() -> io::Result<RawMode>; } // Unix: termios of stdin, cfmakeraw; Windows: input and output console modes with VT
pub fn raw_active() -> bool;
pub struct Watch;                                   // tokio: SIGWINCH (a 500 ms poll on Windows), SIGTERM, SIGHUP
impl Watch { pub fn new() -> io::Result<Watch>; pub async fn next(&mut self) -> Event; } // Resize(Size) | Terminate
pub mod escape;  // Escapes::new(ch).feed(&[u8]) -> (Vec<u8>, Vec<Command>): `~.`, `~?`, `~~` after a newline only
```
On `Event::Terminate` the caller ends and drops `RawMode`. On Windows the console handler restores the modes, then ends the process. A `SIGKILL` of the process that holds `RawMode` cannot restore: no code runs, and the documentation says so.

Acceptance of P-11: a test process on a pty that the test opens enters raw mode, then ends by each path (drop, a panic, `SIGTERM`, `SIGHUP`, and the end of a session whose command died by `SIGKILL`); after each, the termios bytes of the pty equal the bytes before. On Windows the console input and output modes after a drop and after a panic equal the modes before. A window change on the test pty gives one `Resize` with the new size. `escape`: `~.` after a newline gives `Disconnect`; `~.` inside a line passes as bytes; `~~` gives one `~`. The tests of podssh for these modules pass on the crate. The static probe builds on the 14 targets. Adoption trials: podssh; U-run-tty of podswarm.

### 6.8 `pod-ssh`: an SSH client library (ask P-13)

Cut from `podssh-ssh` (host key check, `known_hosts`, auth chain, exec channel) onto the `russh` of the workspace (`ring`), which `pod-devtunnel` runs over a stream. podssh reads `ssh_config`, the environment and the terminal; the crate takes each value from the caller.

```rust
pub struct HostPolicy { pub name: String,            // `host` or `[host]:port`
    pub files: Vec<PathBuf>,                          // known_hosts files of the caller, in order; `@revoked`, `@cert-authority`, patterns
    pub fingerprints: Vec<String>,                    // when not empty, the only keys taken; none recorded
    pub unknown: Box<dyn Fn(&HostKeyInfo) -> Accept + Send + Sync> } // Accept::{No, Once, Record}: Record appends to files[0]
pub enum Auth { Agent(AgentPath), KeyFile(PathBuf), KeyboardInteractive, Password }   // tried in this order, after `none`
pub trait Prompt: Send + Sync { fn ask(&self, text: &str, echo: bool) -> Option<Zeroizing<String>>; }
pub async fn connect(io: pod_core::BoxedIo, user: &str, host: &HostPolicy, auth: &[Auth],
                     prompt: Option<&dyn Prompt>) -> Result<Client, Failure>;
impl Client { pub async fn exec(&self, command: &str) -> Result<Exec, Failure>; }
impl Exec { pub fn split(self) -> (ExecIn, ExecOut, ExecOut, Ended); } // stdin (shutdown sends EOF), stdout, stderr
impl Ended { pub async fn wait(self) -> Result<End, Failure>; }       // End::Status(u32) | End::Signal { name: String, core: bool }
```
A changed or revoked key always fails, whatever `unknown` says.

Acceptance of P-13: an OpenSSH `sshd` that the test starts as the CI user on a loopback port, with keys made at test time, gives the rows of the subprocess road (U-conf-road of file 23): a 1 GiB stream through stdin and stdout keeps its BLAKE3 hash; a half close of stdin reaches the command; a kill of the command gives its exit signal; exit status 0, 7 and 255 pass through; stderr arrives on its own stream. A changed host key fails and names the key that the server showed. An unknown key calls `unknown`, and `No` ends the connection. The auth chain tries the agent, then the key file, then the prompt. The static probe builds on the 14 targets, the Windows targets included. Adoption trials: podssh; U-conf-road of podswarm.

### 6.9 Interfaces of the changes to existing crates

P-2, `pod-ws` module `serve` (feature `serve`). The numbers of podswarm are in file 16, section 14; the crate takes each as a value.

```rust
pub struct Deadlines { pub tls: Duration, pub head: Duration, pub ready: Duration, // from the accept
                       pub first: Duration }                                      // from the upgrade to the first frame
pub struct Caps { pub max_unauth: usize, pub per_prefix: usize,  // a prefix: /32 for IPv4, /64 for IPv6; loopback too
                  pub preauth_bytes: usize, pub head_bytes: usize, pub head_lines: usize }
pub struct Serve { pub deadlines: Deadlines, pub caps: Caps, pub lowat: Option<u32>, pub limits: pod_ws::Limits }
pub struct Accepted { pub session: RelaySession<TlsStream<TcpStream>>, pub peer: SocketAddr,
                      pub key: Option<pod_identity::PublicKey>, pub gate: PreAuth }   // key: pod_tls::peer::peer_key
impl PreAuth { pub fn ready(self); }  // the caller admitted the peer: its slot is free and its deadlines stop
pub async fn serve(listeners: Vec<tokio::net::TcpListener>, tls: Arc<rustls::ServerConfig>, cfg: Serve,
                   on: impl FnMut(Accepted) + Send) -> Result<(), Failure>;
```
A connection is pre-auth from the accept to `ready`. `preauth_bytes` counts the buffers of the loop and `limits.message` for each session before `ready`. When `max_unauth` or `preauth_bytes` is full, an accept evicts the connection in the earliest stage (TLS, head, first frame, ready), the oldest within it; when nothing can be evicted the accept is closed. An accept over `per_prefix` is closed. A deadline that passes, or a `PreAuth` dropped with no `ready`, cuts the connection. Each accepted socket gets `TCP_NODELAY`, and `TCP_NOTSENT_LOWAT` of `lowat` where the system has it.

P-4, `pod-link`. Optional: a class number for each stream (lower first, equal classes in turn), which serves the classes of file 04, section 7.2; the minimum is one first stream.

```rust
impl Link { pub fn open_first(&self) -> Result<Stream, Error>;  // its frames go before the DATA of each other stream
            pub fn set_windows(&self, stream_window: u32, link_window: u32) -> Result<(), Error>; } // the ranges of Settings::check
```

P-5, `pod-hostprobe`. The cache file is a path of the caller.

```rust
pub fn report(f: &Findings) -> serde_json::Value;     // validates against the schema in `schemas/` of podcrates
pub fn capabilities(f: &Findings) -> Vec<Capability>; // name, yes | no | unknown, and the rows that decide it
pub struct CacheKey { pub kernel_release: String,     // uname(2) release
                      pub boot_id: String,            // /proc/sys/kernel/random/boot_id
                      pub probe_binary: [u8; 32] }    // BLAKE3 of the file that the probe children run (/proc/self/exe)
pub fn run_cached(s: &Settings, candidates: &[(String, String)], cache: &Path) -> Findings;
```

P-6, the probe of each new row. Each row runs in a probe child, as the rows of `PROBES` do, or reads a file.

| Row | Probe |
| --- | --- |
| user plus PID namespace in one clone | `clone(CLONE_NEWUSER \| CLONE_NEWPID)` in a child |
| cgroup2 delegation | `cgroup.subtree_control` of the own cgroup (`/proc/self/cgroup`) opens for write |
| FUSE mount in a user namespace | in new user and mount namespaces, `open(/dev/fuse)` and `mount("fuse", fd=N)` |
| notification with `CONTINUE` | a filter with a listener; a notified `getppid` answered with `SECCOMP_USER_NOTIF_FLAG_CONTINUE` returns |
| `PTRACE_SEIZE` of a descendant | the probe child seizes its own child, then detaches |
| `memfd_secret` | `memfd_secret(0)` gives a descriptor |
| `ramfs` in a user namespace | `mount("ramfs")` in new user and mount namespaces |
| `memory.swap.max` | the file of the own cgroup opens for write |
| swap state | `/proc/swaps` lists a device; `/sys/module/zswap/parameters/enabled` is `Y` |
| `qemu` of each guest architecture | `qemu-system-ARCH --version` of each candidate, as the x86_64 row |
| SNP | `/sys/module/kvm_amd/parameters/sev_snp` is `Y` and `/dev/sev` opens |
| TDX | `/sys/module/kvm_intel/parameters/tdx` is `Y` |
| `hidepid` | the `hidepid=` option of `/proc` in `/proc/self/mountinfo` |
| other root users | the count of uid 0 accounts in `/etc/passwd` and of the members of `sudo` and `wheel` in `/etc/group` (file 13, section 9) |

P-18, `pod-guest`. The Linux flavour sits beside `plan::argv` (UEFI) and `dos::argv`, and keeps `-nic none`, QMP and `emu_args`.

```rust
pub mod linux;   // linux::argv(p: &linux::Plan) -> Vec<String>
pub struct Plan { pub emulator: PathBuf, pub accel: Accel, pub share: PathBuf, pub cpus: u32, pub memory_mib: u64,
                  pub kernel: PathBuf, pub initrd: PathBuf, pub append: String, // the fixed command line of the guest set
                  pub run_dir: PathBuf,  // mode 0700: the chardev socket, the scratch disk, the QMP socket
                  pub mem_lock: bool, pub snp: Option<Snp>, pub emu_args: Vec<String> }
pub struct Snp { pub cbitpos: u8, pub ovmf: PathBuf }   // policy=0x30000, reduced-phys-bits=1, kernel-hashes=on
```
With `emu_args` empty, the argv may name a host path only from this set: the emulator binary and its share directory (`-L`), the files of the guest set (kernel, initramfs, OVMF), and paths under the per-run directory of mode 0700 (the `chardev` socket, the scratch disk, the QMP socket). `-append` is the fixed command line of the guest set. No argv element holds a file name, file content, argv value or environment value of the run, or a name of the caller's tree.

## 7. Asks

Each ask has a fallback in the podswarm repository, so no ask blocks a milestone. An ask goes to the target as an issue in the form of podcrates: `Target:` (column Target), Problem (column Problem and use case), Change (column Change), Interface (the code of section 6 for a crate, else the item that column Change names), Acceptance, Use case (the file that column Problem names), References (column Refs). A crate name goes as a comment on podcrates#1. Ids: P for podcrates, V for podvm, N for podnet. An id is never reused.

| Id | Target | Change | Problem and use case | Acceptance | Fallback | Milestone | Refs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P-1 | podcrates | new crate `pod-proc` (6.1); move `launcher/tree.rs` out of `pod-supervise`, whose `end::Residual` gives way to `pod_job::Residual` (the same wire form), and `limits` out of `pod-enter` | one tree kill for podvm, podrunner and podswarm | the list of 6.1: F-19 and F-20 of file 23 in the crate, the four takeover cases, adoption trials of podvm and podrunner | `podswarm-exec/src/proc/` | M0 | T-162 (done, the base) |
| P-2 | podcrates | `pod-ws` module `serve` (feature `serve`, 6.9): accept loop over caller-bound listeners, stage deadlines, caps per address, `TCP_NODELAY` and `TCP_NOTSENT_LOWAT` on each socket | coordinator and hub need a listener | 1,000 upgrades from the loopback, at most 64 pre-auth at one time, each marked `ready`, all reach the caller; a client that stalls in TLS, in the head or before its first frame is cut at the deadline of that stage; with 64 pre-auth from 127.0.0.1 the next accept from it is closed and one from 127.0.0.2 is taken; with `max_unauth` full an accept evicts the oldest of the earliest stage; `getsockopt` reads `TCP_NODELAY` and `TCP_NOTSENT_LOWAT`; a plant that skips a deadline fails | `podswarm-net/src/accept.rs` | M4 | T-036, T-120, podcrates#82 |
| P-3 | podcrates | `pod-tls`: an enrolment mode of the client verifier of `peer` that admits a client of any Ed25519 key with a valid handshake signature, so that `peer_key` reports it and the caller checks an invite. The server key is Ed25519. TLS 1.3 only, no tickets, a live key set and the report of the key exist in `peer` | identity in the handshake (file 16) | a client of a key outside `Keys` passes in the enrolment mode and its key is reported; it fails in the pinned mode | a rustls verifier in `podswarm-net` | M4 | T-304, podcrates#88 |
| P-4 | podcrates | `pod-link`: a write priority for one stream; a change of the window caps on a live link (6.9) | control frames must not wait behind bulk data on a slow road (file 04) | `frame_size` 4 KiB, a carrier shaped to 1 Mbit/s, one bulk stream that always has credit and data: between the write of a 64-byte message on the first stream and its frame, the carrier carries at most 4 KiB of bulk `DATA` plus frame headers; after `set_windows` lowers `stream_window` from 1 MiB to 64 KiB, the unread bytes of a stream that is not read stay at most 64 KiB once the credit granted before the call is used; after a raise, the stream reaches the new window; a value that `Settings::check` refuses returns an error and keeps the old values; the same `Link` and streams throughout | a fairness test; settings computed at each link start | M1 | T-300, podcrates#88 |
| P-5 | podcrates | `pod-hostprobe`: the JSON report with a schema, a map from findings to capabilities, a cache across runs keyed by the kernel release, the boot id and the BLAKE3 id of the probe binary (6.9) | worker `caps` and `doctor` | the report validates against the schema; a second start with the same key reads the cache and starts no probe child; a change of each part of the key runs the probes again; a cache file that does not parse is ignored and written again | a local map and cache in `podswarm-worker` | M1 | T-107, podcrates#82, podvm#239 |
| P-6 | podcrates | `pod-hostprobe` rows that `PROBES` lacks: user plus PID namespace in one clone, cgroup2 delegation, FUSE mount in a user namespace, notification with `CONTINUE`, `PTRACE_SEIZE` of a descendant, `memfd_secret`, `ramfs` in a user namespace, `memory.swap.max`, swap state, the `qemu` version of each guest architecture, SNP, TDX, `hidepid`, other root users; the probe of each row is in 6.9. The rows `clone(CLONE_NEWUSER)`, `unshare(CLONE_NEWPID)`, `open(/dev/fuse, O_RDWR)`, `seccomp(NEW_LISTENER)`, `ptrace(PTRACE_TRACEME)` and `qemu-system-x86_64 --version` exist | the probe of files 06, 07, 12, 13 | one test per row with a fake result and a real run on the CI kernel; a row that cannot run gives `Skip`, never "denied" | a probe module in `podswarm-worker` | M1; spread row M3; guest rows M8 | T-107 |
| P-8 | podcrates | `pod-job`: `LimitMode::Polled` | the keeper polls memory, CPU and disk (file 12) | serde round trip of `polled`; schema updated | a podswarm enum that maps to `reported` on the wire of podrunner | M0 | |
| P-9 | podcrates | `pod-core`: `Stage::Task` | worker errors with a stage of their own | consumers updated in the same release (the enum is exhaustive) | `Stage::Host` | M0 | |
| P-10 | podcrates | `pod-proxy`: `ChildIo::spawn_args(program, args)` with no shell, stderr as a pipe, a `wait` future. `ChildIo::spawn(command)` (through `sh -c`, stderr inherited) and `exited` exist | the `ssh` and `exec:` roads | a road test reads stderr and the exit status | `tokio::process` in `podswarm-net` | M1 | |
| P-11 | podcrates | new crate `pod-tty` (6.7): the local terminal guard cut from podssh `terminal/` and `escape.rs` | raw mode and restore of the caller's terminal on Unix and Windows | the list of 6.7: termios bytes equal after drop, panic, `SIGTERM`, `SIGHUP` and a command killed by `SIGKILL`; Windows console modes equal; one resize event; the escape parser | `podswarm-cli/src/tty/` | M1 | podcrates#1 |
| P-12 | podcrates | new crate `pod-cas` (6.2) | one content store for view, data and checkpoints | a cut write resumes at its offset; bytes that do not match their id are refused; the sweep keeps a blob under the age guard | `podswarm-store/src/cas/` | M6 | podcrates#1 |
| P-13 | podcrates | new crate `pod-ssh` (6.8) cut from `podssh-ssh`, on the `russh` of the workspace that `pod-devtunnel` already runs over a stream (host key check, `direct-tcpip`): host key policy, auth chain, exec channel with status | no system `ssh` needed, above all on Windows callers | the list of 6.8: the rows of U-conf-road against a local `sshd`, the host key cases, the order of the auth chain | the system `ssh` as a subprocess | M10 | podcrates#1 |
| P-14 | podcrates | `pod-hold`: `Program` carries a `PreExec` plan to apply before exec (6.5) | the hold and the keeper share one fork (file 14) | a held child sees each step of the plan before `execve`; a failed step is named and no exec runs (6.5) | the shim of file 14 | M7 | |
| P-15 | podcrates | `pod-hold` growth (6.5) | `trap` rung and exec rung `seccomp` | the list of 6.5: the marker, `enosys`, `filter::install` in a single-thread child, `read_cstr` and `read_argv`; the four takeover cases belong to P-1 | `podswarm-exec/src/trap/` | M2; M3 | |
| P-16 | podcrates | new crate `pod-fuse` (6.3) | the live view | the list of 6.3: a socket-pair test per write opcode, a real mount where `/dev/fuse` opens, `pod-enter` tests unchanged | `podswarm-view/src/fuse/` | M1 | podcrates#1 |
| P-17 | podcrates | new crate `pod-view` (6.4) | a view for other projects | the list of 6.4: loopback tests of the crate parts of F-40 to F-47 and the `conformance` suite against a rung of the tests and a planted bad rung | `podswarm-view` | after M2 | podcrates#1 |
| P-18 | podcrates | `pod-guest`: a Linux flavour of `plan::argv` beside the UEFI flavour that exists (which already has `-nic none` and `emu_args`), with one virtio-serial `chardev` socket, one raw scratch disk, `-overcommit mem-lock=on`; an SNP variant (`sev-snp-guest`, `kernel-hashes=on`) | shield `guest` and `sealed` (file 13) | golden tests of the argv with and without `mem_lock` and of the SNP variant; each path of the argv is in the set of 6.9; a canary in a file name, a file body, an argv element and a variable of the run is absent from the argv; no `-fsdev`, `-virtfs`, `virtiofs` or `-netdev`; UEFI and DOS golden tests unchanged | QEMU argv built in `podswarm-exec` | M8 | |
| P-19 | podcrates | new crate `pod-attest` (6.6) | shield `sealed` | the list of 6.6: a public test vector passes, each flipped field fails by name, the golden measurements | `podswarm-exec/src/attest/` | M8 | podcrates#1 |
| P-20 | podcrates | `pod-enter` `fuse.rs`: the module text says that `mount(2)` of FUSE fails in a user namespace; it is allowed since Linux 4.18 when `/dev/fuse` opens | a wrong fact in a crate document | the text names the condition | none needed | none | an entry of podcrates |
| P-21 | podcrates | reserve the names `pod-proc`, `pod-cas`, `pod-fuse`, `pod-view`, `pod-tty`, `pod-ssh`, `pod-attest` | the owner reserves each name | the check is part of the ask: each name answers 404 on crates.io before its reservation, then is reserved; a taken name gets another name from the owner | the code stays in `podswarm-*` | M0 | podcrates#1 |
| V-1 | podvm | a library call for `run` with a typed request and the `--report` record | no parse of a CLI whose flags change | a test starts `true` through the call and reads the report | spawn the CLI | M8 | |
| V-2 | podvm | read the probe cache in `run` | the probe costs each `run` | with a warm cache, the median of 10 runs of `run --rm IMAGE true` is lower than the median with no cache by at least 80 percent of the median of 10 runs of `probe --json` | none; the cost stays | M8 | |
| V-3 | podvm | cgroup2 limits where delegated, refused by name elsewhere | `memory.max` for `sandbox` and `vm` | a run over its limit ends with a named reason | limits stay `polled` (file 12) | M8 | |
| V-4 | podvm | a foreground payload dies with podvm | a worker that kills podvm on a timeout leaves no payload | `SIGKILL` of `podvm` leaves no process | the keeper kills the tree | M8 | |
| V-5 | podvm | a read-only root with a tmpfs upper layer | `run` copies the image today | a second run starts with no copy | accept the copy | M8 | |
| V-6 | podvm | a warm `exec` into a booted machine guest | a warm sandbox per slot (file 24) | `exec` into a running guest returns the exit code | boot per attempt | M8 | |
| V-7 | podvm | boot the guest plan of shield `guest`: no host file in the guest, no NIC, one `chardev` socket, one raw scratch disk, `mem-lock` | shield `guest` (file 13) | a run with a canary in a file name, a file body, an argv element and a variable: as root, no canary in the argv and environment of host processes, in the per-run directory or in the state of podvm; the run data reach the guest through the `chardev` socket only; `ip link` in the guest shows `lo` only. Adoption trial: E-19 to E-21 of podswarm | P-18 argv with QEMU run by podswarm | M8 | |
| V-8 | podvm | versioned schemas for `--report` and `probe --json` | podswarm reads both | schema files in the release | parse with a version check | M8 | T-1714, podvm#239, podcrates#82 |
| N-1 | podnet | add and remove a door and a network while the router runs, with counters per door | a policy per attempt (file 14) | a door added and removed with no restart | a new router per change of the door set | M7 | |
| N-2 | podnet | rules by port, also on the loopback | `home=PORTS` | `tcp:127.0.0.1:5432=home` routes | the hold of podswarm maps the ports | M7 | |
| N-3 | podnet | `podnet exit --stdio`: SOCKS5 with UDP ASSOCIATE on stdio | an exit member over any road | a UDP send through the exit | `psw net-exit` | M7 | podnet#466, podnet#471 |
| N-4 | podnet | a decision on the aggregation of one flow | the default "aggregated" of the owner | a plan, or "per flow only" in the documents; either answer closes the ask | the report says `aggregation: per_flow` | M7 | podnet#495 |
| N-5 | podnet | a JSON report of `podnet pod` and its exit status equal to the command's | the run report | the report validates; the status passes through | parse the stderr line; status from the shim | M7 | |

## 8. Asks that are not made

| Not asked | Reason |
| --- | --- |
| P-7, the key of the peer of an accepted `wss` session | present in the pin: `pod_tls::peer::peer_key` reads it from the TLS connection before `pod_ws::server::session` |
| `pod-task` (task records) | no second consumer; the types stay in `podswarm-proto` |
| `pod-listen` | it is glue over `pod-ws`, `pod-proxy` and `pod-tls`; P-2 puts the loop in `pod-ws` |
| a pinned TLS client with no client certificate | the `wss` road uses mutual TLS with a client key (file 16); P-3 covers the server side |
| changes to `pod-session` | the link has its own reattach (file 04); `pod-session` adds a second heartbeat and handshake |
| `pod-job` arch values | podswarm reports its own `caps` |
| `pod-supervise` ephemeral mode | the keeper of `pod-proc` replaces a launcher per attempt |
| `pod-enter` host-command path | the keeper applies limits with `pod_hostprobe::sys::set_rlimit` |
| a separate `pod-pty` | the terminal of an attempt is part of `pod-proc` |
| `pod-trap` | the trap is a growth of `pod-hold` and the takeover is a module of `pod-proc` (6.5, D-120) |
| a move of clock, journal or audit code out of podrunner | podswarm writes its own; the code is small and the shapes differ |
| a CRIU crate | CRIU is GPL-2.0; a later migration rung runs it as a separate helper (file 07) |
| asks to stub repositories (`podnode`, `podinit`, `pods`, `podkey`, `podlog`, `podstat`, `podrepl`, `podsnap`, `podinfo`) | they hold no code; file 22 lists them with no milestone |
| a hub address in `pod-services` | third-party data only belongs there |

## 9. Traits with conformance suites

Each seam is a trait with one conformance suite in the crate that defines it. Each suite runs against every implementation and against one planted bad implementation, which must fail it (file 23). An adapter that speaks the plugin lines of file 17 implements the trait for a plugin.

```rust
// podswarm-net; full form in file 04
pub trait Road: Send + Sync {
    fn scheme(&self) -> &'static str;
    fn facts(&self) -> RoadFacts;
    fn open<'a>(&'a self, want: &'a Want) -> BoxFuture<'a, Result<Opened, RoadError>>;
}
// podswarm-view; rules in file 06
pub trait ViewRung: Send {
    fn probe(&self, host: &Probe) -> Result<RungFacts, Refusal>;          // fuse, fuse-userns, trap, sync
    fn prepare(&mut self, ws: &Workspace, epoch: u64) -> Result<Prepared, Failure>;  // namespace fds or a replica
    fn after(&mut self, attempt: AttemptId) -> Result<WriteBack, Failure>;          // ops for the home
}
// podswarm-exec; rules in files 12 and 13
pub trait Executor: Send + Sync {
    fn boundary(&self) -> Boundary;
    fn caps(&self) -> ExecCaps;                       // rung, limit modes, shield rows
    fn start(&self, a: &AttemptPlan) -> Result<AttemptId, SpawnFailed>;
    fn signal(&self, id: AttemptId, how: How) -> Result<(), Failure>;
    fn next_event(&mut self) -> Option<ExecEvent>;    // Running | Ended(ExitReport)
}
// podswarm-store; commands and levels in file 11
pub trait Store: Send {
    fn apply(&mut self, cmds: Vec<StoreCmd>) -> Result<Vec<StoreAck>, StoreError>;
    fn load(&self, sink: &mut dyn FnMut(Loaded)) -> Result<(), StoreError>;
    fn reader(&self) -> Box<dyn StoreRead>;
}
// podswarm-worker; rules in file 15
pub trait Checkpointer: Send {
    fn save(&mut self, task: TaskId, seq: u32, dir: &Path) -> Result<Saved, CkptError>;   // manifest id
    fn restore(&mut self, saved: &Saved, dir: &Path) -> Result<(), CkptError>;
}
// podswarm-core; rules in files 08 and 10
pub trait Placement {
    fn candidates(&self, need: &Needs, pool: &[MachineView]) -> Vec<MachineId>;   // filter
    fn score(&self, need: &Needs, m: &MachineView, learned: &Learned) -> Estimate;  // lowest wins
}
```

The admission policy is a seam of file 17. The conformance suites, their ids and the plants are in file 23.
