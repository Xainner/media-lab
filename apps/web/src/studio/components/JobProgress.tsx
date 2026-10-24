import type { Job } from '../lib/api'

export default function JobProgress({ job, onCancel, actionError, cancelDisabled = false }: { job: Job | null; onCancel?: () => void; actionError?: string; cancelDisabled?: boolean }) {
  if (!job) return null
  const active = ['queued', 'running'].includes(job.status)
  const progress = job.progress
  return (
    <div className={`job-card ${job.status}`}>
      <div className="job-head">
        <div><span className="pulse" /><b>{{queued:'En cola',running:'Creando',completed:'Completado',failed:'Error',cancelled:'Cancelado',interrupted:'Interrumpido',blocked_gpu:'Esperando recursos'}[job.status]||job.status}</b> <code>{job.id || job.job_id}</code>
          {job.gpu != null && <small> · GPU {job.gpu}</small>}</div>
        {active && onCancel && <button className="danger ghost" onClick={onCancel} disabled={cancelDisabled}>CANCELAR</button>}
      </div>
      {job.status === 'queued' && <p>En cola · posición {job.queue_position ?? 0}</p>}
      {job.activity?.length > 0 && <div className="activity">{job.activity.map((a, i) => <span key={`${a}-${i}`}>{a}</span>)}</div>}
      {progress && (
        <>
          <div className="progress-label"><span>{progress.node || 'difusión'}</span><b>{progress.pct ?? 0}%</b></div>
          <div className="progress"><i style={{ width: `${progress.pct || 0}%` }} /></div>
          {progress.steps > 0 && <small>paso {progress.step}/{progress.steps}</small>}
        </>
      )}
      {job.error && <p className="error">{job.error}</p>}
      {actionError && <p className="error">{actionError}</p>}
    </div>
  )
}

