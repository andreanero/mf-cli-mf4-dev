import struct, sys, collections
f=open(sys.argv[1],'rb'); t0=None; cur=None; reads=collections.Counter()
while True:
    h=f.read(8)
    if len(h)<8: break
    bt,bl=struct.unpack('<II',h); b=f.read(bl-8)
    if bt!=6: continue
    cl=struct.unpack('<I',b[12:16])[0]; p=b[20:20+cl]
    if len(p)<64 or p[9]!=2: continue
    ts=struct.unpack('<q',p[16:24])[0]+struct.unpack('<i',p[24:28])[0]/1e6
    if t0 is None: t0=ts
    L,lc=struct.unpack('<II',p[32:40]); s=p[40:48]; ev=p[8:9]
    if ev==b'S' and L==8 and p[14]==0:
        rt,req,val,idx,ln=struct.unpack('<BBHHH',s)
        if rt & 0x80: reads[(hex(rt),hex(req),hex(val),hex(idx),ln)]+=1; cur=None; continue
        cur=(ts,rt,req,val,idx,ln)
        if ln==0: print(f"{ts-t0:8.3f} rt={rt:02x} req={req:02x} wValue={val:04x} wIndex={idx:04x} len=0"); cur=None
    elif cur and ev==b'S' and L>0:
        ts0,rt,req,val,idx,ln=cur
        data = p[64:64+lc] if lc else s[:min(L,8)]
        print(f"{ts0-t0:8.3f} rt={rt:02x} req={req:02x} wValue={val:04x} wIndex={idx:04x} len={ln} data={data.hex(' ')}{' (trunc)' if not lc and L>8 else ''}")
        cur=None
print("reads:", dict(reads))
