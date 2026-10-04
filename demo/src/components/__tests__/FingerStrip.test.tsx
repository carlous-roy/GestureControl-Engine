// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FingerStrip from '../FingerStrip.tsx'
import Readout from '../Readout.tsx'

describe('FingerStrip', () => {
  it('lists the five channels with their measurements and latches', () => {
    render(
      <FingerStrip
        measurement={{ thumb: -0.12, fingers: [0.74, 0.8, -0.3, 0.1], palmWidth: 61.4 }}
        states={[false, true, true, false, false]}
      />
    )
    expect(screen.getByText('palm 61 px')).toBeInTheDocument()
    expect(screen.getByText('0.74')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'index: on' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'ring: off' })).toBeInTheDocument()
  })

  it('shows nothing to measure without a hand', () => {
    render(<FingerStrip measurement={null} states={null} />)
    expect(screen.getByText('no measurement')).toBeInTheDocument()
  })
})

describe('Readout', () => {
  it('shows the confirmed count, its relays and the confirmation run', () => {
    render(<Readout handPresent rawCount={3} confirmedCount={2} candidate={3} runLength={2} />)
    expect(screen.getByLabelText('Confirmed count')).toHaveTextContent('2')
    expect(screen.getByText('relay 2')).toBeInTheDocument()
    expect(screen.getByText('seeing 3: frame 2 of 3')).toBeInTheDocument()
  })

  it('says the relays hold when the hand is gone', () => {
    render(
      <Readout handPresent={false} rawCount={-1} confirmedCount={5} candidate={-1} runLength={0} />
    )
    expect(screen.getByText('no hand: the relays hold')).toBeInTheDocument()
    expect(screen.getByText('all on')).toBeInTheDocument()
  })
})
