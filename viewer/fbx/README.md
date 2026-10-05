# Recordings for Visualize FBX

`demo_RK0F.fbx` is the only recording in the repository: one Captury take, included to demonstrate the viewer
(see LICENSE.md, section 6). The dataset it comes from is distributed separately.

To add your own recordings to the menu, copy them here and add a line to `index.json`; other FBX files in this folder
are ignored by git. Any FBX can also be opened with "Open your own FBX…" or by dropping it into the viewer window.

```json
{"file": "my_take.fbx", "name": "My take", "group": "My recordings", "frame": "2026-02"}
```

`frame` (`2026-02` = WishCap panel, `shot_003` = Captury) is used only for an FBX without cameras; a Captury FBX is
registered automatically from the cameras it contains.
