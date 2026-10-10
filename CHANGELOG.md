# Changelog

Each `## MT2 Tools Patch - <version>` section becomes that version's GitHub release notes (`python scripts/release.py`), and MT2 Tools shows them when it offers the update.

## MT2 Tools Patch - 0.6.2
### New
- **Themes panel**: once your mod has a theme, a **Themes** panel shows up under Asset. It lists every theme in the mod with its pieces; click a piece to import it, or to jump to it if it's already in the scene. No more hunting through folders with Import ▸ File after **New theme**. Right-click a theme to delete it.
- The **Theme** text box is gone. Pieces picked from Themes already know their theme, and a model made from scratch picks one from a list, so a typo can't split a wall and its turret into two folders anymore.
- **Import from game**: Shift-click a result to import it and keep the search open, so you can grab several models in a row.

## MT2 Tools Patch - 0.6.1
### Fixed
- Fixed an issue where a vehicle with no pads could be exported and crash the game when placed. Export now stops and tells you to add a pad with an entrance.
- Fixed the makeshift airship, the wizard airship and the turtle coming in without their deck pad when imported.

## MT2 Tools Patch - 0.6.0
### New
- **Updates from GitHub**: MT2 Tools now checks for a new release when Blender starts. If there is one, an **Update to …** button shows at the top of the MT2 tab: one click downloads and installs it, and hovering over it shows what's new. You can turn the check off, or run it by hand, in the add-on preferences. Needs Blender's *Allow Online Access* (Preferences ▸ System ▸ Network).

### Fixed
- Potenial crash that could occur if you use the helper "Flat Colors"

## MT2 Tools Patch - 0.5.9
### Fixed
- Fixed the costme glow material appearing on non-costume assets.

## MT2 Tools Patch - 0.5.8
### New
- **Glowing costume faces**: Select faces in Edit Mode and click **Materials ▸ glow**. They glow in their color slot, just as bright in sun, shade and at night, and players can still recolor them in the character editor. A darker shade makes them glow less.

### Fixed
- Fixed an issue where changing the material of one of the game's costume parts didn't count as a change, so the export kept using the game's original part and your new material never made it into the game.

## MT2 Tools Patch - 0.5.7
### New
- **Flat shading helper**: Fixes models that show soft color gradients across faces that should look sharp. Works on the whole model or only on the faces you've selected.

### Fixed
- Mod id capitals and spaces are cleaned up as you type, so you can't lock yourself out with a bad id. If the id is still invalid, the Setup button will remain visible telling you something ain't right.
- Fixed an issue with costumes where if you had two parts on one bone, the export only picked one of them and silently dropped the other. Now the export warns you about it and tells you to join the extra parts.
- Fixed an issue where moving parts that were exported under a bone, to a new bone, would not change the bone's attribute properly and cause the export checks to panic into a wall.
- Fixed an issue where Point Lights weren't hooked into the painting tool properly. Now you can change the light's color like you change any other surface using vertex colors.
