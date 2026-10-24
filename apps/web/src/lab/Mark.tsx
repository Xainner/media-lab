/** Media Lab mark: an ember tile holding a lens whose aperture blades turn on hover. */
export function Mark({ size = 30 }: { size?: number }) {
  return <svg className="ml-mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
    <rect x="1" y="1" width="30" height="30" rx="9" fill="var(--ml-accent)" />
    <g className="ml-mark-lens">
      <circle cx="16" cy="16" r="8.2" fill="none" stroke="var(--ml-ink)" strokeWidth="3.4" strokeDasharray="8.6 4.3" strokeLinecap="round" />
    </g>
    <circle cx="16" cy="16" r="2.7" fill="var(--ml-ink)" />
  </svg>
}

export function Wordmark() {
  return <span className="ml-wordmark"><Mark /><span><b>MEDIA</b><i>LAB</i></span></span>
}
