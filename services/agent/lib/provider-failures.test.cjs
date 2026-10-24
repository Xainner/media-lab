const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { AgentEngine } = require('./agent-engine.cjs');
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function done(engine, id) { for (let i = 0; i < 500; i++) { const r = engine.get(id); if (!['running', 'recovering'].includes(r.status)) return r; await sleep(10); } throw new Error('timeout'); }
function create(t, chat) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'rvl-provider-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const requests = [];
  const engine = new AgentEngine({ directory, provider: () => ({ tools: true, vision: true }), chat,
    inspect: async () => ({ kind: 'image', preview: { mime: 'image/png', base64: 'PREVIEW' } }),
    runtime: async (method, route, body) => {
      requests.push({ method, route, body });
      if (route === '/v1/capabilities') return { model_precisions: { bf16: true } };
      if (route === '/v1/health') return { workers: [], queue: {} };
      if (route === '/v1/jobs/generate' && method === 'POST') return { job_id: 'job_000000000001', status: 'queued' };
      if (route === '/v1/jobs/job_000000000001') return { status: 'completed', result: { media: [{ uri: 'artifact://s/images/result.png', sha256: 'a'.repeat(64) }] } };
      return {};
    }, pollMs: 1,
  });
  return { engine, requests, directory };
}
test('provider timeout is bounded; direct runtime remains available', async t => {
  let attempts = 0;
  const { engine, requests } = create(t, async () => { attempts++; throw new Error('fetch failed timeout'); });
  const r = await engine.start({ prompt: 'Create', session: 's' });
  assert.equal((await done(engine, r.id)).status, 'failed'); assert.equal(attempts, 2);
  assert.ok(!requests.some(r => r.route.startsWith('/v1/jobs/')));
  assert.ok(await engine.runtime('GET', '/v1/capabilities'));
});
test('invalid provider response has no effects', async t => {
  const { engine, requests } = create(t, async () => ({ content: { invalid: true } }));
  const r = await engine.start({ prompt: 'Create', session: 's' });
  assert.equal((await done(engine, r.id)).status, 'failed');
  assert.ok(!requests.some(r => r.route.startsWith('/v1/jobs/')));
});
test('vision failure degrades to metadata without repeating completed generation', async t => {
  let attempts = 0;
  const { engine, requests } = create(t, async messages => {
    if (!attempts++) return { tool_calls: [{ id: 'create', type: 'function', function: { name: 'image_generate', arguments: '{"prompt":"x"}' } }] };
    if (messages.some(m => Array.isArray(m.content) && m.content.some(p => p.type === 'image_url'))) throw new Error('Proveedor respondió 500: vision failed');
    return { content: 'Result completed; visual review unavailable.' };
  });
  const r = await engine.start({ prompt: 'Create one image', session: 's' });
  const result = await done(engine, r.id);
  assert.equal(result.status, 'completed'); assert.equal(result.visionDisabled, true);
  assert.equal(requests.filter(r => r.route === '/v1/jobs/generate' && r.method === 'POST').length, 1);
});
test('model cannot request unsolicited correction generation', async t => {
  let n = 0;
  const { engine, requests } = create(t, async () => n++ < 2 ? { tool_calls: [{ id: `create${n}`, type: 'function', function: { name: 'image_generate', arguments: '{"prompt":"x"}' } }] } : { content: 'done' });
  const r = await engine.start({ prompt: 'Create one image', session: 's' });
  const result = await done(engine, r.id);
  assert.equal(result.status, 'completed'); assert.ok(result.turns[1].result.error);
  assert.equal(requests.filter(r => r.route === '/v1/jobs/generate' && r.method === 'POST').length, 1);
});
