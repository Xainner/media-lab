import { afterEach, expect, test, vi } from 'vitest'
import { droppedKind, improve, mentioned, operations, requests, speechTags, withCharacters, type Submission } from './live'

const ref = { uri: 'artifact://s/images/a.png', sha256: 'a' }
const base = (patch: Partial<Submission>): Submission => ({ kind: 'image', prompt: 'un faro', modelId: 'qwen-quality', values: { aspect: '1:1', quality: 'Calidad' }, count: 1, refs: [], ...patch })
afterEach(() => { vi.unstubAllGlobals() })

test('images fan out per copy and switch to edit when references are attached', () => {
  expect(requests(base({ count: 3 })).map(r => r.path)).toEqual(['/v1/jobs/generate', '/v1/jobs/generate', '/v1/jobs/generate'])
  const [edit] = requests(base({ refs: [ref], modelId: 'qwen-turbo' }))
  expect(edit.path).toBe('/v1/jobs/edit')
  expect(edit.body).toMatchObject({ references: [ref], model_variant: 'turbo' })
})

test('swap modes send the source clip and one image to the swap job, never through the IA pass', async () => {
  const clip = { uri: 'artifact://s/sources/clip.mp4', sha256: 'c' }
  const swap = (mode: string) => base({ kind: 'video', prompt: 'the dancer', values: { mode, aspect: '16:9', duration: '5 s' }, refs: [ref], source: clip })
  const [character] = requests(swap('Cambiar personaje'))
  expect(character).toMatchObject({ path: '/v1/jobs/swap', operation: 'swap', body: { mode: 'character', video: clip, character: ref, target: 'the dancer' } })
  expect(requests(swap('Cambiar cabeza'))[0].body.mode).toBe('head')
  vi.stubGlobal('visualLab', { agent: { improve: async () => { throw new Error('no') } } })
  expect(await improve(swap('Cambiar cabeza'))).toMatchObject({ prompt: 'the dancer' })
})

test('structure guides create a new image that follows one photo', async () => {
  const guided = base({ refs: [ref], count: 2, values: { mode: 'Estructura', guide: 'Pose', aspect: '3:4', quality: 'Calidad' } })
  const list = requests(guided)
  expect(list).toHaveLength(2)
  expect(list[0]).toMatchObject({ path: '/v1/jobs/generate', body: { aspect_ratio: '3:4', control: { reference: ref, mode: 'pose' } } })
  expect(requests({ ...guided, values: { ...guided.values, guide: 'Mapa listo' } })[0].body.control.mode).toBe('map')
  const improveSpy = vi.fn(async () => ({ prompt: 'better' }))
  vi.stubGlobal('visualLab', { agent: { improve: improveSpy } })
  await improve(guided)
  expect(improveSpy).toHaveBeenCalledWith('un faro', 't2i', [], undefined)
})

test('angle re-shoots send one photo and the QMA camera, never through the IA pass', async () => {
  const shot = base({ prompt: '', refs: [ref], values: { mode: 'Ángulo', orbit: 'Espalda', height: 'Picado', distance: 'Primer plano' } })
  const [edit] = requests(shot)
  expect(edit).toMatchObject({ path: '/v1/jobs/edit', body: { prompt: '', references: [ref], resolution: 1024,
    camera: { azimuth: 'back view', elevation: 'high-angle shot', distance: 'close-up' } } })
  expect(edit.body.model_variant).toBeUndefined()
  vi.stubGlobal('visualLab', { agent: { improve: async () => { throw new Error('no') } } })
  expect(await improve(shot)).toBe(shot)
})

test('video model cards pick their H3 profile', () => {
  const video = (modelId: string) => requests(base({ kind: 'video', modelId, values: { mode: 'Texto', aspect: '16:9', duration: '5 s' } }))[0].body.profile
  expect(['h3', 'h3-turbo', 'h3-fused', 'fasth3-omni'].map(video)).toEqual(['base', 'turbo', 'fused_turbo', 'omni'])
})

test('removing a person sends the clip, who to erase and an optional clean frame', () => {
  const clip = { uri: 'artifact://s/videos/clip.mp4', sha256: 'c' }
  const remove = (refs: typeof ref[]) => requests(base({ kind: 'video', prompt: 'man in yellow hoodie', values: { mode: 'Quitar persona' }, refs, source: clip }))[0]
  expect(remove([])).toMatchObject({ path: '/v1/jobs/remove', operation: 'remove', body: { video: clip, target: 'man in yellow hoodie', clean_frame: null } })
  expect(remove([ref]).body.clean_frame).toEqual(ref)
})

test('splitting a song sends it with two or four stems', () => {
  const song = { uri: 'artifact://s/songs/a.flac', sha256: 's' }
  const split = (stems: string) => requests(base({ kind: 'audio', prompt: '', values: { type: 'Separar pistas', stems }, source: song }))
  expect(split('Voz + instrumental')).toEqual([{ path: '/v1/jobs/stems', operation: 'stems', body: { audio: song, stems: 'two', session_id: expect.any(String) } }])
  expect(split('4 pistas')[0].body.stems).toBe('four')
})

test('removing a background is one fixed edit of the first photo', () => {
  const second = { uri: 'artifact://s/images/b.png', sha256: 'b' }
  expect(requests(base({ values: { mode: 'Quitar fondo' }, refs: [ref, second], count: 3 }))).toEqual([{ path: '/v1/jobs/edit', operation: 'edit',
    body: { prompt: '', references: [ref], remove_background: true, session_id: expect.any(String) } }])
})

test('following a clip sends it as H3 control in r2v with optional references', () => {
  const clip = { uri: 'artifact://s/videos/dance.mp4', sha256: 'd' }
  const [job] = requests(base({ kind: 'video', modelId: 'h3-turbo', prompt: 'she dances on a rooftop', values: { mode: 'Seguir vídeo', follow: 'Bordes', aspect: '16:9', duration: '5 s' }, refs: [ref], source: clip }))
  expect(job.body).toMatchObject({ mode: 'r2v', references: [ref], profile: 'turbo', control: { video: clip, mode: 'canny', keep_audio: true } })
})

test('the SCAIL-2 engine turns a character swap into mode scail', () => {
  const clip = { uri: 'artifact://s/videos/clip.mp4', sha256: 'c' }
  const swap = (engine: string) => requests(base({ kind: 'video', prompt: 'the man', values: { mode: 'Cambiar personaje', engine }, refs: [ref], source: clip }))[0].body.mode
  expect([swap('H3'), swap('SCAIL-2')]).toEqual(['character', 'scail'])
})

test('the resolution chip sets H3 options.resolution and leaves preview implicit', () => {
  const video = (resolution: string) => requests(base({ kind: 'video', prompt: 'a fox', values: { mode: 'Texto', aspect: '16:9', duration: '5 s', resolution } }))[0].body
  expect(video('Vista previa')).not.toHaveProperty('options')
  expect(video('720p').options).toEqual({ resolution: '720p' })
  expect(video('Nativa').options).toEqual({ resolution: 'native' })
})

test('MOSS-Image creates with its own model and never edits', () => {
  const [moss] = requests(base({ modelId: 'moss-image', values: { aspect: '16:9', quality: 'Borrador' } }))
  expect(moss).toMatchObject({ path: '/v1/jobs/generate', body: { model: 'moss', aspect_ratio: '16:9', quality: 'draft' } })
  expect(moss.body.model_variant).toBeUndefined()
})

test('ACE-Step songs ask for the exact length and covers stay on YuE2', () => {
  const song = (type: string) => base({ kind: 'audio', modelId: 'ace-step', prompt: 'cumbia, 100 BPM', lyrics: '[verse] hola', values: { type, duration: '2:00' } })
  expect(requests(song('Canción'))[0].body).toMatchObject({ model: 'ace_step', style: 'cumbia, 100 BPM', lyrics: '[verse] hola', max_duration: 120 })
  expect(requests(song('Instrumental'))[0].body.lyrics).toBe('[Instrumental]')
  expect(requests(song('Cover'))[0].body.model).toBeUndefined()
})

test('the IA pass uses the guide that matches each creator mode', async () => {
  const calls: any[] = []
  vi.stubGlobal('visualLab', { agent: { improve: async (...args: any[]) => {
    calls.push(args)
    return args[1] === 'ace_song' ? { prompt: 'cumbia, accordion', lyrics: '[Verse]\nlunes', bpm: 98, key: 'A minor', language: 'es' }
      : args[1] === 'song' ? { prompt: 'pop, warm', lyrics: '[verse] hola' } : args[1] === 'kandinsky' ? { prompt: 'A vendor says: <S>¡Hola!<E>', audio_prompt: 'warm voice; no music' }
      : { prompt: 'mejorado' } } } })
  expect((await improve(base({ refs: [ref] }))).prompt).toBe('mejorado')
  await improve(base({ kind: 'video', values: { mode: 'Imagen inicial', duration: '0:08', aspect: '16:9' }, refs: [ref, ref] }))
  const song = await improve(base({ kind: 'audio', values: { type: 'Canción', duration: '1:00' }, lyrics: 'mi letra' }))
  const cover = await improve(base({ kind: 'audio', values: { type: 'Cover', duration: '1:00' } }))
  await improve(base({ modelId: 'moss-image' }))
  await improve(base({ modelId: 'moss-image', refs: [ref], values: { mode: 'Estructura' } }))
  const ace = await improve(base({ kind: 'audio', modelId: 'ace-step', prompt: 'una cumbia sobre el lunes', values: { type: 'Canción', duration: '2:00' } }))
  await improve(base({ kind: 'video', modelId: 'h3-turbo', values: { mode: 'Referencias', duration: '0:05', aspect: '16:9' }, refs: [ref] }))
  const k6 = await improve(base({ kind: 'video', modelId: 'kandinsky6', prompt: 'una vendedora dice "hola"', values: { mode: 'Imagen inicial', aspect: '16:9' }, refs: [ref] }))
  // FLUX, Stable Audio and the voice rewrite or read the text themselves.
  for (const [modelId, kind] of [['flux3-klein', 'image'], ['stable-audio3', 'audio'], ['qwen3-tts', 'audio']] as const) expect((await improve(base({ modelId, kind, refs: kind === 'image' ? [ref] : [] }))).prompt).toBe('un faro')
  expect(calls.map(c => c[1])).toEqual(['i2i', 'i2v', 'song', 'moss', 't2i', 'ace_song', 'r2v', 'kandinsky'])
  expect(calls[1][2]).toEqual([ref])
  expect(calls[1][3]).toBe(8)
  expect(calls[2][0]).toContain('mi letra')
  // The first box is the idea, never lyrics; with no lyrics the provider is told to write them.
  expect(calls[5][0]).toMatch(/^Song idea \(a description of the song, not lyrics\): una cumbia sobre el lunes/)
  expect(calls[5][0]).toContain('No lyrics supplied')
  expect(calls[5][0]).toContain('2:00 (exact)')
  expect(requests(ace)[0].body).toMatchObject({ model: 'ace_step', style: 'cumbia, accordion', lyrics: '[Verse]\nlunes', bpm: 98, key: 'A minor', language: 'es', max_duration: 120 })
  expect(calls[7][2]).toEqual([ref])
  expect(k6).toMatchObject({ prompt: 'A vendor says: <S>¡Hola!<E>', lyrics: 'warm voice; no music' })
  expect(requests(k6)[0].body).toMatchObject({ prompt: 'A vendor says: <S>¡Hola!<E>', audio_prompt: 'warm voice; no music' })
  expect(song).toMatchObject({ prompt: 'pop, warm', lyrics: '[verse] hola' })
  expect(song.music).toBeUndefined()
  expect(cover.prompt).toBe('un faro')
})

const ana = { id: 'char_a', handle: 'ana', name: 'Ana', description: 'woman with curly hair',
  references: [{ uri: 'artifact://s/references/ana1.png', sha256: 'n1' }, { uri: 'artifact://s/references/ana2.png', sha256: 'n2' }],
  lora: { id: 'lora_qwen', name: 'Ana style', base: 'qwen' as const, trigger: 'zxc', strength: 1, status: 'ready' } }

test('@handle brings the character images in as numbered references and its LoRA when the model matches', () => {
  const edit = withCharacters(base({ prompt: '@ana en la playa junto a <image1>', refs: [ref] }), [ana])
  expect(edit.refs).toEqual([ref, ...ana.references])
  expect(edit.prompt).toBe('<image2> (woman with curly hair) en la playa junto a <image1>')
  expect(edit.loras).toEqual([{ id: 'lora_qwen' }])
  expect(requests(edit)[0].body).toMatchObject({ references: [ref, ...ana.references], loras: [{ id: 'lora_qwen' }] })
  const clip = withCharacters(base({ kind: 'video', prompt: '@ana baila', values: { mode: 'Texto', aspect: '16:9', duration: '5 s' } }), [ana])
  expect(clip).toMatchObject({ prompt: '<Picture 1> (woman with curly hair) baila', values: { mode: 'Referencias' }, loras: [] })
  expect(requests(clip)[0].body).toMatchObject({ mode: 'r2v', references: ana.references })
  expect(mentioned('hola @anabel y @ana', [ana])).toEqual([ana])
})

test('a swap takes the mentioned character as its image and LoRAs only reach jobs that take them', () => {
  const source = { uri: 'artifact://s/videos/clip.mp4', sha256: 'c' }
  const swap = withCharacters(base({ kind: 'video', prompt: '@ana por el chico de rojo', values: { mode: 'Cambiar personaje' }, source }), [ana])
  expect(swap).toMatchObject({ refs: [ana.references[0]], prompt: 'por el chico de rojo', loras: [] })
  expect(requests(swap)[0].body).not.toHaveProperty('loras')
  const moss = withCharacters(base({ prompt: 'póster de @ana', modelId: 'moss-image', loras: [{ id: 'lora_qwen' }] }), [ana])
  expect(moss).toMatchObject({ prompt: 'póster de woman with curly hair', refs: [], loras: [] })
  expect(requests(base({ loras: [{ id: 'lora_x', strength: 0.6 }] }))[0].body.loras).toEqual([{ id: 'lora_x', strength: 0.6 }])
})

const REF = { uri: 'artifact://images/a.png', sha256: 'a'.repeat(64) }

test('FLUX 3 Klein creates from text and edits up to four photos', () => {
  const create = requests(base({ modelId: 'flux3-klein', values: { aspect: '16:9', quality: 'Borrador' } }))[0]
  expect(create.path).toBe('/v1/jobs/generate')
  expect(create.body).toMatchObject({ model: 'flux3', aspect_ratio: '16:9', quality: 'draft' })
  const edit = requests(base({ modelId: 'flux3-klein', refs: [REF, REF, REF, REF, REF] }))[0]
  expect(edit.path).toBe('/v1/jobs/edit')
  expect(edit.body.model).toBe('flux3')
  expect(edit.body.references).toHaveLength(4)
  expect(edit.body).not.toHaveProperty('loras')
})

test('Kandinsky turns quoted dialogue into speech marks and sends the sounds apart', () => {
  expect(speechTags('Ella dice «Hola, amigo» y sonríe')).toBe('Ella dice <S>Hola, amigo<E> y sonríe')
  expect(speechTags('Ya marcado <S>sí<E> y "no"')).toBe('Ya marcado <S>sí<E> y "no"')
  const body = requests(base({ kind: 'video', modelId: 'kandinsky6', prompt: 'Un hombre dice "buenas noches"', lyrics: 'voz grave, lluvia',
    values: { mode: 'Imagen inicial', aspect: '9:16' }, refs: [REF] }))[0].body
  expect(body).toMatchObject({ model: 'kandinsky6', mode: 'i2v', first_frame: REF, aspect_ratio: '9:16', seconds: 5, audio_prompt: 'voz grave, lluvia' })
  expect(body.prompt).toBe('Un hombre dice <S>buenas noches<E>')
})

test('Stable Audio and Qwen3-TTS map the audio chips', () => {
  const sound = requests(base({ kind: 'audio', modelId: 'stable-audio3', prompt: 'lluvia en un techo de lámina', values: { sound: 'Efecto', length: '10 s' } }))[0]
  expect(sound).toMatchObject({ path: '/v1/jobs/sound', body: { kind: 'sfx', seconds: 10 } })
  const preset = requests(base({ kind: 'audio', modelId: 'qwen3-tts', prompt: 'Hola', lyrics: 'susurrando', values: { voice: 'Voz del estudio', speaker: 'Ryan (hombre)', language: 'Español' } }))[0]
  expect(preset).toMatchObject({ path: '/v1/jobs/speech', body: { voice: 'preset', speaker: 'ryan', instruct: 'susurrando', language: 'spanish' } })
  const clone = requests(base({ kind: 'audio', modelId: 'qwen3-tts', prompt: 'Hola', source: REF, consent: true, values: { voice: 'Clonar voz', language: 'Automático' } }))[0].body
  expect(clone).toMatchObject({ voice: 'clone', reference: REF, consent: true, language: 'auto' })
  expect(clone).not.toHaveProperty('speaker')
})

test('dropped files go to references or to the audio/video source by type, with or without a browser MIME type', () => {
  const file = (name: string, type = '') => new File(['x'], name, { type })
  expect(droppedKind(file('a.png', 'image/png'))).toBe('image')
  expect(droppedKind(file('foto.JPG'))).toBe('image')
  expect(droppedKind(file('song.mp3', 'audio/mpeg'))).toBe('media')
  expect(droppedKind(file('voz.wav', 'audio/x-wav'))).toBe('media')
  expect(droppedKind(file('clip.mkv'))).toBe('media')
  expect(droppedKind(file('notes.pdf', 'application/pdf'))).toBeNull()
})

test('the Escalar mode sends the source clip to FlashVSR, never through the IA pass', async () => {
  const clip = { uri: 'artifact://s/videos/clip.mp4', sha256: 'c' }
  const up = (values: Record<string, string>) => base({ kind: 'video', prompt: '', modelId: 'kandinsky6', values: { mode: 'Escalar', ...values }, source: clip })
  expect(requests(up({}))).toEqual([{ path: '/v1/jobs/upscale', operation: 'upscale', body: expect.objectContaining({ video: clip, scale: 2, quality: 'fast' }) }])
  expect(requests(up({ scale: '×4', finish: 'Calidad' }))[0].body).toMatchObject({ scale: 4, quality: 'quality' })
  // Reloading the video view must keep listing (and following) upscale jobs.
  expect(operations.video).toContain('upscale')
  vi.stubGlobal('visualLab', { agent: { improve: async () => { throw new Error('no') } } })
  expect(await improve(up({}))).toMatchObject({ prompt: '' })
})
