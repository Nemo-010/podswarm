# 17. Extending: how programs and agents use podswarm

podswarm carries no agent, no prompt system and no memory. An agent or a program uses podswarm as it uses `ssh`: through the CLI with machine output, through a Model Context Protocol (MCP) server, through events and hooks, and through plugins. This file defines these four doors and the run identity that a run shows to other services. File 18 has the verbs and flags. File 19 has the exit codes and the settings table. File 05 has the shape and the error codes. File 15 has checkpoints. File 08 has pools and cells. File 16 has keys, organisation statements, submitters and quotas.

## 1. The machine interface of the CLI

Each verb is a client of the same operations as the MCP server (file 05, section 9). These rules hold for every verb.

* `--json` prints one JSON document on stdout. `--jsonl` prints one object per line. Each document and each object starts with `"schema":1` and has a `kind` that names its type. A list in `--json` is `{"schema":1,"kind":"rows","rows":[...],"next":CURSOR}`; `next` is an opaque string cursor, or null at the end.
* Human text goes to stderr only. With `--json` or `--jsonl` there is no colour, no progress line and no prompt. `NO_COLOR` is honoured.
* When stdin is not a terminal, or `PODSWARM_NONINTERACTIVE=1` is set, no verb prompts. A verb that needs an answer fails with exit 64 and names the flag that gives the answer.
* Exit codes are the table of file 19. With `--json` a failure prints one error document and the exit code is set as usual:

```
{"schema":1,"kind":"error","error":{"code":"quota","text":"max_running reached","exit":77,
 "retry":"no","scope":"submitter","limit":64,"used":64}}
```

  `retry` is `no`, `fix` (change the request), `backoff` or `wait` (use `retry_after_ms`). Section 3 maps each exit code to a class. The fields `scope`, `limit`, `used`, `reason` and `retry_after_ms` appear when the code has them (section 9).
* Each verb that changes state takes `--dry-run`. It checks the request, prints what it would do, changes nothing and exits 0, or exits with the code of the first check that fails. The document is `{"schema":1,"kind":"dry_run","actions":[{"op","target","detail"}]}`. For `run` and `submit` the action `place` names the worker, the boundary, the shield, the view rung and the network policy that the run would get.
* `--key K` on `run`, `submit` and `x` sets the task `key` (file 09). A retry of the same call after a lost reply returns the first run and starts nothing new.
* `podswarm version --json` prints the protocol numbers, the feature names and the exit table. `podswarm skill --commands --json` lists each verb, its flags and the `kind` of its output. `podswarm skill --schema KIND` prints the JSON Schema of one `kind`. A program reads these instead of parsing help text.

`podswarm run --json` runs the command with `io = capture` (file 05). It cannot attach the terminal, because stdout carries the document. `--stdin FILE` or `--stdin -` sends input. The result document:

```
{"schema":1,"kind":"run.result","run_id":12,"task_id":345,"attempt_no":1,
 "ok":true,"outcome":"exited","code":0,"signal":null,"reason":null,
 "worker":{"wid":3,"name":"big","cell":"home","boundary":"confined","shield":"private","juris":null},
 "where":{"road":"ssh","view":"fuse","net":"pool"},
 "wall_ms":8123,"user_ms":15010,"sys_ms":820,"rss_kib":912340,
 "in_bytes":10240,"out_bytes":482113,"net_bytes":null,
 "started_unix":1794000100,"ended_unix":1794000108,
 "stdout":{"len":482113,"trunc":true,"enc":"utf8","head":"...","tail":"..."},
 "stderr":{"len":0,"trunc":false,"enc":"utf8"}}
```

`ok` is true when `code` is in `ok_codes`. `outcome` and `reason` are the values of file 05. `net_bytes` is null where the host does not report it. `where.road` is a road name of file 04; `where.view` is a rung of file 06 or `none`. `enc` is `utf8` or `base64` (file 12, section 9). `stdout` and `stderr` hold a head and a tail of at most `capture_max` bytes (file 05); the full text is read with `logs`. The exit code of `podswarm run` follows file 18.

`podswarm watch --jsonl [--run R] [--type T,...] [--since SEQ]` streams events. In a swarm each event has a `seq` that rises by one in the cell, and `--since` resumes after it; delivery is at least once, so the reader keeps the last `seq`. In a session there is no store: `watch` streams the live events of the home and `--since` is refused. When `--since` is older than the retention of the events table (file 11), the stream sends `{"schema":1,"kind":"event","type":"gap","oldest":N}` and goes on from `oldest`.

```
{"schema":1,"kind":"event","seq":4711,"id":"<ulid>","type":"task.end","time_unix":1794000123,
 "cell":"home","run_id":12,"task_id":345,"attempt_no":1,"data":{...}}
```

| `type` | `data` fields |
| --- | --- |
| `run.start` | `name`, `submitter`, `tasks`, `io`, `delivery`, `tags` |
| `run.end` | `state` (`succeeded`, `failed`, `cancelled`, `halted`), `counts{succeeded,failed,cancelled,lost}`, `wall_ms` |
| `task.end` | `outcome`, `code`, `signal`, `reason`, `accepted`, `worker`, and the usage fields of section 9 |
| `worker.join` | `wid`, `name`, `tags`, `boundary`, `shield`, `juris`, `caps`, `road` |
| `worker.leave` | `wid`, `reason` (`bye`, `drain`, `lifetime`, `lost`, `revoked`), `attempts_lost` |
| `checkpoint.saved` | `ckpt` (the name of file 15), `seq`, `kind`, `bytes`, `files`, `label`, `external_ref` |
| `checkpoint.damaged` | `ckpt`, `seq`, `reason` (`missing` or `mismatch`: a blob is absent or does not verify; file 15, section 11.6) |
| `admission.refused` | `submitter`, `code`, `scope`, `limit`, `used` |
| `scale.tick` | coordinator only, every `hooks.scale_tick_s`: `classes[{class, ready, running}]`, `workers`, `free_slots`, `eta_s` (section 5) |

`data` never holds output text, input text or a secret. An event is at most 16 KiB.

## 2. The agent face: `podswarm mcp`

`podswarm mcp [--profile NAME] [--workspace DIR]` is an MCP server on stdio. It speaks newline-delimited JSON-RPC 2.0, writes only MCP messages to stdout and logs to stderr. It offers tools only: no prompts, no resources and no HTTP transport. A hosted MCP server with OAuth is a wrapper that a platform writes over the submitter API (section 10). [EV-084]

The server is a thin client of the submitter operations. It starts no daemon and lives as long as the pipe of the agent. In a session it uses the holder (file 04), so a run survives between tool calls. A server never sends a notification of progress: the agent polls `show` with `wait_s`, which is a long poll.

Each tool has an `inputSchema` and an `outputSchema`. A result is `structuredContent` plus one line of text. A failure is `isError: true` with the error document of section 1 as `structuredContent`.

| Tool | Arguments | Result and limits |
| --- | --- | --- |
| `pool` | `cell?` | Cells, machines (name, tags, boundary, shield, juris, state, free `cores_m`, `mem_mib`, `disk_mib`, `res`) and queue depth. Read only. It holds no key and no address of a machine. |
| `run` | `argv` or `shell`, `cwd?`, `env?`, `needs?{cores_m,mem_mib,res}`, `timeout_s?`, `wait_s?`, `cell?`, `juris?`, `key?` | `{run_id,task_id,state,exit_code?,stdout_tail,stderr_tail,truncated,wall_ms,worker}`. A tail is at most `output_bytes`. When the command still runs after `wait_s`, the state is `running` and the agent calls `show`. |
| `batch` | `template`, `inputs[]`, `needs?`, `timeout_s?`, `retries?`, `key?` | `{run_id,tasks,state_counts}`. The template is the grammar of file 18. At most `max_tasks_per_call` inputs. No stdin stream. |
| `show` | `run_id`, `task_id?`, `fields?`, `limit?`, `cursor?`, `wait_s?` | Counts and rows with state, exit code, wall time and checkpoint count. `limit` is at most 200. `wait_s` is a long poll for a change. |
| `logs` | `task_id`, `stream` (`stdout`, `stderr`), `offset?`, `limit?` | Text with control characters as escapes (output is untrusted text) and the next `offset`. `limit` is at most 65,536 bytes. |
| `cancel` | `run_id` or `task_id` | Idempotent. Only for runs that this server created (tag `mcp:SESSION`). |
| `checkpoint` | `action` (`save`, `ls`), `task_id`, `label?` | `save` asks the running task to save a checkpoint (file 15) and returns its name. `ls` lists the names, sizes and labels. |

Files do not pass through the model. The command sees the workspace directory by the view, and its writes land in that directory (file 06). A large output is read from the directory.

**The capability profile.** A profile is a table `[mcp.profile.NAME]` in the user config (file 19). A workspace file cannot define or change one. The default profile `default` applies when `--profile` is absent.

| Key | Default | Range | Meaning |
| --- | --- | --- | --- |
| `workspace` | the `--workspace` directory, else the working directory | an absolute path | `cwd` and the view root. A `cwd` outside it is refused. |
| `cells`, `juris` | the cells of the user | a subset of the user's cells and labels | The allowed set of selectors. |
| `boundary_min`, `shield_min` | `none`; `none` | boundary names; shield names (file 13) | The floor of `needs.boundary` and `needs.shield`. A call can raise it and cannot lower it. |
| `env_allow` | `[]` | at most 64 names | Names that `env` may set. |
| `max_timeout_s`, `timeout_s` | 3,600; 600 | 1 to 604,800; 1 to `max_timeout_s` | Wall limit of one command, and its default. |
| `wait_s` | 25 | 0 to 60 | The wait of `run`. It stays under the timeout of a typical MCP client. |
| `max_running`, `max_cores_running` | 8; 16,000 | 1 to 10,000; 1,000 to 10,000,000 millicores | Concurrency of this profile. |
| `max_tasks_per_call`, `max_calls_per_min` | 1,000; 120 | 1 to 100,000; 1 to 10,000 | Size and rate of the calls. |
| `output_bytes` | 16,384 per stream | 0 to 65,536 | The tail in a `run` result. |

An agent cannot do these things with any profile, because no tool exists for them: add or bootstrap a host; create an invite, a submitter, an organisation key or a statement; change `cells`, a shield, a boundary, a worker policy or a residency rule, or pass `--ignore-workspace-rules` (file 08); read a key, a secret, a data key or the config; sign an identity token for an audience of its choice (section 6); cancel the runs of another session; change a quota or a policy.

How the profile is enforced:

* In a swarm, `podswarm key new --for mcp` makes a separate submitter key with the scopes `submit,read` and the quotas of the profile (file 16). The server holds only this key. The coordinator applies the scopes and the quotas, so a modified MCP client cannot exceed them. The profile keys that a quota cannot express (`cwd`, `env_allow`, `output_bytes`) are checked by the server.
* In a session there is no coordinator. The holder reads the profile file of its user and applies it to each call from the MCP server. This stops a mistake of an agent that uses the tools. It does not stop a process that runs as the same user and calls the CLI directly. A caller who needs a fence uses a swarm.

## 3. The text an agent reads once

`podswarm skill` prints a `SKILL.md`. `podswarm skill --install DIR` writes it to `DIR/podswarm/SKILL.md`. `podswarm skill --llms` prints an `llms.txt` and `podswarm skill --llms-full` prints an `llms-full.txt`. Both are in the binary and need no network. A build generates them from the tables of the CLI: verbs, flags, output kinds, exit codes and error codes. A golden test compares the output with the tables, so the text cannot drift (test U-skill, file 23).

The structure is a quick card, then detail:

```
---
name: podswarm
description: Use it when: you must run a command on a stronger or another machine, run
  many commands in parallel, keep a long run that survives a loss, or give an agent
  compute. Not for: an interactive login (use ssh), a fast command on this machine.
---
# podswarm
## Quick card
1. First call:  podswarm run --json -- uname -a
2. Many:        podswarm x --json -t 'sha256sum {}' FILE
3. Look:        podswarm ls --json --run 12 ; podswarm logs --json 345
Failures: table below. Fields to read: ok, code, outcome, wall_ms, worker.name.
Version: <12 hex digits>
## Failures
| exit | error.code | retry | do |
## Fields
## Recipes
```

The version is the first 12 hex digits of the BLAKE3 hash of the text with an empty version line. It changes when anything that a caller reads changes. `llms-full.txt` ends with the pipeline contract: the stable fields, every failure by retry class and the paging loop of `ls`.

| Exit | Class | The agent does |
| --- | --- | --- |
| 0 | ok | Read the result. |
| 1 | task failed (`x`, `submit --wait`, `wait`) | Read `code`, `outcome` and the log tail. Retry only if the task is safe to repeat. |
| N | `run` and `wait --return`: the exit code of the command (128 + N for a signal) | As for 1. |
| 64, 66 | fix | Change the request or the id. |
| 69 | backoff | Retry with growing delay. |
| 70 | no | Report a defect. |
| 75 | wait | Retry after `retry_after_ms`, else with backoff. A refused `submit` records nothing, so the retry is safe. |
| 76, 80 | no | Upgrade or report. |
| 77, 79 | no | A quota, a key or a policy refused. Do not retry. Report the `limit` and the `reason`. |
| 78 | no | Config or revoked key. Ask the owner. |
| 124 | fix | The wait or the run ended first (`--wait-timeout`, `--run-timeout`, file 18, section 6.5); for `run`, the task timeout passed. Raise the limit or split the work. |
| 126, 127 | fix | `run`: the program cannot run, or is not found. |
| 130 | no | Interrupted. |
| 255 | by `error.code` | `run`: podswarm failed. With `--json` the error document gives the class and its code above. |

## 4. External subcommands

`podswarm NAME ARGS` runs the program `podswarm-NAME` when NAME is not a built-in verb. The exit code, stdin, stdout and stderr pass through. A name is `[a-z0-9-]` and at most 32 characters.

* Lookup order: the directories of `PODSWARM_PLUGIN_PATH`, the `plugins` directory of the user config, then `PATH`. The current directory and any directory of a workspace are never searched, so a repository cannot plant a command.
* A built-in verb always wins. A plugin does not shadow a verb, a hidden compatibility verb (`cluster`, `list`, `info`), `mcp` or `skill`. A name that starts with `road-`, `ckpt-` or `admit-` is reserved for the plugin kinds of section 7 and does not run as a subcommand.
* Environment given: `PODSWARM_BIN` (absolute path of the binary), `PODSWARM_PROTO`, `PODSWARM_CELL`, `PODSWARM_JSON=1` when the caller gave `--json`, `PODSWARM_NONINTERACTIVE`, `NO_COLOR`, `PODSWARM_CONFIG_DIR`. No key file, token or data key is given. A plugin that needs the pool runs `"$PODSWARM_BIN" --json ...`, as a `kubectl` plugin runs `kubectl`.
* The plugin has the authority of the user. There is no sandbox, as for `git` and `cargo` subcommands.
* `podswarm plugin ls --json` lists the `podswarm-*` programs found. A program may answer `--psw-describe` with one line `{"schema":1,"name","version","summary","proto":1}`.
* podswarm has no registry and no installer. A user copies the executable into a directory of the lookup.

## 5. Hooks and events

The events of section 1 come from one source: the events table of a coordinator (file 11), or the memory of a home. Pull is `podswarm watch`. Push is a hook or a webhook.

**Hooks.** A hook is a command that runs for one event type.

```
[hooks]
"run.end"  = ["notify-send", "podswarm"]
"task.end" = ["/usr/local/bin/log-usage"]
```

* Where: the user config for a client, the coordinator config for a coordinator (file 19). A workspace file cannot define a hook, because a repository must not run a command on a machine.
* The command runs from an argv with no shell. It gets one JSON document, the event, on stdin and the name of the event in `PODSWARM_EVENT`. The hook of a client runs where the CLI runs and sees the events of the runs that this CLI created. The hook of a coordinator runs on the coordinator host and sees every event of the cell.
* Limits: `hooks.timeout_s` 10, range 1 to 600 (the process is killed at the limit); `hooks.max_inflight` 4, range 1 to 64. When more than 256 events wait, the oldest are dropped and a log line counts them. The output goes to the log.
* A hook never fails a run and never delays one. A CLI that ends a run waits at most `hooks.timeout_s` for the hooks of `run.end`.

**The scale hook.** A coordinator emits the event `scale.tick` every `hooks.scale_tick_s` (default 30, range 5 to 3,600) while a run is open. `data` holds, for each class (file 10), the counts of `ready` and `running` tasks; `workers`, the count of workers with a session; `free_slots`; and `eta_s`, the time to end the ready tasks at the end rate of the last minute (null with no ended task). The hook starts or stops machines by its own means, for example `podswarm bootstrap` or the API of a provider. `podswarm coord --scale-hook CMD` (file 18) sets `[hooks] "scale.tick"` for that coordinator. podswarm itself starts and stops no machine (D-99).

**Webhooks.** A coordinator can sign and send events to a URL.

```
[[webhook]]
name = "ci"
url = "https://example.org/psw"
aud = "https://example.org"
events = ["run.end", "task.end"]
```

* `url` is `https`; `http` is allowed for a loopback address. The coordinator checks the address of the destination against `net_allow` (file 16), so a webhook cannot reach an internal address.
* A delivery is a `POST` with `Content-Type: application/json`, the header `Authorization: Bearer JWT` and one event as the body (at most 64 KiB). The JWT is signed with the hook key (EdDSA, separate from the identity key of section 6; header `typ` is `psw-hook+jwt`):

```
iss  the issuer of section 6, or "podswarm:CELL"      aud  the `aud` of the webhook
iat, nbf, exp = iat + 300                              jti  base64url without padding of 16 random bytes, new for each attempt
body_sha256  base64url without padding of SHA-256 over the exact body bytes (SHA-256: the receiver is outside podswarm)
event_id  the event id, the same in each attempt       delivery  a ULID, the same in each attempt
```

* Retry: 7 attempts at 0 s, 5 s, 20 s, 1 min, 3 min, 8 min and 15 min after the first. A `Retry-After` is honoured up to the longest interval. The coordinator keeps the delivery for 72 hours, and `podswarm coord resend DELIVERY` sends it again.
* The receiver verifies the signature before it parses the body. It checks `iss`, `aud` and `exp` (leeway 60 s), compares `body_sha256` with the raw body in constant time, and keeps each `jti` until `exp` plus the leeway. It removes duplicates by `event_id`, because `jti` changes in each attempt.

## 6. Run identity

A run can prove to a third party (a cloud identity service, a forge, an internal service) which run it is, with no long-lived secret. The proof is a JWT (RFC 7519) for one audience and one attempt.

**Algorithms.** A coordinator signs with ES256, with a P-256 key that it makes for tokens only; its TLS key is an Ed25519 key (file 16). A caller who has no coordinator signs with EdDSA. The reason: cloud verifiers differ. AWS accepts RS256, RS384, RS512, ES256, ES384 and ES512 in the discovery document of an OIDC provider, and EdDSA is not in the list. Google Cloud workload identity federation takes tokens signed with RS256 or ES256. [EV-085] A verifier that needs RS256 is served by a platform wrapper. `id.alg` is `ES256`.

**Header and claims.** The header is `{"alg":"ES256","typ":"JWT","kid":K}`. `kid` is the first 8 hex digits of the SHA-256 of the public key. The signature is the raw 64 bytes of the JWS form.

```
iss  the issuer URL                  sub  "podswarm:CELL:run:RUN:task:TASK"
aud  the requested audience          iat, nbf, exp, jti (16 random bytes, base64url without padding)
cell, run_id, task_id, attempt_no    worker (wid)   boundary ("none","confined","sandbox","vm")
shield (shield of the attempt)       juris (label of the worker)    shape (the first 16 hex of the shape id)
sub_key  fingerprint of the submitter key     org  fingerprint of the organisation key, if any
ws  a label the submitter set   ref  a free string the submitter set with --ref
```

`boundary` and `shield` are in the token so that the relying service decides: for example, it gives no production secret to `boundary = none` or `shield = none`.

**Where the run finds it.** The worker writes the token for the default audience to `$TASK_DIR/.psw/id.jwt`, mode 0400. The path is in `TASK_ID_TOKEN_FILE`. The worker writes the file again at half of the lifetime while the attempt lives. A file is used because an environment variable of a running process cannot change, and a token in argv shows in the process table. For another audience the run calls `podswarm key token --aud URL`. The CLI talks to its worker on the socket in `TASK_SOCK`, and the worker sends `id_req{task_id, attempt_no, aud}` to the authority, and gets `id_rep` (file 05, D-98). The authority checks that the attempt is live and that the audience is allowed.

**Limits.** `id.audiences` is a list of exact strings. A submitter has `id_aud` patterns and the scope `id` (file 16); the default is off. A run cannot name an arbitrary audience, because it would then be a signing service for any code on any worker. `id.ttl_s` is 600 (range 60 to `id.max_ttl_s`). `id.max_ttl_s` is 3,600 (range 60 to 86,400). There is no revocation. The authority issues no token for an attempt that is not live. A token that exists stays valid until `exp`, so the lifetime is short. A host with root reads `TASK_DIR`: the token proves "this attempt, on a host of this boundary and shield" and does not hide itself from the host.

**The issuer of a swarm.** `id.issuer` is a URL. Without it there is no federation, only verifiers with pinned keys. The coordinator makes its ES256 key at first start in its state directory. The key is not in a workspace and is not the TLS key or the hook key. It publishes the current and the next key. It publishes the next key at least 1 hour before it uses it, because verifiers cache a key set for about 1 hour. [EV-086] The discovery document `/.well-known/openid-configuration` and the key set are two static files (each at most 8 KiB, no credential needed). `podswarm id export DIR` writes them (file 18). The issuer URL `id.issuer` is any HTTPS site that serves them. The next key reaches verifiers only after `id export` runs again and the site serves the new files, so the operator runs it after each new key. The coordinator does not serve them: its listener has no certificate of a public CA (file 24).

The discovery document has `issuer`, `jwks_uri`, `response_types_supported` (`["id_token"]`), `subject_types_supported` (`["public"]`), `id_token_signing_alg_values_supported` and `claims_supported`. The key set also holds the hook key (own `kid`, `typ` and `aud` keep a token of one use from serving the other).

**A session.** With no coordinator the home signs. The worker sends `id_req` over the link to the home, and the home signs with the key of the caller (`alg` EdDSA, `iss` `key:SHA256:FP`, the claims above without `cell`; `sub` is `podswarm::run:RUN:task:TASK`, with an empty cell part). A verifier trusts a pinned list of caller keys, as `authorized_keys` does. There is no document to publish.

**Rules for a verifier** (printed in the skill): allow a list of algorithms and reject `none`; check `iss`, `aud`, `exp` and `nbf` with at most 60 s leeway; check `jti` for replay when replay matters; never take a host from a claim.

## 7. Out-of-process plugins

Three kinds exist. A kind is out of process only where a plugin cannot weaken a boundary and the call is not on the hot path of the queue.

| Kind | Called by | Install name |
| --- | --- | --- |
| Road | the client | `exec:COMMAND` in the pool entry (file 08) |
| Checkpoint sink | the worker, after a local commit | `podswarm-ckpt-NAME` |
| Admission policy | the coordinator, at `submit` | `podswarm-admit-NAME` |

**Road.** `road = "exec:COMMAND ARGS"` runs a command that reaches a machine, as the `ProxyCommand` of ssh does. The client appends the argv of the far side (`podswarm worker --stdio`, or the shell command of a bootstrap, file 04). A `{remote}` token in the command puts the argv elsewhere. The stdin and stdout of the child are the byte stream of the link, with no JSON and no handshake of the plugin; the far worker writes the road preface (file 04). stderr goes to the log. The end of the child ends the link. The environment has `PODSWARM_ROAD_TARGET` (the name of the entry) and `PODSWARM_PROTO`. An example is `exec:kubectl exec -i POD --`.

**Framing of the two JSON kinds.** The host starts the executable and talks over its stdin and stdout. One JSON object is one line (UTF-8, no newline inside). stderr goes to the log. The first line comes from the plugin:

```
{"psw_plugin":1,"kind":"ckpt","name":"git","version":"1.2.0","ops":["put","get","rm"]}
```

`kind` is `ckpt` or `admit`. The host checks `kind` and `ops`, then sends request lines `{"id":1,"op":"put",...}`. The plugin answers `{"id":1,"ok":true,...}` or `{"id":1,"ok":false,"code":C,"reason":R,"text":T,"retry_after_ms":N}`; `reason` and `retry_after_ms` are optional. `code` is `retry`, `refused`, `not_found`, `unsupported` or `internal`. An unknown op gets `unsupported`. The host closes stdin to end the plugin. The party that needs the plugin starts it for the use and ends it after, so no daemon stays (file 03). A call has a time limit: `plugin.timeout_s` 60 for a normal op and 600 for `put` and `get` (range 1 to 3,600). At the limit the host kills the plugin and treats the call as `retry`.

Bulk data does not pass through the pipe. A sink gets directory paths on its own host.

**Checkpoint sink.** `checkpoint.sink = "NAME"` in the shape (file 15) makes the worker start `podswarm-ckpt-NAME` after the local commit of a checkpoint.

| Op | Request | Answer |
| --- | --- | --- |
| `put` | `dir`, `ckpt` (name), `label?` | `ref`: an opaque string, stored as `external_ref` |
| `get` | `ref`, `dir` | `ok`, the files are in `dir` |
| `rm` | `ref` | `ok` |

A sink for Git pushes the tree to a ref of the user. It holds the push credential. Core holds no Git credential and no Git code. A sink may redact before it pushes. Core does no redaction.

**Admission policy.** `admit.plugin = "NAME"` in the coordinator config. Op `admit`:

```
{"id":7,"op":"admit","submitter":"SHA256:...","cell":"eu1","run":12,
 "shape":{"needs":{...},"timeout_s":600,"tags":{"k":"v"}},
 "usage":{"running":3,"cores_m_running":3000,"open_runs":1}}
{"id":7,"ok":true}
{"id":7,"ok":false,"code":"refused","reason":"credit_exhausted","text":"..."}
```

The coordinator maps a refusal to `err{code:"policy", reason}` (exit 79) and a `retry` to `err{code:"busy", retry_after_ms}`. The time limit of `admit` is `admit.timeout_ms` 200 (range 10 to 10,000). At the limit, or when the plugin fails, `admit.on_error` decides: `refuse` or `allow`; the default is `refuse`. The event `admission.refused` records it.

**Install and trust.** A plugin is an executable that the user or the operator copies into a directory of the lookup of section 4. The host checks that the file is owned by the user or by root and is not writable by group or others. `[plugin.NAME] id = "b3:HEX"` in the config pins the content (BLAKE3), and a start with another hash is refused. A worker starts only the sinks that its policy names in `plugin_allow` (file 16), default none. A plugin gets no key and no token. It gets `PODSWARM_PLUGIN=1`, `PODSWARM_PROTO` and its own configuration. A credential reaches it from the environment of its host or through `secrets.1` (file 24). A plugin has the authority of the process that starts it. A plugin from the net needs a checksum from another origin, HTTPS and an explicit file mode; podswarm ships no installer. `podswarm plugin test --kind ckpt -- ./PLUGIN` runs the suite of section 8 against a plugin and prints the suite version that it passed.

## 8. Seams in the code

A seam is a Rust trait with one conformance suite. The suite runs against each implementation. An adapter that speaks the lines of section 7 implements the trait for a plugin, so one suite tests both (tests U-conf-* and G-17, file 23).

| Seam | Implementations | Behaviour owned by |
| --- | --- | --- |
| Road | ssh stdio, TLS over WebSocket, PodUtils roads, `exec:` | file 04 |
| View rung | `fuse`, `fuse-userns`, `trap`, `sync` | file 06 |
| Executor and boundary | `none`, `confined`; later `sandbox`, `vm` | files 12 and 13 |
| Store | memory, SQLite | file 11 |
| Checkpointer | blob store, sink plugin | file 15 |
| Placement policy | fit by tags, boundary and capacity | files 08 and 10 |
| Admission policy | quotas of the submitter, `admit` plugin | file 16 |

The executor and the boundary, the store and the view are not plugin kinds. A boundary must not be a process that the attacker can replace, and the store and the view are on the hot path. A platform that needs a rule for placement or cost uses the admission plugin, or wraps `podswarm` and chooses the cell (file 08). Other kinds come only on a request of a user.

## 9. Quotas, admission and usage

**The answer.** A refusal carries the limit, so a client does not hard-code it. The fields of `err` (file 05) for `busy`, `quota`, `too_large` and `policy` are `scope` (`submitter` or `swarm`), `limit`, `used`, `reason` and `retry_after_ms` (D-24). A shed `submit` records nothing, so a retry is safe, and the text says so.

| Case | Code | `retry_after_ms` | Exit |
| --- | --- | --- | --- |
| Rate or in-flight budget, full for now | `busy` | yes | 75 |
| Hard cap, for example `max_queued` | `quota` | no | 77 |
| The admission plugin refuses | `policy` with `reason` | no | 79 |
| Size over a limit | `too_large` with `limit` | no | 76 |

The quotas, the budgets and the pause of a run are in file 16 and file 10. A pause has a `paused_by` text: `admin` or `policy:REASON`. An operator or a platform changes a quota with the submitter operations, pauses with `podswarm update RUN --pause` (file 18), and ends work with `cancel`.

**Usage.** Each ended attempt writes one row. The key is `(cell, run_id, task_id, attempt_no)`, so a reader that stores rows by key is idempotent.

| Field | Meaning |
| --- | --- |
| `outcome`, `code`, `accepted` | `accepted` is false for a late result that a decided task discarded. The platform decides whether to count it. |
| `wall_ms`, `user_ms`, `sys_ms`, `rss_kib` | Measured by the keeper (file 12). |
| `cores_m`, `mem_mib` | Requested. |
| `reserved_mcore_ms` | `cores_m * wall_ms / 1000`. A platform normally bills this. |
| `boundary`, `shield`, `wid`, `class` | Where and what. |
| `in_bytes`, `out_bytes`, `ckpt_count` | Input fetched; output, blobs and checkpoint bytes sent; checkpoints saved. |
| `net_bytes` | Only where the host reports it; else null. |
| `submitter`, `tags` | Who and what. |

`podswarm usage --since SEQ|TIME [--by submitter|run|tag:K|boundary] --json|--jsonl` reads the rows. The `task.end` event has the same fields. A per-day rollup outlives the attempt rows (file 11). A platform exports the rows before the retention ends.

**Outside podswarm:** billing, prices, balances and invoices; prompts and agent definitions; memory and search; a forge and its triggers; the rule that sets a quota. podswarm gives the hooks: events, the admission plugin, the quota operations, `pause` and `cancel`.

## 10. What a hosted agent platform needs, and where it is served

| A hosted agent platform does | podswarm serves it with | Stays outside |
| --- | --- | --- |
| Runs an agent in a runner, from an immutable run record, with a key for retry | `run`, `submit` with `--key`, the shape and the view (files 05, 06) | The agent, its prompt, versions, harness and model keys |
| Chooses an isolation for the runner | boundary and shield (file 13) | Which level a product sells |
| Starts a run on an event such as a push | A consumer of `watch`, a hook or a webhook calls `submit` | The forge, trigger rules, approval state |
| Saves sessions and resumes them elsewhere | Checkpoints and `checkpoint` (file 15), the sink plugin for Git | Transcript format, redaction, the forge |
| Splits the service in regional cells with placement | Cells, `--cell`, `--juris` and residency rules (file 08) | A directory service, legal posture |
| One identity valid across cells | Organisation key and member statement (file 16) | Accounts, login, single sign-on |
| Gives a run an identity for other services | Run identity (section 6) | The trust policy of the relying service |
| Plugins with installation and suspension | External subcommands, hooks, three plugin kinds (sections 4, 5, 7) | A registry, an install flow, a permission catalogue |
| Signed webhooks | Section 5 | The receivers |
| A hosted tool endpoint for agents | `podswarm mcp` on stdio; a platform wraps the submitter API for HTTP and OAuth | The OAuth server, the hosted endpoint |
| Documents for agents | `podswarm skill`, `podswarm skill --llms` | A docs site |
| Admission, limits and pause with a reason | Quotas, `admit` plugin, `err` with `limit` (section 9) | The numbers, credit, trials |
| Usage and billing | `podswarm usage`, `task.end` (section 9) | Prices, invoices |
| Run state and cancel | `ls`, `show`, `cancel`, `watch` | The product UI |
| Memory, search, reviews, insights, telemetry | None. podswarm sends no telemetry (file 16). | All of it |
