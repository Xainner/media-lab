import { useEffect, useState } from 'react'
import { cancelJob, clearRecoveryValue, runtime, waitJob, type ArtifactRef, type Job } from '../lib/api'
import JobProgress from '../components/JobProgress'

export function useCreativeJob(key: string) {
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const id = localStorage.getItem(key)
    if (!id) return
    const controller = new AbortController()
    void waitJob(id, setJob, controller.signal).then(final => {
      if (['completed', 'cancelled'].includes(final.status)) clearRecoveryValue(key, id)
    }).catch(e => { if (!controller.signal.aborted) setError(String(e)) })
    return () => controller.abort()
  }, [key])
  async function submit(path: string, payload: unknown) {
    setError('')
    setJob(null)
    try {
      const result = await runtime('POST', path, payload)
      const id = result.job_id as string
      localStorage.setItem(key, id)
      const final = await waitJob(id, setJob)
      if (['completed', 'cancelled'].includes(final.status)) clearRecoveryValue(key, id)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
  }
  async function cancel() {
    if (!job) return
    try { await cancelJob(job.id || job.job_id || '') }
    catch (e) { setError(String(e)) }
  }
  return { job, error, submit, cancel }
}

export function CreativeResult({ media }: { media?: ArtifactRef }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!media) return
    let live = true
    void window.visualLab.runtime.mediaUrl(media.uri).then(value => { if (live) setUrl(value) })
      .catch(e => { if (live) setError(String(e)) })
    return () => { live = false }
  }, [media?.uri])
  if (!media) return null
  const audio = /\.(flac|wav|mp3|opus|ogg)$/i.test(media.uri)
  const master = media.uri.endsWith('.mkv')
  return <div className="creative-result">
    {audio ? <audio controls src={url} /> : master ? <p>Master Matroska con el flujo de audio original. Expórtalo para verlo en un reproductor compatible.</p> : <video controls src={url} />}
    <button className="primary" onClick={() => void window.visualLab.runtime.saveMedia(media.uri).catch(e => setError(String(e)))}>EXPORTAR ARCHIVO</button>
    {error && <p className="error">{error}</p>}
  </div>
}

export function CreativeProgress({ state }: { state: ReturnType<typeof useCreativeJob> }) {
  return <><JobProgress job={state.job} onCancel={() => void state.cancel()} />{state.error && <p className="error">{state.error}</p>}
    <CreativeResult media={state.job?.result?.media?.[0]} /></>
}
