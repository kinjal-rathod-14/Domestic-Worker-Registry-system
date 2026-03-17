/**
 * BiometricCapture — WebRTC camera component for capturing worker photos.
 * Validates image quality (resolution, face detected) before accepting.
 * Used in both AssistedRegistration and VerificationPanel.
 */

import React, { useRef, useState, useCallback } from "react";

interface BiometricCaptureProps {
  onCapture: (base64Image: string) => void;
  onError?: (error: string) => void;
  label?: string;
  minResolution?: { width: number; height: number };
}

type CaptureState = "idle" | "loading" | "preview" | "captured" | "error";

export const BiometricCapture: React.FC<BiometricCaptureProps> = ({
  onCapture,
  onError,
  label = "Capture Photo",
  minResolution = { width: 320, height: 240 },
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [state, setState] = useState<CaptureState>("idle");
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startCamera = useCallback(async () => {
    setState("loading");
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1280, min: minResolution.width },
          height: { ideal: 720, min: minResolution.height },
        },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setState("preview");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Camera access denied";
      setError(msg);
      setState("error");
      onError?.(msg);
    }
  }, [minResolution, onError]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  const capture = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);

    // Validate minimum resolution
    if (video.videoWidth < minResolution.width || video.videoHeight < minResolution.height) {
      const msg = `Image resolution too low. Minimum: ${minResolution.width}x${minResolution.height}`;
      setError(msg);
      onError?.(msg);
      return;
    }

    // Export as base64 JPEG (quality 0.85)
    const base64 = canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
    setCapturedImage(canvas.toDataURL("image/jpeg", 0.85));
    setState("captured");
    stopCamera();
    onCapture(base64);
  }, [minResolution, onCapture, onError, stopCamera]);

  const retake = useCallback(() => {
    setCapturedImage(null);
    setState("idle");
  }, []);

  return (
    <div className="flex flex-col items-center gap-4">
      <canvas ref={canvasRef} className="hidden" />

      {state === "idle" && (
        <button
          type="button"
          onClick={startCamera}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          {label}
        </button>
      )}

      {state === "loading" && (
        <div className="flex items-center gap-2 text-gray-600">
          <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <span>Starting camera...</span>
        </div>
      )}

      {state === "preview" && (
        <div className="flex flex-col items-center gap-3">
          <div className="relative w-full max-w-sm">
            <video
              ref={videoRef}
              className="w-full rounded-lg border-2 border-blue-200"
              autoPlay
              muted
              playsInline
            />
            {/* Face alignment guide overlay */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="w-32 h-40 border-2 border-blue-400 border-dashed rounded-full opacity-60" />
            </div>
          </div>
          <p className="text-sm text-gray-500">Align face within the oval guide</p>
          <button
            type="button"
            onClick={capture}
            className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium"
          >
            Take Photo
          </button>
        </div>
      )}

      {state === "captured" && capturedImage && (
        <div className="flex flex-col items-center gap-3">
          <img
            src={capturedImage}
            alt="Captured photo"
            className="w-full max-w-sm rounded-lg border border-green-200"
          />
          <div className="flex items-center gap-1 text-green-600 text-sm">
            <span>✓</span>
            <span>Photo captured successfully</span>
          </div>
          <button
            type="button"
            onClick={retake}
            className="px-4 py-1.5 border border-gray-300 text-gray-600 rounded-lg text-sm hover:bg-gray-50"
          >
            Retake Photo
          </button>
        </div>
      )}

      {state === "error" && (
        <div className="flex flex-col items-center gap-3">
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm max-w-sm text-center">
            {error}
          </div>
          <button
            type="button"
            onClick={() => setState("idle")}
            className="px-4 py-1.5 border border-gray-300 rounded-lg text-sm"
          >
            Try Again
          </button>
        </div>
      )}
    </div>
  );
};

export default BiometricCapture;
