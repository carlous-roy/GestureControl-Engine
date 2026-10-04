import { useCallback, useRef } from 'react'
import { useBench } from '../hooks/useBench.ts'
import TopBar from '../components/TopBar.tsx'
import Viewport from '../components/Viewport.tsx'
import Readout from '../components/Readout.tsx'
import FingerStrip from '../components/FingerStrip.tsx'
import RelayModule from '../components/RelayModule.tsx'
import ControllerPanel from '../components/ControllerPanel.tsx'
import Scope from '../components/Scope.tsx'
import ReplayDeck from '../components/ReplayDeck.tsx'
import Timings from '../components/Timings.tsx'
import LogPane from '../components/LogPane.tsx'
import Explain from '../components/Explain.tsx'
import Footer from '../components/Footer.tsx'

/** The whole bench: source on top, measurements and hardware beside it, the deck and the log below. */
export default function BenchPage() {
  const bench = useBench()
  const { view } = bench
  const refs = useRef<{
    viewport: HTMLCanvasElement | null
    scope: HTMLCanvasElement | null
    video: HTMLVideoElement | null
  }>({ viewport: null, scope: null, video: null })

  const bindViewport = useCallback(
    (canvas: HTMLCanvasElement | null, video: HTMLVideoElement | null) => {
      refs.current.viewport = canvas
      refs.current.video = video
      bench.bind(refs.current)
    },
    [bench]
  )
  const bindScope = useCallback(
    (canvas: HTMLCanvasElement | null) => {
      refs.current.scope = canvas
      bench.bind(refs.current)
    },
    [bench]
  )

  const frame = view.frame
  const result = frame?.result ?? null
  const relaysOnBoard = view.host.levels.map((level) => level === (view.host.activeLow ? 0 : 1))

  return (
    <div className="app">
      <TopBar
        mode={view.mode}
        onMode={bench.setMode}
        model={view.model}
        cameraError={view.cameraError}
      />
      <main className="bench">
        <div className="bench-top">
          <div className="column picture">
            <Viewport
              mode={view.mode}
              frame={frame}
              model={view.model}
              cameraError={view.cameraError}
              stalled={view.host.state === 'stalled'}
              onBind={bindViewport}
              onRetryCamera={() => {
                bench.setMode('replay')
                bench.setMode('camera')
              }}
            />
            <Scope onBind={bindScope} />
          </div>
          <div className="column measures">
            <Readout
              handPresent={result?.handPresent ?? false}
              rawCount={result?.rawCount ?? -1}
              confirmedCount={result?.confirmedCount ?? -1}
              candidate={frame?.candidate ?? -1}
              runLength={frame?.runLength ?? 0}
            />
            <FingerStrip
              measurement={frame?.measurement ?? null}
              states={result?.fingerStates ?? null}
            />
            <Timings mode={view.mode} timings={view.timings} />
          </div>
          <div className="column hardware">
            <RelayModule
              energised={relaysOnBoard}
              written={view.host.relays}
              desired={view.host.desired}
              holds={view.host.holds}
              levels={view.host.levels}
              activeLow={view.host.activeLow}
              tripped={view.host.tripped}
              powered={view.host.powered}
              hostRunning={view.host.state === 'running'}
            />
            <ControllerPanel host={view.host} faults={bench.faults} />
            <ReplayDeck
              mode={view.mode}
              replay={view.replay}
              controls={bench.replay}
              onMode={bench.setMode}
            />
          </div>
        </div>

        <LogPane lines={view.log} onClear={bench.clearLog} />
        <Explain />
      </main>
      <Footer />
    </div>
  )
}
