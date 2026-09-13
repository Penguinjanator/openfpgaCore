Normal MiSTer application menu smoke test, SS1, 2026-09-13.

The remote application and FPGA hashes are in menu-build-hashes.txt. They
match the final normal MiSTer ELF and normal core in artifacts.json. The
application has no diagnostic recorder or automated rotation enabled.
The core and game used the private profiling MGL and private disk copies.

Screenshots were inspected at their native 640×480 resolution. The MiSTer
screenshot command captures the game frame without the OSD overlay. OSD
activation was therefore checked through input interception:

1. menu-before-navigation.png shows Doom's LOAD GAME item selected.
2. Down with the OSD closed selects SAVE GAME in
   menu-navigation-osd-closed.png.
3. F12 followed by Down leaves SAVE GAME selected in
   menu-navigation-osd-open.png, showing that navigation was intercepted.
4. F12 closes the OSD; Escape then returns to the game. This return was
   inspected in the source capture escape-to-game.png.

doom-options.png confirms that the Doom OPTIONS screen opened.
gameplay-after-options.png confirms Escape returns directly to gameplay
with the HUD restored. No extra Escape is needed. Earlier automation sent
two Escapes, so its second Escape reopened the Doom main menu; screenshot
labels in menu-keys.log and menu-verified.jsonl describe requested states,
not assertions about the captured result. Subsequent steps corrected this.

Repeated F12 open/navigation/close sequences ran while Doom's main menu
was open without a CPU trap. The final sequence started in verified
gameplay, enabled standard invulnerability, then opened, navigated and
closed the OSD. invulnerability.png shows the inverse lighting and the
power-up message. gameplay-after-osd.png shows active gameplay with that
lighting and an intact HUD after closing the OSD. No crash was observed.

These checks cover a short normal-build menu smoke test. They do not
establish long-term stability or absence of audible distortion. No audio
recording or listening assessment was performed.
