# 13. Trust: boundary and shield

This file defines the two protection axes of an attempt. The **boundary** protects the host from the task. The **shield** protects the task and the caller from the host. File 12 says how a worker makes boundary `confined`, file 24 holds the boundaries `sandbox` and `vm` and the image view, file 16 holds keys, policies and the attack table, file 06 the view, file 07 spreading, file 14 the network policy, and file 15 checkpoints.

## 1. Two axes

| Axis | Protects | Shape field | Order | CLI |
| --- | --- | --- | --- | --- |
| boundary | the host from the task | `needs.boundary` | `none < confined < sandbox < vm` | `--boundary` |
| shield | the task and the caller from the host | `needs.shield` | `none < private < guest < sealed` | `--shield` |

Both axes follow one rule: a worker never runs an attempt at a weaker level than the attempt asked for. A worker advertises the strongest level of each axis that it can give now (`caps.boundary`, `caps.shield.max`). The scheduler and the placement of one command (files 08 and 10) match only where `boundary >= needs.boundary` and `shield.max >= needs.shield`. A level is always named, never numbered: a key that sets a floor (`boundary_min`, `shield_min` in a residency rule, a capability profile or a policy, files 08, 16, 17) takes a level name.

One guest serves both axes. The reverse is false.

| Shield asked | Boundary that the attempt gets as well | Reason |
| --- | --- | --- |
| `none`, `private` | no change | `private` changes where data lives, not what the task can do |
| `guest`, `sealed` | at least `vm` | the payload runs under a guest kernel |

Boundary `vm` does not give shield `guest`: the image view of boundary `vm` puts host files and a host file server in the path, so the host sees the files (file 24).

The caller's own machine meets every shield level, because there the host is the caller. The local worker of a session counts as `shield.max = sealed` for placement, and it never runs a guest for the shield (D-76).

## 2. Boundary

| Level | Testable sentence | Where |
| --- | --- | --- |
| `none` | The attempt runs as the worker's uid. podswarm promises the wall timeout and the tree kill of the advertised containment rung (file 12). Other attempts and the worker key are readable by it. | core, every OS |
| `confined` | An `open`, `execve` or `truncate` outside the granted lists fails; with `confine_tcp` a TCP `connect` or `bind` outside the granted ports fails; `ptrace`, `process_vm_*`, `mount`, namespace creation, `bpf`, `keyctl` and `io_uring_*` fail; `no_new_privs` is 1; a read of the worker's `/proc/<pid>/environ` fails. | core, Linux only |
| `sandbox` | System calls of the attempt are served by a user-space kernel (gVisor through podvm); a host path that is not mounted is not reachable. | later (file 24) |
| `vm` | The attempt runs under a separate guest kernel; a host file that is not shared is not readable. Under TCG the boundary is the emulator process. | later (file 24) |

* The mechanism of `confined` (Landlock, seccomp, the features `confine_fs`, `confine_tcp`, `confine_scope`, `confine_unix`, `confine_udp` by Landlock ABI, the default profile, the `AF_UNIX` rule below ABI 9) is in file 12, section 17. A shape that needs a feature matches only a worker that lists it.
* `caps.boundary` is the list of levels that the worker probed and that its policy key `allow_boundaries` allows (file 16). A worker reports the level it really entered in the result field `boundary`.
* The image view (`shape.image`) gives an image's root file system and makes no boundary claim. It matches separately (file 24).
* A worker that gets an attempt above its level answers `spawn_failed`, reason `isolation_refused`. When no worker of the pool can ever meet the level, the authority answers `needs_unsatisfiable` (file 05).
* On boundary `none`, a task of another submitter on the same worker can read the worker key and stop the worker. File 16 states what this means for a shared worker.

## 3. Shield: the attackers and what each level stops

Attackers:
* **U**: another unprivileged user on the host, while the run is live.
* **D**: a later read of the disk: a co-tenant who copies the disk after the session, a host backup, a reuse of the disk by the operator of the machine.
* **R1**: a root user with ordinary tools: `ps`, `/proc/PID/cmdline`, `/proc/PID/environ`, `/proc/PID/cwd`, `/proc/PID/root`, `ls`, `find`, `lsof`, `tcpdump` on the host interfaces, the journal and log files, a copy of a `tmpfs`.
* **R2**: a root user who reads memory: `/proc/PID/mem` and `ptrace` (with `CAP_SYS_PTRACE`), `gcore`, the swap device, the page cache, guest RAM through the QEMU process or QMP `dump-guest-memory`, a kernel module.
* **R3**: a root user who changes things: replaces the copied podswarm binary, a compiler or any tool on `PATH`, QEMU, the firmware or the guest image; changes outputs; fakes a probe; stops or slows the run.
* **R4**: a root user who keeps data: copies the warm store and captured traffic for later.
* **P**: a person with physical access to the server (a memory bus interposer, a cold boot).
* **N**: the network between the caller and the host.

| Attacker | `none` | `private` | `guest` | `sealed` |
| --- | --- | --- | --- | --- |
| U | file modes only; sees payload argv in `ps` | stops file and memory reads; sees payload argv in `ps` (`hidepid` is the host's choice) | stops; sees one QEMU process | stops |
| D | no | stops: the work area is in RAM, the warm store is ciphertext and its key is not on the host; residual: swap where the report says `swap: possible`, sizes of store objects, the login line of sshd | stops; residual: guest RAM in host swap unless `mem-lock` | stops |
| R1 | no | stops blind scans only (the area is in a private mount namespace, not on disk, not in the host mount table); does not stop a root user who opens `/proc/PID/cwd` or `/proc/PID/root` of the run | stops: no file, name, argv or environment value of the run is on the host | stops |
| R2 | no | no; session keys sit in `memfd_secret` where the kernel has it, so `/proc/PID/mem` does not give them, but the plaintext files do | no: guest RAM is QEMU memory | stops; residual: side channels, attacks below the TCB floor (section 8.7) |
| R3 | no | no; podswarm cannot detect it | no; the root user can put a fake guest in place of the real one | stops: a modified guest has another measurement, a modified result fails the channel; residual: denial of service |
| R4 | no | partial: the store is useless without the key, but an R2 user can take the key during a session | as `private` | stops: the key lives only in encrypted guest memory |
| P | no | no | no | partial: DDR4 and DDR5 bus interposers break SNP and TDX |
| N | ssh or TLS | ssh or TLS | ssh plus the inner channel | ssh plus the attested inner channel; residual at every level: sizes and timing |

`private` and `guest` protect against curiosity and leftovers. Only `sealed` protects against a root user who wants the data, and nothing protects the run from being stopped.

[EV-054]
[EV-055]

## 4. Pool trust and the default shield

A pool entry has `trust = "own" | "shared"` (file 08). It is a fact about the machine that the user states. It does not name a level; it gives the default shield.

| Machine | Default shield |
| --- | --- |
| the caller's own machine (the local worker) | `none` |
| remote, `trust = "own"` | `none` (the credential rules of section 5 still hold) |
| remote, `trust = "shared"` | `private` |
| remote, no `trust` key | `private` |

So the default shield of every remote machine is `private`. `private` costs RAM for the work area and about one core-second per 3 GiB of warm state, needs no setup, and gives the first use case of file 01: a rented server on which other people have root. `guest` needs a guest boot and a toolchain image, and `sealed` needs hardware, so neither is a default.

* The pool key `shield` sets a level for one machine. `--shield LEVEL` raises the level for one run.
* A run level below the level that the pool entry sets needs `--force-lower` as well, so a script cannot lower it by accident.
* The first use of a remote machine with no `trust` key prints one line: `HOST: shield private (set trust in the pool file)`.
* The shield rungs of sections 6 to 8 are Linux mechanisms. A remote machine on another OS has `shield.max = none`, so it needs `trust = "own"` or `--shield none`, else it refuses (section 9).

## 5. Credential rules at every level

These rules hold at every shield level, `none` included.

* **No forwarding.** The ssh road (file 04) always adds `-a -x -o ForwardAgent=no -o ForwardX11=no -o ClearAllForwardings=yes -o SendEnv=-*`. No flag turns agent forwarding on (D-75). A forwarded agent lets a root user on the host sign with the caller's keys for the life of the session. [EV-056]
* **The view serves no credential file.** This deny list applies before every other view rule (file 06): `.env`, `.env.*`, `.netrc`, `.npmrc`, `.pypirc`, `.git-credentials`, `.cargo/credentials`, `.cargo/credentials.toml`, `.docker/config.json`, `.aws/`, `.config/gcloud/`, `.azure/`, `.kube/config`, `.ssh/`, `.gnupg/`, `*.pem`, `*.key`, `id_*` except `*.pub`. A denied path reads as absent (`ENOENT`), so a tool does not fail on `EACCES`. Only the user's own configuration or `--allow GLOB` for one run (file 06) opens an entry; the CLI prints that path once per session. A workspace file cannot open an entry, because a cloned repository must not open the caller's secrets.
* **`.git/config` is filtered.** The view serves a copy without `credential.*` sections, without `url.*.insteadOf` values that hold a user part, and without user info in `remote.*.url`. The caller's file does not change.
* **Variables.** The environment of `podswarm run` passes to the remote process inside the protocol, minus the deny list below; it never travels as ssh variables. File 12 (section 10) builds the environment of each kind of attempt from this list. `--env-allow NAME` lets one name pass for one run. A name of the list is refused in the worker policy key `env_pass` (file 16).

| Variable names | Remote worker | Local worker |
| --- | --- | --- |
| `PODSWARM_*`, `*_TOKEN`, `*_SECRET*`, `*_KEY`, `*PASSWORD*`, `*_PASS`, `*CREDENTIAL*`, `SSH_AUTH_SOCK`, `KRB5CCNAME`, a `*_URL` whose value holds `user:password@` | removed | removed |
| `AWS_*`, `GOOGLE_*`, `AZURE_*`, `DOCKER_*`, `GPG_*`, `KUBECONFIG` | removed | kept: the user's own commands on the user's own machine need them |

* **A needed credential** goes as a secret with `min_shield` (section 10), as a file in the work area, never as a variable.

## 6. Shield `private`

### 6.1 The testable sentence
At shield `private`, the run's work area is memory-backed; no file that the run made remains in plaintext on a disk of the host after the session ends, also after a SIGKILL of the worker or a cut of the road; the host holds no key that decrypts the kept warm state between sessions; no credential of the caller is readable on the host; and the area is never written to swap when the report says `swap: locked`.

The run report names the area rung and the swap state, so the claim and its proof use the same words.

### 6.2 The work area
The worker picks the first rung that works, in this order, and names it in the report field `area`. The probe rows that this needs are ask P-6 (file 21).

| Rung | Who | Mechanism | Swap |
| --- | --- | --- | --- |
| `tmpfs-noswap` | root | `tmpfs` with `noswap,size=N,mode=0700` in a private mount namespace; Linux 6.4 and later | `locked` |
| `ramfs-ns` | any user with user namespaces | a new user and mount namespace (own uid mapped to itself), `ramfs`, size cap kept by the keeper | `locked` |
| `tmpfs-ns` | as `ramfs-ns`, when the run needs `tmpfs` features | `tmpfs` in the namespaces | `locked` with the cgroup control of 6.3, else `possible` |
| `sealed-fuse` | any user with FUSE, when the view uses FUSE | the view server writes the run's new files to disk as sealed objects (6.4); plaintext only in the page cache; also the home of an owned directory that does not fit in memory (below) | `locked` |
| `runtime` | any user, no namespaces | a 0700 directory in `$XDG_RUNTIME_DIR` (a per-user `tmpfs`), else in `/dev/shm` | as `tmpfs-ns` |

* A plain disk directory is never a rung of `private`. When no rung works, the run is refused with `shield_unavailable`, reason `no_memory_area`.
* At `private`, `TASK_DIR` (file 12, section 12), `TMPDIR`, the output spill file and the worker journal are in the area. The worker writes no other file outside the area and the binary cache.
* `area_max`: default 50 percent of `MemAvailable` at session start. A write over the cap fails with `ENOSPC`, and the result carries reason `area_full`. `ramfs` has no cap of its own, so the keeper polls the size of the area once per second in the loop that polls memory (file 12) and stops the attempt at the cap.

Owned directories of the view (file 06, section 10.4, for example `target/`) at `private`:
* **Estimate.** At session start the worker takes, for each owned directory, the size that the sealed manifest (6.4) recorded at the end of the last session, times 1.5. A directory with no record counts as 1 GiB.
* **Placement.** Smallest estimate first, the worker puts a directory in the memory rung while the sum of estimates stays under 75 percent of `area_max`. The rest of the area is for `TASK_DIR`, `TMPDIR`, the spill file and the journal. Each other directory is in the sealed store on disk: the view server serves it as on the `sealed-fuse` rung, with plaintext only in the page cache.
* **Overflow.** A write that passes `area_max` fails with `ENOSPC` and the reason `area_full` (file 05, section 3). The home records the directory for that machine. The CLI prints one line with the directory, its size, `area_max` and the way out (`--area sealed`, or `trust = "own"` for a machine that only the user controls). The next session starts that directory in the sealed store.
* **Setting `area`** (`--area`, pool key `area`): `auto` (default) applies the rules above; `memory` puts each owned directory in memory; `sealed` puts each owned directory in the sealed store.
* **FUSE.** The sealed store of a directory needs a FUSE rung of the view (file 06, section 3). With `area = "sealed"` and no FUSE rung, the run is refused with `shield_unavailable`, reason `no_sealed_area`. With `auto` and no FUSE rung, each owned directory is in memory.

[EV-057]

### 6.3 Swap
The payload holds file contents in its own anonymous memory, and an unprivileged process cannot `mlock` gigabytes. So when the worker has the containment rung `cgroup` (file 12), it writes `memory.swap.max = 0` on the cgroup of each attempt at `private` and above. [EV-058]

The report field `swap` is one of:
* `none`: `/proc/swaps` lists no device.
* `locked`: no swap can receive the run's pages: no swap device, or `memory.swap.max = 0` is set and the area rung is `tmpfs-noswap`, `ramfs-ns` or `sealed-fuse`.
* `possible`: every other case. A host with zswap and a swap device reports `possible` unless the cgroup limit is set.

`--shield-require swap-locked` (pool key `shield_require = ["swap-locked"]`) refuses a run with reason `swap_not_locked` when the state is `possible`. Without it, `possible` is allowed and reported.

### 6.4 Warm state as ciphertext
Speed needs state between runs: the content cache of the view and warm build directories. On a shared host this is data at rest. The default keeps it, as ciphertext, under a key that only the caller holds. Kernel encryption (fscrypt, dm-crypt) needs the host's admin or root, and fscrypt hides nothing from other users while its key is added, so podswarm uses its own store. [EV-059]

* **Keys.** The home holds a 32-byte `home_key` in the caller's key store (file 16). Per machine it keeps a 16-byte random `host_salt`. `K_host = HKDF-SHA-256(ikm = home_key, salt = host_salt, info = "podswarm-store-1" || pool name || remote uid)`. The home sends `K_host` over the road at session start. The worker keeps it in a `memfd_secret` mapping, else in `mlock`ed memory, and zeroes it at exit. The host never stores it.
* **Format.** One store holds the view cache and the warm overlay. An object holds at most 1 MiB of plaintext and is sealed with AES-256-GCM, or ChaCha20-Poly1305 when the CPU has no AES instructions, with a random 96-bit nonce. The associated data is the object id, the store generation and the shield level. The file name of an object is the hex of the keyed BLAKE3 hash of its plaintext (the `b3k:` form of file 15) under a name key that HKDF derives from `K_host` with `info = "podswarm-name-1"`, so equal content dedupes inside one store and names leak nothing. A sealed manifest maps paths, modes and times to object ids and records the size of each owned directory at session end; file names of the tree are only in the manifest. After 2^31 seals under one key the home makes a new `host_salt` and the next session starts cold.
* **Level.** A store opens only at its own level or higher, because the level is in the associated data.
* **Cost.** AES-256-GCM seals at about 3 GiB/s on one x86_64 core, so a restore of 3 GiB costs about one core-second, less than a read of 3 GiB from most disks. Restore is parallel per object. The cost is RAM: a restored overlay sits in the area. On the `sealed-fuse` rung the restore is lazy: the view server opens an object when a process opens its file. [EV-060]
* **Change between sessions.** The manifest carries a generation counter. The home keeps the BLAKE3 id of the last manifest per machine. At start, a manifest with another hash is discarded, the run starts cold, and the report says `store: discarded`. A flipped byte in an object fails its tag and has the same effect.
* **Change during a session.** It is not detected: a root user who holds the key in memory (R2) can write valid objects (R3).
* **Save.** The worker writes new and modified objects at session end and after 60 s with no command. A crash loses warmth, not correctness: the next run starts cold.
* **Off.** `--no-cache` (pool key `cache = false`) keeps nothing: the area dies with the session.
* **Rotation.** `podswarm forget HOST` deletes the store and makes a new `host_salt`, so a key that an R2 user took in an older session opens nothing new.

### 6.5 Process hygiene
| Measure | Stops | Does not stop |
| --- | --- | --- |
| no secret in argv or environment | U, R1 with `ps` | nothing more |
| `PR_SET_DUMPABLE 0` and `RLIMIT_CORE 0` in the worker (file 12), `RLIMIT_CORE 0` in the payload | core files on disk; ptrace by other users of the same uid | root |
| session keys in `memfd_secret`, else `mlock` | key pages in swap; key reads through `/proc/PID/mem` | a root user who injects code or loads a module |
| private mount namespace for the area | blind scans, the host mount table | `nsenter`, `/proc/PID/root` |
| no log file on the host (6.6) | R1 and D on logs | the login line of sshd |
| `hidepid` on `/proc` | the host's choice; the probe reports it | |

[EV-061]

### 6.6 Logs
At `private` and above the worker writes no log file on the host. Its log goes to the home over the link (the log channel of file 04). The probe cache of file 12 holds host facts only and stays, except with `leftovers = "none"`.

### 6.7 The binary on the host
The road copies the podswarm binary into the cache directory of file 04 (directory 0700, file 0500). The binary is public, so the copy leaks nothing, and it saves about 10 MB of transfer per session.
* The worker reads its own file and sends its size and SHA-256 in `hello` (the value that `SHA256SUMS` of the release lists, file 16). The home compares them with its own copy and sends the binary again on a mismatch. This catches a damaged copy. It does not catch R3: the host computes the answer.
* After start the worker copies itself into a `memfd` and re-executes from it (`memfd_create`, `fexecve`), so a later change of the file does not change the running worker. This does not stop R3 either.
* `leftovers = "none"` (CLI `--no-trace`, file 04): the binary goes into the area for each session, the worker runs from the `memfd`, and at exit it removes the file, the store, the probe cache and the cache directory. The run report lists what stays on the host: `left: ["bin", "store"]` or `left: []`.

### 6.8 Removal at exit and after a crash
* On a memory area, removal is: kill every process of the session, then unmount or remove the tree. The pages go back to the kernel. podswarm does not overwrite them.
* On the sealed store, removal is: drop the key. The worker zeroes `K_host` and the session keys and closes the `memfd_secret`. The ciphertext stays for the next session unless `--no-cache`.
* On a plain disk nothing is reliable: an overwrite on an SSD does not reach remapped flash blocks. podswarm writes no plaintext of the run to a disk at `private`, so it never needs to wipe one.
* Worker crash: the spawner (file 12) sees end of file. At `private` it also owns the area: it kills the attempt trees, removes the area and exits. On a namespace rung the area dies with the last process of the namespace, so a SIGKILL of every process still frees it.
* `runtime` rung: a SIGKILL of the worker and the spawner together leaves the directory. The spawner holds a `flock` on a lock file in the area. The next start of any podswarm command of that user removes each area directory whose lock is free. systemd-logind also removes `$XDG_RUNTIME_DIR` at the user's last logout.
* Road cut: the worker keeps the session for the reattach window (file 04), then ends its attempts by the fence, removes the area and exits.
* The key is gone in every case, because it lived only in process memory.

### 6.9 Integrity
At shield `private` and `guest`, a root user of the host can change the result, the exit code and any file that the run writes back, and podswarm cannot detect it. Use `sealed`, or run the command on a second machine and compare (`--check-on HOST2` with `verify.1`, file 24).

Tools from the host's `PATH` are the host's. At `private` the run uses them unless the shape names an image by digest (file 24) or a toolchain path in the view.

### 6.10 Tests
Each test plants a canary: 32 random bytes in hex, in a file name, a file body, a variable and an argv element of the caller.

Tests of file 23: E-10 leftovers, E-11 kill of every process, E-12 road cut, E-13 credentials, E-14 swap, E-15 store at rest, E-16 keys, E-17 no logs, E-18 refusal with `no_memory_area`, E-36 a build directory past `area_max`, E-37 refusal with `no_sealed_area`.

## 7. Shield `guest`

### 7.1 What podvm gives today
The machine rung of podvm boots a pinned kernel under KVM where `/dev/kvm` opens, else under TCG. It puts host data in the guest: a volume is a 9p mount of a host directory, the base and run archives are host files, stdin is copied into the run archive on disk, and the network is QEMU user mode, which reaches the host loopback. Each of these shows the run's data to the host in plaintext. `pod-guest` has no network (`-nic none`) but its only channel is a mailbox volume, which is also a host file, and it has UEFI and DOS flavours only. So shield `guest` uses its own guest plan, not the podvm machine rung as it is. The asks are V-7 to podvm and P-18 to podcrates (file 21). [EV-062]

### 7.2 The guest plan
* **Boot.** The pinned guest kernel plus an initramfs that holds the static podswarm binary and an init, and nothing from the user. No 9p, no virtiofs, no network card (`-nic none`), no host stdin file.
* **Link.** One `virtserialport` bound to a `chardev` Unix socket in the per-run 0700 directory. A TCP port on the host loopback is refused: any local user can connect to it. vsock needs `/dev/vhost-vsock` and is a later option.
* **Disk.** One raw virtio-blk file in the per-run directory holds the store of 6.4, written by the guest podswarm.
* **Memory.** `-m` is the memory need of the attempt plus 256 MiB. When `RLIMIT_MEMLOCK` allows it, the worker adds `-overcommit mem-lock=on` and reports `swap: locked`, else `swap: possible`.
* **Toolchain.** From an image by digest (file 24), which the guest podswarm fetches over the inner channel and checks inside the guest, or from the caller's view. Never from the host's `PATH`.

### 7.3 The worker inside the guest
The worker that the road starts on the host is a relay. It probes, starts QEMU with the guest plan, and splices bytes between the road and the `chardev` socket. It sends nothing secret and reads nothing of the run. The guest podswarm is the worker of the attempt: the rules of file 12 apply inside the guest, the area of 6.2 is the guest's own RAM, and the guest holds `K_host`. The relay reports the guest's results unchanged. When the road cuts, the relay keeps the guest for the reattach window (file 04).

### 7.4 The inner channel
At shield `guest` and `sealed` the link between the home and the guest podswarm carries an inner channel: TLS 1.3 (`rustls`), server = the guest with an Ed25519 raw public key made at guest boot, client = the home with its session key. The relay carries it as one opaque `pod-link` stream. This is the one exception to the rule that a self-authenticating road carries no TLS (file 04): ssh ends at the host, and the host is outside the protected area. A guest without AES instructions offers ChaCha20-Poly1305 first. At `guest` the home cannot verify the guest key, so the channel stops a passive copy of the relayed bytes only. At `sealed` the attestation report binds the guest key (8.3), so the channel stops R3 as well. One code path serves both.

### 7.5 KVM and TCG
Under KVM a guest boots in about 0.6 s and its CPU speed is close to native. The cost is the guest memory, reserved for the session. Under TCG work runs 3 to 21 times slower by benchmark, and compile work is near the top of that range. [EV-063]

So `guest` on TCG runs only with `guest_tcg = true` in the pool entry or `--allow-tcg`, else it is refused with reason `no_kvm`. This is a refusal on cost, not a downgrade: the user can choose `private`. `guest` is not practical on a rented virtual server with no nested virtualization when the work is a build.

### 7.6 The sentence and the residual
At shield `guest`, no file name, file content, argv value, environment value or terminal byte of the run appears in a file of the host, in the argv, environment or open files of a host process, or in plaintext on a host interface; the only copy of the run's plaintext on the host is the memory of the QEMU process.

A root user can read the guest memory through the QEMU process, can dump it with QMP, can read it from swap, and can start a fake guest in place of the real one. podswarm cannot detect this at `guest`. The inner channel protects against a passive copy of the relayed bytes only.

Tests of file 23: E-19 canaries at `guest`, E-20 refusal with `no_kvm`, E-21 no network card in the guest.

## 8. Shield `sealed`

### 8.1 Platform floor (SEV-SNP first)
* CPU: AMD EPYC 7003 or later, with SNP on in the BIOS and the firmware.
* Host: Linux 6.11 or later with `kvm_amd` SNP on; QEMU 9.1 or later; access to `/dev/kvm` and `/dev/sev` (root in practice). A user who is root on the machine can launch it when the BIOS has SNP.
* Probe (a hint only, section 9): `/sys/module/kvm_amd/parameters/sev_snp` is `Y`, `/dev/sev` opens, `qemu-system-x86_64 --version` is 9.1 or later.
[EV-064]

### 8.2 The measured guest set
Each podswarm release ships a guest set: an OVMF build of the `AmdSev` package (stateless, because NVRAM is not measured), a guest kernel, and an initramfs that holds only the static podswarm binary and an init. The build is reproducible. The signed `SHA256SUMS` of the release covers the three files (file 16). The podswarm binary embeds their hashes. The kernel has no IA32 emulation (`CONFIG_IA32_EMULATION=n`), no module load after boot, and only virtio-serial, virtio-blk, the SEV guest driver and configfs-tsm. The fixed, measured command line holds `ia32_emulation=0`. Restricted interrupt injection or Secure AVIC is turned on when the kernel and the hardware have it.

### 8.3 The attestation flow
1. **Expected value.** The home computes the launch measurement for (vCPU count, vCPU type, VMM type `QEMU`) and the guest set with the `measurement` module of the `sev` crate, and caches it per tuple. It never takes this value from the host.
2. **Launch.** The relay starts QEMU with `-machine confidential-guest-support=sev0 -object sev-snp-guest,id=sev0,cbitpos=N,reduced-phys-bits=1,policy=0x30000,kernel-hashes=on`, the guest set, `-nic none`, one `virtserialport` and one raw disk. It sends nothing secret.
3. **Challenge.** The home sends a 32-byte random nonce `n` through the relay.
4. **Report.** The guest podswarm makes an ephemeral Ed25519 key pair at boot. It writes `SHA-512("podswarm-seal-1" || n || guest_public_key)` (64 bytes) to `inblob` of a configfs-tsm report, reads `outblob` and `auxblob`, and sends `{report, certs, guest_public_key}`. [EV-065]
5. **Verify, on the caller.** Each check must hold, else the session ends with reason `attestation_failed` and the name of the field:
   * signature chain: the ARK of the product (Milan, Genoa, Turin; pinned in the binary) signs the ASK (or ASVK for a VLEK), which signs the VCEK (or VLEK), which signs the report (ECDSA P-384);
   * `MEASUREMENT` equals the value of step 1;
   * `POLICY`: debug off, migration agent off; SMT only when `seal_smt = true`;
   * `REPORT_DATA` equals the hash of step 4;
   * `VMPL` is 0;
   * `REPORTED_TCB` is at or above the floor table of this release (8.7), else reason `tcb_below_floor` with the component;
   * `HOST_DATA` and `ID_BLOCK` are set by the host and are ignored;
   * `CHIP_ID` equals `seal_chip` when the pool entry has one. The home writes it at the first verified launch, so a move to another chip is seen.
6. **Bind.** The home completes the inner channel (7.4) with `guest_public_key` as the server's raw public key. Only then does it send the view, secrets and `K_host`.

### 8.4 What the caller fetches and caches
* ARK and ASK of each product: embedded in the binary. A release updates them.
* VCEK: first from `auxblob` (the host supplies it; the chain check makes that safe). Else from the caller's cache, keyed by (`CHIP_ID`, `REPORTED_TCB`). Else one GET from the caller to `https://kdsintf.amd.com/vcek/v1/{product}/{hwid}?blSPL=..&teeSPL=..&snpSPL=..&ucodeSPL=..`.
* CRL: `https://kdsintf.amd.com/vcek/v1/{product}/crl`, fetched when the caller is online, cached, and checked when present. An offline caller with the VCEK in its cache verifies everything except revocation, and the report says `crl: stale` with the age.
* VLEK: only from `auxblob`; it chains to the ASVK.
* Crate: `sev` with `default-features = false, features = ["snp", "crypto_nossl"]` (pure Rust P-384, RSA, SHA-2, X.509). Guard G-15 of file 23 checks the static musl link. The crate `pod-attest` is ask P-19 (file 21).

### 8.5 TDX, the second backend
TDX needs Linux 6.16, QEMU 10.1, the TDX module, and a Quote Generation Service with SGX and a PCCS on the host. That is host setup that the first use case does not want, so TDX follows SNP. The guest set then moves to one IGVM file for both. The caller verifies a quote with `dcap-qvl` (pure Rust) and caches the collateral (TCB info, QE identity, CRLs) until its `nextUpdate`. [EV-066]

### 8.6 What is not possible
* **Arm CCA.** The guest side is in Linux 6.13; the KVM host side and QEMU Realm support are not merged. [EV-067]
* **A confidential guest inside a rented cloud VM.** The large public clouds give no nested virtualization on their confidential VM types, and the one that offers SNP child guests does so only through its managed container service. A cloud confidential VM can itself be the `sealed` host when the user is its only root: the whole machine is the guest, attested by the cloud's own report. That is a later mode.
* **SGX enclaves for builds.** A library OS emulates `fork` by a new enclave per process, and a build starts a process per crate and per build script, at up to 1,000 times the native fork cost. Enclaves do not exist on AMD. They are not a rung.

### 8.7 Residual, the TCB floor and hardening
* **TCB floor.** The release carries a table per product of the minimum `REPORTED_TCB` (bootloader, TEE, SNP firmware, microcode SPL) that includes every vendor bulletin fix known at release. `--seal-tcb-floor ack-old` accepts an older TCB for a lab and prints the bulletin ids.
* **Residual.** `sealed` does not stop: a stop, a pause or a slow-down of the guest; side channels (page-fault patterns, cache timing, the sizes and times of relayed bytes and of disk writes); attacks below the TCB floor that the vendor has not fixed; a malicious interrupt attack for which SNP has no fix yet; and a person with physical access to the memory bus. [EV-068]

### 8.8 The sentence and the tests
At shield `sealed`, the caller sends no file, key, secret or terminal byte to a guest before it has verified, on the caller, an SNP report whose signature chains to AMD, whose measurement equals the value the caller computed for the released guest set, whose report data binds the caller's nonce and the guest's channel key, and whose TCB is at or above the release floor; any other guest gets nothing and the run fails with a named field.

Tests of file 23: U-attest (a valid report, each field flipped, another nonce, another guest key, the computed measurements); E-22 a real launch; E-23 a changed initramfs; E-24 a plain KVM guest with an old report; E-25 reads of guest RAM; E-26 refusal with `no_snp`.

## 9. No downgrade, and what a probe is worth

A run that asks for shield N on a machine whose `shield.max` is below N fails with exit 79 and the error `shield_unavailable{asked, max, reason, field?}` (class Policy, file 05). The run never starts at a lower level. Reasons: `no_memory_area`, `no_sealed_area` (6.2), `swap_not_locked`, `no_kvm`, `no_qemu`, `qemu_too_old`, `no_snp`, `attestation_failed` (with `field`), `tcb_below_floor` (with `field` = the component).

The worker sends its shield rows in `hello.caps.shield`. `podswarm doctor HOST --shield` prints them with one line per level: `available`, `available, claimed`, or the refusal reason.

| Row | Values |
| --- | --- |
| `max` | the strongest level the worker can give now |
| `area` | the first area rung that works, or `none` |
| `swap` | `none`, `locked`, `possible` |
| `memfd_secret`, `userns`, `cgroup_swap`, `fuse`, `kvm` | `yes` or `no` |
| `qemu` | version or `none` |
| `snp` | the `kvm_amd` parameter and whether `/dev/sev` opens |
| `tdx` | `yes` or `no` |
| `hidepid` | the mount option of `/proc` |
| `other_root` | the count of uid 0 accounts and of members of `sudo` and `wheel`, for information |

What a probe is worth:
* At `private` and `guest` the probe and the report come from host software that a root user can change. The run report marks them `mode: claimed`. The claim is still worth having: it is true on a machine whose root users do not attack podswarm, which is the first use case of file 01.
* At `sealed` the probe is a hint for placement only. The attestation of 8.3 is the proof, and the report marks it `mode: attested`.

## 10. Interplay with other features

* **View (file 06).** At `private` the plaintext of the view is only in the area and the page cache. At `guest` and `sealed` the view client runs inside the guest, and the view cache is decrypted only inside the guest.
* **Warm state.** The store of 6.4 is the same at every level from `private`. At `guest` and `sealed` it lives on the guest's raw disk and the guest holds `K_host`.
* **Spreading (file 07).** The shield of a session is the minimum level that every member machine meets. Placement of a spread process filters by `shield.max >= session shield`. A machine below it is not used, never used with a warning.
* **Checkpoints (file 15).** A checkpoint records the shield of the attempt that made it. A restore goes only to a machine at that shield or higher. At `private` and above the checkpoint directory and its cached blobs stay in the work area (file 15, section 11.11). A checkpoint leaves the machine as plaintext unless `checkpoint.encrypt = "run"` (file 15, section 11.10). In a session the home sends the run data key to the worker of the attempt over the link, as it sends `K_host`, and the worker holds it in memory only. In a swarm the worker asks a home of the submitter for the key at each attempt that writes or restores a checkpoint, and the home checks the shield report of this section before it answers (file 15, section 11.10); `--key-escrow` lets the coordinator answer and read the checkpoints (file 16, section 18.1) (D-126). A process checkpoint (file 07, a later rung) holds the whole memory of a process and is always encrypted under such a key. At `sealed` a restore needs a fresh attestation of the target.
* **Secrets (`secrets.1`, file 24).** A secret has `min_shield`, default `private`. The home releases it only to an attempt at or above that level, as a file in the area. On a machine with `trust = "shared"` below `sealed` the CLI prints once per session: `secret NAME is readable by root on HOST`.
* **Network (file 14).** At `private` the host's interfaces carry the run's traffic. With a podnet tunnel exit, `tcpdump` on the host sees only the tunnel's packets, sizes and times; the tunnel key is in worker memory (R2). At `guest` and `sealed` the guest has no network card: the run's connections are streams in the inner channel to the exit of the network policy. When that exit is this same machine, the host sees the destinations and the report says `net_exit: this_host`.
* **Logs.** At `private` and above nothing is logged on the host (6.6).
* **Outputs.** They go back to the caller through the view or the sync of file 06, so no output file stays on the host.
* **The copied binary.** Section 6.7.

## 11. Settings and the run report

| Setting | Scope | Values | Default |
| --- | --- | --- | --- |
| `--shield`, `needs.shield`, pool `shield` | run, shape, machine | `none`, `private`, `guest`, `sealed` | from `trust` (section 4) |
| pool `trust` | machine | `own`, `shared` | `shared` |
| `--force-lower` | run | flag | off |
| `--shield-require swap-locked`, pool `shield_require` | run, machine | list of `swap-locked` | empty |
| `area_max` | machine | MiB, 64 to the host RAM | 50 percent of `MemAvailable` |
| `--area`, pool `area` | run, machine | `auto`, `memory`, `sealed` | `auto` |
| `--no-cache`, pool `cache` | run, machine | bool | true |
| `--no-trace`, pool `leftovers` | run, machine | `bin`, `none` | `bin` |
| `--allow-tcg`, pool `guest_tcg` | run, machine | bool | false |
| pool `seal_smt` | machine | bool | true |
| pool `seal_chip` | machine | hex `CHIP_ID` | written at the first verified launch |
| `--seal-tcb-floor` | run | `release`, `ack-old` | `release` |
| `--env-allow` | run | name list | empty |
| secret `min_shield` | secret | a level | `private` |

```toml
[host.build]
road = "ssh://build.example"
trust = "shared"
shield = "private"
cache = true
leftovers = "bin"
guest_tcg = false
seal_smt = true
```

The run report carries `shield{asked, got, mode, area, swap, cache, store, left, net_exit?, measurement?, tcb?, crl?}`. `mode` is `claimed` or `attested`. `area` is a rung of section 6.2, or null at shield `none`. `cache` is a bool (the pool key `cache`). `store` is `warm`, `cold` or `discarded`. At `sealed`: `measurement` is 96 lowercase hex (the 48-byte launch measurement), `tcb` is 16 lowercase hex (the 64-bit `REPORTED_TCB`), and `crl` is `ok`, `stale` or `absent`.

## 12. What the first release has

Milestones are those of file 22.
* M1, with `podswarm run HOST -- cmd`: the credential rules of section 5 in full; `private` with the rungs `ramfs-ns`, `tmpfs-noswap` and `runtime`; the `swap` row and `memory.swap.max = 0` where the `cgroup` rung exists; keys in `memfd_secret`; removal and the start-time sweep of 6.8; no host logs; warm state within one session (the holder keeps the worker and its area between commands); the probe rows, the report fields, `shield_unavailable`; the default `private` for remote machines; boundary `none`. Known limit: each owned directory is in memory, so a build directory larger than its share of `area_max` ends with `area_full`.
* M2: the sealed store across sessions (6.4), the mismatch check, the swap and store tests, and the `sealed-fuse` rung when the view uses FUSE; the placement of owned directories and the setting `area` (6.2).
* M7: boundary `confined` (file 12, section 17).
* M8: `guest` (section 7) and the inner channel; `sealed` on SNP; then TDX.
* With no milestone yet: the cloud confidential VM as the whole guest.
* Later (file 24): `--check-on` with `verify.1`; it moves into M9 when `verify.1` ships, and file 18 gains the flag with this item.

The asks of podvm and podcrates that `guest`, `sealed` and the probe rows need are in file 21 (V-7, P-6, P-18, P-19).
