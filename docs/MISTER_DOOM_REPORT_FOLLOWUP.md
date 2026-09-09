# MiSTer DOOM report follow-up

The reported platform is MiSTer. The screenshot reports music fading/distorting
while SFX continue, menu residue on the HUD, frame drops, and a return to the
startup console. The exact game/core versions, map, duration and music settings
have not been supplied. These fixes reproduce specific defects in the code;
they do not establish which defect caused that particular gameplay failure.

## Mixer ownership

`src/firmware/os/hal/mixer.c` is called directly through the service table from
both the game and the MIDI timer callback. Flat MMIO addresses avoid a shared
selector register, but do not make allocating a voice atomic.

Before this change, playback selected a slot, incremented its generation and
marked it inactive, then restored interrupts while flushing samples and writing
registers. A MIDI callback could claim that same slot. The interrupted caller
then overwrote its registers and returned a handle whose generation was already
stale. Group updates also assembled two packed words without excluding an
interrupt, allowing an older snapshot to overwrite a callback's group assignment.

Playback now validates and flushes samples before selecting a slot. Selection,
generation, group assignment, register programming and activation share one
critical section. The expensive sample flush retains the caller's interrupt
state; it does not add a long interrupt blackout to main-thread SFX preparation.
Legacy playback also updates the hardware group when resetting a reused voice
to SFX. Explicit group changes and legacy stop protect their shared updates.

Retriggering uses the same ordering and validates the original handle after
writeback. If a callback stole the voice during that interval, retrigger fails
without overwriting the new owner. Invalid samples no longer invalidate the
original handle. A pending end from the previous playback is cleared before
the new generation starts.

The allocator no longer frees slots by intersecting its active state with
`MIX_ACTIVE_MASK`. That hardware mask excludes queued starts; the software
backend also updates its mask after rendering. A full pool of pending starts
could therefore be handed out again. Slots now become free through pending
end notifications or explicit stops, with the existing strictly-lower-priority
steal policy when full. This deliberately removes the unsafe mask-based
recovery of allegedly missed ends; the existing end queue remains in use.

## HUD and visible faults

The companion DOOM change invalidates the current status-bar cache before a
menu/message/debug overlay draws. This addresses Options-to-parent-menu
transitions, automap menus and delayed reuse of any of the three framebuffers.
The existing close-menu clearing remains in place. The previous SIGIL wall-math
candidate is retained in the game build.

The MiSTer fatal-trap path used to restore only the startup console and send
exception details to UART, which is unavailable on this target. It now draws
the cause, PC, fault address, SP and return address directly into the terminal
framebuffer before mirroring it to the displayed buffer. The renderer, labels
and font live in BRAM and use no allocator or mutable terminal state. A host
pixel test verifies the values, hexadecimal formatting and framebuffer bounds.
The first six console rows hold the report; remaining log rows are preserved.
This diagnoses future exceptions; it is not a fix for an unidentified crash.

`couldn't open DOOMMUS.WAD` is an optional PCM-pack lookup. The existing code
falls back to MIDI when it is absent. The line is not evidence that a required
game WAD was missing or that this lookup caused the later exit.

## Validation

- Nine production-HAL regression scenarios pass with AddressSanitizer and
  UndefinedBehaviorSanitizer. All nine fail against `176c163`'s mixer. They
  cover allocation/retrigger interruption, stolen handles, delayed hardware
  acknowledgement, group reuse, rejected buffers and end delivery. The boundary
  scenario attempts interrupt injection at 60 service/MMIO/cache boundaries for
  each of four operations (240 attempts), including entry with interrupts off.
- The existing MIDI scheduler and 20-voice synth lifetime regressions pass.
- The RTL mixer suite passes 146 checks. The MiSTer output suite passes 12,000
  stereo samples across 90/100 MHz patterns, including deliberate underrun and
  reset during a clock change. These are simulations, not listening tests.
- All 22 DOOM smoothness regressions pass under both sanitizers. The new HUD
  regression fails against the previous status-bar implementation.
- Official firmware-container builds pass for MiSTer and Pocket. MiSTer uses
  14,072 of its 16,384 reserved OS BRAM bytes. The crash display is MiSTer-only;
  including it in Pocket exceeded that target's existing BRAM budget, so the
  Pocket trap path remains unchanged. DOOM's official MiSTer build succeeds;
  its application BRAM still ends at `0x77f0`, leaving 16 bytes.

Commands:

```sh
python3 tools/check_mixer_ownership.py
python3 tools/check_midi_scheduler.py
python3 tools/check_smp_voice_lifetime.py
cc -std=c11 -Wall -Wextra -Werror -O2 -fsanitize=address,undefined -no-pie \
  tools/tests/test_trap_screen.c -o /tmp/openfpgaos-trap-screen-test
/tmp/openfpgaos-trap-screen-test
make -C src/fpga/test audio-mixer mister-audio-output
# In the Doom repository:
python3 tools/check_smoothness.py --sanitize
```

## Test package and remaining evidence

`build/review-mister-report/candidate/` holds the matching MiSTer RBF, `boot.rom`
and `doom.elf`, with patches, hashes and build/test evidence. This is a local
test package, not a new public release. No WAD, save or launcher is replaced.
The trap-handler change requires the new RBF as well as the OS image.

Quartus 17 updates the BRAM contents in an isolated copy of the exact released
v0.9.1 fit (original RBF SHA-256
`d02a50e6633093d1b975771a3130e10e0bb1e444fe53818f9d72a7dab31bab90`).
The fitted logic and clock settings are unchanged. CDB confirms it processed
the new `firmware.mif`; assembly succeeds. Inherited project warnings concern
the absent `rtl/pll.qip` reference and absent `cfgstr.hex`, whose contents were
left unchanged in the fitted database. This is a MIF update, not a new fit.
The existing 28,068-ALM fit's -0.206 ns setup slack at 100 MHz remains an open
timing limitation; this work does not claim timing closure or an ALM reduction.

Hardware confirmation needs the affected MiSTer to run the same map and music
past its usual failure point, then exercise Options/back, automap menus, pause,
level transitions and sound-heavy combat. Record the exact package and a photo
of any new exception screen. Stable 60 FPS, a resolved gameplay crash and the
absence of audible distortion have not been measured on that machine.
