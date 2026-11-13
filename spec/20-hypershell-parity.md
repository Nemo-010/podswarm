# 20. HyperShell parity

This file lists each HyperShell feature with a verdict and the exact podswarm form. HyperShell parity is one face of podswarm: the batch face (`podswarm x` and `podswarm submit`). It does not define the product (file 01, file 03). The commands are in file 18, the tokens in file 18, the settings in file 19, the queue in files 09 and 10, the store in file 11, the security rules in file 16.

`psw` is the short alias of `podswarm`. The table cells use `psw`.

Pin: HyperShell `2.8.7` (master) and `2.9.0a7` (develop). Verdicts: **KEEP** same behaviour. **CHANGE** same purpose, other mechanism, with the reason. **DROP** left out, with the reason. **LATER** planned, with the file that owns it. A source named `ROADMAP: section` is a section title of `ROADMAP.md` in the HyperShell repository.

A fact about HyperShell that a reader can doubt carries an `[EV-nnn]` tag (resolved in `evidence/facts.md`).

## 1. Commands

| HyperShell | Verdict | podswarm form |
| --- | --- | --- |
| `hs cluster`, `hsx` | KEEP | `psw x` and `pswx`. `psw cluster` is a hidden alias. |
| `hs server` | CHANGE | `psw coord`. Durable store, authority of a swarm. |
| `hs client` | CHANGE | `psw join @FILE` (or `-` for stdin, or `--invite-fd N`). The worker dials out. A machine that nobody can dial needs only this one command. |
| `hs submit` | KEEP | `psw submit`. `-q` (skip the database) has no form: a submit always goes to an authority. |
| `hs task submit -- ARGS` (one task) | CHANGE | `echo 'CMD ARGS' \| psw submit`. The attached form is `psw run` (file 18). [EV-090] |
| `hs initdb` | CHANGE | automatic at first start. `psw coord check`. `--backup` is `psw coord backup --to FILE`. `--vacuum` and `--truncate` are `psw coord gc` options (file 11). `--rotate` is DROP: age-based retention in the store replaces it (file 11). |
| `hs info ID` | KEEP | `psw show TASK` (hidden alias `info`) with `--stdout`, `--stderr`, `--attempts`, `--json`, `--field F` (`-x`). |
| `hs info --perf` | KEEP | `psw show TASK` prints wall, user, sys and peak memory of each attempt. A per-second series is LATER (section 2, `--monitor`). |
| `hs info --yaml`, `-i` (ignore partitions) | DROP | `--json` is the machine format. There are no partitions. |
| `hs wait ID` | CHANGE | `psw wait TASK\|RUN` with `--status`, `--return`, `--info`. It subscribes to events and does not poll every 5 s. |
| `hs run -- ARGS` | CHANGE | `psw run` (file 18) is attached: terminal, stdin, exit code of the command. HyperShell `run` needs a database and a client with `--capture`, and has no exit-code option; `hs wait --return` has one. [EV-091] |
| `hs list` (alias `search`) | KEEP | `psw ls` (hidden alias `list`): `-w EXPR`, `--failed`, `--succeeded`, `--remaining`, `--cancelled`, `--retries`, `--signal NAME`, `--all`, `--order-by`, `--limit`, `--count`, `--format`, `--json`, `--jsonl`, `--csv`, `--fields`, `--tag-keys`, `--tag-values KEY`. |
| `hs list -w` filter language | KEEP | same operators `== != >= <= > < ~` (regex) over the fields of `ls --fields`. |
| `hs list` refuses over 1,000 rows | KEEP | `ls` on a terminal refuses more than 1,000 rows without `--all`, `--limit` or `--count`. |
| `hs list --part N`, `card` format | DROP | no source partitions. `show` serves the single-task view. |
| `hs update --cancel` | CHANGE | `psw cancel`. It stops a running process. HyperShell cannot cancel a task after it reached a remote client. [EV-092] |
| `hs update --revert` | CHANGE | `psw retry SEL`. Budgets reset. The act is audited. |
| `hs update --delete` | CHANGE | `psw update --purge RUN --yes` removes a whole run. |
| `hs update --remove-tag`, tag edits | KEEP | `psw update SEL --tag K:V` and `--untag K`. |
| `hs update -w`, `--order-by`, `--limit` (bulk) | KEEP | same options on `cancel`, `retry`, `update`. |
| `hs config get\|set\|which\|edit` | KEEP | `psw config get\|set\|path\|edit`. `which` is `path`. |
| `hs relay` (2.9) | not covered | A relay is a site sub-scheduler: it is a client upstream, runs its own server and database at the site, launches site clients, evicts locally. [EV-093] The match is the later sub-coordinator (file 24). The later `hub` forwards bytes and is a different feature. |
| Python API (`ServerThread`, `ClientThread`, functional API) | DROP | the wire and the CLI are the interface. |

## 2. Flags of `cluster` (`hsx`), `server`, `client`, `submit`

| HyperShell flag | Verdict | podswarm form |
| --- | --- | --- |
| `FILE`, stdin | KEEP | positional `FILE` or stdin. The positional rule is in file 18 (with `-t`, one positional is FILE). |
| `--restart` | CHANGE | `--db FILE --resume`, or `--joblog FILE --resume` with no store. Tasks with a key that succeeded are skipped (file 18). `--retry-failed` and `--retry-lost` re-run the rest. |
| `--repeat`, `--update`, source guard (2.9) | CHANGE | task keys (command hash plus occurrence number), `--key` for your own keys, `--resume`. Same effect: no double submit. |
| `--forever` | CHANGE | a coordinator is the forever mode. A run stays open: `psw submit --name NAME`. |
| `-r`, `--max-retries` | CHANGE | `-r`, `--retries N`: N retries after the first attempt. The HyperShell text is ambiguous on this count. [EV-094] |
| `--eager` | CHANGE | `--retry-first` |
| `--no-db` | CHANGE | the `memory` level of the store keeps the full state machine, with retry and groups (file 11). |
| `--initdb`, `--no-confirm` | DROP | no confirm step. The assignment is stored at hand-out, so orphan recovery never waits for a late acknowledgement. [EV-095] |
| `--ssh HOST...`, `--ssh-group`, `--ssh-args`, `-E`, `--remote-exe` | CHANGE | `--on HOSTS` (ranges `node[01-32]` expand), `--on @GROUP` with groups in the pool file (file 08), `--ssh-args`, `--remote-exe`. The system `ssh` starts a static worker (file 04). No Python on the node. `-E` and `--ssh-env` become `--env NAME`, which passes the named variable only. |
| `--mpi`, `--launcher ARGS` | KEEP | `--launcher PREFIX`. One function builds each worker command line. |
| `-A`, `--autoscaling`, `-F`, `-P`, `-I`, `-X`, `-Y` | CHANGE | `psw coord --scale-hook CMD` (the hook `scale.tick`, file 17) runs CMD every `hooks.scale_tick_s` with the event on stdin: the `ready` and `running` counts of each class, `workers`, `free_slots` and `eta_s`. The script starts workers; podswarm computes no pressure. A swarm of small machines scales by machines that join. HyperShell defines pressure as `toc / (factor x avg_duration)` over the active group only. [EV-096] |
| `-N`, `--num-threads` | CHANGE | `-N`, `--slots`. The default is the core count. HyperShell defaults to 1 and takes 0 as "auto". A script for HyperShell that omits `-N` runs one task at a time there and one per core here. The reason is the GNU parallel habit. `--num-threads` and `--num-tasks` are aliases. [EV-097] |
| `-t`, `--template` | KEEP | `-t` is the template on `x` only. Without `-t` the positional rule of file 18 applies. |
| `-b`, `--bundlesize` | CHANGE | accepted with a warning and ignored: the authority sizes each offer from the `pull` of the worker (file 10). HyperShell 2.9 uses the client's `-b` as the size it asks for. |
| `-w`, `--bundlewait` | CHANGE | `--batch-wait D`: longest wait of a partial batch before a flush. The default is in file 18. HyperShell default is 5 s. |
| `-d`, `--delay-start` | KEEP | `--delay-start D`. A negative value means a random delay up to that size. |
| `-T`, `--timeout` (client idle) | KEEP | `-T`, `--timeout`, `--idle-exit D`. The whole-run limit is `--run-timeout`. |
| `-W`, `--task-timeout` | KEEP | `-W`, `--task-timeout` |
| `-S`, `--signalwait` | CHANGE | `--kill-grace D`. The ladder is polite signal, wait, kill of the tree. HyperShell sends SIGINT, SIGTERM, SIGKILL to the shell process only. [EV-098] |
| `-R`, `--ratelimit` | CHANGE | `--rate N` per run (file 10); there is no per-worker form. HyperShell applies it per executor although the help says per client. [EV-099] |
| `-C`, `--client-cores` | CHANGE | `-N`, `--slots`. |
| `-M`, `--client-memory` | CHANGE | accepted with a warning and ignored; a worker reports its memory. |
| `-c`, `-m` (task cores, memory) | KEEP | `--needs cores=N,mem=SIZE`; `-c`, `--cores` and `-m`, `--memory` are aliases. A trailer sets them per line. |
| server defaults `-c -m -W` | CHANGE | the submitter sets them. A coordinator has no task defaults: the shape is the contract. |
| `-Q`, `--poll` | DROP | parked pulls replace polling. |
| `-H`, `-p` (bind, port) | CHANGE | `--listen ADDR` on `coord`, and on `x` for one run. `:PORT` means all interfaces. A coordinator listens only when asked. `-H` and `-p` are aliases of `--listen HOST:PORT`. HyperShell default port is 50001. |
| `-o`, `-e`, `--capture` | CHANGE | `-o` and `-e` work with remote workers because output streams back. The store keeps a capped head and tail. `psw x` streams the full output. HyperShell refuses `-o` and `-e` with remote clients. |
| `--print` (server) | CHANGE | `--failures -` writes the failed lines to stdout. |
| `--monitor` | LATER | accepted with a warning. Result rows carry CPU and peak memory. A per-second series follows (file 24). |
| `-f`, `--failures` | KEEP | `-f`, `--failures FILE` |
| `--no-tls`, `--tls-ca`, `--tls-cert`, `--tls-key` | CHANGE | TLS 1.3 is on for each TLS road, pinned by the invite. A road that authenticates by itself (ssh, stdio) has no TLS. `--no-tls` is refused (file 18). |
| `-k`, `--auth` | DROP | a key never goes on a command line. Each worker has its own key (file 16). |
| `-g`, `--group` | KEEP | `--group N` |
| `-t`, `--tag` at submit | CHANGE | `--tag K:V` on every verb. `-t` is not a tag. |
| `--template` at submit | KEEP | same flag. |
| `--from-json SPEC` (2.9) | KEEP | `--from-json FILE@SELECTOR`. Each key of a record is a tag and a `{key}` field. |
| `--zone` (2.9) | CHANGE | tags and `needs.tags_all`: `--worker-tag zone:a`. Cells and placement rules are in file 08. |
| `--min-size`, `--max-size`, `--factor` | CHANGE | the hook script (above) holds the bounds. The coordinator does not count machines to start. |
| 2.9 `-b` on the client as its request size | CHANGE | see section 5, first row. |

## 3. Input, templates, metadata

| HyperShell | Verdict | podswarm form |
| --- | --- | --- |
| one task per line, blank lines skipped | KEEP | same. |
| a bare `#` cuts the line, blind to quotes | CHANGE | `#` is part of the line. Only a trailer is metadata. HyperShell lists this as a defect. [EV-100] |
| trailer `# HYPERSHELL: k:v`: tags, `group`, `cores`, `memory`, `timeout` | KEEP | regex `#\s*(PODSWARM\|HYPERSHELL):?`. The space and the colon are both optional, as in HyperShell. `#HYPERSHELL: timeout:1:30:00` matches. `--no-line-attrs` turns it off. [EV-101] |
| tag grammar, size grammar (K, M, G, T, powers of 1024), duration grammar (`1h30m`, Slurm times) | KEEP | same. |
| `{}`, `{.}`, `{..}`, `{/}`, `{/-}`, `{-}`, `{+}`, `{++}` | KEEP | same meanings. `{.}` is the directory part, as in HyperShell. It is not the GNU extension strip. There is no `--compat parallel` mode (section 9). |
| `{[a:b:c]}` slice | CHANGE | `{N}` and `{N:M}` fields. No `eval`. |
| `{= expr =}` Python lambda | DROP | needs Python and runs code from the input. Use `--from-json` fields or a command before `psw x`. |
| `{% cmd %}` shell expansion at submit | DROP | the same reason. |
| `{key}` | KEEP in part | For a `--from-json` field it matches HyperShell: a built-in token wins over a key of the same name, each `{key}` must exist in each record, or the submit fails with exit 64. Values are strings: `true`, empty for null, compact JSON for nested. For a plain tag, `{key}` is a podswarm extension. [EV-102] |
| `{slot}`, `{slot_count}` (2.9, 0-based, at execution) | KEEP | same names and base. `{%}` is the GNU form and is 1-based. HyperShell has no `{%}` token. [EV-103] |
| `{#}`, `{q}`, `{token\|q}` | CHANGE | podswarm tokens: `{#}` index, `{q}` and `\|q` quote for the shell. `--argv` mode runs with no shell. |
| token list | KEEP | `{}`, `{.}`, `{..}`, `{/}`, `{/-}`, `{-}`, `{+}`, `{++}`, `{q}`, `{N}`, `{N:M}`, `{#}`, `{%}`, `{slot}`, `{slot_count}`, `{key}`, `{{`, `}}`, suffix `\|q` (file 18). |
| `TASK_*` variables | KEEP in part | `TASK_ID` (integer), `TASK_ARGS`, `TASK_COMMAND`, `TASK_CWD`, `TASK_ATTEMPT`, `TASK_TAG_*`, `TASK_SLOT`, `TASK_SLOT_COUNT`, `TASK_START_TIME`, `TASK_PREVIOUS_ATTEMPT`. Added: `TASK_RUN`, `TASK_INDEX`, `TASK_GROUP`, `TASK_KEY`, `TASK_WORKER`, `TASK_DIR`, `TASK_CPUS` (file 12). |
| `TASK_SUBMIT_*`, `TASK_SERVER_*`, `TASK_CLIENT_*`, `TASK_SCHEDULE_TIME`, `TASK_WAITED`, `TASK_PREVIOUS_ID` | DROP | the host names and times belong to the store (`psw show`). `TASK_PREVIOUS_ATTEMPT` replaces the id link. |
| `TASK_OUTPATH`, `TASK_ERRPATH` | CHANGE | output returns through the link. `TASK_DIR` is the work directory. |
| `[export]` table, `HYPERSHELL_EXPORT_FOO` becomes `FOO` in the task | KEEP | `[export]` and `PODSWARM_EXPORT_FOO` become `env` of the shape. The worker policy `env_pass` and `deny_env` still apply (file 16). |
| `HYPERSHELL_*` config variables | CHANGE | `PODSWARM_*`. Same precedence order (file 19). |
| `_env`, `_eval` config suffixes | DROP | `_eval` runs a command to read a value. A secret goes through a file. |
| file logging with rotation, compression, keep | CHANGE | log to stderr. The service manager or `logrotate` rotates. SIGHUP reopens the log file. |
| SQLite pragma advice, `database.echo` | DROP | the store sets its pragmas (file 11). |

## 4. Data model and storage

| HyperShell | Verdict | podswarm form |
| --- | --- | --- |
| SQLite default | KEEP | SQLite WAL, one writer (file 11). |
| PostgreSQL provider | DROP | a second writer and a server. The store trait keeps the option open. |
| TimescaleDB, Turso | DROP | no consumer. |
| state from NULL columns | CHANGE | explicit state enum (file 09). |
| `task` table columns | CHANGE | `tasks`, `attempts` (file 11). |
| retries as new rows linked by `previous_id` | CHANGE | one task, many attempts. One stable id. |
| `exit_status` holds code, `-signal`, `-1` cancel | CHANGE | separate `outcome`, `exit_code`, `signal`. A `kill -HUP` of the task and a cancel no longer share a value. [EV-104] |
| `client` table, `evicted`, `disconnected_at` | CHANGE | `workers` table (file 11). |
| no migration (2.8); in-place upgrade (2.9) | KEEP the 2.9 idea | numbered migrations (file 11). |
| source table, fingerprints, `task.part` | CHANGE | task `key` and `--resume`. |
| a late result written over a row | CHANGE | one accepted result per task. A late one is recorded and `show` prints it (file 09). |
| in-memory run with no database | KEEP | `psw x` with no `--db` (the `memory` level). |

## 5. Scheduling and execution

| HyperShell | Verdict | podswarm form |
| --- | --- | --- |
| 2.8.x: the server pushes a bundle to a size-1 queue, the first client to read wins | CHANGE | see the next row. |
| 2.9: a client asks for work, names its zone and its bundle size; the server cuts a reply from its pool, at most `bundlemax` 1,000 per reply, waits 2 s when empty, `PROTOCOL = 1`, a client older than 2.9 is refused | CHANGE | The pull is not a difference. Differences: the link is outbound-only or goes over a road (ssh, a PodUtils road), with no open port at the coordinator; the binary is static; each attempt has a lease and a fence on the worker, so a falsely evicted worker stops its tasks; the transport is JSON frames and not Python pickles. Bundle size comes from the authority with credit (file 10). [EV-105] [EV-106] |
| default `queuesize` 1, `bundlesize` 1 | CHANGE | `auto` bundles and parked pulls. |
| confirm step to stamp `client_id` | DROP | stored at hand-out. |
| task groups, failure-budget halt | KEEP | `--group`, `--continue-groups`, `--halt-on-fail N\|P%`. [EV-107] |
| resource-aware start, backfill | KEEP the declared model | matching and reservation in the authority (file 10). Resources are declared, not measured. |
| head-of-line blocking on unstartable tasks | CHANGE | class matching: a task that fits no worker waits in its own class. [EV-108] |
| heartbeat 10 s, evict 600 s, revert orphans | CHANGE | heartbeat, fence and lease on monotonic clocks (file 05). A worker kills its own attempts at the silence deadline. |
| timeout ladder SIGINT, SIGTERM, SIGKILL to the shell PID | CHANGE | polite signal, grace, kill of the tree (file 12). |
| SIGUSR1 stop scheduling and drain, SIGUSR2 drain and escalate, SIGHUP rotate logs | KEEP | `psw workers drain` and SIGUSR1; SIGUSR2 escalates; SIGHUP reopens logs. |
| `Popen(shell=True)` | KEEP | `shell` tasks. `argv` tasks run with no shell. |
| a task runs as the client user with no isolation | KEEP, extend | boundary `none`; `confined` on Linux; more in file 13. |
| output stored on the client host, fetched by SFTP | CHANGE | output streams back (file 15). |
| SSH launcher: one `ssh` per host in a loop | CHANGE | `--on` and `--launcher` start hosts in parallel with `--delay-start` stagger. |
| key given to an ssh-launched client | CHANGE | the road authenticates (file 04). A TLS worker takes its token on stdin or from a 0600 file. |
| per-executor threads | CHANGE | async tasks in one static process. |
| `hs` name clash with another tool | CHANGE | `psw`. [EV-109] |

## 6. Security and exit codes

| HyperShell | Verdict | podswarm form |
| --- | --- | --- |
| shared key and pickle RPC | DROP | per-worker keys, JSON frames, no object deserialisation. [EV-110] |
| self-signed RSA-3072 TLS, optional pin | CHANGE | TLS 1.3, pin in the invite (file 16). |
| no per-client identity, no revocation | CHANGE | per-worker identity; `psw workers revoke`; `psw invite revoke`. |
| IPv4-only listener | CHANGE | dual stack for `:PORT`. [EV-111] |
| exit codes 0 to 6 | CHANGE | the table below. |
| a run with failed tasks exits 0 | CHANGE | exit 1. A script that needs 0 uses `\|\| true`. [EV-112] |
| an empty input never finishes | CHANGE | exits 0 at once. [EV-113] |
| a pipe that closes while the feeder runs ends the run early | CHANGE | the run waits until stdin ends. [EV-114] |
| all launched clients fail: the run waits for ever | CHANGE | `--no-worker-timeout D` ends the run with exit 69. [EV-115] |
| merged output can interleave | CHANGE | one piece per stream and task; `--line-buffer` for lines. [EV-116] |
| live progress and ETA planned | KEEP | `--progress` with rate and ETA on a terminal. |

Exit codes of podswarm (file 19 holds the full table):

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | a run ended with a task not succeeded (`x`, `submit --wait`, `wait`) |
| 64 Usage, 66 NotFound, 69 Unavailable, 70 internal | as sysexits |
| 75 TempFail, 76 Protocol, 77 Refused, 78 Config or Revoked, 79 Policy, 80 Unsupported | named failures |
| 124 | the wait ended first: `--run-timeout` of `x`, `--wait-timeout` of `wait` and `submit --wait`; for `run`, `--task-timeout` passed |
| 126, 127 | `run`: the program cannot run, or is not found |
| 130 | interrupted |
| 255 | `run`: a failure of podswarm itself |

`psw run` exits with the command's own code (128 plus the signal number for a signal) and has no option for it (file 18).

## 7. Platforms

HyperShell runs on Linux, macOS and Windows through Python 3.11 or later. podswarm builds a worker for Linux, macOS and Windows. Each build is static on its target (file 01). The BSDs are best effort. Confinement is Linux only (file 13).

## 8. What podswarm adds

* A way in only: `psw run HOST -- cmd` over ssh or a PodUtils road. No service stays behind (file 03, file 04).
* Outbound-only workers (`psw join`). HyperShell needs the server port open to each client.
* A static binary on small machines. No Python and no package on the node.
* The live view of the caller's directory, with sync as the fallback (file 06). `x` defaults to `--view auto`, so a HyperShell one-liner keeps its relative paths on a remote worker with no flag: through the view, or on a cluster with a shared file system in the mount itself (D-127). `submit` defaults to `none`.
* Exec-level spreading: each process of a program can run on another pooled machine (file 07).
* Pools and placement of one command (file 08). Cells and region rules.
* Per-worker keys and revocation. Invites with rules.
* Leases with a fence, reattach after a link cut, a result journal.
* Containment with a named promise and no silent downgrade. Shields (file 13).
* Network policy served by podnet (file 14).
* `argv` tasks with no shell. The `{q}` token.
* Adaptive bundles, parked pulls, tail reclaim.
* Content-addressed input and output, resumable. Checkpoints and resume (file 15).
* `psw each`: one task on each matching worker.
* Worker lifetime: `--time-limit`, read from `SLURM_JOB_END_TIME` or `PBS_WALLTIME`.
* An explicit delivery contract and `delivery = at_most_once`.
* Exit codes that report failure.
* An agent face and hooks for agents that use podswarm (file 17).

## 9. GNU parallel and xargs forms

GNU parallel parity is not a goal. A user from GNU parallel meets these forms. There is no `--compat parallel` mode: the forms below are accepted or refused in every run. A refused form exits 64 with the hint `not supported; use ...`.

| GNU form | Verdict | podswarm form |
| --- | --- | --- |
| `-j N` | accepted | `-N` |
| `-k` | accepted | `--ordered` |
| `-a FILE` | accepted | positional `FILE` |
| `--joblog FILE` | KEEP | `--joblog FILE` (TSV, GNU columns plus `Outcome` and `Attempt`) |
| `--resume` with `--joblog` | KEEP | `--joblog FILE --resume`. Tasks whose key has exit value 0 are skipped, new lines append. No store is made. |
| `--resume-failed` | accepted | `--joblog FILE --resume --retry-failed` |
| `--halt now,fail=1` | accepted | `--halt-on-fail 1` |
| `--dry-run` | KEEP | `--dry-run` prints each expanded command. |
| `-0`, `--null` | KEEP | `-0`, `--null` |
| `--line-buffer` | KEEP | `--line-buffer` |
| `--results DIR` | KEEP | `--results DIR` |
| `{/.}` | accepted | `{/-}` |
| `{//}` | accepted | `{.}` |
| `{.}` (GNU: strip the extension) | differs | `{.}` is the directory part. Use `{-}` for the strip. The hint is in `--help`. |
| `:::`, `::::`, `--colsep`, `-X`, `-m`, `--pipe`, `--shuf` | refused | `not supported; pre-process the input, or use {N} fields` |
| `--bar`, `--eta` | refused | `not supported; use --progress` |
| `-S HOST`, `--sshlogin`, `--sshloginfile` | refused | `not supported; use --on or a pool file (file 08)` |

xargs: `xargs -P N -I{}` maps to `psw x -N N -t 'CMD {}'`. `-n`, `-L` and `-s` are refused with the hint `not supported; use {N} fields`. The test U-gnu covers this table (file 23).

## 10. HyperShell features that podswarm does not cover

| Feature | Reason |
| --- | --- |
| `hs relay`, the site sub-scheduler | A different design: a second scheduler with a site database. The later sub-coordinator is the match (file 24). |
| Python API and functional API | The wire and the CLI are the interface. |
| `{= expr =}` and `{% cmd %}` | They need Python and run code from the input. |
| `_eval` config suffix | It runs a command to read a value. |
| PostgreSQL, TimescaleDB, Turso providers | One writer and one file keep the static promise. |
| The HyperShell wire and pickle RPC | A podswarm worker cannot join an `hs server`, and the reverse. The two share no protocol. |
| `-k`, `--auth` on a command line | A key in argv leaks. |
| `--no-confirm` | It disables orphan recovery. |
| `--part`, `-i`, the source table | There are no source partitions. Task keys replace them. |
| `--monitor` time series, node and GPU telemetry | LATER (file 24). |
| Nextflow executor plugin | LATER. The machine interface of file 17 is the base. |
| S3 provider for captured output | LATER. Blobs are the store of output (file 15). |
| Zone-aware and relay-topology autoscaling | LATER. The scale hook gets the class and cell data (file 08). |
| Docker and Apptainer files, Homebrew tap, man page | LATER (file 22). Shell completion is in the first release: `psw completion bash\|zsh\|fish`. |
| SQL access to the store | There is no `psw sql`. Use `sqlite3 -readonly` on the store file. |
