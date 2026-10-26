import type { Job } from '../lib/api'
import { t, type MessageKey } from '../../i18n'

const STATUS: Record<string, MessageKey> = { queued: 'shell.job.status.queued', running: 'shell.job.status.running', completed: 'shell.job.status.completed', failed: 'shell.job.status.failed', cancelled: 'shell.job.status.cancelled', interrupted: 'shell.job.status.interrupted', blocked_gpu: 'shell.job.status.blockedGpu' }

export default function JobProgress({ job, onCancel, actionError, cancelDisabled = false }: { job: Job | null; onCancel?: () => void; actionError?: string; cancelDisabled?: boolean }) {
  if (!job) return null
  const active = ['queued', 'running'].includes(job.status)
  const progress = job.progress
  return (
    <div className={`job-card ${job.status}`}>
      <div className="job-head">
        <div><span className="pulse" /><b>{STATUS[job.status] ? t(STATUS[job.status]) : job.status}</b> <code>{job.id || job.job_id}</code>
          {job.gpu != null && <small> · GPU {job.gpu}</small>}</div>
        {active && onCancel && <button className="danger ghost" onClick={onCancel} disabled={cancelDisabled}>{t('shell.job.cancel')}</button>}
      </div>
      {job.status === 'queued' && <p>{t('shell.job.queuePosition', { position: job.queue_position ?? 0 })}</p>}
      {job.activity?.length > 0 && <div className="activity">{job.activity.map((a, i) => <span key={`${a}-${i}`}>{a}</span>)}</div>}
      {progress && (
        <>
          <div className="progress-label"><span>{progress.node || t('shell.job.diffusion')}</span><b>{progress.pct ?? 0}%</b></div>
          <div className="progress"><i style={{ width: `${progress.pct || 0}%` }} /></div>
          {progress.steps > 0 && <small>{t('shell.job.step', { step: progress.step, steps: progress.steps })}</small>}
        </>
      )}
      {job.error && <p className="error">{job.error}</p>}
      {actionError && <p className="error">{actionError}</p>}
    </div>
  )
}

