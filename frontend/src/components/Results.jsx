import PhotoCard from './PhotoCard'

export default function Results({ photos, showScores, onReset }) {
  function downloadAll() {
    photos.forEach((photo, i) => {
      setTimeout(() => window.open(photo.download_url, '_blank'), i * 150)
    })
  }

  return (
    <div className="results-wrap">
      <div className="results-header">
        <h2>Found <strong>{photos.length}</strong> photo{photos.length !== 1 ? 's' : ''} with you!</h2>
        <button className="download-all-btn" onClick={downloadAll}>
          ↓ Download All
        </button>
      </div>

      <div className="photo-grid">
        {photos.map((photo, i) => (
          <PhotoCard
            key={photo.file_id}
            photo={photo}
            index={i}
            showScores={showScores}
          />
        ))}
      </div>

      <button className="reset-btn" onClick={onReset}>← Try Another Selfie</button>
    </div>
  )
}
