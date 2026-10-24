const { test } = require('node:test');
const assert = require('node:assert/strict');
const { RecoveryGate } = require('./recovery.cjs');

test('boot failure stays closed until every pending user reconciles later', () => {
  const gate = new RecoveryGate();
  assert.equal(gate.recovering, true);
  gate.scan(['alice', 'bob']);
  gate.resolved('alice');
  assert.equal(gate.recovering, true);
  gate.resolved('bob');
  assert.equal(gate.recovering, false);
});

test('empty successful scan opens but an unknown user cannot clear pending users', () => {
  const gate = new RecoveryGate();
  gate.scan(['alice']); gate.resolved('bob');
  assert.equal(gate.recovering, true);
  gate.resolved('alice'); assert.equal(gate.recovering, false);
  gate.scan([]); assert.equal(gate.recovering, false);
});
