// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ControllerPanel from '../ControllerPanel.tsx'
import type { BenchView } from '../../hooks/useBench.ts'

function host(overrides: Partial<BenchView['host']> = {}): BenchView['host'] {
  return {
    state: 'running',
    exitCode: null,
    linkUp: true,
    powered: true,
    relays: [false, false, false, false],
    desired: [false, false, false, false],
    holds: [0, 0, 0, 0],
    levels: [1, 1, 1, 1],
    activeLow: true,
    tripped: false,
    armed: true,
    sinceHeartbeatMs: 120,
    timeoutMs: 1000,
    stallRemainingS: 0,
    lost: false,
    ...overrides,
  }
}

function faults() {
  return {
    stall: vi.fn(),
    pullCable: vi.fn(),
    plugCable: vi.fn(),
    cutPower: vi.fn(),
    restorePower: vi.fn(),
    interrupt: vi.fn(),
    restart: vi.fn(),
  }
}

describe('ControllerPanel', () => {
  it('shows a running host with the watchdog counting down and wires the faults', () => {
    const f = faults()
    render(<ControllerPanel host={host()} faults={f} />)
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('880 ms')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Stall host 2 s' }))
    expect(f.stall).toHaveBeenCalledWith(2)
    fireEvent.click(screen.getByRole('button', { name: 'Pull USB' }))
    expect(f.pullCable).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Ctrl-C' }))
    expect(f.interrupt).toHaveBeenCalled()
  })

  it('offers the way back after each fault', () => {
    const f = faults()
    render(
      <ControllerPanel
        host={host({ state: 'exited', exitCode: 3, linkUp: false, powered: false, tripped: true })}
        faults={f}
      />
    )
    expect(screen.getByText(/code 3: a relay may be left on/)).toBeInTheDocument()
    expect(screen.getByText('USB out')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Plug USB back' }))
    fireEvent.click(screen.getByRole('button', { name: 'Restore power' }))
    fireEvent.click(screen.getByRole('button', { name: 'Restart host' }))
    expect(f.plugCable).toHaveBeenCalled()
    expect(f.restorePower).toHaveBeenCalled()
    expect(f.restart).toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Stall host 2 s' })).toBeDisabled()
  })
})
