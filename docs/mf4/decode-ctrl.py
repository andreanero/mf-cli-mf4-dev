#!/usr/bin/env python3
"""Stream a VirtualBox pcapng usbmon capture and print reassembled control
transfers. VirtualBox logs setup, data and status stages as separate URBs."""
import struct, sys

path = sys.argv[1]
show_std = "--std" in sys.argv
t0 = None
cur = None  # [ts, rt, req, val, idx, ln, data]

def emit(c):
    ts, rt, req, val, idx, ln, data = c
    if (rt & 0x60) == 0 and not show_std:
        return
    print(f"{ts - t0:9.3f} rt=0x{rt:02x} req=0x{req:02x} wValue=0x{val:04x} "
          f"wIndex=0x{idx:04x} wLen={ln:3d} {'IN ' if rt & 0x80 else 'OUT'} "
          f"{data.hex(' ') if data else '-'}")

with open(path, "rb") as f:
    while True:
        hdr = f.read(8)
        if len(hdr) < 8:
            break
        btype, blen = struct.unpack("<II", hdr)
        body = f.read(blen - 8)
        if btype != 6:
            continue
        caplen = struct.unpack("<I", body[12:16])[0]
        pkt = body[20:20 + caplen]
        if len(pkt) < 64 or pkt[9] != 2:
            continue
        ev, ep = pkt[8:9], pkt[10]
        tss, tsu = struct.unpack("<qi", pkt[16:28])
        length, lencap = struct.unpack("<II", pkt[32:40])
        ts = tss + tsu / 1e6
        if t0 is None:
            t0 = ts
        if ev == b"S" and ep == 0x00 and length == 8 and pkt[14] == 0:
            if cur:
                emit(cur)
            rt, req, val, idx, ln = struct.unpack("<BBHHH", pkt[40:48])
            cur = [ts, rt, req, val, idx, ln, b""]
        elif cur and cur[5] and not cur[6]:
            if cur[1] & 0x80 and ev == b"C" and ep == 0x80 and lencap:
                cur[6] = pkt[64:64 + lencap]
            elif not cur[1] & 0x80 and ev == b"S" and ep == 0x00 and lencap:
                cur[6] = pkt[64:64 + lencap]
    if cur:
        emit(cur)
