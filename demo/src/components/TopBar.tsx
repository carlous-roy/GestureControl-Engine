import { REPO_URL } from '../edition.ts'
import type { ModelStatus, SourceMode } from '../hooks/useBench.ts'
import Led from './Led.tsx'

interface Props {
  mode: SourceMode
  onMode: (mode: SourceMode) => void
  model: ModelStatus
  cameraError: string | null
}

export default function TopBar({ mode, onMode, model, cameraError }: Props) {
  const status =
    mode === 'replay'
      ? 'Golden sequences from the engine'
      : cameraError !== null
        ? 'Camera unavailable'
        : model.phase === 'downloading'
          ? `Fetching the hand landmarker ${Math.round(model.progress * 100)}%`
          : model.phase === 'starting'
            ? 'Starting the landmarker'
            : model.phase === 'ready'
              ? 'Landmarker running in this tab'
              : model.phase === 'error'
                ? 'Model unavailable'
                : 'Opening the webcam'
  const tone =
    mode === 'replay'
      ? 'green'
      : cameraError !== null || model.phase === 'error'
        ? 'red'
        : model.phase === 'ready'
          ? 'green'
          : 'amber'
  return (
    <header className="topbar">
      <div className="brand">
        <img src="/rc-logo.svg" alt="" width="26" height="24" className="mark" />
        <span className="wordmark">GestureControl</span>
        <span className="product">Hardware bench</span>
      </div>
      <div className="bar-controls">
        <div className="segmented" role="group" aria-label="Source">
          <button type="button" aria-pressed={mode === 'replay'} onClick={() => onMode('replay')}>
            Golden replay
          </button>
          <button type="button" aria-pressed={mode === 'camera'} onClick={() => onMode('camera')}>
            Webcam
          </button>
        </div>
        <span className="status small">
          <Led on tone={tone} label="Source" />
          {status}
        </span>
      </div>
      <a className="source" href={REPO_URL} target="_blank" rel="noopener noreferrer">
        Source
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </a>
    </header>
  )
}
