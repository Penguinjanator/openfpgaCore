Normal MiSTer build smoke test, SS1, 2026-09-13.

The executable and core hashes in menu-build-hashes.txt match normal-mister
and normal-core in artifacts.json. The app runs without benchmark arguments
or recording instrumentation, using the private boot and save images.

Seven native 640×480 screenshots were inspected:

- normal-gameplay.png: the first-slot E1M1 save is loaded and rendering.
- doom-main.png: Escape opens the menu and Down selects OPTIONS.
- osd-intercept.png: F12 opens the MiSTer OSD; another Down leaves Doom's
  OPTIONS selection unchanged. The MiSTer screenshot command omits the OSD
  overlay, so navigation interception is used to verify OSD activation.
- doom-options.png: after closing the OSD, Enter opens Doom OPTIONS.
- options-closed.png: Escape returns to gameplay with the HUD restored.
- invulnerability.png: the standard cheat activates inverse world lighting.
- after-osd.png: gameplay with invulnerability remains active after another
  F12/open, Down/Up navigation and F12/close sequence.

No CPU trap or crash was observed. This is a short smoke test, not a long-term
stability claim or an audio-quality assessment. Audio was not recorded.
