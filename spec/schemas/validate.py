#!/usr/bin/env python3
"""Check every schema and every example of this directory. Needs Python 3 only.

Usage, from the root of the tree:  python3 -I schemas/validate.py

Rules:
* Each NAME.1.schema.json loads, and uses only the keywords of the set KEYWORDS.
  An unknown keyword is a failure, so a keyword is never ignored in silence.
* examples/valid-NAME-*.json must pass the schema NAME; examples/invalid-NAME-*.json must
  fail it. The schema of an example is the longest schema name that starts its file name.
* Each schema has at least 2 valid and 3 invalid examples.
* A duplicate key in an example is an error of that example (file 05, section 1, for a shape).

The validator implements the subset of JSON Schema draft 2020-12 that the schemas use.
When the Python package jsonschema is installed, each example also gets its verdict, and a
disagreement is a failure.

Output: one line per failure, then one summary line. Exit 0 when every check holds, else 1.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
MIN_VALID = 2
MIN_INVALID = 3

ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "default", "$defs"}
KEYWORDS = ANNOTATIONS | {
    "type", "enum", "const", "required", "properties", "additionalProperties", "propertyNames",
    "minProperties", "maxProperties", "items", "prefixItems", "minItems", "maxItems",
    "minimum", "maximum", "minLength", "maxLength", "pattern",
    "oneOf", "anyOf", "allOf", "not", "if", "then", "else", "$ref",
}
SUB_ONE = ("items", "additionalProperties", "not", "if", "then", "else", "propertyNames")
SUB_MAP = ("properties", "$defs")
SUB_LIST = ("oneOf", "anyOf", "allOf", "prefixItems")


class Unusable(Exception):
    """A schema cannot be used."""


class DuplicateKey(Exception):
    """An example has a duplicate key."""


def no_duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKey(key)
        out[key] = value
    return out


def same(a, b):
    """JSON equality: true is not 1, 1.0 is 1."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


class Checker:
    def __init__(self, docs):
        self.by_id = {}
        for name, doc in docs.items():
            if "$id" not in doc:
                raise Unusable(name + " has no $id")
            self.by_id[doc["$id"]] = doc

    def resolve(self, ref, root):
        base, _, frag = ref.partition("#")
        if base:
            if base not in self.by_id:
                raise Unusable("unresolved reference " + ref)
            root = self.by_id[base]
        node = root
        for part in [p for p in frag.split("/") if p]:
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                raise Unusable("unresolved reference " + ref)
            node = node[part]
        return node, root

    def check_keywords(self, schema, where, root):
        if isinstance(schema, bool):
            return
        if not isinstance(schema, dict):
            raise Unusable("schema is neither object nor boolean at " + where)
        for key, val in schema.items():
            if key not in KEYWORDS:
                raise Unusable("unknown keyword %r at %s" % (key, where))
            if key in SUB_MAP:
                for name, sub in val.items():
                    self.check_keywords(sub, where + "/" + key + "/" + name, root)
            elif key in SUB_ONE:
                self.check_keywords(val, where + "/" + key, root)
            elif key in SUB_LIST:
                for index, sub in enumerate(val):
                    self.check_keywords(sub, "%s/%s/%d" % (where, key, index), root)
            elif key == "$ref":
                self.resolve(val, root)
            elif key == "pattern":
                re.compile(val)

    @staticmethod
    def is_type(value, name):
        if name == "integer":
            return (isinstance(value, int) and not isinstance(value, bool)) or (isinstance(value, float) and value.is_integer())
        if name == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        kinds = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
        if name not in kinds:
            raise Unusable("unknown type " + name)
        return isinstance(value, kinds[name])

    def errors(self, value, schema, root, path="$"):
        """Return a list of error strings. An empty list means valid."""
        if schema is True:
            return []
        if schema is False:
            return [path + ": nothing is allowed here"]
        out = []
        if "$ref" in schema:
            target, new_root = self.resolve(schema["$ref"], root)
            out += self.errors(value, target, new_root, path)
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(self.is_type(value, n) for n in names):
                return out + ["%s: expected type %s" % (path, "|".join(names))]
        if "enum" in schema and not any(same(value, e) for e in schema["enum"]):
            out.append("%s: %s is not one of %s" % (path, json.dumps(value)[:40], json.dumps(schema["enum"])[:60]))
        if "const" in schema and not same(value, schema["const"]):
            out.append("%s: %s is not %s" % (path, json.dumps(value)[:40], json.dumps(schema["const"])))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                out.append("%s: %r is below %r" % (path, value, schema["minimum"]))
            if "maximum" in schema and value > schema["maximum"]:
                out.append("%s: %r is above %r" % (path, value, schema["maximum"]))
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                out.append("%s: shorter than %d" % (path, schema["minLength"]))
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                out.append("%s: longer than %d" % (path, schema["maxLength"]))
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                out.append("%s: %s does not match the pattern" % (path, json.dumps(value)[:40]))
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                out.append("%s: fewer than %d items" % (path, schema["minItems"]))
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                out.append("%s: more than %d items" % (path, schema["maxItems"]))
            prefix = schema.get("prefixItems", [])
            for index, item in enumerate(value):
                if index < len(prefix):
                    out += self.errors(item, prefix[index], root, "%s[%d]" % (path, index))
                elif "items" in schema:
                    out += self.errors(item, schema["items"], root, "%s[%d]" % (path, index))
        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    out.append("%s: missing required property %r" % (path, name))
            if "maxProperties" in schema and len(value) > schema["maxProperties"]:
                out.append("%s: more than %d properties" % (path, schema["maxProperties"]))
            if "minProperties" in schema and len(value) < schema["minProperties"]:
                out.append("%s: fewer than %d properties" % (path, schema["minProperties"]))
            props = schema.get("properties", {})
            for name, sub in value.items():
                if "propertyNames" in schema and self.errors(name, schema["propertyNames"], root, path):
                    out.append("%s: property name %r is not allowed" % (path, name))
                if name in props:
                    out += self.errors(sub, props[name], root, path + "." + name)
                elif "additionalProperties" in schema:
                    out += self.errors(sub, schema["additionalProperties"], root, path + "." + name)
        for sub in schema.get("allOf", []):
            out += self.errors(value, sub, root, path)
        if "anyOf" in schema and all(self.errors(value, sub, root, path) for sub in schema["anyOf"]):
            out.append("%s: matches none of anyOf" % path)
        if "oneOf" in schema:
            results = [self.errors(value, sub, root, path) for sub in schema["oneOf"]]
            hits = sum(1 for r in results if not r)
            if hits != 1:
                near = min((r for r in results if r), key=len, default=[])
                out.append("%s: matches %d of oneOf%s" % (path, hits, (" (" + near[0] + ")") if near and hits == 0 else ""))
        if "not" in schema and not self.errors(value, schema["not"], root, path):
            out.append("%s: matches the schema of not" % path)
        if "if" in schema:
            if not self.errors(value, schema["if"], root, path):
                out += self.errors(value, schema.get("then", True), root, path)
            else:
                out += self.errors(value, schema.get("else", True), root, path)
        return out


def second_opinion(docs):
    """Return a function (schema name, instance) -> bool valid, or None without jsonschema."""
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError:
        return None
    registry = Registry().with_resources([(d["$id"], Resource.from_contents(d)) for d in docs.values()])

    def run(name, instance):
        return Draft202012Validator(docs[name], registry=registry).is_valid(instance)

    return run


def main():
    failures = []
    docs = {}
    for path in sorted(HERE.glob("*.1.schema.json")):
        try:
            docs[path.name[: -len(".1.schema.json")]] = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
        except (ValueError, DuplicateKey) as problem:
            failures.append("SCHEMA %s does not load: %s" % (path.name, problem))
    if not docs:
        failures.append("no schema found in " + HERE.name)
    try:
        checker = Checker(docs)
        for name, doc in docs.items():
            checker.check_keywords(doc, name, doc)
            if "file " not in doc.get("description", ""):
                failures.append("SCHEMA %s has no home file in its description" % name)
    except (Unusable, re.error) as problem:
        failures.append("SCHEMA %s" % problem)
        checker = None
    other = second_opinion(docs) if checker else None
    seen = {name: {"valid": 0, "invalid": 0} for name in docs}
    count = 0
    for path in sorted((HERE / "examples").glob("*.json")) if checker else []:
        kind, _, rest = path.stem.partition("-")
        match = [n for n in docs if rest == n or rest.startswith(n + "-")]
        if kind not in ("valid", "invalid") or not match:
            failures.append("NAME %s names no kind or no schema" % path.name)
            continue
        name = max(match, key=len)
        count += 1
        seen[name][kind] += 1
        try:
            instance = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates)
            errs = checker.errors(instance, docs[name], docs[name])
        except DuplicateKey as key:
            instance, errs = None, ["duplicate key %s" % key]
        except (ValueError, Unusable) as problem:
            failures.append("LOAD %s: %s" % (path.name, problem))
            continue
        if kind == "valid" and errs:
            failures.append("FAIL %s: %s" % (path.name, errs[0][:160]))
        elif kind == "invalid" and not errs:
            failures.append("FAIL %s: accepted, must fail" % path.name)
        elif other is not None and instance is not None:
            theirs = other(name, instance)
            if theirs != (not errs):
                failures.append("DISAGREE %s: jsonschema says %s" % (path.name, "valid" if theirs else "invalid"))
    for name, counts in sorted(seen.items()):
        if counts["valid"] < MIN_VALID or counts["invalid"] < MIN_INVALID:
            failures.append("COVERAGE %s has %d valid and %d invalid examples; needs %d and %d" % (
                name, counts["valid"], counts["invalid"], MIN_VALID, MIN_INVALID))
    for line in failures:
        print(line)
    print("%d schemas, %d examples, %d failures, second opinion: %s" % (
        len(docs), count, len(failures), "jsonschema" if other else "not installed"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
