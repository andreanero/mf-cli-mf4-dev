#!/usr/bin/env python3
"""Send one MiniFuse control command: mf4-probe.py <wValue hex> <value>
value: integer (0, 1, 4...), a level like -12dB, or -inf
Same transfer as mf-cli: bmRequestType 0x21, bRequest 0x22, wIndex 0, 2 data bytes."""
import ctypes, sys

VID, PID = 0x1C75, 0xAF70
wvalue = int(sys.argv[1], 16)
arg = sys.argv[2].lower()
if arg == "-inf":
    value = -32768
elif arg.endswith("db"):
    value = round(float(arg[:-2]) * 256)
else:
    value = int(arg, 0)

lib = ctypes.CDLL("libusb-1.0.so.0")
lib.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
lib.libusb_open_device_with_vid_pid.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16]
lib.libusb_control_transfer.argtypes = [ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint8,
                                        ctypes.c_uint16, ctypes.c_uint16, ctypes.c_char_p,
                                        ctypes.c_uint16, ctypes.c_uint]
for fn in ("libusb_detach_kernel_driver", "libusb_attach_kernel_driver",
           "libusb_claim_interface", "libusb_release_interface", "libusb_kernel_driver_active"):
    getattr(lib, fn).argtypes = [ctypes.c_void_p, ctypes.c_int]
lib.libusb_close.argtypes = [ctypes.c_void_p]
lib.libusb_error_name.restype = ctypes.c_char_p

lib.libusb_init(None)
h = lib.libusb_open_device_with_vid_pid(None, VID, PID)
if not h:
    sys.exit("MiniFuse 4 not found or permission denied (run with sudo)")

detached = lib.libusb_kernel_driver_active(h, 0) == 1
if detached:
    lib.libusb_detach_kernel_driver(h, 0)
try:
    r = lib.libusb_claim_interface(h, 0)
    if r:
        sys.exit(f"claim failed: {lib.libusb_error_name(r).decode()}")
    data = value.to_bytes(2, "little", signed=value < 0)
    r = lib.libusb_control_transfer(h, 0x21, 0x22, wvalue, 0, data, 2, 500)
    print(f"wValue=0x{wvalue:04x} data={data.hex(' ')} -> "
          + ("ok" if r == 2 else lib.libusb_error_name(r).decode()))
    lib.libusb_release_interface(h, 0)
finally:
    if detached:
        lib.libusb_attach_kernel_driver(h, 0)
    lib.libusb_close(h)
