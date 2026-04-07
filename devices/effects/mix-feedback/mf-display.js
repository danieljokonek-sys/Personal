/**
 * mf-display.js
 * Mix Feedback Device — Compact JSUI Display
 *
 * Horizontal layout designed to fit within Ableton's device view height limit.
 * Layout: [Score | Spectrum Bars | Status] — all in one ~100px tall strip.
 *
 * Loaded by [jsui @filename mf-display.js @size 580 100]
 */

mgraphics.init();
mgraphics.relative_coords = 0;
mgraphics.autofill = 0;

// ─── State ──────────────────────────────────────────────────────────

var refBands = [-60, -60, -60, -60, -60, -60];
var mixBands = [-60, -60, -60, -60, -60, -60];
var score = -1;
var statusText = "Load references to begin";
var refCount = 0;
var issueCount = 0;
var scanning = false;

var BAND_NAMES = ["Sub", "Low", "Lo-Mid", "Mid", "Hi-Mid", "High"];

// Colors
var BG = [0.12, 0.12, 0.14, 1.0];
var GRID = [0.25, 0.25, 0.28, 1.0];
var REF_COLOR = [0.3, 0.7, 0.9, 0.7];
var MIX_COLOR = [0.9, 0.6, 0.2, 0.85];
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

	// Layout: [Score 70px] [Spectrum rest] [Status 140px]
	var scoreW = 70;
	var statusW = 140;
	var spectrumX = scoreW + 5;
	var spectrumW = width - scoreW - statusW - 10;

	drawScoreCompact(0, 0, scoreW, height);
	drawSpectrumCompact(spectrumX, 0, spectrumW, height);
	drawStatusCompact(width - statusW, 0, statusW, height);
}

function drawScoreCompact(x, y, w, h) {
	// Score section
	mgraphics.set_source_rgba(GRID);
	mgraphics.rectangle(x, y, w, h);
	mgraphics.fill();

	if (score < 0) {
		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(10);
		mgraphics.move_to(x + 15, y + 35);
		mgraphics.text_path("--");
		mgraphics.fill();
	} else {
		var scoreColor = score >= 80 ? GOOD_COLOR :
		                 score >= 50 ? WARN_COLOR : BAD_COLOR;
		mgraphics.set_source_rgba(scoreColor);
		mgraphics.set_font_size(24);
		mgraphics.move_to(x + (score >= 100 ? 5 : score >= 10 ? 12 : 20), y + 40);
		mgraphics.text_path(score + "");
		mgraphics.fill();
	}

	// Label
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(7);
	mgraphics.move_to(x + 10, y + 12);
	mgraphics.text_path("SCORE");
	mgraphics.fill();

	// Score bar at bottom
	if (score >= 0) {
		var scoreColor2 = score >= 80 ? GOOD_COLOR :
		                  score >= 50 ? WARN_COLOR : BAD_COLOR;
		var barY = y + h - 8;
		mgraphics.set_source_rgba([0.2, 0.2, 0.22, 1.0]);
		mgraphics.rectangle(x + 4, barY, w - 8, 4);
		mgraphics.fill();
		mgraphics.set_source_rgba(scoreColor2);
		mgraphics.rectangle(x + 4, barY, (w - 8) * (score / 100), 4);
		mgraphics.fill();
	}

	// /100 label
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(8);
	mgraphics.move_to(x + 14, y + 52);
	mgraphics.text_path("/100");
	mgraphics.fill();
}

function drawSpectrumCompact(x, y, w, h) {
	var barCount = 6;
	var barGap = 4;
	var totalGaps = barGap * (barCount + 1);
	var barGroupWidth = (w - totalGaps) / barCount;
	var barWidth = (barGroupWidth - 2) / 2;
	var topPad = 14;
	var botPad = 16;
	var barAreaH = h - topPad - botPad;
	var dbMin = -50;
	var dbMax = 0;
	var dbRange = dbMax - dbMin;

	// Title
	mgraphics.set_source_rgba(TEXT_COLOR);
	mgraphics.set_font_size(8);
	mgraphics.move_to(x + 2, y + 10);
	mgraphics.text_path("MIX FEEDBACK");
	mgraphics.fill();

	// Legend
	mgraphics.set_source_rgba(REF_COLOR);
	mgraphics.rectangle(x + w - 55, y + 3, 6, 6);
	mgraphics.fill();
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(7);
	mgraphics.move_to(x + w - 47, y + 9);
	mgraphics.text_path("Ref");
	mgraphics.fill();

	mgraphics.set_source_rgba(MIX_COLOR);
	mgraphics.rectangle(x + w - 25, y + 3, 6, 6);
	mgraphics.fill();
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.move_to(x + w - 17, y + 9);
	mgraphics.text_path("Mix");
	mgraphics.fill();

	// Grid lines
	mgraphics.set_source_rgba(GRID);
	mgraphics.set_line_width(0.5);
	for (var db = -40; db <= 0; db += 20) {
		var gy = y + topPad + barAreaH - ((db - dbMin) / dbRange) * barAreaH;
		mgraphics.move_to(x, gy);
		mgraphics.line_to(x + w, gy);
		mgraphics.stroke();
	}

	// Bars
	for (var i = 0; i < barCount; i++) {
		var bx = x + barGap + i * (barGroupWidth + barGap);

		// Reference bar
		var refVal = Math.max(dbMin, Math.min(dbMax, refBands[i]));
		var refH = Math.max(2, ((refVal - dbMin) / dbRange) * barAreaH);
		var refY = y + topPad + barAreaH - refH;
		mgraphics.set_source_rgba(REF_COLOR);
		mgraphics.rectangle(bx, refY, barWidth, refH);
		mgraphics.fill();

		// Mix bar
		var mixVal = Math.max(dbMin, Math.min(dbMax, mixBands[i]));
		var mixH = Math.max(2, ((mixVal - dbMin) / dbRange) * barAreaH);
		var mixY = y + topPad + barAreaH - mixH;
		mgraphics.set_source_rgba(MIX_COLOR);
		mgraphics.rectangle(bx + barWidth + 2, mixY, barWidth, mixH);
		mgraphics.fill();

		// Delta
		var delta = mixBands[i] - refBands[i];
		if (Math.abs(delta) > 1.5 && refBands[i] > -48) {
			var deltaColor = Math.abs(delta) > 5 ? BAD_COLOR :
			                 Math.abs(delta) > 3 ? WARN_COLOR : GOOD_COLOR;
			mgraphics.set_source_rgba(deltaColor);
			mgraphics.set_font_size(7);
			var sign = delta > 0 ? "+" : "";
			mgraphics.move_to(bx, Math.max(y + topPad + 8, refY - 4));
			mgraphics.text_path(sign + delta.toFixed(1));
			mgraphics.fill();
		}

		// Band label
		mgraphics.set_source_rgba(DIM_TEXT);
		mgraphics.set_font_size(7);
		mgraphics.move_to(bx, y + h - 4);
		mgraphics.text_path(BAND_NAMES[i]);
		mgraphics.fill();
	}
}

function drawStatusCompact(x, y, w, h) {
	// Divider line
	mgraphics.set_source_rgba(GRID);
	mgraphics.set_line_width(1);
	mgraphics.move_to(x, y + 4);
	mgraphics.line_to(x, y + h - 4);
	mgraphics.stroke();

	x += 8;

	// Ref count
	mgraphics.set_source_rgba(DIM_TEXT);
	mgraphics.set_font_size(8);
	mgraphics.move_to(x, y + 14);
	var refText = refCount > 0 ? refCount + " ref" + (refCount > 1 ? "s" : "") + " loaded" : "no references";
	mgraphics.text_path(refText);
	mgraphics.fill();

	// Status
	mgraphics.set_source_rgba(TEXT_COLOR);
	mgraphics.set_font_size(8);
	mgraphics.move_to(x, y + 30);
	mgraphics.text_path(statusText);
	mgraphics.fill();

	// Issue count
	if (issueCount > 0) {
		mgraphics.set_source_rgba(WARN_COLOR);
		mgraphics.set_font_size(8);
		mgraphics.move_to(x, y + 46);
		mgraphics.text_path(issueCount + " issue" + (issueCount !== 1 ? "s" : "") + " found");
		mgraphics.fill();
	}

	// Scanning indicator
	if (scanning) {
		mgraphics.set_source_rgba(WARN_COLOR);
		mgraphics.set_font_size(9);
		mgraphics.move_to(x, y + 62);
		mgraphics.text_path("SCANNING...");
		mgraphics.fill();
	}
}

// ─── Message Handlers ───────────────────────────────────────────────

function reference() {
	if (arguments.length >= 6) {
		for (var i = 0; i < 6; i++) {
			refBands[i] = arguments[i];
		}
	}
	mgraphics.redraw();
}

function mix() {
	if (arguments.length >= 6) {
		for (var i = 0; i < 6; i++) {
			mixBands[i] = arguments[i];
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
