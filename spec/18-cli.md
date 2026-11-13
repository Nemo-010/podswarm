# 18. Command line

This file defines the names of the binary, the rules that every verb follows, the verb list, `podswarm run`, `podswarm x`, the template language, and the synopsis of each other verb. A verb here points to the file that owns its semantics. File 19 holds the settings table, the configuration files, the exit code table, the walkthroughs and the recipes. File 17 holds the machine interface (`--json` documents, events, MCP).

## 1. Names

* The binary is `podswarm`. Every document, script and example that must work on any host spells `podswarm`.
* `psw` is the short alias. `pswx` is the alias of `podswarm x`. All three are one file: the program reads the base name of `argv[0]`. `pswx` means `podswarm x`; any other name means `podswarm`.
* `podswarm self install-aliases --yes` makes `psw` and `pswx` as symbolic links beside the binary (a copy on Windows). It never replaces a file or a link that it did not make. Without `--yes` it prints what it would do. An installer does not make the aliases.
* The short name is a convenience, not a contract, because another program has it. [EV-087] The release publishes the crate `podswarm` only.

## 2. Global rules

* **Streams.** Results go to stdout. Diagnostics, progress, prompts and banners go to stderr. A command in a pipeline can rely on it. `podswarm run` gives stdout and stderr of the far command to the caller byte for byte.
* **Machine output.** Every verb that reports takes `--json` (one document) or `--jsonl` (one object per line). The documents, the `kind` names and the error document are in file 17. With either flag there is no colour, no progress line and no prompt.
* **Dry run.** Every verb that changes state takes `--dry-run`: it checks the request, prints what it would do, changes nothing, and exits 0 or with the code of the first failed check (file 17).
* **Quiet and verbose.** `-q` prints errors only. `-v`, `-vv`, `-vvv` raise the log level (levels in file 19). `-v` also prints decisions that are silent by default: placement, the view rung, the positional rule of `x`.
* **Colour.** `--color auto|always|never`, default `auto`. `auto` colours only when stderr is a terminal and `NO_COLOR` is unset or empty. The progress line exists only on a terminal.
* **Prompts.** A verb prompts only when stdin and stderr are terminals. `--batch`, or `PODSWARM_NONINTERACTIVE=1`, turns every prompt off, also the first ssh connection of file 04. A verb that needs an answer and cannot prompt exits 64 and names the flag that gives the answer (`--yes` for a destructive change).
* **Flags.** An unknown flag exits 64. A long flag has one meaning on every verb. A short flag has one meaning on each verb; `-t`, `-T` and `-w` differ between verbs because ssh and HyperShell give them those meanings (sections 4 and 6.2). A secret is never a flag value: a token or a key comes from `@FILE`, from stdin (`-`) or from a descriptor (file 16).
* **Help.** `podswarm --help` shows at most 10 verbs: `run`, `x`, `submit`, `wait`, `ls`, `show`, `logs`, `cancel`, `pool`, `doctor`, then the line `more: podswarm --help-all`. `podswarm VERB --help` shows at most 12 flags and examples; `VERB --help-all` shows every flag. `--version` prints the version line of `podswarm version`.
* **Untrusted text.** Output of a task, a reason text and a name from a worker are untrusted. On a terminal the CLI prints control characters as escapes (`\x1b`). `podswarm run` with a pty is the exception: the bytes go to the terminal raw, as with ssh.
* **Durations.** A bare number is seconds. Suffixes `ms`, `s`, `m`, `h`, `d` combine (`1h30m`, `1.5h`, `250ms`). `HH:MM:SS` and `D-HH:MM:SS` are accepted. A point in time (`--not-before`, `--deadline`) is RFC 3339 or `+DURATION` from now.
* **Sizes.** A bare number is bytes, or MiB where the flag says so. Suffixes `K`, `M`, `G`, `T` (also `KiB`, `MiB`, `GiB`, `TiB`) are powers of 1024. Cores are decimal: `cores=0.25` is 250 millicores.
* **Configuration.** Precedence and the files are in file 19. A file in the working directory sets only what file 16 allows.

### 2.1 Where a command connects

1. `--coordinator ADDR` on the command line.
2. Else `PODSWARM_COORDINATOR`.
3. Else, for `run`, `x`, `submit` and `each`: the swarm cell that `--cell` or `[defaults] cell` names (file 08).
4. Else the holder of the user (file 04). A command starts the holder when none answers. With `--no-hold` the command itself is the home.

ADDR is a cell name of the pool file, a connect string `psw1s.` (file 16), or `wss://HOST[:PORT]` with a pin in the pool file. A coordinator with no pin is refused. The verbs that only a swarm has (`coord`, `invite`, `submitter`, `org`, `id`, `workers approve|revoke`) use the local socket of a coordinator of the same user on this host when none of 1 to 3 applies, and exit 69 when there is none. A workspace file never names a coordinator.

## 3. Verbs

| Verb | What it does | Where | Wire operation (file 05) or local |
| --- | --- | --- | --- |
| **Run work** | | | |
| `run` | one command now, with this terminal, stdin, signals and exit code | both | a session: the home opens the `io` streams; a coordinator: `submit` (one task, `io = attached`), then `attach` |
| `x` | one task per input line; waits and prints the output (the HyperShell `hsx` face) | both | `submit`, `watch`, `logs` |
| `submit` | queues tasks and prints the run id; `--wait` behaves as `x` | both | `run_new`, `submit`, `run_close` |
| `wait` | blocks until a run or a task ends | both | `watch` |
| **Look** | | | |
| `ls` | lists tasks, runs or workers (hidden alias `list`) | both | `ls` |
| `show` | one task, run or worker with its attempts (hidden alias `info`) | both | `show` |
| `logs` | stdout and stderr of a task; `-f` follows | both | `logs` |
| `watch` | streams events as JSON lines (file 17) | both | `watch` |
| `get` | writes the results and output files of a run to a directory (file 15) | both | `ls`, `logs`, `blob_get` |
| `pull` | copies paths that stayed in the warm workspace of a machine to the caller's tree, after the run (file 06) | both | the view of file 06 |
| **Change** | | | |
| `cancel` | cancels tasks | both | `cancel` |
| `retry` | runs ended tasks again | both | `retry` |
| `update` | holds, releases, tags, reprioritises, pauses, pins or purges | both | `update` |
| **Machines** | | | |
| `pool` | edits and probes the pool file (file 08) | session | local; `probe` opens roads |
| `forget` | removes podswarm, its caches and its run directories from a machine | session | local, road |
| `join` | runs a worker on this machine that dials a coordinator | swarm | `hello` as a worker |
| `workers` | lists, drains, approves, revokes and tags workers | both | `ls`, `worker_*` |
| `bootstrap` | installs and starts a dialling worker on hosts over ssh | swarm | local, road |
| `each` | runs one command on each machine of a selection | both | `submit` of pinned tasks |
| **A swarm** | | | |
| `coord` | runs and maintains a coordinator | swarm | local; `status`, `gc` |
| `invite` | makes, lists and revokes worker invites | swarm | `invite_*` |
| `submitter` | adds, lists and removes submitter keys | swarm | `submitter_*` |
| `key` | makes and shows a key; gets a run identity token | both | local; `id_req` |
| `id` | writes the static files of the run identity issuer (file 17) | swarm | local |
| `org` | makes an organisation key, issues and trusts member statements (file 16) | swarm | local; `org_add`, `org_ls`, `org_rm` |
| **Extend** | | | |
| `mcp` | MCP server on stdio (file 17) | both | the operations above |
| `skill` | prints the text and the schemas that an agent reads (file 17) | both | local |
| `plugin` | lists and tests plugins (file 17) | both | local |
| `checkpoint` | saves, lists, pins, removes, exports and imports checkpoints (file 15) | both | `ckpt_save`, `ckpt_ls`, `ckpt_show`, `ckpt_pin`, `ckpt_rm`, `ckpt_export`, `ckpt_import`; the task socket |
| `usage` | prints the usage rows of ended attempts (file 17) | both | `usage` |
| **Plumbing** | | | |
| `doctor` | probes this machine, a far machine or a coordinator | both | local, road |
| `config` | reads and writes the user config file | both | local |
| `self` | fetches release binaries, verifies a binary, makes the aliases | both | local |
| `autostart` | starts a worker or a coordinator at boot or login | swarm | local |
| `bench` | runs the built-in benchmarks (file 23) | both | local |
| `version` | prints the version, the protocol range, the features and the exit table | both | local; `version` |
| `completion` | prints a completion script for `bash`, `zsh` or `fish` | both | local |
| `holder` | shows or stops the holder (hidden) | session | local |

Hidden compatibility verbs: `cluster` (= `x`, HyperShell `hs cluster`), `list` (= `ls`), `info` (= `show`). Internal verbs, not for users and not in help: `worker --stdio`, `worker --attach` (file 04), `net-exit` (file 14). Verbs of later features: `job`, `secret`, `hub`, `audit` (file 24). An unknown verb NAME runs the external program `podswarm-NAME` (file 17).

## 4. `podswarm run`

```
podswarm run [OPTIONS] HOST [--] CMD [ARGS...]
podswarm run [OPTIONS] -- CMD [ARGS...]
```

`run` is ssh, but what the user gets is compute. It runs one command, now, with the caller's working directory through the view (file 06), the caller's terminal, stdin, signals and environment (minus the credential rules of file 13), and exits with the exit code of the command. The command is a task with one attempt, `io = attached`, `delivery = at_most_once` and `retries = 0` (file 09).

* **Parsing.** With `--`, every word before it is an option, except at most one word: HOST. No such word means "place it" (file 08). Without `--`, the first word that is not an option is HOST, and every later word belongs to the command, as with ssh.
* **The command.** The words after HOST are the argv of the command. When the command is one word that holds white space or a shell metacharacter, it runs as a `shell` command (file 12), so `podswarm run big 'cd sub && make'` works as with ssh.
* **HOST.** A pool name, `@GROUP`, `local`, or a road of file 04: `host`, `user@host`, `ssh://user@host:port`, `podssh://name`, `exec:CMD`. A road that the pool file does not list gets the defaults of a machine with no entry (`trust = "shared"`, file 13).
* **Placement.** With no HOST the home picks one machine by file 08: `--on SEL` limits the candidates, `--local` keeps the command on this machine, and `--cell`, `--region`, `--juris` select cells. A command whose learned run time is short stays local. `-v` prints the choice and `--dry-run` prints it with no run.

### 4.1 Terminal, stdin and signals

| Case | Rule |
| --- | --- |
| pty | The worker runs the command on a pty when stdin and stdout of `run` are both terminals. `-t` forces a pty. `-T` forbids one. A worker with no usable `/dev/ptmx` refuses a pty run with the probe row (file 12). |
| pty, local side | The caller's terminal goes raw. Keys pass as bytes, so `^C`, `^Z`, `^\` become signals by the far terminal. The window size goes at start and at each change (`resize`, file 05). `TERM` and `COLORTERM` pass; terminfo fallback is in file 12. The terminal is restored at exit, on a panic and on `SIGTERM` or `SIGHUP`. |
| pty, stderr | stderr of the command goes to the pty when stderr of `run` is the same terminal, else to a pipe, so `run HOST -- make 2>err.log` keeps the split. |
| no pty, stdin | stdin streams with backpressure. End of file closes the stdin of the command once; the command runs on. `-n` gives the command the null device. `--stdin FILE` sends a file. |
| no pty, signals | `SIGINT`, `SIGTERM`, `SIGHUP`, `SIGQUIT` of `run` go to the process group of the command (`signal`, file 05). A second `SIGINT` within 2 s sends `SIGKILL`. A third ends `run` with 255, and the fence of file 05 ends the attempt. |
| escape | With a pty, `~.` after a newline ends the command and `run`; `~?` lists the escapes; `~~` sends one `~`. `--escape C` sets another character; `--escape none` turns it off. |
| link cut | The command keeps running. A cut shorter than the silence budget is not seen (file 04). |

### 4.2 Exit code

| What happened | `run` exits |
| --- | --- |
| The command exited with code N | N |
| A signal N ended the command | 128 + N; `run` prints one line and does not kill itself |
| `--task-timeout` passed | 124 |
| The program is not found, or is not executable (`spawn_failed`, reason `bad_argv`) | 127, or 126 |
| A failure of podswarm: usage, road, refusal, policy, a lost attempt, a lost holder | 255, and one line `podswarm: CLASS: TEXT` on stderr |

With `--json` the command runs with `io = capture`, stdout carries the `run.result` document (file 17), and the error document gives the class and its exit code of file 19. A script that must tell a code of the command from a failure of podswarm uses `--json`.

### 4.3 Options of `run` only

| Flag | Meaning |
| --- | --- |
| `-t`, `-T` | force a pty, forbid a pty |
| `-n` | stdin of the command is the null device |
| `--stdin FILE\|-` | send FILE, or stdin, as the input of a captured run |
| `--escape C\|none` | the escape character; default `~` |
| `--json` | capture the output and print one `run.result` document |
| `--key K` | the task key: a repeat of the same call returns the first run (file 17) |
| `--no-hold` | no holder: this command is the home |
| `--no-trace` | leave no binary and no cache on the far machine (pool key `leftovers = "none"`, file 13) |

The flags of section 5 apply too.

### 4.4 Examples

```
podswarm run bigbox -- cargo build --release
podswarm run --pull target/release/app bigbox -- cargo build --release
podswarm run dev@10.0.0.7 htop
podswarm run -- make -j32
podswarm run --spread -- make -j64
podswarm run --shield none --on @lab -- ./bench.sh
podswarm run --json bigbox -- uname -a
```

## 5. Flags of `run`, `x`, `submit` and `each`

| Flag | Meaning | Owner |
| --- | --- | --- |
| `--on SEL` | candidates: comma list of names, roads, `@GROUP`, `tag:T` | 08 |
| `--local` | this machine only | 08 |
| `--cell NAME`, `--region R`, `--juris J` | cell selectors; a swarm cell gets a run only when named | 08 |
| `--ignore-workspace-rules` | widen past a workspace residency rule; prints the file | 08 |
| `--coordinator ADDR` | send the work to this coordinator (section 2.1) | 16 |
| `--needs K=V,...` | `cores`, `mem`, `disk`, `time`, and named resources (`gpu=1`) | 09 |
| `--worker-tag T` | a worker tag that must match; repeat for all; `A\|B` for any one | 09 |
| `--os L`, `--arch L` | allowed lists; `--arch` takes `uname -m` names; a value may hold tokens (`--os '{1}'`) | 09 |
| `--exclusive` | the attempt takes the whole worker | 09 |
| `--boundary B` | `none`, `confined`, `sandbox`, `vm` | 13 |
| `--shield S` | `none`, `private`, `guest`, `sealed` | 13 |
| `--force-lower` | allow a shield below the level of the pool entry | 13 |
| `--shield-require swap-locked` | refuse when the pages of the run can reach swap | 13 |
| `--area A` | `auto`, `memory`, `sealed`: where the owned directories live at shield `private` (pool key `area`) | 13 |
| `--allow-tcg`, `--seal-tcb-floor ack-old` | `guest` without KVM; `sealed` on an older TCB | 13 |
| `--view V` | `auto`, `fuse`, `fuse-userns`, `trap`, `sync`, `none`; `run` and `x` default to `auto`; `submit` defaults to `none` (the command runs in the directory that the worker gives it); `auto` makes no view where the worker already has the caller's directory (file 06) | 06 |
| `--root DIR`, `--with PATH` | the export root; one more projected path, read only | 06 |
| `--allow GLOB` | open one entry of the credential deny list for this run | 06 |
| `--pull GLOB`, `--keep GLOB` | copy owned files back at exit; keep writes to projected paths on the worker | 06 |
| `--clean` | empty the owned directories of the workspace on that worker first | 06 |
| `--no-cache` | keep no warm state on the worker (pool key `cache = false`) | 13 |
| `--key-escrow` | store the data key of an encrypted checkpoint in the secret store of the coordinator, which then answers key requests (D-126) | 16 |
| `--spread[=SEL]`, `--no-spread` | run each new process where it is fastest; turn a pool default off | 07 |
| `--local-only P`, `--remote-only P` | programs that never move, or always move (repeatable) | 07 |
| `--net POLICY` | the network policy string, with its `;KEY=VALUE` modifiers | 14 |
| `--env NAME[=VALUE]` | set NAME, or pass the caller's NAME; `NAME=@FILE` reads the value from FILE | 12 |
| `--env-allow NAME` | let a deny-listed variable name pass | 13 |
| `--task-timeout D`, `-W D` | wall limit of one attempt (`timeout_s`) | 05 |
| `--kill-grace D`, `--silence D` | `kill_grace_s`, `silence_s` | 05 |
| `--cap K=V,...` | limits `mem`, `as`, `cpu`, `fsize`, `nofile`, `pids` | 12 |
| `--merge` | stderr goes to the stdout pipe | 05 |
| `--shell KIND`, `--shell-always` | run by that shell and need it; no auto-argv | 12 |
| `--ok-codes L` | exit codes that count as success | 05 |
| `--tag K:V` | a tag of the task; repeatable | 09 |
| `--shape FILE` | a JSON object of shape fields with no flag (`checkpoint`, `confine`, `delivery`) | 05 |
| `--ssh-args A`, `--remote-exe PATH` | extra ssh options; a binary already on the far host | 04 |
| `--offline` | never fetch a binary from the release; exit 69 instead | 04 |

A flag value wins over `[defaults]` and the pool file. `--shape` is read first, so a flag wins over a field of it.

## 6. `podswarm x`

```
podswarm x [OPTIONS] [FILE]                 each input line is the command
podswarm x [OPTIONS] TEMPLATE [FILE]        each input line fills the template
podswarm x [OPTIONS] -t TEMPLATE [FILE]
```

With no FILE the input is stdin. When stdin is a terminal, `x` prints `reading commands from stdin, Ctrl-D to end` on stderr. The positional rule, in this order:
1. With `-t T` the template is T, and at most one positional is allowed: FILE.
2. With two positionals, the first is TEMPLATE and the second is FILE.
3. With one positional: it is FILE when it names an existing regular file and holds no white space and no token; else it is TEMPLATE.
4. With no template each input line is the command.

`-v` prints the resolution (`template from -t`, `file from positional`).

`x` defaults to `--view auto`: in a session its tasks see the caller's working directory through the view (file 06), so relative paths in the template work as in HyperShell. `auto` makes no view on the caller's machine, or on a worker that has the caller's directory on a shared file system at the same path (file 06, D-127). `submit` defaults to `--view none`: each task runs in the directory that the worker gives it (`TASK_DIR`, file 12). `--stage-each` sends each input file as a blob (file 15). With `--coordinator` the run goes to the coordinator; `-N`, `--listen` and `--launcher` are refused there. A session listens on no TCP port unless the user gives `--listen` or `--launcher`; both exist from M4, the milestone of the `wss` road (file 22).

### 6.1 Options of `x` and `submit`

| Flag | Meaning |
| --- | --- |
| `-t`, `--template T` | the template (on `x` and `submit`; never a tag) |
| `-0`, `--null` | input records end with NUL |
| `--argv` | split the template into argv by shell word rules and run with no shell |
| `--no-line-attrs` | treat a `# PODSWARM:` trailer as part of the line |
| `--from-json FILE[@PATH]` | one task per JSON object of FILE (JSON lines, or the array at the dot path PATH); each key is a tag and a `{key}` field |
| `--stage-each` | each input line is a local file: upload it, stage it as `in/<basename>`; `{}` names the staged file |
| `-N`, `--slots N` | tasks at one time on each machine that the run uses, at most its `slots`; default: the machine's `slots` |
| `--listen ADDR` | the home listens on ADDR for the run; workers join with a one-run invite (section 6.3); from M4 |
| `--launcher PREFIX` | start workers as `PREFIX podswarm join --invite-fd 0`; for `srun`, `mpirun`; from M4 |
| `--no-worker-timeout D` | exit 69 when no worker is ready within D |
| `--idle-exit D`, `--delay-start D` | for the workers that the run starts: exit when idle (file 10); delay the first dial |
| `-r`, `--retries N` | retries after a failure (file 09) |
| `--retry-delay D`, `--retry-first` | base of the backoff; retries go before new tasks |
| `--no-retry-codes L` | exit codes that never retry |
| `--at-most-once` | `delivery = at_most_once` (file 09) |
| `--halt-on-fail N\|P%`, `--halt-mode drain\|now` | stop the run after N failures or P percent; mode `drain` is the default (file 09) |
| `--group N`, `--continue-groups` | the group of the tasks; open the next group when the current one is terminal (file 09) |
| `--run-timeout D` | wall limit of the whole run; exit 124 |
| `--rate N` | at most N task starts per second for the run (file 10) |
| `--batch-wait D` | the longest wait of a partial batch of input lines before it is sent; default 200 ms |
| `--file SRC:DST`, `--bin PATH`, `--dir PATH`, `--shared-fs` | staging (file 15) |
| `--outputs GLOB` | output files to return (file 15) |
| `--results DIR`, `--durable-results` | per-task result directories (file 15) |
| `--pin-outputs` | keep the output blobs of the run from the sweep |
| `-o`, `--output FILE`, `-e`, `--errors FILE` | write task stdout, task stderr to FILE |
| `--ordered` | print output in input order |
| `--line-buffer` | write each line when it arrives |
| `-f`, `--failures FILE\|-` | write the input lines of failed tasks |
| `--joblog FILE` | one TSV line per ended task |
| `--progress`, `--no-progress` | the progress line with rate and ETA; default on a terminal |
| `--jsonl` | one result object per task on stdout |
| `--db FILE`, `--durability L` | keep the run in a store file; level `strict`, `batched` or `memory` (file 11) |
| `--name NAME` | the run name; `x` in a store file defaults to `x` |
| `--resume`, `--retry-failed`, `--retry-lost` | section 6.4 |
| `--key K` | task keys `K.<index>` (file 17) |

Only on `submit`: `--wait` (block, print and exit as `x`; `--wait-timeout D` bounds the wait), `--hold`, `--array A:B[:S]`, `--priority P`, `--weight W`, `--max-running N`, `--not-before T`, `--deadline T`. Later: `--speculate` (file 24).

### 6.2 HyperShell flags

Each HyperShell flag of `hs cluster` and `hsx` parses. `alias`: accepted with no message. `warn`: accepted, one line on stderr. `refuse`: exit 64 with the hint. The full verdict list is in file 20; GNU parallel and `xargs` forms are in file 20, section 9.

| HyperShell | Verdict | podswarm |
| --- | --- | --- |
| `--max-retries` | alias | `--retries` |
| `--num-threads`, `--num-tasks` | alias | `-N` |
| `-w`, `--bundlewait` | alias | `--batch-wait` (on `x` and `submit` only) |
| `-c`, `--cores`, `-m`, `--memory` | alias | `--needs cores=N`, `--needs mem=SIZE` |
| `-C`, `--client-cores` | alias | `-N` |
| `-T`, `--timeout` | alias | `--idle-exit` of the started workers (on `x` and `join` only) |
| `-W`, `--task-timeout`, `--template`, `-f`, `--failures`, `-d`, `--delay-start`, `-g`, `--group`, `--ssh-args`, `--remote-exe`, `--launcher` | same | same |
| `-S`, `--signalwait`, `-R`, `--ratelimit`, `--eager` | alias | `--kill-grace`, `--rate`, `--retry-first` |
| `-H`, `--bind`, `-p`, `--port` | alias | `--listen HOST:PORT` |
| `-E`, `--env NAME` | alias | `--env NAME` |
| `--ssh HOSTS`, `--ssh-group G` | alias | `--on HOSTS` (ranges `node[01-32]` expand), `--on @G` |
| `--mpi` | alias | `--launcher mpirun` |
| `--zone Z` | alias | `--worker-tag zone:Z` |
| `--restart` | alias | `--resume` (needs `--db` or `--joblog`) |
| `--print` | alias | `--failures -` |
| `-b`, `--bundlesize`, `-M`, `--client-memory`, `-Q`, `--poll`, `--capture`, `--monitor`, `--no-confirm`, `--initdb`, `--no-db` | warn | "ignored: not needed in podswarm" |
| `-A`, `--autoscaling`, `-F`, `-P`, `-I`, `-X`, `-Y`, `--min-size`, `--max-size`, `--factor` | refuse | "use podswarm coord --scale-hook" |
| `--forever`, `--repeat`, `--update` | refuse | "use podswarm coord, --key or --resume" |
| `--no-tls`, `--tls-key`, `--tls-cert`, `--tls-ca`, `-k`, `--auth` | refuse | "keys never go on a command line; TLS is pinned by the invite" |

### 6.3 Behaviour

* **Input.** One task per line; blank lines are skipped. A `#` is part of the line. A trailer that matches `#\s*(PODSWARM|HYPERSHELL):?` followed by `k:v` words sets `group`, `cores`, `mem`, `timeout`, `key` and tags of that task, each capped by the quota and the worker policy (file 09). An empty input exits 0 at once. When stdin is a pipe, the run waits until the pipe ends.
* **Output grouping.** A task's stdout is written in one piece when the task ends, so two tasks never mix inside a line. Each line is the full task output, with no cap; the caps of file 12 apply only to what an authority stores. `--line-buffer` writes each line on arrival; a partial line is cut at 64 KiB and written with no newline. `--ordered` follows input order; output held behind a slow task spills to `$TMPDIR` above 64 MiB. A task's stderr goes to stderr. `--jsonl` puts both in one object per task.
* **Job log.** The header is `Seq Host Starttime Runtime Send Receive Exitval Signal Command Outcome Attempt`: the GNU parallel columns plus `Outcome` and `Attempt`.
* **Listen.** With `--listen` or `--launcher` the home listens for this run only. It writes a one-run invite to a 0600 file in the runtime directory, prints the join command without the token on stderr, gives the token to started workers on a descriptor, and revokes the invite and closes the listener at the end of the run. `:PORT` means all interfaces, IPv6 and IPv4.
* **Ctrl-C.** The first `SIGINT` cancels the run, ends the started workers with `bye`, and exits 130.
* **Store file.** With `--db` the run prints `run: NAME` on stderr at start and at end.

### 6.4 Resume

The key of a task is the BLAKE3 of the expanded command, the group and the sorted tags, in lowercase hex, then `.`, then the occurrence of that value in this input (0 for the first), so equal lines stay separate tasks. `--key K` replaces it with `K.<index>`.
* `--db FILE --resume`: join the run of that name; skip each line whose task `succeeded`; run `waiting`, `ready`, `leased` and `running` tasks again after their old attempts are fenced; run `failed` and `cancelled` tasks again only with `--retry-failed`, and `lost` ones only with `--retry-lost`. A task in the file whose key is not in this input is counted on stderr and left as it is.
* `--joblog FILE --resume`: no store. Read FILE, compute the key from each `Command` and its occurrence, skip keys with `Outcome` `succeeded`, and append new lines. `--retry-failed` runs failed lines again.

### 6.5 Exit code of `x`, `submit --wait` and `wait`

This section is the home of these codes; files 17 and 19 copy them.

| What happened | Exit |
| --- | --- |
| Each task succeeded, or the input is empty | 0 |
| One or more tasks did not succeed | 1 |
| The wait ended first: `--wait-timeout` of `wait` or `submit --wait` (the run goes on), or `--run-timeout` of `x` (the run is cancelled) | 124 |
| An interrupt (`SIGINT`) | 130 |
| A failure of podswarm | the code of its class in the table of file 19 |

## 7. Templates

There is no `eval`, no interpreter and no shell expansion inside a token. The submitter expands each line before it queues a task, with the same code as the worker (`tmpl = 1`, file 05). A bad token fails the run with exit 64 before anything is queued.

| Token | Value |
| --- | --- |
| `{}` | the input line, raw |
| `{.}` | the directory part of the line (HyperShell; not the GNU extension strip) |
| `{..}` | the directory of that directory |
| `{/}`, `{/-}` | the base name; the base name without its extension |
| `{-}` | the line without its extension |
| `{+}`, `{++}` | the extension with the dot, without the dot |
| `{q}` | the line as one POSIX single-quoted word (= `{\|q}`) |
| `{N}`, `{N:M}` | field N, or fields N to M, 1-based, split on white space with shell quotes honoured |
| `{#}` | the 1-based index of the task in the run |
| `{%}` | the slot of the attempt, 1-based (GNU form) |
| `{slot}`, `{slot_count}` | the slot, 0-based, and the slot count (HyperShell 2.9; also `TASK_SLOT`, `TASK_SLOT_COUNT`) |
| `{key}` | a `--from-json` field or a tag of the task |
| `{{`, `}}` | a literal brace |

`{%}`, `{slot}` and `{slot_count}` are known only at the start of the attempt, so the worker expands them; every other token is expanded at submit.

* **Grammar.** A brace group is a token only when its text is exactly one of: empty, `.`, `..`, `/`, `/-`, `-`, `+`, `++`, `q`, `#`, `%`, `slot`, `slot_count`, an integer `N`, `N:M`, or a name of `[A-Za-z_][A-Za-z0-9_.-]*`, with an optional suffix `|q`. A `{` right after `$` is never a token (`${HOME}`). Any other group (`{print $1}`, `{1..5}`, `{"a":1}`) is literal text. A built-in token wins over a field of the same name.
* **Names.** A name that is a `--from-json` field must exist in every record, else exit 64. A name that no task of the run has is literal text, with one warning per run on stderr. `{N}` above the field count of a line is exit 64.
* **Quote modifier.** `|q` makes the value one POSIX single-quoted word (`'` becomes `'\''`). In `--argv` mode `|q` is exit 64, because a token is already one argv element. A shell template with `|q` or `{q}` needs a Unix shell: it adds `needs.os` of the Unix systems unless `--os` is given, and an `--os` that holds `windows` is exit 64 with `quoting for cmd is not supported; use --argv`.
* **Quoting.** In shell mode (the default, as HyperShell) a token is put in raw: an input line that holds `; rm -rf ~` runs it. In `--argv` mode a token stays inside one argv element and cannot inject. Use `--argv` or `{token|q}` for input that is not yours. A file name with a newline needs `-0`.
* **No token.** A template with no token gets ` {}` appended: `podswarm x gzip` runs `gzip LINE`.

## 8. Look and change

```
podswarm ls [tasks|runs|workers] [SELECTOR] [--failed|--succeeded|--remaining|--cancelled] [--fields F,...]
            [--order-by F] [--desc] [--limit N] [--count] [--format table|csv] [--tag-keys] [--tag-values K]
podswarm show ID [--attempts] [--stdout] [--stderr] [--field F]
podswarm logs TASK [--attempt N] [--stream out|err] [-f]
podswarm watch [--run R] [--type T,...] [--since SEQ]
podswarm get RUN DIR [--flat] [--durable-results]
podswarm wait RUN|TASK [--wait-timeout D] [--status] [--return] [--info]
podswarm pull [HOST] PATH...
podswarm cancel SELECTOR
podswarm retry SELECTOR [--failed|--lost|--cancelled] [--fresh] [--force]
podswarm update SELECTOR --hold|--release|--tag K:V|--untag K|--priority P|--pause|--unpause|--pin|--unpin|--purge
```

* **Selector.** `[ID...] [--run R] [--tag K:V]... [--where EXPR]... [--state S] [--group N] [--worker W] [--all]`. Parts combine with AND. `EXPR` is `FIELD OP VALUE` with `OP` one of `== != >= <= > < ~` (`~` is a regular expression) over the fields of `ls --fields`. `-w` is a short form of `--where` on these verbs.
* `cancel`, `retry` and `update` refuse an empty selector with exit 64 unless `--all` is given, take `--dry-run` (print the ids and the count), and ask once on a terminal unless `--yes`.
* `ls` on a terminal refuses more than 1,000 rows without `--all`, `--limit` or `--count`. `--json` pages with `next` (file 17).
* `show` prints `late_ok` with the attempt number (file 09) and environment names, never values.
* `retry --force` is needed for a task with `late_ok`. `retry --fresh` ignores the checkpoint of the task (file 15).
* `update --pause` stops new offers of a run with `paused_by = admin` (file 17). `--pin` keeps the output blobs of the run. `--purge` deletes whole runs and needs `--yes`.
* `wait --return` exits with the exit code of the one task. `--status` prints the final state; `--info` prints `show`. `--wait-timeout D` stops the wait, not the run, and exits 124 (section 6.5).
* `pull` copies each PATH that stayed in the warm workspace of HOST (owned directories, kept paths) to the same path of the caller's tree, with the rules of `--pull` (file 06). With no HOST it takes the machine of the last run of this workspace. `--pull GLOB` and `[view] pull` do the same at the end of each run.
* `logs -f` follows a running task; a slow reader never stops the task (file 05).

## 9. Machines

```
podswarm pool add NAME ROAD [--tag T] [--trust own|shared] [--cell C] [--slots N] [--res K=N] [--no-auto]
podswarm pool ls [SEL] | rm NAME | probe [SEL] [--no-copy] | import-ssh [--include G] [--exclude G] [--file PATH]
podswarm forget HOST [--yes]
podswarm join [wss://HOST[:PORT]] @FILE|-|--invite-fd N [WORKER FLAGS]
podswarm workers ls [--pending] [SEL] | show W | drain W|--tag T|--all [--now] | undrain W|--tag T|--all
                 | revoke W | approve W|--all-pending | tag W +K:V -K
podswarm bootstrap HOST...|--hosts-file FILE --join @FILE [--parallel N] [--if-present skip|replace]
podswarm each [--on SEL] [--tag T] -- CMD [ARGS...]
```

* `pool` is defined in file 08, section 1.4. `pool add NAME ROAD` with a `wss://` or `psw1s.` road writes a `[cell.NAME]` entry (a swarm cell) instead of a machine.
* `forget` opens the road, sends `bye` to a lingering worker, and removes the binary cache, the content cache, the probe cache and the free run directories (file 04); on the caller it makes a new host salt (file 13) and drops held view items after one confirmation (file 06).
* `join` runs a worker that dials out and stays (file 04, section 14). The token comes from `@FILE`, stdin, `--invite-fd N`, or `PODSWARM_INVITE` on the launcher path only (file 16). The worker prints its `wid` and its key fingerprint on stdout after `ready`. `--detach`: the parent prints them after `ready`, then exits 0; the worker writes `<state>/log/worker.log`. `--ensure` starts a worker only when the state lock is free (for cron).
* `workers drain --now` cancels the running attempts after `kill_grace_s`. Signals of a `join` worker: `SIGUSR1` drain; `SIGUSR2` drain, then kill after the grace; `SIGTERM` drain now; `SIGHUP` reopens the log.
* `bootstrap` follows file 04, section 14: probe, copy, `self verify`, keep `podswarm.prev`, start, roll back when the worker is not `ready` in 60 s. The token goes on a pipe, never in a command line. It prints one line per host (`--json`: `{host, outcome, exit, detail}`) and exits 0 when every host started, else 1.
* `each` is defined in file 08, section 7, and its queue rule in file 10. It exits 0 when every attempt exited with a code of `ok_codes`, else 1.

| Worker flag (`join`) | Meaning | Owner |
| --- | --- | --- |
| `--name N`, `--tag T` | worker name; requested tags | 16 |
| `--slots N`, `--resource K=N`, `--time-limit D` | slots; named resources; lifetime | 08 |
| `--idle-exit D`, `--delay-start D` | exit when idle; delay before the first dial (negative: random up to that size) | 10 |
| `--state DIR`, `--state-on-network-fs` | state directory; allow a network file system | 12 |
| `--policy FILE` | the worker policy file (default `worker.toml`) | 16 |
| `--lite`, `--containment R`, `--background`, `--nice N`, `--pin-slots`, `--shell PATH` | process model and scheduling | 12 |
| `--max-kbps N`, `--notice SPEC` | cap of blob traffic; preemption notice source | 15 |
| `--repin`, `--same-user-as-coordinator` | pins from a new token; the uid rule | 16 |
| `--detach`, `--ensure` | as above | 18 |

A far worker of a session takes the same values from its pool entry (file 08).

## 10. A swarm

```
podswarm coord [--state DIR] [--listen ADDR] [--durability strict|batched] [--detach] [--allow-temp-state]
               [--fast-start] [--scale-hook CMD]
podswarm coord stop | status | check | backup --to FILE [--verify] | restore FILE | gc [--vacuum]
               | logs [-f] [--lines N] | resend DELIVERY
podswarm invite new --out FILE|- [--uses N] [--ttl D] [--tag T]... [--max-cores N] [--max-slots N]
               [--max-boundary B] [--approve] [--worker-ttl D] [--ephemeral]
podswarm invite ls | revoke ID [--cascade]
podswarm submitter add KEY|FINGERPRINT [--name N] [--scopes S,...] [--routes R,...] [--quota K=V]... [--id-aud P]...
podswarm submitter ls | rm FINGERPRINT
podswarm key new [--out FILE] [--for mcp] | show [FILE] | token --aud URL
podswarm id export DIR
podswarm org key new [--out FILE] | issue MEMBER --scopes S --cells C --days N
podswarm org trust KEY --name N --scopes S --routes R --max-life D [--allow-admin] | untrust KEY | revoke MEMBER
```

* `coord` runs in the foreground. `--detach` re-executes, takes the lock, calls `setsid`, writes `<state>/log/coord.log`, prints one JSON line with the pin and the listen addresses, and exits 0. `--listen :PORT` means all interfaces, IPv6 and IPv4; a refused bind exits 69 and names the port rule of file 19. Without `--listen` the coordinator has only its local socket. The state directory, the levels, `check`, `backup`, `restore` and `gc` are in file 11. `--scale-hook CMD` sets CMD as the hook of the event `scale.tick` (file 17, section 5). `resend` sends a stored webhook delivery again (file 17).
* `invite new` needs `--out`: FILE is made with `O_EXCL` at mode 0600; `-` writes to stdout. It warns when `--uses` is above 1 and `--approve` is not given. The rules are in file 16, section 7.
* `submitter add` prints the connect string `psw1s.` on stdout. A new key has the scopes `read` and `submit` unless `--scopes` names others (file 16, section 8).
* `key new` makes an Ed25519 key at mode 0600, refuses to overwrite, and prints its fingerprint. `--for mcp` makes the separate key of an MCP profile (file 17). `key token --aud URL` runs inside a task and prints a run identity token for that audience (file 17, section 6).
* `id export DIR` writes the two static files of the run identity issuer: the discovery document and the key set of the coordinator token key. Any HTTPS site that serves them at `id.issuer` is the issuer (file 17, section 6).
* `org` is defined in file 16, section 9.

## 11. Extend

```
podswarm mcp [--profile NAME] [--workspace DIR]
podswarm skill [--install DIR] [--llms|--llms-full|--commands|--schema KIND]
podswarm plugin ls | test --kind ckpt|admit|road -- PROGRAM [ARGS...]
podswarm checkpoint save [TASK] [--label L] [--pin] | ls TASK | show NAME | pin NAME | unpin NAME
                    | rm NAME | export NAME DIR | import DIR TASK
podswarm usage [--since SEQ|TIME] [--by submitter|run|tag:K|boundary]
```

* `skill` prints `SKILL.md`; `--install DIR` writes `DIR/podswarm/SKILL.md`; `--llms` and `--llms-full` print `llms.txt` and `llms-full.txt`; `--commands` lists each verb, its flags and the `kind` of its output; `--schema KIND` prints the JSON Schema of one `kind` (file 17, sections 1 and 3).
* `plugin test` runs the conformance suite of one plugin kind and prints the suite version that passed (file 17, section 7).
* `checkpoint save` with no TASK runs inside a task and talks to its worker on `TASK_SOCK`. With TASK it sends `ckpt_save`, and the authority asks the worker with `ckpt_req`. Both return the name after the commit (file 15, section 11). `pin` and `unpin` send `ckpt_pin`; `import DIR TASK` sends `ckpt_import`, and TASK resumes from the checkpoint (file 15, section 11.7).

## 12. Plumbing

```
podswarm doctor [HOST] [--shield] [--json]
podswarm config get KEY | set KEY VALUE | path | edit
podswarm self fetch [--target T]... [--all] | verify SHA256 | install-aliases [--yes]
podswarm autostart add|rm [--role worker|coord]
podswarm version [--json]
podswarm completion bash|zsh|fish
podswarm bench [NAME]
podswarm holder status|stop
```

* `doctor` prints one line per check: `ok`, `fail` with the cause, or `unknown`. Local rows: the probe of `pod-hostprobe` (file 12), the state and runtime directories and their modes, the config files. With HOST: the road, the far probe, the view rungs (file 06), the shield rows with `--shield` (file 13), `StrictHostKeyChecking` and logind `KillUserProcesses` (file 04). With `--coordinator`: the pin, the handshake and `ready`. A listen check binds a random port on the interface of the listen address, so a running coordinator does not make it fail.
* `config` reads and writes the user file only, and keeps its comments. `path` prints each file that applies, in precedence order (file 19).
* `self fetch` fills the binary cache with the release binaries of other targets, after the signature and hash checks of file 16. `self verify SHA256` hashes the running file, checks that its directory is owned by the uid, mode 0700 and not a symbolic link, and exits 0 on a match, 65 on a hash mismatch, 77 on a bad directory; bootstrap runs it (file 04).
* `holder status` prints the holder of this user: version, roads, links, attempts, idle time. `holder stop` sends `bye` on each link and ends it.

| `autostart add` on | What it writes |
| --- | --- |
| Linux with systemd | `~/.config/systemd/user/podswarm-ROLE.service` with `Restart=on-failure`, `RestartPreventExitStatus=78`, `KillMode=control-group`, `Delegate=yes`; `systemctl --user enable --now`; `loginctl enable-linger`. When linger is refused it prints "starts at login only". |
| Linux with no systemd | crontab `@reboot podswarm join --ensure ...` and a 5-minute `join --ensure` line, because cron does not restart a dead process. It reports when no cron daemon runs. |
| macOS | `~/Library/LaunchAgents/` agent with `RunAtLoad` and `KeepAlive` on failure. An agent starts at login, not at boot; a start at boot needs root. |
| Windows | `schtasks /Create /SC ONLOGON` for the user, with no administrator right. |
| Android (Termux) | a script in `~/.termux/boot/` that calls `termux-wake-lock` first; needs the Termux:Boot app. It prints the note on the phantom process limit of Android 12 and later. |

`autostart rm` removes what `add` wrote.
