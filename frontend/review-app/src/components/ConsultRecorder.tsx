"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAudioRecorder } from "@/lib/useAudioRecorder";
import { useMicrophoneDevices } from "@/lib/useMicrophoneDevices";

interface ConsultRecorderProps {
  onComplete: (sessionId: string) => void;
}

/** Lijst met lokaal opgeslagen opnames (in-memory + bestandsnaam). */
interface SavedRecording {
  id: string;
  filename: string;
  blob: Blob;
  timestamp: Date;
  duration: number;
  uploaded: boolean;
}

/**
 * Spreekkamer-recorder: opnemen → lokaal opslaan → uploaden → SOEP pipeline.
 * Vergelijkbaar met Juvely/Dragon Medical workflow.
 *
 * Opnames worden altijd eerst lokaal bewaard (download-optie),
 * zodat ze nooit verloren gaan als de backend offline is.
 */
export default function ConsultRecorder({ onComplete }: ConsultRecorderProps) {
  const { devices, selectedDeviceId, selectDevice, loading: devicesLoading } =
    useMicrophoneDevices();

  const {
    state,
    duration,
    audioBlob,
    audioUrl,
    analyserNode,
    error: recorderError,
    start,
    pause,
    resume,
    stop,
    reset,
  } = useAudioRecorder({
    deviceId: selectedDeviceId || undefined,
  });

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [savedRecordings, setSavedRecordings] = useState<SavedRecording[]>([]);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  // ---------------------------------------------------------------------------
  // Auto-save: zodra opname stopt, sla lokaal op
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (state === "stopped" && audioBlob && !saved) {
      const timestamp = new Date();
      const ext = audioBlob.type.includes("webm") ? "webm" : "m4a";
      const filename = `consult-${timestamp.toISOString().replace(/[:.]/g, "-")}.${ext}`;

      const recording: SavedRecording = {
        id: crypto.randomUUID(),
        filename,
        blob: audioBlob,
        timestamp,
        duration,
        uploaded: false,
      };

      setSavedRecordings((prev) => [recording, ...prev]);
      setSaved(true);
    }
  }, [state, audioBlob, saved, duration]);

  // Reset saved flag wanneer nieuwe opname start
  useEffect(() => {
    if (state === "recording") {
      setSaved(false);
      setUploadError(null);
    }
  }, [state]);

  // ---------------------------------------------------------------------------
  // Waveform visualisatie
  // ---------------------------------------------------------------------------
  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    const analyser = analyserNode;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(dataArray);

      const { width, height } = canvas;
      ctx.fillStyle = "#f9fafb";
      ctx.fillRect(0, 0, width, height);

      ctx.lineWidth = 2;
      ctx.strokeStyle = "#dc2626";
      ctx.beginPath();

      const sliceWidth = width / bufferLength;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * height) / 2;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += sliceWidth;
      }

      ctx.lineTo(width, height / 2);
      ctx.stroke();
    };

    draw();
  }, [analyserNode]);

  useEffect(() => {
    if (state === "recording" && analyserNode) {
      drawWaveform();
    } else {
      cancelAnimationFrame(animFrameRef.current);
    }
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [state, analyserNode, drawWaveform]);

  // ---------------------------------------------------------------------------
  // Download opname lokaal (fallback / backup)
  // ---------------------------------------------------------------------------
  const handleDownload = (blob?: Blob, filename?: string) => {
    const targetBlob = blob || audioBlob;
    if (!targetBlob) return;

    const ext = targetBlob.type.includes("webm") ? "webm" : "m4a";
    const name =
      filename ||
      `consult-${new Date().toISOString().replace(/[:.]/g, "-")}.${ext}`;

    const url = URL.createObjectURL(targetBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // ---------------------------------------------------------------------------
  // Upload naar backend
  // ---------------------------------------------------------------------------
  const handleUpload = async (blob?: Blob) => {
    const targetBlob = blob || audioBlob;
    if (!targetBlob) return;

    setUploading(true);
    setUploadError(null);

    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const ext = targetBlob.type.includes("webm") ? "webm" : "m4a";
      const file = new File([targetBlob], `consult-${timestamp}.${ext}`, {
        type: targetBlob.type,
      });

      const formData = new FormData();
      formData.append("file", file);

      const apiUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("ca_token")
          : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch(`${apiUrl}/api/consult/upload`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload mislukt (${response.status})`);
      }

      const data = await response.json();

      // Markeer opname als geüpload
      setSavedRecordings((prev) =>
        prev.map((r) =>
          r.blob === targetBlob ? { ...r, uploaded: true } : r
        )
      );

      onComplete(data.session_id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Upload mislukt";

      // Geef duidelijke melding bij connection refused
      if (
        message.includes("ERR_CONNECTION_REFUSED") ||
        message.includes("Failed to fetch") ||
        message.includes("NetworkError")
      ) {
        setUploadError(
          "Backend niet bereikbaar. De opname is lokaal opgeslagen - je kunt het bestand downloaden of later opnieuw proberen."
        );
      } else {
        setUploadError(message);
      }
    } finally {
      setUploading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60)
      .toString()
      .padStart(2, "0");
    const s = (seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const error = recorderError || uploadError;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="space-y-4">
      {/* Hoofdkaart: Recorder */}
      <div className="bg-white rounded-lg shadow p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Consult opnemen
            </h2>
            <p className="text-sm text-gray-500">
              Neem het gesprek op en ontvang automatisch een SOEP-concept.
            </p>
          </div>
          {state !== "idle" && (
            <div className="flex items-center gap-2">
              {state === "recording" && (
                <span className="flex items-center gap-1.5 text-sm font-medium text-red-600">
                  <span className="w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse" />
                  Opname
                </span>
              )}
              {state === "paused" && (
                <span className="text-sm font-medium text-amber-600">
                  Gepauzeerd
                </span>
              )}
              {state === "stopped" && (
                <span className="flex items-center gap-1.5 text-sm font-medium text-green-600">
                  <CheckIcon />
                  Lokaal opgeslagen
                </span>
              )}
            </div>
          )}
        </div>

        {/* Microfoon selectie */}
        {state === "idle" && (
          <div className="mb-4 p-3 bg-gray-50 rounded-lg">
            <label
              htmlFor="mic-select"
              className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-2"
            >
              <MicSettingsIcon />
              Microfoon
            </label>
            {devicesLoading ? (
              <p className="text-sm text-gray-400">Apparaten laden...</p>
            ) : devices.length === 0 ? (
              <p className="text-sm text-amber-600">
                Geen microfoon gevonden. Sluit een microfoon aan en ververs de pagina.
              </p>
            ) : (
              <select
                id="mic-select"
                value={selectedDeviceId}
                onChange={(e) => selectDevice(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Standaard microfoon</option>
                {devices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* Timer */}
        <div className="text-center my-6">
          <div
            className={`text-5xl font-mono font-light tracking-wider ${
              state === "recording"
                ? "text-red-600"
                : state === "paused"
                ? "text-amber-600"
                : "text-gray-700"
            }`}
          >
            {formatTime(duration)}
          </div>
          {duration > 0 && state !== "idle" && (
            <p className="text-xs text-gray-400 mt-1">
              {state === "recording" && "Spreek duidelijk in de microfoon"}
              {state === "paused" && "Opname gepauzeerd - druk op hervat"}
              {state === "stopped" &&
                "Opname voltooid - klaar voor verwerking"}
            </p>
          )}
        </div>

        {/* Waveform */}
        {(state === "recording" || state === "paused") && (
          <div className="mb-6 bg-gray-50 rounded-lg p-2">
            <canvas
              ref={canvasRef}
              width={600}
              height={80}
              className="w-full h-20 rounded"
            />
          </div>
        )}

        {/* Audio preview na stop */}
        {state === "stopped" && audioUrl && (
          <div className="mb-6 bg-gray-50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm text-gray-600">Beluister de opname:</p>
              {audioBlob && (
                <span className="text-xs text-gray-400">
                  {formatFileSize(audioBlob.size)}
                </span>
              )}
            </div>
            <audio src={audioUrl} controls className="w-full" />
          </div>
        )}

        {/* Controls */}
        <div className="flex items-center justify-center gap-3">
          {/* IDLE: Start knop */}
          {state === "idle" && (
            <button
              onClick={start}
              className="flex items-center gap-2 px-8 py-4 bg-red-600 text-white rounded-full font-medium text-lg hover:bg-red-700 transition-colors shadow-lg hover:shadow-xl"
            >
              <MicIcon />
              Start opname
            </button>
          )}

          {/* RECORDING: Pauze + Stop */}
          {state === "recording" && (
            <>
              <button
                onClick={pause}
                className="flex items-center gap-2 px-5 py-3 bg-amber-100 text-amber-700 rounded-full font-medium hover:bg-amber-200 transition-colors"
              >
                <PauseIcon />
                Pauzeer
              </button>
              <button
                onClick={stop}
                className="flex items-center gap-2 px-5 py-3 bg-gray-800 text-white rounded-full font-medium hover:bg-gray-900 transition-colors"
              >
                <StopIcon />
                Stop opname
              </button>
            </>
          )}

          {/* PAUSED: Hervat + Stop */}
          {state === "paused" && (
            <>
              <button
                onClick={resume}
                className="flex items-center gap-2 px-5 py-3 bg-red-600 text-white rounded-full font-medium hover:bg-red-700 transition-colors"
              >
                <MicIcon />
                Hervat
              </button>
              <button
                onClick={stop}
                className="flex items-center gap-2 px-5 py-3 bg-gray-800 text-white rounded-full font-medium hover:bg-gray-900 transition-colors"
              >
                <StopIcon />
                Stop opname
              </button>
            </>
          )}

          {/* STOPPED: Verwerk + Download + Opnieuw */}
          {state === "stopped" && (
            <>
              <button
                onClick={() => handleUpload()}
                disabled={uploading || !audioBlob}
                className="flex items-center gap-2 px-8 py-4 bg-primary-600 text-white rounded-full font-medium text-lg hover:bg-primary-700 transition-colors shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {uploading ? (
                  <>
                    <span className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full" />
                    Uploaden...
                  </>
                ) : (
                  <>
                    <SendIcon />
                    Start SOEP-verwerking
                  </>
                )}
              </button>
              <button
                onClick={() => handleDownload()}
                disabled={!audioBlob}
                className="flex items-center gap-2 px-5 py-3 bg-blue-50 text-blue-700 rounded-full font-medium hover:bg-blue-100 transition-colors"
                title="Sla opname op als bestand"
              >
                <DownloadIcon />
                Download
              </button>
              <button
                onClick={reset}
                disabled={uploading}
                className="flex items-center gap-2 px-5 py-3 bg-gray-100 text-gray-700 rounded-full font-medium hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                <RetryIcon />
                Opnieuw
              </button>
            </>
          )}
        </div>

        {/* Error met fallback-acties */}
        {error && (
          <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-700">{error}</p>
            {uploadError && audioBlob && (
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => handleDownload()}
                  className="text-sm px-3 py-1.5 bg-white border border-red-200 text-red-700 rounded-md hover:bg-red-50 transition-colors"
                >
                  Download opname
                </button>
                <button
                  onClick={() => handleUpload()}
                  className="text-sm px-3 py-1.5 bg-white border border-red-200 text-red-700 rounded-md hover:bg-red-50 transition-colors"
                >
                  Opnieuw proberen
                </button>
              </div>
            )}
          </div>
        )}

        {/* Privacy notice */}
        <p className="mt-6 text-xs text-gray-400 text-center">
          Audio wordt volledig lokaal verwerkt en automatisch verwijderd na
          goedkeuring van het transcript.
        </p>
      </div>

      {/* Eerdere opnames (sessie) */}
      {savedRecordings.length > 0 && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Opnames deze sessie
          </h3>
          <div className="space-y-2">
            {savedRecordings.map((rec) => (
              <div
                key={rec.id}
                className="flex items-center justify-between py-2 px-3 bg-gray-50 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      rec.uploaded ? "bg-green-500" : "bg-amber-400"
                    }`}
                  />
                  <div>
                    <p className="text-sm text-gray-700">{rec.filename}</p>
                    <p className="text-xs text-gray-400">
                      {formatTime(rec.duration)} &middot;{" "}
                      {formatFileSize(rec.blob.size)} &middot;{" "}
                      {rec.timestamp.toLocaleTimeString("nl-NL", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                      {rec.uploaded && (
                        <span className="text-green-600 ml-1">
                          &middot; geüpload
                        </span>
                      )}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {!rec.uploaded && (
                    <button
                      onClick={() => handleUpload(rec.blob)}
                      disabled={uploading}
                      className="p-1.5 text-gray-400 hover:text-primary-600 rounded transition-colors"
                      title="Upload naar server"
                    >
                      <SendIcon />
                    </button>
                  )}
                  <button
                    onClick={() => handleDownload(rec.blob, rec.filename)}
                    className="p-1.5 text-gray-400 hover:text-blue-600 rounded transition-colors"
                    title="Download bestand"
                  >
                    <DownloadIcon />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Icons (inline SVG)
// ---------------------------------------------------------------------------
function MicIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function MicSettingsIcon() {
  return (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
      <circle cx="18" cy="18" r="3" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M18 15v1.5M18 20.5V22M15.4 16.4l1.06 1.06M19.54 20.54l1.06 1.06M15 18h1.5M20.5 18H22M15.4 19.6l1.06-1.06M19.54 15.46l1.06-1.06" />
    </svg>
  );
}
