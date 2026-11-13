# podswarm: the specification

podswarm is "ssh, but what you get is compute": one static binary and one protocol that give the processors, the memory and the network of any machine that the user can reach. This tree is its design. Nothing of it is built yet; file 22 gives the order of the work. The licence of the tree and of the product is 0BSD.

## The files

| File | Title (the first line of the file) | What it answers |
| --- | --- | --- |
| 00 | Summary | What podswarm is, what ships when, and what the owner must decide, on one page. |
| 01 | Requirements | The owner's words, the use cases, goals, non-goals, the single system image ladder, the headline targets. |
| 02 | Fit with the org | Which org rules bind podswarm, which repositories and `pod-*` crates it uses, what it gives back. |
| 03 | Architecture | The layers, the roles of the one binary, session and swarm, walk-throughs, processes, failure domains. |
| 04 | Roads and links | How the caller reaches a machine, copies the binary, makes a link, reattaches after a cut; the holder. |
| 05 | Attempts: the process protocol | The shape, the messages, attached and captured I/O, reconciliation, the fence, wire limits, error codes. |
| 06 | View: the caller's files on another machine | How a remote process sees the caller's files at the same path, how writes come back, the rungs, `sync`. |
| 07 | Spread: the single system image ladder | Exec-level spreading of a process tree over machines; process migration and pooled memory as goals. |
| 08 | Pool: machines, capacity and placement | The pool file, what a worker reports, placement of one command, the learned table, cells and residency. |
| 09 | Queue: durable work | Tasks, states, transitions T1 to T11, invariants I1 to I7, the delivery contract, retry, groups, runs. |
| 10 | Queue engine: how the queue drives workers | Classes, queue depth, offers and pulls, fairness, tail reclaim, reservation, the throughput model. |
| 11 | Storage | The SQLite store: schema, write path, durability levels, recovery, generation, backup, retention. |
| 12 | Execution: how a worker runs an attempt | Spawner and keeper, containment rungs, limits, output, environment, directories, boundary `confined`. |
| 13 | Trust: boundary and shield | The two protection axes: boundary (host from task) and shield (task from host), with what each level stops. |
| 14 | Network of a run | The network policy of a run, served by podnet: values, members, holds, exits, DNS. |
| 15 | Data: content store, staging, outputs and checkpoints | The content store, transfers, staging for queued tasks, outputs, checkpoints and resume. |
| 16 | Security: identity, admission and limits | Identity, keys, invites, submitters, organisation statements, policies, the path rule, the attack table. |
| 17 | Extending: how programs and agents use podswarm | The machine interface, the MCP server, hooks, webhooks, plugins, the run identity. |
| 18 | Command line | Every verb and flag, `run`, `x`, templates, exit codes of `run` and of the batch verbs. |
| 19 | Reference: settings, files, exit codes, recipes | Every setting with scope, type, range and home file; config files, environment, directories, exit codes, recipes. |
| 20 | HyperShell parity | Each HyperShell feature with a verdict and the podswarm form. |
| 21 | Crates and asks | The pin, the crates, the build rules, the `pod-*` crates given back, the asks and their fallbacks. |
| 22 | Roadmap | Milestones M0 to M10 with scope and exit criteria. |
| 23 | Testing, benchmarks and targets | Test layers, the simulation, guards, fault tests, benchmarks, and the full table of targets. |
| 24 | Later features | Designed features outside the core, each with its feature name and its condition to ship. |
| 25 | Decisions | The log of the decisions D-01 to D-129, with reason, rejected choice and home file. |
| 26 | Risks, rulings and known gaps | Ranked risks, unknowns, the owner's rulings and the questions still asked, known gaps. |
| 27 | Glossary | The terms that more than one file uses, with their home file. |
| 28 | Prior art | The tools and systems that podswarm is compared with, by face. |

## Reading orders

* **The owner.** File 00, then file 01 (the requirements in the owner's words), file 26 (the rulings still asked, R-01 to R-16), file 22 (what ships when).
* **An implementer of one crate.** File 21 (the crate, its layer rule and its asks), file 03 (the map), the file of the topic of the crate (for example file 06 for `podswarm-view`, file 12 for `podswarm-exec`), file 05 (the wire), file 19 (the settings), the tests of that topic in file 23, and file 27 for the words.
* **A reviewer of the protocol.** Files 03, 04, 05, 09, 10 and 11 in that order, then file 16 (identity and limits), file 25 (the decisions and what they reject) and the simulation and fault tests of file 23.

## Conventions

* **Pointers.** A rule names its neighbour as `(file NN)`, often with a section. Each `file NN` names a file that exists; the lint checks it.
* **One home.** Each rule, setting and number has one home file. Another file names the setting and points to the home; it does not copy a default or a limit. The default of a setting is in the file of its topic. File 19 lists every setting with scope, type, range and home file. Where two files differ, the home file is right.
* **Style.** ASD-STE100: short sentences, active voice, present tense. The tree holds no history; file 25 holds the decisions.
* **Tags.** `[EV-nnn]` is a checked fact; `evidence/facts.md` resolves it with its source and check. `[T]` is a target: a number that no benchmark of podswarm code backs yet; file 23 holds its conditions and its test.
* **Numbered files.** The first line is `# N. Title` and each section is `## N. Title`.

Id families and their home files:

| Family | What | Home |
| --- | --- | --- |
| D-nn | decisions | file 25 |
| K-nn, R-nn | risks; rulings of the owner | file 26 |
| A-nn | targets | file 23 |
| B-nn, E-nn, F-nn, M-nn, S-nn, G-nn, `U-name` | benchmarks, environment, fault, simulation, soak tests; guards; unit and conformance tests | file 23 |
| P-nn, V-nn, N-nn | asks to podcrates, podvm, podnet | file 21 |
| X-nn | attacks | file 16 |
| EV-nnn | evidence | `evidence/facts.md` |
| T1 to T11, I1 to I7, W1 to W7 | task transitions, invariants, worker transitions | file 09 |
| U1 to U9, G1 to G14, N1 to N14 | use cases, goals, non-goals | file 01 |
| M0 to M10 | milestones | file 22 |

An id with a hyphen belongs to a family of the first rows; an id with no hyphen (G1, N1, U1, M1) is a goal, a non-goal, a use case or a milestone. An id is never reused.

## Other directories

* `evidence/`: the facts and the raw material behind them.
  * `evidence/facts.md` lists each fact `[EV-nnn]` with its source, its check (`measured`, `read`, `run` or `not re-checked`), its date and the files that cite it.
  * `evidence/spread/results.md`: both runs of the exec prototypes (`execbench.c`, `takeover.c`, `shim.c`) of file 07.
  * `evidence/view/results.md`: the manifest size and walk results of the view scripts (`manifest_size.py`, `walk.py`) of file 06.
  * `evidence/scale/README.md`: the host and the output files of the coordinator prototype and the connection probes (files 03, 10, 11).
  * `evidence/bench/`: the source and two runs of the store benchmark (file 11).
* `schemas/`: 17 JSON Schemas (draft 2020-12) of the wire messages and records, `NAME.1.schema.json`; `examples/` with the valid and invalid examples (194 files); `validate.py`, which checks the schemas and the examples; `README.md`, which gives the rule of precedence (the Markdown file wins).
* `scripts/`: the checks of the tree. `lint-docs.py` checks the form (line count, dashes, filler words, machine paths, `file NN` pointers, headings, links). `check-ids.py` checks that each cited id has one definition in its home file and that no draft tag stays. `check-refs.py` checks that each pointer `file NN, section M` names a section that exists. `make-manifest.sh` writes `MANIFEST.sha256`. `verify.sh` runs the checks.

## Checks

Run from the root of the tree:

```sh
sh scripts/verify.sh
```

It runs five checks: the form check (`python3 -I scripts/lint-docs.py .`), the id check (`python3 -I scripts/check-ids.py .`), the section pointer check (`python3 -I scripts/check-refs.py .`), the schema validator (`python3 -I schemas/validate.py`, when it exists) and the manifest check (`sha256sum -c MANIFEST.sha256`, when the manifest exists). It prints `PASS` or `FAIL` for each check and exits 0 only when each check passes. After a change of a file, run `sh scripts/make-manifest.sh` again.
