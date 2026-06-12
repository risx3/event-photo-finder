import CameraCapture from './CameraCapture'

export default function UploadCard({ selectedFile, previewUrl, previewLabel, onFile, onFind, onReset }) {
  function handleCapture(file) {
    onFile(file, 'Selfie')
  }

  return (
    <div className="upload-card">
      <h2>Take a selfie to find your photos</h2>

      {!selectedFile && <CameraCapture onCapture={handleCapture} />}

      {/* Preview */}
      {selectedFile && previewUrl && (
        <div className="preview-wrap">
          <img src={previewUrl} alt="Selfie preview" />
          <p className="preview-label">{previewLabel}</p>
          <button className="change-link" onClick={onReset}>
            retake photo
          </button>
        </div>
      )}

      <button className="find-btn" disabled={!selectedFile} onClick={onFind}>
        Find My Photos
      </button>
    </div>
  )
}
