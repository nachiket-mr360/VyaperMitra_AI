import assert from 'node:assert/strict'

function rms(frame) {
  if (frame.length === 0) return 0
  let sum = 0
  for (let i = 0; i < frame.length; i += 1) sum += frame[i] * frame[i]
  return Math.sqrt(sum / frame.length)
}

assert.equal(rms(new Float32Array(0)), 0)
assert.ok(rms(new Float32Array(64).fill(0)) < 0.0001)
assert.ok(rms(new Float32Array(64).fill(0.2)) > 0.19)
console.log('vad rms ok')
