export type Tone = 'amber' | 'green' | 'red' | 'cyan' | 'grey'

interface Props {
  on: boolean
  tone?: Tone
  size?: number
  label?: string
}

/** A panel LED: lit with a glow, or dark. */
export default function Led({ on, tone = 'amber', size = 10, label }: Props) {
  return (
    <span
      className={`led tone-${tone} ${on ? 'on' : ''}`}
      style={{ width: size, height: size }}
      role={label ? 'img' : undefined}
      aria-label={label ? `${label}: ${on ? 'on' : 'off'}` : undefined}
      aria-hidden={label ? undefined : true}
    />
  )
}
