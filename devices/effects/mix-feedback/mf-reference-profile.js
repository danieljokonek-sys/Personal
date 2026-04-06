/**
 * mf-reference-profile.js
 * Mix Feedback Device — Reference Profile Builder
 *
 * Reads audio from buffer~ objects, extracts features using mf-analysis-core,
 * and builds a composite reference profile from 1–5 reference tracks.
 *
 * Uses Max's Buffer object API to read sample data.
 */

// ─── Reference Profile Storage ──────────────────────────────────────

var referenceProfiles = [];
var compositeProfile = null;
var MAX_REFERENCES = 5;

// Buffer names (set by the patcher)
var bufferNames = ["ref1", "ref2", "ref3", "ref4", "ref5"];

// ─── Read Buffer into Sample Arrays ─────────────────────────────────

/**
 * Read a Max buffer~ into left/right sample arrays.
 * Uses Max's Buffer API: new Buffer("name"), buf.peek(chan, frame)
 *
 * @param {string} bufName - Name of the buffer~ object
 * @returns {object|null} { left: [], right: [], sampleRate, frames }
 */
function readBuffer(bufName) {
	var buf = new Buffer(bufName);
	if (!buf || !buf.framecount || buf.framecount() <= 0) {
		return null;
	}

	var frames = buf.framecount();
	var channels = buf.channelcount();
	var sr = buf.samplerate ? buf.samplerate() : 44100;

	var left = new Array(frames);
	var right = new Array(frames);

	for (var i = 0; i < frames; i++) {
		left[i] = buf.peek(1, i);
		right[i] = (channels >= 2) ? buf.peek(2, i) : left[i];
	}

	return {
		left: left,
		right: right,
		sampleRate: sr,
		frames: frames
	};
}

// ─── Analyze a Single Reference Track ───────────────────────────────

/**
 * Analyze one reference track loaded in a buffer~.
 *
 * @param {number} refIndex - Reference slot index (0–4)
 * @returns {object|null} Full feature profile or null if buffer empty
 */
function analyzeReference(refIndex) {
	if (refIndex < 0 || refIndex >= MAX_REFERENCES) return null;

	var bufName = bufferNames[refIndex];
	var audio = readBuffer(bufName);
	if (!audio) return null;

	// Mix to mono for spectral analysis
	var mono = new Array(audio.frames);
	for (var i = 0; i < audio.frames; i++) {
		mono[i] = (audio.left[i] + audio.right[i]) * 0.5;
	}

	// Extract mono features (spectral balance, dynamics)
	var monoFeatures = extractFeatures(mono, audio.sampleRate, 0.1);

	// Extract stereo features (width, correlation)
	var stereoFeatures = extractStereoFeatures(
		audio.left, audio.right, audio.sampleRate
	);

	// Extract transient density
	var transients = extractTransients(mono, audio.sampleRate);

	var profile = {
		index: refIndex,
		bufferName: bufName,
		durationSec: audio.frames / audio.sampleRate,
		sampleRate: audio.sampleRate,
		mono: monoFeatures,
		stereo: stereoFeatures,
		transients: transients
	};

	referenceProfiles[refIndex] = profile;
	return profile;
}

// ─── Build Composite Profile ────────────────────────────────────────

/**
 * Average all loaded reference profiles into a single composite.
 * This composite IS the target — your mix is compared against this.
 *
 * @returns {object} Composite reference profile
 */
function buildComposite() {
	var loaded = [];
	for (var i = 0; i < referenceProfiles.length; i++) {
		if (referenceProfiles[i]) loaded.push(referenceProfiles[i]);
	}

	if (loaded.length === 0) {
		compositeProfile = null;
		return null;
	}

	var n = loaded.length;

	// Average global features
	var avgGlobalRmsDb = 0;
	var avgGlobalPeakDb = 0;
	var avgCrestFactor = 0;
	var avgDynamicRange = 0;
	var avgStereoWidth = 0;
	var avgMonoCompat = 0;
	var avgTransientDensity = 0;
	var avgTransientStrength = 0;

	// Average per-band features
	var avgBands = [];
	var avgBandCorrelation = [];
	var avgBandWidth = [];
	for (var b = 0; b < 6; b++) {
		avgBands.push({
			rmsDb: 0, peakDb: 0, crestFactor: 0, dynamicRange: 0
		});
		avgBandCorrelation.push(0);
		avgBandWidth.push(0);
	}

	for (var j = 0; j < n; j++) {
		var p = loaded[j];
		avgGlobalRmsDb += p.mono.globalRmsDb;
		avgGlobalPeakDb += p.mono.globalPeakDb;
		avgCrestFactor += p.mono.crestFactor;
		avgDynamicRange += p.mono.dynamicRange;
		avgStereoWidth += p.stereo.stereoWidth;
		avgMonoCompat += p.stereo.monoCompatibility;
		avgTransientDensity += p.transients.density;
		avgTransientStrength += p.transients.avgStrength;

		for (var b2 = 0; b2 < 6; b2++) {
			avgBands[b2].rmsDb += p.mono.bands[b2].rmsDb;
			avgBands[b2].peakDb += p.mono.bands[b2].peakDb;
			avgBands[b2].crestFactor += p.mono.bands[b2].crestFactor;
			avgBands[b2].dynamicRange += p.mono.bands[b2].dynamicRange;
			avgBandCorrelation[b2] += p.stereo.bandCorrelation[b2];
			avgBandWidth[b2] += p.stereo.bandWidth[b2];
		}
	}

	// Divide by count
	avgGlobalRmsDb /= n;
	avgGlobalPeakDb /= n;
	avgCrestFactor /= n;
	avgDynamicRange /= n;
	avgStereoWidth /= n;
	avgMonoCompat /= n;
	avgTransientDensity /= n;
	avgTransientStrength /= n;

	for (var b3 = 0; b3 < 6; b3++) {
		avgBands[b3].rmsDb /= n;
		avgBands[b3].peakDb /= n;
		avgBands[b3].crestFactor /= n;
		avgBands[b3].dynamicRange /= n;
		avgBands[b3].name = loaded[0].mono.bands[b3].name;
		avgBands[b3].center = loaded[0].mono.bands[b3].center;
		avgBands[b3].lo = loaded[0].mono.bands[b3].lo;
		avgBands[b3].hi = loaded[0].mono.bands[b3].hi;
		avgBandCorrelation[b3] /= n;
		avgBandWidth[b3] /= n;
	}

	compositeProfile = {
		numReferences: n,
		globalRmsDb: avgGlobalRmsDb,
		globalPeakDb: avgGlobalPeakDb,
		crestFactor: avgCrestFactor,
		dynamicRange: avgDynamicRange,
		bands: avgBands,
		stereoWidth: avgStereoWidth,
		monoCompatibility: avgMonoCompat,
		bandCorrelation: avgBandCorrelation,
		bandWidth: avgBandWidth,
		transientDensity: avgTransientDensity,
		transientStrength: avgTransientStrength
	};

	return compositeProfile;
}

// ─── Transient Detection ────────────────────────────────────────────

/**
 * Simple transient detection by comparing short-term to long-term envelope.
 */
function extractTransients(samples, sampleRate) {
	var shortWindow = Math.floor(sampleRate * 0.005); // 5ms
	var longWindow = Math.floor(sampleRate * 0.05);   // 50ms
	var hopSize = Math.floor(sampleRate * 0.005);
	var numHops = Math.floor((samples.length - longWindow) / hopSize);

	if (numHops < 1) {
		return { density: 0, avgStrength: 0 };
	}

	var transients = [];
	var threshold = 1.5; // Short-term must be 1.5x long-term to count

	for (var h = 0; h < numHops; h++) {
		var pos = h * hopSize;

		// Short-term RMS
		var shortSum = 0;
		for (var s = pos; s < pos + shortWindow && s < samples.length; s++) {
			shortSum += samples[s] * samples[s];
		}
		var shortRms = Math.sqrt(shortSum / shortWindow);

		// Long-term RMS
		var longSum = 0;
		for (var l = pos; l < pos + longWindow && l < samples.length; l++) {
			longSum += samples[l] * samples[l];
		}
		var longRms = Math.sqrt(longSum / longWindow);

		if (longRms > 0.0001 && shortRms / longRms > threshold) {
			transients.push(shortRms / longRms);
		}
	}

	var density = transients.length / (samples.length / sampleRate); // per second
	var avgStrength = 0;
	if (transients.length > 0) {
		for (var t = 0; t < transients.length; t++) {
			avgStrength += transients[t];
		}
		avgStrength /= transients.length;
	}

	return {
		density: density,
		avgStrength: avgStrength
	};
}

// ─── Clear / Reset ──────────────────────────────────────────────────

function clearReferences() {
	referenceProfiles = [];
	compositeProfile = null;
}

function clearReference(index) {
	if (index >= 0 && index < MAX_REFERENCES) {
		referenceProfiles[index] = null;
	}
}

function getComposite() {
	return compositeProfile;
}

function getLoadedCount() {
	var count = 0;
	for (var i = 0; i < referenceProfiles.length; i++) {
		if (referenceProfiles[i]) count++;
	}
	return count;
}
