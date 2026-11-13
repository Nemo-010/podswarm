# evidence/scale

Output files of the coordinator prototype benchmark: one host, one run unless a file says otherwise. Files 03, 10 and 11 cite this directory as `evidence/scale/`.

Host: 8 vCPU Intel Xeon virtual machine, 14 GiB RAM, Linux 6.12.116, ext4 on virtio, loopback only. The server was not pinned and shared the CPUs with the load generator.

| Path | Command and content |
| --- | --- |
| `res/`, `res2/` | prototype runs with the schema of the prototype (five row writes per task, more than file 11): strict and batched durability, variants, checkpoint bytes |
| `m_strict.txt`, `a1_ckpt.txt`, `t1core.txt`, `tvar.txt`, `twin.txt` | single result files of the same prototype |
| `conn/` | the connection probe: source, `run.sh`, and outputs `cli_5000.txt`, `srv_5000.txt`, `cli_10000.txt`, `srv_10000.txt` (TLS with `rustls` and WebSocket framing with `tungstenite`, 5,000 and 10,000 connections) |
| `sizeb/` | the dependency skeleton whose stripped binary size is the A3 floor (source and manifest only) |
| `summ.py` | summary script over the prototype result files |

Not included: the prototype source tree, build directories, lock files and compiled binaries. The prototype cannot be rerun from this tree. The numbers are Observed on the host above and `scripts/verify.sh` does not reproduce them.

Limits of the measurements:
* Only a configuration with a `RESULT` line has a number. These configurations ended at the timeout (`exit=124`) and have no result: the coordinator pinned to one CPU (`taskset -c 0`) with 200 workers and bundles 10 and 100 (`res/core1.txt`); 10 workers, bundle 1, `ckpt=idle` (`res/strict_idle.txt`, `res2/ckpt_bytes.txt`); 10,000 workers with `ckpt=auto`, bundles 1 to 1,000 (`res/strict_auto.txt`). The cause is not known. `res/hang.out` holds one short run that ended (200 workers, bundle 10, 5 s); it records no hang.
* Only `a1_ckpt.txt`, `t1core.txt`, `tvar.txt` and `twin.txt` have `VERIFY` lines (a check of the store from outside after the run). The other files report the counters of the prototype only.
* No prototype run used an ARM host, an SD card, the wire, TLS or JSON. The connection probe of `conn/` used TLS and WebSocket framing only.
