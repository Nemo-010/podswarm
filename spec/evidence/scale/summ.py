import re,sys
for f in sys.argv[1:]:
    print("==",f)
    print("W     B    tasks/s  meanB  pullp50 pullp99 ackp50 ackp99 commits/s ev/c  commit_ms p50/p99/max  coordcores rssMiB  us/task(w+s) wal_MB exit")
    t=open(f).read().split("### ")[1:]
    for blk in t:
        g=lambda p:re.search(p,blk)
        m=g(r"workers=(\d+) bundle=(\d+) dur=\S+ tail=\S+ lease_wait=\S+ ckpt=\S+ tasks=(\d+) wall=([\d.]+)s tasks_per_s=(\d+) mean_bundle=([\d.]+)")
        if not m: print(blk.split("\n")[0],"NO RESULT",blk[-100:].replace("\n"," ")); continue
        pl=g(r"pull_lat_ms p50=([\d.]+) p99=([\d.]+)\s+result_ack_lat_ms p50=([\d.]+) p99=([\d.]+)")
        c=g(r"commits=\d+ commits_per_s=(\d+) events_per_commit=([\d.]+) commit_ms p50=([\d.]+) p99=([\d.]+) max=([\d.]+)")
        cp=g(r"coord_cores=([\d.]+)\s+rss_hwm_mib=(\d+)")
        pt=g(r"writer=(\d+) sched=(\d+); wal_max_bytes=(\d+)")
        ex=g(r"exit=(\d+)")
        print(m.group(1).rjust(5),m.group(2).rjust(5),m.group(5).rjust(8),m.group(6).rjust(6),*[x.rjust(7) for x in pl.groups()],c.group(1).rjust(8),c.group(2).rjust(7),"/".join(c.groups()[2:]).rjust(18),cp.group(1).rjust(6),cp.group(2).rjust(6),(pt.group(1)+"+"+pt.group(2)).rjust(8),str(int(pt.group(3))//10**6).rjust(6),ex.group(1) if ex else "?")
