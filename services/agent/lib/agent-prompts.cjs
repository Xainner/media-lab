/* System prompts for the user's external provider, built from the shared model guides. */
const { modelPromptLanguage, guides } = require('./agent-language.cjs');

const IMPROVE = {
  t2i: { guide: 'qwenImage', label: 'Qwen-Image-2.1 text-to-image prompt',
    task: 'Rewrite the request into one Qwen-Image-2.1 text-to-image prompt that follows the guide exactly.' },
  i2i: { guide: 'qwenEdit', label: 'Qwen-Image-2.1 editing instruction',
    task: 'Rewrite the request into one Qwen-Image-2.1 editing instruction that follows the guide exactly. Use <image1>, <image2>… only when two or more references are supplied.' },
  t2v: { guide: 'h3', label: 'MiniMax H3 T2VA prompt',
    task: 'Rewrite the request into one complete MiniMax H3 Base (T2VA) prompt with the three fields, timed for the stated duration.' },
  i2v: { guide: 'h3', label: 'MiniMax H3 I2VA prompt',
    task: 'Rewrite the request into one H3 Base I2VA prompt that develops forward from the supplied first frame <Picture 1>. Do not write the alignment line; the runtime adds it. If two images are supplied they are the first and last frames (FL2VA): describe the path between them.' },
  r2v: { guide: 'h3', label: 'MiniMax H3 Ref2VA prompt',
    task: 'Rewrite the request into one complete H3 Ref2VA prompt with the six sections. Supplied images are <Picture 1>, <Picture 2>… in order; cite only labels that exist and say so if the request needs a reference that was not supplied.' },
  song: { guide: 'yue2', label: 'YuE2 style and lyrics',
    task: 'Write YuE2 inputs. Return ONLY JSON {"style":"comma-separated English tags","lyrics":"structured lyrics"}. Keep lyrics the user supplied verbatim. For a vocal song without supplied lyrics write original lyrics in the requested language; never reproduce or recall the lyrics of an existing song. For an instrumental use section tags only and add "instrumental, no vocals" to the style.' },
};

function improveSystem(mode, { references = 0, seconds } = {}) {
  const spec = IMPROVE[mode];
  if (!spec) throw new Error('Modo de prompt no admitido.');
  const context = [`References supplied: ${references}.`];
  if (['t2v', 'i2v', 'r2v'].includes(mode)) context.push(`Requested duration: ${seconds || 5} seconds (use the effective duration table).`);
  return [
    `You propose a ${spec.label} for Media Lab. You never execute tools or generate media.`,
    spec.task,
    mode === 'song' ? '' : 'Return only the final prompt text: no commentary, headings, labels or code fences.',
    'Preserve every explicit requirement, identity, count, literal quoted text, dialogue and lyric exactly; invent only what the user left open.',
    context.join(' '), modelPromptLanguage, guides.language, guides[spec.guide],
  ].filter(Boolean).join('\n\n');
}

function parseImproved(mode, content) {
  const raw = String(content || '').trim().replace(/^```(?:json|text)?\s*/i, '').replace(/\s*```$/, '');
  if (mode !== 'song') return { prompt: raw };
  let value;
  // Tolerate prose or fences around the object; providers often add them.
  try { value = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1)); } catch { throw new Error('El proveedor no devolvió JSON válido'); }
  if (typeof value.style !== 'string' || typeof value.lyrics !== 'string' || !value.style.trim() || !value.lyrics.trim()) throw new Error('Respuesta de canción incompleta');
  return { prompt: value.style.trim(), lyrics: value.lyrics.trim() };
}

// Includes room for reasoning models, which count their thinking against max_tokens.
const improveTokens = mode => (['t2v', 'i2v', 'r2v'].includes(mode) ? 6000 : mode === 'song' ? 5000 : 4096);

function directorSystem() {
  return [
    'You are the director of a music video rendered with Qwen-Image-2.1 keyframes and MiniMax H3 clips.',
    'Return ONLY valid JSON: {"scenes":[{"start":0,"end":5,"image_prompt":"...","video_prompt":"..."}]}.',
    'Cover the entire supplied duration with contiguous scenes of more than 0 and at most 15 seconds; only the final scene may be shorter than 5 seconds. Cut on the supplied musical sections.',
    'Each image_prompt is a complete Qwen-Image-2.1 observer paragraph; each video_prompt is a complete H3 Base I2VA prompt (three fields) starting from that keyframe, with non_diegetic_music: N/A.',
    'Only when the brief asks for a visible singer to lip-sync, add "lip_sync": true to that scene (at least 2 seconds) and write its video_prompt as the six-section Ref2VA lip-sync prompt from the guide.',
    'The original song is the soundtrack. Audio analysis is technical metadata only; never claim you heard the song.',
    modelPromptLanguage, guides.director, guides.qwenImage, guides.h3,
  ].join('\n\n');
}

function reviewSystem() {
  return [
    'Factually review the image against the request. Return ONLY JSON {"verdict":"concise review","suggested_prompt":null}.',
    'If a material correction is needed, set suggested_prompt to a complete prompt that follows the guide below; never execute it. Consider the supplied alpha statistics for transparency.',
    modelPromptLanguage, guides.qwenImage,
  ].join('\n\n');
}

module.exports = { improveSystem, parseImproved, improveTokens, directorSystem, reviewSystem, IMPROVE };
