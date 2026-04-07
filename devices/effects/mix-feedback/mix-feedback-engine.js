/**
 * mix-feedback-engine.js
 * Mix Feedback Device — Main Engine (Max [js] object entry point)
 *
 * This is the top-level script loaded by the [js] object in the Max patcher.
 * It includes all sub-modules and exposes message handlers that the patcher
 * calls to drive the analysis workflow.
 *
 * Workflow:
 *   1. User loads 1-5 reference tracks into buffer~ objects
 *   2. User clicks "Analyze References" → builds composite reference profile
 *   3. User clicks "Analyze Mix" → captures + analyzes master bus audio
 *   4. User clicks "Scan Tracks" → LOM solos each track, analyzes individually
 *   5. User clicks "Get Feedback" → generates detailed suggestions
 *
 * Outlets:
 *   0: Messages to patcher (scan control, UI updates)
 *   1: Feedback text lines (to textedit or jsui)
 *   2: Spectral data (to multislider display)
 *   3: Score/status (to UI elements)
 */

// Max js object configuration
inlets = 3;   // 0: commands, 1: live band measurements, 2: scan capture data
outlets = 4;  // 0: patcher control, 1: feedback text, 2: spectral, 3: status

// ─── Include Sub-Modules ────────────────────────────────────────────
// In Max's [js], we use include() to load other JS files from the same dir

include("mf-analysis-core.js");
include("mf-reference-profile.js");
include("mf-track-scanner.js");
include("mf-comparator.js");
include("mf-suggestions.js");

// ─── State ──────────────────────────────────────────────────────────

var mixProfile = null;
var mixStereoProfile = null;
var lastComparison = null;
var lastTrackComparisons = [];
var lastFeedback = [];

// Helper: send status/score/etc to both outlet 3 (route) and outlet 2 (JSUI)
function sendToUI(msg, val) {
	outlet(3, msg, val);
	outlet(2, msg, val);
}

var liveAnalysis = {
	capturing: false,
	captureBuffer: "mix_capture",
	captureDurationSec: 8,
	bandLevels: [0, 0, 0, 0, 0, 0],
	bandPeaks: [0, 0, 0, 0, 0, 0]
};

// ─── Command Handlers (inlet 0) ─────────────────────────────────────

/**
 * Analyze all loaded reference tracks and build composite profile.
 */
function analyze_references() {
	post("Analyzing reference tracks...\n");
	sendToUI("set_working", 1);
	sendToUI("set_progress_label", "Analyzing references");
	sendToUI("set_progress", 0);
	sendToUI("status", "Analyzing references...");

	// Count loaded buffers first
	var loadedCount = 0;
	for (var c = 0; c < 5; c++) {
		var testBuf = new Buffer(bufferNames[c]);
		if (testBuf && testBuf.framecount() > 0) loadedCount++;
	}

	if (loadedCount === 0) {
		post("No reference tracks loaded. Load audio into ref1-ref5 buffers.\n");
		sendToUI("set_working", 0);
		sendToUI("status", "No references loaded");
		return;
	}

	var count = 0;
	for (var i = 0; i < 5; i++) {
		sendToUI("set_progress", (i / 5));
		sendToUI("status", "Analyzing ref " + (i + 1) + " of 5...");
		var profile = analyzeReference(i);
		if (profile) {
			count++;
			post("  Reference " + (i + 1) + ": " +
			     profile.durationSec.toFixed(1) + "s, " +
			     profile.mono.globalRmsDb.toFixed(1) + " dB RMS\n");
		}
	}

	sendToUI("set_progress", 0.9);
	sendToUI("status", "Building composite profile...");

	var composite = buildComposite();
	post("Composite profile built from " + count + " references.\n");
	post("  Target RMS: " + composite.globalRmsDb.toFixed(1) + " dB\n");
	post("  Target crest factor: " + composite.crestFactor.toFixed(1) + " dB\n");
	post("  Target stereo width: " + Math.round(composite.stereoWidth * 100) + "%\n");

	// Send spectral profile to display
	outputSpectralData("reference", composite.bands);

	sendToUI("set_progress", 1.0);
	sendToUI("set_working", 0);
	sendToUI("status", "References analyzed (" + count + " tracks)");
	sendToUI("set_ref_count", count);

	// Auto-compare if mix was already analyzed
	tryCompare();
}

/**
 * Analyze the mix captured in the mix_capture buffer.
 * The patcher records master bus audio into this buffer before calling this.
 */
function analyze_mix() {
	post("Analyzing mix...\n");
	sendToUI("set_working", 1);
	sendToUI("set_progress_label", "Analyzing mix");
	sendToUI("set_progress", 0);
	sendToUI("status", "Analyzing mix...");

	var audio = readBuffer(liveAnalysis.captureBuffer);
	if (!audio) {
		post("Mix capture buffer is empty. Record your mix first.\n");
		sendToUI("set_working", 0);
		sendToUI("status", "No mix audio captured");
		return;
	}

	// Mono analysis
	sendToUI("set_progress", 0.1);
	sendToUI("status", "Converting to mono...");
	var mono = new Array(audio.frames);
	for (var i = 0; i < audio.frames; i++) {
		mono[i] = (audio.left[i] + audio.right[i]) * 0.5;
	}

	sendToUI("set_progress", 0.2);
	sendToUI("status", "Extracting spectral features...");
	var features = extractFeatures(mono, audio.sampleRate, 0.1);

	sendToUI("set_progress", 0.5);
	sendToUI("status", "Analyzing stereo field...");
	var stereo = extractStereoFeatures(audio.left, audio.right, audio.sampleRate);

	sendToUI("set_progress", 0.8);
	sendToUI("status", "Detecting transients...");
	var transients = extractTransients(mono, audio.sampleRate);

	// Build mix profile in same shape as composite reference
	mixProfile = {
		globalRmsDb: features.globalRmsDb,
		globalPeakDb: features.globalPeakDb,
		crestFactor: features.crestFactor,
		dynamicRange: features.dynamicRange,
		bands: features.bands,
		stereoWidth: stereo.stereoWidth,
		monoCompatibility: stereo.monoCompatibility,
		bandCorrelation: stereo.bandCorrelation,
		bandWidth: stereo.bandWidth,
		transientDensity: transients.density,
		transientStrength: transients.avgStrength
	};

	mixStereoProfile = stereo;

	post("Mix analyzed: " + features.durationSec.toFixed(1) + "s captured\n");
	post("  RMS: " + features.globalRmsDb.toFixed(1) + " dB\n");
	post("  Crest factor: " + features.crestFactor.toFixed(1) + " dB\n");
	post("  Stereo width: " + Math.round(stereo.stereoWidth * 100) + "%\n");

	// Send spectral to display
	sendToUI("set_progress", 0.95);
	sendToUI("status", "Generating results...");
	outputSpectralData("mix", features.bands);

	sendToUI("set_progress", 1.0);
	sendToUI("set_working", 0);
	sendToUI("status", "Mix analyzed");

	// Auto-compare if both sides are ready
	tryCompare();
}

/**
 * Auto-compare if both reference profile and mix profile exist.
 * Called at the end of both analyze_references and analyze_mix.
 */
function tryCompare() {
	if (getComposite() && mixProfile) {
		compare();
		// Also try generating per-track feedback if scan data exists
		generate_track_feedback();
	}
}

/**
 * Compare mix against reference profile and generate feedback.
 */
function compare() {
	var composite = getComposite();
	if (!composite) {
		post("No reference profile yet — analyze references first.\n");
		sendToUI("status", "Waiting for references...");
		return;
	}
	if (!mixProfile) {
		post("No mix profile yet — analyze your mix first.\n");
		sendToUI("status", "Waiting for mix analysis...");
		return;
	}

	post("Comparing mix to references...\n");
	sendToUI("status", "Comparing...");

	lastComparison = compareMixToReference(mixProfile, composite);

	post("  Score: " + lastComparison.overallScore + "/100\n");
	post("  Issues: " + lastComparison.totalIssues + "\n");

	sendToUI("set_score", lastComparison.overallScore);
	sendToUI("issues", lastComparison.totalIssues);

	// Generate and output feedback
	outputFeedback();
}

/**
 * Start the track-by-track scan using LOM.
 */
function scan_tracks(durationSec) {
	if (!durationSec) durationSec = 4;
	startScan(durationSec);
}

/**
 * Called by patcher when a track's capture is complete.
 * Analyzes the captured audio and stores the track profile.
 */
function track_captured(trackIndex) {
	var audio = readBuffer(scanState.captureBuffer);
	if (!audio) {
		post("Track capture buffer empty for track " + trackIndex + "\n");
		scanNextTrack();
		return;
	}

	var mono = new Array(audio.frames);
	for (var i = 0; i < audio.frames; i++) {
		mono[i] = (audio.left[i] + audio.right[i]) * 0.5;
	}

	var features = extractFeatures(mono, audio.sampleRate, 0.1);
	var stereo = extractStereoFeatures(audio.left, audio.right, audio.sampleRate);

	var trackFeatureProfile = {
		globalRmsDb: features.globalRmsDb,
		globalPeakDb: features.globalPeakDb,
		crestFactor: features.crestFactor,
		dynamicRange: features.dynamicRange,
		bands: features.bands,
		stereoWidth: stereo.stereoWidth,
		bandCorrelation: stereo.bandCorrelation
	};

	receiveTrackAnalysis(trackIndex, trackFeatureProfile, stereo);

	// Continue to next track
	scanNextTrack();
}

/**
 * Generate per-track comparisons after scan is complete.
 * Called when scan_complete message is received, or auto-triggered
 * when reference/mix analysis completes and track data is waiting.
 */
function generate_track_feedback() {
	var composite = getComposite();
	var profiles = getTrackProfiles();
	var hasTrackData = false;
	for (var t = 0; t < profiles.length; t++) {
		if (profiles[t]) { hasTrackData = true; break; }
	}

	if (!hasTrackData) {
		// No track scan done yet — nothing to do
		return;
	}

	if (!composite || !mixProfile) {
		post("Track scan data is ready — waiting for " +
		     (!composite ? "reference analysis" : "mix analysis") +
		     " before generating per-track feedback.\n");
		sendToUI("status", "Track data ready — waiting for " +
		         (!composite ? "references" : "mix analysis"));
		return;
	}

	var tracks = getSessionTracks();
	lastTrackComparisons = [];

	for (var i = 0; i < profiles.length; i++) {
		if (profiles[i]) {
			var tc = compareTrackContribution(
				profiles[i].features,
				mixProfile,
				composite,
				profiles[i].track
			);
			if (tc && tc.issues.length > 0) {
				lastTrackComparisons.push(tc);
			}
		}
	}

	post("Per-track analysis complete. " + lastTrackComparisons.length +
	     " tracks have suggestions.\n");

	// Re-generate feedback with track data
	outputFeedback();
}

/**
 * Abort an in-progress scan.
 */
function abort_scan() {
	abortScan();
}

// ─── Inlet 1: Live Band Measurements ───────────────────────────────
// The patcher sends real-time band levels from biquad~ + snapshot~

function msg_int(v) {
	// Not used for this inlet configuration
}

/**
 * Receive real-time band level measurements from the patcher.
 * Message format: band_level <band_index> <rms_db>
 */
function band_level(bandIndex, rmsDb) {
	if (bandIndex >= 0 && bandIndex < 6) {
		liveAnalysis.bandLevels[bandIndex] = rmsDb;
	}
}

/**
 * Receive real-time band peak measurements.
 */
function band_peak(bandIndex, peakDb) {
	if (bandIndex >= 0 && bandIndex < 6) {
		liveAnalysis.bandPeaks[bandIndex] = peakDb;
	}
}

// ─── Configuration ──────────────────────────────────────────────────

/**
 * Set the capture duration for mix analysis.
 */
function set_capture_duration(seconds) {
	liveAnalysis.captureDurationSec = Math.max(2, Math.min(30, seconds));
	post("Capture duration set to " + liveAnalysis.captureDurationSec + "s\n");
}

/**
 * Set the capture buffer name for mix analysis.
 */
function set_mix_buffer(name) {
	liveAnalysis.captureBuffer = name;
}

/**
 * Set reference buffer names.
 */
function set_ref_buffer(index, name) {
	if (index >= 0 && index < 5) {
		bufferNames[index] = name;
	}
}

// ─── Output Functions ───────────────────────────────────────────────

function outputFeedback() {
	lastFeedback = generateFeedback(lastComparison, lastTrackComparisons);

	// Clear previous feedback
	outlet(1, "clear");

	// Send each line
	for (var i = 0; i < lastFeedback.length; i++) {
		outlet(1, "append", lastFeedback[i]);
	}

	sendToUI("status", "Feedback ready (" + lastFeedback.length + " lines)");
}

function outputSpectralData(label, bands) {
	// Send band RMS values to JSUI display as individual arguments
	// Max's outlet doesn't pass arrays — must send each value separately
	outlet(2, label,
		bands[0].rmsDb, bands[1].rmsDb, bands[2].rmsDb,
		bands[3].rmsDb, bands[4].rmsDb, bands[5].rmsDb);
}

// ─── Full Analysis Shortcut ─────────────────────────────────────────

/**
 * Run the complete analysis pipeline:
 * 1. Analyze references
 * 2. Analyze mix
 * 3. Compare and generate feedback
 */
function full_analysis() {
	analyze_references();

	// The patcher needs to capture mix audio between these steps
	// So we signal the patcher to start capture, then call analyze_mix
	// when capture is complete
	outlet(0, "start_mix_capture", liveAnalysis.captureDurationSec);
}

/**
 * Run the complete pipeline including track scan.
 */
function full_analysis_with_tracks() {
	analyze_references();
	outlet(0, "start_full_scan");
}

// ─── Utility ────────────────────────────────────────────────────────

function get_status() {
	var refCount = getLoadedCount();
	var hasMix = mixProfile !== null;
	var hasComparison = lastComparison !== null;
	var trackCount = getTrackProfiles().length;

	post("Status:\n");
	post("  References loaded: " + refCount + "\n");
	post("  Mix analyzed: " + (hasMix ? "yes" : "no") + "\n");
	post("  Comparison: " + (hasComparison ? "score " + lastComparison.overallScore : "not run") + "\n");
	post("  Tracks scanned: " + trackCount + "\n");
	post("  Scanning: " + (isScanInProgress() ? "yes" : "no") + "\n");
}

function bang() {
	// Default action: run compare if possible, otherwise show status
	if (getComposite() && mixProfile) {
		compare();
	} else {
		get_status();
	}
}
