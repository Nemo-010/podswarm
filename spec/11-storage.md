# 11. Storage

This file defines the durable store of a coordinator and of `podswarm x --db FILE`, and the in-memory store of a session. It gives the schema, the write path, the durability levels, the checkpoint rule, recovery, generation, retention, backup and migration. The records and their states are in file 09, the messages that wait for a commit are in file 05, and the throughput model that uses the store bound is in file 10.

## 1. The `Store` trait

The scheduler actor of an authority (file 03) never touches SQLite. It sends **commands** to a store and gets **acknowledgements** back. A command carries a completion token. The store applies the command and returns the token after the command is durable at the level in force (section 7). Commands: `submit` (run fields, shapes, task rows), `run_new`, `run_update`, `lease` (one offer), `end` (attempt rows, task updates, output rows), `task_update` (hold, release, cancel, retry, tag edit, purge), `worker_put`, `invite_use`, `submitter_put`, `org_put`, `blob_put`, `blob_ref`, `ckpt_commit`, `event`, `sweep`. Reads go through a separate reader interface that answers from a read transaction (section 10).

Two implementations exist, both in the crate `podswarm-store` (file 21):

| Implementation | Used by | Durable | Completion |
| --- | --- | --- | --- |
| `SqliteStore` | `podswarm coord`, `podswarm x --db FILE` | yes, `strict` or `batched` | after the commit of the batch that holds the command |
| `MemStore` | a session: `podswarm run`, `podswarm x` with no `--db` (level `memory`) | no | in the same actor step, after the in-memory update |

`MemStore` opens no SQLite file. It keeps the tables of section 4 as Rust structures. It drops an ended attempt and its output when the session's printer consumed them (file 18). A crash of the home process ends the session and its queue: nothing re-offers a task after it, so `memory` keeps `at_most_once` (file 09) with no lease commit.

The simulation of file 23 wraps the trait with a fault store that crashes before, during and after a commit.

## 2. Decision: SQLite in WAL mode, bundled, one writer thread

The durable store is SQLite in WAL mode, built from the bundled C amalgamation (`rusqlite` with feature `bundled`) and linked statically (file 21). One thread owns the only connection that writes. A second thread owns a connection that only checkpoints (section 9). Other connections only read. There is no consensus layer and no second writer process.

Reasons:
* A reader with the `sqlite3` shell can query a live store (section 16). HyperShell users query their database in this way.
* `ALTER TABLE`, `user_version` and a published file format make migration and inspection cheap.
* A planned replicator of the org (`podrepl`) targets SQLite files (section 17).
* Speed is enough. The prototype below runs above target A-01 (file 23) without wire cost.

The `Store` trait keeps another engine possible. Reopen this decision when a benchmark of file 23 shows the store as the first limit of the coordinator.

Measurements that support the decision:
* Queue benchmark, two row writes per task. SQLite WAL with `synchronous=FULL` runs 165 to 168 tasks/s with one commit per task and 11,262 to 11,728 tasks/s with 100 tasks per commit. With `synchronous=NORMAL` it runs 6,409 to 6,903 and 83,516 to 84,175 tasks/s. [EV-031]
* Coordinator prototype with one writer thread, `strict`, a null executor and five row writes per task: 28,290 to 37,211 tasks/s at 200 workers and bundle 10, where a check from outside found each task `succeeded` and no second accept; 47,359 to 61,928 tasks/s at 1,000 workers and bundles 100 to 1,000 with checkpoints only when idle (29,588 to 31,972 with automatic checkpoints); 13 to 17 us of writer CPU per task. [EV-032]
* At 200 workers and bundle 10 a commit held 139 to 151 events and took 17.8 to 20.7 ms at p50, at 41 to 50 commits/s. Commit time is the fsync plus the row work of the batch. [EV-033]

These numbers come from one x86_64 VM with a virtio disk, a null executor, no wire, no TLS, no JSON and a schema with five row writes per task; they say nothing about an SD card, an ARM coordinator or the schema of section 4.

## 3. Version floor

The bundled SQLite is 3.51.3 or newer. At start the store reads `sqlite3_libversion_number()` and refuses a value under 3051003 with exit 70. A WAL-reset bug in versions 3.7.0 to 3.51.2 can corrupt a database when two connections write or checkpoint at the same instant; 3.51.3 fixes it. [EV-034] The WAL checkpointer thread of section 9 runs on its own connection beside the writer, so the floor is required. (G-01)

WAL does not work over a network file system. [EV-035] Section 19 gives the check.

## 4. Schema version 1

`PRAGMA user_version` holds the schema version. A new store applies the block below in this order, in one transaction after the three pragmas. `page_size` and `auto_vacuum` take effect only before the first table exists, so they come first and `journal_mode` comes last. After the create the store reads `PRAGMA auto_vacuum` and exits 70 unless it is 2. (G-11)

```sql
PRAGMA page_size = 4096;
PRAGMA auto_vacuum = INCREMENTAL;
PRAGMA journal_mode = WAL;
BEGIN IMMEDIATE;
-- Times (*_at, not_before, deadline) are unix seconds. Durations end in _ms.

-- Keys: swarm_id (32 hex), gen (16 hex), created_with, next_task_id, next_run_id, next_job_id,
-- next_shape_id (decimal), starts (JSON array of the last 3 start times), restore_pending ('1' in a backup copy only).
CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT NOT NULL) WITHOUT ROWID;

CREATE TABLE runs(
  run_id INTEGER PRIMARY KEY, name TEXT,
  owner TEXT NOT NULL,                       -- submitter fingerprint, or 'local'
  weight INTEGER NOT NULL DEFAULT 1, priority INTEGER NOT NULL DEFAULT 0, max_running INTEGER,
  halt_n INTEGER, halt_pct INTEGER,          -- --halt-on-fail N or P%
  halt_mode INTEGER NOT NULL DEFAULT 0,      -- 0 drain, 1 now
  durability INTEGER NOT NULL,               -- 0 strict, 1 batched: the level that applies
  active_grp INTEGER NOT NULL DEFAULT 0, paused INTEGER NOT NULL DEFAULT 0, halted INTEGER NOT NULL DEFAULT 0,
  closed INTEGER NOT NULL DEFAULT 0,         -- run_close received
  created_at INTEGER NOT NULL,
  ended_at INTEGER,                          -- closed and every task terminal
  n_tasks INTEGER, n_ok INTEGER, n_failed INTEGER, n_cancelled INTEGER, n_lost INTEGER  -- written with ended_at
);

-- One row per submit message: its contiguous task ids.
CREATE TABLE run_ranges(first_id INTEGER PRIMARY KEY, last_id INTEGER NOT NULL,
                        run_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE INDEX run_ranges_run ON run_ranges(run_id);

CREATE TABLE shapes(
  shape_id INTEGER PRIMARY KEY,              -- u32, never reused
  hash BLOB NOT NULL UNIQUE,                 -- BLAKE3 of spec, 32 bytes (the `b3:` id, file 15)
  class INTEGER NOT NULL,                    -- class(shape) = hash(needs, priority), file 09
  spec BLOB NOT NULL,                        -- the exact shape bytes the submitter sent
  refs INTEGER NOT NULL DEFAULT 0,           -- task rows that name the shape
  created_at INTEGER NOT NULL
);

CREATE TABLE tasks(
  task_id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, shape_id INTEGER NOT NULL,
  idx INTEGER NOT NULL, grp INTEGER NOT NULL DEFAULT 0,
  state INTEGER NOT NULL,                    -- 0 held, 1 waiting, 2 ready, 5 succeeded, 6 failed, 7 cancelled, 8 lost
  attempts INTEGER NOT NULL DEFAULT 0,       -- highest attempt_no that has an attempts row
  failures INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0,
  win INTEGER,                               -- attempt_no of the accepted attempt
  late_ok INTEGER NOT NULL DEFAULT 0,        -- 1: a success came after a terminal state
  input TEXT,                                -- the input line
  extra TEXT,                                -- JSON {fields, tags} of the task row, NULL when empty
  key TEXT, not_before INTEGER, deadline INTEGER, ended_at INTEGER
);
CREATE UNIQUE INDEX tasks_key ON tasks(run_id, key) WHERE key IS NOT NULL;
CREATE INDEX tasks_bad ON tasks(run_id) WHERE state IN (6, 7, 8);

-- One row per offer, deleted with the last attempts row of its items.
CREATE TABLE leases(lease_id INTEGER PRIMARY KEY, wid INTEGER NOT NULL,
                    offered_at INTEGER NOT NULL, items BLOB NOT NULL);  -- items: section 5.3

-- One row per ended attempt, written at its end; a late result updates a lost row once (section 5.4).
CREATE TABLE attempts(
  task_id INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
  wid INTEGER NOT NULL,                      -- 0: no worker (section 12)
  end_kind INTEGER NOT NULL,                 -- 0 exited, 1 signaled, 2 timeout, 3 spawn_failed, 4 killed,
                                             -- 5 cancelled, 6 not_started, 7 lost, 8 superseded, 9 checkpointed
  reason TEXT,                               -- the reason of killed, spawn_failed and lost (file 09)
  code INTEGER, signal INTEGER,
  accepted INTEGER NOT NULL DEFAULT 0,       -- 1 only for the accepted success (I2)
  started_at INTEGER,                        -- from result started_unix
  ended_at INTEGER NOT NULL,                 -- when the coordinator recorded the result
  wall_ms INTEGER, user_ms INTEGER, sys_ms INTEGER, rss_kib INTEGER,
  extra TEXT,                                -- JSON of rare result fields: boundary, shield, residual, outputs[],
                                             -- the usage fields in_bytes, out_bytes, ckpt_count, net_bytes (file 17)
  PRIMARY KEY(task_id, attempt_no)
) WITHOUT ROWID;

-- Captured output of an ended attempt; a row exists only for a stream that is not empty.
CREATE TABLE outputs(
  task_id INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
  stream INTEGER NOT NULL,                   -- 1 stdout or merged, 2 stderr
  len INTEGER NOT NULL,                      -- bytes the attempt wrote
  trunc INTEGER NOT NULL,                    -- 1 when head and tail do not hold all bytes
  head BLOB, tail BLOB,
  blob BLOB,                                 -- BLAKE3 id of the full stream when uploaded (file 15)
  ended_at INTEGER NOT NULL,
  PRIMARY KEY(task_id, attempt_no, stream)
) WITHOUT ROWID;

CREATE TABLE workers(
  wid INTEGER PRIMARY KEY AUTOINCREMENT,     -- u32, never reused
  key BLOB NOT NULL UNIQUE,                  -- Ed25519 public key, 32 bytes
  name TEXT,
  state INTEGER NOT NULL,                    -- 0 pending, 1 active, 2 draining, 3 revoked, 4 retired
  suspect INTEGER NOT NULL DEFAULT 0,
  tags TEXT NOT NULL, caps TEXT NOT NULL,    -- JSON
  speed_w INTEGER NOT NULL DEFAULT 1000,     -- per mille (file 10)
  invite_id TEXT, enrolled_at INTEGER NOT NULL,
  last_seen INTEGER,                         -- written at session end, never per hb
  lifetime_s INTEGER
);

CREATE TABLE invites(
  invite_id TEXT PRIMARY KEY,                -- 16 hex
  verifier BLOB NOT NULL,                    -- Ed25519 public key derived from the invite secret (file 16)
  uses_left INTEGER NOT NULL, expires_at INTEGER NOT NULL,
  rules TEXT NOT NULL,                       -- JSON
  created_by TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
) WITHOUT ROWID;

CREATE TABLE submitters(
  fp TEXT PRIMARY KEY,                       -- SHA256:<base64> of the key, the format of pod-identity (file 16)
  key BLOB NOT NULL, name TEXT,
  scopes TEXT NOT NULL,                      -- JSON list: read, submit, id, admin, verify (file 16)
  routes TEXT NOT NULL,                      -- JSON
  id_aud TEXT,                               -- JSON list of audience patterns for scope id (file 17)
  max_queued INTEGER, max_spec_bytes INTEGER, max_output_bytes INTEGER, max_blob_mib INTEGER,
  max_ckpt_mib INTEGER,
  source INTEGER NOT NULL DEFAULT 0,         -- 0 local (submitter add), 1 org (member statement, file 16)
  org_key BLOB, min_serial INTEGER NOT NULL DEFAULT 0,  -- organisation key and serial floor of a member
  created_at INTEGER NOT NULL
) WITHOUT ROWID;

-- Organisation trust entries (org trust, file 16).
CREATE TABLE org_trust(key BLOB PRIMARY KEY, name TEXT NOT NULL, max_scopes TEXT NOT NULL, routes TEXT NOT NULL,
  max_life_s INTEGER NOT NULL, allow_admin INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL) WITHOUT ROWID;

CREATE TABLE blobs(id BLOB PRIMARY KEY,      -- BLAKE3, 32 bytes (file 15)
                   size INTEGER NOT NULL, refs INTEGER NOT NULL DEFAULT 0,
                   pinned INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
                   last_used INTEGER NOT NULL) WITHOUT ROWID;

CREATE TABLE blob_owners(id BLOB NOT NULL,
                         owner TEXT NOT NULL,  -- submitter fingerprint, or the run owner for a worker upload
                         PRIMARY KEY(id, owner)) WITHOUT ROWID;

-- Committed checkpoints of a task (file 15, section 11).
CREATE TABLE checkpoints(task_id INTEGER NOT NULL, seq INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
  manifest BLOB NOT NULL,                    -- content id of the manifest blob (b3: or b3k:)
  bytes INTEGER NOT NULL, files INTEGER NOT NULL, created_at INTEGER NOT NULL, label TEXT, kind TEXT NOT NULL,
  key_id BLOB, external_ref TEXT, pinned INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(task_id, seq)) WITHOUT ROWID;

-- Per-day usage rollup (file 17, section 9); it outlives the attempts rows.
CREATE TABLE usage_days(day INTEGER NOT NULL, owner TEXT NOT NULL, boundary TEXT NOT NULL,
  attempts INTEGER NOT NULL, reserved_mcore_ms INTEGER NOT NULL, wall_ms INTEGER NOT NULL, user_ms INTEGER NOT NULL,
  sys_ms INTEGER NOT NULL, in_bytes INTEGER NOT NULL, out_bytes INTEGER NOT NULL, PRIMARY KEY(day, owner, boundary)) WITHOUT ROWID;

-- Admin and security events: a plain table. File 16 lists the kinds.
CREATE TABLE events(seq INTEGER PRIMARY KEY, at INTEGER NOT NULL, kind TEXT NOT NULL,
                    who TEXT, subject TEXT, detail TEXT);  -- detail: JSON

PRAGMA user_version = 1;
COMMIT;
```

The extensions add the tables `jobs` (`jobs.1`) and `secrets` (`secrets.1`) by migration (file 24). Signed shapes add `shapes.sig`, verification adds `attempts.spec`, and the audit hash chain (`audit-chain.1`) adds `events.prev`, `events.hash` and `meta.audit_base`, each by migration (file 24).

## 5. Rules of the schema

### 5.1 Identifiers and ranges
* The actor assigns `task_id`, `run_id`, `job_id` and `shape_id` from counters in memory. The `submit` or `run_new` transaction writes the next value of each counter into `meta` (`next_task_id` and the others). At start a counter is the larger of its `meta` value and the column maximum plus 1. An id is never reused, also after retention deletes the newest rows.
* The tasks of one submit message get contiguous ids `first_id..last_id` and one `run_ranges` row. `ls --run R` scans the ranges of R by `task_id`. A start scans the ranges of open runs (section 11).
* A task enters the ready structures only after its `submit` commit. A task id that a worker ran is then always a committed id.
* `wid` comes from `AUTOINCREMENT` and is never reused. A worker learns its `wid` from `ready` (file 04).
* `lease_id` comes from a counter in memory that starts at `max(lease_id) + 1`. A lease id that a crash lost can be reused; it never leaves the coordinator.

### 5.2 Stored states
The store holds `ready` (2) for a task that memory holds as `leased` or `running`; the `leases` row names the attempt. Codes 3 and 4 are never stored. State 1 means "waiting for `not_before` or for the group gate"; T2 (file 09) is memory only, and the loader derives `ready` from `not_before <= now` and `grp <= runs.active_grp`.

### 5.3 The packed lease list
`leases.items` lists the attempts of one offer:

```
items    = count, item * count
item     = delta, attempt_no
count    = varint                 number of items, 1 to 1,000
delta    = varint                 task_id minus the task_id of the previous item (0 before the first)
attempt_no = varint
varint   = unsigned LEB128, at most 10 bytes
```

Items are sorted by `task_id` ascending and a `task_id` appears once. A reader refuses a list whose count does not match its bytes. A typical offer of contiguous tasks costs 2 bytes per item.

### 5.4 The end of an attempt and invariant I2
Every ended attempt gets one `attempts` row, `not_started`, `superseded` and `checkpointed` included. The same transaction updates the task with one prepared statement:

```sql
UPDATE tasks
   SET state = ?2, attempts = ?3, failures = ?4, losses = ?5, win = ?6, not_before = ?7, ended_at = ?8
 WHERE task_id = ?1 AND state < 5;
```

The actor computes every value from memory and uses it for the end of an attempt of a task that is not terminal. `win` is set only with `state = 5`. The clause `state < 5` enforces I2 in the store: a second terminal update changes no row. One actor owns the state, so a change count of 0 is a divergence between memory and the store, never a race. The writer then aborts the batch, logs `store_divergence` with the task id, and the coordinator exits 70; the next start recovers from the store (section 11).

Other task writes:

```sql
-- A late result of an attempt whose row ended as lost (attempt deadline): one update of the result
-- columns of that row; end_kind and reason stay, extra holds the reported outcome. A lost row has
-- no wall_ms, so a second late result changes no row:
UPDATE attempts SET code = ?3, signal = ?4, wall_ms = ?5, user_ms = ?6, sys_ms = ?7, rss_kib = ?8,
       extra = ?9, accepted = ?10
 WHERE task_id = ?1 AND attempt_no = ?2 AND end_kind = 7 AND wall_ms IS NULL;
-- A result for a terminal task (late, superseded, or the end of a cancelled attempt):
-- an attempts row with accepted = 0 (or the update above), then (?3 is 1 for a success, else 0):
UPDATE tasks SET attempts = max(attempts, ?2), late_ok = max(late_ok, ?3) WHERE task_id = ?1 AND state >= 5;
-- T10 cancel (also of a task with a live attempt; its attempts row comes later):
UPDATE tasks SET state = 7, ended_at = ?2 WHERE task_id = ?1 AND state < 5;
-- T11 retry: budgets reset, attempts keeps rising (I3, I7):
UPDATE tasks SET state = 2, failures = 0, losses = 0, ended_at = NULL WHERE task_id = ?1 AND state IN (6, 7, 8);
-- T3 hold and release:
UPDATE tasks SET state = ?2 WHERE task_id = ?1 AND state IN (0, 1, 2);
```

A `lease` command inserts the `leases` row. The `end` command that writes the last `attempts` row of a lease also runs `DELETE FROM leases WHERE lease_id = ?1`; the actor counts the open items of each lease.

### 5.5 Other statements
* An invite use (file 16): `UPDATE invites SET uses_left = uses_left - 1 WHERE invite_id = ?1 AND uses_left > 0 AND revoked = 0 AND expires_at > ?2`. It runs in the transaction that inserts the worker row. A change count of 0 refuses the enrol.
* A submit adds `refs` to each shape it names: `UPDATE shapes SET refs = refs + ?2 WHERE shape_id = ?1`, once per shape per submit.
* A shape is inserted with `INSERT INTO shapes(...) VALUES (...)` only when the actor's map of `hash` to `shape_id` lacks it. The actor loads that map at start.

## 6. Write path

### 6.1 Writes per task
A task with one attempt and no retry, offers of `B` tasks:

| Step | Row writes | B-tree entry writes |
| --- | --- | --- |
| submit (bulk insert, multi-row `INSERT` of up to 64 rows) | 1 `tasks` insert | 1, plus 1 for `tasks_key` when the task has a key |
| offer | `leases` insert and delete, shared by B tasks | 2/B |
| start | none | 0 |
| end | 1 `attempts` insert, 1 `tasks` update | 2, plus 1 per `outputs` row, plus 1 for `tasks_bad` when the end state is 6, 7 or 8 |
| total | 3 + 2/B | 3 + 2/B in the common case |

A failed attempt that retries writes the same end pair. A `tasks` row holds no spec, so an update rewrites a cell of about 50 to 100 bytes (section 18). The store has no index of ready tasks, waiting tasks, the tasks of a run, live attempts or accepted results: the ready and timer structures live in memory and a start rebuilds them by the range scan, `ls` scans the id ranges, the live attempts are in memory and in `leases`, and I2 is the clause of section 5.4. Each index that stays changes only at insert (`tasks_key`, `shapes.hash`) or at a bad end (`tasks_bad`, which lists the failed, cancelled and lost tasks of a run for `ls` and `retry`).

What a crash loses, by the step it hits:

| Crash after | `strict` and `batched`, process crash | `batched`, power loss | `memory` |
| --- | --- | --- | --- |
| `submitted` sent | nothing | the commits of the last second (section 7) | the whole queue |
| offer sent, lease not committed | the attempt is unknown to the store; section 8 | same | the whole queue |
| lease committed | nothing; the attempt is rebuilt from `leases` | the last second | the whole queue |
| `ack` sent | nothing | the last second: the result is lost and the task runs again | the whole queue |

### 6.2 Natural group commit
The writer thread blocks on its queue. When it wakes it takes every queued command, up to 8,192 events or 4 MiB of estimated WAL bytes, and applies them in one `BEGIN IMMEDIATE` transaction. An event is one task row of a submit, one lease, or one result item. It commits, then completes each token in queue order. There is no timer: at `strict` the fsync of the last commit is the batching window, and at `batched` the commit has no fsync and the writer commits as fast as row work allows. A window of 0, 500 us or 2 ms gave the same throughput within noise, and a 50 ms timer at `batched` made it about 7 times slower than `strict` at 10 workers. [EV-036] A fixed cap of 256 events per commit limited the prototype to 17,174 to 17,866 tasks/s at 1,000 workers and bundle 1, so the cap is 8,192. [EV-028]

The writer and the actor each block on their queue and never spin. (B-15) One prototype run on one CPU stopped with a timeout. [EV-030]

### 6.3 Backpressure
The writer publishes the age of its oldest queued command and the count of queued events. The actor uses them for the backpressure rule of file 10, section 8 (`backpressure_age_ms`, `backpressure_events`).

## 7. Durability levels

| Level | Store | Pragmas | Commit | Survives |
| --- | --- | --- | --- | --- |
| `strict` | `SqliteStore` | `synchronous=FULL`; on macOS also `fullfsync=ON` | each commit syncs the WAL | a process crash and a power loss: nothing acknowledged is lost |
| `batched` | `SqliteStore` | `synchronous=NORMAL`; on macOS `checkpoint_fullfsync=ON` | no sync at commit; the WAL checkpointer syncs the WAL at least once per second (section 9) | a process crash; a power loss drops at most the commits of the last second plus the disk's own write cache |
| `memory` | `MemStore` | none | none | nothing: the queue ends with the process |

In WAL mode with `synchronous=NORMAL` a commit does not sync the WAL; a checkpoint syncs it. [EV-039] On macOS `synchronous=FULL` does not issue `F_FULLFSYNC` unless `fullfsync=ON`; so `strict` sets it. [EV-040]

Defaults: `podswarm coord` `strict`; `podswarm x --db FILE` `batched`; `podswarm x` and `podswarm run` `memory`. `podswarm coord` takes `strict` or `batched`. The level of the coordinator is a floor. A submit may ask for a stricter level for its run, and `runs.durability` records the level that applies. A run with an `at_most_once` task uses `strict`. A commit syncs as `strict` when any command in it belongs to a `strict` run: the writer sets `PRAGMA synchronous` before `BEGIN` of that batch.

## 8. Which acknowledgements wait for a commit

Invariant I6 (file 09): `submitted` and the result `ack` leave only after the commit of their command. In a session (`memory`) they leave after the in-memory update.

These do not wait for a commit:
* `hback`. It comes from memory.
* `offer` of `at_least_once` tasks. The actor queues the `lease` command and sends the offer at once. This cut pull latency at p50 from 8.99 ms to 0.21 ms and raised the prototype from 9,981 to 14,818 tasks/s. [EV-029]
* `cancel`, and the other effects of a transition.

An `offer` that holds an `at_most_once` task waits for the commit of its `leases` row. Frames to one session leave in the order the actor made them: a `cancel` for an attempt whose offer waits for its commit waits behind that offer.

A crash between an offer and its lease commit leaves attempts that the store does not know. After the restart the task is `ready` in the store and its next `attempt_no` comes from `tasks.attempts` and `leases` (section 11), so it can repeat the number of the unknown attempt. Reconciliation (file 05) handles both cases: a `hold` entry with no row of this worker gets `cancel{kill}`, and a result for an attempt that the sending worker does not hold gets the verdict `dropped` and writes no row. When the worker that holds the unknown attempt gets the same `(task_id, attempt_no)` in an offer, it keeps the attempt it holds (file 05). The task runs at least once, as `at_least_once` allows. `at_most_once` never takes this path, because its offer waits for the lease commit and its worker writes a spawn record first (file 12).

## 9. Checkpoints

The WAL checkpointer, a thread, owns its own connection. It runs:
* `PRAGMA wal_checkpoint(PASSIVE)` when the WAL holds more than 4,096 pages (16 MiB). The writer reads the page count from `sqlite3_wal_hook` after each commit and publishes it to the WAL checkpointer. PASSIVE never blocks the writer.
* `PRAGMA wal_checkpoint(TRUNCATE)` when the writer has had no command for 10 s. The WAL checkpointer connection has `busy_timeout` 100 ms; a TRUNCATE that does not get the lock waits for the next idle period.
* At `batched`, a PASSIVE checkpoint at least once per second while the WAL holds frames that no checkpoint synced.

`wal_autocheckpoint` is 0 on every connection, so no commit checkpoints by itself. `journal_size_limit` is 64 MiB, so the WAL file shrinks after a reset. The coordinator reports `wal_bytes`. Above 256 MiB it logs an alarm once per minute, sets `wal_alarm` in `status`, and runs a PASSIVE checkpoint at once. The usual cause is a reader that keeps a read transaction open, which stops the WAL from resetting; the alarm names the open reader connections of the coordinator and says that an outside reader can be the cause.

Both triggers are needed. With a checkpoint only at idle the prototype WAL reached 79 MB to 1.11 GB in 15 s, and a schema with five row writes per task writes about 1.4 KB of WAL per task. [EV-042] A checkpoint on the writer thread cost 48 percent of throughput at most over 24 pairs of cells, median 9 percent, and 38 to 48 percent at 1,000 workers with offers of 100 and 1,000; on its own connection it leaves the commit path. [EV-043] (B-17)

## 10. Connections and pragmas

| Pragma | Writer | Checkpointer | Readers |
| --- | --- | --- | --- |
| `journal_mode` | `WAL` (persistent in the file) | not set | not set |
| `synchronous` | per level (section 7) | as the writer | not set |
| `fullfsync`, `checkpoint_fullfsync` | macOS, section 7 | as the writer | not set |
| `wal_autocheckpoint` | 0 | 0 | 0 |
| `journal_size_limit` | 67108864 | 67108864 | not set |
| `cache_size` | -65536 (64 MiB); -16384 under 4 GiB of RAM | -2048 | -16384 |
| `temp_store` | `MEMORY` | `MEMORY` | `MEMORY` |
| `mmap_size` | 0 | 0 | 268435456 on 64-bit targets, 0 on 32-bit |
| `busy_timeout` | 5000 | 100 | 5000 |
| `query_only` | 0 | 0 | 1 |
| `foreign_keys` | `OFF` | `OFF` | `OFF` |

The writer keeps a prepared statement cache of 64 statements. Two reader connections serve `show`, `ls` and `logs` of ended work, each request in one read transaction. The actor overlays the live states from memory on what a reader returns (file 09): a task that a reader sees as `ready` and memory holds as `running` is shown `running`.

## 11. Recovery at start

1. Set `umask 077`. Check the modes and owners of section 19. A wrong mode or owner exits 77 and names the path.
2. Take an exclusive `flock` on `<state>/coord.lock` with no wait. A held lock exits 69.
3. Check the library version (section 3). Refuse a network file system (section 19).
4. Open the database. A missing file is created with mode 0600 and the block of section 4. SQLite replays the WAL by itself.
5. Run `PRAGMA quick_check` unless `--fast-start` is given. A result other than `ok` exits 70 with a message that names `podswarm coord restore`.
6. Read `user_version`. A value above the known version exits 78. A lower value runs the migrations (section 15).
7. If `meta.restore_pending` is `'1'`, run the generation step of section 12.
8. Append the start time to `meta.starts` (keep the last 3). When the 3 starts fall within 600 s, log the crash loop alarm and set `crash_loop` in `status`. Each start gives every live attempt a full deadline again, so the time bound of I1 counts from the last start (file 09).
9. Load `meta`, `workers`, `invites`, `submitters`, the map of shape hashes, and the runs with `ended_at IS NULL`.
10. For each open run, scan its `run_ranges` by `task_id`. Put each non-terminal task into the memory structures: `held` (0), the timer heap (1, by `not_before` and the group gate), the ready heaps (2), and the deadline heap when `deadline` is set. Rebuild the run counters. Load the spec of each shape that an open run names.
11. Read every `leases` row. For each item with no `attempts` row, make an in-memory attempt `offered` for the lease's `wid`, and mark the task `leased`. Set the next `attempt_no` of each task to `max(tasks.attempts, attempt_no in leases) + 1`. Delete a lease row whose items all have `attempts` rows.
12. Set `last_rx` of every worker to now, so each rebuilt attempt gets the deadline `now + silence_s + kill_grace_s + grace_eff` (file 05). The first `hb` of each worker reconciles its attempts (file 05).
13. Start the timers: `not_before`, `deadline`, retention (section 13), the WAL checkpointer.
14. Open the local socket and the listener.

Target A-12 (file 23) bounds the time from step 1 to step 14.

## 12. Generation and restore

`meta.gen` is 16 lowercase hex characters from a random u64. The store writes a new one at create and in the generation step. The authority sends it in `ready` (file 04).

A backup copy carries `meta.restore_pending = '1'` (section 14). A store that starts with it runs the generation step in one transaction:
1. Write a new `meta.gen`.
2. Raise `next_task_id`, `next_run_id`, `next_job_id` and `next_shape_id` by 2^32 above their current values. A journal written before the restore can then never name a new task.
3. For each non-terminal task of an `at_most_once` run: write `state = 8` with the `UPDATE` of section 5.4, and an `attempts` row with the next `attempt_no`, `wid = 0`, `end_kind = 7` (`lost`) and `reason = 'generation'`. Delete every `leases` row.
4. Delete `restore_pending`.
5. Insert an `events` row of kind `generation` with the previous and the new `gen`.

A worker whose stored `gen` differs from `ready.gen` deletes its journal, kills every attempt and starts empty (file 04). Its key must still have a `workers` row in the restored store, else it enrols again (file 16). `at_least_once` tasks in flight at the backup run again from the restored state.

A raw copy of the database file is not a supported restore: it has no `restore_pending`, keeps the `gen` of the source, and can lose committed transactions when the WAL file is not beside it. [EV-044]

`podswarm coord restore FILE` runs with the coordinator stopped. It opens FILE, checks `integrity_check`, `user_version` and `restore_pending`, moves the current database to `<state>/pre-restore-<unix s>.db`, removes its `-wal` and `-shm` files, and copies FILE into place at mode 0600. The next start runs the generation step.

## 13. Retention and compaction

A sweep runs when the writer is idle, as `sweep` commands of at most 1,000 rows each, so a sweep never holds the writer for long.

| What | Rule | Default |
| --- | --- | --- |
| a run and its tasks | a run with `ended_at` older than `retain_days` is deleted with its `run_ranges`, `tasks`, `attempts` and `outputs` | `retain_days` 30 |
| ended tasks of an open run | in a run open longer than `retain_days`, terminal tasks with `ended_at` older than `retain_days` are deleted, scanning its ranges from the lowest id | as above |
| inline output | `outputs` rows with `ended_at` older than `retain_output_days` | `retain_output_days` 7 |
| events | `events` rows with `at` older than `retain_events_days` | `retain_events_days` 365 |
| shapes | a shape with `refs = 0` is deleted; a task delete subtracts from `refs` | none |
| blobs | see below | `blob_ttl_days` 14 |
| checkpoints | by the rules of file 15, section 11.9 (`retain`, `ckpt_after_end_days`, `ckpt_after_fail_days`) | file 15 |
| usage rollup | before it deletes `attempts` rows, the sweep adds them to `usage_days`; `usage_days` rows older than `retain_events_days` are deleted | as events |

Blobs: a submit that names a blob checks ownership and adds to `refs` in its own transaction. The sweep deletes `blobs` rows with `refs = 0 AND pinned = 0 AND last_used < now - max(blob_ttl_days, 1) * 86400`, then unlinks the files after the commit. A `blob_have` with a positive answer sets `last_used`. A sweep that finds `refs` different from the real references rebuilds the count. File 15 owns the blob rules.

After each delete step the sweep runs `PRAGMA incremental_vacuum(1000)`. It returns pages only because `auto_vacuum` is 2 (section 4). The store deletes by age inside one file and never rotates files, so every query sees all retained history.

## 14. Backup

* `podswarm coord backup --to FILE` runs on a dedicated read connection. It calls `sqlite3_backup_step(-1)` once, so the copy comes from one read transaction and the writer does not stop. While the backup runs, the WAL cannot reset.
* The copy is written to `FILE.partial` at mode 0600. The command then opens the copy, writes `meta.restore_pending = '1'`, runs `PRAGMA integrity_check`, and renames it to FILE. `--verify` also reopens FILE and checks `user_version` and the table count.
* Never copy the main database file alone while a coordinator runs (section 12).
* A backup holds the database only. Never in a backup: the coordinator TLS key, the invite secrets (the store keeps verifiers only), the blob files under `<state>/blobs/`, the worker state, and the keys of the extension `secrets.1` (file 24). After a restore, a blob row whose file is missing is removed by the sweep, and a task that names it fails with `spawn_failed` reason `input` (file 15).
* Moving the copy off the machine is the operator's step.

## 15. Migration

* `user_version` is the schema number. Migrations are numbered SQL scripts in the binary. The store applies each missing one in order, each in one transaction.
* Before the first migration the store writes a backup `<state>/pre-migrate-<N>.db` with the method of section 14, where N is the version before the migration.
* A store with a `user_version` above the binary's version is refused with exit 78. This applies to `podswarm x --db FILE` too.
* A new column is nullable or has a constant default.
* There is no downgrade. The pre-migrate backup is the way back.

## 16. Reading the store from outside

The database is a plain SQLite file. `sqlite3 -readonly <state>/coord.db` works on a live store as the same uid. Example:

```sh
sqlite3 -readonly "$STATE/coord.db" 'SELECT state, count(*) FROM tasks GROUP BY 1'
```

What an outside reader sees:
* A task that is `leased` or `running` shows as `ready` (2). A task that waits only for its group gate or a passed `not_before` shows as `waiting` (1).
* A running attempt has no row. Its offer appears only inside the packed `leases.items`.
* Ended attempts, their output rows, the runs and the workers as of the last commit.
* At `batched` and `strict`, work of the last commit batch can be missing.

The live state is in memory: `podswarm ls`, `show` and `status` answer from it. There is no `sql` wire operation; remote queries use `ls` with its selector and fields (file 18). An outside reader that keeps a transaction open blocks the WAL reset and raises the alarm of section 9. (U-store-readonly)

## 17. High availability

One coordinator has one writer. There is no failover, no second writer and no leader election.
* Committed data survives a process crash at `strict` and `batched`, and a power loss at `strict`.
* A restart restores the swarm from the store with no manual step (section 11). Running attempts keep running while their fence holds, so a long `silence_s` lets them survive a restart.
* Cold standby: a second machine runs `podswarm coord` on a restored backup. An invite token lists more than one coordinator address (file 16), so workers find it. The operator moves the address or the DNS name. A restore loses the commits after the backup, and the generation step of section 12 protects the fence.
* `podrepl` is a planned org project for single-writer SQLite replication. When it exists, a standby that replays its stream can shorten a failover. It stays single writer.

## 18. Sizes

Row sizes from the SQLite record format, with a 40-byte input line and no key:

| Row | Bytes |
| --- | --- |
| `tasks` | about 70 (header 18, integers 12, input 40) |
| `attempts` | about 50 |
| `leases` | about 20 plus 2 per item, deleted after the offer ends |
| `outputs` | 30 plus head and tail, only for non-empty streams (at most two times `capture_max`, file 05) |

A task with one attempt and no output costs about 150 bytes with b-tree overhead: one million tasks are about 150 MB. A shape is stored once. The WAL carries about 0.4 to 0.6 KB per task between checkpoints. [T] (B-18, A-39)

The coordinator reports `db_bytes` and `wal_bytes`. At `max_db_bytes` it refuses new submits with `err{busy}`; running tasks complete and their results commit. The default of `max_db_bytes` is 80 percent of the free space of the state directory at start. (F-06)

On an SD card the checkpoint writes are random 4 KiB writes, which run at 1.7 to 4.0 MB/s on common cards. [EV-045] Target A-04 (file 23) covers a Raspberry Pi coordinator.

## 19. State directory and file modes

The coordinator state directory and its default are defined in file 19 (directories). A durable level refuses a state directory under a temporary directory or the working directory unless `--allow-temp-state` is given.

| File | Mode |
| --- | --- |
| the state directory | 0700 |
| `coord.db`, `coord.db-wal`, `coord.db-shm` | 0600 |
| `coord.lock` | 0600 |
| `pre-migrate-<N>.db`, `pre-restore-<unix s>.db`, backups the coordinator writes | 0600 |
| files under `blobs/` | 0600 |

The coordinator sets `umask 077` first and creates each SQLite file empty with mode 0600 before SQLite opens it. It refuses to start, with exit 77 and the path in the message, when the directory or one of these files is group or world accessible or is owned by another uid. (G-12)

The state directory must be on a local disk. On Linux the store reads `statfs` and refuses the types NFS (0x6969), SMB (0x517B), CIFS (0xFF534D42), SMB2 (0xFE534D42), 9P (0x01021997), Ceph (0x00C36400), AFS (0x5346414F) and Lustre (0x0BD00BD0) with exit 78. On other systems it refuses the type names `nfs`, `smbfs` and `afpfs` from `statfs`.

`podswarm x --db FILE` uses FILE and `FILE-wal` and `FILE-shm` beside it, with the same modes and the same lock rule on `FILE.lock`.

## 20. Settings

| Name | Scope | Default | Range |
| --- | --- | --- | --- |
| `durability` | coord, `x` | `coord` `strict`; `x --db` `batched`; `x`, `run` `memory` | `strict`, `batched` (coord); `strict`, `batched`, `memory` (`x`) |
| `db` | `x` | none (`memory`) | a file path |
| `state_dir` | coord | file 19 | a local directory |
| `allow_temp_state` | coord | false | bool |
| `fast_start` | coord | false | bool |
| `retain_days` | coord | 30 | 1 to 36,500 |
| `retain_output_days` | coord | 7 | 0 to 36,500 |
| `retain_events_days` | coord | 365 | 1 to 36,500 |
| `blob_ttl_days` | coord | 14 | 0 to 36,500 |
| `max_db_bytes` | coord | 80 percent of free space at start | bytes, at least 64 MiB |

Fixed values, not settings: batch caps 8,192 events and 4 MiB; checkpoint at 4,096 pages and after 10 s idle; `journal_size_limit` 64 MiB; WAL alarm 256 MiB; crash loop alarm at 3 starts in 600 s; sweep steps of 1,000 rows.
