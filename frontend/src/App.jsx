import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import UploadCard from './components/UploadCard'
import Loader from './components/Loader'
import Results from './components/Results'
import SettingsPanel from './components/SettingsPanel'

const SERVER_DEFAULTS = {
  eventName: 'My Event',
  eventSubtitle: 'Find all your photos from this event',
  showScores: true,
}

export default function App() {
  // ── View state ────────────────────────────────────────────────────
  // 'upload' | 'loading' | 'results' | 'error' | 'empty'
  const [view, setView]         = useState('upload')
  const [photos, setPhotos]     = useState([])
  const [errorMsg, setErrorMsg] = useState('')

  // ── File / preview ────────────────────────────────────────────────
  const [selectedFile, setSelectedFile]   = useState(null)
  const [previewUrl, setPreviewUrl]       = useState(null)
  const [previewLabel, setPreviewLabel]   = useState('')
  // Incrementing this key forces UploadCard to fully remount on reset,
  // which resets its local tab/drag state cleanly.
  const [uploadKey, setUploadKey]         = useState(0)

  // ── Settings ──────────────────────────────────────────────────────
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [config, setConfig]             = useState(SERVER_DEFAULTS)

  // Load config: fetch server defaults, then overlay localStorage overrides
  useEffect(() => {
    async function loadConfig() {
      let fromServer = {}
      try {
        const res = await fetch('/api/config')
        if (res.ok) {
          const data = await res.json()
          fromServer = {
            eventName:     data.event_name     || SERVER_DEFAULTS.eventName,
            eventSubtitle: data.event_subtitle || SERVER_DEFAULTS.eventSubtitle,
          }
        }
      } catch {
        // Dev mode with no backend reachable — skip
      }
      const fromStorage = JSON.parse(localStorage.getItem('eventConfig') || '{}')
      setConfig({ ...SERVER_DEFAULTS, ...fromServer, ...fromStorage })
    }
    loadConfig()
  }, [])

  // ── File selection ────────────────────────────────────────────────
  const handleFile = useCallback((file, label = '') => {
    // Revoke any previously created object URL to avoid memory leaks
    setPreviewUrl(prev => {
      if (prev) URL.revokeObjectURL(prev)
      return URL.createObjectURL(file)
    })
    setSelectedFile(file)
    setPreviewLabel(label || file.name)
  }, [])

  // ── Find photos ───────────────────────────────────────────────────
  const handleFind = useCallback(async () => {
    if (!selectedFile) return
    setView('loading')

    const form = new FormData()
    form.append('selfie', selectedFile)

    try {
      const res  = await fetch('/api/match', { method: 'POST', body: form })
      const data = await res.json()

      if (!res.ok) {
        setErrorMsg(data.detail || 'Something went wrong. Please try again.')
        setView('error')
        return
      }
      if (!data.success) {
        setErrorMsg(data.error || 'Could not process your selfie.')
        setView('error')
        return
      }
      if (data.matched_count === 0) {
        setView('empty')
        return
      }
      setPhotos(data.photos)
      setView('results')
    } catch {
      setErrorMsg('Could not reach the server. Make sure the backend is running.')
      setView('error')
    }
  }, [selectedFile])

  // ── Reset ─────────────────────────────────────────────────────────
  const handleReset = useCallback(() => {
    setPreviewUrl(prev => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
    setSelectedFile(null)
    setPreviewLabel('')
    setPhotos([])
    setErrorMsg('')
    setView('upload')
    setUploadKey(k => k + 1)
  }, [])

  // ── Settings save ─────────────────────────────────────────────────
  const handleSaveConfig = useCallback((updates) => {
    setConfig(prev => {
      const next = { ...prev, ...updates }
      localStorage.setItem('eventConfig', JSON.stringify(next))
      return next
    })
  }, [])

  // ── Render ────────────────────────────────────────────────────────
  return (
    <div className="app">
      <Header config={config} onSettingsClick={() => setSettingsOpen(true)} />

      <main className="main">
        {/* Upload card — always mounted during upload/error/empty so the
            user can change their file without losing the card state */}
        {(view === 'upload' || view === 'error' || view === 'empty') && (
          <UploadCard
            key={uploadKey}
            selectedFile={selectedFile}
            previewUrl={previewUrl}
            previewLabel={previewLabel}
            onFile={handleFile}
            onFind={handleFind}
          />
        )}

        {view === 'loading' && <Loader />}

        {view === 'results' && (
          <Results
            photos={photos}
            showScores={config.showScores}
            onReset={handleReset}
          />
        )}

        {view === 'error' && (
          <div className="fade-up">
            <div className="message-box error-box">⚠ {errorMsg}</div>
            <button className="reset-btn" onClick={handleReset}>← Try Another Selfie</button>
          </div>
        )}

        {view === 'empty' && (
          <div className="fade-up">
            <div className="message-box empty-box">
              <div className="empty-icon">📷</div>
              <p>No matching photos found.<br />Try a clearer selfie with good lighting.</p>
            </div>
            <button className="reset-btn" onClick={handleReset}>← Try Another Selfie</button>
          </div>
        )}
      </main>

      <footer className="site-footer">
        Made with love ♥ &nbsp;·&nbsp; Powered by face recognition
      </footer>

      <SettingsPanel
        open={settingsOpen}
        config={config}
        onSave={handleSaveConfig}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  )
}
