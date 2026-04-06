/**
 * mf-display.js
 * Mix Feedback Device — JSUI Display Component
 *
 * Renders the visual feedback panel inside a [jsui] object:
 *   - Spectral comparison bars (reference vs mix per band)
 *   - Match score meter
 *   - Status indicator
 *   - Severity color coding
 *
 * This file is loaded by [jsui @filename mf-display.js @size 580 320]
 */

// JSUI setup
mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

// ─── State ──────────────────────────────────────────────────────────

var refBands = [-60, -60, -60, -60, -60, -60];
var mixBands = [-60, -60, -60, -60, -60, -60];
var score = -1; // -1 = not yet analyzed
var statusText = "Load references to begin";
var refCount = 0;
var issueCount = 0;
var scanning = false;

var BAND_NAMES = ["Sub", "Low", "Lo-Mid", "Mid", "Hi-Mid", "High"];
var BAND_FREQS = ["20-60", "60-250", "250-1k", "1k-4k", "4k-8k", "8k-20k"];

// Colors
var BG = [0.12, 0.12, 0.14, 1.0];
var GRID = [0.25, 0.25, 0.28, 1.0];
var REF_COLOR = [0.3, 0.7, 0.9, 0.7];    // Blue for reference
var MIX_COLOR = [0.9, 0.6, 0.2, 0.85];   // Orange for mix
var TEXT_COLOR = [0.85, 0.85, 0.85, 1.0];
var DIM_TEXT = [0.5, 0.5, 0.55, 1.0];
var GOOD_COLOR = [0.2, 0.8, 0.4, 1.0];
var WARN_COLOR = [0.95, 0.75, 0.1, 1.0];
var BAD_COLOR = [0.95, 0.25, 0.2, 1.0];

// ─── Drawing ────────────────────────────────────────────────────────

function paint() {
	var width = mgraphics.size[0];
	var height = mgraphics.size[1];

	// Background
	mgraphics.set_source_rgba(BG);
	mgraphics.rectangle(0, 0, width, height);
	mgraphics.fill();

	// Title bar
	drawTitleBar(width);

	// Spectrum comparison
	drawSpectrum(10, 40, width - 20, 180);

	// Score meter
	drawScore(10, 230, 120, 80);

	// Status area
	drawStatus(140, 230, width - 150, 80);
}

function drawTitleBar(width) {
	mgraphics.set_source_rgba(TEXT_COLOR);
	mgraphics.set_font_size(13);
	mgraphics.move_to(10, 16);
	mgraphics.text_path("MIX FEEDBACK");
	mgraphics.fill();

	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(10);
	mgraphics.move_to(10, 30);
	var refText = refCount > 0 ? refCount + " ref" + (refCount > 1 ? "s" : "") + " loaded" : "no references";
	mgraphics.text_path(refText);
	mgraphics.fill();

	// Scanning indicator
	if (scanning) {
		mgraphics.set_source_rgba(WARN_COLOR);
		mgraphics.set_font_size(10);
		mgraphics.move_to(width - 100, 16);
		mgraphics.text_path("SCANNING...");
		mgraphics.fill();
	}
}

function drawSpectrum(x, y, w, h) {
	var barCount = 6;
	var barGap = 8;
	var barGroupWidth = (w - barGap * (barCount + 1)) / barCount;
	var barWidth = barGroupWidth / 2 - 2;
	var dbMin = -60;
	var dbMax = 0;
	var dbRange = dbMax - dbMin;

	// Grid lines
	mgraphics.set_source_rgba(GRID);
	mgraphics.set_line_width(0.5);
	for (var db = -50; db <= 0; db += 10) {
		var gy = y + h - ((db - dbMin) / dbRange) * h;
		mgraphics.move_to(x, gy);
		mgraphics.line_to(x + w, gy);
		mgraphics.stroke();

		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(8);
		mgraphics.move_to(x + w - 20, gy - 2);
		mgraphics.text_path(db + "");
		mgraphics.fill();
		mgraphics.set_source_rgba(GRID);
	}

	// Draw bars for each band
	for (var i = 0; i < barCount; i++) {
		var bx = x + barGap + i * (barGroupWidth + barGap);

		// Reference bar
		var refH = Math.max(2, ((refBands[i] - dbMin) / dbRange) * h);
		var refY = y + h - refH;
		mgraphics.set_source_rgba(REF_COLOR);
		mgraphics.rectangle(bx, refY, barWidth, refH);
		mgraphics.fill();

		// Mix bar
		var mixH = Math.max(2, ((mixBands[i] - dbMin) / dbRange) * h);
		var mixY = y + h - mixH;
		mgraphics.set_source_rgba(MIX_COLOR);
		mgraphics.rectangle(bx + barWidth + 2, mixY, barWidth, mixH);
		mgraphics.fill();

		// Delta indicator (colored line showing difference)
		var delta = mixBands[i] - refBands[i];
		if (Math.abs(delta) > 1.5 && refBands[i] > -55) {
			var deltaColor = Math.abs(delta) > 5 ? BAD_COLOR :
			                 Math.abs(delta) > 3 ? WARN_COLOR : GOOD_COLOR;
			mgraphics.set_source_rgba(deltaColor);
			mgraphics.set_font_size(9);
			var sign = delta > 0 ? "+" : "";
			mgraphics.move_to(bx + barWidth * 0.5, refY - 12);
			mgraphics.text_path(sign + delta.toFixed(1));
			mgraphics.fill();
		}

		// Band label
		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(9);
		mgraphics.move_to(bx, y + h + 12);
		mgraphics.text_path(BAND_NAMES[i]);
		mgraphics.fill();

		mgraphics.set_font_size(7);
		mgraphics.move_to(bx, y + h + 22);
		mgraphics.text_path(BAND_FREQS[i]);
		mgraphics.fill();
	}

	// Legend
	mgraphics.set_source_rgba(REF_COLOR);
	mgraphics.rectangle(x + w - 80, y - 5, 8, 8);
	mgraphics.fill();
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(9);
	mgraphics.move_to(x + w - 68, y + 3);
	mgraphics.text_path("Ref");
	mgraphics.fill();

	mgraphics.set_source_rgba(MIX_COLOR);
	mgraphics.rectangle(x + w - 40, y - 5, 8, 8);
	mgraphics.fill();
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.move_to(x + w - 28, y + 3);
	mgraphics.text_path("Mix");
	mgraphics.fill();
}

function drawScore(x, y, w, h) {
	// Score box
	mgraphics.set_source_rgba(GRID);
	mgraphics.rectangle(x, y, w, h);
	mgraphics.fill();

	if (score < 0) {
		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(11);
		mgraphics.move_to(x + 20, y + 40);
		mgraphics.text_path("--/100");
		mgraphics.fill();
	} else {
		// Score number with color
		var scoreColor = score >= 80 ? GOOD_COLOR :
		                 score >= 50 ? WARN_COLOR : BAD_COLOR;
		mgraphics.set_source_rgba(scoreColor);
		mgraphics.set_font_size(28);
		mgraphics.move_to(x + 12, y + 42);
		mgraphics.text_path(score + "");
		mgraphics.fill();

		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(11);
		mgraphics.move_to(x + (score >= 100 ? 72 : score >= 10 ? 58 : 40), y + 42);
		mgraphics.text_path("/100");
		mgraphics.fill();

		// Score bar
		var barY = y + 55;
		mgraphics.set_source_rgba([0.2, 0.2, 0.22, 1.0]);
		mgraphics.rectangle(x + 10, barY, w - 20, 6);
		mgraphics.fill();
		mgraphics.set_source_rgba(scoreColor);
		mgraphics.rectangle(x + 10, barY, (w - 20) * (score / 100), 6);
		mgraphics.fill();

		// Label
		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(9);
		mgraphics.move_to(x + 10, y + 75);
		mgraphics.text_path("MATCH SCORE");
		mgraphics.fill();
	}
}

function drawStatus(x, y, w, h) {
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(10);
	mgraphics.move_to(x, y + 14);
	mgraphics.text_path(statusText);
	mgraphics.fill();

	if (issueCount > 0) {
		mgraphics.set_font_size(9);
		mgraphics.move_to(x, y + 30);
		mgraphics.text_path(issueCount + " issue" + (issueCount !== 1 ? "s" : "") + " found");
		mgraphics.fill();
	}
}

// ─── Message Handlers ───────────────────────────────────────────────

function reference(vals) {
	// Receive reference band values: reference -25 -20 -18 -22 -30 -40
	if (arguments.length >= 6) {
		for (var i = 0; i < 6; i++) {
			refBands[i] = arguments[i];
		}
	} else if (vals && vals.length >= 6) {
		for (var j = 0; j < 6; j++) {
			refBands[j] = vals[j];
		}
	}
	mgraphics.redraw();
}

function mix(vals) {
	if (arguments.length >= 6) {
		for (var i = 0; i < 6; i++) {
			mixBands[i] = arguments[i];
		}
	} else if (vals && vals.length >= 6) {
		for (var j = 0; j < 6; j++) {
			mixBands[j] = vals[j];
		}
	}
	mgraphics.redraw();
}

function set_score(val) {
	score = val;
	mgraphics.redraw();
}

function status(text) {
	statusText = text;
	mgraphics.redraw();
}

function set_ref_count(val) {
	refCount = val;
	mgraphics.redraw();
}

function issues(val) {
	issueCount = val;
	mgraphics.redraw();
}

function set_scanning(val) {
	scanning = val ? true : false;
	mgraphics.redraw();
}

function bang() {
	mgraphics.redraw();
}
