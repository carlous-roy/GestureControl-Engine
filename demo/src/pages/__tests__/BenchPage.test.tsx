// @vitest-environment jsdom
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import BenchPage from '../BenchPage.tsx'

beforeAll(() => {
  // jsdom has no canvas; the drawing code treats a missing context as nothing to draw.
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', { value: () => null })
})

describe('BenchPage', () => {
  it('runs the replay through the pipeline and the host, and takes the faults', async () => {
    vi.useFakeTimers()
    try {
      render(<BenchPage />)
      expect(screen.getByText('15/15 match the engine')).toBeInTheDocument()
      expect(screen.getByText('running')).toBeInTheDocument()
      // A second of animation frames: the first sequence is count_up, which confirms counts.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1500)
      })
      const log = screen.getByRole('region', { name: 'Log' })
      expect(within(log).getAllByText(/Gesture: \d finger\(s\)/).length).toBeGreaterThan(0)

      fireEvent.click(screen.getByRole('button', { name: 'Pull USB' }))
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400)
      })
      expect(screen.getByText(/exited, code 3/)).toBeInTheDocument()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1200)
      })
      expect(within(log).getByText('watchdog: no heartbeat, relays released')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Plug USB back' }))
      fireEvent.click(screen.getByRole('button', { name: 'Restart host' }))
      expect(screen.getByText('running')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('switches to the webcam and reports a missing camera', async () => {
    render(<BenchPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Webcam' }))
    const viewport = screen.getByRole('region', { name: 'Viewport' })
    expect(
      await within(viewport).findByText(/no camera access/i, {}, { timeout: 3000 })
    ).toBeInTheDocument()
    expect(screen.getByText('Camera unavailable')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Back to the replay' }))
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
  })
})
