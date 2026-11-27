/* Daily-history studies used by the Pro report. Null means insufficient data. */
(() => {
    const finite = (value) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
    const series = (values) => (values || []).map(finite);
    const sma = (values, length) => {
        const out = Array(values.length).fill(null);
        let sum = 0;
        let count = 0;
        for (let i = 0; i < values.length; i++) {
            if (values[i] !== null) { sum += values[i]; count++; }
            if (i >= length && values[i - length] !== null) { sum -= values[i - length]; count--; }
            if (i >= length - 1 && count === length) out[i] = sum / length;
        }
        return out;
    };
    const ema = (values, length) => {
        const out = Array(values.length).fill(null);
        const seed = sma(values, length);
        const weight = 2 / (length + 1);
        let previous = null;
        for (let i = 0; i < values.length; i++) {
            if (values[i] === null) { previous = null; continue; }
            if (previous === null) previous = seed[i];
            else previous = values[i] * weight + previous * (1 - weight);
            out[i] = previous;
        }
        return out;
    };
    const bands = (values, length = 20, deviations = 2) => {
        const middle = sma(values, length);
        const upper = Array(values.length).fill(null);
        const lower = Array(values.length).fill(null);
        for (let i = length - 1; i < values.length; i++) {
            if (middle[i] === null) continue;
            const window = values.slice(i - length + 1, i + 1);
            const variance = window.reduce((sum, value) => sum + (value - middle[i]) ** 2, 0) / length;
            const spread = Math.sqrt(variance) * deviations;
            upper[i] = middle[i] + spread;
            lower[i] = middle[i] - spread;
        }
        return { middle, upper, lower };
    };
    const rsi = (values, length = 14) => {
        const out = Array(values.length).fill(null);
        let gains = 0;
        let losses = 0;
        let count = 0;
        let averageGain = null;
        let averageLoss = null;
        for (let i = 1; i < values.length; i++) {
            if (values[i] === null || values[i - 1] === null) {
                gains = losses = count = 0;
                averageGain = averageLoss = null;
                continue;
            }
            const change = values[i] - values[i - 1];
            const gain = Math.max(change, 0);
            const loss = Math.max(-change, 0);
            if (averageGain === null) {
                gains += gain; losses += loss; count++;
                if (count === length) {
                    averageGain = gains / length;
                    averageLoss = losses / length;
                }
            } else {
                averageGain = (averageGain * (length - 1) + gain) / length;
                averageLoss = (averageLoss * (length - 1) + loss) / length;
            }
            if (averageGain !== null) out[i] = averageLoss === 0 ? (averageGain === 0 ? 50 : 100) :
                100 - 100 / (1 + averageGain / averageLoss);
        }
        return out;
    };
    const macd = (values) => {
        const fast = ema(values, 12);
        const slow = ema(values, 26);
        const line = fast.map((value, i) => value === null || slow[i] === null ? null : value - slow[i]);
        const signal = ema(line, 9);
        return { line, signal, histogram: line.map((value, i) => value === null || signal[i] === null ? null : value - signal[i]) };
    };
    const atr = (high, low, close, length = 14) => {
        const out = Array(close.length).fill(null);
        let sum = 0;
        let count = 0;
        let previous = null;
        for (let i = 0; i < close.length; i++) {
            if (high[i] === null || low[i] === null || close[i] === null) { sum = count = 0; previous = null; continue; }
            const priorClose = i > 0 ? close[i - 1] : null;
            const range = Math.max(high[i] - low[i], priorClose === null ? 0 : Math.abs(high[i] - priorClose),
                priorClose === null ? 0 : Math.abs(low[i] - priorClose));
            if (previous === null) {
                sum += range; count++;
                if (count === length) previous = sum / length;
            } else previous = (previous * (length - 1) + range) / length;
            out[i] = previous;
        }
        return out;
    };
    const calculate = (history) => {
        const close = series(history.close);
        const high = series(history.high);
        const low = series(history.low);
        return {
            sma20: sma(close, 20), sma50: sma(close, 50), sma200: sma(close, 200),
            ema12: ema(close, 12), ema26: ema(close, 26),
            bands: bands(close), rsi: rsi(close), macd: macd(close), atr: atr(high, low, close),
        };
    };
    const api = { finite, series, sma, ema, bands, rsi, macd, atr, calculate };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    if (typeof window !== "undefined") window.StockSightIndicators = api;
})();
