const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { purgeAccount } = require('./purge.cjs');

function fixture(t) {
  const directory = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'rvl-purge-')));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const uid = 'a'.repeat(32), other = 'b'.repeat(32);
  for (const owner of [uid,other]) { fs.mkdirSync(path.join(directory,owner)); fs.writeFileSync(path.join(directory,owner,'private.json'),'private'); }
  return { uid, other, directory, engines:new Map(), blockedUsers:new Set(), inflight:new Map(), recovery:{resolved() {}} };
}
test('purge waits for execution and admission, then removes only the owner and is retryable', t => {
  const f=fixture(t), run={cancelled:false}, engine={runs:new Map([['run',run]]),executing:new Set(['run']),startingSessions:new Set(),save() {}};
  f.engines.set(f.uid,{engine});
  assert.equal(purgeAccount(f),false); assert.equal(run.cancelled,true); assert.equal(f.blockedUsers.has(f.uid),true);
  engine.executing.clear(); f.inflight.set(f.uid,1);
  assert.equal(purgeAccount(f),false); f.inflight.delete(f.uid);
  assert.equal(purgeAccount(f),true); assert.equal(fs.existsSync(path.join(f.directory,f.uid)),false);
  assert.equal(fs.readFileSync(path.join(f.directory,f.other,'private.json'),'utf8'),'private');
  assert.equal(purgeAccount(f),true); assert.equal(f.engines.has(f.uid),false);
});
test('unsafe owner and symlinked account do not affect another account', t => {
  const f=fixture(t);
  assert.throws(()=>purgeAccount({...f,uid:'../'+f.other}));
  fs.rmSync(path.join(f.directory,f.uid),{recursive:true});
  fs.symlinkSync(path.join(f.directory,f.other),path.join(f.directory,f.uid),'junction');
  assert.throws(()=>purgeAccount(f),/Unsafe path/);
  assert.equal(fs.readFileSync(path.join(f.directory,f.other,'private.json'),'utf8'),'private');
});
