# 14. Network of a run

This file defines the network policy of an attempt: the values, the members of a pooled policy, how podswarm steers the traffic of one process tree with no root, the fallbacks and their reports, flows back to the caller's machine, exits, DNS, and what podswarm asks of podnet and podcrates. The shape field `net` and the header of a `net` stream are in file 05. The shield, which decides who can see the traffic on a host, is in file 13. The pool file, cells and the residency rule are in file 08. The keeper that starts the command is in file 12.

podswarm uses podnet through its command line and its sockets. It does not link the `podnet` crates.

## 1. The policy

The shape field `net` holds one policy string. The default is `pool`.

| Value | Meaning |
| --- | --- |
| `host` | The worker's own network. No hold. The traffic leaves the machine as the traffic of any local program does. |
| `pool` | Each flow takes one member of the pooled network (section 2), balanced per flow. Many flows use several uplinks at one time. A `pool` with one member is `host` and is reported as `host`. |
| `exit:NAME` | Every flow leaves through the exit NAME of the pool file (section 7). |
| `home` | Every flow leaves from the caller's machine (section 6). Never a default. |
| `none` | No network. A connect or a send to an IP address fails. Needs an enforced rung (section 4). |

The owner asked for this default: the pooled uplinks, balanced and aggregated.
* What podnet gives now: balance per flow. Each flow takes one member, and many parallel flows use the sum of the bandwidth of several uplinks.
* What podnet does not give: aggregation of one flow over several uplinks. One flow uses one uplink. This is ask N-4 to podnet (file 21) and risk K-16 (file 26).
So `pool` promises balance across flows only, and the run report says `aggregation: per_flow`.

### 1.1 The string
```
POLICY[;KEY=VALUE]...
```
| Key | Values, default | Meaning |
| --- | --- | --- |
| `require` | `any`, `advisory`, `enforced`; default `any` for `pool`, `advisory` for `exit:NAME` and `home`, `enforced` for `none` | The weakest hold level that the run accepts (section 4) |
| `strict` | `0` or `1`, `0` | `1`: a `pool` that cannot get its members is refused, not served as `host` |
| `members` | names joined by `+`, all allowed | The members of `pool` that the run may use |
| `balance` | `weighted`, `rr`, `minrtt`, `leastload`, `protect` (the names of podnet), `leastload` | How `pool` picks a member for each flow |
| `dns` | `policy`, `host`; `policy` | Where a name resolves (section 9) |
| `udp` | `auto`, `off`; `auto` | `off`: a UDP send fails |
| `home` | port list, at most 16, none | Loopback ports that reach the caller's machine (section 6.2) |

CLI: `--net POLICY` (file 18). The keys are modifiers of the string, not separate settings or flags. Example: `--net 'pool;require=enforced;home=5432,6379'`.

A workspace file cannot set `home`, `home=` or an `exit:` policy, and cannot lower `require`. Reason: these send the caller's network or traffic to a place that the user did not choose (file 08, residency conditions).

## 2. Members of a pooled policy

The members of `pool` for an attempt on worker W are, in this order:
1. **W's own uplinks.** The networks of the podnet configuration on W, or W's default route when podnet has none. This member is called `direct`.
2. **Pool machines with `uplink = true`** (file 08). A flow to such a member travels inside the link from W to the authority, and inside the link from the authority to that machine, which dials the destination. The authority relays: the home in a session, the coordinator in a swarm.
3. **The caller's machine**, when its pool entry `[host.local]` sets `uplink = true`.

A member serves a flow of a run only when the **member check** passes:

| Check | Rule |
| --- | --- |
| cell | The member's cell labels pass the selectors and the residency rule of the run (file 08). The caller's machine passes. |
| shield | Run at shield `none` or `private`: any member. Run at `guest` or `sealed`: the caller's machine and members with `trust = "own"` only. |
| user list | The member is in `members=` when the run sets it. |

Reason for the shield rule: a member sees the destination, the size and the timing of each flow, and the plaintext of a protocol with no TLS. At `private` the host's own interfaces already carry the run's traffic (file 13), so a shared member adds no new kind of exposure. At `guest` and `sealed` the run asked that a shared host see nothing, so only a machine that the user owns may carry its flows.

The same check applies to `exit:NAME` and to `home`. A failing member of `pool` is dropped and listed in the report. A failing exit or `home` refuses the run.

## 3. What podnet has

| Capability | State | Tracked by |
| --- | --- | --- |
| Multi WAN by networks and groups, one member per flow, policies `weighted`, `rr`, `minrtt`, `leastload`, `protect`, health probes, kill switch [EV-069] | works | |
| Pin a group to a member, rotate or reconnect a network, on a control socket | works | |
| Add or remove a door or a network while the router runs | absent | N-1 |
| Aggregation of one flow over several uplinks [EV-070] | absent, deferred | N-4 |
| Split of the request and the answer of a flow over two uplinks | UDP only, off by default | podnet issues 375, 473 |
| An exit role in podnet (a member that lends its egress) | absent; planned as services of a peer | podnet issues 466, 471; N-3 |
| An exit role in podssh (`podssh node --exit`, `podssh proxy --exit NAME`) [EV-071] | works, TCP only | |
| Rules by port, also on the loopback | absent: rules are by domain or CIDR | N-2 |
| Machine-readable report of `podnet pod` (backend, level, UDP limit) | one stderr line | N-5 |
| Hold of one process tree with no root: `netns` enforced, `seccomp` advisory [EV-072] | works | P-14 for the fork |
| User-mode IP stack (`pod-netstack`) | works | |
| WARP, WireGuard, Tailscale, NetBird as networks with no TUN | works (TCP; WireGuard also UDP) | |
| Egress proxy per job with an allow list (`pod-broker`) | library; its TLS end is open | podcrates T-100 |
| Kernel multi WAN (policy routing, nftables) | works with `CAP_NET_ADMIN` | not used: needs root |
| Systems | Linux only, static, 8 targets | |
| Library | thin; the router is not a library | podswarm uses the CLI |

## 4. Steering one process tree with no root

A program can ignore every hint, and a static program has its own resolver and makes its own sockets. So the policy is applied by a **hold**: a mechanism that catches the socket calls of the whole tree. The hold sends each caught flow to a **door**: a local endpoint of the worker that serves the policy (section 5).

| Rung | Mechanism | Level | UDP | Needs | Code |
| --- | --- | --- | --- | --- | --- |
| `guest` | The guest has no network card. A user-mode stack on a TUN device in the guest turns each flow into a stream of the inner channel to the exit of the policy (file 13). | enforced | yes | shield `guest` or `sealed` | `pod-netstack` in the guest |
| `netns` | A user namespace and a net namespace with a TUN or veth device; a user-mode stack in the supervisor carries each flow to the door. | enforced, except Unix sockets of the file system and inherited descriptors | datagrams of at most 1,500 bytes | unprivileged user namespaces; `/dev/net/tun` | `pod-hold` netns, `pod-netstack`; `podnet pod --backend netns` |
| `notify` | seccomp user notification on `connect`, `sendto`, `sendmsg` and `bind`; the supervisor answers with a descriptor of a socket to the door (`SECCOMP_ADDFD`). | advisory: Unix, netlink, raw and packet sockets, loopback TCP and inherited descriptors are not held | yes | Linux 5.14; a host that allows seccomp | `pod-hold` seccomp; `podnet pod --backend seccomp` |
| `deny` | Landlock TCP rules with no port, a seccomp deny of UDP, raw and packet sockets, and the Unix socket rule of `confined` (file 12). | enforced; serves `none` only | denied | Landlock ABI 4 (Linux 6.7); UDP by ABI 10 or the seccomp rule | `pod-confine` |
| `env` | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` and their lower-case forms point to a door on a loopback TCP port, with a random user and password per attempt in the URL. The door refuses a connection without them. | env: a program may ignore the variables | no | nothing | podswarm |

The levels, from strong to weak: `enforced`, `advisory`, `env`. A run with no hold has level `none`.

| Policy | Rungs, best first | Default `require` |
| --- | --- | --- |
| `host` | none | |
| `none` | `guest`, `netns` with no route, `deny` | `enforced` |
| `pool`, `exit:NAME`, `home` | `guest`, `netns`, `notify`, `env` | `any` for `pool`; `advisory` for the others |

The worker takes the best rung that it has. When that rung is below `require`, the run is refused. Reason for `advisory` on an exit: a flow that escapes the hold leaves through the host, which is the wrong place for an exit policy; the `notify` rung catches each connect of a static program.

Reason against the `env` rung for `none`: a variable cannot stop a program. A `none` that a program can ignore is a false promise, so `none` with no enforced rung is refused.

Kernel policy routing and nftables need `CAP_NET_ADMIN`. podswarm does not use them.

The kernel takes one seccomp listener per filter chain. So the `notify` rung does not run beside the exec filter of spreading (file 07) or the view rung `trap` (file 06): a spread session takes `netns` or `env`, and when the policy needs `notify` and no `netns` exists, spreading is off with a reason. One combined filter is later work.

## 5. Doors and flows

On a Linux worker with podnet, the worker runs one `podnet route` child with a configuration that it writes to its runtime directory. Each door is a Unix socket of mode 0600 in that directory: one door per policy and member set in use (`pool`, `exit-NAME`, `home`). The networks of the router are:
* `direct`: the uplinks of W (section 2).
* one member per remote member: the spec `socks5h+exec:psw net-exit MEMBER`. podnet starts the worker's own binary per connection; it speaks SOCKS5 on its stdio and joins a `net` stream of the link (file 05). podnet probes the health of each member through it.

The header of a `net` stream (file 05) names the attempt, the protocol (`tcp` or `udp`), the destination `dst`, and the `member`. `dst` is `NAME:PORT`, `IPV4:PORT` or `[IPV6]:PORT`. `member` is a machine name of the pool, or `direct`. A UDP stream carries datagrams, each with a 2-byte length before it. The worker opens a `net` stream for a flow of its attempt. The authority opens one toward the member that serves the flow (D-79; the header is in file 05). The authority and the member accept a `net` stream only for an open attempt whose policy names that member, and close the streams of an attempt when it ends.

Until podnet can add a door while it runs (N-1), the worker writes the configuration for the doors that the attempts of its link need, and starts a new router when that set changes. Each start takes milliseconds [T].

## 6. `home`: flows back to the caller

### 6.1 The policy `home`
Every flow of the attempt leaves from the caller's machine. The worker opens a `net` stream to the home. The home connects to the destination from the caller's machine, so the remote process reaches services of the caller's LAN. Names resolve on the caller's machine (section 9). A destination on the loopback of the attempt stays on the attempt's own loopback, except the ports of `home=`.

The user setting `net_home_allow` (a CIDR list, default all addresses) limits the destinations that the home dials for a remote attempt. A workspace file cannot set it.

### 6.2 Loopback ports: `home=PORTS`
With `home=5432,6379` on any policy, a connect of the attempt to `127.0.0.1:P`, `[::1]:P` or `localhost:P`, with P in the list, reaches port P on the loopback of the caller's machine through a `net` stream. Other flows follow the policy.

| Rung | How |
| --- | --- |
| `netns` | A listener of the supervisor on `lo` of the namespace, for each port of the list, joins each connection to a stream. |
| `notify` | The supervisor answers the `connect` with one end of a socket pair that it joins to a stream. |
| `env`, no hold | Refused. |

The home connects only to `127.0.0.1` or `::1`, only to a listed port, and only for an open attempt whose policy lists it. podswarm never opens a listener on the worker host for this, because another root user or another user of that host could connect to it.

`home` and `home=` are never a default. The user names them on the command line or in a user config file.

## 7. Exits

An exit is a named place where flows leave. It is a table `[exit.NAME]` in the pool file (file 08).

| Key | Meaning |
| --- | --- |
| `via` | `host:NAME`: a pool machine lends its uplink; flows travel through the authority to it. `podssh:NODE`: a podssh exit node, through `podssh proxy --exit NODE` as an `exec` member on the worker; TCP only. A podnet network spec that the podnet of the worker opens: `socks5h://...`, `wg:FILE`, `warp`, `tailscale:PATH`, `netbird:PORT`; a file in it is a path on the worker. |
| `trust`, `cell`, `region`, `juris` | Facts for the member check of section 2. An exit with no `trust` is `shared`. |

A run with `exit:NAME` sends every flow there or fails it. A UDP flow to an exit with TCP only fails at the hold, and the report counts it as `udp_refused`.

## 8. Fallbacks and reports

**Order.** The policy comes first, then the rung.
1. `pool` drops each member that fails the member check or is not healthy. When only `direct` stays, or W has no podnet, `pool` is served as `host`. With `strict=1` that is a refusal.
2. `exit:NAME`, `home` and `none` never change into another policy. When the worker cannot serve them, the run is refused. A silent `host` would send the traffic out of the wrong place, or out at all.
3. The worker takes the best rung of section 4. A rung below `require` refuses the run.

**Refusal.** Placement (file 08) skips a machine whose `caps.net` cannot serve the policy. When no machine of the pool can, the run fails with `needs_unsatisfiable` and the text names `net`. When the hold fails on the worker at start, the attempt ends `spawn_failed` with reason `isolation_refused` and the text names the rung.

**Report.** A fallback is reported and never silent. The run record has `net{asked, got, members[], dropped[{name, reason}], rung, level, aggregation, dns, egress?}`. `egress` is the public address of the member as the egress check of podnet sees it, when podnet gives one. When `got` differs from `asked`, the CLI prints one line on stderr, once per session for each machine and pair of values, also without `-v`:
```
podswarm: net: pool served as host on bigbox (no podnet)
```

## 9. DNS of an attempt

| Policy | Where a name resolves |
| --- | --- |
| `host` | The resolver of W. podswarm does not touch it. |
| `pool`, `exit:NAME` with `dns=policy` | At the member that dials the flow. The door receives the name (`socks5h`). On the `netns` rung the stack answers a query with an address of `198.18.0.0/15` and maps it back to the name. On the `notify` rung a send to port 53 of the attempt's resolver goes to the DNS door of podnet, which resolves at the member. |
| any held policy with `dns=host` | On W. The flow carries an address. |
| the `env` rung | The program resolves on W. The report says `dns: host`. |
| `home` | On the caller's machine, so names of the caller's LAN work. |
| `none` | No resolution. |

A program that sends its own DNS over HTTPS makes a flow like any other, and that flow follows the policy.

## 10. Who sees the traffic

The member that dials a flow sees its destination, its size and its timing, and the plaintext of a protocol with no TLS. TLS of the program protects the content from every hop. It does not hide the destination or the server name.

| Policy | What a co-tenant with root on W sees |
| --- | --- |
| `host`, or the member `direct` | The flows on the interfaces of W: destinations, server names, sizes, times, and plaintext with no TLS. |
| a podnet tunnel network on W (WireGuard, WARP, Tailscale) | On the interface only the packets of the tunnel, their sizes and times. The tunnel key and the plaintext are in a process on W: a root user who reads that memory sees them. |
| a remote member, an exit, `home` | On the wire only the link (ssh or TLS), its sizes and times. The hold supervisor on W holds each flow in the clear before it enters the link: a root user who reads that memory sees it. At `private` this is the stated limit of file 13. |
| any policy at `guest` or `sealed` | Only the inner channel. When the exit of the policy is W itself (`host` or `direct`), the relay on W dials and the host sees the destinations; the shield report says `net_exit: this_host` (file 13). |

Residency (file 08) does not govern the destinations of a program. It governs the members: a member must pass the cell check of section 2.

The worker policy `net_allow` (file 16) limits the destinations of each held flow on that worker. On boundary `confined` the ports of `confine.connect` (file 12) also apply to the destination of a held flow.

## 11. Where the hold is applied

The keeper of the attempt (file 12) applies the policy before the command runs. `pod-hold` forks the held child itself: `pod_hold::spawn` forks from a helper thread, and the `netns` hold makes the child enter its namespaces and send a descriptor back. The keeper of file 12 forks the payload too. Both cannot own one fork. So the keeper hands the fork to the hold, and the hold starts a **shim**: the podswarm binary with an internal flag, as the new spawner is started (file 12).

1. The keeper builds the plan of file 12 (argv, environment, `cwd`, limits, the confine spec) and writes it to a sealed `memfd`.
2. The hold starts the shim with the plan descriptor:
   * first form: the keeper's payload child applies the child state of file 12 without confinement and execs `podnet pod -x DOOR --backend RUNG -- psw SHIM FD`;
   * later form: the keeper links `pod-hold` and `pod-netstack`, calls the hold with the program `psw SHIM FD`, and serves the hold on a thread of its own.
3. The shim applies the confinement of file 12 (Landlock, the seccomp deny list, `no_new_privs`), closes the plan descriptor, and execs the command.

Order: the hold first (the filter or the namespaces), then confinement, then exec. A seccomp filter stays across `execve`, and Landlock after the filter is valid. The keeper stays the subreaper of the tree, so the tree kill, the limits and the accounting of file 12 hold. `podnet pod` must exit with the status of the command (N-5). Test E-27 of file 23 checks the `netns` hold under the `pidns` containment rung.

## 12. What the worker reports: `caps.net`

| Field | Type | Meaning |
| --- | --- | --- |
| `policies` | list of strings | The policies that the worker can serve now: `host`, `none`, `pool`, `exit`, `home` |
| `rungs` | list of strings | The hold rungs that work: `guest`, `netns`, `notify`, `deny`, `env` |
| `podnet` | string or null | The version of the podnet binary that the worker found |
| `uplinks` | list of strings | The names of the networks of `direct` |
| `udp` | boolean | UDP works on the best rung |

The worker looks for podnet by the setting `net_podnet`. With `net_podnet_copy`, the home copies a static podnet to a Linux worker as it copies its own binary (file 04), when a run needs a hold and the worker has none.

## 13. Asks

Each ask has a fallback in the podswarm repository. File 21 owns the ids, the milestones and the acceptance tests; this table names what this file needs.

| Id | To | Ask | Fallback |
| --- | --- | --- | --- |
| N-1 | podnet | Calls on the control socket that add and remove a door and a network while the router runs, with counters per door | A new router per change of the door set, with a written configuration (section 5) |
| N-2 | podnet | Rules by port: `tcp:HOST:PORT=WAY` and `port:N=WAY`, also on the loopback | podswarm maps the ports of `home=` in its own hold (section 6.2) |
| N-3 | podnet | `podnet exit --stdio`: a SOCKS5 server on stdio with UDP ASSOCIATE, or the peer service of podnet issue 471 | `psw net-exit`, the SOCKS5 helper of podswarm (section 5) |
| N-4 | podnet | A decision on the aggregation of one flow (issue 495): a plan, or "per flow only" in the documents | The report says `aggregation: per_flow`; nothing more is promised |
| N-5 | podnet | A machine-readable report of `podnet pod` (backend, level, UDP limit), and its exit status equal to the command's | Parse the stderr line; read the status from the shim |
| P-14 | podcrates | `pod-hold`: a `Program` that carries a plan to apply before exec, so the hold and the keeper share one fork | The shim of section 11 |

## 14. Milestones

Milestones are those of file 22.

| Milestone | Policies served | Rungs |
| --- | --- | --- |
| M1 (`podswarm run HOST -- cmd`) | `host` only. The default `pool` is served as `host` and reported once per session (`pool served as host`). `none`, `exit:NAME` and `home` are refused with reason `not_built`. | none |
| M7 | `none`; `pool` over the uplinks of W when podnet is on W; then `home`, `home=PORTS`, `exit:NAME`; the member check; then `pool` with members on other machines (section 2, items 2 and 3; risk K-17) | `deny`, `netns`, `notify` through `podnet pod`, then the linked `pod-hold` with the shim |
| M8 | flows of `guest` and `sealed` through the inner channel | `guest` |

## 15. Tests

File 23 holds the tests of this file: M-44 (`pool` with no podnet), M-45 (refusal of `none` and `exit:x`), E-27 (`netns` under `pidns`), E-28 (a static program on `notify`), E-29 (`none` on `netns` and `deny`), E-30 (`home=5432`), E-31 (UDP to a TCP-only exit), U-member (member check by shield).

## 16. Settings of this file

| Name | Default | Range | Meaning |
| --- | --- | --- | --- |
| `net` | `pool`; each modifier has the default of section 1.1 | the string of section 1.1 | the policy of a shape (field of file 05), of a run (`--net`) and of a user default |
| `net_home_allow` | all addresses | CIDR list, user config only | destinations that the home dials for `home` |
| `net_podnet` | `auto` (`PATH`, then the cache of file 04) | a path, `auto`, `off` | the podnet binary of a worker |
| `net_podnet_copy` | true | bool | the home copies podnet to a Linux worker that needs it |
