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
