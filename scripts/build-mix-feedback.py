#!/usr/bin/env python3
"""
build-mix-feedback.py
Generates a minimal Max for Live Audio Effect patcher that Ableton will accept.

Run this, then open the output .amxd in Ableton Live.
The generated patcher includes:
  - plugin~ / plugout~ for audio passthrough
  - buffer~ objects for references and capture
  - record~ for mix capture
  - js engine loading
  - jsui display
  - textedit for feedback
  - live.text buttons for UI
  - All necessary patch cords

Usage:
    python build-mix-feedback.py
    python build-mix-feedback.py output-path.amxd
"""

import json
import sys
import os

def make_box(obj_id, maxclass, text=None, numinlets=1, numoutlets=1,
             outlettype=None, patching_rect=None, presentation=0,
             presentation_rect=None, extra=None):
    """Create a Max box object."""
    box = {
        "id": obj_id,
        "maxclass": maxclass,
        "numinlets": numinlets,
        "numoutlets": numoutlets,
    }
    if text is not None:
        box["text"] = text
    if outlettype is not None:
        box["outlettype"] = outlettype
    else:
        box["outlettype"] = [""] * numoutlets
    if patching_rect is not None:
        box["patching_rect"] = patching_rect
    else:
        box["patching_rect"] = [0, 0, 100, 22]
    if presentation:
        box["presentation"] = 1
        if presentation_rect:
            box["presentation_rect"] = presentation_rect
    if extra:
        box.update(extra)
    return {"box": box}


def make_line(src_id, src_outlet, dst_id, dst_inlet):
    """Create a patch cord."""
    return {
        "patchline": {
            "source": [src_id, src_outlet],
            "destination": [dst_id, dst_inlet]
        }
    }


def make_live_button(obj_id, label, param_short, param_long, px, py,
                     pres_x, pres_y, width=70, height=20):
    """Create a live.text button with proper parameter attributes."""
    return {"box": {
        "id": obj_id,
        "maxclass": "live.text",
        "numinlets": 1,
        "numoutlets": 2,
        "outlettype": ["", ""],
        "text": label,
        "texton": label,
        "mode": 0,
        "patching_rect": [px, py, width, height],
        "presentation": 1,
        "presentation_rect": [pres_x, pres_y, width, height],
        "parameter_enable": 1,
        "saved_attribute_attributes": {
            "valueof": {
                "parameter_shortname": param_short,
                "parameter_longname": param_long,
                "parameter_type": 2,
                "parameter_mmax": 1.0,
                "parameter_enum": ["val1", "val2"]
            }
        },
        "varname": param_long
    }}


def build_patcher():
    """Build the complete Mix Feedback patcher."""
    boxes = []
    lines = []

    # ─── Audio I/O ───────────────────────────────────────────────
    boxes.append(make_box("obj-1", "newobj", "plugin~ 2",
                          numinlets=1, numoutlets=3,
                          outlettype=["signal", "signal", ""],
                          patching_rect=[30, 30, 80, 22]))

    boxes.append(make_box("obj-2", "newobj", "plugout~ 2",
                          numinlets=3, numoutlets=0, outlettype=[],
                          patching_rect=[30, 600, 80, 22]))

    # Audio passthrough
    lines.append(make_line("obj-1", 0, "obj-2", 0))
    lines.append(make_line("obj-1", 1, "obj-2", 1))

    # ─── Buffers ─────────────────────────────────────────────────
    for i in range(1, 6):
        boxes.append(make_box(
            f"obj-ref{i}", "newobj", f"buffer~ ref{i}",
            numinlets=1, numoutlets=2,
            outlettype=["float", "bang"],
            patching_rect=[180 + (i-1)*110, 30, 95, 22]))

    boxes.append(make_box("obj-mixbuf", "newobj",
                          "buffer~ mix_capture 30000 2",
                          numinlets=1, numoutlets=2,
                          outlettype=["float", "bang"],
                          patching_rect=[180, 60, 185, 22]))

    boxes.append(make_box("obj-scanbuf", "newobj",
                          "buffer~ scan_capture 10000 2",
                          numinlets=1, numoutlets=2,
                          outlettype=["float", "bang"],
                          patching_rect=[380, 60, 190, 22]))

    # ─── Recording ───────────────────────────────────────────────
    boxes.append(make_box("obj-recmix", "newobj",
                          "record~ mix_capture 2",
                          numinlets=3, numoutlets=1,
                          outlettype=["signal"],
                          patching_rect=[30, 130, 145, 22]))

    boxes.append(make_box("obj-recscan", "newobj",
                          "record~ scan_capture 2",
                          numinlets=3, numoutlets=1,
                          outlettype=["signal"],
                          patching_rect=[30, 160, 150, 22]))

    # Audio into recorders
    lines.append(make_line("obj-1", 0, "obj-recmix", 0))
    lines.append(make_line("obj-1", 1, "obj-recmix", 1))
    lines.append(make_line("obj-1", 0, "obj-recscan", 0))
    lines.append(make_line("obj-1", 1, "obj-recscan", 1))

    # ─── JS Engine ───────────────────────────────────────────────
    boxes.append(make_box("obj-js", "newobj",
                          "js mix-feedback-engine.js",
                          numinlets=3, numoutlets=4,
                          outlettype=["", "", "", ""],
                          patching_rect=[200, 320, 180, 22]))

    # ─── JSUI Display ───────────────────────────────────────────
    boxes.append(make_box("obj-jsui", "jsui",
                          numinlets=1, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[200, 420, 580, 320],
                          presentation=1,
                          presentation_rect=[5, 5, 580, 320],
                          extra={"filename": "mf-display.js"}))

    # ─── Feedback Text Display ───────────────────────────────────
    boxes.append({"box": {
        "id": "obj-text",
        "maxclass": "textedit",
        "numinlets": 1,
        "numoutlets": 4,
        "outlettype": ["", "int", "", ""],
        "patching_rect": [450, 320, 380, 260],
        "presentation": 1,
        "presentation_rect": [5, 330, 580, 270],
        "readonly": 1,
        "wordwrap": 1,
        "fontsize": 10.0,
        "fontname": "Arial",
        "textcolor": [0.85, 0.85, 0.85, 1.0],
        "bgcolor": [0.15, 0.15, 0.17, 1.0],
        "border": 0,
        "rounded": 4.0
    }})

    # JS outlet 1 → feedback text
    lines.append(make_line("obj-js", 1, "obj-text", 0))
    # JS outlet 2 → jsui display
    lines.append(make_line("obj-js", 2, "obj-jsui", 0))

    # ─── Route status messages from JS outlet 3 ─────────────────
    boxes.append(make_box("obj-route", "newobj",
        "route status score ref_count issues scan_start scan_capture scan_complete start_mix_capture",
        numinlets=1, numoutlets=9,
        outlettype=[""] * 9,
        patching_rect=[200, 360, 580, 22]))

    lines.append(make_line("obj-js", 3, "obj-route", 0))

    # ─── Load Reference Buttons ──────────────────────────────────
    ref_buttons = []
    for i in range(1, 6):
        btn_id = f"obj-loadref{i}"
        boxes.append(make_live_button(
            btn_id, f"Ref {i}", f"Ref{i}", f"Load Ref {i}",
            px=180 + (i-1)*65, py=95,
            pres_x=5 + (i-1)*55, pres_y=607, width=50, height=20))

        # Trigger → read message → buffer
        trig_id = f"obj-trig{i}"
        read_id = f"obj-read{i}"
        boxes.append(make_box(trig_id, "newobj", "t b",
                              numinlets=1, numoutlets=1,
                              outlettype=["bang"],
                              patching_rect=[180 + (i-1)*65, 120, 30, 22]))
        boxes.append(make_box(read_id, "message", "read",
                              numinlets=2, numoutlets=1,
                              outlettype=[""],
                              patching_rect=[180 + (i-1)*65, 145, 35, 22]))

        lines.append(make_line(btn_id, 0, trig_id, 0))
        lines.append(make_line(trig_id, 0, read_id, 0))
        lines.append(make_line(read_id, 0, f"obj-ref{i}", 0))

    # ─── Analyze Mix Button ──────────────────────────────────────
    boxes.append(make_live_button(
        "obj-analyzebtn", "Analyze Mix", "Analyze", "Analyze Mix",
        px=200, py=200, pres_x=285, pres_y=607, width=90, height=20))

    # Analyze: first record mix, then analyze refs, then analyze mix
    boxes.append(make_box("obj-anal-t", "newobj", "t b b",
                          numinlets=1, numoutlets=2,
                          outlettype=["bang", "bang"],
                          patching_rect=[200, 225, 50, 22]))

    boxes.append(make_box("obj-recstart", "message", "1",
                          numinlets=2, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[200, 250, 25, 22]))

    boxes.append(make_box("obj-recstop-delay", "newobj", "delay 8000",
                          numinlets=2, numoutlets=1,
                          outlettype=["bang"],
                          patching_rect=[200, 275, 80, 22]))

    boxes.append(make_box("obj-recstop", "message", "0",
                          numinlets=2, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[200, 298, 25, 22]))

    boxes.append(make_box("obj-anal-refs-msg", "message",
                          "analyze_references",
                          numinlets=2, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[260, 275, 115, 22]))

    boxes.append(make_box("obj-anal-mix-msg", "message",
                          "analyze_mix",
                          numinlets=2, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[260, 298, 75, 22]))

    # Button → trigger
    lines.append(make_line("obj-analyzebtn", 0, "obj-anal-t", 0))
    # Trigger right outlet → start recording
    lines.append(make_line("obj-anal-t", 1, "obj-recstart", 0))
    lines.append(make_line("obj-recstart", 0, "obj-recmix", 2))
    # Trigger right outlet → delay → stop recording
    lines.append(make_line("obj-anal-t", 1, "obj-recstop-delay", 0))
    lines.append(make_line("obj-recstop-delay", 0, "obj-recstop", 0))
    lines.append(make_line("obj-recstop", 0, "obj-recmix", 2))
    # Delay done → analyze refs then mix
    lines.append(make_line("obj-recstop-delay", 0, "obj-anal-refs-msg", 0))
    lines.append(make_line("obj-anal-refs-msg", 0, "obj-js", 0))
    # Small delay after refs before mix analysis
    boxes.append(make_box("obj-mixdelay", "newobj", "delay 500",
                          numinlets=2, numoutlets=1,
                          outlettype=["bang"],
                          patching_rect=[260, 318, 70, 22]))
    lines.append(make_line("obj-recstop-delay", 0, "obj-mixdelay", 0))
    lines.append(make_line("obj-mixdelay", 0, "obj-anal-mix-msg", 0))
    lines.append(make_line("obj-anal-mix-msg", 0, "obj-js", 0))

    # ─── Scan Tracks Button ──────────────────────────────────────
    boxes.append(make_live_button(
        "obj-scanbtn", "Scan Tracks", "Scan", "Scan Tracks",
        px=330, py=200, pres_x=380, pres_y=607, width=90, height=20))

    boxes.append(make_box("obj-scan-msg", "message", "scan_tracks 4",
                          numinlets=2, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[330, 225, 85, 22]))

    lines.append(make_line("obj-scanbtn", 0, "obj-scan-msg", 0))
    lines.append(make_line("obj-scan-msg", 0, "obj-js", 0))

    # ─── live.thisdevice for init ────────────────────────────────
    boxes.append(make_box("obj-thisdev", "newobj", "live.thisdevice",
                          numinlets=0, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[700, 30, 100, 22]))

    boxes.append(make_box("obj-loadbang", "newobj", "loadbang",
                          numinlets=1, numoutlets=1,
                          outlettype=["bang"],
                          patching_rect=[700, 60, 65, 22]))

    boxes.append(make_box("obj-init-msg", "message", "get_status",
                          numinlets=2, numoutlets=1,
                          outlettype=[""],
                          patching_rect=[700, 85, 68, 22]))

    lines.append(make_line("obj-loadbang", 0, "obj-init-msg", 0))
    lines.append(make_line("obj-init-msg", 0, "obj-js", 0))

    # ─── Assemble Patcher ────────────────────────────────────────
    patcher = {
        "patcher": {
            "fileversion": 1,
            "appversion": {
                "major": 8,
                "minor": 6,
                "revision": 5,
                "architecture": "x64",
                "modernui": 1
            },
            "classnamespace": "box",
            "rect": [100, 100, 1000, 800],
            "bglocked": 0,
            "openinpresentation": 1,
            "default_fontsize": 12.0,
            "default_fontface": 0,
            "default_fontname": "Arial",
            "gridonopen": 1,
            "gridsize": [15.0, 15.0],
            "gridsnaponopen": 1,
            "objectsnaponopen": 1,
            "statusbarvisible": 2,
            "toolbarvisible": 0,
            "lefttoolbarpinned": 0,
            "toptoolbarpinned": 0,
            "righttoolbarpinned": 0,
            "bottomtoolbarpinned": 0,
            "toolbars_unpinned_last_save": 0,
            "tallnewobj": 0,
            "boxanimatetime": 200,
            "enablehscroll": 1,
            "enablevscroll": 1,
            "devicewidth": 600,
            "description": "Mix Feedback - compare your mix against reference tracks.",
            "digest": "Personalized mix feedback based on your reference tracks.",
            "tags": "analysis mixing feedback",
            "style": "",
            "subpatcher_template": "",
            "assistshowspatchername": 0,
            "boxes": boxes,
            "lines": lines,
            "parameters": {
                "parameterbanks": {
                    "0": {
                        "index": 0,
                        "name": "",
                        "parameters": []
                    }
                }
            },
            "dependency_cache": [
                {"name": "mix-feedback-engine.js", "bootpath": ".", "type": "TEXT"},
                {"name": "mf-analysis-core.js", "bootpath": ".", "type": "TEXT"},
                {"name": "mf-reference-profile.js", "bootpath": ".", "type": "TEXT"},
                {"name": "mf-track-scanner.js", "bootpath": ".", "type": "TEXT"},
                {"name": "mf-comparator.js", "bootpath": ".", "type": "TEXT"},
                {"name": "mf-suggestions.js", "bootpath": ".", "type": "TEXT"},
                {"name": "mf-display.js", "bootpath": ".", "type": "TEXT"}
            ]
        }
    }

    return patcher


def main():
    # Default output path: same directory as this script's parent
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_output = os.path.join(script_dir, "..", "devices", "effects",
                                  "mix-feedback", "mix-feedback.amxd")

    output_path = sys.argv[1] if len(sys.argv) > 1 else default_output
    output_path = os.path.normpath(output_path)

    patcher = build_patcher()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(patcher, f, indent="\t", ensure_ascii=False)

    print(f"Built: {output_path}")
    print(f"Objects: {len(patcher['patcher']['boxes'])}")
    print(f"Connections: {len(patcher['patcher']['lines'])}")
    print()
    print("Next steps:")
    print(f"  1. Open Ableton Live")
    print(f"  2. Drag {os.path.basename(output_path)} onto your Master track")
    print(f"  3. If it won't load, open it in Max directly (File > Open)")
    print(f"     then save as .amxd from Max (File > Save As)")


if __name__ == "__main__":
    main()
