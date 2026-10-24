'use strict';

// Fail closed until the filesystem scan succeeds; a later successful account
// reconciliation must also clear failures from the initial bounded boot retry.
class RecoveryGate {
  constructor() { this.pending = null; }
  scan(users) { this.pending = new Set(users); }
  resolved(user) { this.pending?.delete(user); }
  get recovering() { return this.pending === null || this.pending.size > 0; }
}

module.exports = { RecoveryGate };
