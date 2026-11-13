# Results of the exec prototypes

The three programs of this directory measure the ways to catch an exec and the takeover of file 07. Build each with `gcc -O2` (`shim.c` with `-static`). Both runs are on one x86_64 guest with 4 virtual processors, Linux 6.18. The host of the guest is shared, and its load differs between the runs: read the difference between two rows of one run, not a value alone.

## Run 1

Summary values. The raw log of this run is not kept.

| Measure | Value |
| --- | --- |
| bare fork, exec, wait of a static program | 626 to 642 us |
| bare fork, exec, wait of a dynamic program | 638 to 775 us |
| seccomp notification, answer `CONTINUE` | 660 to 706 us |
| `RET_TRACE` with fork events | 765 to 796 us |
| ptrace of every call | 1,519 to 2,272 us; 39.6 to 40.5 us per `getppid` |
| `getppid` under the filter | 87 to 95 ns against 78 to 97 ns bare |
| moved exec through the takeover | 1,105 to 1,144 us against 943 to 987 us for a direct exec of the stub |
| static launcher in front of `/bin/true` | 1,273 to 1,310 us against 757 to 775 us |

## Run 2

`./execbench /bin/true 2000`, three times. The columns are the mode, the time of one fork, exec and wait, and the time of one `getppid`.

```
bare           exec+wait   1058.2 us   getppid  103.2 ns
notify         exec+wait   1153.9 us   getppid  129.3 ns
notify+sync    exec+wait   1249.5 us   getppid  118.7 ns
ptrace-exec    exec+wait   1313.2 us   getppid  131.2 ns
ptrace-all     exec+wait   2946.1 us   getppid 50060.3 ns
bare           exec+wait   1064.9 us   getppid  102.0 ns

notify         exec+wait   1212.5 us   getppid  132.3 ns
notify+sync    exec+wait   1213.7 us   getppid  109.0 ns
ptrace-exec    exec+wait   1296.5 us   getppid  132.5 ns
ptrace-all     exec+wait   3065.7 us   getppid 50276.3 ns
bare           exec+wait   1078.0 us   getppid  100.8 ns

notify         exec+wait   1176.2 us   getppid  120.3 ns
notify+sync    exec+wait   1202.8 us   getppid  120.9 ns
ptrace-exec    exec+wait   1238.0 us   getppid  121.2 ns
ptrace-all     exec+wait   2902.1 us   getppid 50199.1 ns
bare           exec+wait   1083.7 us   getppid  100.4 ns
```

`./execbench ./shim 2000` against `./execbench /bin/true 2000`, the row `bare`, two times.

```
shim           exec+wait   1698.1 us
/bin/true      exec+wait   1020.6 us
shim           exec+wait   1692.2 us
/bin/true      exec+wait    995.2 us
```

`./takeover`, three times. Each run also prints the checks of the mechanism: the stub takes over the pid for `fork` plus `execve` and for `posix_spawnp`, a local `/bin/true` runs untouched, and the caller of a failed exec sees `ENOENT`.

```
moved exec via takeover 1883 us; direct exec of the stub 1367 us
moved exec via takeover 1652 us; direct exec of the stub 1315 us
moved exec via takeover 1480 us; direct exec of the stub 1287 us
```

## Both runs

| Measure | Run 1 | Run 2 |
| --- | --- | --- |
| seccomp notification over bare, exec stays local | +30 to +56 us (5 to 9 percent) | +90 to +130 us (8 to 12 percent) |
| `getppid` under the filter over bare | +8 to +12 ns | +7 to +30 ns |
| moved exec over a direct exec of the stub | +140 to +170 us | +190 to +520 us |
| static launcher over a direct exec | +500 us (70 percent) | +670 to +700 us (68 percent) |
| ptrace of every call, per exec | 1,519 to 2,272 us | 2,902 to 3,066 us |
