import os, sys, time
def walk(root):
    n=0; d=0; st=[root]
    while st:
        p=st.pop()
        try: it=os.scandir(p)
        except OSError: continue
        d+=1
        with it:
            for e in it:
                n+=1
                try:
                    s=e.stat(follow_symlinks=False)
                except OSError: continue
                if e.is_dir(follow_symlinks=False) and e.name!='target': st.append(e.path)
    return n,d
for r in sys.argv[1:]:
    t=time.perf_counter(); n,d=walk(r); t2=time.perf_counter()-t
    t=time.perf_counter(); walk(r); t3=time.perf_counter()-t
    print(r, n, "entries", d, "dirs", "first %.3fs warm %.3fs = %.2f us/entry"%(t2,t3,t3/max(n,1)*1e6))
