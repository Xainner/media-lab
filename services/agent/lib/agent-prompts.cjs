/* System prompts for the user's external provider, built from the shared model guides. */
const { modelPromptLanguage, guides } = require('./agent-language.cjs');

// The request describes a song; a weak provider otherwise sings the description itself.
const SONG_RULES = 'The request describes the song you must write: never copy the description into the lyrics or the style. Keep lyrics the user supplied verbatim. If no lyrics are supplied and the song is not instrumental, write original lyrics in the language the idea asks for (otherwise the language of the idea), sized for the stated length. Never reproduce or recall the lyrics of an existing song. Turn artist or song names into the genre, era, production and vocal traits they suggest; never name the artist in the style.';

const IMPROVE = {
  t2i: { guide: 'qwenImage', label: 'Qwen-Image-2.1 text-to-image prompt',
    task: 'Rewrite the request into one Qwen-Image-2.1 text-to-image prompt that follows the guide exactly.' },
  i2i: { guide: 'qwenEdit', label: 'Qwen-Image-2.1 editing instruction',
    task: 'Rewrite the request into one Qwen-Image-2.1 editing instruction that follows the guide exactly. Use <image1>, <image2>… only when two or more references are supplied.' },
  moss: { guide: 'moss', label: 'MOSS-Image caption',
    task: 'Rewrite the request into one finished MOSS-Image caption that follows the guide exactly: English prose in 2–4 paragraphs, layout in reading order, every visible string quoted verbatim with its line breaks.' },
  t2v: { guide: 'h3', label: 'MiniMax H3 T2VA prompt',
    task: 'Rewrite the request into one complete MiniMax H3 Base (T2VA) prompt with the three fields, timed for the stated duration.' },
  i2v: { guide: 'h3', label: 'MiniMax H3 I2VA prompt',
    task: 'Rewrite the request into one H3 Base I2VA prompt that develops forward from the supplied first frame <Picture 1>. Do not write the alignment line; the runtime adds it. If two images are supplied they are the first and last frames (FL2VA): describe the path between them.' },
  r2v: { guide: 'h3', label: 'MiniMax H3 Ref2VA prompt',
    task: 'Rewrite the request into one complete H3 Ref2VA prompt with the six sections. Supplied images are <Picture 1>, <Picture 2>… in order; cite only labels that exist and say so if the request needs a reference that was not supplied.' },
  kandinsky: { guide: 'kandinsky6', label: 'Kandinsky 6 prompt and audio prompt', json: true,
    task: 'Write Kandinsky 6 inputs for one 5-second clip. Return ONLY JSON {"prompt":"English scene in the guide order, spoken words as <S>exact words<E>","audio_prompt":"English voice, sounds, ambience and music"}. Keep spoken words verbatim in their own language; quoted dialogue in the request is spoken. If a first frame is supplied, describe what happens next from it.' },
  song: { guide: 'yue2', label: 'YuE2 style and lyrics', json: true,
    task: `Write YuE2 inputs. Return ONLY JSON {"style":"comma-separated English tags","lyrics":"structured lyrics"}. ${SONG_RULES} For an instrumental use section tags only and add "instrumental, no vocals" to the style.` },
  ace_song: { guide: 'aceStep', label: 'ACE-Step caption, lyrics and metadata', json: true,
    task: `Write ACE-Step 1.5 inputs. Return ONLY JSON {"style":"English caption of at most 500 characters, without BPM or key","lyrics":"structured lyrics","bpm":96,"key":"D major","time_signature":"4","language":"es"}. ${SONG_RULES} For an instrumental the lyrics are exactly "[Instrumental]". language is the two-letter code of the sung language.` },
};

const VIDEO = ['t2v', 'i2v', 'r2v'];

function improveSystem(mode, { references = 0, seconds } = {}) {
  const spec = IMPROVE[mode];
  if (!spec) throw new Error('Modo de prompt no admitido.');
  const context = [`References supplied: ${references}.`];
  if (VIDEO.includes(mode)) context.push(`Requested duration: ${seconds || 5} seconds (use the effective duration table).`);
  return [
    `You propose a ${spec.label} for Media Lab. You never execute tools or generate media.`,
    spec.task,
    spec.json ? '' : 'Return only the final prompt text: no commentary, headings, labels or code fences.',
    'Preserve every explicit requirement, identity, count, literal quoted text, dialogue and lyric exactly; invent only what the user left open.',
    context.join(' '), modelPromptLanguage, guides.language, guides[spec.guide],
  ].filter(Boolean).join('\n\n');
}

const text = value => (typeof value === 'string' ? value.trim() : '');

function parseImproved(mode, content) {
  const raw = String(content || '').trim().replace(/^```(?:json|text)?\s*/i, '').replace(/\s*```$/, '');
  if (!IMPROVE[mode]?.json) return { prompt: raw };
  let value;
  // Tolerate prose or fences around the object; providers often add them.
  try { value = JSON.parse(raw.slice(raw.indexOf('{'), raw.lastIndexOf('}') + 1)); } catch { throw new Error('El proveedor no devolvió JSON válido'); }
  if (mode === 'kandinsky') {
    if (!text(value.prompt)) throw new Error('Respuesta de vídeo incompleta');
    return { prompt: text(value.prompt), audio_prompt: text(value.audio_prompt) };
  }
  if (!text(value.style) || !text(value.lyrics)) throw new Error('Respuesta de canción incompleta');
  const result = { prompt: text(value.style), lyrics: text(value.lyrics) };
  if (mode !== 'ace_song') return result;
  // Metadata the runtime would refuse is dropped; it falls back to its own defaults.
  const bpm = Math.round(Number(value.bpm));
  if (bpm >= 40 && bpm <= 240) result.bpm = bpm;
  if (/^[A-G][#b]? (major|minor)$/.test(text(value.key))) result.key = text(value.key);
  if (['2', '3', '4', '6'].includes(String(value.time_signature))) result.time_signature = String(value.time_signature);
  if (/^[a-z]{2}$/.test(text(value.language))) result.language = text(value.language);
  return result;
}

// Includes room for reasoning models, which count their thinking against max_tokens.
const improveTokens = mode => (VIDEO.includes(mode) ? 6000 : IMPROVE[mode]?.json || mode === 'moss' ? 5000 : 4096);

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
