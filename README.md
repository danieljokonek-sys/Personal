# Max for Live Devices

A collection of custom Max for Live devices for Ableton Live.

## Repository Structure

```
devices/
  instruments/   — Max for Live instrument devices (.amxd)
  effects/       — Max for Live audio/midi effect devices (.amxd)
  midi/          — Max for Live MIDI tools and utilities (.amxd)
lib/             — Shared abstractions and reusable Max patches
presets/         — Device presets organized by device name
docs/            — Device documentation, design notes, signal flow diagrams
tests/           — Test patches and validation utilities
scripts/         — Build, export, and utility scripts
```

## Getting Started

### Requirements

- [Ableton Live Suite](https://www.ableton.com/en/live/) (11 or later recommended)
- [Max 8](https://cycling74.com/products/max) (bundled with Live Suite, or standalone license)

### Local Development Path

All local development lives in:

```
C:\Users\Owner\Claude Bots\max4live bots\
```

This folder maps to the root of this repository.

### Quick Setup (Windows / PowerShell)

Open PowerShell and run:

```powershell
# Clone the repo and set up device symlinks in one step
.\scripts\setup-windows.ps1
```

This will clone the repo, verify all device files, and create a symlink in Ableton's User Library so devices appear in Live's browser automatically.

### Manual Installation

1. Add the `devices\` folder to your Ableton Live User Library, or copy individual `.amxd` files into:
   - **Windows:** `C:\Users\Owner\Documents\Ableton\User Library\Presets\Max Audio Effect\` (or MIDI Effect / Instruments)
   - **macOS:** `~/Music/Ableton/User Library/Presets/Max Audio Effect/`

2. **Add JS files to Max's search path** (required for devices with JavaScript):
   - Open Max editor via any M4L device
   - **Options > File Preferences > +**
   - Add the folder containing the `.amxd` and its `.js` files

3. Restart Ableton Live. Your devices will appear in the browser under **User Library**.

## Development Workflow

### Creating a New Device

1. Open Ableton Live and create a new Max for Live device (or open an existing `.amxd`).
2. Save the device into the appropriate `devices/` subdirectory:
   - `devices/instruments/` for synths and samplers
   - `devices/effects/` for audio effects
   - `devices/midi/` for MIDI processors
3. If the device uses reusable sub-patches, place them in `lib/` and reference via Max's search path.
4. Add a brief doc in `docs/` describing the device's purpose, parameters, and signal flow.

### Conventions

- **Naming:** Use lowercase with hyphens for device files (e.g., `granular-delay.amxd`).
- **Abstractions:** Shared logic goes in `lib/` with a `m4l.` prefix (e.g., `m4l.lfo.maxpat`).
- **Presets:** Store presets in `presets/<device-name>/` as `.json` or `.maxpresets` files.
- **Versioning:** Bump the device version attribute in the Max patcher inspector when making breaking changes.

### Working with Max Patchers in Git

Max `.amxd` and `.maxpat` files are JSON-based. To get cleaner diffs:

```powershell
# View a readable summary of a Max patcher
python scripts\maxpat_diff.py devices\effects\my-effect.amxd

# Diff two versions of a patcher
python scripts\maxpat_diff.py old-version.amxd new-version.amxd
```

### Shared Abstractions (lib/)

The `lib/` directory contains reusable Max patches. Add this directory to your Max search path:

**Max > Options > File Preferences > Add `lib/`**

This lets any device reference shared abstractions by name without absolute paths.

## Device Catalog

| Device | Type | Description |
|--------|------|-------------|
| [Mix Feedback](devices/effects/mix-feedback/) | Audio Effect | Analyze your mix against 3-5 reference tracks and get specific, per-track mixing suggestions. Uses LOM to scan your session and read device parameters. |

## Contributing

1. Create a feature branch: `git checkout -b feature/my-device`
2. Develop and test your device in Ableton Live
3. Commit the `.amxd` file along with any new abstractions or docs
4. Open a pull request with a description of the device and a short demo if possible

## Resources

- [Max for Live Documentation](https://docs.cycling74.com/max8)
- [Ableton Max for Live Guide](https://www.ableton.com/en/live-manual/max-for-live/)
- [Cycling '74 Forums](https://cycling74.com/forums)
- [Max for Live API Reference](https://docs.cycling74.com/max8/vignettes/live_api_overview)

## License

MIT License — see [LICENSE](LICENSE) for details.
