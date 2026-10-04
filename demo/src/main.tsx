import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/space-grotesk'
import '@fontsource/space-mono/400.css'
import '@fontsource/space-mono/700.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/bench.css'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'

const root = document.getElementById('root')
if (root === null) throw new Error('index.html has no #root element')

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>
)
