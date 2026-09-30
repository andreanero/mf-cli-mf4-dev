# MiniFuse 4 support: working notes

Status as of 2026-09-24. Branch `mf4-dev`, **nothing committed** (the user asked not to commit).

## Done

- Imported the MF4 change from `../mf-cli` (upstream commit `671dcae`, "experimental mf4 support"): PID `0xaf70`.
- `src/main.rs`: a `Model` enum, model detection before parsing targets (used by both the kernel-module path and the userspace path), and per-model selectors.
- `99-minifuse.rules`: added `af70`.
- `README.md`, `PKGBUILD`, `flake.nix`, `nix/package.nix`, `nix/module.nix`: now say "MiniFuse 1/2/4". The README has a per-model targets table and a Protocol section. The PKGBUILD is synced with the AUR, so the AUR copy needs the same description change.
- The kernel module (`kmod/minifuse_mod.c`) needs no change: it passes any `"%hx %d"` selector through.

### Targets verified on hardware (MF4, userspace path)

| Target | wValue | Verified |
|---|---|---|
| `inst1` / `inst` | `0x0000` | yes |
| `inst2` | `0x0001` | yes |
| `48v` | `0x0300` | yes (the manual says it covers inputs 1 and 2) |
| `monitor` | n/a | refused on the MF4 (it has no Direct Mono) |

`0x0400` / `0x0401` (the MF1/MF2 48V value) do nothing visible on the MF4.

## Protocol

Every setting is one control transfer: `bmRequestType 0x21`, `bRequest 0x22`, `wIndex 0`, 2-byte payload.
`wValue = (feature << 8) | channel`. Levels are signed 16-bit little-endian in **1/256 dB**, where `0x8000` means silent (-inf).

### MF4 mixer and other features, decoded from the captures (not yet verified by ear)

| Feature | wValue | Values | Evidence |
|---|---|---|---|
| Mixer channel level to the **left** bus | `0x1dNN` | dB (1/256) | fader moves; NN = mix source channel |
| Mixer channel level to the **right** bus | `0x27NN` | dB (1/256) | always paired with `0x1d`; pan = the L/R difference |
| Channel mute | `0x4dNN` | 1 = muted, 0 = unmuted | "mute / unmute" step |
| Mix master volume | `0x4600` | dB, down to -64 | "master volume" step |
| Out 1-2 USB-direct | `0x5800` | 0 = custom mix, 1 = USB direct | "USB off" step |
| Loopback source | `0x5a00` | 4 = USB 5-6, 5 = Cue2Mix, 6 = OUT 1-2, 7 = OUT 3-4 | loopback menu step |
| LED brightness | `0x0800` | steps (4 and 2 seen) | LED step |
| Trim link (inputs 3 and 4) | `0x0600` | 1 / 0 | Link clicked 3 times |
| Unknown | `0x50NN`, `0x53NN`, `0x56NN` | 0 / 1 | sent on first touch of a channel or on channel creation; probably app bookkeeping |

Adding an input to a mix created channels `06` and `07`: `0x1d06 = 0 dB` with `0x2706 = -inf` (left), and `0x1d07 = -inf` with `0x2707 = 0 dB` (right), with mute `0x4d06` / `0x4d07` = 1.

On connect the app writes `0x1d03`/`0x2703` and `0x1d05`/`0x2705` once.

Tested by ear: `4600 -inf`, then `4600 0dB`, with Out 1-2 in USB-direct mode, gave **no audible difference**. The master volume presumably only affects a custom mix.

### Status polling (read-only, for a future `status` or `meter` command)

- `GET 0xa1 / 0xc2` (64 bytes): polled constantly, probably meters.
- `GET 0xa1 / 0xb2` (190 bytes): state block; byte 14 flips to `01` when 48V is on.
- `GET 0xa1 / 0xa2 wValue 0x0700` (2 bytes).
- Standard UAC2 clock requests on entity `0x29` (clock 41).

## Open questions

1. **Output-pair addressing**: how does a mixer command select Out 1-2, Out 3-4 or Loopback? No write carries an output number; the low byte is always a source channel or `00`.
2. **Next hardware test (pending)**: with audio playing, run `5800 0`, then `4600 -inf`, then `4600 0dB`, then `5800 1`, and report what is heard after each step.
3. Out 3-4 volume (step 1 of the second capture) could not be clearly isolated. The best candidate is `0x1d00`/`0x2700` at 101 to 105 s. Ask whether 5 to 100 s was exploration.
4. Input 3 trim sent nothing. Ask whether the trim was actually moved.
5. Did the user turn USB back on at 294.7 s (`5800 = 1`)?
6. Sleep mode (holding the Arturia button) is probably front-panel only.
7. Not controllable over USB: gain knobs, Monitor Volume (Out 1-2), headphone knobs. The USB descriptor has no Feature Unit, and `amixer -c M4` shows no controls.

## MF1 / MF2

The manuals list nothing more that the app can control (only INST, 48V and meters). The only possible additions are read-only: meters and firmware version.

## Tools (this directory)

- `mf4-probe.py <wValue hex> <value>`: sends one command. The value can be `0` or `1`, an integer, `-12dB` or `-inf`. Needs `sudo`; it detaches `snd-usb-audio` from interface 0, which causes a short audio dropout.
- `decode-writes.py <pcap>`: lists the vendor writes and a count of reads.
- `decode-ctrl.py <pcap> [--std]`: reassembles control transfers.
- `mf4-usb-descriptor.txt`: `lsusb -v` output for the MF4.

### VirtualBox capture quirks

- The captures are pcapng with linktype 220 (usbmon mmapped).
- VirtualBox logs setup, data and status as separate URBs.
- The 8-byte setup stage is an `S` event on ep 0 with `length == 8` and `flag_setup == 0`, and the setup packet is in the setup field.
- The payload of an OUT data stage is not in the packet data. Its bytes overwrite the start of the setup field of the following `S` URB, which has `length == wLength`.

### Capture workflow

- VM `win10` (VirtualBox 7.1.18) with xHCI enabled.
- The auto-attach USB filter for the MiniFuse 4 is **disabled** (`VBoxManage usbfilter modify 0 --target win10 --active no`). While it was active it grabbed the device without capturing, which caused `LIBUSB_ERROR_BUSY`.
- To capture:
  ```
  U=$(VBoxManage list usbhost | awk '/^UUID/{u=$2} /ProductId:.*AF70/{print u}')
  VBoxManage controlvm win10 usbattach $U --capturefile ~/mf4-xxx.pcap
  # ...do the actions in Control Center, one every ~5 s...
  VBoxManage controlvm win10 usbdetach $U
  ```
- The UUID changes every time the device re-enumerates. Always look it up with the awk line above, because a looser grep once attached the webcam.

Existing captures (large, safe to delete once decoded):

| File | Size | Contents |
|---|---|---|
| `~/mf4.pcap` | 3.2 GB | INST and 48V |
| `~/mf4-out.pcap` | 541 MB | first mixer session |
| `~/mf4-out2.pcap` | 1.2 GB | second mixer session; steps 7 and 8 done in swapped order |

## Build

- The system cargo is 1.75, but the crate uses edition 2024, which needs 1.85 or newer, so `cargo build` fails in the repo.
- Workaround used for testing: copy `Cargo.toml` and `src/` to a temporary directory, set `edition = "2021"`, and build there. The code does not depend on edition 2024.
- Better fix: install a newer toolchain with rustup.

## Manuals

- MF1: https://dl.arturia.net/products/minifuse-1/manual/minifuse-1_Manual_1_0_0_EN.pdf
- MF2: https://dl.arturia.net/products/minifuse-2/manual/minifuse-2_Manual_1_0_0_EN.pdf
- MF4: https://dl.arturia.net/products/minifuse-4/manual/minifuse-4_Manual_1_0_0_EN.pdf (Control Center: chapter 6.2 Input Features, chapter 6.3 Output Features / Custom Mixes)
