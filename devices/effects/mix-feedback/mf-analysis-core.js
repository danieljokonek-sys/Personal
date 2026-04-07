/**
 * mf-analysis-core.js
 * Mix Feedback Device — Analysis Core
 *
 * IIR bandpass filter bank and feature extraction for spectral analysis.
 * Runs inside Max's [js] object. Provides functions used by the main engine.
 *
 * Frequency Bands:
 *   0: Sub      (20–60 Hz)
 *   1: Low      (60–250 Hz)
 *   2: Low-Mid  (250–1000 Hz)
 *   3: Mid      (1000–4000 Hz)
 *   4: High-Mid (4000–8000 Hz)
 *   5: High     (8000–20000 Hz)
 */

// ─── Band Definitions ───────────────────────────────────────────────

var BANDS = [
	{ name: "Sub",      lo: 20,   hi: 60,    center: 40    },
	{ name: "Low",      lo: 60,   hi: 250,   center: 125   },
	{ name: "Low-Mid",  lo: 250,  hi: 1000,  center: 500   },
	{ name: "Mid",      lo: 1000, hi: 4000,  center: 2000  },
	{ name: "High-Mid", lo: 4000, hi: 8000,  center: 6000  },
	{ name: "High",     lo: 8000, hi: 20000, center: 14000 }
];

var NUM_BANDS = BANDS.length;

// ─── 2nd-Order IIR Biquad Filter ────────────────────────────────────

function BiquadBandpass(centerFreq, bandwidth, sampleRate) {
	var w0 = 2.0 * Math.PI * centerFreq / sampleRate;
	var cosw0 = Math.cos(w0);
	var sinw0 = Math.sin(w0);
	var sinhArg = Math.LN2 / 2.0 * bandwidth * w0 / sinw0;
	var alpha = sinw0 * (Math.exp(sinhArg) - Math.exp(-sinhArg)) / 2.0;

	// Bandpass filter coefficients (constant skirt gain, peak = Q)
	this.b0 = alpha;
	this.b1 = 0.0;
	this.b2 = -alpha;
	this.a0 = 1.0 + alpha;
	this.a1 = -2.0 * cosw0;
	this.a2 = 1.0 - alpha;

	// Normalize coefficients
	this.b0 /= this.a0;
	this.b1 /= this.a0;
	this.b2 /= this.a0;
	this.a1 /= this.a0;
	this.a2 /= this.a0;

	// Filter state
	this.x1 = 0.0;
	this.x2 = 0.0;
	this.y1 = 0.0;
	this.y2 = 0.0;
}

BiquadBandpass.prototype.process = function(x) {
	var y = this.b0 * x + this.b1 * this.x1 + this.b2 * this.x2
	        - this.a1 * this.y1 - this.a2 * this.y2;
	this.x2 = this.x1;
	this.x1 = x;
	this.y2 = this.y1;
	this.y1 = y;
	return y;
};

BiquadBandpass.prototype.reset = function() {
	this.x1 = 0.0; this.x2 = 0.0;
	this.y1 = 0.0; this.y2 = 0.0;
};

// ─── Filter Bank ────────────────────────────────────────────────────

function FilterBank(sampleRate) {
	this.sampleRate = sampleRate;
	this.filters = [];
	for (var i = 0; i < NUM_BANDS; i++) {
		var bw = Math.log(BANDS[i].hi / BANDS[i].lo) / Math.LN2;
		this.filters.push(new BiquadBandpass(BANDS[i].center, bw, sampleRate));
	}
}

FilterBank.prototype.reset = function() {
	for (var i = 0; i < this.filters.length; i++) {
		this.filters[i].reset();
	}
};

FilterBank.prototype.processSample = function(x) {
	var out = [];
	for (var i = 0; i < this.filters.length; i++) {
		out.push(this.filters[i].process(x));
	}
	return out;
};

// ─── Feature Extraction ─────────────────────────────────────────────

/**
 * Analyze a mono audio buffer (array of samples) and extract features.
 *
 * @param {number[]} samples - Mono audio samples (-1 to 1)
 * @param {number} sampleRate - Sample rate in Hz
 * @param {number} windowSec - Analysis window length in seconds (default 0.1)
 * @returns {object} Feature set
 */
function extractFeatures(samples, sampleRate, windowSec) {
	if (!windowSec) windowSec = 0.1;

	var numSamples = samples.length;
	var windowSize = Math.floor(sampleRate * windowSec);
	var numWindows = Math.floor(numSamples / windowSize);
	if (numWindows < 1) numWindows = 1;

	var bank = new FilterBank(sampleRate);

	// Accumulators
	var bandRmsSum = [];
	var bandPeak = [];
	var bandRmsWindows = []; // per-window RMS for dynamic range calc
	for (var b = 0; b < NUM_BANDS; b++) {
		bandRmsSum.push(0.0);
		bandPeak.push(0.0);
		bandRmsWindows.push([]);
	}

	var globalRmsSum = 0.0;
	var globalPeak = 0.0;
	var globalRmsWindows = [];

	// Process each window
	// NOTE: do NOT reset the filter bank between windows —
	// IIR filters need continuity to produce accurate band energy.
	for (var w = 0; w < numWindows; w++) {
		var start = w * windowSize;
		var end = Math.min(start + windowSize, numSamples);
		var windowBandRms = [];
		var windowGlobalSum = 0.0;
		var windowGlobalPeak = 0.0;

		for (var b2 = 0; b2 < NUM_BANDS; b2++) {
			windowBandRms.push(0.0);
		}

		for (var s = start; s < end; s++) {
			var sample = samples[s];
			var bandSamples = bank.processSample(sample);

			windowGlobalSum += sample * sample;
			var absSample = Math.abs(sample);
			if (absSample > windowGlobalPeak) windowGlobalPeak = absSample;
			if (absSample > globalPeak) globalPeak = absSample;

			for (var b3 = 0; b3 < NUM_BANDS; b3++) {
				var bs = bandSamples[b3];
				windowBandRms[b3] += bs * bs;
				var absbs = Math.abs(bs);
				if (absbs > bandPeak[b3]) bandPeak[b3] = absbs;
			}
		}

		var windowLen = end - start;
		var windowGlobalRms = Math.sqrt(windowGlobalSum / windowLen);
		globalRmsWindows.push(windowGlobalRms);
		globalRmsSum += windowGlobalSum;

		for (var b4 = 0; b4 < NUM_BANDS; b4++) {
			var rms = Math.sqrt(windowBandRms[b4] / windowLen);
			bandRmsWindows[b4].push(rms);
			bandRmsSum[b4] += windowBandRms[b4];
		}
	}

	// Global features
	var globalRms = Math.sqrt(globalRmsSum / numSamples);
	var globalRmsDb = ampToDb(globalRms);
	var globalPeakDb = ampToDb(globalPeak);
	var crestFactor = globalPeakDb - globalRmsDb;
	var dynamicRange = calcDynamicRange(globalRmsWindows);

	// Per-band features
	var bandFeatures = [];
	for (var b5 = 0; b5 < NUM_BANDS; b5++) {
		var bRms = Math.sqrt(bandRmsSum[b5] / numSamples);
		var bRmsDb = ampToDb(bRms);
		var bPeakDb = ampToDb(bandPeak[b5]);
		var bCrest = bPeakDb - bRmsDb;
		var bDynRange = calcDynamicRange(bandRmsWindows[b5]);

		bandFeatures.push({
			name: BANDS[b5].name,
			center: BANDS[b5].center,
			lo: BANDS[b5].lo,
			hi: BANDS[b5].hi,
			rmsDb: bRmsDb,
			peakDb: bPeakDb,
			crestFactor: bCrest,
			dynamicRange: bDynRange
		});
	}

	return {
		globalRmsDb: globalRmsDb,
		globalPeakDb: globalPeakDb,
		crestFactor: crestFactor,
		dynamicRange: dynamicRange,
		bands: bandFeatures,
		sampleRate: sampleRate,
		durationSec: numSamples / sampleRate
	};
}

// ─── Stereo Feature Extraction ──────────────────────────────────────

/**
 * Extract stereo-specific features (width, correlation per band).
 *
 * @param {number[]} leftSamples
 * @param {number[]} rightSamples
 * @param {number} sampleRate
 * @returns {object} Stereo features
 */
function extractStereoFeatures(leftSamples, rightSamples, sampleRate) {
	var numSamples = Math.min(leftSamples.length, rightSamples.length);
	var bankL = new FilterBank(sampleRate);
	var bankR = new FilterBank(sampleRate);

	// Per-band correlation accumulators
	var bandLR = [];
	var bandLL = [];
	var bandRR = [];
	for (var b = 0; b < NUM_BANDS; b++) {
		bandLR.push(0.0);
		bandLL.push(0.0);
		bandRR.push(0.0);
	}

	// Global mid/side energy
	var midEnergy = 0.0;
	var sideEnergy = 0.0;

	for (var s = 0; s < numSamples; s++) {
		var l = leftSamples[s];
		var r = rightSamples[s];

		var mid = (l + r) * 0.5;
		var side = (l - r) * 0.5;
		midEnergy += mid * mid;
		sideEnergy += side * side;

		var bL = bankL.processSample(l);
		var bR = bankR.processSample(r);

		for (var b2 = 0; b2 < NUM_BANDS; b2++) {
			bandLR[b2] += bL[b2] * bR[b2];
			bandLL[b2] += bL[b2] * bL[b2];
			bandRR[b2] += bR[b2] * bR[b2];
		}
	}

	// Per-band correlation (-1 to +1, where +1 = mono, 0 = uncorrelated)
	var bandCorrelation = [];
	var bandWidth = [];
	for (var b3 = 0; b3 < NUM_BANDS; b3++) {
		var denom = Math.sqrt(bandLL[b3] * bandRR[b3]);
		var corr = (denom > 0.0) ? bandLR[b3] / denom : 1.0;
		bandCorrelation.push(corr);
		// Width: 0 = mono, 1 = full stereo, >1 = out of phase
		bandWidth.push(1.0 - corr);
	}

	// Overall stereo width (mid/side ratio)
	var totalEnergy = midEnergy + sideEnergy;
	var stereoWidth = (totalEnergy > 0.0) ? sideEnergy / totalEnergy : 0.0;

	return {
		stereoWidth: stereoWidth,
		bandCorrelation: bandCorrelation,
		bandWidth: bandWidth,
		monoCompatibility: midEnergy / (totalEnergy > 0 ? totalEnergy : 1.0)
	};
}

// ─── Utility Functions ──────────────────────────────────────────────

function ampToDb(amp) {
	if (amp <= 0.000001) return -120.0;
	return 20.0 * Math.log(amp) / Math.LN10;
}

function dbToAmp(db) {
	return Math.pow(10.0, db / 20.0);
}

function calcDynamicRange(rmsWindows) {
	if (rmsWindows.length < 2) return 0.0;

	// Sort and take 10th and 90th percentile to avoid outliers
	var sorted = rmsWindows.slice().sort(function(a, b) { return a - b; });
	var p10idx = Math.floor(sorted.length * 0.1);
	var p90idx = Math.floor(sorted.length * 0.9);

	var quiet = sorted[p10idx];
	var loud = sorted[p90idx];

	if (quiet <= 0.000001) quiet = 0.000001;
	if (loud <= 0.000001) return 0.0;

	return ampToDb(loud) - ampToDb(quiet);
}
