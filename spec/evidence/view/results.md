# Results of the view scripts

`manifest_size.py TREE` encodes the directory records of a tree as file 06 describes them (name, kind, mode, size, modification time, a version of 8 bytes, and with `hash=True` a content id of 32 bytes for each file) and prints the size raw and with deflate level 6. `walk.py TREE` walks a tree two times and prints the time of the warm walk for each entry.

## A tree of 97,637 entries

Summary values. The raw output of this run is not kept.

| Measure | Value |
| --- | --- |
| records without content ids | 37.1 B per entry raw, 16.9 B per entry compressed |
| records with content ids | 63.0 B per entry raw, 43.7 B per entry compressed |

## A tree of 2,810 entries

The tree is the source tree of podcrates `v0.34.0`.

```
entries 2810 hash=False raw 102676 B (36.5 B/entry) zlib6 50887 (18.1 B/entry)
entries 2810 hash=True raw 180724 B (64.3 B/entry) zlib6 132384 (47.1 B/entry)
TREE 2810 entries 372 dirs first 0.007s warm 0.006s = 2.11 us/entry
```
