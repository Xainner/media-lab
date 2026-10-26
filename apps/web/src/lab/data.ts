import type { ArtifactRef } from '../studio/lib/api'
import { t, type MessageKey, type Vars } from '../i18n'

// Media Lab catalog. Art lives in public/art/lab; "soon" models are on the roadmap, not installed.
// Copy is read through getters so it follows the active language; option and tag ids stay in Spanish (see label).
export type Modality = 'image' | 'video' | 'audio'
export type Model = { id: string; name: string; maker: string; modality: Modality; blurb: string; tags: string[]; art: string; status: 'ready' | 'new' | 'soon' }
export type Art = { src: string; ratio: number; prompt: string; kind: Modality; model: string; id?: string; ref?: ArtifactRef; created?: number }

export const art = (name: string) => `/art/lab/${name}.webp`

export const models: Model[] = [
  { id: 'qwen-turbo', name: 'Qwen Image 2.1 Turbo', maker: 'Qwen', modality: 'image', get blurb() { return t('composer.model.qwenTurbo.blurb') }, tags: ['Rápido', 'Texto nítido'], art: art('model-image'), status: 'ready' },
  { id: 'qwen-quality', name: 'Qwen Image 2.1', maker: 'Qwen', modality: 'image', get blurb() { return t('composer.model.qwenQuality.blurb') }, tags: ['Calidad', 'Edición', 'Ángulos'], art: art('feed-fashion'), status: 'ready' },
  { id: 'moss-image', name: 'MOSS-Image', maker: 'OpenMOSS', modality: 'image', get blurb() { return t('composer.model.moss.blurb') }, tags: ['Layout', 'Tipografía'], art: art('feed-miniature'), status: 'new' },
  { id: 'flux3-klein', name: 'FLUX 3 Klein', maker: 'Black Forest Labs', modality: 'image', get blurb() { return t('composer.model.flux3Klein.blurb') }, tags: ['Foto', 'Rápido', 'Edición'], art: art('feed-product'), status: 'new' },
  { id: 'h3', name: 'MiniMax H3', maker: 'MiniMax', modality: 'video', get blurb() { return t('composer.model.h3.blurb') }, tags: ['Audio', '15 s'], art: art('model-video'), status: 'ready' },
  { id: 'h3-turbo', name: 'H3 Turbo', maker: 'MiniMax · LightX2V', modality: 'video', get blurb() { return t('composer.model.h3Turbo.blurb') }, tags: ['Rápido', 'Referencias'], art: art('feed-alley'), status: 'new' },
  { id: 'h3-fused', name: 'H3 Fused Turbo', get maker() { return t('composer.model.makerCommunity') }, modality: 'video', get blurb() { return t('composer.model.h3Fused.blurb') }, tags: ['Experimental'], art: art('model-director'), status: 'ready' },
  { id: 'fasth3-omni', name: 'FastH3 Omni', maker: 'FastVideo · Nuva Lab', modality: 'video', get blurb() { return t('composer.model.fastH3Omni.blurb') }, tags: ['Referencias', 'Rápido'], art: art('feed-desert'), status: 'new' },
  { id: 'kandinsky6', name: 'Kandinsky 6', maker: 'Kandinsky Lab', modality: 'video', get blurb() { return t('composer.model.kandinsky6.blurb') }, tags: ['Lip-sync', 'Audio', '5 s'], art: art('app-musicvideo'), status: 'new' },
  { id: 'ace-step', name: 'ACE-Step 1.5 XL', maker: 'ACE Studio', modality: 'audio', get blurb() { return t('composer.model.aceStep.blurb') }, tags: ['Rápido', 'Español'], art: art('app-cover'), status: 'new' },
  { id: 'yue2', name: 'YuE2 3B', maker: 'M-A-P', modality: 'audio', get blurb() { return t('composer.model.yue2.blurb') }, tags: ['Canción', 'Cover'], art: art('model-music'), status: 'ready' },
  { id: 'qwen3-tts', name: 'Qwen3-TTS', maker: 'Qwen', modality: 'audio', get blurb() { return t('composer.model.qwen3Tts.blurb') }, tags: ['Voz', '10 idiomas'], art: art('app-agent'), status: 'new' },
  { id: 'stable-audio3', name: 'Stable Audio 3', maker: 'Stability', modality: 'audio', get blurb() { return t('composer.model.stableAudio3.blurb') }, tags: ['SFX', 'Instrumental'], art: art('feed-ocean'), status: 'new' },
]

export const apps = [
  { id: 'cover', get title() { return t('composer.app.cover.title') }, get blurb() { return t('composer.app.cover.blurb') }, art: art('app-cover'), size: 'wide' },
  { id: 'musicvideo', get title() { return t('composer.app.musicVideo.title') }, get blurb() { return t('composer.app.musicVideo.blurb') }, art: art('app-musicvideo'), size: 'tall' },
  { id: 'character', get title() { return t('composer.app.character.title') }, get blurb() { return t('composer.app.character.blurb') }, art: art('app-character'), size: 'square' },
  { id: 'camera', get title() { return t('composer.app.camera.title') }, get blurb() { return t('composer.app.camera.blurb') }, art: art('app-camera'), size: 'square' },
  { id: 'upscale', get title() { return t('composer.app.upscale.title') }, get blurb() { return t('composer.app.upscale.blurb') }, art: art('app-upscale'), size: 'square' },
  { id: 'agent', get title() { return t('composer.app.agent.title') }, get blurb() { return t('composer.app.agent.blurb') }, art: art('app-agent'), size: 'wide' },
] as const

export const feed: Art[] = [
  { src: art('feed-fashion'), ratio: 2 / 3, get prompt() { return t('composer.feed.fashion') }, kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('feed-alley'), ratio: 16 / 9, get prompt() { return t('composer.feed.alley') }, kind: 'video', model: 'MiniMax H3' },
  { src: art('feed-food'), ratio: 1, get prompt() { return t('composer.feed.food') }, kind: 'image', model: 'Qwen Image 2.1 Turbo' },
  { src: art('feed-anime'), ratio: 2 / 3, get prompt() { return t('composer.feed.anime') }, kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('feed-miniature'), ratio: 4 / 3, get prompt() { return t('composer.feed.miniature') }, kind: 'image', model: 'Qwen Image 2.1 Turbo' },
  { src: art('feed-ocean'), ratio: 16 / 9, get prompt() { return t('composer.feed.ocean') }, kind: 'video', model: 'MiniMax H3' },
  { src: art('feed-product'), ratio: 4 / 5, get prompt() { return t('composer.feed.product') }, kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('model-image'), ratio: 4 / 5, get prompt() { return t('composer.feed.modelImage') }, kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('feed-desert'), ratio: 16 / 9, get prompt() { return t('composer.feed.desert') }, kind: 'video', model: 'H3 Fused Turbo' },
  { src: art('app-camera'), ratio: 1, get prompt() { return t('composer.feed.appCamera') }, kind: 'video', model: 'MiniMax H3' },
  { src: art('model-video'), ratio: 4 / 5, get prompt() { return t('composer.feed.modelVideo') }, kind: 'video', model: 'MiniMax H3' },
  { src: art('app-character'), ratio: 1, get prompt() { return t('composer.feed.appCharacter') }, kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('model-director'), ratio: 4 / 5, get prompt() { return t('composer.feed.modelDirector') }, kind: 'video', model: 'MiniMax H3' },
]

/** Image structure guides (Qwen Fun ControlNet Union) and camera moves (QMA LoRA), Spanish label → runtime value. */
export const GUIDES: Record<string, 'pose' | 'canny' | 'depth' | 'map'> = { Pose: 'pose', Bordes: 'canny', Profundidad: 'depth', 'Mapa listo': 'map' }
// The first option is each chip's default: quarter views are QMA's most reliable orbit.
export const ORBITS: Record<string, string> = { 'Frente derecha': 'front-right quarter view', 'Frente': 'front view', 'Lado derecho': 'right side view',
  'Atrás derecha': 'back-right quarter view', 'Espalda': 'back view', 'Atrás izquierda': 'back-left quarter view', 'Lado izquierdo': 'left side view', 'Frente izquierda': 'front-left quarter view' }
export const HEIGHTS: Record<string, string> = { 'Altura de ojos': 'eye-level shot', 'Contrapicado': 'low-angle shot', 'Elevada': 'elevated shot', 'Picado': 'high-angle shot' }
export const DISTANCES: Record<string, string> = { 'Plano medio': 'medium shot', 'Primer plano': 'close-up', 'Plano general': 'wide shot' }

/** Stable Audio 3 kinds and the lengths offered for each (exact seconds). */
export const SOUND_KINDS: Record<string, 'music' | 'instrument' | 'sfx' | 'one_shot'> = { Música: 'music', Instrumento: 'instrument', Efecto: 'sfx', Golpe: 'one_shot' }
export const SOUND_LENGTHS: Record<string, string[]> = { music: ['0:30', '1:00', '2:00', '3:00', '6:00'], instrument: ['0:08', '0:15', '0:30', '1:00'],
  sfx: ['3 s', '5 s', '10 s', '30 s'], one_shot: ['1 s', '2 s', '4 s'] }
/** Qwen3-TTS voices, studio speakers and languages, Spanish label → runtime value. */
export const VOICES: Record<string, 'preset' | 'design' | 'clone'> = { 'Voz del estudio': 'preset', 'Diseñar voz': 'design', 'Clonar voz': 'clone' }
export const SPEAKERS: Record<string, string> = { 'Serena (mujer)': 'serena', 'Vivian (mujer)': 'vivian', 'Sohee (mujer)': 'sohee', 'Anna (mujer)': 'ono_anna',
  'Ryan (hombre)': 'ryan', 'Aiden (hombre)': 'aiden', 'Eric (hombre)': 'eric', 'Dylan (hombre)': 'dylan', 'Fu (hombre mayor)': 'uncle_fu' }
export const LANGUAGES: Record<string, string> = { Automático: 'auto', Español: 'spanish', Inglés: 'english', Portugués: 'portuguese', Francés: 'french',
  Alemán: 'german', Italiano: 'italian', Japonés: 'japanese', Coreano: 'korean', Chino: 'chinese', Ruso: 'russian' }
/** Kandinsky 6 makes 5 s clips in these two shapes only. */
export const K6_ASPECTS = ['16:9', '9:16']

type Choice = { id: string; label: string; options: string[] }
export const settings: Record<Modality, Choice[]> = {
  image: [
    { id: 'mode', get label() { return t('composer.setting.mode') }, options: ['Crear', 'Estructura', 'Ángulo', 'Quitar fondo'] },
    { id: 'guide', get label() { return t('composer.setting.guide') }, options: Object.keys(GUIDES) },
    { id: 'orbit', get label() { return t('composer.setting.orbit') }, options: Object.keys(ORBITS) },
    { id: 'height', get label() { return t('composer.setting.height') }, options: Object.keys(HEIGHTS) },
    { id: 'distance', get label() { return t('composer.setting.distance') }, options: Object.keys(DISTANCES) },
    { id: 'aspect', get label() { return t('composer.setting.aspect') }, options: ['1:1', '4:5', '3:4', '2:3', '9:16', '5:4', '4:3', '3:2', '16:9'] },
    { id: 'quality', get label() { return t('composer.setting.quality') }, options: ['Calidad', 'Borrador'] },
  ],
  video: [
    { id: 'mode', get label() { return t('composer.setting.mode') }, options: ['Texto', 'Imagen inicial', 'Referencias', 'Seguir vídeo', 'Cambiar personaje', 'Cambiar cabeza', 'Quitar persona', 'Escalar'] },
    { id: 'follow', get label() { return t('composer.setting.follow') }, options: ['Movimiento', 'Bordes', 'Profundidad'] },
    { id: 'engine', get label() { return t('composer.setting.engine') }, options: ['H3', 'SCAIL-2'] },
    { id: 'aspect', get label() { return t('composer.setting.aspect') }, options: ['16:9', '9:16', '1:1'] },
    { id: 'duration', get label() { return t('composer.setting.duration') }, options: ['5 s', '10 s', '15 s'] },
    { id: 'resolution', get label() { return t('composer.setting.resolution') }, options: ['Vista previa', '480p', '720p', 'Nativa'] },
    { id: 'scale', get label() { return t('composer.setting.scale') }, options: ['×2', '×4'] },
    { id: 'finish', get label() { return t('composer.setting.finish') }, options: ['Rápido', 'Calidad'] },
  ],
  audio: [
    { id: 'type', get label() { return t('composer.setting.type') }, options: ['Canción', 'Instrumental', 'Cover', 'Separar pistas'] },
    { id: 'stems', get label() { return t('composer.setting.stems') }, options: ['Voz + instrumental', '4 pistas'] },
    { id: 'duration', get label() { return t('composer.setting.duration') }, options: ['1:00', '2:00', '3:00'] },
    { id: 'sound', get label() { return t('composer.setting.sound') }, options: Object.keys(SOUND_KINDS) },
    { id: 'length', get label() { return t('composer.setting.length') }, options: SOUND_LENGTHS.music },
    { id: 'voice', get label() { return t('composer.setting.voice') }, options: Object.keys(VOICES) },
    { id: 'speaker', get label() { return t('composer.setting.speaker') }, options: Object.keys(SPEAKERS) },
    { id: 'language', get label() { return t('composer.setting.language') }, options: Object.keys(LANGUAGES) },
  ],
}

/** The preset ratio closest to an image's shape. */
export const nearestAspect = (width: number, height: number) =>
  settings.image.find(c => c.id === 'aspect')!.options.reduce((best, o) => Math.abs(Math.log(ratioOf(o) * height / width)) < Math.abs(Math.log(ratioOf(best) * height / width)) ? o : best)

/** What a followed clip passes on to the new one (H3 Fun ControlNet-Union). */
export const FOLLOWS: Record<string, 'pose' | 'canny' | 'depth'> = { Movimiento: 'pose', Bordes: 'canny', Profundidad: 'depth' }

/** Video modes that edit a source clip instead of generating from a prompt. */
export const SWAP_MODES: Record<string, 'character' | 'head' | 'remove'> = { 'Cambiar personaje': 'character', 'Cambiar cabeza': 'head', 'Quitar persona': 'remove' }

export const ratioOf = (aspect: string) => { const [w, h] = aspect.split(':').map(Number); return w && h ? w / h : 1 }

/** H3 output sizes (options.resolution). Vista previa is the fast default: 640×352 at 16:9. */
export const RESOLUTIONS: Record<string, string> = { 'Vista previa': 'preview', '480p': '480p', '720p': '720p', 'Nativa': 'native' }

/** Options and tags keep their Spanish ids (state, runtime maps); this is only how they are shown. Unknown ids show as is. */
const LABELS: Record<string, MessageKey | [MessageKey, Vars]> = {
  Crear: 'composer.option.create', Estructura: 'composer.option.structure', Ángulo: 'composer.option.angle', 'Quitar fondo': 'composer.option.removeBackground',
  Bordes: 'composer.option.edges', Profundidad: 'composer.option.depth', 'Mapa listo': 'composer.option.readyMap',
  'Frente derecha': 'composer.option.frontRight', Frente: 'composer.option.front', 'Lado derecho': 'composer.option.rightSide', 'Atrás derecha': 'composer.option.backRight',
  Espalda: 'composer.option.back', 'Atrás izquierda': 'composer.option.backLeft', 'Lado izquierdo': 'composer.option.leftSide', 'Frente izquierda': 'composer.option.frontLeft',
  'Altura de ojos': 'composer.option.eyeLevel', Contrapicado: 'composer.option.lowAngle', Elevada: 'composer.option.elevated', Picado: 'composer.option.highAngle',
  'Plano medio': 'composer.option.mediumShot', 'Primer plano': 'composer.option.closeUp', 'Plano general': 'composer.option.wideShot',
  Calidad: 'composer.option.quality', Borrador: 'composer.option.draft', Texto: 'composer.option.text', 'Imagen inicial': 'composer.option.startImage',
  Referencias: 'composer.option.references', 'Seguir vídeo': 'composer.option.followVideo', 'Cambiar personaje': 'composer.option.swapCharacter',
  'Cambiar cabeza': 'composer.option.swapHead', 'Quitar persona': 'composer.option.removePerson', Escalar: 'composer.option.upscale', Movimiento: 'composer.option.motion',
  'Vista previa': 'composer.option.preview', Nativa: 'composer.option.native', Rápido: 'composer.option.fast',
  Canción: 'composer.option.song', 'Separar pistas': 'composer.option.splitStems', 'Voz + instrumental': 'composer.option.vocalsInstrumental', '4 pistas': 'composer.option.fourStems',
  Música: 'composer.option.music', Instrumento: 'composer.option.instrument', Efecto: 'composer.option.effect', Golpe: 'composer.option.oneShot',
  'Voz del estudio': 'composer.option.studioVoice', 'Diseñar voz': 'composer.option.designVoice', 'Clonar voz': 'composer.option.cloneVoice',
  'Serena (mujer)': ['composer.option.speakerFemale', { name: 'Serena' }], 'Vivian (mujer)': ['composer.option.speakerFemale', { name: 'Vivian' }],
  'Sohee (mujer)': ['composer.option.speakerFemale', { name: 'Sohee' }], 'Anna (mujer)': ['composer.option.speakerFemale', { name: 'Anna' }],
  'Ryan (hombre)': ['composer.option.speakerMale', { name: 'Ryan' }], 'Aiden (hombre)': ['composer.option.speakerMale', { name: 'Aiden' }],
  'Eric (hombre)': ['composer.option.speakerMale', { name: 'Eric' }], 'Dylan (hombre)': ['composer.option.speakerMale', { name: 'Dylan' }],
  'Fu (hombre mayor)': ['composer.option.speakerOlderMale', { name: 'Fu' }],
  Automático: 'composer.option.auto', Español: 'composer.language.spanish', Inglés: 'composer.language.english', Portugués: 'composer.language.portuguese',
  Francés: 'composer.language.french', Alemán: 'composer.language.german', Italiano: 'composer.language.italian', Japonés: 'composer.language.japanese',
  Coreano: 'composer.language.korean', Chino: 'composer.language.chinese', Ruso: 'composer.language.russian',
  'Texto nítido': 'composer.tag.sharpText', Edición: 'composer.tag.editing', Ángulos: 'composer.tag.angles', Tipografía: 'composer.tag.typography',
  Foto: 'composer.tag.photo', Voz: 'composer.tag.voice', '10 idiomas': 'composer.tag.tenLanguages',
}
export const label = (id: string) => { const l = LABELS[id]; return !l ? id : typeof l === 'string' ? t(l) : t(l[0], l[1]) }
