/**
 * PatientInstructie component - Toont gegenereerde patientinstructie in eenvoudig Nederlands.
 */

"use client";

import { useState } from "react";

interface PatientInstructionProps {
  instruction: string;
  sessionId: string;
}

export default function PatientInstruction({ instruction, sessionId }: PatientInstructionProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(instruction);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handlePrint = () => {
    const printWindow = window.open("", "_blank");
    if (printWindow) {
      printWindow.document.write(`
        <html>
          <head>
            <title>Patientinstructie</title>
            <style>
              body { font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; line-height: 1.6; }
              h1 { font-size: 18px; border-bottom: 2px solid #333; padding-bottom: 8px; }
              .footer { margin-top: 40px; font-size: 12px; color: #666; border-top: 1px solid #ddd; padding-top: 8px; }
            </style>
          </head>
          <body>
            <h1>Informatie voor u</h1>
            <div>${instruction.replace(/\n/g, "<br>")}</div>
            <div class="footer">
              AI-Consultassistent - Dit document is gegenereerd ter ondersteuning van uw huisarts.
              Neem bij vragen altijd contact op met uw huisartsenpraktijk.
            </div>
          </body>
        </html>
      `);
      printWindow.document.close();
      printWindow.print();
    }
  };

  return (
    <div className="bg-white rounded-lg shadow border border-gray-200">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Patientinstructie</h3>
          <p className="text-xs text-gray-500">Eenvoudig Nederlands (B1-niveau)</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleCopy}
            className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            {copied ? "Gekopieerd!" : "Kopieer"}
          </button>
          <button
            onClick={handlePrint}
            className="px-3 py-1.5 text-xs font-medium bg-primary-100 text-primary-700 rounded-md hover:bg-primary-200 transition-colors"
          >
            Print
          </button>
        </div>
      </div>
      <div className="p-4">
        <div className="prose prose-sm max-w-none text-gray-700 whitespace-pre-wrap">
          {instruction}
        </div>
      </div>
    </div>
  );
}
