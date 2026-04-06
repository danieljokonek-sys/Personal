/**
 * mf-suggestions.js
 * Mix Feedback Device — Suggestion Generator
 *
 * Translates comparison deltas into specific, actionable mixing advice.
 * This is where "your low-mids are 3dB hot" becomes "Track 'Bass': cut 2-3dB
 * at 350Hz with Q=2 on your Channel EQ, or reduce the Compressor threshold
 * by 2dB to control the sustain."
 */

// ─── Main Suggestion Generator ──────────────────────────────────────

/**
 * Generate human-readable feedback from comparison results.
 *
 * @param {object} comparison - Output from compareMixToReference()
 * @param {object[]} trackComparisons - Per-track comparisons (optional)
 * @returns {string[]} Array of feedback strings, ordered by priority
 */
function generateFeedback(comparison, trackComparisons) {
	var feedback = [];

	if (!comparison) {
		feedback.push("No comparison data available. Load references and analyze your mix first.");
		return feedback;
	}

	// Header with overall score
	feedback.push("=== MIX FEEDBACK REPORT ===");
	feedback.push("Match Score: " + comparison.overallScore + "/100");
	feedback.push("Issues: " + comparison.criticalCount + " critical, " +
	              comparison.warnCount + " warnings, " +
	              comparison.suggestCount + " suggestions");
	feedback.push("");

	if (comparison.totalIssues === 0) {
		feedback.push("Your mix closely matches your references. Nice work!");
		return feedback;
	}

	// Process each issue
	for (var i = 0; i < comparison.issues.length; i++) {
		var issue = comparison.issues[i];
		var suggestion = generateIssueSuggestion(issue, trackComparisons);
		if (suggestion) {
			feedback.push(severityPrefix(issue.severity) + suggestion);
		}
	}

	// Add per-track specific suggestions if available
	if (trackComparisons && trackComparisons.length > 0) {
		var trackSuggestions = generateTrackSuggestions(trackComparisons);
		if (trackSuggestions.length > 0) {
			feedback.push("");
			feedback.push("=== PER-TRACK SUGGESTIONS ===");
			for (var t = 0; t < trackSuggestions.length; t++) {
				feedback.push(trackSuggestions[t]);
			}
		}
	}

	return feedback;
}

// ─── Issue-Specific Suggestion Logic ────────────────────────────────

function generateIssueSuggestion(issue, trackComparisons) {
	switch (issue.category) {
		case "loudness":
			return suggestLoudness(issue);
		case "compression":
			return suggestCompression(issue);
		case "dynamics":
			return suggestDynamics(issue);
		case "spectral":
			return suggestSpectral(issue);
		case "band_compression":
			return suggestBandCompression(issue);
		case "stereo_width":
			return suggestStereoWidth(issue);
		case "band_stereo":
			return suggestBandStereo(issue);
		case "mono_compat":
			return suggestMonoCompat(issue);
		case "transients":
			return suggestTransients(issue);
		default:
			return null;
	}
}

// ─── Loudness ───────────────────────────────────────────────────────

function suggestLoudness(issue) {
	var delta = Math.abs(issue.delta).toFixed(1);
	if (issue.direction === "louder") {
		return "Mix is " + delta + "dB louder than references (" +
		       issue.mixValue.toFixed(1) + " vs " + issue.refValue.toFixed(1) +
		       " dB RMS). Pull back your master fader or limiter input by ~" +
		       delta + "dB. If using a limiter, raise the ceiling or reduce " +
		       "the input gain.";
	} else {
		return "Mix is " + delta + "dB quieter than references (" +
		       issue.mixValue.toFixed(1) + " vs " + issue.refValue.toFixed(1) +
		       " dB RMS). You have headroom to push the limiter input by ~" +
		       delta + "dB. Check that your master bus gain staging " +
		       "leaves enough level hitting the limiter.";
	}
}

// ─── Compression ────────────────────────────────────────────────────

function suggestCompression(issue) {
	var delta = Math.abs(issue.delta).toFixed(1);
	if (issue.direction === "over_compressed") {
		var suggestions = "Mix crest factor is " + delta + "dB below references (" +
		       issue.mixValue.toFixed(1) + "dB vs " + issue.refValue.toFixed(1) +
		       "dB) — the mix is over-compressed.";

		if (issue.delta < -3) {
			suggestions += " Try these in order: (1) Raise master bus compressor threshold " +
			               "by 2-4dB. (2) If ratio is above 4:1, reduce to 2:1-3:1. " +
			               "(3) Slow down the attack to 20-30ms to let transients through. " +
			               "(4) Check if your limiter is doing too much — aim for no more " +
			               "than 2-3dB of gain reduction on the limiter.";
		} else {
			suggestions += " Raise your master bus compressor threshold by ~" +
			               delta + "dB, or reduce the ratio by one step.";
		}
		return suggestions;
	} else {
		return "Mix crest factor is " + delta + "dB above references (" +
		       issue.mixValue.toFixed(1) + "dB vs " + issue.refValue.toFixed(1) +
		       "dB) — the mix could use more glue. Try a gentle bus compressor " +
		       "(2:1 ratio, 30ms attack, 100ms release, -2 to -4dB GR) to add " +
		       "cohesion. Or add light parallel compression on the drum bus.";
	}
}

// ─── Dynamic Range ──────────────────────────────────────────────────

function suggestDynamics(issue) {
	var delta = Math.abs(issue.delta).toFixed(1);
	if (issue.direction === "less_dynamic") {
		return "Dynamic range is " + delta + "dB narrower than references (" +
		       issue.mixValue.toFixed(1) + "dB vs " + issue.refValue.toFixed(1) +
		       "dB). The mix sounds flat/lifeless compared to references. " +
		       "Check for over-limiting on the master, or too many compressors " +
		       "stacked in series across the mix bus chain. Consider using " +
		       "automation for level changes instead of relying on compression.";
	} else {
		return "Dynamic range is " + delta + "dB wider than references (" +
		       issue.mixValue.toFixed(1) + "dB vs " + issue.refValue.toFixed(1) +
		       "dB). Quiet sections may disappear on consumer playback systems. " +
		       "Consider gentle compression on the mix bus (start with 1.5:1, " +
		       "slow attack, auto release) or use volume automation to ride " +
		       "the quiet sections up by 2-3dB.";
	}
}

// ─── Spectral Balance ───────────────────────────────────────────────

function suggestSpectral(issue) {
	var delta = Math.abs(issue.delta).toFixed(1);
	var freqRange = issue.bandLo + "-" + issue.bandHi + "Hz";
	var bandName = issue.bandName;

	if (issue.direction === "hot") {
		return bandName + " (" + freqRange + ") is +" + delta +
		       "dB above references. " + getSpectralHotAdvice(issue.band, delta);
	} else {
		return bandName + " (" + freqRange + ") is -" + delta +
		       "dB below references. " + getSpectralThinAdvice(issue.band, delta);
	}
}

function getSpectralHotAdvice(bandIndex, delta) {
	var advice = {
		0: "Sub frequencies are too loud. Check your kick drum sub and bass synth " +
		   "below 60Hz. Apply a high-pass filter at 30-40Hz on everything except " +
		   "kick and bass. If the sub is intentional, check it in mono — phase " +
		   "issues cause sub buildup.",

		1: "Low end is boomy. Common culprits: bass guitar body resonance (80-120Hz), " +
		   "kick drum fundamental (60-100Hz), or room tone from vocal mics. Try a " +
		   "broad " + delta + "dB cut centered around 100-150Hz on your mix bus, " +
		   "or hunt for the offending tracks and cut there instead.",

		2: "Low-mids are muddy. This is the most common mix problem. Check for " +
		   "buildup from multiple instruments stacking around 250-500Hz — guitars, " +
		   "keys, vocals, and snare all live here. Cut " + delta + "dB on 2-3 " +
		   "of the busiest tracks at 300-400Hz with Q=1.5. Don't cut everything " +
		   "— pick the least important elements in this range.",

		3: "Mids are too forward. The mix may sound boxy or nasal. Check vocals " +
		   "at 1-2kHz and guitars at 2-3kHz. A broad " + Math.ceil(parseFloat(delta) * 0.7) +
		   "dB cut around 1.5-2.5kHz on the mix bus can help, or address " +
		   "individual tracks. Watch out for resonant peaks in vocal chains.",

		4: "High-mids are harsh/aggressive. Likely causes: vocal sibilance (5-7kHz), " +
		   "cymbal harshness (4-6kHz), or guitar presence peak. Try a de-esser on " +
		   "vocals targeting 5-7kHz, or a dynamic EQ on the mix bus that only cuts " +
		   "when this range gets loud. A static cut of " + delta + "dB at 5kHz " +
		   "with Q=1 is a starting point.",

		5: "Highs are too bright/harsh. The mix may cause ear fatigue. Reduce " +
		   "cymbal/hi-hat levels, or apply a gentle shelf cut of " +
		   Math.ceil(parseFloat(delta) * 0.6) + "dB above 8kHz on the mix bus. " +
		   "Check for excess high-freq content from synths, reverb tails, or " +
		   "overuse of exciter/aural exciter plugins."
	};
	return advice[bandIndex] || "";
}

function getSpectralThinAdvice(bandIndex, delta) {
	var advice = {
		0: "Sub frequencies are weak. If the genre calls for sub presence, " +
		   "check that your kick and bass have content below 60Hz. A sub-harmonic " +
		   "generator or layering a clean sine at the kick fundamental can help. " +
		   "Also verify your monitoring can actually reproduce these frequencies.",

		1: "Low end is thin. The mix may sound lightweight on larger speakers. " +
		   "Check bass and kick levels — boost the bass by " + delta + "dB or add " +
		   "a low shelf at 100Hz on the mix bus. Make sure high-pass filters on " +
		   "individual tracks aren't cutting too aggressively above 60-80Hz.",

		2: "Low-mids are thin. The mix may lack warmth and body. Check that " +
		   "you haven't over-cut this range while fighting mud. Boost guitar and " +
		   "vocal body around 250-400Hz by " + Math.ceil(parseFloat(delta) * 0.7) +
		   "dB, or ease up on existing low-mid cuts across your tracks.",

		3: "Mids are recessed. Vocals and lead instruments may lack presence. " +
		   "Boost vocal presence around 2-3kHz by " + delta + "dB, or check " +
		   "if reverb/delay is washing out the midrange. A mid-range boost on " +
		   "the vocal bus often fixes this.",

		4: "High-mids are lacking. The mix may sound dull or distant. Add " +
		   "presence to vocals (3-5kHz) and clarity to drums (4-6kHz). An air " +
		   "boost on the drum bus or vocal bus with a wide bell at 5kHz can " +
		   "bring the mix forward.",

		5: "Highs are dull/dark. The mix lacks air and sparkle compared to " +
		   "references. Try a high shelf boost of " + Math.ceil(parseFloat(delta) * 0.6) +
		   "dB at 10kHz on the mix bus. Check that your master bus processing " +
		   "isn't rolling off highs — compressors and saturators can darken the top end."
	};
	return advice[bandIndex] || "";
}

// ─── Band Compression ───────────────────────────────────────────────

function suggestBandCompression(issue) {
	var delta = Math.abs(issue.delta).toFixed(1);
	if (issue.direction === "over_compressed") {
		return issue.bandName + " band dynamics are " + delta +
		       "dB flatter than references. The " + issue.bandName.toLowerCase() +
		       " range sounds squashed. Check for compressors on tracks/buses " +
		       "dominant in this range — reduce their ratio or raise the threshold.";
	} else {
		return issue.bandName + " band dynamics are " + delta +
		       "dB wilder than references. Consider taming the " +
		       issue.bandName.toLowerCase() + " range with a multiband compressor " +
		       "targeting this band, or individual track compression on the " +
		       "dominant elements.";
	}
}

// ─── Stereo Width ───────────────────────────────────────────────────

function suggestStereoWidth(issue) {
	var pct = Math.round(issue.mixValue * 100);
	var refPct = Math.round(issue.refValue * 100);

	if (issue.direction === "wider") {
		return "Stereo width (" + pct + "%) is wider than references (" +
		       refPct + "%). The mix may lose punch in mono or sound phasey. " +
		       "Check stereo widener plugins, wide-panned reverbs, and " +
		       "chorus/ensemble effects. Keep bass, kick, snare, and lead " +
		       "vocal narrow (center). Test in mono to find phase issues.";
	} else {
		return "Stereo width (" + pct + "%) is narrower than references (" +
		       refPct + "%). The mix may sound flat/small. Pan supporting " +
		       "elements (guitars, keys, backing vocals, hi-hats) wider. " +
		       "Use stereo delay or reverb with wider pre-delay to create " +
		       "space. Keep the low end centered but widen the mids and highs.";
	}
}

// ─── Per-Band Stereo ────────────────────────────────────────────────

function suggestBandStereo(issue) {
	if (issue.direction === "narrower") {
		return issue.bandName + " range is narrower than references. " +
		       "Consider panning elements in this range wider or adding " +
		       "stereo processing (chorus, stereo delay) to elements " +
		       "dominant in the " + issue.bandName.toLowerCase() + " band.";
	} else {
		return issue.bandName + " range is wider than references. " +
		       "This may cause phase issues on mono playback. Check " +
		       "stereo effects on elements in this range. " +
		       (issue.band <= 1 ?
		       "Low frequency content should generally be mono — check " +
		       "your bass and kick for stereo processing that shouldn't be there." :
		       "Test in mono to verify nothing disappears.");
	}
}

// ─── Mono Compatibility ────────────────────────────────────────────

function suggestMonoCompat(issue) {
	if (issue.direction === "less_mono") {
		var pct = Math.round(issue.mixValue * 100);
		return "Mono compatibility is " + pct + "% (references: " +
		       Math.round(issue.refValue * 100) + "%). Elements may " +
		       "cancel in mono playback (phone speakers, club systems, Bluetooth). " +
		       "Check stereo bass processing, wide reverbs, and stereo " +
		       "widener plugins. Use a Utility set to mono on the master " +
		       "to preview and identify problem tracks.";
	} else {
		return "Mix is more mono-focused than references (" +
		       Math.round(issue.mixValue * 100) + "% vs " +
		       Math.round(issue.refValue * 100) + "%). Safe for mono " +
		       "playback, but the mix may sound flat on stereo systems. " +
		       "Try widening non-critical elements (pads, effects, doubles).";
	}
}

// ─── Transients ─────────────────────────────────────────────────────

function suggestTransients(issue) {
	if (issue.direction === "fewer_transients") {
		return "Transient detail is lower than references. The mix sounds " +
		       "rounded/dull in attack. Common causes: (1) Limiter attack too " +
		       "fast — try 1-5ms. (2) Bus compressor attack too fast — try " +
		       "20-30ms to let transients pass. (3) Too many compressors in " +
		       "series eating transients. Consider a transient shaper plugin " +
		       "on the drum bus (+3-5dB attack) to restore punch.";
	} else {
		return "Mix has more transient energy than references. This can sound " +
		       "spiky/harsh. A faster limiter attack (0.1-0.5ms) will catch " +
		       "peaks. Or add gentle compression on the drum bus with a faster " +
		       "attack (5-10ms) to tame the transients without killing them.";
	}
}

// ─── Per-Track Suggestions ──────────────────────────────────────────

function generateTrackSuggestions(trackComparisons) {
	var suggestions = [];

	for (var t = 0; t < trackComparisons.length; t++) {
		var tc = trackComparisons[t];
		if (!tc || !tc.issues || tc.issues.length === 0) continue;

		suggestions.push("");
		suggestions.push("--- " + tc.trackName + " ---");

		for (var i = 0; i < tc.issues.length; i++) {
			var issue = tc.issues[i];
			var sug = generateTrackIssueSuggestion(issue);
			if (sug) {
				suggestions.push(severityPrefix(issue.severity) + sug);
			}
		}
	}

	return suggestions;
}

function generateTrackIssueSuggestion(issue) {
	if (issue.category === "track_spectral") {
		var delta = Math.abs(issue.delta).toFixed(1);
		var freqRange = issue.bandLo + "-" + issue.bandHi + "Hz";
		var devInfo = findRelevantDevice(issue.trackDevices, "eq");

		var sug = "'" + issue.trackName + "' is contributing to " +
		          issue.bandName + " (" + freqRange + ") buildup (+";
		sug += delta + "dB on master). ";

		if (issue.mixDirection === "hot") {
			sug += "Cut ~" + Math.ceil(parseFloat(delta) * 0.7) + "dB at " +
			       issue.bandCenter + "Hz with Q=1.5";
			if (devInfo) {
				sug += " on your " + devInfo.name;
			} else {
				sug += " — add an EQ to this track";
			}
			sug += ".";
		} else {
			sug += "This track has energy where the mix is thin — " +
			       "consider boosting it ~" + Math.ceil(parseFloat(delta) * 0.5) +
			       "dB at " + issue.bandCenter + "Hz.";
		}
		return sug;
	}

	if (issue.category === "track_compression") {
		var compDev = findRelevantDevice(issue.trackDevices, "compressor");

		if (issue.direction === "over_compressed") {
			var sug2 = "'" + issue.trackName + "' is over-compressed (crest: " +
			          issue.trackValue.toFixed(1) + "dB vs ref: " +
			          issue.refValue.toFixed(1) + "dB). ";
			if (compDev) {
				sug2 += "On your " + compDev.name + ": ";
				if (compDev.parameters["Ratio"]) {
					var currentRatio = compDev.parameters["Ratio"].value;
					var suggestedRatio = Math.max(1.5, currentRatio * 0.6);
					sug2 += "reduce ratio from " + currentRatio.toFixed(1) +
					        ":1 to ~" + suggestedRatio.toFixed(1) + ":1. ";
				}
				if (compDev.parameters["Threshold"]) {
					sug2 += "Raise threshold by 3-5dB. ";
				}
				if (compDev.parameters["Attack"]) {
					var currentAttack = compDev.parameters["Attack"].value;
					if (currentAttack < 15) {
						sug2 += "Slow attack to 20-30ms to preserve transients. ";
					}
				}
			} else {
				sug2 += "Reduce compression on this track — raise the threshold " +
				       "or lower the ratio.";
			}
			return sug2;
		} else {
			var sug3 = "'" + issue.trackName + "' has wide dynamics (crest: " +
			          issue.trackValue.toFixed(1) + "dB vs ref: " +
			          issue.refValue.toFixed(1) + "dB). ";
			if (compDev) {
				sug3 += "On your " + compDev.name + ": increase ratio or lower threshold.";
			} else {
				sug3 += "Consider adding compression (start with 3:1, medium attack).";
			}
			return sug3;
		}
	}

	return null;
}

// ─── Helpers ────────────────────────────────────────────────────────

function findRelevantDevice(devices, deviceType) {
	if (!devices) return null;
	for (var d = 0; d < devices.length; d++) {
		if (devices[d].type === deviceType && devices[d].isEnabled) {
			return devices[d];
		}
	}
	return null;
}

function severityPrefix(severity) {
	switch (severity) {
		case "critical": return "[!!] ";
		case "warn":     return "[!]  ";
		case "suggest":  return "[>]  ";
		case "info":     return "[i]  ";
		default:         return "     ";
	}
}
