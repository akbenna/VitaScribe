/**
 * API Client - AI-Consultassistent
 * Typed fetch wrapper met JWT authenticatie.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ca_token");
}

async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    // Token verlopen: uitloggen
    localStorage.removeItem("ca_token");
    localStorage.removeItem("ca_user");
    window.location.reload();
    throw new Error("Sessie verlopen");
  }

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error ${response.status}: ${error}`);
  }

  return response.json();
}

// --- Types ---

export interface ConsultStartResponse {
  session_id: string;
  status: string;
}

export interface ConsultStatus {
  session_id: string;
  status: string;
  steps: {
    transcription: string;
    extraction: string;
    soep_generation: string;
    detection: string;
  };
}

export interface SOEPConcept {
  S: string;
  O: string;
  E: string;
  P: string;
  icpc_code: string | null;
  icpc_titel: string | null;
  confidence: number | null;
}

export interface RedFlag {
  id: string;
  ernst: string;
  categorie: string;
  beschrijving: string;
  nhg_referentie: string | null;
}

export interface MissingInfo {
  id: string;
  veld: string;
  beschrijving: string;
  prioriteit: string;
}

export interface DetectionResult {
  rode_vlaggen: RedFlag[];
  ontbrekende_info: MissingInfo[];
}

export interface TranscriptSegment {
  spreker: string;
  start: number;
  eind: number;
  tekst: string;
  confidence: number;
}

export interface ConsultListItem {
  id: string;
  status: string;
  started_at: string | null;
  patient_hash: string;
}

// --- API Calls ---

export const api = {
  health: () => fetchAPI<{ status: string; version: string }>("/health"),

  startConsult: (patientHash: string) =>
    fetchAPI<ConsultStartResponse>("/api/consult/start", {
      method: "POST",
      body: JSON.stringify({ patient_hash: patientHash }),
    }),

  stopConsult: (sessionId: string) =>
    fetchAPI<{ session_id: string; status: string }>(
      `/api/consult/${sessionId}/stop`,
      { method: "POST" }
    ),

  uploadAudio: async (file: File, patientHash: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("patient_hash", patientHash);

    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(`${API_BASE}/api/consult/upload`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
    return response.json();
  },

  getStatus: (sessionId: string) =>
    fetchAPI<ConsultStatus>(`/api/consult/${sessionId}/status`),

  getTranscript: (sessionId: string) =>
    fetchAPI<{ session_id: string; segments: TranscriptSegment[]; raw_text: string }>(
      `/api/consult/${sessionId}/transcript`
    ),

  getSOEP: (sessionId: string) =>
    fetchAPI<SOEPConcept>(`/api/consult/${sessionId}/soep`),

  getDetection: (sessionId: string) =>
    fetchAPI<DetectionResult>(`/api/consult/${sessionId}/detection`),

  approveSOEP: (sessionId: string, soep: SOEPConcept, corrections: object[]) =>
    fetchAPI(`/api/consult/${sessionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ soep_final: soep, corrections }),
    }),

  exportToHIS: (sessionId: string, target: "clipboard" | "api" = "clipboard") =>
    fetchAPI(`/api/consult/${sessionId}/export`, {
      method: "POST",
      body: JSON.stringify({ target }),
    }),

  listConsults: (limit = 20, offset = 0) =>
    fetchAPI<{ consults: ConsultListItem[]; total: number }>(
      `/api/consults?limit=${limit}&offset=${offset}`
    ),
};
