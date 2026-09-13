The recovery smoke test used the retained normal Doom executable and the
previous normal core, recorded in `menu-build-hashes.txt`. It did not test
the experimental pipeline build.

All seven screenshots were inspected. The E1M1 save loaded, Doom OPTIONS
opened and closed, and the HUD was restored without leftover menu text.
Invulnerability switched the world rendering to the expected palette while
the HUD remained readable, and gameplay remained visible after OSD navigation.

MiSTer screenshots omit the OSD overlay. OSD activation was checked through
input routing: Doom was left on OPTIONS, then F12 and Down were pressed.
The Doom selection remained on OPTIONS. After F12 closed the OSD, Enter
opened Doom OPTIONS, confirming that the earlier Down was intercepted.
The key sequence and screenshot paths are in `menu-verified.jsonl`.

This is a short recovery and rendering smoke test. Audio was not recorded
or assessed by listening; it is not a long-duration stability result.
