"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import LoginPage from "@/components/LoginPage";
import AudioUpload from "@/components/AudioUpload";
import ConsultRecorder from "@/components/ConsultRecorder";
import SOEPEditor from "@/components/SOEPEditor";
import DetectionPanel from "@/components/DetectionPanel";
import TranscriptViewer from "@/components/TranscriptViewer";
import PatientInstruction from "@/components/PatientInstruction";
import { api } from "@/lib/api";
import type { SOEPConcept, DetectionResult, TranscriptSegment } from "@/lib/api";

type AppState = "input" | "processing" | "review" | "approved";
type InputMode = "record" | "upload";

export default function Home() {
  const { user, isLoading, logout } = useAuth();
  const [state, setState] = useState<AppState>("input");
  const [inputMode, setInputMode] = useState<InputMode>("record");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [soep, setSoep] = useState<SOEPConcept | null>(null);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);
  const [patientInstruction, setPatientInstruction] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Toon laadscherm
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full" />
      </div>
    );
  }

  // Toon login als niet ingelogd
  if (!user) return <LoginPage />;

  const pollStatus = async (sid: string) => {
    const wsUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001")
      .replace("http", "ws");

    // Probeer WebSocket, val terug op polling
    try {
      const ws = new WebSocket(`${wsUrl}/ws/consult/${sid}`);

      ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        if (data.status === "reviewing" || data.status === "approved") {
          ws.close();
          await loadResults(sid);
        } else if (data.status === "failed") {
          ws.close();
          setError("Verwerking mislukt. Probeer het opnieuw.");
          setState("input");
        }
      };

      ws.onerror = () => {
        ws.close();
        fallbackPolling(sid);
      };

      // Timeout na 5 minuten
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.close();
          setError("Verwerking duurt te lang.");
          setState("input");
        }
      }, 300000);
    } catch {
      fallbackPolling(sid);
    }
  };

  const loadResults = async (sid: string) => {
    const [soepData, detectionData, transcriptData] = await Promise.all([
      api.getSOEP(sid),
      api.getDetection(sid),
      api.getTranscript(sid).catch(() => ({ segments: [], raw_text: "" })),
    ]);
    setSoep(soepData);
    setDetection(detectionData);
    setTranscript(transcriptData.segments || []);
    setState("review");
  };

  const fallbackPolling = async (sid: string) => {
    for (let i = 0; i < 60; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const status = await api.getStatus(sid);
        if (status.status === "reviewing" || status.status === "approved") {
          await loadResults(sid);
          return;
        }
        if (status.status === "failed") {
          setError("Verwerking mislukt. Probeer het opnieuw.");
          setState("input");
          return;
        }
      } catch { /* retry */ }
    }
    setError("Verwerking duurt te lang.");
    setState("input");
  };

  const handleUploadComplete = (newSessionId: string) => {
    setSessionId(newSessionId);
    setState("processing");
    setError(null);
    pollStatus(newSessionId);
  };

  const handleApprove = async () => {
    if (!sessionId || !soep) return;
    try {
      await api.approveSOEP(sessionId, soep, []);
      setState("approved");
    } catch {
      setError("Goedkeuring mislukt. Probeer het opnieuw.");
    }
  };

  const handleExport = async (target: "clipboard" | "api") => {
    if (!sessionId) return;
    try {
      const result = await api.exportToHIS(sessionId, target) as { export_text?: string };
      if (target === "clipboard" && result.export_text) {
        navigator.clipboard.writeText(result.export_text);
      }
    } catch {
      setError("Export mislukt.");
    }
  };

  const handleReset = () => {
    setState("input");
    setSessionId(null);
    setSoep(null);
    setDetection(null);
    setTranscript([]);
    setPatientInstruction("");
    setError(null);
  };

  return (
    <>
      {/* Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">AI</span>
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gray-900">
                AI-Consultassistent
              </h1>
              <p className="text-xs text-gray-500">
                SOEP-dossiervoering Review
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <span className="text-sm font-medium text-gray-700">{user.display_name}</span>
              <span className="block text-xs text-gray-400">{user.role}</span>
            </div>
            <button
              onClick={logout}
              className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100"
            >
              Uitloggen
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Error melding */}
        {error && (
          <div className="bg-danger-50 border border-danger-200 text-danger-600 px-4 py-3 rounded-lg text-sm">
            {error}
            <button onClick={() => setError(null)} className="ml-2 underline">Sluiten</button>
          </div>
        )}

        {/* Status bar */}
        <div className="flex items-center gap-2 text-sm">
          <Step label="1. Invoer" active={state === "input"} done={state !== "input"} />
          <Connector />
          <Step label="2. Verwerking" active={state === "processing"} done={state === "review" || state === "approved"} />
          <Connector />
          <Step label="3. Review" active={state === "review"} done={state === "approved"} />
          <Connector />
          <Step label="4. Goedgekeurd" active={state === "approved"} done={false} />
        </div>

        {/* Input: Opnemen of Uploaden */}
        {state === "input" && (
          <div>
            {/* Mode toggle */}
            <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1 w-fit mb-4">
              <button
                onClick={() => setInputMode("record")}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  inputMode === "record"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="23" />
                  <line x1="8" y1="23" x2="16" y2="23" />
                </svg>
                Opnemen
              </button>
              <button
                onClick={() => setInputMode("upload")}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  inputMode === "upload"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Bestand uploaden
              </button>
            </div>

            {/* Recorder of Upload component */}
            {inputMode === "record" ? (
              <ConsultRecorder onComplete={handleUploadComplete} />
            ) : (
              <AudioUpload onComplete={handleUploadComplete} />
            )}
          </div>
        )}

        {/* Processing */}
        {state === "processing" && (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin w-12 h-12 border-4 border-primary-200 border-t-primary-600 rounded-full mx-auto mb-4" />
            <h2 className="text-lg font-semibold text-gray-900">Verwerking bezig...</h2>
            <p className="text-gray-500 mt-2">
              Audio wordt getranscribeerd en geanalyseerd. Dit duurt enkele minuten.
            </p>
          </div>
        )}

        {/* Review */}
        {state === "review" && soep && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              <SOEPEditor soep={soep} onChange={setSoep} onApprove={handleApprove} />
              <TranscriptViewer segments={transcript} />
              {patientInstruction && sessionId && (
                <PatientInstruction instruction={patientInstruction} sessionId={sessionId} />
              )}
            </div>
            <div>
              <DetectionPanel detection={detection} />
            </div>
          </div>
        )}

        {/* Approved */}
        {state === "approved" && (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="w-16 h-16 bg-success-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-success-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900">SOEP goedgekeurd</h2>
            <p className="text-gray-500 mt-2">Het SOEP-verslag is opgeslagen en klaar voor export naar het HIS.</p>
            <div className="mt-6 flex gap-3 justify-center">
              <button
                onClick={() => handleExport("clipboard")}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
              >
                Kopieer naar klembord
              </button>
              <button
                onClick={handleReset}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
              >
                Nieuw consult
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 mt-auto">
        <div className="max-w-7xl mx-auto px-4 py-3 text-center text-xs text-gray-400">
          AI-Consultassistent v0.1.0 - Volledig lokale verwerking - NEN 7510/7513 conform
        </div>
      </footer>
    </>
  );
}

function Step({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span
      className={`px-3 py-1 rounded-full text-xs font-medium ${
        active
          ? "bg-primary-100 text-primary-700 ring-2 ring-primary-500"
          : done
          ? "bg-success-100 text-success-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      {label}
    </span>
  );
}

function Connector() {
  return <div className="w-8 h-px bg-gray-300" />;
}
