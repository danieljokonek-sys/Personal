# Mix Feedback Device

## Overview

A Max for Live audio effect that analyzes your mix against 3-5 reference tracks **you choose**, then gives detailed, specific suggestions for what to fix. Unlike generic analyzers, this device builds its target profile entirely from your references — it's trained on your taste, not a generic loudness curve.

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  1. LOAD REFERENCES (up to 5 tracks)                │
│     buffer~ ref1...ref5                             │
│         ↓                                           │
│  2. ANALYZE → IIR filter bank → feature extraction  │
│     Per-band RMS, peak, crest factor, dynamic range │
│     Stereo width + correlation per band             │
│     Transient density + strength                    │
│         ↓                                           │
│  3. BUILD COMPOSITE PROFILE (average of all refs)   │
│     = Your target sound                             │
├─────────────────────────────────────────────────────┤
│  4. CAPTURE MIX (master bus audio, 2-30 sec)        │
│     record~ → buffer~ → same analysis pipeline      │
│         ↓                                           │
│  5. COMPARE mix features vs reference profile       │
│     Calculate deltas per band, per feature          │
│     Flag issues by severity (info/suggest/warn/crit)│
│         ↓                                           │
│  6. GENERATE FEEDBACK                               │
│     Translate deltas into specific mixing advice    │
│     e.g. "Cut 2dB at 350Hz" not "reduce low-mids"  │
├─────────────────────────────────────────────────────┤
│  7. TRACK SCAN (optional, most powerful mode)       │
│     LOM enumerates all tracks in session            │
│     Solos each track → analyzes individually        │
│     Reads device chains + parameter values          │
│         ↓                                           │
│  8. PER-TRACK FEEDBACK                              │
│     Identifies which tracks cause which problems    │
│     References actual plugin parameters on tracks   │
│     e.g. "Track 'Vocals': your Compressor ratio is  │
│     4:1 — transients are lost, try 2:1 w/ 30ms atk" │
└─────────────────────────────────────────────────────┘
```

### What It Measures

| Feature | Per-Band | What It Tells You |
|---------|----------|-------------------|
| RMS Level | Yes (6 bands) | Spectral balance — where's the energy? |
| Peak Level | Yes | Headroom per frequency range |
| Crest Factor | Yes | How compressed each band is (peak minus RMS) |
| Dynamic Range | Yes | Loudness variation over time (10th-90th percentile) |
| Stereo Width | Yes | Mid/side energy ratio per band |
| Correlation | Yes | L/R phase relationship (-1 to +1) |
| Transient Density | Global | How many transients per second (punch) |
| Transient Strength | Global | How sharp the transients are |
| Mono Compatibility | Global | How much energy survives mono fold-down |

### Frequency Bands

| Band | Range | Typical Content |
|------|-------|-----------------|
| Sub | 20-60 Hz | Sub bass, kick sub |
| Low | 60-250 Hz | Bass fundamental, kick body |
| Low-Mid | 250-1000 Hz | Vocals body, guitar, muddiness zone |
| Mid | 1000-4000 Hz | Vocal presence, snare attack, guitar bite |
| High-Mid | 4000-8000 Hz | Sibilance, cymbal presence, harshness |
| High | 8000-20000 Hz | Air, sparkle, hi-hat shimmer |

## Usage

### Setup

1. Drop `mix-feedback.amxd` on your **master track** in Ableton Live
2. The device passes audio through unchanged — it's purely analytical

### Basic Workflow (Master Only)

1. **Load references**: Click Ref 1-5 buttons to load your reference tracks (WAV, AIFF, MP3)
2. **Click "Analyze Mix"**: The device captures 8 seconds of your master bus and analyzes it
3. **Read the feedback**: Specific suggestions appear in the text panel, scored by severity

### Advanced Workflow (Track Scan)

1. Load references and analyze as above
2. **Click "Scan Tracks"**: The device will:
   - Enumerate every track, group, and return in your session
   - Read all device chains and plugin parameters
   - Solo each track one at a time (4 seconds each)
   - Analyze each track's spectral and dynamic contribution
   - Unsolo and restore original solo states
3. **Per-track feedback** appears with specific suggestions referencing your actual plugins

### What the Feedback Looks Like

```
=== MIX FEEDBACK REPORT ===
Match Score: 62/100
Issues: 2 critical, 3 warnings, 4 suggestions

[!!] Low-Mid (250-1000Hz) is +4.2dB above references. Low-mids are muddy.
     This is the most common mix problem. Check for buildup from multiple
     instruments stacking around 250-500Hz. Cut 3dB on 2-3 of the busiest
     tracks at 300-400Hz with Q=1.5.

[!!] Mix crest factor is 4.1dB below references (5.2dB vs 9.3dB) — the mix
     is over-compressed. Try these in order: (1) Raise master bus compressor
     threshold by 2-4dB. (2) If ratio is above 4:1, reduce to 2:1-3:1.
     (3) Slow down the attack to 20-30ms to let transients through.

[!]  High (8000-20000Hz) is -2.8dB below references. Highs are dull/dark.
     Try a high shelf boost of 2dB at 10kHz on the mix bus.

=== PER-TRACK SUGGESTIONS ===

--- Bass ---
[!!] 'Bass' is contributing to Low-Mid (250-1000Hz) buildup (+4.2dB on master).
     Cut ~3dB at 500Hz with Q=1.5 on your Channel EQ.

--- Drums ---
[!]  'Drums' is over-compressed (crest: 4.8dB vs ref: 9.3dB). On your
     Glue Compressor: reduce ratio from 6.0:1 to ~3.6:1. Raise threshold
     by 3-5dB. Slow attack to 20-30ms to preserve transients.
```

## Files

| File | Purpose |
|------|---------|
| `mix-feedback.amxd` | Max patcher — the device you load in Ableton |
| `mix-feedback-engine.js` | Main JS engine — coordinates the workflow |
| `mf-analysis-core.js` | IIR filter bank and feature extraction |
| `mf-reference-profile.js` | Reference track loading and composite profile builder |
| `mf-track-scanner.js` | LOM track enumeration and solo-based scanning |
| `mf-comparator.js` | Mix vs reference comparison with delta calculation |
| `mf-suggestions.js` | Feedback text generator with mixing-specific advice |
| `mf-display.js` | JSUI visual display (spectrum bars, score meter) |

## Parameters

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| Capture Length | 2-30 sec | 8 sec | How long to record mix for analysis |
| Load Ref 1-5 | button | — | Load a reference track into each slot |
| Analyze Mix | button | — | Capture and analyze the master bus |
| Scan Tracks | button | — | Full track-by-track LOM scan |

## Technical Notes

### Cross-Platform

- All JS code uses Max's built-in `js` runtime — no Node.js, no externals
- No absolute paths — buffer~ reads via file dialog
- Uses only `Arial` font (built-in on both platforms)
- Tested IIR coefficients are sample-rate independent (adapts via `dspstate~`)

### Performance

- Reference analysis happens once per load (offline, reads buffer~)
- Mix capture analysis is one-shot (not real-time) — low CPU impact
- Track scan temporarily solos tracks — don't use during recording/performance
- The JS analysis of a typical buffer takes <1 second per track

### Customizing Thresholds

In `mf-comparator.js`, the `THRESHOLDS` object controls sensitivity:

```javascript
var THRESHOLDS = {
    bandRmsDb: 1.5,       // dB per band before flagging (raise = less sensitive)
    crestFactor: 1.5,     // dB crest factor difference
    dynamicRange: 2.0,    // dB dynamic range difference
    stereoWidth: 0.08,    // Width ratio difference
    // ... etc
};
```

Raise values for fewer, more significant suggestions. Lower for more detailed feedback.

## Changelog

- **v1.0** — Initial release: 6-band analysis, reference profiling, LOM track scan, per-track feedback with device parameter reading
