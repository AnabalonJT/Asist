import { useEffect, useRef, useState, FormEvent } from 'react'
import { BrowserMultiFormatReader, IScannerControls } from '@zxing/browser'

interface BarcodeScannerProps {
  onDetected: (code: string) => void
}

// BarcodeScanner: scan a product barcode with the device camera (via
// @zxing/browser over getUserMedia) or type it in manually. Both paths call
// onDetected(code). The manual input is always visible so the component works
// even when the camera is unavailable or permission is denied. Spanish UI copy.
export function BarcodeScanner({ onDetected }: BarcodeScannerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  // Keep the scanner controls so we can stop the camera on cleanup.
  const controlsRef = useRef<IScannerControls | null>(null)
  // Keep the reader instance stable across renders.
  const readerRef = useRef<BrowserMultiFormatReader | null>(null)

  const [scanning, setScanning] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [manualCode, setManualCode] = useState('')

  // Stop the live scan and release the camera stream (turns the light off).
  function stopCamera() {
    try {
      controlsRef.current?.stop()
    } catch {
      // Ignore errors while stopping; we still clear the stream below.
    }
    controlsRef.current = null

    // Fallback: stop any MediaStream tracks still attached to the video element.
    const video = videoRef.current
    const stream = video?.srcObject as MediaStream | null
    if (stream) {
      stream.getTracks().forEach((track) => track.stop())
    }
    if (video) {
      video.srcObject = null
    }
  }

  // Start streaming the camera into the <video> and decode continuously.
  async function startCamera() {
    setCameraError('')
    if (!videoRef.current) return

    if (!readerRef.current) {
      readerRef.current = new BrowserMultiFormatReader()
    }

    try {
      const controls = await readerRef.current.decodeFromVideoDevice(
        undefined,
        videoRef.current,
        (result) => {
          if (result) {
            onDetected(result.getText())
          }
        },
      )
      controlsRef.current = controls
      setScanning(true)
    } catch (err: any) {
      // NotAllowedError / NotFoundError / NotReadableError (or anything else):
      // surface a Spanish message and keep the manual entry available.
      setScanning(false)
      setCameraError(
        'No se pudo acceder a la cámara. Puedes ingresar el código manualmente.',
      )
    }
  }

  // Release the camera when the component unmounts.
  useEffect(() => {
    return () => {
      stopCamera()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleActivate() {
    startCamera()
  }

  function handleStop() {
    stopCamera()
    setScanning(false)
  }

  function handleManualSubmit(e: FormEvent) {
    e.preventDefault()
    const code = manualCode.trim()
    if (code) {
      onDetected(code)
    }
  }

  return (
    <div className="card space-y-3">
      <h3 className="text-sm font-semibold text-text-primary">📷 Escanear código de barras</h3>

      {/* Camera preview + controls */}
      <div className="space-y-2">
        <video
          ref={videoRef}
          className="w-full rounded-lg bg-bg-base border border-bg-border aspect-video object-cover"
          muted
          playsInline
        />

        <div className="flex gap-2">
          {!scanning ? (
            <button type="button" onClick={handleActivate} className="btn-primary text-sm">
              Activar cámara
            </button>
          ) : (
            <button type="button" onClick={handleStop} className="btn-ghost text-sm">
              Detener cámara
            </button>
          )}
        </div>

        {cameraError && <p className="text-xs text-danger">{cameraError}</p>}
      </div>

      {/* Manual entry — always visible */}
      <form onSubmit={handleManualSubmit} className="border-t border-bg-border pt-3 space-y-2">
        <label className="text-xs text-text-secondary">Ingresa el código manualmente</label>
        <div className="flex gap-2">
          <input
            type="text"
            inputMode="numeric"
            className="input flex-1"
            placeholder="Ej. 7501234567890"
            value={manualCode}
            onChange={(e) => setManualCode(e.target.value)}
          />
          <button type="submit" className="btn-primary text-sm">
            Buscar código
          </button>
        </div>
        <p className="text-xs text-text-dim">
          Si no tienes cámara o se denegó el permiso, escribe el código del producto.
        </p>
      </form>
    </div>
  )
}
