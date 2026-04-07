/**
 * mf-track-scanner.js
 * Mix Feedback Device — LOM Track Scanner
 *
 * Uses Ableton's Live Object Model to:
 *   1. Enumerate all tracks, groups, and return tracks in the session
 *   2. Read device chains and parameter values on each track
 *   3. Solo each track one at a time for individual analysis
 *   4. Build per-track feature profiles
 *
 * This runs inside Max's [js] object with LiveAPI access.
 */

// ─── Track Info Storage ─────────────────────────────────────────────

var sessionTracks = [];
var trackProfiles = [];
var scanState = {
	scanning: false,
	currentTrack: -1,
	totalTracks: 0,
	captureBuffer: "scan_capture",
	originalSoloStates: [],
	analysisCallback: null
};

// ─── Session Enumeration ────────────────────────────────────────────

/**
 * Enumerate all tracks in the current Ableton session.
 * Returns an array of track info objects.
 */
function enumerateTracks() {
	sessionTracks = [];

	var liveSet = new LiveAPI("live_set");

	// Regular tracks (audio, MIDI, groups)
	var tracks = liveSet.get("tracks");
	var trackCount = tracks.length / 2; // LOM returns [id, id, id, ...]
	for (var i = 0; i < trackCount; i++) {
		var info = getTrackInfo("live_set tracks " + i, "track", i);
		if (info) sessionTracks.push(info);
	}

	// Return tracks
	var returns = liveSet.get("return_tracks");
	var returnCount = returns.length / 2;
	for (var r = 0; r < returnCount; r++) {
		var rInfo = getTrackInfo("live_set return_tracks " + r, "return", r);
		if (rInfo) sessionTracks.push(rInfo);
	}

	// Master track
	var mInfo = getTrackInfo("live_set master_track", "master", 0);
	if (mInfo) sessionTracks.push(mInfo);

	return sessionTracks;
}

/**
 * Get detailed info about a single track.
 */
function getTrackInfo(path, trackType, index) {
	var api = new LiveAPI(path);
	if (!api || !api.id) return null;

	var name = api.get("name").toString();
	var isMuted = parseInt(api.get("mute"));
	var soloState = parseInt(api.get("solo"));
	var volume = parseFloat(api.get("mixer_device volume value"));
	var pan = parseFloat(api.get("mixer_device panning value"));
	var hasAudio = parseInt(api.get("has_audio_output"));
	var isGroup = parseInt(api.get("is_foldable"));

	// Get devices on this track
	var devices = getTrackDevices(path);

	return {
		path: path,
		type: trackType,
		index: index,
		name: name,
		isMuted: isMuted,
		soloState: soloState,
		volume: volume,
		pan: pan,
		hasAudio: hasAudio,
		isGroup: isGroup,
		devices: devices
	};
}

// ─── Device Chain Reading ───────────────────────────────────────────

/**
 * Read all devices on a track and their parameters.
 * This is what enables "your compressor ratio is 4:1" level feedback.
 */
function getTrackDevices(trackPath) {
	var api = new LiveAPI(trackPath);
	var deviceIds = api.get("devices");
	var deviceCount = deviceIds.length / 2;
	var devices = [];

	for (var d = 0; d < deviceCount; d++) {
		var devPath = trackPath + " devices " + d;
		var devApi = new LiveAPI(devPath);

		var devName = devApi.get("name").toString();
		var className = devApi.get("class_name").toString();
		var isEnabled = parseInt(devApi.get("is_active"));

		// Read parameters
		var params = getDeviceParameters(devPath);

		// Identify device type for targeted feedback
		var devType = classifyDevice(className, devName);

		devices.push({
			path: devPath,
			name: devName,
			className: className,
			type: devType,
			isEnabled: isEnabled,
			parameters: params
		});
	}

	return devices;
}

/**
 * Read all parameters of a device.
 */
function getDeviceParameters(devicePath) {
	var api = new LiveAPI(devicePath);
	var paramIds = api.get("parameters");
	var paramCount = paramIds.length / 2;
	var params = {};

	for (var p = 0; p < paramCount; p++) {
		var paramPath = devicePath + " parameters " + p;
		var paramApi = new LiveAPI(paramPath);

		var paramName = paramApi.get("name").toString();
		var paramValue = parseFloat(paramApi.get("value"));
		var paramMin = parseFloat(paramApi.get("min"));
		var paramMax = parseFloat(paramApi.get("max"));

		params[paramName] = {
			value: paramValue,
			min: paramMin,
			max: paramMax
		};
	}

	return params;
}

// ─── Device Classification ──────────────────────────────────────────

/**
 * Classify a device by its function (compressor, EQ, reverb, etc.)
 * so the feedback engine can make parameter-specific suggestions.
 */
function classifyDevice(className, displayName) {
	var name = (className + " " + displayName).toLowerCase();

	if (name.indexOf("compressor") >= 0 || name.indexOf("glue") >= 0 ||
	    name.indexOf("dynamics") >= 0 || name.indexOf("multiband") >= 0) {
		return "compressor";
	}
	if (name.indexOf("eq") >= 0 || name.indexOf("equalizer") >= 0 ||
	    name.indexOf("channel eq") >= 0 || name.indexOf("filter") >= 0) {
		return "eq";
	}
	if (name.indexOf("limiter") >= 0 || name.indexOf("maximizer") >= 0) {
		return "limiter";
	}
	if (name.indexOf("reverb") >= 0 || name.indexOf("convolution") >= 0 ||
	    name.indexOf("hybrid") >= 0) {
		return "reverb";
	}
	if (name.indexOf("delay") >= 0 || name.indexOf("echo") >= 0) {
		return "delay";
	}
	if (name.indexOf("saturator") >= 0 || name.indexOf("overdrive") >= 0 ||
	    name.indexOf("distortion") >= 0 || name.indexOf("pedal") >= 0) {
		return "saturation";
	}
	if (name.indexOf("gate") >= 0) {
		return "gate";
	}
	if (name.indexOf("utility") >= 0 || name.indexOf("gain") >= 0) {
		return "utility";
	}
	if (name.indexOf("stereo") >= 0 || name.indexOf("width") >= 0 ||
	    name.indexOf("imager") >= 0) {
		return "stereo";
	}
	if (name.indexOf("transient") >= 0) {
		return "transient_shaper";
	}

	return "other";
}

// ─── Track Scanning (Solo-Based) ────────────────────────────────────

/**
 * Start a track-by-track scan.
 * The device solos each track one at a time, captures audio for analysis,
 * then unsolos and moves to the next track.
 *
 * @param {number} captureDurationSec - How long to capture each track (default 4)
 */
function startScan(captureDurationSec) {
	if (scanState.scanning) {
		post("Scan already in progress\n");
		return;
	}

	if (!captureDurationSec) captureDurationSec = 4;

	// First, enumerate all tracks
	enumerateTracks();

	if (sessionTracks.length === 0) {
		post("No tracks found in session\n");
		return;
	}

	// Store original solo states so we can restore them
	scanState.originalSoloStates = [];
	for (var i = 0; i < sessionTracks.length; i++) {
		scanState.originalSoloStates.push(sessionTracks[i].soloState);
	}

	// Clear all solos first
	clearAllSolos();

	scanState.scanning = true;
	scanState.currentTrack = 0;
	scanState.totalTracks = sessionTracks.length;
	scanState.captureDuration = captureDurationSec;
	trackProfiles = [];

	post("Starting track scan: " + sessionTracks.length + " tracks\n");
	sendToUI("status", "Scanning " + sessionTracks.length + " tracks...");
	sendToUI("set_progress", 0.05);

	// Signal to the patcher to start the scan sequence
	// The patcher will call scanNextTrack() via a metro/delay chain
	outlet(0, "scan_start", sessionTracks.length, captureDurationSec);
}

/**
 * Solo the next track for analysis.
 * Called by the patcher after each capture window completes.
 */
function scanNextTrack() {
	if (!scanState.scanning) return;

	// Unsolo previous track
	if (scanState.currentTrack > 0) {
		var prevTrack = sessionTracks[scanState.currentTrack - 1];
		var prevApi = new LiveAPI(prevTrack.path);
		prevApi.set("solo", 0);
	}

	if (scanState.currentTrack >= sessionTracks.length) {
		finishScan();
		return;
	}

	var track = sessionTracks[scanState.currentTrack];

	// Skip muted tracks and tracks without audio output
	if (track.isMuted || !track.hasAudio || track.type === "master") {
		scanState.currentTrack++;
		scanNextTrack(); // Recurse to next track
		return;
	}

	// Solo this track
	var api = new LiveAPI(track.path);
	api.set("solo", 1);

	var trackNum = scanState.currentTrack + 1;
	var totalTracks = sessionTracks.length;
	post("Scanning track " + trackNum + "/" + totalTracks + ": " + track.name + "\n");

	sendToUI("set_progress", trackNum / totalTracks);
	sendToUI("status", "Scanning " + trackNum + "/" + totalTracks + ": " + track.name);

	// Signal patcher to start capturing audio for this track
	outlet(0, "scan_capture", scanState.currentTrack, track.name);

	scanState.currentTrack++;
}

/**
 * Receive analysis results for the current track being scanned.
 * Called by the patcher after audio capture + analysis completes.
 *
 * @param {number} trackIndex - Which track was analyzed
 * @param {object} features - Feature set from extractFeatures
 * @param {object} stereoFeatures - From extractStereoFeatures
 */
function receiveTrackAnalysis(trackIndex, features, stereoFeatures) {
	if (trackIndex < sessionTracks.length) {
		trackProfiles[trackIndex] = {
			track: sessionTracks[trackIndex],
			features: features,
			stereo: stereoFeatures
		};
	}
}

/**
 * Finish the scan, restore solo states, and trigger feedback generation.
 */
function finishScan() {
	// Restore original solo states
	for (var i = 0; i < sessionTracks.length; i++) {
		if (i < scanState.originalSoloStates.length) {
			var api = new LiveAPI(sessionTracks[i].path);
			api.set("solo", scanState.originalSoloStates[i]);
		}
	}

	scanState.scanning = false;
	scanState.currentTrack = -1;

	post("Track scan complete. Analyzed " + trackProfiles.length + " tracks.\n");

	sendToUI("set_progress", 1.0);
	sendToUI("set_working", 0);
	sendToUI("status", "Scan complete — " + trackProfiles.length + " tracks analyzed");

	// Signal patcher to generate feedback
	outlet(0, "scan_complete", trackProfiles.length);
}

/**
 * Abort a scan in progress and restore solo states.
 */
function abortScan() {
	if (!scanState.scanning) return;

	// Unsolo current track
	if (scanState.currentTrack > 0 && scanState.currentTrack <= sessionTracks.length) {
		var api = new LiveAPI(sessionTracks[scanState.currentTrack - 1].path);
		api.set("solo", 0);
	}

	// Restore original solo states
	for (var i = 0; i < sessionTracks.length; i++) {
		if (i < scanState.originalSoloStates.length) {
			var apiR = new LiveAPI(sessionTracks[i].path);
			apiR.set("solo", scanState.originalSoloStates[i]);
		}
	}

	scanState.scanning = false;
	post("Scan aborted.\n");
	sendToUI("set_working", 0);
	sendToUI("status", "Scan aborted");
	outlet(0, "scan_aborted");
}

// ─── Helpers ────────────────────────────────────────────────────────

function clearAllSolos() {
	for (var i = 0; i < sessionTracks.length; i++) {
		var api = new LiveAPI(sessionTracks[i].path);
		api.set("solo", 0);
	}
}

function getSessionTracks() {
	return sessionTracks;
}

function getTrackProfiles() {
	return trackProfiles;
}

function isScanInProgress() {
	return scanState.scanning;
}
