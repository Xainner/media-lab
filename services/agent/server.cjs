'use strict';
const { improveSystem, parseImproved, improveTokens, directorSystem, reviewSystem } = require('./lib/agent-prompts.cjs');
// Private Node engine. Provider networking/secrets remain in the authenticated Python backend.
const http = require('node:http');
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { AgentEngine } = require('./lib/agent-engine.cjs');
const { RecoveryGate } = require('./recovery.cjs');
const { purgeAccount } = require('./purge.cjs');

const keyPath = process.env.AGENT_SERVICE_KEY_FILE;
const keyInfo = fs.statSync(keyPath);
if ((keyInfo.mode & 0o077) || keyInfo.uid !== process.getuid()) throw new Error('Service key must be owned by service uid with mode 0600');
const key = fs.readFileSync(keyPath);
if (key.length !== 32) throw new Error('Service key must be 32 bytes');
const serviceKey = key.toString('hex');
const origin = new URL(process.env.PUBLIC_ORIGIN || 'https://media.example.com');
const ca = fs.readFileSync(process.env.ORIGIN_CA_FILE);
const directory = process.env.AGENT_STATE_ROOT;
const engines = new Map();
const blockedUsers = new Set();
const inflight = new Map();
const recovery = new RecoveryGate();
const same = (a, b) => { const x = Buffer.from(String(a || '')), y = Buffer.from(b); return x.length === y.length && crypto.timingSafeEqual(x, y); };

function backend(uid, method, route, body, idempotencyKey) {
  if (!/^\/v1\/(capabilities|health|library|media\/(inspect|analyze)|prompts\/check$|sessions(?:\/|$)|jobs(?:\/|$)|private\/(provider\/(chat|status)|agent\/record))/.test(route)
      || /[\r\n\\]/.test(route)) return Promise.reject(new Error('Ruta no permitida'));
  return new Promise((resolve, reject) => {
    const raw = body === undefined ? undefined : JSON.stringify(body);
    const request = https.request({ hostname: '127.0.0.1', port: Number(process.env.RUNTIME_PORT || 8390),
      servername: origin.hostname, ca, method, path: route,
      headers: { Host: origin.host, 'X-Service-Key': serviceKey, 'X-Owner': uid,
        ...(raw ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(raw) } : {}),
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}) }, timeout: 240000 }, response => {
      let size = 0; const parts = [];
      response.on('data', chunk => { size += chunk.length; if (size > 8 * 1024 * 1024) response.destroy(new Error('Respuesta demasiado grande')); else parts.push(chunk); });
      response.on('error', () => reject(new Error('Conexión al runtime interrumpida')));
      response.on('end', () => {
        if (response.statusCode !== 200 && response.statusCode !== 202) return reject(new Error(`Runtime ${response.statusCode}: ${runtimeDetail(parts)}`));
        try { resolve(JSON.parse(Buffer.concat(parts).toString('utf8'))); } catch { reject(new Error('Respuesta inválida')); }
      });
    });
    request.on('timeout', () => request.destroy());
    request.on('error', () => reject(new Error('Runtime no disponible')));
    request.end(raw);
  });
}

// The runtime's own validation/provider message (already secret-free) so callers can act on it.
function runtimeDetail(parts) {
  try {
    const detail = JSON.parse(Buffer.concat(parts).toString('utf8')).detail;
    const text = typeof detail === 'string' ? detail : JSON.stringify(detail);
    return text && text !== 'undefined' ? text.slice(0, 300) : 'operación rechazada';
  } catch { return 'operación rechazada'; }
}

// Reasons from our own checks, the runtime or the provider; never stack traces or internals.
function publicError(error) {
  const message = String(error?.message || '');
  return /^(Runtime \d{3}:|El proveedor|El modelo|Proveedor|Revisión visual|Prompt inválido|Ruta no permitida|Respuesta)/.test(message)
    ? message.slice(0, 300) : 'Operación no disponible o argumentos inválidos';
}

const REVIEW_TOKENS = 4096;

function jsonReply(reply) {
  const raw = String(reply.content || '').trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
  try { return JSON.parse(raw); } catch { throw new Error('El proveedor no devolvió JSON válido'); }
}

async function engine(uid) {
  if (!/^[a-f0-9]{32}$/.test(uid)) throw new Error('Usuario inválido');
  let item = engines.get(uid);
  if (!item) {
    const runtime = (method, route, body, idempotencyKey) => backend(uid, method, route, body, idempotencyKey);
    const chat = (messages, tools, maxTokens) => runtime('POST', '/v1/private/provider/chat', { messages, tools, maxTokens });
    const inspect = ref => runtime('GET', `/v1/media/inspect?${new URLSearchParams({ uri: ref.uri, sha256: ref.sha256 })}`);
    const director = async payload => {
      const duration = Number(payload.analysis?.duration);
      if (!Number.isFinite(duration) || duration < 5 || duration > 900) throw new Error('Duración inválida');
      const reply = await chat([{ role: 'system', content: directorSystem() }, { role: 'user', content: JSON.stringify(payload) }], null, 8000);
      const parsed = jsonReply(reply);
      if (!Array.isArray(parsed.scenes) || !parsed.scenes.length || parsed.scenes.length > 100) throw new Error('Storyboard inválido');
      return { scenes: parsed.scenes, outbound: payload };
    };
    item = { capabilities: null, runtime, chat, inspect, director, records: new Map() };
    item.engine = new AgentEngine({ directory: path.join(directory, uid), runtime, chat, inspect, director,
      provider: () => item.capabilities, web: true,
      emit: run => {
        if (item.records.get(run.id) === run.status) return;
        item.records.set(run.id, run.status);
        void runtime('POST', '/v1/private/agent/record', { id: run.id, session: run.session, status: run.status }).catch(() => item.records.delete(run.id));
      },
      exporter: async (ref, options) => ({ prepared: true, cancelled: false, download: { media: ref, ...options } }),
      redact: value => value.replace(/Bearer\s+[A-Za-z0-9._~+\/-]+/gi, 'Bearer [omitted]') });
    engines.set(uid, item);
  }
  const configuration = await item.runtime('GET', '/v1/private/provider/status');
  item.capabilities = configuration.configured ? configuration.capabilities : null;
  if (!item.recovered) { item.recovered = true; await item.engine.recover(); }
  recovery.resolved(uid);
  return item;
}

async function readBody(request) {
  const parts = []; let size = 0;
  for await (const chunk of request) { size += chunk.length; if (size > 2 * 1024 * 1024) throw new Error('Solicitud demasiado grande'); parts.push(chunk); }
  return parts.length ? JSON.parse(Buffer.concat(parts).toString('utf8')) : {};
}

const server = http.createServer(async (request, response) => {
  response.setHeader('Content-Type', 'application/json'); response.setHeader('Cache-Control', 'no-store');
  if (!same(request.headers['x-service-key'], serviceKey)) { response.writeHead(403); return response.end('{"error":"denied"}'); }
  if (request.method === 'GET' && request.url === '/active-count') {
    const count = [...engines.values()].reduce((n, item) => n + item.engine.startingSessions.size +
      [...item.engine.runs.values()].filter(r => ['running', 'recovering'].includes(r.status)).length, 0);
    return response.end(JSON.stringify({ count, recoveringAtBoot: recovery.recovering }));
  }
  const uid = request.headers['x-owner'];
  let counted = false;
  try {
    if (!/^[a-f0-9]{32}$/.test(uid || '')) throw new Error('Usuario inválido');
    if (request.method === 'POST' && request.url === '/purge') {
      if (!purgeAccount({uid,directory,engines,blockedUsers,inflight,recovery})) {
        response.writeHead(409); return response.end('{"error":"waiting for active operations"}');
      }
      return response.end('{"ok":true}');
    }
    if (blockedUsers.has(uid)) { response.writeHead(404); return response.end('{"error":"account removed"}'); }
    inflight.set(uid, (inflight.get(uid) || 0) + 1); counted = true;
    if (request.method === 'POST' && request.url === '/disable') {
      const active = engines.get(uid)?.engine;
      if (active) for (const r of active.runs.values()) { r.cancelled = true; r.status = 'cancelled'; active.save(r); }
      else {
        const folder = path.join(directory, uid);
        if (fs.existsSync(folder)) for (const name of fs.readdirSync(folder).filter(n => /^run_[a-f0-9]{24}\.json$/.test(n))) {
          const file = path.join(folder, name), r = JSON.parse(fs.readFileSync(file, 'utf8'));
          r.cancelled = true; r.status = 'cancelled';
          fs.writeFileSync(file + '.tmp', JSON.stringify(r), { mode: 0o600 }); fs.renameSync(file + '.tmp', file);
        }
      }
      return response.end('{"ok":true}');
    }
    const item = await engine(uid), e = item.engine;
    const url = new URL(request.url, 'http://127.0.0.1');
    const body = request.method === 'POST' ? await readBody(request) : {};
    let value;
    if (request.method === 'GET' && url.pathname === '/runs') value = e.get(url.searchParams.get('id'), url.searchParams.get('session'));
    else if (request.method === 'POST' && url.pathname === '/start') value = await e.start(body);
    else if (request.method === 'POST' && url.pathname === '/cancel') value = await e.cancel(body.id, body.jobId);
    else if (request.method === 'POST' && url.pathname === '/continue') value = await e.continue(body.id);
    else if (request.method === 'POST' && url.pathname === '/disable') {
      for (const r of e.runs.values()) { r.cancelled = true; r.status = 'cancelled'; e.save(r); }
      value = { ok: true };
    }
    else if (request.method === 'POST' && url.pathname === '/director') value = await item.director(body);
    else if (request.method === 'POST' && url.pathname === '/improve') {
      const prompt = String(body.prompt || '');
      const references = body.references || [];
      const mode = body.mode || 't2i';
      if (!prompt.trim() || prompt.length > 20000 || !Array.isArray(references) || references.length > 16) throw new Error('Prompt inválido');
      const label = { i2i: i => `Reference <image${i}>${i === 1 ? ' (canvas)' : ''}`, i2v: i => `<Picture ${i}> (${i === 1 ? 'first' : 'last'} frame)`,
        r2v: i => `<Picture ${i}> (reference image ${i})` }[mode] || (i => `Reference image ${i}`);
      let content = [{ type: 'text', text: prompt }];
      for (let index = 0; index < references.length; index++) {
        const inspected = await item.inspect(references[index]);
        content.push({ type: 'text', text: label(index + 1) });
        if (item.capabilities?.vision && inspected.preview) content.push({ type: 'image_url', image_url: { url: `data:${inspected.preview.mime};base64,${inspected.preview.base64}` } });
      }
      const system = improveSystem(mode, { references: references.length, seconds: body.seconds });
      const reply = await item.chat([{ role: 'system', content: system }, { role: 'user', content }], null, improveTokens(mode));
      value = parseImproved(mode, reply.content);
    }
    else if (request.method === 'POST' && url.pathname === '/review') {
      if (!item.capabilities?.vision) throw new Error('Revisión visual no disponible');
      const inspected = await item.inspect(body.media);
      const reply = await item.chat([{ role: 'system', content: reviewSystem() }, { role: 'user', content: [{ type: 'text', text: `${body.prompt}\nAlpha: ${JSON.stringify(inspected.alpha)}` }, { type: 'image_url', image_url: { url: `data:${inspected.preview.mime};base64,${inspected.preview.base64}` } }] }], null, REVIEW_TOKENS);
      const result = jsonReply(reply);
      value = { verdict: String(result.verdict), suggestedPrompt: result.suggested_prompt || null, alpha: inspected.alpha };
    }
    else { response.writeHead(404); return response.end('{"error":"not found"}'); }
    response.end(JSON.stringify(value));
  } catch (error) {
    const status = error.message === 'Idempotency-Key conflict' ? 409 : error.message === 'Ejecución desconocida.' ? 404 : 400;
    response.writeHead(status); response.end(JSON.stringify({ error: publicError(error) }));
  } finally {
    if (counted) { const count = (inflight.get(uid) || 1) - 1; if (count) inflight.set(uid, count); else inflight.delete(uid); }
  }
});
server.requestTimeout = 250000;
server.listen(8392, '127.0.0.1');
// Recover authorized runs on service startup, not only when a browser comes back.
void (async () => {
  try {
    const users = fs.existsSync(directory) ? fs.readdirSync(directory).filter(n => /^[a-f0-9]{32}$/.test(n)) : [];
    recovery.scan(users);
    for (const uid of users) {
      let resolved = false;
      for (let attempt = 0; attempt < 6 && !resolved; attempt++) {
        try { await engine(uid); resolved = true; }
        catch (error) {
          if (/Runtime (401|404):/.test(error.message)) { resolved = true; recovery.resolved(uid); } // Disabled/deleted account, no execution.
          else await new Promise(resolve => setTimeout(resolve, Math.min(16000, 500 * 2 ** attempt)));
        }
      }
    }
  } catch { /* Keep the lifecycle guard closed on filesystem errors. */ }
})();

