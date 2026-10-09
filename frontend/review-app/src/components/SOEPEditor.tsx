"use client";

import { useState } from "react";
import type { SOEPConcept } from "@/lib/api";

interface SOEPEditorProps {
  soep: SOEPConcept;
  onChange: (soep: SOEPConcept) => void;
  onApprove: () => void;
}

const SOEP_LABELS: Record<string, { label: string; description: string; color: string }> = {
  S: {
    label: "Subjectief",
    description: "Klachtpresentatie vanuit patientperspectief",
    color: "blue",
  },
  O: {
    label: "Objectief",
    description: "Bevindingen bij onderzoek",
    color: "green",
  },
  E: {
    label: "Evaluatie",
    description: "Werkdiagnose + differentiaaldiagnosen",
    color: "amber",
  },
  P: {
    label: "Plan",
    description: "Medicatie, verwijzingen, onderzoek, controle",
    color: "purple",
  },
};

export default function SOEPEditor({ soep, onChange, onApprove }: SOEPEditorProps) {
  const [editingField, setEditingField] = useState<string | null>(null);

  const handleFieldChange = (field: string, value: string) => {
    onChange({ ...soep, [field]: value });
  };

  const colorClasses: Record<string, string> = {
    blue: "border-l-blue-500 bg-blue-50",
    green: "border-l-green-500 bg-green-50",
    amber: "border-l-amber-500 bg-amber-50",
    purple: "border-l-purple-500 bg-purple-50",
  };

  const badgeClasses: Record<string, string> = {
    blue: "bg-blue-100 text-blue-800",
    green: "bg-green-100 text-green-800",
    amber: "bg-amber-100 text-amber-800",
    purple: "bg-purple-100 text-purple-800",
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">SOEP-concept</h2>
          {soep.confidence && (
            <p className="text-xs text-gray-500 mt-1">
              Confidence: {(soep.confidence * 100).toFixed(0)}%
              {soep.icpc_code && ` | ICPC: ${soep.icpc_code} - ${soep.icpc_titel}`}
            </p>
          )}
        </div>
        <button
          onClick={onApprove}
          className="px-4 py-2 bg-success-600 text-white rounded-lg font-medium hover:bg-success-500 text-sm"
        >
          Goedkeuren
        </button>
      </div>

      <div className="p-4 space-y-4">
        {(["S", "O", "E", "P"] as const).map((field) => {
          const meta = SOEP_LABELS[field];
          const isEditing = editingField === field;
          const value = soep[field];

          return (
            <div
              key={field}
              className={`border-l-4 rounded-r-lg p-4 ${colorClasses[meta.color]}`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-0.5 rounded ${badgeClasses[meta.color]}`}>
                    {field}
                  </span>
                  <span className="text-sm font-medium text-gray-700">
                    {meta.label}
                  </span>
                </div>
                <button
                  onClick={() => setEditingField(isEditing ? null : field)}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  {isEditing ? "Klaar" : "Bewerken"}
                </button>
              </div>

              {isEditing ? (
                <textarea
                  value={value}
                  onChange={(e) => handleFieldChange(field, e.target.value)}
                  className="w-full p-2 border border-gray-300 rounded text-sm bg-white min-h-[80px] focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  autoFocus
                />
              ) : (
                <p className="text-sm text-gray-800 whitespace-pre-wrap">
                  {value || <span className="italic text-gray-400">Geen data</span>}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
