# Max for Live Development Guide

## Environment Setup

1. **Ableton Live Suite** (11+) — includes Max for Live
2. **Max 8** — launches automatically when editing M4L devices
3. **Git** — for version control of patcher JSON files

### Recommended Max Packages

- **CNMAT Externals** — advanced DSP objects
- **Bach** — computer-assisted composition
- **mi-gen~** — physical modeling (Mutable Instruments ports)

## Max for Live Architecture

### Device Types

| Type | File Suffix | Lives On |
|------|-------------|----------|
| Instrument | `.amxd` | MIDI track |
| Audio Effect | `.amxd` | Audio track (or return) |
| MIDI Effect | `.amxd` | MIDI track (before instrument) |

### Key Concepts

- **live.thisdevice** — reference to the hosting device; use for initialization
- **live.path / live.object / live.observer** — Live Object Model (LOM) access
- **plugsend~ / plugreceive~** — audio I/O within the device chain
- **live.dial / live.slider / live.menu** — UI objects that auto-map to Live parameters
- **pattr / autopattr** — parameter storage and recall

## Cross-Platform Compatibility (PC + Mac)

All devices in this repo **must** work on both Windows and macOS. Follow these rules:

### File Paths

- **Never use absolute paths** in patchers. No `C:\...` or `/Users/...` references.
- Use **relative paths** for all file references (samples, abstractions, sub-patchers).
- Use Max's **search path** mechanism (`Options > File Preferences`) instead of hardcoded paths.
- Abstractions in `lib/` are referenced by name only (e.g., `m4l.lfo`) — Max resolves them via search path.
- If a device loads external files at runtime (samples, config), use `conformpath` or `filepath` objects to normalize paths across OS.

### Externals & Dependencies

- **Avoid platform-specific externals.** Only use externals that ship builds for both `.mxe64` (Windows) and `.mxo` (macOS).
- Prefer built-in Max objects and `gen~` over third-party externals whenever possible — this guarantees cross-platform support with zero dependencies.
- If an external is required, document it in the device's doc file and verify it has both PC and Mac builds before using it.
- **Never use shell/system commands** (`shell`, `aka.osascript`, `mxj`) that are OS-specific.

### File Naming

- Use **lowercase with hyphens** for all filenames (e.g., `granular-delay.amxd`).
- Avoid spaces, special characters, and characters illegal on Windows (`< > : " / \ | ? *`).
- Keep filenames under 60 characters to avoid Windows path length issues.

### Audio & DSP

- Do not assume a specific sample rate — always query `dspstate~` and adapt.
- Use `gen~` for DSP where possible — it compiles natively on both platforms.
- Avoid platform-specific audio driver assumptions in device logic.

### UI & Fonts

- Use only **Max built-in fonts** (Arial, Lato, Ableton Sans) — custom fonts may not be installed on all systems.
- Use `live.*` UI objects which render consistently across platforms.
- Test that device width/height renders correctly on both OS (Windows may have different DPI scaling).

### JavaScript (js/jsui)

- If using `js` or `jsui` objects, avoid Node.js-style or OS-specific APIs.
- Use forward slashes (`/`) in any path strings within JS code — Max normalizes these on both platforms.
- Do not use `system()` or `exec()` calls.

### Checklist for Every Device

- [ ] No absolute file paths anywhere in the patcher
- [ ] No platform-specific externals
- [ ] Filenames are lowercase, no spaces, no special characters
- [ ] Fonts are Max built-ins only
- [ ] Sample rate independent (queries `dspstate~`)
- [ ] All dependencies documented in device doc

## Best Practices

### Performance

- Use `poly~` for voice management in instruments
- Minimize scheduler-thread work; prefer audio-thread processing
- Gate DSP with `mute~` or `selector~` when sections are inactive
- Avoid `js` in the audio thread; use `gen~` or `codebox~` instead

### UI Design

- Follow Ableton's Live UI Guidelines for consistent look and feel
- Use `live.*` UI objects for automatic parameter mapping
- Keep device width reasonable (max ~600px for standard use)
- Support both light and dark themes with `live.colors`

### Parameter Management

- Mark automatable parameters as **Parameter Mode: Stored**
- Give each parameter a unique short name and long name
- Set sensible ranges, default values, and units
- Use `pattr` for non-automatable internal state

### File Organization

- One `.amxd` per device in the appropriate `devices/` subfolder
- Shared abstractions in `lib/` with `m4l.` prefix
- Presets in `presets/<device-name>/`
- Complex devices can use sub-patchers saved alongside the main `.amxd`

## Live Object Model (LOM)

The LOM lets you control almost anything in Ableton Live from Max:

```
live_set
  ├── tracks[]
  │     ├── clip_slots[]
  │     ├── devices[]
  │     └── mixer_device
  ├── return_tracks[]
  ├── master_track
  └── scenes[]
```

Common patterns:

```max
# Get current track
[live.path thispath]
  → [live.path path up 2]
    → [live.object]

# Observe transport
[live.path live_set]
  → [live.observer @property is_playing]
```

## Testing Devices

1. Load the device in Ableton on an appropriate track type
2. Verify all parameters automate correctly
3. Test preset save/recall
4. Check CPU usage with Live's CPU meter
5. Test with different sample rates (44.1k, 48k, 96k)
6. Verify the device freezes/flattens correctly
7. **Cross-platform:** Test on both Windows and macOS before tagging a release
8. **Cross-platform:** Verify no missing externals or broken paths on either OS
9. **Cross-platform:** Check UI layout renders correctly on both (DPI differences)
