# 16. Security: identity, admission and limits

This file defines who may make a machine run a command, how each party proves who it is, what each party may do, and the limits that hold before and after admission. File 04 has the roads, the link and the `hello` and `ready` messages. File 13 has the two protection axes: boundary (the host against the task) and shield (the task and the caller against the host). File 12 has the containment of an attempt. File 06 has the view. File 17 has plugins, the agent face and the run identity token.

## 1. The central fact

An authority runs commands on workers. A worker serves its machine to an authority. A caller exports files to a worker. That is the product. So:

* Whoever controls an authority controls every worker that serves it, up to the boundary of each attempt (file 13).
* Whoever may submit to a coordinator controls what its workers run, inside the routes and quotas of the submitter.
* Whoever controls a worker machine sees the attempts and the files that reach it, down to the shield of each attempt (file 13).

The model is not "workers are safe from tasks". It is: each party gets the power that it holds a key or a road for, and no more.

podswarm sends no telemetry. A process opens a connection only to a road, a coordinator, a URL input, a webhook or a release URL that a user or an operator named.

## 2. Parties and trust

### 2.1 A session

| Party | Trusted to | Not trusted to |
| --- | --- | --- |
| Caller (the user, the home, the holder) | everything that the caller's own account can do | nothing beyond its account |
| Far machine reached by a self-authenticating road (`ssh`, `podssh`, `exec:`) | run the attempts that the home sends, as the caller's own account there | not to read or change the attempt: that is the shield (file 13) |
| Other users of the far machine, root included | nothing | reach the far worker, its sockets or its files; root can, down to the shield |
| The network between caller and far machine | carry bytes | nothing; the road (ssh) gives confidentiality and integrity |

### 2.2 A swarm

| Party | Trusted to | Not trusted to |
| --- | --- | --- |
| Operator (owns the coordinator host and its uid) | run and administer the swarm; holds the coordinator key and the local socket | nothing beyond the host; a compromise of the host is a compromise of the swarm |
| Submitter (a key in `submitters`, or a member by statement) | submit and manage its own runs inside its scopes, routes and quotas | target a worker outside its routes; see or change another submitter's runs, blobs or outputs; exceed a quota |
| Worker that dials out (`podswarm join`) | run the attempts it is offered, report honestly | read task data or keep results true: a worker is a claim (section 20, X-14) |
| Worker owner | run the worker | read task data: not prevented below shield `guest` (file 13) |
| Organisation key holder | sign member statements that cells trust | add a member to a cell that does not list the key |
| Hub (extension, file 24) | forward bytes | read or change them; TLS runs end to end through it |
| Network | carry packets | nothing; assume interception, replay and injection |
| Task code | run | leave its boundary (file 13) |

## 3. Threat table

| Asset | Attacker | Answer |
| --- | --- | --- |
| Commands run on workers | network attacker | TLS 1.3 with the coordinator pin and the client key in the handshake (section 4); ssh on a self-authenticating road |
| Commands run on workers | thief of an invite token | uses, expiry, `--approve`, `worker_ttl`, cascade revoke (section 7) |
| Commands run on workers | hostile coordinator | worker policy (section 12); signed shapes are an extension (file 24) |
| Commands run on workers | submitter outside its scope | `routes`, scopes (section 8) |
| Worker host and worker key | task code at boundary `none` | `PR_SET_DUMPABLE 0` (file 12); a separate worker uid; nothing more |
| Worker host and worker key | task code at boundary `confined` | Landlock paths, signal scope, seccomp, `AF_UNIX` closed below ABI 9 (file 12) |
| Coordinator admin | a process of the coordinator uid | none; run the coordinator as its own user; a worker refuses that uid (section 10) |
| Session holder | a process of the caller uid | none; a confined local attempt cannot reach the socket (section 5.3) |
| Task data and the caller's files | root or another user of the far machine | shield `private`, `guest`, `sealed` (file 13); credential rules (section 18) |
| The caller's files outside the workspace | the far worker | the view serves only the workspace and its deny list (file 06) |
| Result integrity | lying worker | none in the core (stated); one accepted result per task (file 09); `verify.1` (file 24) |
| Submitter's or caller's disk | hostile worker through output paths | the path rule at accept and a write beneath the target (section 13) |
| Submitter's tasks | fake coordinator | the coordinator pin in the connect string (section 8.4) |
| Coordinator availability | unauthenticated flood | absolute pre-auth caps, stage deadlines, eviction by stage (section 14); residual: volume |
| Coordinator availability | a submitter or a worker | quotas by tasks and by bytes, wire limits (section 15) |
| Binaries on far machines | compromised release channel | signed `SHA256SUMS` checked by the binary (section 16) |
| Metadata | network or hub | none: sizes, timing, addresses (stated) |

## 4. Identity on a `wss` road

### 4.1 Keys and certificates

* Each worker and each submitter has one Ed25519 key, stored by `pod_identity::file` at mode 0600. A file with a wrong mode is refused and never replaced. The key is made at the first `podswarm join` or `podswarm key new`.
* A `wss` road always uses mutual TLS. No client connects with a pin and no client certificate.
* The client presents its key as a self-signed X.509 certificate in the TLS 1.3 handshake. The client makes the certificate in memory at each process start from its key. The CertificateVerify signature proves possession of the key for this handshake.
* The coordinator has an Ed25519 `pod-identity` key in its state directory at mode 0600, the key type of each worker and each submitter (D-129). It presents the key as a self-signed certificate. This key serves TLS only. The token key of the run identity is separate (file 17).
* A pin is a `pod_identity::KeyName`. Files, tokens and connect strings hold the `SHA256:` fingerprint of `PublicKey::fingerprint` (section 4.3). No other key type and no other pin form exist on a `wss` road.
* TLS 1.3 only. No session tickets, no resumption, no 0-RTT. ALPN: none (a WebSocket upgrade). Cipher order and paths: file 04.
* There is no in-band signature exchange. No nonce, no challenge message and no transcript signature exist above TLS. The identity of both ends is the TLS handshake.
* **Channel binding.** No proof above TLS exists, so no proof needs a binding to the TLS session. Each end signs the transcript of this one TLS 1.3 session in its CertificateVerify. A relay that holds the coordinator key ends the TLS of the client and must open a second session to the coordinator; there it needs the client's private key, so it cannot act as the client (X-03). A thief of the coordinator key can act as the coordinator to a client that reaches it first (X-09).

### 4.2 What the client checks

The client dials with `pod_tls::peer::client_config` and its pin set (`pod_tls::peer::Keys`): the leaf holds an Ed25519 key that a pin names, and the TLS 1.3 handshake signature verifies with that key itself. A pin check without the signature check accepts anyone who copies the public certificate. A coordinator of another key fails the handshake, and `pod_tls::peer::refusal` gives the key that it proved, for the error text. [EV-081]
The client ignores names and dates in a pinned certificate. A client with no pin does not connect: a coordinator with a certificate of a public CA is a later item (file 24). A client never pins a key that it did not get from a token, a connect string or `ready.pins` (section 4.4).

### 4.3 What the coordinator's verifier accepts

* Client authentication is mandatory. The verifier accepts a chain of exactly one certificate whose key is Ed25519 and whose CertificateVerify signature verifies. It ignores names, dates and extensions. It refuses every other key type. This is the enrolment mode of `pod_tls::peer::server_config` (ask P-3, file 21).
* After the handshake the coordinator reads the key with `pod_tls::peer::peer_key`, computes its fingerprint (`SHA256:` plus base64 of the SHA-256 of the 32-byte key, the form of `pod-identity` and OpenSSH) and maps it by the path of the upgrade [EV-082]:

| Path | Key found | Key not found |
| --- | --- | --- |
| `/v1/w` | the `workers` row: `active` and `draining` get a session; `pending` gets a session with no offer; `revoked` gets `err{revoked, fatal}` | only `hello` with `enrol` (section 7.4) or with a statement of scope `worker` (section 9); else `unauthorized` |
| `/v1/s` | the `submitters` row: a session with its scopes | only `hello` with a statement (section 9); else `unauthorized` |

* A key that is in both tables acts only in the role of the path.
* The local socket (section 10) has no TLS. The embedded link of a session in one process has no TLS.

### 4.4 The pin set and its rotation

* A worker stores the pin set from its token, a submitter from its connect string, in a 0600 file of its state or config directory. A set holds at most 4 pins.
* Rotation adds first and removes late. The coordinator sends `ready.pins` with the new and the old pin while the old key is live. The client adds each new pin. It removes a pin only when the coordinator presented another key of the set in a later handshake, and at least 24 hours after the client first stored that other key. A `ready` can never shrink the set at once.
* Reason: a thief of the coordinator key who reaches a client first cannot push the real key out of the set.
* After a theft of the coordinator key, the operator makes a new key and a new token or connect string, and each client takes the new set from it (`podswarm join --repin`, file 18). A client never takes a pin set that removes pins from any other source.
* A person compares a pin or a key in the display form of `pod_identity::DisplayFingerprint` (five groups of eight base32 characters with a checksum). Files and the wire use the `SHA256:` form.

## 5. Identity on a self-authenticating road

### 5.1 The road is the proof

A road that authenticates both ends by itself (`ssh`, `podssh`, `exec:`, `local`) carries no TLS and no podswarm key exchange. The caller's ssh client proved the host key, and sshd proved the caller's account. So:

* The far worker belongs to the caller for the session. It runs as the caller's account on that machine.
* The far worker takes commands only from the stream of the road that started it. It listens on no network port.
* No other caller can use it. Another account on that machine reaches it only through its reattach socket, which refuses (section 5.2).
* There is no invite, no enrol and no pin. The worker number is given by the home for the session (section 6).
* At shield `guest` and `sealed` an inner TLS channel ends inside the guest (file 13).

### 5.2 The reattach socket of a far worker

When a road cuts, the far worker keeps its attempts and listens on a Unix socket in its runtime directory (directory 0700, socket 0600). The worker accepts a connection only when the peer uid (`SO_PEERCRED`, `getpeereid`) equals its own uid. The first frame of the joining stream carries a 32-byte random attach secret that the worker sent to the home on the original link; the worker compares it in constant time and closes the socket on a mismatch (D-16). A process of the same uid that cannot read the worker's memory cannot take the session. The worker calls `PR_SET_DUMPABLE 0` (file 12), so a process of the same uid cannot read the secret from memory.

### 5.3 The holder socket

The holder (file 04) listens on a Unix socket in the caller's runtime directory (`$XDG_RUNTIME_DIR/podswarm/`, else `/tmp/podswarm-<uid>/`; directory 0700 and owned by the uid, else refused; socket 0600). It checks the peer uid at each connection. A process of the caller's uid can drive the holder, and through it every machine of the session: this is the same power that an ssh control master gives. A local attempt at boundary `confined` cannot connect to the socket (`AF_UNIX` rule, file 12). A local attempt at boundary `none` can. The holder does not pass its socket path to an attempt (`PODSWARM_*` is on the variable deny list, file 13, section 5).

## 6. Worker identity and worker numbers

* In a swarm, a worker's identity is its Ed25519 public key. Its number `wid` (u32) is given at enrol from the `workers` table, is unique, and is never reused. The key column is unique (file 11).
* In a session, the home gives each link a `wid` from 1. It is not stored.
* A worker keeps its key, its pin set, its `wid` and the swarm id in a host-unique state directory, held by an `flock` (file 12). A copy of that directory on a second machine is a duplicate identity: the rule of file 04 marks the worker `suspect`, and the event `dup_identity` records it. Two live holders of one key are evidence of theft.
* `podswarm join` prints the `wid` and the key fingerprint on stdout. `podswarm workers ls --pending` prints the fingerprint in display form, the address and the requested tags, for comparison before `approve`.
* Capabilities and tags that a worker reports are claims. The coordinator grants tags only as the invite rules allow (section 7.3). A worker that lies about capacity gets tasks it fails; that is a failure, not a breach.
* Key rotation is an extension (file 24). In the core, a worker changes its key by an enrol with a new invite, and the operator revokes the old `wid`.

## 7. Invites

### 7.1 The token

`podswarm invite new` makes an invite and prints a token: `psw1.` followed by base64url (no padding) of one JSON object:

```json
{"c":["coord.example.net:443"],"a":["192.0.2.7"],"k":"SHA256:BASE64FINGERPRINT43","i":"4f2a9c01d3b7e650","s":"BASE64URL16BYTES","w":"BASE64URL16BYTES","x":1794086400}
```

| Field | Meaning |
| --- | --- |
| `c` | coordinator addresses `host:port`, tried in order |
| `a` | optional IP addresses of the first host, used when the system resolver is absent or fails (Android without `/etc/resolv.conf`) |
| `k` | the coordinator pin: the `SHA256:` fingerprint of its Ed25519 key; present in every token |
| `i` | invite id, 16 lowercase hex characters |
| `s` | the invite secret, 16 random bytes, base64url with no padding |
| `w` | the swarm id, 16 random bytes made when the store is made, base64url with no padding; `ready.swarm` carries the same bytes as 32 lowercase hex (file 04) |
| `x` | expiry, unix seconds |

### 7.2 The verifier

The coordinator never stores `s`. It stores the verifier: the Ed25519 public key whose 32-byte seed is `HKDF-SHA-256(ikm = s, salt = empty, info = "podswarm-invite-1")`. A stolen store or backup holds no usable credential. Offline guessing of `s` costs 2^128.

### 7.3 Uses, expiry and rules

| Rule | Default | Effect |
| --- | --- | --- |
| uses | 1 | enrols left; one is spent by the statement of file 11 in the transaction that inserts the worker row |
| expiry | 1 hour | the coordinator checks it with its own clock; the worker checks `x` only to refuse an expired token before it dials |
| `tags` | none | the tags a worker may get; granted tags are the requested tags that the rule allows; reserved cell tags (file 08) come only from here |
| `max_cores`, `max_slots` | the worker's values | caps on what the worker may declare; a larger declaration is clamped |
| `max_boundary` | none | the highest boundary the worker may offer to tasks |
| `approve` | off | the worker enrols as `pending` (W1, file 09) and gets no offer until `podswarm workers approve` |
| `worker_ttl` | none | the worker becomes `revoked` this long after its enrol |
| `ephemeral` | off | the worker exits when idle (file 10), and its row becomes `revoked` after 600 s with no session |

Use `approve` when the token travels over a channel that you do not control. `podswarm invite new` prints a warning when `uses` is above 1 and `approve` is off. `podswarm invite revoke ID` stops the invite. `--cascade` also revokes every worker that enrolled with it (W6, file 09).

### 7.4 Enrol

The worker sends `hello` with `enrol{invite, proof, name?}` (file 04) on `/v1/w`, with its own key in the handshake. `proof` is the Ed25519 signature by the invite key, base64url with no padding, over:

```
"podswarm-enrol-1" 0x00 || swarm_id (16 bytes) || client_key (the 32 bytes of the Ed25519 key)
```

The coordinator checks, in this order, and answers one error `unauthorized` for every failure:
1. The client key has no `workers` row. A key with a row is a known worker (section 4.3): when the row's `invite_id` equals `enrol.invite`, the coordinator ignores the `enrol` and answers `ready` with the same `wid`, and spends no use; this makes a retry after a lost `ready` idempotent. When the row has another invite, the enrol is refused, and the event `enrol_refused` records the key.
2. The invite exists, is not revoked and is not expired.
3. `proof` verifies with the stored verifier.
4. The use update of file 11 changes one row.
Then the coordinator inserts the worker row and answers `ready{wid}`. A connection that fails before `ready` spends nothing. A failed enrol counts against the source prefix (section 14).

### 7.5 Token handling

* A token is a secret. It never goes into argv, a log, an error text, a URL or stderr.
* `podswarm invite new` writes the token to a file that it creates with `O_EXCL` at mode 0600, or to stdout when the user asks for stdout.
* A command reads a token from `@FILE`, from stdin (`-`), or from a descriptor (`--invite-fd N`). A token given as a plain argument is refused with exit 64.
* A detached worker gets the token on an inherited pipe (`--invite-fd`), and the parent closes its end.
* `PODSWARM_INVITE` is read only on the batch launcher path (file 18). The worker reads it once, removes it from its environment, and never passes it to a task. The initial environment block of the process stays readable by the same uid until exit; the docs say so.
* The worker deletes the token from memory and from disk after a successful enrol.

## 8. Submitters

### 8.1 The `submitters` table

The `submitters` table of the store is the truth (file 11). There is no submitter file. `podswarm submitter add|ls|rm` edits the table through the local socket, or through a session of a key with `admin`. `add` takes a public key or a fingerprint, a name, the routes, the scopes and the quotas. A removed key loses its open sessions within 5 s. The local user of the coordinator host needs no key.

### 8.2 Scopes and routes

Scopes are the operations a key may use:

| Scope | Operations (file 05) |
| --- | --- |
| `read` | `ls`, `show`, `watch`, `logs`, `blob_get`, `blob_have`, `ckpt_ls`, `ckpt_show`, `usage`, `status`, `version`, for its own runs |
| `submit` | `submit`, `run_new`, `run_close`, `cancel`, `retry`, `update`, `attach`, `blob_put`, `ckpt_save`, `ckpt_pin`, `ckpt_rm`, `ckpt_export`, `ckpt_import`, for its own runs; `secret_*` of file 24 for its own secrets |
| `id` | run identity tokens for the audiences of its `id_aud` patterns (file 17); off by default |
| `admin` | every run; `invite_*`, `worker_*`, `submitter_*`, `gc`, `usage` of every run, organisation trust with `org_add`, `org_ls`, `org_rm`, `org_revoke` (sections 9.3, 9.4) |
| `verify` | set the shape field `verify` (file 24); off by default |

A key that `submitter add` makes has `read` and `submit`, unless the command names other scopes.

`routes` is a list of tag selectors `K:V`, or `*`. A task of the key is matched only to a worker that carries at least one tag of `routes`; `*` matches every worker; an empty list matches none. The coordinator adds the rule to the fit of file 10, and the task cannot name a worker outside it. Another submitter's run, blob or output answers `not_found`, the same answer as an absent one.

### 8.3 Quotas

| Quota | Default | Counted at |
| --- | --- | --- |
| `max_queued` | 100,000 | submit: non-terminal tasks of the key |
| `max_spec_bytes` | 1 GiB | submit: shapes and task records of the key that the store holds |
| `max_output_bytes` | 4 GiB | result accept: inline output and output records of the key's tasks |
| `max_blob_mib` | 10,240 | `blob_put`: each owner pays the full size of each blob it owns (file 15) |
| `max_ckpt_mib` | file 15 | checkpoint commit: the checkpoint bytes of the key (file 15) |

A spent quota answers `quota` with `scope`, `limit` and `used` (file 05). The local user has no quota. An admission plugin can refuse more (file 17).

### 8.4 The connect string

`podswarm submitter add` prints a connect string: `psw1s.` followed by base64url of `{"c":[ADDR...],"k":PIN,"w":SWARM_ID}`. It holds no secret. The submitter stores it in its user config. A command refuses a remote coordinator that has no pin. The pin set of a submitter rotates by the rule of section 4.4.

## 9. Organisation statements

An organisation key signs a statement that makes a member key valid in each cell that trusts the organisation key. The member key stays the proof of possession: it is the TLS client key of the session. A coordinator alone cannot add a member.

### 9.1 The form

A statement is `{"doc": TEXT, "key": HEX, "sig": BASE64}`, the form of `pod-relay` `pool/signed.rs`. `doc` is the exact signed text, `key` is the organisation's Ed25519 public key, and `sig` is the signature over `LABEL || TEXT`, in standard base64 with padding, as that crate writes it. No canonical form exists: the verifier checks the bytes of `doc`, then parses them. [EV-083]

```
LABEL = "podswarm-member/1\0"
TEXT  = {"podswarm-member":1,"member":"SHA256:<fingerprint of the member key>","name":"alice","scopes":["submit","read"],"cells":["eu1"],"juris":["eu"],"serial":17,"issued":1794000000,"not_after":1794604800}
```

TEXT is one line of JSON with this field order. It has at most 2,048 bytes, so a `hello` that carries it stays under the pre-auth cap of file 05. `cells`, `juris` and `max_queued` are optional. `scopes` uses the names of section 8.2, plus `worker` for a worker that joins with a statement in place of an invite. The label serves no other use of the key.

### 9.2 The checks of a cell

The client sends the statement in `hello.stmt` (file 04). The coordinator accepts it only when every check holds; each failure answers `unauthorized`:
1. `key` is an organisation key that this cell trusts (section 9.4).
2. `sig` verifies over `LABEL || doc` with `verify_strict`. A form number other than 1 answers `unsupported`.
3. `member` equals the fingerprint of the TLS client key.
4. `now + 300 >= issued` and `now <= not_after`. The life from `issued` to `not_after` is at most the trust entry's `max_life_s` (default 30 days).
5. When `cells` is present, it names this cell. When `juris` is present, it holds this cell's jurisdiction label (file 08).
6. `serial` is at least the floor that the cell keeps for this member of this organisation.
7. The scope of the path holds: `worker` on `/v1/w`, any other scope on `/v1/s`.
Granted scopes are `scopes` intersected with the trust entry's `max_scopes`. `admin` is granted only when the trust entry sets `allow_admin`. A quota in the statement can only lower the cell's quota for the member. On the first accepted statement the coordinator makes a `submitters` row (or a `workers` row for scope `worker`) with source `org`. Only a revoke changes that row. Routes of a member come from the trust entry's `routes`.

### 9.3 Revocation

A statement lives at most `max_life_s`. `podswarm org revoke MEMBER` on a cell raises the serial floor of that member above every serial seen, so each statement issued before it is refused; it also closes the member's sessions. The organisation issues a new statement with a higher serial to restore the member. A signed revocation list from the organisation key is a later item.

### 9.4 How a cell trusts an organisation key

`podswarm org trust KEY --name N --scopes S --routes R --max-life D [--allow-admin]` adds a trust entry through the local socket or a key with `admin`. `podswarm org untrust` removes it and closes the sessions of its members. `podswarm org key new` makes an organisation key; `podswarm org issue MEMBER --scopes ... --cells ... --days N` prints a signed statement. The organisation key can live on an offline machine: only `issue` needs it.

## 10. The local socket of a coordinator

The coordinator listens on `coord.sock` in its runtime directory (file 19; directory 0700, socket 0600). It accepts a connection only when the peer uid equals its own uid. The peer then has every right of `admin` and no quota. So any process of the coordinator's uid is the operator:
* Run the coordinator as its own user.
* A worker refuses to start under the uid of a coordinator socket on the same host, unless `--same-user-as-coordinator` is given. The embedded worker of a session is exempt.
* A confined attempt cannot connect to a pathname Unix socket (file 12).
The coordinator does not read `/proc` of the peer to tell a task from the operator: the uid split is the control.

## 11. Configuration files

* podswarm reads a system file and a user file (file 19). The coordinator also reads its own config. The state directory and the config directory must be owned by the uid and not writable by group or others, else the process refuses to start.
* A file `.podswarm.toml` in the working directory, or in a parent up to the Git root, is written by whoever wrote the repository. It may set only:
  * the table `[defaults]`: settings of scope shape and run (file 19), such as `retries` and `timeout_s`; never a cell or a road;
  * a residency rule `[residency]` that restricts placement (file 08);
  * the table `[view]`, which can only add globs to `pull`, `keep` and `protect`, and lower the five view thresholds (file 06).
* A residency rule in a workspace file is safe because it can only intersect: the effective rule is the user config, intersected with every workspace file from the working directory up, intersected with the command line. A nearer file cannot widen a farther one. An empty result is a refusal (`no_cell`), never a fallback. A key that would widen or lower protection is an error that names the key: in `[defaults]` this includes `net = "home"`, `home=PORTS`, an `exit:` policy, and a `shield` or `boundary` below the user's (files 13, 14). Only `--ignore-workspace-rules` widens it, and it prints the file name (file 08).
* A workspace file never sets a road, a pool entry, a cell, a coordinator, a pin, a key file, a worker policy, a state directory, a listener, a hub, a hook, a plugin, an MCP profile, a view allow entry or the `trust` of a machine. Such a key is an error that names the file and the key.
* A workspace file that is not owned by the user, or is writable by group or others, is ignored with one warning line.

## 12. Worker policy

The worker policy is `worker.toml` in the config directory of the worker's user. The worker reads it at start and prints the effective policy with `-v`. The worker applies it before it starts an attempt. A refusal is `spawn_failed` with reason `policy` (file 05). A policy never changes a task in silence.

| Key | Type | Default | Effect |
| --- | --- | --- | --- |
| `allow_boundaries` | list of boundary names | every boundary the probe found | boundaries this worker offers |
| `allow_shell` | boolean | true | false refuses a shape with `shell` |
| `max_cores` | integer | the host's cores | cap of `needs.cores_m` per attempt, and of the slots the worker declares |
| `max_mem_mib` | integer | the host's memory | cap of `needs.mem_mib` per attempt |
| `env_pass` | list of names | [] | names of the worker's own environment that pass to an attempt (file 12) |
| `deny_env` | list of patterns | [] | names added to the variable deny list of file 13, section 5 |
| `net_allow` | list of CIDR prefixes and `host:port` rules | public unicast addresses | destinations of URL inputs (file 15); checked after DNS and at connect |
| `allow_abs_cwd` | boolean | false | accept an absolute `cwd` of a task with `shared_fs` |
| `allow_unix` | boolean | false | accept `confine.unix` (file 12) |
| `confine_allow_read`, `confine_allow_write`, `confine_allow_exec` | lists of absolute path prefixes | [] | an absolute `confine` path outside them is refused |
| `accept_submitters` | list of `SHA256:` fingerprints | [] (any) | refuse a task whose owner is not listed; the owner is the coordinator's claim unless the shape is signed (file 24) |
| `plugin_allow` | list of plugin names | [] | sinks the worker may start (file 17) |
| `require_signed_by` | list of fingerprints | [] | extension `sig.1` (file 24) |
| `max_spec_age_s`, `unsigned_boundary_min` | see file 24 | see file 24 | extension `sig.1` (file 24) |

A far worker of a session reads the same file from the far account's config directory. There the caller and the far account are one principal, so the file is a guard that the user sets for that machine (cores, memory, boundaries). `accept_submitters` and `require_signed_by` do not apply in a session. A coordinator has its own `net_allow` with the same syntax and default for webhook destinations (file 17).

## 13. The path rule

One rule holds for every relative path that crosses a link: `files[].path`, `outputs` globs, output paths that a worker reports, a relative `cwd`, a relative `confine` path, entries of an archive that the worker unpacks (after PAX and GNU long-name processing), entries of a checkpoint manifest (file 15), and file names of `--results`. A path is refused when any item holds:

1. It is not valid UTF-8, or it is longer than 1,024 bytes.
2. It is empty, starts with `/`, or ends with `/`.
3. A segment (split by `/`) is empty, is `.` or `..`, or is longer than 255 bytes.
4. It holds a byte below 0x20 or 0x7F.
5. It holds one of `\ : " < > |`, or `*` or `?` outside an `outputs` glob.
6. A segment ends with `.` or a space.
7. A segment, before its first `.` and in any case, is a Windows device name: `CON`, `PRN`, `AUX`, `NUL`, `COM0` to `COM9`, `LPT0` to `LPT9`.
8. The first segment, in any case, is `.secrets`, `tmp` or `.psw`.
9. Two paths of one task are equal after Unicode NFC and case folding.

An absolute `cwd` is not a relative path: a worker accepts it only with `shared_fs` and `allow_abs_cwd`.
Where it is checked: the authority at submit (the home in a session, the coordinator in a swarm); the worker before it stages, unpacks or reports; the coordinator at result accept, where an output path must also match a declared glob, else the result is refused with `bad_request`; the client before it writes. The client writes each file beneath the target directory with `openat2(RESOLVE_BENEATH | RESOLVE_NO_SYMLINKS)` on Linux, and with `O_CREAT | O_EXCL | O_NOFOLLOW` and a check of each component elsewhere.
The view resolves the names that the far side asks for under the workspace root with its own rules (file 06); items 2, 3 and 4 hold there too.

## 14. Pre-auth limits of a listener

A connection is pre-auth until `ready`. These limits hold on each listener of a coordinator. Loopback addresses get no exemption. A source prefix is /32 for IPv4 and /64 for IPv6.

| Limit | Default |
| --- | --- |
| `max_unauth`: pre-auth connections at one time | 1,024 |
| `unauth_per_prefix`: pre-auth connections of one prefix | 64 |
| TLS handshake complete | 5 s from accept |
| HTTP upgrade head | 3 s; at most 4 KiB and 32 header lines |
| first `hello` | 2 s after the upgrade |
| `ready` sent | 10 s from accept |
| `preauth_bytes`: buffers of all pre-auth connections | 64 MiB |
| failed handshakes and failed enrols per prefix | 20 per minute, then a ban of the prefix for 60 s |

* Before `ready` the WebSocket accepts no extension (`permessage-deflate` is refused), no fragmented message and no continuation frame, and checks masking. The message cap before `ready` is in file 05.
* When `max_unauth` or `preauth_bytes` is full, the listener evicts the connection in the earliest stage first (TLS not complete, then HTTP head, then `hello`), and the oldest within that stage. When nothing can be evicted, it refuses the accept.
* A ban refuses accepts of the prefix and writes one aggregated `ban` event per prefix per minute.
* Total connections: `max_conns` (file 10).
* Behind a hub (file 24) the limits per prefix apply per `peer` of the stream, and the address of the hub is never banned. The hub allowlist binds each coordinator key to one name (`name=`, `pod-identity` allowlist form).

What a peer learns before `ready`, and the bound of each:

| Oracle | What leaks | Bound |
| --- | --- | --- |
| The certificate of the coordinator | its pin and that it is a podswarm listener | none; the pin is public by design |
| A known or unknown client key | whether a key has a row | only for a key whose private key the peer holds (mutual TLS) |
| Enrol failures | nothing: one `unauthorized` for each failure (section 7.4) | invite ids of 16 hex characters; 20 failures per prefix per minute, then a ban |
| A statement on `/v1/s` | whether the statement passes the checks of section 9.2 | the peer must hold the member key; the same failure limit |
| The time of an answer | the step of section 7.4 that refused | the verifier compare is constant time; the failure limit |

## 15. Quotas and denial of service

By a submitter: the quotas of section 8.3; the wire limits of file 05 (a `submit` message at most 4 MiB, a shape at most 65,536 bytes); `fanout_max` for staged data (file 15); run weights and `max_running` (file 10); the store backpressure that delays `ack` (file 11).
By a worker: the credit windows of each stream and the spill cap of an attempt (file 12); the standing `pull` state, which grants no offer above the capacity the invite allows (`max_slots`, `max_cores`); the attempt wall deadline, which ends a row that a worker holds and never reports (file 09); the `hb` row cap (file 05); a worker upload is charged to the owner of the run. A worker that breaks a wire rule gets `err{bad_request, fatal}` and its session closes.
By either: one connection per worker identity (file 04); the pre-auth limits of section 14.

## 16. Release signing, `self fetch` and bootstrap checks

* Each release has `SHA256SUMS` and `SHA256SUMS.sig`. The signature is Ed25519 over `"podswarm-release/1\0" || content of SHA256SUMS`, made with an offline release key.
* The binary embeds the release public key and one backup key.
* `podswarm self fetch` downloads `SHA256SUMS` and its signature, verifies the signature with an embedded key, downloads the binaries, checks each SHA-256, and only then writes them into the binary cache. A failure leaves the cache as it is.
* Bootstrap over a road (file 04) sends only a binary from that cache or the running binary itself. The far side checks the SHA-256 with `podswarm self verify SHA256` (file 18) before it renames the file and at each start. A failed check stops the session with the expected and the found hash.
* A later `self update` uses the same check and refuses a lower version.

## 17. Rules for `ssh` roads

* The road runs the system `ssh` with `BatchMode=yes` for each connection after the first. Only the first connection to a host may prompt for a passphrase or a second factor, and only with a terminal.
* The user's host key checks stay as configured. podswarm never passes `StrictHostKeyChecking=no` or `UserKnownHostsFile`. A host with an unknown key fails with its fingerprint and the remedy.
* No agent forwarding and no other forwarding: `-a -x -o ClearAllForwardings=yes -o PermitLocalCommand=no -o RemoteCommand=none -o SendEnv=-*`. The user's config cannot add them. The full flag set is in file 04.
* The environment of the caller never travels as ssh variables. The environment of `podswarm run` crosses inside the protocol, minus the credential deny list (file 13); a queued task gets the shape `env` and the allowlist of file 12.
* A far worker of a session leaves the binary in its cache directory and the content cache (sealed or absent by the shield, file 13). `podswarm forget HOST` removes both. `--no-trace` removes them at the end of the session. It leaves no service, no key and no listener.
* `podswarm bootstrap` (a worker that joins a swarm) passes the token on the stdin of `ssh` to `podswarm join --invite-fd 0`, never in the remote command line.
* Workers that a run starts on hosts to join a coordinator use an invite with uses equal to the host count, the run's lifetime as expiry, and `ephemeral`; they keep their state in a temporary directory that they remove at exit; at the end of the run the coordinator revokes them by cascade (W6, file 09).

## 18. Credentials

At every shield level, `none` included, no credential of the caller travels by default: no agent forwarding (section 17); the view does not serve credential files and serves a filtered `.git/config` (file 06); secret-looking variables are not passed and are refused in `env_pass` unless named by `--env-allow` (file 13); a credential that a run needs goes as a file through `secrets.1` (file 24), never in the environment. File 13 holds these rules and what each shield level adds.

### 18.1 The data key of a run in a swarm

The data key of an encrypted checkpoint (file 15, section 11.10) is one symmetric key for the run and stays with the submitter (D-126). A worker asks for it with `ckpt_key_req` at each attempt that writes or restores a checkpoint, and a connected home of the submitter answers with `ckpt_key` after it checks the shield report of the worker (file 13). `--key-escrow` (run flag, default off) stores the key in the secret store of the coordinator (`secrets.1`, file 24), sealed under the master key, and the coordinator answers with the same check.

| Case | What the coordinator can read |
| --- | --- |
| No escrow | ciphertext, `key_id`, rounded sizes and times; the key passes it sealed to the link key of the worker |
| `--key-escrow` | each checkpoint of the run: a reader of the store and of the master key can unseal the key |
| Either case | nothing of a worker: the worker that runs the attempt holds the plain bytes and the key (file 13) |

Use `--key-escrow` only with a coordinator that you trust as you trust the data. Without it, a task waits in `held`, reason `needs_key`, while no home of the submitter is connected (file 15).

## 19. Security events

The `events` table (file 11) holds one row per event of this list. Text from a worker or a task is escaped and cut at 200 bytes. Rows of `auth_fail` and `ban` are aggregated per prefix and minute.

| Kind | When |
| --- | --- |
| `invite_new`, `invite_revoke` | an invite made or revoked (with `cascade`) |
| `enrol`, `enrol_refused` | a worker row made; an enrol of a key known under another invite |
| `approve`, `worker_revoke`, `worker_expire` | W3; W6 by an operator; W6 by `worker_ttl` or `ephemeral` |
| `auth_fail`, `ban` | failed handshakes or enrols; a prefix ban |
| `dup_identity` | two live holders of one worker key |
| `submitter_add`, `submitter_rm` | an edit of the table |
| `org_trust`, `org_untrust`, `member_admit`, `member_revoke` | section 9 |
| `admin_op` | another admin operation; the operation name, not its body |
| `policy_refusal` | a worker policy or a scope refused a task |
| `generation` | the generation step of file 11 |

## 20. Attack table

| Id | Attack | Control | Residual |
| --- | --- | --- | --- |
| X-01 | Eavesdrop on a `wss` link | TLS 1.3, no resumption | sizes and timing |
| X-02 | Man in the middle at first contact | the pin `k` in the token or connect string; pin and handshake signature checked | the channel that carries the token or connect string |
| X-03 | Relay a client's handshake to the real coordinator | the client's CertificateVerify covers its own handshake; a relay has two handshakes | none known |
| X-04 | Replay a recorded enrol `proof` | the proof binds the swarm and the client key; using it needs the client's private key | none known |
| X-05 | Steal an invite token | uses, expiry, `approve`, `worker_ttl`, cascade revoke, file at 0600 | the thief enrols until the uses or the expiry end |
| X-06 | Guess an invite | 128-bit secret, verifier only in the store, one error for every enrol failure, 16-hex ids, bans | none practical |
| X-07 | Enrol a known worker key under another invite | refused with `unauthorized` and `enrol_refused` | none known |
| X-08 | Steal a worker key | per-worker revoke; one session per identity; `dup_identity` | the thief acts as that worker until revoked |
| X-09 | Steal the coordinator key | key file 0600; a new key and a new token or connect string for each client | the thief can act as the coordinator to clients that hold the old pin |
| X-10 | Push a pin set that removes the real pin | add first, remove only after the other key is seen and 24 h passed | none known |
| X-11 | Clone a worker's state directory | duplicate identity rule (file 04), `suspect`, `dup_identity` | the two copies lose work until the operator acts |
| X-12 | A submitter targets a worker outside its scope | `routes` in the fit; scopes per operation | inside its routes it runs any command at the worker's boundary |
| X-13 | A submitter floods the queue or the store | quotas by tasks and by bytes, wire limits, backpressure | a key at quota still fills its share |
| X-14 | A hostile worker returns wrong results | one accepted result per task; `verify.1` (file 24) | wrong results of one attempt are not detected in the core |
| X-15 | A hostile worker writes outside the target through output paths | the path rule at accept, glob match, `RESOLVE_BENEATH` and `O_NOFOLLOW` at write | a defect in the checks; fuzz target |
| X-16 | A hostile worker wastes the coordinator | credit windows, spill caps, `max_slots`, attempt wall deadline, `hb` cap | bandwidth up to the limits |
| X-17 | A hostile worker reads task data | shield (file 13); routes keep tasks off untrusted workers | below `guest`, a worker owner sees the data |
| X-18 | A hostile coordinator sends hostile commands | worker policy; `sig.1` signed shapes (file 24) | without signed shapes, full control up to the policy |
| X-19 | A hostile co-tenant (root or another user) on a worker machine | shield `private`, `guest`, `sealed` (file 13); modes 0700 and 0600 | root reads memory below `sealed` (file 13) |
| X-20 | Another user of a far machine takes the reattach socket | modes, peer uid check, attach secret | root (X-19) |
| X-21 | A hostile far side asks the view for files outside the workspace or for credentials | the view root and deny list (file 06); credential rules (section 18) | files inside the workspace that hold secrets the deny list does not know |
| X-22 | Task code leaves its boundary | file 13 states what each boundary stops | `none` stops nothing |
| X-23 | A same-uid task attacks its worker (key, journal, `SIGSTOP`) | `PR_SET_DUMPABLE 0`, spawner fence, signal scope on `confined` (file 12) | at boundary `none` the task has the worker's power |
| X-24 | A task drives the coordinator's local socket or the holder socket | `AF_UNIX` rule on `confined`; a worker refuses the coordinator's uid | a local `none` attempt of a session can drive the holder (section 5.3) |
| X-25 | Path traversal in `files`, `outputs`, `cwd`, archives, checkpoints | the path rule of section 13 at each party | a defect in the unpacker; fuzz target |
| X-26 | Control characters from task output in a terminal or a log | captured output and logs show control characters as escapes (file 12) | an attached terminal of `podswarm run` passes bytes raw, as ssh does |
| X-27 | Pre-auth flood or slow handshakes | absolute caps, stage deadlines, byte budget, eviction by stage, bans | a distributed flood fills the pre-auth share |
| X-28 | Compression bomb or oversized frame | caps before and after `ready`, inflate cap, field caps (file 05), unpack caps (file 15) | none known |
| X-29 | Downgrade of TLS, protocol or features | TLS 1.3 only; `proto` range and features inside the authenticated link | none known |
| X-30 | A workspace file redirects a coordinator, a key or a policy | the workspace file sets only `[defaults]`, a residency rule that restricts, and `[view]`, which can only add globs and lower the five view thresholds (file 06) | a hostile rule can refuse runs in that directory |
| X-31 | A compromised release or a swapped binary in transit | signed `SHA256SUMS`, embedded keys, hash check at bootstrap and at each start | a theft of the release key until the backup key replaces it |
| X-32 | A spoofed ssh host or a user config that adds forwards | host key checks untouched, `BatchMode`, forwards cleared (section 17) | a user who accepted a wrong host key before |
| X-33 | Theft and replay of an organisation statement | the member key must be the TLS client key; short life; serial floor | the org key holder can issue to any key |
| X-34 | Theft of an organisation key | trust per cell with `max_scopes`, `max_life_s`, no `admin` unless allowed; `org untrust` | statements up to `max_life_s` until untrusted |
| X-35 | Server-side request forgery through a URL input or a webhook | `net_allow`, checked after DNS and at connect, public addresses by default | a URL with a credential in it is stored in clear |
| X-36 | Read a blob by knowing its hash | a hash is not a capability; one `not_found` for absent and not yours; a worker reads only blobs of an attempt it holds | none known |
| X-37 | Clock moved on a worker or the coordinator | fence and deadlines on monotonic clocks (file 05) | `not_before_unix`, `deadline_unix`, expiries and statements use the wall clock |
| X-38 | A plugin acts against its host | owner and mode check, content `id` pin, `plugin_allow` (file 17) | a plugin has the power of the process that starts it |
| X-39 | An agent misuses the MCP face | capability profile, separate key with scopes and quotas (file 17) | in a session, a same-uid process bypasses the profile (file 17) |
| X-40 | A run asks a token for an audience it does not own | `id.audiences`, `id_aud`, scope `id`, live check (file 17) | a token stays valid until `exp` |
| X-41 | A dependency with a vulnerability | `cargo deny` advisories and bans, pinned tags (file 21) | a flaw between audits |
| X-42 | Secret in argv, a log, a URL or stderr | token handling of section 7.5; offer bodies and request bodies never logged | a task that prints its own secret |

## 21. What is not protected

* Task data and the caller's files from root of a worker machine, below shield `sealed`; from the owner of a worker, below shield `guest` (file 13).
* Integrity of results from a hostile worker in the core.
* Anything inside the power of an attempt at boundary `none`.
* The swarm from the operator or from root of the coordinator host. The session from a process of the caller's uid.
* Availability against an attacker with enough volume to reach the listener.
* Side channels between attempts on one machine.
* Metadata on the network: sizes, timing, addresses.
* An external system that a task changes twice (file 09).
* Knowledge of a content id (`b3:`) grants nothing, and is not a secret.

## 22. Extensions

The extensions are in file 24, one line each here:
* Signed shapes (`sig.1`): a submitter signs a shape; a worker with `require_signed_by` runs only signed shapes.
* Secrets (`secrets.1`): named secret files, sealed at rest, written into the work area of the attempt, never in the environment.
* Replication and sampling (`verify.1`): runs a task on several workers and compares.
* Audit hash chain (`audit-chain.1`): chains the `events` rows and anchors the head off the host.
* Key rotation: a worker or a submitter moves to a new key under the old key's signature.
* Hub (`hub.1`): a relay of TLS streams with its own per-link caps.
