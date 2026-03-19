import { useState, useRef } from 'react'
import CameraCapture from './CameraCapture'

export default function UploadCard({ selectedFile, previewUrl, previewLabel, onFile, onFind }) {
  const [tab, setTab] = useState('upload')
  const [dragging, setDragging] = useState(false)
  const fileInputRef = useRef(null)

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) pick(file)
  }

  function pick(file, label) {
    if (!file.type.startsWith('image/')) return
    onFile(file, label)
  }

  function handleCapture(file) {
    setTab('upload')           // show preview in upload tab
    pick(file, 'Camera capture')
  }

  return (
    <div className="upload-card">
      <h2>Upload a selfie to find your photos</h2>

      {/* Mode tabs */}
      <div className="input-tabs">
        <button
          className={`input-tab${tab === 'upload' ? ' active' : ''}`}
          onClick={() => setTab('upload')}
        >
          📁 Upload Photo
        </button>
        <button
          className={`input-tab${tab === 'camera' ? ' active' : ''}`}
          onClick={() => setTab('camera')}
        >
          📷 Take a Photo
        </button>
      </div>

      {/* Upload panel */}
      {tab === 'upload' && (
        <div
          className={`drop-zone${dragging ? ' dragover' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={e => { if (e.target.files[0]) pick(e.target.files[0]) }}
          />
          <div className="dz-icon">🖼</div>
          <p>
            <strong>Click to choose</strong> or drag &amp; drop a photo<br />
            <small>JPG, PNG · Works best with a clear face shot</small>
          </p>
        </div>
      )}

      {/* Camera panel — mounts/unmounts to start/stop the stream */}
      {tab === 'camera' && <CameraCapture onCapture={handleCapture} />}

      {/* Preview */}
      {selectedFile && previewUrl && (
        <div className="preview-wrap">
          <img src={previewUrl} alt="Selfie preview" />
          <p className="preview-label">{previewLabel}</p>
          <button
            className="change-link"
            onClick={() => { fileInputRef.current?.click() }}
          >
            change photo
          </button>
        </div>
      )}

      <button className="find-btn" disabled={!selectedFile} onClick={onFind}>
        Find My Photos
      </button>
    </div>
  )
}
