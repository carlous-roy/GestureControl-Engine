// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RelayModule from '../RelayModule.tsx'

const base = {
  energised: [true, false, false, false],
  written: [true, false, false, false],
  desired: [true, false, false, false],
  holds: [0, 0, 0, 0],
  levels: [0, 1, 1, 1],
  activeLow: true,
  tripped: false,
  powered: true,
  hostRunning: true,
}

describe('RelayModule', () => {
  it('shows each channel with its pin level and state', () => {
    render(<RelayModule {...base} />)
    expect(screen.getByRole('img', { name: 'Relay 1: on' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Relay 2: off' })).toBeInTheDocument()
    expect(screen.getAllByText('LOW')).toHaveLength(1)
    expect(screen.getAllByText('HIGH')).toHaveLength(3)
    expect(screen.getAllByText('settled')).toHaveLength(4)
  })

  it('counts down a change held by the switching interval', () => {
    render(<RelayModule {...base} desired={[false, true, false, false]} holds={[0.31, 0, 0, 0]} />)
    expect(screen.getByText('off in 0.31 s')).toBeInTheDocument()
    expect(screen.getByText('applying')).toBeInTheDocument()
  })

  it('explains a tripped watchdog and a host that is down', () => {
    const { rerender } = render(
      <RelayModule {...base} tripped energised={[false, false, false, false]} />
    )
    expect(screen.getByText(/watchdog has released every relay/)).toBeInTheDocument()
    rerender(<RelayModule {...base} hostRunning={false} />)
    expect(screen.getAllByText('host down')).toHaveLength(4)
  })
})
