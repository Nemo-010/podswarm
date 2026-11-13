# 19. Reference: settings, files, exit codes, recipes

This file lists every setting with its scope, type, range and home file, the configuration files and their precedence, the environment variables, the directories, the exit codes and the log levels. It ends with four walkthroughs and a few recipes. The default of each setting is in its home file. The verbs and flags are in file 18.

## 1. Settings

Scopes: **home** (the home of a session; `[home]` of the user config), **coord** (a coordinator; `[coord]`), **authority** (both), **worker** (`[worker]` of the config of the worker's user, or a `join` flag), **shape** (a shape field; `[defaults]`, a flag or `--shape`), **run** (one command; a flag or `[defaults]`), **pool entry** (`[host.NAME]` of `pool.toml`, file 08), **link** (each `pod-link` link), **submitter** and **invite** (rows of the store, file 16), **profile** (`[mcp.profile.NAME]`), **job** (file 24). A name with a dot is a key of a table (`ssh.max_sessions` is `max_sessions` in `[ssh]`). "Fixed" is a constant, listed so that a builder finds it.

| Key | Scope | Type | Range | File |
| --- | --- | --- | --- | --- |
| `hold_s` | home | seconds | 0 to 86,400 | 04 |
| `linger_s` | home, pool entry | seconds | 0 to 86,400 | 04 |
| `ssh.max_sessions` | home, pool entry | count | 1 to 10 | 04 |
| `ssh.control_persist_s` | home | seconds | 0 to 3,600 | 04 |
| `ssh_args` | home, pool entry | list of strings | not the refused flags of file 04 | 04 |
| `jump`, `remote_exe` | pool entry | string; path | | 04 |
| `frame_size` | link | bytes | 1 KiB to 1 MiB | 04 |
| `stream_window`, `link_window` | link | bytes | 64 KiB to 8 MiB; 256 KiB to 8 MiB | 04 |
| `max_streams` | link | count | 1 to 4,096 | 04 |
| `keepalive_s`, `dead_after_s` | link | seconds | above 0; above `keepalive_s` | 04 |
| `hb_s`, `grace_s` | authority | seconds | 2 to 60; 1 to 60 | 05 |
| `e_max` | authority | percent | 0.01 to 5 | 05 |
| `rtt_max` | authority | seconds | 1 to 30 | 05 |
| `silence_s` | shape | seconds | 30 to 86,400 | 05 |
| `kill_grace_s` | shape | seconds | 0 to 600 | 05 |
| `timeout_s` | shape | seconds or none | 1 and up | 05 |
| `capture_max` | shape | bytes per stream | 0 to 65,536 | 05 |
| `io` | shape | `capture`, `attached` | | 05 |
| `pty`, `merge`, `shared_fs`, `inherit_env`, `shell_always` | shape | bool | | 05, 12 |
| `ok_codes` | shape | list of exit codes | 0 to 255 | 05 |
| `tmpl` | shape | integer | 0, 1 | 05 |
| `view` (`--view`) | run, shape | enum; default per verb in file 06 | `auto`, `fuse`, `fuse-userns`, `trap`, `sync`, `none` | 06 |
| `view_sync_rtt_ms` | home | ms | 0 to 10,000 | 06 |
| `view_ws_keep_d`, `view_log_keep_d` | worker, home | days | 1 to 365; 1 to 90 | 06 |
| `view_put_max_mib`, `view_wb_max_mib` | home; a workspace may lower it in `[view]` | MiB | 1 to 65,536; 1 to 1,048,576 | 06 |
| `view_del_max`, `view_del_max_pct`, `view_ops_max` | home; a workspace may lower it in `[view]` | count; percent; count | 0 to 10,000,000; 0 to 100; 1 to 10,000,000 | 06 |
| `[view] pull`, `keep`, `protect` | home, workspace (add only) | glob lists | | 06 |
| `spread` | run | enum | `off`, `on` | 07 |
| `spread_min_cpu_ms`, `spread_hold_ms`, `spread_publish_max_ms` | home | ms | 0 to 60,000; 0 to 60,000; 10 to 60,000 | 07 |
| `spread_anchor_reserve` | home | cores | 0 to the cores of the anchor | 07 |
| `spread_grant_s` | home | seconds | 1 to 3,600 | 07 |
| `spread_table_max` | home | count | 1,024 to 1,000,000 | 07 |
| `spread_unknown_fds`, `spread_cpus`, `spread_retry`, `spread_tools` | home | enum | `local`, `drop`; `pooled`, `anchor`; `auto`, `never`; `anchor`, `member` | 07 |
| `road`, `tags`, `slots`, `auto`, `uplink`, `source` | pool entry | string; list; count; bool; bool; string | file 08, section 1.1 | 08 |
| `cell`, `region`, `juris` | pool entry, run | names | `[a-z0-9-]`, at most 32 | 08 |
| `res` (`--resource`) | pool entry, worker | map of name to count | 16 names; 1 to 1,000,000 | 08 |
| `time_limit` (`--time-limit`) | pool entry, worker | duration | 1 s to 365 days | 08 |
| `local`, `on` | run | bool; selector | | 08 |
| `local_under_ms`, `place_wait_ms` | home | ms | 0 to 10,000 | 08 |
| `place_rtts`, `place_tty_rtts`, `place_tie_pct` | home | count; count; percent | 0 to 100; 0 to 1,000; 0 to 50 | 08 |
| `assume_cpu_ms`, `dial_default_ms`, `boot_default_ms`, `view_cold_ms` | home | ms | 1 to 86,400,000; 1 to 60,000; 1 to 600,000; 0 to 600,000 | 08 |
| `dial_max`, `roads_max` | home | count | 1 to 256; 1 to 1,024 | 08 |
| `road_idle_s` | home | seconds | 0 to 86,400 | 08 |
| `calib_ms` | worker | ms | 20 to 2,000 | 08 |
| `learn_alpha`, `learn_ttl_days`, `learn_max` | home | ratio; days; count | 0.01 to 1; 1 to 3,650; 64 to 1,000,000 | 08 |
| `[residency]` `allow_cell`, `deny_cell`, `allow_region`, `allow_juris`, `shield_min`, `boundary_min` | workspace, pool file | lists; levels | restrict only | 08 |
| `pool_max` | fixed | count | | 08 |
| `retries` | shape | count | 0 to 1,000 | 09 |
| `retry_delay_s` | shape | seconds | 0 to 3,600 | 09 |
| `max_lost` | shape | count | 0 to 1,000 | 09 |
| `delivery` | shape | enum | `at_least_once`, `at_most_once` | 09 |
| `priority` | shape, run | integer | -100 to 100 | 09 |
| `no_retry_codes`, `tags` | shape | list; map | exit codes; the tag grammar | 09 |
| `needs.*` | shape | file 09, section 4 | | 09 |
| `weight`, `max_running` | run | count | 1 to 100; 1 and up | 09 |
| `halt_on_fail`, `halt_mode`, `continue_groups` | run | N or P%; enum; bool | N 1 and up, P 1 to 100; `drain`, `now` | 09 |
| `max_attempt_s` | authority | seconds | 3,600 to 31,536,000 | 09 |
| `depth_min_s`, `depth_max_s` | authority | seconds | 0.1 to 10; 1 to 60 | 10 |
| `bundle_max`, `offer_bytes_max` | authority | count; bytes | 1 to 1,000; 16 KiB to 1 MiB | 10 |
| `hold_max_s`, `park_s` | authority | seconds | 1 to 3,600; 1 to 60 | 10 |
| `rtt_default_ms` | authority | ms | 1 to 10,000 | 10 |
| `result_rows_max`, `result_bytes_max` | worker | count; bytes | 1 to 1,000; 4 KiB to 1 MiB | 10 |
| `backpressure_age_ms`, `backpressure_events` | coord | ms; count | 10 to 10,000; 1,024 to 1,048,576 | 10 |
| `drr_quantum`, `expiries_per_step` | authority | count | 1 to 10,000; 100 to 100,000 | 10 |
| `reserve_after_s`, `assume_time_s` | authority | seconds | 1 to 3,600; 1 to 604,800 | 10 |
| `drain_margin_s` | worker, authority | seconds | 0 to 3,600 | 10 |
| `idle_exit_s` (`--idle-exit`) | worker | seconds | 0 to 604,800 | 10 |
| `accept_rate`, `max_conns` | coord | per second; count | 10 to 100,000; 64 to the descriptor limit | 10 |
| `rate` (`--rate`) | run | per second | 1 and up | 10 |
| `retry_first` (`--retry-first`) | run | bool | | 10 |
| `class_max` | fixed | count | | 10 |
| `durability` | coord, run | enum | `strict`, `batched` (coord); also `memory` (`x`) | 11 |
| `db` | run | path | | 11 |
| `state_dir`, `allow_temp_state`, `fast_start` | coord | path; bool; bool | a local directory | 11 |
| `retain_days`, `retain_output_days`, `retain_events_days`, `blob_ttl_days` | coord | days | 1 to 36,500; 0 to 36,500; 1 to 36,500; 0 to 36,500 | 11 |
| `max_db_bytes` | coord | bytes | 64 MiB and up | 11 |
| `limits.mem_mib`, `limits.as_mib`, `limits.fsize_mib` (`--cap`) | shape | MiB | 1 and up | 12 |
| `limits.cpu_s`, `limits.pids` | shape | seconds; count | 1 and up | 12 |
| `limits.nofile` | shape | count | 16 to the hard limit | 12 |
| `confine.read`, `confine.write`, `confine.exec` | shape | path lists | at most 64, each at most 1,024 bytes | 12 |
| `confine.connect`, `confine.bind`, `confine.udp`, `confine.unix` | shape | port lists; bool; bool | 0 to 65,535 | 12 |
| `lite`, `containment`, `background`, `nice`, `pin_slots`, `shell`, `state_on_network_fs` | worker | bool; rung; bool; integer; bool; path; bool | `nice` 0 to 19; rungs of file 12 | 12 |
| `disk_reserve` | worker | size or percent | 0 to 50 percent | 12 |
| `spill_max` | worker | bytes per attempt | 0 to 1 GiB | 12 |
| `shield` | run, shape, pool entry | enum | `none`, `private`, `guest`, `sealed` | 13 |
| `trust` | pool entry, cell | enum | `own`, `shared` | 08 |
| `shield_require` | run, pool entry | list | `swap-locked` | 13 |
| `area_max` | pool entry | MiB | 64 to the RAM of the host | 13 |
| `area` (`--area`) | run, pool entry | enum | `auto`, `memory`, `sealed` | 13 |
| `cache` (`--no-cache`), `leftovers` (`--no-trace`) | run, pool entry | bool; enum | `bin`, `none` | 13 |
| `guest_tcg`, `seal_smt`, `seal_chip`, `seal_tcb_floor` | pool entry, run | bool; bool; hex; enum | `release`, `ack-old` | 13 |
| `env_allow` | run, profile | name list | | 13 |
| `net` | shape, run | policy string | file 14, section 1.1 | 14 |
| `net_home_allow` | home | CIDR list | | 14 |
| `net_podnet`, `net_podnet_copy` | worker; home | path or `auto`, `off`; bool | | 14 |
| `blob_max_mib`, `max_blob_bytes` | coord | MiB; bytes | 1 and up | 15 |
| `blob_streams_max` | authority | count | 1 to 1,024 | 15 |
| `fanout_warn`, `fanout_max` | home | bytes | | 15 |
| `url_fetch_s` | worker | seconds | 10 to 86,400 | 15 |
| `max_kbps`, `notice` | worker | kbit/s; source | 0 and up; `aws-spot`, `file:PATH`, `signal:SIG` | 15 |
| `ckpt_chunk_over`, `ckpt_min_interval_s` | worker; authority | MiB; seconds | 8 to 4,096; 0 to 3,600 | 15 |
| `ckpt_after_end_days`, `ckpt_after_fail_days` | coord | days | 0 to 3,650 | 15 |
| `checkpoint.*`, `capture_blob` | shape | file 15, section 11.2 | | 15 |
| `max_unauth`, `unauth_per_prefix` | coord | count | 16 to 65,536; 1 to 65,536 | 16 |
| `tls_handshake_s`, `http_head_s`, `hello_s`, `ready_s` | coord | seconds | 1 to 60; 1 to 30; 1 to 30; 2 to 120 | 16 |
| `preauth_bytes`, `fail_per_prefix_min`, `ban_s` | coord | bytes; count; seconds | 1 MiB to 1 GiB; 1 to 10,000; 0 to 86,400 | 16 |
| `net_allow` | coord, worker policy | rules | CIDR and `host:port` | 16 |
| `uses`, `ttl`, `tags`, `max_cores`, `max_slots`, `max_boundary`, `approve`, `worker_ttl`, `ephemeral` | invite | file 16, section 7.3 | `uses` 1 to 1,000,000; `ttl` 1 min to 365 days | 16 |
| `max_queued`, `max_spec_bytes`, `max_output_bytes`, `max_blob_mib` | submitter | count; bytes; bytes; MiB | `max_queued` 0 to 2^32 | 16 |
| `max_ckpt_mib` | submitter | MiB | 0 and up | 15 |
| `cache_max` | worker, home | bytes | 1 GiB and up | 15 |
| `key_escrow` (`--key-escrow`) | run | bool | | 16 |
| `scopes`, `routes`, `id_aud` | submitter | lists | `read`, `submit`, `id`, `admin`, `verify` | 16 |
| `max_scopes`, `routes`, `max_life_s`, `allow_admin` | organisation trust entry | list; list; seconds; bool | `max_life_s` 3,600 to 31,536,000 | 16 |
| `allow_boundaries`, `allow_shell`, `max_cores`, `max_mem_mib`, `env_pass`, `deny_env`, `allow_abs_cwd`, `allow_unix`, `confine_allow_*`, `accept_submitters`, `plugin_allow`, `require_signed_by` | worker policy (`worker.toml`) | file 16, section 12 | | 16 |
| `hooks.timeout_s`, `hooks.max_inflight` | home, coord | seconds; count | 1 to 600; 1 to 64 | 17 |
| `hooks.scale_tick_s` (`coord --scale-hook`) | coord | seconds | 5 to 3,600 | 17 |
| `[[webhook]]` `name`, `url`, `aud`, `events` | coord | strings | `https`, or `http` to loopback | 17 |
| `id.issuer`, `id.audiences`, `id.ttl_s`, `id.max_ttl_s`, `id.alg` | coord | HTTPS URL of a site that serves the files of `id export`; list; seconds; seconds; `ES256` | `id.ttl_s` 60 to `id.max_ttl_s`; `id.max_ttl_s` 60 to 86,400 | 17 |
| `workspace`, `cells`, `juris`, `boundary_min`, `shield_min`, `max_timeout_s`, `timeout_s`, `wait_s`, `max_running`, `max_cores_running`, `max_tasks_per_call`, `max_calls_per_min`, `output_bytes` | profile | file 17, section 2 | file 17, section 2 | 17 |
| `plugin.timeout_s`, `[plugin.NAME] id` | home, coord, worker | seconds; `b3:` content id | 1 to 3,600 | 17 |
| `admit.plugin`, `admit.timeout_ms`, `admit.on_error` | coord | name; ms; enum | `admit.timeout_ms` 10 to 10,000; `refuse`, `allow` | 17 |
| `color` (`--color`) | run | enum | `auto`, `always`, `never` | 18 |
| `batch_wait` (`--batch-wait`) | run | duration | 0 to 60 s | 18 |
| `replicas`, `restart`, `backoff.*`, `crashloop.*`, `overlap`, `catch_up`, `tz` | job | file 24, section 1 | | 24 |
| `spec_max`, `speculate_*`, `backfill_margin`, `replica_wait_s` | authority | file 24 | | 24 |
| `require_signed_by`, `max_spec_age_s`, `unsigned_boundary_min`, `sandbox_idle_s` | worker | file 24 | | 24 |
| `audit_head_s`, the hub limits, `--master-key`, `--launcher`, `--size` | coord, hub | file 24 | | 24 |

## 2. Configuration files and precedence

| File | Where (directories in section 4) | Holds |
| --- | --- | --- |
| system file | `/etc/podswarm/config.toml`; `%ProgramData%\podswarm\config.toml` | the tables of the user file |
| user file | `C/config.toml`, or `PODSWARM_CONFIG` | `[defaults]`, `[home]`, `[worker]`, `[coord]`, `[ssh]`, `[view]`, `[hooks]`, `[[webhook]]`, `[id]`, `[admit]`, `[plugin.NAME]`, `[mcp.profile.NAME]`, `[export]` |
| pool file | `C/pool.toml` (file 08) | `[host.NAME]`, `[group.NAME]`, `[cell.NAME]`, `[exit.NAME]`, `[residency.path."PREFIX"]`, `[defaults]` |
| worker policy | `C/worker.toml` of the worker's user (file 16, section 12), or `join --policy FILE` | the policy keys |
| workspace file | `.podswarm.toml` in the working directory and each parent up to the Git root | `[defaults]` (settings of scope run and shape; never a cell or a road), `[residency]` (restrict only), `[view]` (add globs, lower thresholds) |

* **Precedence**, strongest first: the command line; the environment (`PODSWARM_*`); the workspace files, nearest first, for the keys that they may set; the user file and the pool file; the system file; the built-in defaults. A rule of `[residency]` and `[view]` never takes precedence: each file intersects or adds (file 08, file 06).
* `[defaults]` holds settings of scope **run** and **shape**. It may be in the user file or in the pool file. A key in both is a config error (exit 78) that names both files.
* A workspace file never sets a road, a pool entry, a cell, a coordinator, a pin, a key file, a worker policy, a state directory, a listener, a hook, a plugin, an MCP profile, a view allow entry, `net = "home"`, an `exit:` policy, a shield or a boundary below the user's. Such a key is an error that names the file and the key (file 16, section 11).
* A config directory, a state directory or a config file that another uid owns, or that group or others can write, makes the process refuse to start (exit 77). A workspace file of another owner, or writable by others, is ignored with one warning line.
* `[export]` and `PODSWARM_EXPORT_NAME` put `NAME` into the `env` of the shapes that this user submits (file 20). The variable deny list of file 13, section 5 still applies.
* A coordinator reads `[coord]` of the user file of its own user. `podswarm config path` prints each file that applies, in this order.

```toml
# C/config.toml: an example, not the defaults
[defaults]
retries = 1
timeout_s = 7200
shield = "private"

[home]
hold_s = 1800

[worker]
disk_reserve = "10%"

[hooks]
"run.end" = ["notify-send", "podswarm"]
```

## 3. Environment

| Variable | Read by | Meaning |
| --- | --- | --- |
| `PODSWARM_CONFIG` | every verb | path of the user file |
| `PODSWARM_COORDINATOR` | every verb | where a command connects (file 18, section 2.1) |
| `PODSWARM_STATE_DIR` | `coord` | the state directory of a coordinator (section 4) |
| `PODSWARM_INVITE` | `join` on the launcher path only | the token; read once, then removed (file 16) |
| `PODSWARM_LOG` | every process | the log level (section 6) |
| `PODSWARM_NONINTERACTIVE` | every verb | `1`: never prompt |
| `PODSWARM_PLUGIN_PATH` | every verb | directories of external subcommands and plugins (file 17) |
| `PODSWARM_EXPORT_NAME` | `x`, `submit`, `run` | `NAME` into the task `env` |
| `PODSWARM_<KEY>` | every verb | a setting of scope home, run or shape; KEY in capitals, a dot as `_` (`PODSWARM_HOLD_S=60`) |
| `NO_COLOR` | every verb | no colour when set and not empty |
| `HTTPS_PROXY`, `NO_PROXY` | `wss` roads, `self fetch` | through `pod-proxy` |
| `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, `XDG_RUNTIME_DIR`, `TMPDIR`, `APPDATA`, `LOCALAPPDATA`, `ProgramData` | every process | the directories of section 4 |
| `TERM`, `COLORTERM` | `run` with a pty | passed to the far side (file 12) |
| `SLURM_JOB_END_TIME`, `PBS_WALLTIME` | worker | its lifetime (file 10) |
| `SLURM_JOB_ID`, `PBS_JOBID`, `LSB_JOBID` | worker | a node-local state directory (file 12) |
| `TASK_SOCK` | `checkpoint save`, `key token` in a task | the socket of the worker (files 15, 17) |

podswarm sets for others: the `TASK_*` set of a task (file 12); `PODSWARM_VIEW` and `PODSWARM_HOME_PATH` (file 06); `PODSWARM_BIN`, `PODSWARM_PROTO`, `PODSWARM_CELL`, `PODSWARM_JSON`, `PODSWARM_CONFIG_DIR`, `PODSWARM_EVENT`, `PODSWARM_PLUGIN`, `PODSWARM_ROAD_TARGET` for plugins and hooks (file 17). No `PODSWARM_*` variable of the caller reaches a task (the deny list of file 13, section 5).

## 4. Directories

| Name | Linux, macOS, other Unix | Windows |
| --- | --- | --- |
| `C` config | `${XDG_CONFIG_HOME:-$HOME/.config}/podswarm` | `%APPDATA%\podswarm` |
| `S` state | `${XDG_STATE_HOME:-$HOME/.local/state}/podswarm` | `%LOCALAPPDATA%\podswarm\state` |
| `K` cache | `${XDG_CACHE_HOME:-$HOME/.cache}/podswarm` | `%LOCALAPPDATA%\podswarm\cache` |
| `R` runtime | `$XDG_RUNTIME_DIR/podswarm`, else `/tmp/podswarm-<uid>` | named pipes; files in `%LOCALAPPDATA%\podswarm\run` |

Each directory is mode 0700 and owned by the user.

| Role | Places |
| --- | --- |
| Home (the caller) | `C/config.toml`, `C/pool.toml`, `C/plugins/`, the user key `C/submitter.key` (`key new`), the MCP key `C/mcp.key`; `S/holder.log`, the learned table (file 08), the view index (file 06); `K/bin/<target>/` (file 04), `K/blobs/` (file 15); `R/home-<version>.sock` and `R/holder.lock` (file 04), the ssh control directory `R/s` (file 04). On Windows the holder is the pipe `\\.\pipe\podswarm-<user>-<version>`. |
| Far worker of a session | `K/bin/` (file 04), the run directory `R/w-<sid>` else `${TMPDIR:-/tmp}/podswarm-<uid>/w-<sid>` (file 04), the content cache and workspaces under `K` (file 06), else `/var/tmp/podswarm-<uid>/cache` on a network file system; at shield `private` and above the work area of file 13. |
| Worker of a swarm (`join`) | `S/worker-<hostname>` (file 12), or `${TMPDIR:-/tmp}/podswarm-<uid>-<jobid>-<hostname>` under a batch system; `S/worker-<hostname>/log/worker.log`; `K` for blobs; `R/tasks` or `<state>/tasks` for task directories (file 12); `C/worker.toml`. |
| Coordinator | `--state DIR`, else `PODSWARM_STATE_DIR`, else `S/coord`: `coord.db`, `coord.lock`, `blobs/`, `log/coord.log` (file 11); `R/coord.sock` (file 16); `C/master.key` for `secrets.1` (file 24). |

## 5. Exit codes

The codes 64 to 80 are the `pod_core::Class` values [EV-088]. The wire error code of each class is in file 05.

| Code | Class | Meaning | Verbs |
| --- | --- | --- | --- |
| 0 | | success; an empty input | all |
| 1 | | the run ended with a task that did not succeed; a machine or a host failed | `x`, `submit --wait`, `wait`, `each`, `bootstrap` |
| N | | the exit code of the command | `run`, `wait --return` |
| 64 | Usage | `bad_request`, `bad_state`, `wrong_cell`; bad flags, a bad token, an empty selector without `--all`, a prompt that cannot be shown, a secret as a flag value | all but `run` |
| 65 | | a hash mismatch | `self verify` |
| 66 | NotFound | `not_found`: an unknown run, task, worker, blob or attach id | all but `run` |
| 69 | Unavailable | a coordinator or a road that does not answer, a refused bind, a locked state directory, no binary with `--offline`, no worker within `--no-worker-timeout` | all but `run` |
| 70 | | `internal`: a defect, also a store divergence (file 11) | all but `run` |
| 75 | TempFail, Timeout | `busy` (also a rate or in-flight budget that is full for now), `attempt_live` | all but `run` |
| 76 | Protocol | a protocol error, `too_large` | all but `run` |
| 77 | Refused | `unauthorized`, `duplicate_identity`, `quota`, a file or directory with a wrong owner or mode | all but `run` |
| 78 | Config, Revoked | `revoked`, a bad config, a store newer than the binary, a state directory on a network file system, a revoked worker | all but `run` |
| 79 | Policy | `policy`, `needs_unsatisfiable`, `shield_unavailable`, `no_cell` | all but `run` |
| 80 | Unsupported | `unsupported`, a feature that is not built, an unknown target | all but `run` |
| 124 | | the wait ended first (`--wait-timeout` of `wait` and `submit --wait`, `--run-timeout` of `x`, file 18, section 6.5); for `run`, `--task-timeout` passed | `x`, `submit --wait`, `wait`, `run` |
| 126, 127 | | the program is not executable, or not found | `run` |
| 128 + N | | signal N ended the command | `run` |
| 130 | | interrupted by `SIGINT` | all but `run` |
| 255 | | a failure of podswarm itself; `--json` gives the class and its code above | `run` |

A unit file sets `RestartPreventExitStatus=78`, so a revoked or misconfigured worker does not restart.

The codes of `x`, `submit --wait` and `wait` have their home in file 18, section 6.5. The table above lists every error code of file 05, section 11.

A task in the state `held` (file 09) shows its reason in `ls` and `show`. The reasons are in file 09; `needs_key` means that the task waits for the data key of its run (file 15, section 11.10; D-126).

The outcomes and reasons of a result have their home in file 05, section 3; `show` and `--json` print them. Outcomes: `exited`, `signaled`, `timeout`, `spawn_failed`, `killed`, `cancelled`, `not_started`, `checkpointed`. Reasons: of `exited`, `output_failed`, `output_rejected`, `ckpt_failed`; of `signaled`, `mem_exceeded`, `cpu_exceeded`, `disk_full`, `area_full`; of `not_started`, `disk`, `needs_key`, or none; of `killed`, `self_fence`, `drain`, `orphan_cleanup`, `lifetime`; of `spawn_failed`, `bad_argv`, `isolation_refused`, `policy`, `input`, `shape`, `other`. A task that ends `failed` on its attempt cap has the reason `attempt_cap` (file 09).

## 6. Log levels

`error`, `warn`, `info`, `debug`, `trace`. `-q` gives `error`, no flag gives `warn`, `-v` `info`, `-vv` `debug`, `-vvv` `trace`; `PODSWARM_LOG=LEVEL` sets the same. A process writes its log to stderr. The holder writes `S/holder.log`; a detached coordinator or worker writes `log/coord.log` or `log/worker.log` in its state directory. `SIGHUP` reopens the log file; rotation is the job of the service manager or `logrotate`. A log line never holds a token, a key, a secret, an input line or task output (file 16).

## 7. Walkthroughs

### 7.1 The first minute: one command on a server you can ssh to

```
curl -fsSLo podswarm https://github.com/PodUtils/podswarm/releases/download/TAG/podswarm-x86_64-unknown-linux-musl
sha256sum podswarm                     # compare with SHA256SUMS of the release (file 16)
chmod 755 podswarm && mv podswarm ~/.local/bin/
podswarm run me@server.example -- uname -a
```

The first `run` starts the holder, opens ssh (ssh asks its questions once on this terminal), reads `uname -sm` of the server, copies the matching binary, starts a worker, and runs `uname -a` there. The exit code is the code of `uname`. [T] A-23: the first run reaches the command in under 5 s on a 20 Mbit/s link. Then:

```
podswarm self install-aliases --yes
psw pool add big me@server.example --trust shared
psw run big -- cargo build --release
psw run --pull target/release/app big -- cargo build --release
psw run big htop
psw doctor big --shield
psw forget big
```

The build reads the caller's tree through the view; `target/` stays on `big` and `--pull` copies the program back (file 06). `htop` gets a pty because the terminal is one. `trust = "shared"` gives shield `private` (file 13). `forget` removes what podswarm left on `big`.

### 7.2 Three machines and a spread build

These steps use the aliases of 7.1. On another machine, type `podswarm`.

```
podswarm pool add lab1 lab1 --trust own
psw pool add lab2 me@lab2.example --trust own
psw pool add pi4 pi@10.0.0.14 --trust own --slots 3
psw pool probe
psw pool ls
psw run -- cargo build --release
psw run --spread -- make -j64
```

`pool probe` copies the binary to each machine and records its cores, speed and probe rows. `run --` with no host picks the machine with the lowest estimated finish time (file 08); `-v` prints why. `--spread` runs each compiler that `make` starts on the member where it ends first; `pi4` has another architecture, so no process moves to it (file 07).

### 7.3 A batch over a pool

```
podswarm pool ls
ls *.mp4 | psw x --on lab1,lab2 -N 4 'ffmpeg -i {} {/-}.webm'
psw x --joblog sweep.tsv -r 1 'model --alpha {1} --beta {2}' params.txt
psw x --joblog sweep.tsv -r 1 --resume 'model --alpha {1} --beta {2}' params.txt
```

Each line is a task. The tasks read the `.mp4` files through the view and write each `.webm` back to this directory (file 06). The sweep writes a GNU-style job log; after a cut, `--resume` skips the lines that succeeded. The exit code is 1 when a task did not succeed.

### 7.4 A swarm: a coordinator, an invite, 100 workers, a submitter key, a queued run

On the coordinator host:

```
podswarm coord --listen :8443 --detach
podswarm invite new --uses 110 --ttl 30m --tag farm --out token.txt
podswarm self fetch --target aarch64-unknown-linux-musl
podswarm bootstrap --hosts-file hosts.txt --join @token.txt --parallel 32
podswarm workers ls
```

A user process cannot bind a port below 1024 on a default Linux host. Use a port above 1023 and let the firewall redirect 443 to it, or grant `cap_net_bind_service` to the binary, or lower `net.ipv4.ip_unprivileged_port_start`. A worker behind an HTTPS-only egress needs 443. `--uses` is above the host count so that a retried host finds a use; an enrolled host that retries spends none (file 16). `bootstrap` installs and starts a worker on each host over ssh (file 04, section 14). [T] A-13: 100 machines enrolled and running in under 300 s.

On your machine, then on the coordinator host, then on your machine:

```
psw key new
podswarm submitter add SHA256:FINGERPRINT --name me --routes farm
psw pool add farm psw1s.CONNECTSTRING
psw submit --cell farm --name sweep -r 2 --task-timeout 1h 'work {}' inputs.txt
psw wait --coordinator farm 1
psw ls --coordinator farm --run 1 --failed
psw retry --coordinator farm --run 1 --failed
```

`key new` prints the fingerprint. `submitter add` prints the connect string, which holds no secret. `pool add` with a connect string writes a swarm cell. `submit` prints the run id; the tasks wait in the durable store and run on the workers with the tag `farm`.

## 8. Recipes

Each recipe names the milestone that makes it run (file 22).

**Check what a shared server can protect, and leave nothing there.** M1
```
psw doctor big --shield
psw run --no-trace big -- make test
```

**One command on each machine.** M5
```
psw each --on lab1,lab2,pi4 -- df -h /
```

**Test shards with a time limit.** M2
```
seq 0 63 | psw x --on lab1,lab2 --run-timeout 30m -r 1 'make test SHARD={} SHARDS=64'
```

**A sweep that ships its program and returns its files.** M6 (M2 in a session)
```
psw x --cell farm --argv --bin ./model --outputs 'result-*.json' --results ./results \
      'model --alpha {1} --beta {2} --out result-{#}.json' params.txt
```

**A long run that moves to another machine when its machine goes.** M6
```
echo '{"checkpoint":{"exit_code":85,"every_s":1800}}' > ckpt.json
echo './train --state "$TASK_CHECKPOINT_DIR"' | psw submit --cell farm --shape ckpt.json -r 3
```

**A small board that dials out and starts at boot.** M5
```
podswarm join @token.txt --slots 2 --tag pi --max-kbps 512 --detach
podswarm autostart add --role worker
```

**A build matrix over operating systems.** M6; the Windows row from M10
```
printf '%s\n' 'linux x86_64' 'linux aarch64' 'macos aarch64' 'windows x86_64' \
  | psw x --cell farm --argv --os '{1}' --arch '{2}' --bin ./ci-script 'ci-script {1} {2}'
```

**Compute for an agent.** M6
```
psw skill --install ~/.config/agent/skills
psw mcp --profile default
```
The agent starts `podswarm mcp` on stdio with the profile of file 17; the profile bounds what it can do.

**A periodic job in a swarm.** M9 (jobs, file 24)
```
psw job add nightly --cell farm --kind periodic --schedule '17 3 * * *' -- ./scrape.sh
```

**Two regional cells, and a run that stays in one.** M9 (cells, file 08)
```
psw pool add eu psw1s.CONNECTSTRING_EU
psw pool add us psw1s.CONNECTSTRING_US
psw submit --cell eu --juris eu 'work {}' inputs.txt
```
A `[residency]` rule in `.podswarm.toml` can only narrow the cells; an empty result is `no_cell` (file 08).
