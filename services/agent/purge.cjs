'use strict';
const fs = require('node:fs');
const path = require('node:path');

// Called only after authenticating the internal service and owner headers.
function purgeAccount({ uid, directory, engines, blockedUsers, inflight, recovery }) {
  if (!/^[a-f0-9]{32}$/.test(uid || '')) throw new Error('Invalid owner');
  blockedUsers.add(uid);
  const active = engines.get(uid)?.engine;
  if (active) {
    for (const run of active.runs.values()) { run.cancelled = true; active.save(run); }
    if (active.executing.size || active.startingSessions.size) return false;
  }
  if (inflight.get(uid)) return false;
  const root = path.resolve(directory), folder = path.resolve(root, uid);
  if (path.dirname(folder) !== root || folder === root) throw new Error('Unsafe path');
  // A symlinked state root or account is never followed for recursive removal.
  if (fs.realpathSync(root) !== root || (fs.existsSync(folder) && fs.realpathSync(folder) !== folder)) throw new Error('Unsafe path');
  fs.rmSync(folder, { recursive: true, force: true });
  engines.delete(uid);
  recovery.resolved(uid);
  return true;
}
module.exports = { purgeAccount };
