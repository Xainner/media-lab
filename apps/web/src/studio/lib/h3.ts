import { useEffect, useState } from 'react'
import { runtime } from './api'

export type H3Profile = 'base' | 'fused_turbo' | 'turbo'
type Profile = { ready: boolean; steps: { min: number; max: number; default: number } }
const defaults: Record<H3Profile, Profile> = {
  base: { ready: true, steps: { min: 8, max: 40, default: 20 } },
  fused_turbo: { ready: false, steps: { min: 4, max: 12, default: 4 } },
  turbo: { ready: false, steps: { min: 4, max: 12, default: 8 } },
}

export function useH3Profile() {
  const [profiles, setProfiles] = useState(defaults)
  const [profile, setProfile] = useState<H3Profile>('base')
  const [steps, setSteps] = useState(20)
  useEffect(() => {
    let active = true
    void runtime('GET', '/v1/capabilities').then(caps => {
      if (active && caps.video?.profiles) setProfiles(Object.fromEntries((Object.keys(defaults) as H3Profile[]).map(id =>
        [id, { ...defaults[id], ...caps.video.profiles[id], steps: { ...defaults[id].steps, ...caps.video.profiles[id]?.steps } }])) as Record<H3Profile, Profile>)
    }).catch(() => {})
    return () => { active = false }
  }, [])
  const limits = profiles[profile].steps
  function select(value: string) {
    if (!(value in defaults)) return
    const id = value as H3Profile
    if (!profiles[id].ready) return
    setProfile(id); setSteps(profiles[id].steps.default)
  }
  return { profile, steps, setSteps, select, profiles, limits,
    valid: profiles[profile].ready && Number.isInteger(steps) && steps >= limits.min && steps <= limits.max }
}

/** Usage notes per profile, mirrored from the model guide (section 1b). */
export const H3_PROFILE_HELP: Record<H3Profile, string> = {
  base: 'Recomendado para el resultado final: pesos oficiales de MiniMax (Ref2VA real al usar referencias), máxima fidelidad de identidad y estilo. 20 pasos por defecto; menos es borrador, más no garantiza mejor calidad. Más lento.',
  turbo: 'Rápido con los pesos oficiales: LoRA Turbo de LightX2V sobre H3 (también Ref2VA real con referencias), 8 pasos. Buen equilibrio para iterar y para videoclips; Base sigue siendo la máxima fidelidad. Mismo formato de prompt.',
  fused_turbo: 'Para borradores e iterar rápido o videoclips con muchas escenas. Fusión experimental de la comunidad (Turbo + Mystic): usa 4 pasos; 8 o 12 solo afinan un poco el dibujo y tardan más. El audio sale más suave que en Base y puede suavizar estilos 2D planos. Mismo formato de prompt.',
}

/** Wrap a scene's visual direction in the Ref2VA lip-sync structure the runtime expects. */
export function lipSyncTemplate(direction: string) {
  const action = direction.replace(/^[\s\S]*?integrated_multimodal_description:\s*/, '').replace(/\s*overall_soundscape:[\s\S]*$/, '').replace(/^\[Shot 1\]\s*/, '').trim()
  return `subject_definitions:
<Subject 1> is the singer shown in <Picture 1>, preserving facial identity, hair, outfit and body proportions; the picture supplies appearance rather than its exact pose.
<Audio 1> is the song excerpt for this scene, containing the lead vocal and the full accompaniment.

summary:
[reference generation + audio reuse] <Subject 1> performs the excerpt <Audio 1>, lip-syncing its lead vocal.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity and outfit are kept.
<Audio 1>: fully_copy - the excerpt is the complete soundtrack of the clip; the singer's mouth follows its vocal.

detailed_description:
[Shot 1] ${action ? action + ' ' : ''}<Subject 1> (S1) sings in sync with the lead vocal of <Audio 1>, face clearly visible, lips, jaw and breathing following each phrase.

overall_soundscape:
No ambience or foley is added beyond <Audio 1>.

non_diegetic_music:
The accompaniment of <Audio 1> continues as the score.`
}
