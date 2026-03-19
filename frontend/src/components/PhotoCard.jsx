/**
 * Individual photo card in the results grid.
 * Shows a thumbnail, a thin match-strength bar, and a hover overlay
 * with the cosine score and a download button.
 *
 * @param {object} photo  - { thumbnail_url, filename, similarity_score, view_url, download_url }
 * @param {number} index  - position in the grid (drives stagger animation delay)
 * @param {boolean} showScores - whether to show the score overlay
 */
export default function PhotoCard({ photo, index, showScores }) {
  // Map score from [threshold ≈ 0.4, 1.0] to [0%, 100%] for the bar width.
  const barWidth = Math.min(100, Math.max(0, (photo.similarity_score - 0.4) / 0.6 * 100))

  return (
    <div
      className="photo-card"
      style={{ '--card-i': index }}
      onClick={() => window.open(photo.view_url, '_blank')}
    >
      <img src={photo.thumbnail_url} alt={photo.filename} loading="lazy" />

      {/* Match strength bar along the bottom edge */}
      <div className="score-bar" style={{ width: `${barWidth}%` }} />

      <div className="card-overlay">
        {showScores && (
          <span className="score-label">score: {photo.similarity_score.toFixed(2)}</span>
        )}
        <button
          className="dl-btn"
          onClick={e => { e.stopPropagation(); window.open(photo.download_url, '_blank') }}
        >
          Download
        </button>
      </div>
    </div>
  )
}
