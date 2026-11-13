# 4. Roads and links

This file defines how the caller's machine reaches another machine, starts podswarm there with nothing installed, and gets a link on which attempts run. It defines the roads, the bootstrap of the binary, the link, control framing, `hello` and `ready`, the rules of one link, reattach after a cut, the holder, and what stays on a far machine. File 05 defines the messages after `ready`, the fence and reconciliation. File 08 defines the pool file and placement. File 13 defines what a shield level changes on the far side. File 19 defines the directories `C`, `S`, `K` and `R`. File 16 defines keys, invites, pins and the pre-auth limits.

## 1. Roads

A **road** gives one ordered, reliable byte stream from the home or a submitter to a podswarm process on a far machine. Most roads can also start that process. The worker code is the same on every road: only the road changes.

| Kind | URL form | Caller needs | Far end needs | Authenticates | Milestone (file 22) |
| --- | --- | --- | --- | --- | --- |
| `ssh` | `HOST`, `[user@]host`, `ssh://[user@]host[:port][?jump=J]` | an OpenSSH or Dropbear client | sshd, `sh`, `uname`, `cat`, `mkdir`, `chmod`, `mv`, `cp`, `rm` | itself (ssh) | M1 |
| `local` | `local` | nothing | nothing: a worker in the caller's process | itself (one process) | M0 |
| `podssh` | `podssh://name` | the `podssh` binary | as `ssh`, or a podssh node | itself (ssh) | M2 |
| `exec` | `exec:CMD ARGS` | the command, for example `docker exec -i C`, `kubectl exec -i POD --`, `incus exec C --`, `wsl`, `adb shell` | `sh` and the tools of `ssh`, or `--remote-exe` | itself (the user's own command) | M2 |
| `wss` | `wss://host[:port]` | TCP out, optional proxy | a coordinator that listens | mutual TLS (section 5.4) | M4 |
| reverse | `relay://NAME` | the operator file of a `pod-relay` pair | a long-lived `podswarm worker` node that dials a relay | the `pod-relay` pair | later (file 24) |

`HOST` alone means `ssh://HOST`. A pool entry (file 08) names a road in its `road` key. Two internal roads use the carriers of `pod-link`: `unix:PATH` (the socket of the holder, section 12, and the local socket of a coordinator) and `mem:NAME` (tests).

A road that authenticates both ends by itself (`ssh`, `podssh`, `exec`, `local`) carries no TLS and no podswarm key exchange. The user who can open the road owns the far worker for the session. The one exception is shield `guest` and `sealed`: an inner TLS channel ends inside the guest (file 13). A `wss` road carries the mutual TLS identity of section 5.4. This avoids two layers of encryption on small CPUs in the common case.

## 2. The `Road` trait

The trait lives in `podswarm-net`. It is not a `pod_link::Carrier`: a carrier gives bytes to an address and has no start step, no exit status, no diagnostics and no fact about authentication. `CarrierRoad` wraps a carrier (`unix`, `mem`). `ExecRoad` runs a subprocess (`ssh`, `podssh`, `dbclient`, `exec`). `DialRoad` dials with `pod_core::Dial` (`wss`). `RelayRoad` is behind the cargo feature `relay`.

```rust
pub trait Road: Send + Sync {
    fn scheme(&self) -> &'static str;          // "ssh" "podssh" "exec" "local" "wss" "relay" "unix" "mem"
    fn facts(&self) -> RoadFacts;              // known before any connect
    /// One ordered byte stream to a podswarm process on the far machine.
    /// Starts the process when `facts().can_start`. The preface (section 4.4) is already read.
    fn open<'a>(&'a self, want: &'a Want) -> BoxFuture<'a, Result<Opened, RoadError>>;
}
pub struct RoadFacts {
    pub auth: RoadAuth,           // Road { principal } | Tls (podswarm runs the TLS of section 5.4)
    pub can_start: bool,          // false: wss, relay (the process already runs)
    pub shared_connection: bool,  // an ssh master: a new session is cheap
    pub sessions_max: u8,         // sessions on one connection (section 4.5)
}
pub enum Start { Probe, Install { bin: BinSource }, Worker { sid: Sid }, Attach { sid: Sid } }
pub struct Want { pub start: Start, pub nonce: [u8; 16], pub deadline: Instant }
pub struct Opened {
    pub io: pod_link::BoxIo,      // the stream after the preface
    pub diag: DiagRing,           // the last 8 KiB of the road's stderr and of the bytes before the preface
    pub ended: ExitWatch,         // resolves with the exit status of the child
}
```

The principal of a self-authenticating road is a string: `ssh:user@host:port` (the values that `ssh -G` prints), `exec:<command line>`, `local`. The run record carries it as `road_principal` (file 17).

## 3. Identity on a link

* `ssh`, `podssh`, `exec`, `local`: the far worker accepts exactly one controller: the party at the other end of its stdin and stdout, or a later party that attaches through the private socket of section 11 with the same `sid`. `hello` has no `enrol`. `ready` gives the `wid` that the home chose.
* `wss`: each worker, each submitter and the coordinator presents its Ed25519 `pod-identity` key as a self-signed certificate in the TLS 1.3 handshake, and both ends use `pod_tls::peer` (D-129). The client checks the coordinator key against its pin set. The coordinator accepts any client key whose handshake signature is valid and maps the key to a worker or a submitter row after the handshake. There is no in-band nonce and no in-band signature, so the identity is bound to the TLS session itself. A pin is the `SHA256:` fingerprint of the key. Keys, invites, enrolment and pins: file 16.
* The shield (file 13) decides what the far side keeps, seals or refuses. A road gives the identity, not the shield.

## 4. The ssh road

### 4.1 The command line

Every session on an OpenSSH client uses this command line. The order of the options is fixed. A command line option of OpenSSH wins over the user's configuration, and the user's host key checks stay as the user set them.

```
ssh -T -a -x -e none
    -o BatchMode=yes
    -o ForwardAgent=no -o ForwardX11=no -o ClearAllForwardings=yes -o SendEnv=-*
    -o PermitLocalCommand=no -o RemoteCommand=none -o RequestTTY=no
    -o LogLevel=ERROR -o Compression=no -o ConnectTimeout=10
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3
    -o ControlMaster=auto -o ControlPath=CDIR/%C -o ControlPersist=60
    [-p PORT] [-J JUMP] [SSH_ARGS...]
    -- [user@]host COMMAND
```

| Option | Reason |
| --- | --- |
| `-T`, `RequestTTY=no` | No pty on the road. A pty of an attempt is made by the worker (file 05), not by ssh. |
| `-e none` | No escape character. podswarm has its own escape (file 18). |
| `-a -x`, `ForwardAgent=no`, `ForwardX11=no`, `ClearAllForwardings=yes`, `SendEnv=-*` | A user `Host *` block cannot add a forward or send a variable. No flag turns agent forwarding on (file 13, D-75). |
| `PermitLocalCommand=no`, `RemoteCommand=none` | A user configuration cannot run a command that writes into the stream. |
| `BatchMode=yes` | No prompt on a session that the holder opens. The holder has no terminal. |
| `LogLevel=ERROR` | ssh writes no notice into stderr, so stderr stays a log channel. |
| `Compression=no` | The link has its own zstd codec (section 8). |
| `ServerAliveInterval=15`, `ServerAliveCountMax=3` | ssh ends a dead connection after 45 s, and the link sees end of file. |
| `ControlMaster=auto`, `ControlPersist=60` | All sessions to one host share one connection. |

* `CDIR` is the first of `$XDG_RUNTIME_DIR/podswarm/s` and `/tmp/podswarm-<uid>/s` whose full socket path (`CDIR` plus 41 bytes) has at most 100 bytes. A socket path has a limit of about 104 bytes. `CDIR` is mode 0700. The home refuses a `CDIR` that is a symbolic link or that another uid owns.
* `SSH_ARGS` comes from `--ssh-args` and from the pool key `ssh_args` (file 08). podswarm refuses there `-t`, `-N`, `-f`, `-A`, `-X`, `-Y`, `-L`, `-R`, `-D`, `-W`, `-M`, `-S`, and an `-o` of `RequestTTY`, `RemoteCommand`, `LocalCommand`, `PermitLocalCommand`, `ForwardAgent`, `ForwardX11`, `ClearAllForwardings`, `SendEnv`, `SetEnv`, `ControlMaster`, `ControlPath`, `EscapeChar`. Exit 64.
* `?jump=J` and the pool key `jump` give `-J J`. Any podssh road reaches an OpenSSH client as `-o ProxyCommand='podssh proxy %h %p'` in `ssh_args`.
* podswarm never sets `StrictHostKeyChecking`. `podswarm doctor HOST` warns when `ssh -G HOST` prints `stricthostkeychecking false`.

### 4.2 The first connection to a host

The first connection to a host is the only one that may ask the user something: a passphrase, a second factor, a touch of a security key, or a new host key. The foreground command does it, because it has the terminal:

1. `ssh <flags> -O check -- HOST` with the flags of 4.1. Exit 0: a master runs; go to the holder.
2. Else, when stdin and stderr of the command are a terminal and `--batch` is not given: `ssh <flags> -o BatchMode=no -M -N -f -- HOST`. ssh asks its questions on the terminal, authenticates, and goes to the background as the master.
3. Else: no master starts here. The holder opens sessions with `BatchMode=yes`, and the first one becomes the master. A key that needs a prompt fails with the ssh message from the diagnostics ring and exit 69.

### 4.3 The far command

The far side runs `COMMAND` through the user's login shell (`$SHELL -c`). That shell can be `sh`, `bash`, `csh`, `fish` or `nu`. So `COMMAND` is always one form: `sh -c 'SCRIPT' WORD...`, where `SCRIPT` is one line with no single quote, no `!` and no newline, and each `WORD` holds only `[A-Za-z0-9._/:=-]`. The first `WORD` is `$0` of the script. Every shell passes this form unchanged to `sh`. On an `exec` road the same words are separate argv elements and no login shell runs.

### 4.4 The preface

A shell start file (`.bashrc`, `/etc/profile`, a banner) can print to stdout before the worker starts. So the stream starts with a preface that such text cannot match:

```
far to home:   50 53 57 52 4F 41 44 01   NONCE (16 bytes)      "PSWROAD", road version 1, then the nonce
home to far:   50 53 57 52 4F 41 44 01   NONCE (16 bytes)      the same 24 bytes, sent after the home read them
then each end: 50 4F 44 4C 49 4E 4B 01                         the preface of pod-link ("PODLINK", 1)
```

* The home makes a new random `NONCE` for each open of a road and puts it in the command line as `--nonce <32 lowercase hex>`.
* The home reads stdout and discards every byte before the 24 bytes of the far preface, at most 64 KiB. It keeps them in the diagnostics ring. More than 64 KiB, or end of file first, fails the open.
* The home writes nothing to the far stdin before it read the far preface, so a start file that reads stdin gets no byte of the link.
* The worker writes its preface only after it set up its run directory and its spawner. A preface means that the worker runs.
* The worker moves its stream to a private descriptor and points descriptor 1 at `/dev/null`, so a stray print of the worker cannot enter the stream.

### 4.5 Sessions on one connection

* sshd allows `MaxSessions` sessions on one connection (default 10). The home opens at most `ssh.max_sessions` sessions on one master at one time (default 4, range 1 to 10): the link, one probe or install, one attach, one spare. [EV-008]
* A link uses one session. `pod-link` carries every stream of the link in it (section 7).
* A refused session ("administratively prohibited", or a refused channel open) makes the home open that session on its own connection (`-o ControlPath=none`) and mark the host `single_session` in the holder. Dropbear servers and `MaxSessions 1` take this path.

### 4.6 stderr and exit status

* stderr of the ssh child carries both the far stderr and the messages of ssh. The home reads it into the diagnostics ring of 8 KiB. It prints the ring on a failure of the road and with `-v`. The worker writes its log lines to its stderr, so the log of a far worker reaches the home with no file on the far host (file 13).
* Exit status 255 with no far preface read is a failure of the road: exit 69, and the ring. Status 255 after the preface is the status of the worker.
* The worker exits 0 after a `bye` and after the end of its life (section 13). Other codes are the codes of file 19.

### 4.7 Other clients and servers

| Case | Rule |
| --- | --- |
| Dropbear client `dbclient` (detected by `ssh -V`, cached by path and mtime) | `dbclient -T -K 15 -W 1048576 [-p PORT] [-i KEY] [-J 'CMD'] HOST COMMAND`. No connection sharing: one session is one connection. `-J` of `dbclient` is a proxy command, not a jump host. Never `-y`. Default channel window 24,576 bytes, so `-W` is always given. [EV-009] |
| Dropbear server, busybox host | One session per connection may apply (4.5). The far side has `ash` and the busybox applets. The bootstrap uses only `uname`, `cat`, `mkdir`, `chmod`, `mv`, `cp`, `rm`, and `gzip` when present. |
| Windows OpenSSH client | No `ControlMaster`: no control options, one connection per session. |
| Windows far host | Later. Its default shell is `cmd.exe`, with no `sh` and no `cat`. The probe sees `uname` fail and reports `windows`. |
| macOS far host | The binary is signed ad hoc at build. A file that arrives over ssh carries no quarantine attribute. |
| Bastion | `-J` (OpenSSH), or `ProxyCommand` in `ssh_args`. |
| Dial-out proxy for the road | `-o ProxyCommand=...` in `ssh_args`: `podssh proxy %h %p`, `nc -X 5 -x HOST:PORT %h %p`. |

## 5. Other roads

### 5.1 `podssh`
`podssh://name` runs `podssh ssh` with the flags of 4.1. `podssh ssh` takes the options of OpenSSH, keeps stdout byte for byte, writes its own messages to stderr, and exits with the far status or 255. podssh resolves `name` by its own configuration (relay, direct, node). Every other rule of section 4 applies.

### 5.2 `exec`
`exec:CMD ARGS` runs a command whose stdin and stdout reach the far side. The home appends the far argv of section 4.3 as separate words, or puts it at the token `{remote}`. The plugin contract (environment, `{remote}`, logging) is in file 17. The preface, the bootstrap and reattach are as on `ssh`. A far side with no `sh` needs `--remote-exe PATH` (section 6.5).

### 5.3 `local`
The worker runs in the caller's process. The link is in memory: typed messages over channels, no codec, no TLS, no preface (file 03). The caller's machine is a candidate of placement like any other (file 08).

### 5.4 `wss`
The stack, bottom up:

| Layer | Rule |
| --- | --- |
| TCP | `TCP_NODELAY`; `TCP_NOTSENT_LOWAT` 16 KiB, so a control frame waits behind at most 16 KiB in the kernel; `TCP_USER_TIMEOUT` of `2 * hb_s`. The dialler sets them with `pod_proxy::Dialer` (`lowat: Some(16384)`); the coordinator sets them on each accepted socket. |
| Proxy | `pod-proxy`: `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, SOCKS5, HTTP CONNECT, and the `exec` proxy forms of `pod-proxy`. |
| Names | `pod-dns`. On a host with no `/etc/resolv.conf` (Android) the worker skips the system resolver, reads `$PREFIX/etc/resolv.conf` when it exists, else uses DNS over HTTPS. An invite token carries the coordinator addresses beside its name (file 16). |
| TLS | TLS 1.3 only, mutual (section 3), no tickets, no resumption, no 0-RTT. Cipher order: see section 7.3. |
| WebSocket | `pod-ws` through `dial_asking` with `Asking { alpn: none, limits }`; subprotocol `podswarm.1`; no WebSocket extension. Each binary message carries bytes of the link, at most 1 MiB plus 8 bytes. |
| Path | `/v1/w` worker, `/v1/s` submitter, `/v1/h` hub link. |
| Link | `pod-link` over the WebSocket (section 7). No road preface: the WebSocket upgrade does that work. |

A submitter or an admin on the coordinator machine uses the local socket `$XDG_RUNTIME_DIR/podswarm/coord.sock` (mode 0600, peer uid checked, no TLS): `pod-link` over the `unix` carrier of `pod-link`. The pre-auth limits of a listener are in file 16.

### 5.5 Reverse roads (later)
A machine that can only dial out runs `podswarm worker --node NAME --pair FILE`, which embeds `pod_relay::reverse::run` with a channel handler and no local port. The caller opens `relay://NAME`. The worker code is the code of `--stdio`. This gives a session (no coordinator) a machine that nobody can dial. Until then such a machine joins a coordinator (section 14).

## 6. Bootstrap of the binary

### 6.1 Places on the far machine

| Item | Path | Mode |
| --- | --- | --- |
| Binary cache `B` | `${XDG_CACHE_HOME:-$HOME/.cache}/podswarm/bin` | directory 0700 |
| A binary | `B/podswarm-<version>-<hash16>`; `hash16` is the first 16 hex of the SHA-256 of the file | 0500 |
| Run directory `R` of a worker | `$XDG_RUNTIME_DIR/podswarm/w-<sid>` when `XDG_RUNTIME_DIR` is set and writable, else `${TMPDIR:-/tmp}/podswarm-<uid>/w-<sid>` | 0700 |
| In `R` | `attach.sock` (section 11), `lock` (an `flock` while the worker lives), the worker state of file 12, the journal | 0600 |
| Content cache | file 06 and file 15 (sealed or absent by the shield, file 13) | |

`sid` is 16 random bytes in lowercase hex, made by the home for each far worker. The worker checks `R` and each parent it made with `lstat`: owner is its uid, mode 0700, not a symbolic link. Else it exits 77 before the preface.

### 6.2 Steps

A test can follow these steps on a fake road. Each step is one session on the shared connection. `M` is a random marker of 16 hex.

1. **Connect.** Section 4.2.
2. **Probe.** Command: `sh -c 'SCRIPT' psw VERSION M`. `SCRIPT` prints `PSW-MARK-M`, then one line each: `uname -sm`; `uname -o` or `-`; the value of `B`; `$XDG_RUNTIME_DIR` or `-`; `id -u`; `command -v zstd` or `-`; `command -v gzip` or `-`; one line `bin PATH` for each executable file `B/podswarm-VERSION-*`; one line `run SID` for each `w-<sid>` directory with an `attach.sock` in the parent directory of `R` (6.1); then `PSW-END-M`. The home reads only the lines between the two markers.
3. **Target.** The home maps `uname -sm` to a target (table 6.3). `Android` from `uname -o` keeps the Linux target. An unknown pair stops with the pair in the message, exit 80. A failed `uname` (a Windows shell) stops with exit 80 until Windows far hosts exist.
4. **Choose.** The home knows the SHA-256 of its own version for that target (section 6.4). When a `bin` line names `podswarm-VERSION-<hash16>` with that `hash16`, go to step 6.
5. **Install.** Command: `sh -c 'SCRIPT' psw SHA256 DIR...`. The home sends the binary on stdin, compressed with a tool that the far machine has: the zstd form when step 2 found `zstd`, else the gzip form when it found `gzip`, else the raw bytes. This is the one use of gzip, and it is the far machine's tool, not a codec of podswarm. `SCRIPT` does, for each `DIR` in order (`B`, `$XDG_RUNTIME_DIR/podswarm/bin`, `/dev/shm/podswarm-<uid>/bin`, `${TMPDIR:-/tmp}/podswarm-<uid>/bin`), until one works: `umask 077`; `mkdir -p DIR`; write the file once to `DIR/.part.$$` (`zstd -dc`, `gzip -dc` or `cat`), or copy it there from the previous `DIR`; `chmod 500`; run `DIR/.part.$$ self verify SHA256`; on exit 0 `mv -f` it to `DIR/podswarm-VERSION-<hash16>` and print `PSW-OK DIR`; on exit 126 (a `noexec` mount) try the next `DIR`; on another code remove the part file and exit with that code. `self verify` (file 18) hashes its own file, checks that its directory is owned by its uid, mode 0700, not a symbolic link, and exits 0 on a match, 65 on a hash mismatch, 77 on a bad directory. The rename is atomic also on NFS, so many hosts that share one home directory never see a half file.
6. **Start.** Command: `sh -c 'exec "$0" worker --stdio --sid "$1" --nonce "$2"' PATH SID NONCE`. The worker re-executes itself from a `memfd` where the system has one (file 13), sets up `R`, starts its spawner (file 12), writes the preface (4.4), and sends `hello`. `hello.bin` carries the size and the SHA-256 of its file. On a mismatch with the home's copy the home ends the road and runs step 5 again, once.
7. **Link.** The home answers `ready` (section 9). The worker sends its first `hb` (file 05).

The probe (step 2) runs once per host and holder: the holder keeps its answer. A warm host costs step 6 only, or nothing while a link is open.

### 6.3 Targets

| `uname -sm` | Target |
| --- | --- |
| `Linux x86_64` | `x86_64-unknown-linux-musl` |
| `Linux aarch64`, `Linux arm64` | `aarch64-unknown-linux-musl` |
| `Linux armv7l`, `Linux armv8l` | `armv7-unknown-linux-musleabihf` |
| `Linux armv6l` | `arm-unknown-linux-musleabihf` |
| `Linux i686`, `Linux i586`, `Linux i386` | `i686-unknown-linux-musl` |
| `Linux riscv64` | `riscv64gc-unknown-linux-musl` |
| `Linux loongarch64` | `loongarch64-unknown-linux-musl` |
| `Linux ppc64le` | `powerpc64le-unknown-linux-musl` |
| `Darwin x86_64` | `x86_64-apple-darwin` |
| `Darwin arm64` | `aarch64-apple-darwin` |

These are the static targets of the org (file 02). A Linux far host always gets the static musl build.

### 6.4 Binaries for other targets

The home's own file serves its own target. For another target the home reads `${XDG_CACHE_HOME:-$HOME/.cache}/podswarm/bin/<target>/podswarm-<version>` on the caller's machine. `podswarm self fetch --target T` (or `--all`) fills it from the release of the same version. When a target is absent and the release is reachable, the home fetches it on demand and prints one line; `--offline` refuses with exit 69 and names the command. A fetched file is checked against the signed `SHA256SUMS` of the release (file 16). The SHA-256 of each target comes from that file, and the bootstrap (section 6.2) uses that value for `hash16`, `self verify` and `hello.bin`. It is the outside check of a release, so it stays SHA-256 and is not a content id.

### 6.5 Version rule

On a road the far worker always runs the exact version and build of the home: the cache key holds both. There is no version skew on a road. `--remote-exe PATH` (pool key `remote_exe`) uses a binary that is already on the far host, with no copy; its `hello.proto` range must contain the home's protocol number (section 9), else `err{unsupported}`. On a `wss` road the two sides agree on the protocol by `hello.proto` and `ready.proto`.

## 7. The link

### 7.1 `pod-link` on the stream
After the prefaces, the stream carries `pod-link`: many streams over one byte stream, each with a credit window, and a window for the whole link. The party that sends `hello` is the `Dialer` of `pod-link` (odd stream ids) on every road: the worker on a road that the home started, and the worker or the submitter on `wss`. The other party is the `Listener`. Stream 1, opened by the dialer before any other, is the **control stream**. Each other stream carries one bulk transfer (file 05, section 7).

### 7.2 Settings and the window rule

| Setting | Value |
| --- | --- |
| `frame_size` | 16 KiB; 4 KiB when the link estimate is under 2 Mbit/s |
| `stream_window` (the largest window of one stream) | `clamp(2 * bdp, 64 KiB, 8 MiB)` |
| `link_window` | `clamp(4 * bdp, 256 KiB, 8 MiB)`, at least `stream_window`; at most 1 MiB on a worker with under 512 MiB of memory |
| `max_streams` | 64 |
| `keepalive_s` | 30 |
| `dead_after_s` | 90 |

`bdp = rate * rtt`. `rtt` is the round trip of the last `PING` of the link. `rate` is the estimate of the road in bytes per second: the bytes that bulk streams moved per second while they had data to send, as an exponential mean. Before a measure, the holder uses the last values of that host; with none, `stream_window` is 256 KiB and `link_window` is 1 MiB until the first measure.

Reason: throughput is at most `window / rtt`, so a fast link needs a large window. On a slow link a large window fills the road with bulk bytes, and a control frame waits behind them: 8 MiB at 1 Mbit/s is 67 s, longer than the silence budget. With the rule, a control frame waits at most about two round trips plus one frame.

* The writer sends frames of the control stream before frames of other streams (ask P-4 of file 21). Fallback: a fairness test that shows a control frame waits at most one frame of data.
* Among bulk streams with credit, the writer serves the priority class of the stream header first: `demand`, then `prefetch`, then `wb` (file 06), then the others in turn.
* `pod-link` takes its settings when the link starts. Until it can change a window cap on a live link (ask P-4 of file 21), the home computes the settings at each start of a link (also at each reattach) from the values that the holder kept for that host.
* On an ssh road the ssh channel window limits too: 2 MiB on OpenSSH, 1 MiB with `dbclient -W` (4.7). A `stream_window` above it adds memory and no speed.

### 7.3 Cipher order on TLS roads
The client builds its cipher list at start. On aarch64 without the `aes` CPU feature, on armv7, arm, riscv64 and loongarch64: `TLS13_CHACHA20_POLY1305_SHA256` first, then AES-128-GCM, then AES-256-GCM. On x86_64 with AES-NI and on aarch64 with `aes`: AES-128-GCM first. The coordinator follows the client's order. Reason: software AES-GCM on a core with no AES unit runs at about half the speed of ChaCha20-Poly1305. On an ssh road the user's ssh configuration picks the cipher.

## 8. Control framing

A control message on stream 1:

```
u32 length (big endian) | u8 codec | body
```

* `length` counts the codec byte and the body.
* Codec `0x00`: the body is one JSON object (UTF-8).
* Codec `0x01`: the body is zstd, level 1, of one JSON object. A sender uses it only when the JSON form has at least 4,096 bytes, the zstd form is smaller, and both sides have the feature `zstd.1` (D-81). A receiver stops inflating at 4 MiB and ends the link with `err{too_large}`.
* Codec `0x03` is reserved. Every other value ends the link with `err{bad_request}`.
* Before `ready`: a message has at most 4,096 bytes, codec `0x00`. The dialer sends only `hello`. The listener sends only `ready` or `err`.
* After `ready`: the limits of file 05, section 10 (the wire limits table).
* Every object has a string field `t`. The rules for fields, rows and numbers are in file 05, section 3.

## 9. `hello` and `ready`

The dialer sends `hello` as its first message. On a road the home waits at most 10 s for it after the preface. On `wss` the time limits before `ready` are in file 16.

```json
{"t":"hello","proto":[1,1],"role":"worker","inst":"9f2c61d0a4b7e381",
 "sw":"podswarm/0.2.0 x86_64-unknown-linux-musl","bin":{"size":8812344,"sha256":"<64 hex>"},
 "features":["zstd.1","tmpl.1","io.1","pty.1","attach.1","blob.1"],
 "caps":{}, "tags":["lab"], "lifetime_s":7200}
```

| Field | Rule |
| --- | --- |
| `proto` | `[min, max]` of the protocol numbers that the sender speaks. This document defines protocol 1. |
| `role` | `worker`, `submitter` or `hub`. |
| `inst` | 8 random bytes in hex, made at process start. A reattach of the same process sends the same value. |
| `sw` | `podswarm/<version> <target>`. |
| `bin` | size and SHA-256 of the binary file of the process (section 6.2, step 6). |
| `features` | The feature names that the sender supports. |
| `caps` | Worker only: capacity and capabilities. The fields are defined in file 08 (capacity, speed, lifetime), file 12 (containment, limits, shell, probe), file 13 (boundary, shield), file 06 (view rungs), file 14 (network policies). |
| `tags` | Worker tags. |
| `lifetime_s` | Seconds of life that remain (file 10). |
| `enrol` | `wss` only: `{invite, proof, name?}` (file 16). |
| `stmt` | Optional: an organisation member statement `{doc, key, sig}` of at most 2,048 bytes (file 16, section 9). |
| `rotate` | Later: `{new_key, sig}`, a worker key rotation signed by the old key (file 24). |

The listener answers `ready` or `err`:

```json
{"t":"ready","proto":1,"features":["zstd.1","io.1","pty.1","attach.1"],"wid":3,
 "swarm":"5b0c9e7a11f3d2c48e6a0f17c2d94b35","gen":"a17be0c35d9f4e28","hb_s":10,
 "limits":{"msg":1048576,"inflate":4194304,"offer_rows":1000,"result_rows":1000,"hb_rows":8192},
 "reconnect_jitter_ms":0,"cell":{"name":"eu1","region":"eu-west","juris":"eu"}}
```

| Field | Rule |
| --- | --- |
| `proto` | The highest number in both ranges. No common number: `err{unsupported, fatal}`. |
| `features` | The intersection of both lists. A feature is on only when it is in `ready.features`. |
| `wid` | Worker only: the worker number. A home numbers its workers from 1. |
| `swarm` | 32 hex: the 16-byte swarm id of a coordinator (`w` of the invite token, file 16, section 7.1), or 16 random bytes that a home makes at its start. |
| `gen` | The store generation (file 11). A home makes a random one at its start. |
| `hb_s` | The heartbeat period (file 05, section 8). |
| `limits` | The wire limits of file 05, section 10, by name. |
| `tags`, `pins` | Optional: tags that the authority gives; new coordinator pins (file 16). |
| `reconnect_jitter_ms` | The bound of the first reconnect delay (section 11.3). A home sends 0. |
| `cell` | `{name, region, juris}` of the cell of the authority (file 08, D-42). |

Core feature names:

| Name | Gives |
| --- | --- |
| `zstd.1` | codec `0x01` |
| `tmpl.1` | the template grammar 1 of a shape (file 18) |
| `io.1` | attached I/O, `signal`, `resize` (file 05, section 5) |
| `pty.1` | an attempt on a terminal (file 05, file 12) |
| `attach.1` | reattach with stream offsets (section 11, file 05) |
| `blob.1` | `blob_put` and `blob_get` streams (file 15) |
| `view.1`, `spread.1`, `net.1`, `ckpt.1` | the hooks of files 06, 07, 14 and 15; each file defines its feature |

Every feature name has the form `name.N` (D-23).

The names of the extensions are in file 24. A reserved field of a feature that is not on gets `unsupported`.

`ready` does not renew the fence: only an answered `hb` moves `t_ok` (file 05, section 8). The first `hb` after `ready` renews it one round trip later.

## 10. Rules of one link

* **One connection.** A worker has at most one current link. When an authority accepts a new link of a worker, it closes the old one and drops its unread frames. It processes a frame only from the current link of its worker. It sends an `err` only on the link of the frame that caused it. A result that a dropped frame carried comes again from the journal of the worker.
* **Duplicate identity** (`wss`). A new link with the same `inst` replaces the old one at once. A new link with another `inst` replaces the old one only when the old link was silent for `2 * hb_s`. Else the new link gets `err{duplicate_identity, fatal}` and the worker row is marked `suspect` (file 09). On a road the `sid` and the attach socket (section 11) are the identity, and only the home holds the `sid`.
* **Generation.** A worker keeps the `swarm` and the `gen` of its last `ready`. When `ready.swarm` or `ready.gen` differs, the worker deletes its journal, kills every attempt, and starts empty. A new home (a new holder) is a new generation for each far worker.
* **First frame.** After `ready` the first frame of a worker is an `hb` with its full holding. The authority sends no offer on a link before it processed that `hb` (file 05, section 6).

## 11. Cut, reconnect and reattach

### 11.1 Detection
* The home declares a road dead when no frame of the worker arrived for `hb_s + rtt_max` (15 s with the defaults), when the ssh child exits, or when `pod-link` ends. Then it runs `ssh -O exit` on that master, so the next session opens a new connection and does not reuse a hung one.
* The worker sees end of file on stdin, a write error on stdout, or the end of `pod-link`. It keeps its attempts. Their fence (file 05, section 8) runs on: no `hback` moves `t_ok`.

### 11.2 Reattach on a road
The worker listens on `R/attach.sock` (a unix socket, mode 0600, peer uid checked) for its whole life. To reattach, the home opens the road again with:

```
sh -c 'exec "$0" worker --attach "$1" --nonce "$2"' PATH SID NONCE
```

The attach process finds `R` of `SID`, connects to the socket, writes the road preface with its own `NONCE`, and relays bytes between its stdio and the socket in both directions. It exits 0 when either side closes. When no worker with that `sid` lives, it writes no preface and exits 66; the home then counts each open attempt on that worker as lost (file 05) and starts a new worker. The worker treats a new connection on its socket as a new link: it closes the current link (section 10), runs the prefaces of `pod-link`, and sends `hello` with the same `inst`. The home answers `ready` with the same `gen`, and the first `hb` reconciles (file 05, section 6). Streams of attached attempts continue at their offsets (file 05, section 5).

**Reattach window.** A worker waits for an attach until its last attempt ended by the fence, and at least `silence_s` after the cut when it held no attempt. Then it waits `linger_s` (section 13) and exits. A cut that the home repairs within `silence_s` is not seen by a running command [T].

### 11.3 Redial delays
The party that dials again (the home on a road, the worker on `wss`) waits a first delay uniform in `[0, reconnect_jitter_ms]`, then, before retry `k` (from 1), a delay uniform in `[0, min(30 s, 1 s * 2^k)]`. A coordinator sets `reconnect_jitter_ms` from its count of workers (file 10, section 15). A home sends 0, so it redials a road at once.

### 11.4 What a cut cannot survive
On a host where logind kills the processes of a user at logout (`KillUserProcesses=yes`) and linger is off, a cut that ends the last ssh login of that user also ends the worker. Its open attempts are lost. `podswarm doctor HOST` reports this case.

## 12. The holder

The **holder** is a background process of the user that is the home of the session. It is the pattern of an ssh control master. It is not a service: no boot start, no unit file, no listener on a network, one per user and version, and it ends by itself.

* **Start.** A `podswarm` command that needs a home connects to the holder socket. When nothing answers, it starts `podswarm holder` (internal verb) with `setsid`, stdin and stdout on `/dev/null`, stderr to `${XDG_STATE_HOME:-$HOME/.local/state}/podswarm/holder.log`, and connects again. Two commands that start at the same time race on an `flock` of `holder.lock`; the loser connects to the winner.
* **Socket.** `$XDG_RUNTIME_DIR/podswarm/home-<version>.sock`, else `/tmp/podswarm-<uid>/home-<version>.sock`; directory 0700; socket 0600; the holder checks the peer uid (`SO_PEERCRED`, `getpeereid`) and refuses another uid. On Windows: a named pipe `\\.\pipe\podswarm-<user>-<version>` whose access list holds the user only. The command and the holder speak `pod-link` with the control framing of section 8, `hello{role: submitter}`, and the operations of file 05, section 9. The version in the name lets an old holder finish its work while a new one starts.
* **What it keeps warm.** The ssh masters (through its open sessions), the far workers and their links, the probe answers and the binary per host (section 6), the window values per host (section 7.2), the view index of each workspace (file 06), the pool reports (file 08), the learned tables (file 08), and the in-memory queue of the session (file 09).
* **Life.** The holder exits when for `hold_s` (default 600, range 0 to 86,400) no command was connected, no attempt ran and no task was queued. Before it exits it sends `bye{reason: "home_exit"}` on each link. `hold_s = 0` equals `--no-hold`.
* **`--no-hold`.** The command itself is the home. It opens its roads, runs, sends `bye` on each link, and ends them at its exit.
* A command whose holder dies loses the session: each far worker sees a cut, keeps its attempts until the fence, and then ends (section 13). `podswarm run` exits 255 (file 18).

## 13. Life of a far worker

* A worker that a road started lives while its link is in use.
* After a `bye` from the home, the worker ends its attempts with the kill ladder (file 12), sends their results, removes `R` and its run files, and exits 0. After a cut, it waits for the reattach window (section 11.2).
* `linger_s` (pool key and setting; default 0, range 0 to 86,400): after the end of its last link and its last attempt, the worker waits that long on its attach socket before it exits. A new holder finds it in the probe (`run SID`), attaches, and starts with a new generation. This makes the next session start without step 6.
* At each start the worker sets the time of its binary file to now. It removes the other binaries in `B` whose time is older than 30 days.

**What is left after a session**: the binary in `B`, the content cache (sealed or absent by the shield, file 13), the probe cache of file 12, and a lingering worker while `linger_s` runs. Nothing else: no service, no key, no log file.

* `podswarm forget HOST` opens the road and removes `B`, the content cache, the probe cache, and every run directory of the user whose `lock` is free. It sends `bye` to a lingering worker first. File 13 adds what `forget` changes on the caller (the host salt).
* `--no-trace` (pool key `leftovers = "none"`, file 13): the session puts the binary in the work area, and at its end the worker removes it with the rest. The run report lists what stays.

## 14. Workers that dial out

A machine that nobody can dial runs a worker that dials out to a coordinator and stays: `podswarm join wss://host[:port]`. The invite token comes on stdin or through `--invite-fd N` (file 16). The worker keeps its key and its state directory (file 12), dials again after each loss (section 11.3), and is the "long-lived agent" that the owner allows for such machines. The worker code is the code of `--stdio`.

`podswarm bootstrap HOST...|--hosts-file FILE --join @TOKENFILE` installs such a worker over an ssh road. The token holds the coordinator address (file 16):

1. Run steps 1 to 5 of section 6.2, and also read `systemctl --user` and `loginctl show-user $(id -un) -p Linger`.
2. Copy the binary to `~/.local/bin/podswarm.new.<host>.<pid>`, run `self verify`, keep the old file as `podswarm.prev`, and rename the new file to `podswarm`.
3. Start: when linger is on and `systemctl --user` works, `systemd-run --user --unit=podswarm-worker -p Delegate=yes -p KillMode=control-group sh -lc 'exec ~/.local/bin/podswarm join ...'`; else `setsid sh -lc 'exec ~/.local/bin/podswarm join ...'`. The token goes on an inherited pipe, never in argv or in the environment.
4. When the worker is not `ready` at the coordinator within 60 s, restore `podswarm.prev`, start it, and report `rolled_back`.

Start at boot is `podswarm autostart` (file 18). The reverse roads of section 5.5 give the same reach to a session.

## 15. Which road for which machine

| Machine | Road | Notes |
| --- | --- | --- |
| A server I can ssh to | `HOST` (`ssh`) | The first use copies the binary (section 6). |
| A server behind a bastion | `ssh://host?jump=bastion` | `-J`. |
| A container | `exec:docker exec -i NAME`, `exec:kubectl exec -i POD --`, `exec:incus exec NAME --` | Needs `sh` in the image, or `--remote-exe`. |
| WSL, a phone on USB | `exec:wsl`, `exec:adb shell` | |
| A phone behind NAT | `podswarm join wss://...` in Termux; later `relay://NAME` | DNS rule of section 5.4. |
| A host with HTTPS-only egress | `podswarm join wss://...` through the proxy of `pod-proxy`, coordinator on port 443 | Outbound only; no listener on the host. |
| An HPC node inside an allocation | `ssh://node?jump=login`, or `exec:srun --jobid=J -w NODE -N1 -n1 --`, or `srun podswarm join wss://...` | Node-local state (file 12); the lifetime comes from the batch system (file 10). |
| The caller's own machine | `local` | |

## 16. Performance of a road

| Item | Value |
| --- | --- |
| A new ssh connection (TCP, key exchange, authentication) | 150 to 500 ms on a fast network [EV-010] |
| A new session on a shared connection | about 50 ms (same source) |
| A command on a warm link (`podswarm run HOST -- true`) | no new ssh session: one `offer` on the standing `pull` and one `result`; at most 30 ms over the round trip of the link [T] (A-20) |
| First run on a host with no podswarm | connect, probe, install, start: under 5 s on a 20 Mbit/s link [T] (A-23). A binary of 10,000,000 bytes (A-09) takes 4 s raw at 20 Mbit/s, so the compressed copy of step 5 is part of the target. |
| Reattach after a cut | a new connection plus one session, well inside `silence_s` [T] |

Throughput of one window is at most `window / rtt`:

| Round trip | OpenSSH channel 2 MiB | `link_window` 8 MiB | `stream_window` 256 KiB | Dropbear default 24 KiB |
| --- | --- | --- | --- | --- |
| 10 ms | 210 MB/s | 840 MB/s | 26 MB/s | 2.5 MB/s |
| 50 ms | 42 MB/s | 168 MB/s | 5.2 MB/s | 0.49 MB/s |
| 100 ms | 21 MB/s | 84 MB/s | 2.6 MB/s | 0.25 MB/s |
| 200 ms | 10.5 MB/s | 42 MB/s | 1.3 MB/s | 0.12 MB/s |

[EV-011] On an ssh road the smallest of the ssh channel window and the `pod-link` windows sets the ceiling. One ssh connection is one TCP connection and one cipher stream on one core, so more sessions on one master add no bandwidth. Bench B-29 (file 23) checks these values.

## 17. Tests of this file

File 23 holds the tests of this file: U-conf-road (the `Road` suite on `mem`, `unix`, a local sshd and an `exec` loop), U-road-rc (start files that print or read stdin, and the login shells), E-06 (bootstrap on busybox, Dropbear, a `noexec` home and an NFS home), E-07 (a firewall cut of 10 s during a run), E-08 (`MaxSessions 1`), B-29 (road throughput).

## 18. Milestones

Milestones are those of file 22.

| Part | M1 | Later |
| --- | --- | --- |
| Roads | `ssh` (OpenSSH and Dropbear clients), `local` | `exec`, `podssh` (M2); `wss` with the coordinator (M4); `relay` (file 24); Windows far hosts (M10) |
| Bootstrap | sections 6.1 to 6.5, the compressed copy | `podswarm bootstrap --join`, `autostart` (M5) |
| Link | `pod-link`, sections 7 to 10 | a live change of the window cap (ask P-4), a second ssh session for bulk |
| Reattach, holder | sections 11 and 12, `forget`, `--no-trace` | |
| Dial-out workers | | `join` (M4), the reverse roads (file 24) |
| ssh as a library | | ask P-13 of file 21: a `pod-ssh` crate, so no system `ssh` is needed (M10) |

## 19. Settings of this file

`hold_s` 600; `linger_s` 0; `ssh.max_sessions` 4; `ssh.control_persist_s` 60; `ssh_args`, `jump`, `remote_exe` none; the `pod-link` settings of section 7.2. File 19 lists scope, type and range of each. `leftovers` belongs to file 13.
