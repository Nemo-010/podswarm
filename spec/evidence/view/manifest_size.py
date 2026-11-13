import os, sys, struct, zlib, time
def varint(n):
    out=bytearray()
    while True:
        b=n&0x7f; n>>=7
        if n: out.append(b|0x80)
        else: out.append(b); return bytes(out)
def enc(root, with_hash):
    recs=[]; st=[root]; n=0
    while st:
        p=st.pop()
        try: ents=sorted(os.scandir(p), key=lambda e:e.name)
        except OSError: continue
        buf=bytearray(varint(len(ents)))
        for e in ents:
            try: s=e.stat(follow_symlinks=False)
            except OSError: continue
            nm=os.fsencode(e.name)
            buf+=varint(len(nm))+nm+bytes([1])+struct.pack('<H',s.st_mode&0o7777)+varint(s.st_size)+struct.pack('<q',s.st_mtime_ns)+struct.pack('<Q',hash((s.st_ino,s.st_ctime_ns))&(2**64-1))
            if with_hash and e.is_file(follow_symlinks=False): buf+=os.urandom(32)
            if e.is_dir(follow_symlinks=False): st.append(e.path)
            n+=1
        recs.append(bytes(buf))
    return n, b''.join(recs)
try:
    from compression import zstd
except Exception:
    zstd=None
for wh in (False, True):
    n,b=enc(sys.argv[1], wh)
    z=zlib.compress(b,6)
    line="entries %d hash=%s raw %d B (%.1f B/entry) zlib6 %d (%.1f B/entry)"%(n,wh,len(b),len(b)/n,len(z),len(z)/n)
    if zstd:
        zz=zstd.compress(b,3); line+=" zstd3 %d (%.1f B/entry)"%(len(zz),len(zz)/n)
    print(line)
