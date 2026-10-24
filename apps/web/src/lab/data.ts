import type { ArtifactRef } from '../studio/lib/api'

// Media Lab catalog. Art lives in public/art/lab; "soon" models are on the roadmap, not installed.
export type Modality = 'image' | 'video' | 'audio'
export type Model = { id: string; name: string; maker: string; modality: Modality; blurb: string; tags: string[]; art: string; status: 'ready' | 'new' | 'soon' }
export type Art = { src: string; ratio: number; prompt: string; kind: Modality; model: string; id?: string; ref?: ArtifactRef; created?: number }

export const art = (name: string) => `/art/lab/${name}.webp`

export const models: Model[] = [
  { id: 'qwen-turbo', name: 'Qwen Image 2.1 Turbo', maker: 'Qwen', modality: 'image', blurb: 'Imágenes en segundos, 8 pasos.', tags: ['Rápido', 'Texto nítido'], art: art('model-image'), status: 'ready' },
  { id: 'qwen-quality', name: 'Qwen Image 2.1', maker: 'Qwen', modality: 'image', blurb: 'Máxima calidad, edición con hasta 10 referencias, pose de otra foto y ángulos nuevos.', tags: ['Calidad', 'Edición', 'Ángulos'], art: art('feed-fashion'), status: 'ready' },
  { id: 'moss-image', name: 'MOSS-Image', maker: 'OpenMOSS', modality: 'image', blurb: 'Carteles y composiciones con texto legible dentro de la imagen.', tags: ['Layout', 'Tipografía'], art: art('feed-miniature'), status: 'new' },
  { id: 'flux3-klein', name: 'FLUX 3 Klein', maker: 'Black Forest Labs', modality: 'image', blurb: 'Fotorrealismo rápido: su propio modelo amplía tu idea. Edita y combina hasta 4 fotos.', tags: ['Foto', 'Rápido', 'Edición'], art: art('feed-product'), status: 'new' },
  { id: 'h3', name: 'MiniMax H3', maker: 'MiniMax', modality: 'video', blurb: 'Vídeo con audio: texto, imagen o referencias.', tags: ['Audio', '15 s'], art: art('model-video'), status: 'ready' },
  { id: 'h3-turbo', name: 'H3 Turbo', maker: 'MiniMax · LightX2V', modality: 'video', blurb: 'H3 en 8 pasos con los pesos oficiales: el doble de rápido, también con referencias.', tags: ['Rápido', 'Referencias'], art: art('feed-alley'), status: 'new' },
  { id: 'h3-fused', name: 'H3 Fused Turbo', maker: 'Comunidad', modality: 'video', blurb: 'Fusión experimental en 4 pasos para borradores.', tags: ['Experimental'], art: art('model-director'), status: 'ready' },
  { id: 'fasth3-omni', name: 'FastH3 Omni', maker: 'FastVideo · Nuva Lab', modality: 'video', blurb: 'Vídeo desde tus referencias en 8 pasos: personajes, lugares, voces.', tags: ['Referencias', 'Rápido'], art: art('feed-desert'), status: 'new' },
  { id: 'kandinsky6', name: 'Kandinsky 6', maker: 'Kandinsky Lab', modality: 'video', blurb: 'Clips de 5 s con voz, sonido y labios sincronizados: lo que dicen va entre comillas.', tags: ['Lip-sync', 'Audio', '5 s'], art: art('app-musicvideo'), status: 'new' },
  { id: 'ace-step', name: 'ACE-Step 1.5 XL', maker: 'ACE Studio', modality: 'audio', blurb: 'Una canción completa en un minuto, con la duración exacta.', tags: ['Rápido', 'Español'], art: art('app-cover'), status: 'new' },
  { id: 'yue2', name: 'YuE2 3B', maker: 'M-A-P', modality: 'audio', blurb: 'Canciones completas con voz, covers y partituras.', tags: ['Canción', 'Cover'], art: art('model-music'), status: 'ready' },
  { id: 'qwen3-tts', name: 'Qwen3-TTS', maker: 'Qwen', modality: 'audio', blurb: 'Voz desde texto: 9 voces de estudio, diseña una voz con palabras o clona la tuya (con permiso).', tags: ['Voz', '10 idiomas'], art: art('app-agent'), status: 'new' },
  { id: 'stable-audio3', name: 'Stable Audio 3', maker: 'Stability', modality: 'audio', blurb: 'Música instrumental, loops y efectos de sonido con la duración exacta.', tags: ['SFX', 'Instrumental'], art: art('feed-ocean'), status: 'new' },
]

export const apps = [
  { id: 'cover', title: 'Cover de canción', blurb: 'Tu letra sobre la melodía de otra canción.', art: art('app-cover'), size: 'wide' },
  { id: 'musicvideo', title: 'Videoclip', blurb: 'Canción + escenas = videoclip con el Director.', art: art('app-musicvideo'), size: 'tall' },
  { id: 'character', title: 'Personaje', blurb: 'Un personaje consistente en cada escena.', art: art('app-character'), size: 'square' },
  { id: 'camera', title: 'Movimientos de cámara', blurb: 'Órbitas, travellings y ángulos nuevos.', art: art('app-camera'), size: 'square' },
  { id: 'upscale', title: 'Escalar vídeo', blurb: 'Abre un vídeo de tu biblioteca y pulsa Escalar: más resolución con FlashVSR.', art: art('app-upscale'), size: 'square' },
  { id: 'agent', title: 'Agente', blurb: 'Pídelo en una frase y el agente lo produce.', art: art('app-agent'), size: 'wide' },
] as const

export const feed: Art[] = [
  { src: art('feed-fashion'), ratio: 2 / 3, prompt: 'Editorial de moda bajo la lluvia, abrigo de vinilo con reflejos ember', kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('feed-alley'), ratio: 16 / 9, prompt: 'Callejón futurista lluvioso, charcos con neón cálido', kind: 'video', model: 'MiniMax H3' },
  { src: art('feed-food'), ratio: 1, prompt: 'Ramen humeante con luz lateral cálida', kind: 'image', model: 'Qwen Image 2.1 Turbo' },
  { src: art('feed-anime'), ratio: 2 / 3, prompt: 'Chica con auriculares en una azotea al atardecer, anime', kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('feed-miniature'), ratio: 4 / 3, prompt: 'Ciudad isométrica en miniatura, tilt-shift nocturno', kind: 'image', model: 'Qwen Image 2.1 Turbo' },
  { src: art('feed-ocean'), ratio: 16 / 9, prompt: 'Ballena jorobada atravesada por rayos de luz', kind: 'video', model: 'MiniMax H3' },
  { src: art('feed-product'), ratio: 4 / 5, prompt: 'Perfume ámbar sobre roca volcánica mojada', kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('model-image'), ratio: 4 / 5, prompt: 'Retrato editorial con joyería cromada líquida', kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('feed-desert'), ratio: 16 / 9, prompt: 'Coche clásico en el desierto al anochecer', kind: 'video', model: 'H3 Fused Turbo' },
  { src: art('app-camera'), ratio: 1, prompt: 'Busto de mármol con órbita de luz', kind: 'video', model: 'MiniMax H3' },
  { src: art('model-video'), ratio: 4 / 5, prompt: 'Bailarina en giro con estelas de luz', kind: 'video', model: 'MiniMax H3' },
  { src: art('app-character'), ratio: 1, prompt: 'Hoja de personaje en tres vistas', kind: 'image', model: 'Qwen Image 2.1' },
  { src: art('model-director'), ratio: 4 / 5, prompt: 'Set de rodaje nocturno con grúa y niebla', kind: 'video', model: 'MiniMax H3' },
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
    { id: 'mode', label: 'Modo', options: ['Crear', 'Estructura', 'Ángulo', 'Quitar fondo'] },
    { id: 'guide', label: 'Seguir', options: Object.keys(GUIDES) },
    { id: 'orbit', label: 'Cámara', options: Object.keys(ORBITS) },
    { id: 'height', label: 'Altura', options: Object.keys(HEIGHTS) },
    { id: 'distance', label: 'Distancia', options: Object.keys(DISTANCES) },
    { id: 'aspect', label: 'Formato', options: ['1:1', '4:5', '3:4', '2:3', '9:16', '5:4', '4:3', '3:2', '16:9'] },
    { id: 'quality', label: 'Calidad', options: ['Calidad', 'Borrador'] },
  ],
  video: [
    { id: 'mode', label: 'Modo', options: ['Texto', 'Imagen inicial', 'Referencias', 'Seguir vídeo', 'Cambiar personaje', 'Cambiar cabeza', 'Quitar persona'] },
    { id: 'follow', label: 'Seguir', options: ['Movimiento', 'Bordes', 'Profundidad'] },
    { id: 'engine', label: 'Motor', options: ['H3', 'SCAIL-2'] },
    { id: 'aspect', label: 'Formato', options: ['16:9', '9:16', '1:1'] },
    { id: 'duration', label: 'Duración', options: ['5 s', '10 s', '15 s'] },
    { id: 'resolution', label: 'Resolución', options: ['Vista previa', '480p', '720p', 'Nativa'] },
  ],
  audio: [
    { id: 'type', label: 'Tipo', options: ['Canción', 'Instrumental', 'Cover', 'Separar pistas'] },
    { id: 'stems', label: 'Pistas', options: ['Voz + instrumental', '4 pistas'] },
    { id: 'duration', label: 'Duración', options: ['1:00', '2:00', '3:00'] },
    { id: 'sound', label: 'Sonido', options: Object.keys(SOUND_KINDS) },
    { id: 'length', label: 'Duración', options: SOUND_LENGTHS.music },
    { id: 'voice', label: 'Voz', options: Object.keys(VOICES) },
    { id: 'speaker', label: 'Locutor', options: Object.keys(SPEAKERS) },
    { id: 'language', label: 'Idioma', options: Object.keys(LANGUAGES) },
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
