/**
 * mf-comparator.js
 * Mix Feedback Device — Mix vs Reference Comparison
 *
 * Compares your mix's feature profile against the composite reference profile.
 * Produces a structured delta object that the feedback generator turns into
 * actionable suggestions.
 */

// ─── Threshold Constants ────────────────────────────────────────────
// Deltas below these thresholds are considered "close enough" — no feedback

var THRESHOLDS = {
	bandRmsDb: 1.5,          // dB difference per band before flagging
	globalRmsDb: 1.0,        // Overall loudness difference
	crestFactor: 1.5,        // dB crest factor difference
	dynamicRange: 2.0,       // dB dynamic range difference
	stereoWidth: 0.08,       // Stereo width ratio difference
	bandCorrelation: 0.15,   // Per-band correlation difference
	monoCompat: 0.1,         // Mono compatibility difference
	transientDensity: 5.0,   // Transients per second
	transientStrength: 0.3   // Transient strength ratio
};

// Severity levels
var SEV_INFO = "info";
var SEV_SUGGEST = "suggest";
var SEV_WARN = "warn";
var SEV_CRITICAL = "critical";

// ─── Full Mix Comparison ────────────────────────────────────────────

/**
 * Compare a mix feature set against the composite reference profile.
 *
 * @param {object} mixProfile - Features extracted from the current mix
 * @param {object} refProfile - Composite reference profile
 * @returns {object} Structured comparison with deltas and severity
 */
function compareMixToReference(mixProfile, refProfile) {
	if (!mixProfile || !refProfile) return null;

	var issues = [];

	// 1. Overall loudness
	var loudnessDelta = mixProfile.globalRmsDb - refProfile.globalRmsDb;
	if (Math.abs(loudnessDelta) > THRESHOLDS.globalRmsDb) {
		issues.push({
			category: "loudness",
			severity: getSeverity(Math.abs(loudnessDelta), 1.0, 3.0, 5.0),
			delta: loudnessDelta,
			mixValue: mixProfile.globalRmsDb,
			refValue: refProfile.globalRmsDb,
			direction: loudnessDelta > 0 ? "louder" : "quieter"
		});
	}

	// 2. Crest factor (compression indicator)
	var crestDelta = mixProfile.crestFactor - refProfile.crestFactor;
	if (Math.abs(crestDelta) > THRESHOLDS.crestFactor) {
		issues.push({
			category: "compression",
			severity: getSeverity(Math.abs(crestDelta), 1.5, 3.0, 5.0),
			delta: crestDelta,
			mixValue: mixProfile.crestFactor,
			refValue: refProfile.crestFactor,
			direction: crestDelta > 0 ? "less_compressed" : "over_compressed"
		});
	}

	// 3. Dynamic range
	var dynDelta = mixProfile.dynamicRange - refProfile.dynamicRange;
	if (Math.abs(dynDelta) > THRESHOLDS.dynamicRange) {
		issues.push({
			category: "dynamics",
			severity: getSeverity(Math.abs(dynDelta), 2.0, 4.0, 7.0),
			delta: dynDelta,
			mixValue: mixProfile.dynamicRange,
			refValue: refProfile.dynamicRange,
			direction: dynDelta > 0 ? "more_dynamic" : "less_dynamic"
		});
	}

	// 4. Per-band spectral balance
	for (var b = 0; b < 6; b++) {
		var mixBand = mixProfile.bands[b];
		var refBand = refProfile.bands[b];
		var bandDelta = mixBand.rmsDb - refBand.rmsDb;

		if (Math.abs(bandDelta) > THRESHOLDS.bandRmsDb) {
			issues.push({
				category: "spectral",
				band: b,
				bandName: mixBand.name,
				bandCenter: mixBand.center,
				bandLo: mixBand.lo,
				bandHi: mixBand.hi,
				severity: getSeverity(Math.abs(bandDelta), 1.5, 3.0, 5.0),
				delta: bandDelta,
				mixValue: mixBand.rmsDb,
				refValue: refBand.rmsDb,
				direction: bandDelta > 0 ? "hot" : "thin"
			});
		}

		// Per-band crest factor (band-specific compression)
		var bandCrestDelta = mixBand.crestFactor - refBand.crestFactor;
		if (Math.abs(bandCrestDelta) > THRESHOLDS.crestFactor) {
			issues.push({
				category: "band_compression",
				band: b,
				bandName: mixBand.name,
				severity: getSeverity(Math.abs(bandCrestDelta), 1.5, 3.0, 5.0),
				delta: bandCrestDelta,
				mixValue: mixBand.crestFactor,
				refValue: refBand.crestFactor,
				direction: bandCrestDelta > 0 ? "less_compressed" : "over_compressed"
			});
		}
	}

	// 5. Stereo width
	var widthDelta = mixProfile.stereoWidth - refProfile.stereoWidth;
	if (Math.abs(widthDelta) > THRESHOLDS.stereoWidth) {
		issues.push({
			category: "stereo_width",
			severity: getSeverity(Math.abs(widthDelta), 0.08, 0.15, 0.25),
			delta: widthDelta,
			mixValue: mixProfile.stereoWidth,
			refValue: refProfile.stereoWidth,
			direction: widthDelta > 0 ? "wider" : "narrower"
		});
	}

	// 6. Per-band stereo correlation
	if (mixProfile.bandCorrelation && refProfile.bandCorrelation) {
		for (var b2 = 0; b2 < 6; b2++) {
			var corrDelta = mixProfile.bandCorrelation[b2] - refProfile.bandCorrelation[b2];
			if (Math.abs(corrDelta) > THRESHOLDS.bandCorrelation) {
				issues.push({
					category: "band_stereo",
					band: b2,
					bandName: mixProfile.bands[b2].name,
					severity: getSeverity(Math.abs(corrDelta), 0.15, 0.25, 0.4),
					delta: corrDelta,
					mixValue: mixProfile.bandCorrelation[b2],
					refValue: refProfile.bandCorrelation[b2],
					direction: corrDelta > 0 ? "narrower" : "wider"
				});
			}
		}
	}

	// 7. Mono compatibility
	if (mixProfile.monoCompatibility !== undefined) {
		var monoDelta = mixProfile.monoCompatibility - refProfile.monoCompatibility;
		if (Math.abs(monoDelta) > THRESHOLDS.monoCompat) {
			issues.push({
				category: "mono_compat",
				severity: getSeverity(Math.abs(monoDelta), 0.1, 0.2, 0.35),
				delta: monoDelta,
				mixValue: mixProfile.monoCompatibility,
				refValue: refProfile.monoCompatibility,
				direction: monoDelta > 0 ? "more_mono" : "less_mono"
			});
		}
	}

	// 8. Transient preservation
	if (mixProfile.transientDensity !== undefined && refProfile.transientDensity) {
		var transDelta = mixProfile.transientDensity - refProfile.transientDensity;
		if (Math.abs(transDelta) > THRESHOLDS.transientDensity) {
			issues.push({
				category: "transients",
				severity: getSeverity(Math.abs(transDelta), 5.0, 10.0, 20.0),
				delta: transDelta,
				mixValue: mixProfile.transientDensity,
				refValue: refProfile.transientDensity,
				direction: transDelta > 0 ? "more_transients" : "fewer_transients"
			});
		}
	}

	// Sort by severity (critical first)
	var sevOrder = { critical: 0, warn: 1, suggest: 2, info: 3 };
	issues.sort(function(a, b) {
		return (sevOrder[a.severity] || 3) - (sevOrder[b.severity] || 3);
	});

	return {
		issues: issues,
		totalIssues: issues.length,
		criticalCount: countSeverity(issues, SEV_CRITICAL),
		warnCount: countSeverity(issues, SEV_WARN),
		suggestCount: countSeverity(issues, SEV_SUGGEST),
		overallScore: calculateScore(issues)
	};
}

// ─── Per-Track Comparison ───────────────────────────────────────────

/**
 * Compare a single track's features against the full mix and reference.
 * Identifies what this specific track contributes to overall issues.
 *
 * @param {object} trackProfile - Track's feature set
 * @param {object} fullMixProfile - Full mix features
 * @param {object} refProfile - Composite reference
 * @param {object} trackInfo - Track metadata (name, devices, etc.)
 * @returns {object} Per-track issue list
 */
function compareTrackContribution(trackProfile, fullMixProfile, refProfile, trackInfo) {
	if (!trackProfile || !fullMixProfile || !refProfile) return null;

	var issues = [];

	// Check each band — is this track contributing to spectral problems?
	for (var b = 0; b < 6; b++) {
		var mixBandDelta = fullMixProfile.bands[b].rmsDb - refProfile.bands[b].rmsDb;
		var trackBandEnergy = trackProfile.bands[b].rmsDb;

		// If the full mix has a problem in this band, and this track has
		// significant energy in this band, flag it
		if (Math.abs(mixBandDelta) > THRESHOLDS.bandRmsDb && trackBandEnergy > -60) {
			// Calculate how much of the problem this track is responsible for
			var trackContribution = trackBandEnergy - fullMixProfile.bands[b].rmsDb;
			// Higher contribution = closer to 0 dB difference with the full mix

			if (trackContribution > -12) { // Track is a significant contributor
				issues.push({
					category: "track_spectral",
					band: b,
					bandName: trackProfile.bands[b].name,
					bandCenter: trackProfile.bands[b].center,
					bandLo: trackProfile.bands[b].lo,
					bandHi: trackProfile.bands[b].hi,
					trackName: trackInfo.name,
					trackDevices: trackInfo.devices,
					mixDirection: mixBandDelta > 0 ? "hot" : "thin",
					delta: mixBandDelta,
					trackEnergy: trackBandEnergy,
					contribution: trackContribution,
					severity: getSeverity(Math.abs(mixBandDelta), 1.5, 3.0, 5.0)
				});
			}
		}
	}

	// Check track dynamics vs reference
	var trackCrest = trackProfile.crestFactor;
	var refCrest = refProfile.crestFactor;
	var crestDelta = trackCrest - refCrest;

	if (Math.abs(crestDelta) > THRESHOLDS.crestFactor * 1.5) {
		issues.push({
			category: "track_compression",
			trackName: trackInfo.name,
			trackDevices: trackInfo.devices,
			delta: crestDelta,
			trackValue: trackCrest,
			refValue: refCrest,
			direction: crestDelta > 0 ? "less_compressed" : "over_compressed",
			severity: getSeverity(Math.abs(crestDelta), 2.0, 4.0, 6.0)
		});
	}

	return {
		trackName: trackInfo.name,
		trackType: trackInfo.type,
		issues: issues
	};
}

// ─── Helpers ────────────────────────────────────────────────────────

function getSeverity(absDelta, suggestThresh, warnThresh, critThresh) {
	if (absDelta >= critThresh) return SEV_CRITICAL;
	if (absDelta >= warnThresh) return SEV_WARN;
	if (absDelta >= suggestThresh) return SEV_SUGGEST;
	return SEV_INFO;
}

function countSeverity(issues, severity) {
	var count = 0;
	for (var i = 0; i < issues.length; i++) {
		if (issues[i].severity === severity) count++;
	}
	return count;
}

function calculateScore(issues) {
	// 100 = perfect match, deduct points per issue by severity
	var score = 100;
	for (var i = 0; i < issues.length; i++) {
		switch (issues[i].severity) {
			case SEV_CRITICAL: score -= 15; break;
			case SEV_WARN:     score -= 8;  break;
			case SEV_SUGGEST:  score -= 3;  break;
			case SEV_INFO:     score -= 1;  break;
		}
	}
	return Math.max(0, Math.min(100, score));
}
