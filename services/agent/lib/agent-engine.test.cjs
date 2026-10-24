const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { AgentEngine, validate, schemas, safeData } = require('./agent-engine.cjs');
const ref = n => ({ uri: `artifact://s/images/${n}.png`, sha256: String(n).repeat(64) });
const call = (id, name, args) => ({ id, type: 'function', function: { name, arguments: JSON.stringify(args) } });
const tick = () => new Promise(r => setTimeout(r, 10));
async function settled(engine, id) { for (let i = 0; i < 300; i++) { const r = engine.get(id); if (!['running', 'recovering'].includes(r.status)) return r; await tick(); } throw new Error('not settled'); }
function fixture(t, overrides = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'rvl-agent-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  let next = 0;
  const requests = [], chats = [], jobs = new Map(), keys = new Map();
  const defaults = {
    directory, pollMs: 1, provider: () => ({ chat: true, tools: true, vision: true }),
    inspect: async r => ({ kind: 'image', uri: r.uri, preview: { mime: 'image/png', base64: 'PREVIEW' }, alpha: { min: 0 } }),
    director: async () => ({ scenes: [{ start: 0, end: 10, image_prompt: 'x', video_prompt: 'x' }] }),
    exporter: async () => ({ cancelled: true }),
    runtime: async (method, route, body, key) => {
      requests.push({ method, route, body, key });
      if (route === '/v1/capabilities') return { model_precisions: { bf16: true }, video: { ready: true }, music: { ready: true, cover_ready: true } };
      if (route === '/v1/health') return { workers: [], queue: { running: 0, pending: 0 } };
      if (route.includes('/messages')) return {};
      if (route.includes('/v1/library')) return { items: [ref(1)], total: 1 };
      if (route.includes('/media/analyze')) return { duration: 10 };
      if (method === 'POST') { const job_id = keys.get(key) || `job_${(++next).toString(16).padStart(12, '0')}`; keys.set(key, job_id); jobs.set(job_id, { id: job_id, status: 'completed', result: { media: [ref(next)], data: {} } }); return { job_id, status: 'queued' }; }
      if (method === 'DELETE') return { status: 'cancelled' };
      return jobs.get(route.split('/').pop());
    },
    chat: async messages => { chats.push(messages); return { content: 'done' }; },
  };
  const options = { ...defaults, ...overrides };
  const engine = new AgentEngine(options);
  return { engine, options, requests, chats, jobs, directory };
}

test('fused H3 is explicitly selected, defaults to four steps and preserves idempotency', async t => {
  let n = 0;
  const f = fixture(t, { chat: async () => n++ ? { content: 'done' } : { tool_calls: [call('v', 'video_generate', { prompt: 'cup', profile: 'fused_turbo' })] } });
  const baseRuntime = f.options.runtime;
  f.engine.runtime = async (...args) => args[1] === '/v1/capabilities'
    ? { video: { ready: true, profiles: { fused_turbo: { ready: true, steps: { min: 4, max: 12, default: 4 } } } } }
    : baseRuntime(...args);
  const run = await f.engine.start({ prompt: 'Crea un video H3 fused 4 pasos', session: 's' });
  assert.equal((await settled(f.engine, run.id)).status, 'completed');
  const post = f.requests.find(r => r.route === '/v1/jobs/video');
  assert.equal(post.body.profile, 'fused_turbo'); assert.equal(post.body.steps, 4); assert.ok(post.key);
});

for (const args of [{ profile: 'base', steps: 4 }, { profile: 'fused_turbo', steps: 13 }, { profile: 'fused_turbo', steps: 4 }]) {
  test(`invalid or unavailable H3 profile creates no GPU effects: ${JSON.stringify(args)}`, async t => {
    let n = 0;
    const f = fixture(t, { chat: async () => n++ ? { content: 'Unavailable' } : { tool_calls: [call('v', 'video_generate', { prompt: 'cup', ...args })] } });
    const run = await f.engine.start({ prompt: 'Crea video', session: 's' });
    await settled(f.engine, run.id);
    assert.equal(f.requests.filter(r => r.route === '/v1/jobs/video').length, 0);
  });
}

test('web export prepares an action, never claims a local file was saved', async t => {
  let n = 0;
  const f = fixture(t, { web: true, exporter: async (media, options) => ({ prepared: true, download: { media, ...options } }),
    chat: async () => n++ ? { content: 'Click download' } : { tool_calls: [call('export', 'artifact_export', { alias: 'artifact1', format: 'webp', quality: 81 })] } });
  const r = await f.engine.start({ prompt: 'Exporta mi imagen como WebP', session: 's', references: [ref(1)] });
  const done = await settled(f.engine, r.id);
  assert.equal(done.exported.prepared, true);
  assert.equal(done.exported.download.format, 'webp');
  assert.equal(done.turns[0].result.saved, false);
  assert.ok(!f.engine.tools.find(t => t.function.name === 'artifact_export').function.description.includes('native'));
});

test('agent request idempotency replays after restart and conflicts before effects', async t => {
  const f = fixture(t);
  const payload = { prompt: 'Hola', session: 's', idempotencyKey: 'browser-request' };
  const first = await f.engine.start(payload);
  await settled(f.engine, first.id);
  const restarted = new AgentEngine(f.options);
  const replay = await restarted.start(payload);
  assert.equal(replay.id, first.id);
  await assert.rejects(restarted.start({ ...payload, prompt: 'different' }), /conflict/);
  assert.equal(f.chats.length, 1);
});

test('all tool calls get real results and generated aliases can be reused', async t => {
  let step = 0, finalMessages;
  const f = fixture(t, { chat: async messages => {
    if (step++ === 0) return { tool_calls: [call('a', 'image_generate', { prompt: 'literal "RINARI"' }), call('b', 'health', {})] };
    if (step === 2) return { tool_calls: [call('c', 'image_edit', { prompt: 'preserve', references: ['artifact1'] })] };
    finalMessages = messages; return { content: 'Completed' };
  } });
  const r = await f.engine.start({ prompt: 'Crea y luego edita', session: 's' });
  const done = await settled(f.engine, r.id);
  assert.equal(done.status, 'completed'); assert.equal(done.turns.length, 3);
  assert.equal(finalMessages.filter(m => m.role === 'tool').length, 3);
  const posts = f.requests.filter(r => r.method === 'POST' && r.route.startsWith('/v1/jobs/'));
  assert.equal(posts.length, 2); assert.equal(posts[0].body.model_precision, 'bf16'); assert.equal(posts[0].body.quality, 'quality');
  assert.equal(posts[1].body.references[0].uri, ref(1).uri);
});

test('configured secret is redacted in IPC events, session mirror and disk', async t => {
  const secret = 'unique-configured-secret';
  const events = [];
  const f = fixture(t, { redact: text => text.split(secret).join('[REDACTED]'), emit: value => events.push(value),
    chat: async () => ({ content: `Provider echoed ${secret}` }) });
  const r = await f.engine.start({ prompt: 'Hola', session: 's' });
  await settled(f.engine, r.id);
  assert.ok(!JSON.stringify(f.engine.get(r.id)).includes(secret));
  assert.ok(!JSON.stringify(events).includes(secret));
  assert.ok(!JSON.stringify(f.requests.filter(r => r.route.endsWith('/messages'))).includes(secret));
  assert.ok(!fs.readFileSync(path.join(f.directory, `${r.id}.json`), 'utf8').includes(secret));
});

test('ten ordered references are preserved and every preview is numbered', async t => {
  let n = 0, outbound;
  const refs = Array.from({ length: 10 }, (_, i) => ref(i));
  const f = fixture(t, { chat: async messages => { outbound ||= messages; return n++ ? { content: 'done' } : { tool_calls: [call('edit', 'image_edit', { prompt: 'compose', references: refs.map((_, i) => `artifact${10 - i}`) })] }; } });
  const r = await f.engine.start({ prompt: 'Edita diez', session: 's', references: refs });
  assert.equal((await settled(f.engine, r.id)).status, 'completed');
  const post = f.requests.find(r => r.route === '/v1/jobs/edit');
  assert.deepEqual(post.body.references, [...refs].reverse());
  assert.equal(outbound.flatMap(m => Array.isArray(m.content) ? m.content : []).filter(p => p.type === 'image_url').length, 10);
  const persisted = fs.readFileSync(path.join(f.directory, `${r.id}.json`), 'utf8');
  assert.ok(!persisted.includes('PREVIEW')); assert.ok(!persisted.includes('base64'));
});

test('invalid arguments, invented refs and arbitrary paths cause no GPU effects', async t => {
  let n = 0;
  const f = fixture(t, { chat: async () => n++ ? { content: 'reported' } : { tool_calls: [call('bad', 'image_generate', { prompt: 'x', workflow: {} }), call('fake', 'image_edit', { prompt: 'x', references: ['imaginary'] }), call('export', 'artifact_export', { alias: 'artifact1', path: 'C:/evil' })] } });
  const r = await f.engine.start({ prompt: 'Hola', session: 's' });
  const done = await settled(f.engine, r.id);
  assert.equal(done.turns.length, 3); assert.ok(done.turns.every(t => t.result.error));
  assert.ok(!f.requests.some(r => r.method === 'POST' && r.route.startsWith('/v1/jobs/')));
});

test('new attached target keeps its explicit order across existing-session aliases', async t => {
  let instruction;
  const f = fixture(t, { chat: async messages => { instruction = messages[0].content; return { content: 'done' }; } });
  const first = await f.engine.start({ prompt: 'Mira', session: 's', references: [ref(1)] });
  await settled(f.engine, first.id);
  const next = await f.engine.start({ prompt: 'Edita la primera referencia', session: 's', references: [ref(2), ref(1)] });
  const done = await settled(f.engine, next.id);
  assert.deepEqual(done.references, [{ alias: 'artifact2', number: 1, role: 'edit target' }, { alias: 'artifact1', number: 2, role: 'visual reference' }]);
  assert.ok(instruction.includes('first is editing target, regardless of alias number'));
});

test('timeout after submission replays stable idempotency key after restart, never duplicates GPU job', async t => {
  let n = 0;
  const f = fixture(t, { chat: async () => n++ ? { content: 'done' } : { tool_calls: [call('create', 'image_generate', { prompt: 'x' })] } });
  const original = f.options.runtime;
  let lost = true;
  f.engine.runtime = async (...args) => { const result = await original(...args); if (args[0] === 'POST' && args[1].startsWith('/v1/jobs/') && lost) { lost = false; throw new Error('timeout'); } return result; };
  const r = await f.engine.start({ prompt: 'Crea', session: 's' });
  assert.equal((await settled(f.engine, r.id)).status, 'paused');
  const restarted = new AgentEngine(f.options);
  await restarted.continue(r.id);
  assert.equal((await settled(restarted, r.id)).status, 'completed');
  const posts = f.requests.filter(r => r.route === '/v1/jobs/generate');
  assert.equal(posts.length, 2); assert.equal(posts[0].key, posts[1].key); assert.equal(f.jobs.size, 1);
});

test('job cancellation is scoped and saving requires user request', async t => {
  const f = fixture(t);
  const run = { id: 'r', request: 'Hola', jobs: {}, artifacts: { artifact1: ref(1) } };
  await assert.rejects(f.engine.execute(run, { tool: 'job_cancel' }, { job_id: 'foreign' }), /autorizado/);
  await assert.rejects(f.engine.execute(run, { tool: 'artifact_export' }, { alias: 'artifact1' }), /explícita/);
});

test('provider without tools does not disable direct runtime, without vision still executes', async t => {
  const noTools = fixture(t, { provider: () => ({ tools: false }) });
  await assert.rejects(noTools.engine.start({ prompt: 'x', session: 's' }), /herramientas/);
  const noVision = fixture(t, { provider: () => ({ tools: true, vision: false }) });
  const r = await noVision.engine.start({ prompt: 'x', session: 's', references: [ref(1)] });
  assert.equal((await settled(noVision.engine, r.id)).status, 'completed');
  assert.ok(noVision.chats.every(ms => ms.every(m => typeof m.content === 'string')));
});

test('response budget persists and continuation is explicit', async t => {
  let n = 0;
  const f = fixture(t, { chat: async () => ({ tool_calls: [call(`c${++n}`, 'health', {})] }) });
  const r = await f.engine.start({ prompt: 'consulta', session: 's' });
  const done = await settled(f.engine, r.id);
  assert.equal(done.status, 'budget'); assert.equal(done.responses, 16); assert.equal(done.calls, 16);
});

test('schema rejects invalid values and storage strips secret/binary fields', () => {
  assert.throws(() => validate(schemas.video_generate, { prompt: 'x', seconds: 16 }));
  assert.throws(() => validate(schemas.music_generate, { style: 'x', lyrics: 'x', steps: 81 }));
  assert.deepEqual(safeData({ apiKey: 'SECRET', Authorization: 'SECRET', headers: {}, base64: 'BYTES', result: { uri: 'ok' } }), { result: { uri: 'ok' } });
});


test('advanced model options are validated and forwarded by the native agent', async t => {
  validate(schemas.music_generate, { style: 'pop', lyrics: '[Instrumental]', options: { composition: { temperature: 1.4 }, score: { max_abc_tokens: 1024 }, format: 'opus', audio_quality: '192k' } });
  assert.throws(() => validate(schemas.video_generate, { prompt: 'x', options: { cfg: 2 } }), /unknown field/);
  assert.throws(() => validate(schemas.image_generate, { prompt: 'x', options: { sampler: 'invented' } }), /unsupported/);
  let n = 0;
  const options = { resolution: '480p', codec: 'av1', crf: 18, shift_video: 9 };
  const f = fixture(t, { chat: async () => n++ ? { content: 'done' } : { tool_calls: [call('v', 'video_generate', { prompt: 'cup', options })] } });
  const run = await f.engine.start({ session: 's', prompt: 'Genera un vídeo con resolución 480p y AV1' });
  const result = await settled(f.engine, run.id);
  assert.equal(result.status, 'completed');
  const submitted = f.requests.find(r => r.route === '/v1/jobs/video');
  assert.deepEqual(submitted.body.options, options);
});

test('Spanish requests retain original text while all model instructions require English', async t => {
  let outbound;
  const f = fixture(t, { chat: async messages => { outbound = messages; return { content: 'done' }; } });
  const request = 'Crea una imagen con el texto literal "Buenas noches"';
  const run = await f.engine.start({ session: 's', prompt: request });
  const done = await settled(f.engine, run.id);
  assert.equal(done.request, request);
  assert.ok(outbound[0].content.includes('Write all model-facing descriptive prompts in English'));
  assert.ok(outbound[0].content.includes('Do not write descriptive model prompts in Spanish'));
  assert.ok(outbound[0].content.includes('Keep lyrics, literal visible text, spoken dialogue'));
  assert.ok(outbound.some(message => message.content === request));
});

test('capability guidance is English without mutating UI metadata or literal user content', () => {
  const { englishCapabilities } = require('./agent-language.cjs');
  const caps = { generation_options: { image: [{ label: 'Muestreador', group: 'Muestreo', choices: ['euler'], min: 0 }] } };
  const translated = englishCapabilities(caps);
  assert.equal(translated.generation_options.image[0].label, 'Sampler');
  assert.equal(translated.generation_options.image[0].group, 'Sampling');
  assert.equal(caps.generation_options.image[0].label, 'Muestreador');
  assert.deepEqual(translated.generation_options.image[0].choices, ['euler']);
});

test('provider prompts carry the model guide for each target and parse songs', () => {
  const { improveSystem, parseImproved, directorSystem, reviewSystem } = require('./agent-prompts.cjs');
  assert.match(improveSystem('t2i'), /observer/);
  assert.match(improveSystem('i2i', { references: 2 }), /<image1>/);
  assert.match(improveSystem('r2v', { references: 1, seconds: 8 }), /Requested duration: 8[\s\S]*retention_analysis/);
  assert.match(improveSystem('song'), /\[Pre-Chorus\]/);
  assert.throws(() => improveSystem('cover'), /no admitido/);
  assert.deepEqual(parseImproved('song', '```json\n{"style":"rock, drums","lyrics":"[Verse]\\nHola"}\n```'), { prompt: 'rock, drums', lyrics: '[Verse]\nHola' });
  assert.equal(parseImproved('t2v', '```\nintegrated_multimodal_description: x\n```').prompt, 'integrated_multimodal_description: x');
  assert.match(directorSystem(), /non_diegetic_music: N\/A[\s\S]*Qwen-Image-2.1 · text to image[\s\S]*MiniMax H3/);
  assert.match(reviewSystem(), /suggested_prompt/);
  const names = require('./agent-engine.cjs').TOOLS.map(t => t.function.name);
  assert.ok(names.includes('prompt_guide') && names.includes('prompt_check'));
});

test('Qwen Turbo is chosen explicitly, drops fixed-schedule options and never substitutes', async t => {
  let n = 0;
  const f = fixture(t, { chat: async () => n++ ? { content: 'done' } : { tool_calls: [call('i', 'image_generate', { prompt: 'a cafe', model_variant: 'turbo', options: { steps: 30, cfg: 1.2 } })] } });
  const base = f.options.runtime;
  f.engine.runtime = async (...args) => args[1] === '/v1/capabilities'
    ? { model_precisions: { bf16: true }, model_variants: { turbo: { precisions: { int8: true, bf16: false } } } } : base(...args);
  const run = await f.engine.start({ prompt: 'Crea una imagen rápida con Turbo', session: 's' });
  const done = await settled(f.engine, run.id);
  assert.equal(done.status, 'completed');
  const post = f.requests.find(r => r.route === '/v1/jobs/generate');
  assert.equal(post.body.model_variant, 'turbo'); assert.equal(post.body.model_precision, 'int8');
  assert.deepEqual(post.body.options, { cfg: 1.2 });
  assert.ok(done.notices.some(notice => notice.includes('8 pasos')));
});

test('Turbo without installed weights creates no GPU effect', async t => {
  let n = 0;
  const f = fixture(t, { chat: async () => n++ ? { content: 'Unavailable' } : { tool_calls: [call('i', 'image_generate', { prompt: 'a cafe', model_variant: 'turbo' })] } });
  const run = await f.engine.start({ prompt: 'Imagen Turbo', session: 's' });
  await settled(f.engine, run.id);
  assert.equal(f.requests.filter(r => r.route === '/v1/jobs/generate').length, 0);
});

test('video_upscale sends the known video alias with x2 fast defaults', async t => {
  let n = 0;
  const video = { uri: 'artifact://s/videos/clip.mp4', sha256: 'c'.repeat(64) };
  const f = fixture(t, { chat: async () => n++ ? { content: 'done' } : { tool_calls: [call('u', 'video_upscale', { video: 'artifact1' })] } });
  const base = f.options.runtime;
  f.engine.runtime = async (...args) => args[1] === '/v1/capabilities' ? { upscale: { ready: true } } : base(...args);
  const run = await f.engine.start({ prompt: 'Escala este vídeo a x2', session: 's', references: [video] });
  assert.equal((await settled(f.engine, run.id)).status, 'completed');
  const post = f.requests.find(r => r.route === '/v1/jobs/upscale');
  assert.deepEqual(post.body.video, video); assert.equal(post.body.scale, 2); assert.equal(post.body.quality, 'fast'); assert.ok(post.key);
});
