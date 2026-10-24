import { forwardRef } from 'react'

/** The Media Lab mark as a raster emblem (public/brand), for places that need an image. */
export function Emblem({ size = 44, className = '' }: { size?: number; className?: string }) {
  return <img className={`emblem ${className}`} src={size > 120 ? '/brand/emblem.webp' : '/brand/emblem-256.webp'} width={size} height={size} alt="" aria-hidden="true" draggable={false} />
}

/** Emblem + wordmark lockup. */
export function Brand({ size = 40, sub = 'Lab' }: { size?: number; sub?: string }) {
  return <span className="brand"><Emblem size={size} /><span className="brand-word"><b>Media</b><small>{sub}</small></span></span>
}

// Vector trace of the emblem for the "drawn in light" intro. Geometry mirrors the raster logo.
const BLADES = Array.from({ length: 6 }, (_, k) => {
  const a = (k * 60 - 90) * Math.PI / 180, b = a + 1.25
  const p = (r: number, t: number) => `${(100 + r * Math.cos(t)).toFixed(1)} ${(112 + r * Math.sin(t)).toFixed(1)}`
  return `M${p(55, a)} L${p(19, b)}`
})

export const LogoTrace = forwardRef<SVGSVGElement, { className?: string }>(({ className = '' }, ref) =>
  <svg ref={ref} className={`logo-trace ${className}`} viewBox="0 0 200 200" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="trace-g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffe0cc" /><stop offset=".5" stopColor="#ff8a3d" /><stop offset="1" stopColor="#ffb080" /></linearGradient>
      <filter id="trace-glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.4" result="b" /><feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
    </defs>
    <g stroke="url(#trace-g)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" filter="url(#trace-glow)">
      <path data-draw d="M50 76 L58 24 L94 54" />
      <path data-draw d="M150 76 L142 24 L106 54" />
      <circle data-draw cx="100" cy="112" r="62" />
      <circle data-draw cx="100" cy="112" r="55" />
      <rect data-draw x="22" y="88" width="22" height="50" rx="10" />
      <rect data-draw x="156" y="88" width="22" height="50" rx="10" />
      {BLADES.map((d, i) => <path data-draw key={i} d={d} />)}
      <path data-draw d="M92 99 L117 112 L92 125 Z" />
      <path data-draw d="M40 112 L52 112 L56 104 L60 120 L64 108 L68 116 L72 112 M128 112 L132 106 L136 118 L140 108 L144 114 L148 112 L160 112" />
    </g>
  </svg>)
LogoTrace.displayName = 'LogoTrace'
