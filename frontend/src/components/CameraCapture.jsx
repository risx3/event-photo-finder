import { useEffect, useRef, useState } from 'react'

export default function CameraCapture({ onCapture }) {
  const videoRef = useRef(null)
  const [facingMode, setFacingMode] = useState('user')
  const [hasMultiple, setHasMultiple] = useState(false)
  const [error, setError] = useState('')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let activeStream = null
    setError('')
    setReady(false)

    async function start() {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices()
        setHasMultiple(devices.filter(d => d.kind === 'videoinput').length > 1)

        activeStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        })
        if (videoRef.current) {
          videoRef.current.srcObject = activeStream
          setReady(true)
        }
      } catch {
        setError('Camera access denied or unavailable. Please allow permission and try again.')
      }
    }

    start()
    return () => { activeStream?.getTracks().forEach(t => t.stop()) }
  }, [facingMode])

  function capture() {
    const video = videoRef.current
    if (!video || !ready) return

    const canvas = document.createElement('canvas')
    canvas.width  = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')

    // Un-mirror the canvas so the saved photo is not reversed
    if (facingMode === 'user') {
      ctx.translate(canvas.width, 0)
      ctx.scale(-1, 1)
    }
    ctx.drawImage(video, 0, 0)

    canvas.toBlob(
      blob => onCapture(new File([blob], 'selfie.jpg', { type: 'image/jpeg' })),
      'image/jpeg',
      0.92,
    )
  }

  return (
    <div className="camera-wrap">
      {error ? (
        <div className="camera-error">{error}</div>
      ) : (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          className="camera-video"
          style={{ transform: facingMode === 'user' ? 'scaleX(-1)' : 'none' }}
        />
      )}

      <div className="camera-controls">
        {/* spacer keeps capture btn centred */}
        <div style={{ width: 42 }} />

        <button className="capture-btn" onClick={capture} disabled={!!error || !ready}>
          ⬤
        </button>

        {hasMultiple ? (
          <button
            className="switch-cam-btn"
            onClick={() => setFacingMode(m => m === 'user' ? 'environment' : 'user')}
            title="Switch camera"
          >
            ↺
          </button>
        ) : (
          <div style={{ width: 42 }} />
        )}
      </div>
    </div>
  )
}
