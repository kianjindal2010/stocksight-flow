const test = require('node:test');
const assert = require('node:assert/strict');
const studies = require('../static/pro_indicators.js');

test('moving averages wait for enough valid closes', () => {
    assert.deepEqual(studies.sma([1, 2, 3, 4], 3), [null, null, 2, 3]);
    assert.deepEqual(studies.ema([1, 2, 3, 4], 3), [null, null, 2, 3]);
    assert.deepEqual(studies.sma([1, null, 3, 4], 3), [null, null, null, null]);
    assert.equal(studies.finite(null), null);
    assert.equal(studies.finite(''), null);
});

test('Bollinger Bands use the full rolling window', () => {
    const result = studies.bands([1, 2, 3], 3, 2);
    assert.equal(result.middle[2], 2);
    assert.ok(Math.abs(result.upper[2] - (2 + 2 * Math.sqrt(2 / 3))) < 1e-10);
    assert.ok(Math.abs(result.lower[2] - (2 - 2 * Math.sqrt(2 / 3))) < 1e-10);
});

test('RSI distinguishes rising, falling, and flat histories', () => {
    assert.equal(studies.rsi(Array.from({ length: 16 }, (_, i) => i + 1))[14], 100);
    assert.equal(studies.rsi(Array.from({ length: 16 }, (_, i) => 20 - i))[14], 0);
    assert.equal(studies.rsi(Array(16).fill(10))[14], 50);
});

test('MACD signal and ATR only appear after their seed periods', () => {
    const close = Array.from({ length: 40 }, (_, i) => i + 1);
    const macd = studies.macd(close);
    assert.equal(macd.line[24], null);
    assert.ok(Number.isFinite(macd.line[25]));
    assert.equal(macd.signal[32], null);
    assert.ok(Number.isFinite(macd.signal[33]));
    assert.ok(Number.isFinite(macd.histogram[33]));
    const atr = studies.atr(Array(15).fill(11), Array(15).fill(9), Array(15).fill(10));
    assert.equal(atr[12], null);
    assert.equal(atr[13], 2);
});
