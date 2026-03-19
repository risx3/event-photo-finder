import { useState, useEffect } from 'react'

export default function SettingsPanel({ open, config, onSave, onClose }) {
  const [eventName, setEventName]       = useState(config.eventName)
  const [eventSubtitle, setEventSubtitle] = useState(config.eventSubtitle)
  const [showScores, setShowScores]     = useState(config.showScores)

  // Sync fields if config changes from outside (e.g. server refresh)
  useEffect(() => {
    setEventName(config.eventName)
    setEventSubtitle(config.eventSubtitle)
    setShowScores(config.showScores)
  }, [config])

  function handleSave() {
    onSave({ eventName, eventSubtitle, showScores })
    onClose()
  }

  return (
    <>
      {/* Backdrop */}
      <div className={`settings-overlay${open ? ' open' : ''}`} onClick={onClose} />

      {/* Drawer */}
      <aside className={`settings-panel${open ? ' open' : ''}`}>
        <div className="settings-panel-header">
          <h2>Customise Event</h2>
          <button className="settings-close" onClick={onClose}>✕</button>
        </div>

        <div className="settings-body">
          <div className="settings-field">
            <label>Event Name</label>
            <input
              type="text"
              value={eventName}
              onChange={e => setEventName(e.target.value)}
              placeholder="My Event"
            />
          </div>

          <div className="settings-field">
            <label>Subtitle</label>
            <input
              type="text"
              value={eventSubtitle}
              onChange={e => setEventSubtitle(e.target.value)}
              placeholder="Find all your photos from this event"
            />
          </div>

          <div className="toggle-row">
            <span>Show match scores</span>
            <label className="toggle">
              <input
                type="checkbox"
                checked={showScores}
                onChange={e => setShowScores(e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
          </div>

          <p className="settings-hint">
            Changes are saved locally in your browser. To set permanent defaults,
            add <code>EVENT_NAME</code> and <code>EVENT_SUBTITLE</code> to your
            <code>.env</code> file and restart the server.
          </p>
        </div>

        <div className="settings-footer">
          <button className="save-btn" onClick={handleSave}>Save Changes</button>
        </div>
      </aside>
    </>
  )
}
