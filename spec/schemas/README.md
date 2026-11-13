# Schemas of the wire and file formats

This directory holds a JSON Schema (draft 2020-12) for each JSON format of podswarm. Each schema file is
`NAME.1.schema.json`, and its `$id` is `https://podswarm.invalid/schemas/NAME.1.schema.json`. The
description of each schema names its home file.

## Rule of precedence

The Markdown files are the specification. When a schema and a file differ, the file wins. This rule holds
until the Rust types generate the schemas (file 21). A place where a file is not precise has a `$comment`
that starts with `OPEN:` in the schema. Fix the file first, then the schema.

## The schemas

| Schema | Format | Home file |
| --- | --- | --- |
| `shape` | the shape of a task, with the queue fields and the needs | file 05, section 1; file 09, section 3 |
| `task-row` | the offer row and the submit row, as positional arrays | file 05, sections 3 and 9 |
| `control` | any message of the control stream (the union of the three groups below) | file 05, section 3 |
| `control-link` | `hello`, `ready`, `bye`, `err` | file 04, section 9; file 05, section 11 |
| `control-work` | `pull`, `offer`, `hb`, `hback`, `result`, `ack`, `cancel`, `signal`, `resize`, `id_req`, `id_rep` | file 05, section 3 |
| `control-ckpt` | `ckpt_req`, `ckpt_commit`, `ckpt_ack`, `ckpt_key_req`, `ckpt_key` | file 15, section 11.5 |
| `bulk-header` | the header line of each bulk stream, and the answer line of a blob transfer | file 05, section 7; file 15, section 2 |
| `submitter` | `req`, `rep`, `err` and `event` of the submitter operations | file 05, section 9 |
| `result` | the documents of `--json`: `run.result`, `error`, `rows`, `dry_run` | file 17, section 1 |
| `event` | an event of `watch`, a hook and a webhook | file 17, sections 1 and 5 |
| `hook-claims` | the claims of the token of a webhook delivery | file 17, section 5 |
| `run-claims` | the claims of a run identity token | file 17, section 6 |
| `plugin` | the JSON lines of the checkpoint sink and the admission policy | file 17, sections 4 and 7 |
| `pool` | the pool file `pool.toml` as parsed data | file 08, section 1 |
| `workspace` | the workspace file `.podswarm.toml` as parsed data | file 19, section 2; file 16, section 11 |
| `ckpt-manifest` | a tree manifest as the array of its lines | file 15, section 1.1 |
| `invite-token` | the JSON object inside an invite token | file 16, section 7.1 |

Notes on the forms:

* A positional row (file 05) is an array with `prefixItems`. A receiver ignores a trailing element that it
  does not know, so a row schema does not close its tail.
* A control message, a bulk header and a submitter message allow an unknown object field, because a receiver
  ignores it (file 05, section 3). A shape is strict: an unknown field is an error.
* A TOML file is checked as the JSON object that a TOML parser makes of it.
* The road plugin kind carries the bytes of a link and has no JSON line (file 17, section 7).
* Some rules cross fields or count bytes, for example the size of a shape and the sort order of a manifest.
  A schema cannot state them. The `$comment` of the schema names each one.

## Examples

`examples/` holds the examples. A file `valid-NAME-*.json` must pass the schema `NAME`. A file
`invalid-NAME-*.json` must fail it, and the rest of its name names the rule that it breaks. The schema of an
example is the longest schema name that starts its file name. Each schema has at least 2 valid and 3 invalid
examples. All values are made up: host names end in `.example`, keys and tokens are runs of one letter.

## The validator

Run it from the root of the tree:

```
python3 -I schemas/validate.py
```

It needs Python 3 only. It loads each schema and stops on a keyword outside its subset of draft 2020-12, so
no keyword is ignored. It checks each example and the count of examples of each schema. A duplicate key in an
example is an error of that example. It prints one line for each failure and one summary line. It exits 0
when each check holds, else 1. When the Python package `jsonschema` is installed, each example also gets its
verdict, and a disagreement is a failure.

## Change a schema

1. Change the home file first.
2. Change the schema, and add an `invalid-` example for each new rule.
3. Run the validator until it exits 0.
