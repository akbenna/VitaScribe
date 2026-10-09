const fs = require("fs");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
        LevelFormat, BorderStyle, Header, Footer, PageNumber, PageBreak,
        Table, TableRow, TableCell, WidthType, ShadingType } = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function cell(text, opts = {}) {
  return new TableCell({
    borders,
    width: { size: opts.width || 4680, type: WidthType.DXA },
    shading: opts.header ? { fill: "059669", type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: [new Paragraph({
      children: [new TextRun({
        text, bold: opts.bold || opts.header, font: "Arial",
        size: opts.size || 22,
        color: opts.header ? "FFFFFF" : "1F2937",
      })]
    })]
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: "059669" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "1F2937" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "374151" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 } },
    ]
  },
  numbering: {
    config: [
      { reference: "steps",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [
    // ── TITLE PAGE ──
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      children: [
        new Paragraph({ spacing: { before: 3000 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "VitaScribe", font: "Arial", size: 56, bold: true, color: "059669" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "AI Consultassistent", font: "Arial", size: 32, color: "6B7280" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 600 },
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "059669", space: 8 } },
          children: [new TextRun({ text: " ", size: 12 })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [new TextRun({ text: "Installatiehandleiding", font: "Arial", size: 28, color: "1F2937" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 100 },
          children: [new TextRun({ text: "Chrome/Edge Extensie + Cloud API", font: "Arial", size: 22, color: "6B7280" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 1200 },
          children: [new TextRun({ text: "Versie 1.1.0  -  April 2026", font: "Arial", size: 20, color: "9CA3AF" })]
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "Vertrouwelijk - Alleen voor intern gebruik", font: "Arial", size: 18, italics: true, color: "9CA3AF" })]
        }),
      ]
    },

    // ── CONTENT ──
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
        }
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "059669", space: 4 } },
            children: [new TextRun({ text: "VitaScribe - Installatiehandleiding", font: "Arial", size: 16, color: "9CA3AF" })]
          })]
        })
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "Pagina ", font: "Arial", size: 16, color: "9CA3AF" }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "9CA3AF" }),
            ]
          })]
        })
      },
      children: [

        // ── Wat is VitaScribe ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Wat is VitaScribe?")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "VitaScribe is een AI-consultassistent voor de huisartsenpraktijk. Het neemt het gesprek tussen arts en pati\u00EBnt op via de microfoon, transcribeert de audio met Deepgram, en genereert automatisch een SOEP-notitie met ICPC-code via Mistral AI. De resultaten kunnen met \u00E9\u00E9n klik in Bricks Huisarts worden ingevoegd.",
            font: "Arial", size: 22
          })]
        }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "De extensie werkt in Google Chrome en Microsoft Edge. Alle AI-verwerking gebeurt via een beveiligde cloud API - er hoeft niets lokaal ge\u00EFnstalleerd te worden behalve de extensie zelf.",
            font: "Arial", size: 22
          })]
        }),

        // ── Wat heb je nodig ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Wat heb je nodig?")] }),

        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [3000, 6026],
          rows: [
            new TableRow({ children: [
              cell("Onderdeel", { width: 3000, header: true }),
              cell("Details", { width: 6026, header: true }),
            ]}),
            new TableRow({ children: [
              cell("Browser", { width: 3000, bold: true }),
              cell("Google Chrome of Microsoft Edge (actuele versie)", { width: 6026 }),
            ]}),
            new TableRow({ children: [
              cell("Microfoon", { width: 3000, bold: true }),
              cell("Ingebouwde laptop-mic of externe USB-microfoon", { width: 6026 }),
            ]}),
            new TableRow({ children: [
              cell("Internetverbinding", { width: 3000, bold: true }),
              cell("Nodig voor de cloud API (audio wordt verwerkt en direct verwijderd)", { width: 6026 }),
            ]}),
            new TableRow({ children: [
              cell("Bricks Huisarts", { width: 3000, bold: true }),
              cell("Webversie (bfrcloud.com, bfrnet.nl, bricks-huisarts.nl, of bfrw.nl)", { width: 6026 }),
            ]}),
          ]
        }),

        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // ── INSTALLATIE ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Installatie (2 minuten)")] }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Stap 1: Extensie-bestanden verkrijgen")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "Je ontvangt de map chrome-extension/ als ZIP-bestand of via een USB-stick. Pak het ZIP-bestand uit naar een vaste locatie op je computer, bijvoorbeeld:",
            font: "Arial", size: 22,
          })]
        }),
        new Paragraph({
          spacing: { after: 200 },
          shading: { fill: "F3F4F6", type: ShadingType.CLEAR },
          indent: { left: 360 },
          children: [new TextRun({ text: "C:\\VitaScribe\\chrome-extension\\", font: "Consolas", size: 20, color: "059669" })]
        }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "Belangrijk: verplaats of verwijder deze map niet na installatie. De browser verwijst ernaar.",
            font: "Arial", size: 22, italics: true, color: "DC2626",
          })]
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Stap 2: Extensie laden in de browser")] }),

        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Open de extensie-pagina:", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          spacing: { after: 120 },
          indent: { left: 720 },
          children: [
            new TextRun({ text: "Chrome: ", font: "Arial", size: 22, bold: true }),
            new TextRun({ text: "chrome://extensions", font: "Consolas", size: 20, color: "059669" }),
          ]
        }),
        new Paragraph({
          spacing: { after: 120 },
          indent: { left: 720 },
          children: [
            new TextRun({ text: "Edge: ", font: "Arial", size: 22, bold: true }),
            new TextRun({ text: "edge://extensions", font: "Consolas", size: 20, color: "059669" }),
          ]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Zet Ontwikkelaarsmodus aan (schakelaar rechtsboven)", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik op Uitgepakte extensie laden (of Load unpacked)", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 200 },
          children: [new TextRun({ text: "Selecteer de chrome-extension/ map", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "VitaScribe verschijnt nu als icoon in je browserbalk.",
            font: "Arial", size: 22,
          })]
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Stap 3: Verbinding instellen")] }),

        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik op het VitaScribe-icoon in de browserbalk", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik op het tandwiel-icoon (instellingen)", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Vul de API URL in:", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          spacing: { after: 120 },
          indent: { left: 720 },
          shading: { fill: "F3F4F6", type: ShadingType.CLEAR },
          children: [new TextRun({ text: "https://smartvoice-production.up.railway.app", font: "Consolas", size: 20, color: "059669" })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Vul de API Key in (ontvang je van de beheerder)", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik Opslaan en daarna Test verbinding", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({ text: "Je ziet \"Verbinding OK!\" als alles goed staat.", font: "Arial", size: 22 })]
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ── GEBRUIK ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Gebruik")] }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Op de Bricks-pagina (aanbevolen)")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "Wanneer je Bricks opent, verschijnt rechtsonder een groene microfoon-knop. Dit is de VitaScribe-widget.",
            font: "Arial", size: 22,
          })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik op de groene knop - het VitaScribe-paneel opent", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik Start opname voordat het consult begint", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Voer het consult uit zoals gewoonlijk", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Klik Stop & verwerk na het consult", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 120 },
          children: [new TextRun({ text: "Controleer de SOEP-notitie en decisief regel", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "steps", level: 0 },
          spacing: { after: 200 },
          children: [new TextRun({ text: "Klik Invoegen in Bricks - de velden worden automatisch gevuld", font: "Arial", size: 22 })]
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Via de popup (overal)")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "Klik op het VitaScribe-icoon in de browserbalk. De popup bevat dezelfde opname- en verwerkingsfunctionaliteit. Handig als je niet op een Bricks-pagina zit. Resultaten worden automatisch beschikbaar in de widget zodra je Bricks opent.",
            font: "Arial", size: 22,
          })]
        }),

        // ── PRIVACY ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Privacy en beveiliging")] }),

        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          spacing: { after: 100 },
          children: [new TextRun({ text: "Audio wordt na verwerking direct verwijderd - niets wordt opgeslagen", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          spacing: { after: 100 },
          children: [new TextRun({ text: "Alle communicatie verloopt via HTTPS (versleuteld)", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          spacing: { after: 100 },
          children: [new TextRun({ text: "API-toegang is beveiligd met een unieke sleutel per werkplek", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          spacing: { after: 100 },
          children: [new TextRun({ text: "Geen pati\u00EBntgegevens worden opgeslagen in de cloud", font: "Arial", size: 22 })]
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          spacing: { after: 200 },
          children: [new TextRun({ text: "STT (Deepgram) en LLM (Mistral) zijn AVG-conforme EU-providers", font: "Arial", size: 22 })]
        }),

        // ── PROBLEMEN ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Veelgestelde problemen")] }),

        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [3500, 5526],
          rows: [
            new TableRow({ children: [
              cell("Probleem", { width: 3500, header: true }),
              cell("Oplossing", { width: 5526, header: true }),
            ]}),
            new TableRow({ children: [
              cell("Microfoon wordt niet gevonden", { width: 3500, bold: true }),
              cell("Controleer of de browser toestemming heeft voor de microfoon. Ga naar Instellingen > Privacy > Microfoon.", { width: 5526 }),
            ]}),
            new TableRow({ children: [
              cell("\"Geen spraak gedetecteerd\"", { width: 3500, bold: true }),
              cell("Zorg dat je eigen stem gebruikt (geen systeemaudio). Spreek minstens 5 seconden.", { width: 5526 }),
            ]}),
            new TableRow({ children: [
              cell("Test verbinding mislukt", { width: 3500, bold: true }),
              cell("Controleer de API URL en API Key in de instellingen. Controleer je internetverbinding.", { width: 5526 }),
            ]}),
            new TableRow({ children: [
              cell("Widget verschijnt niet op Bricks", { width: 3500, bold: true }),
              cell("Herlaad de Bricks-pagina (F5). Controleer of de extensie actief is in edge://extensions.", { width: 5526 }),
            ]}),
            new TableRow({ children: [
              cell("SOEP-velden worden niet gevuld", { width: 3500, bold: true }),
              cell("Gebruik de Kopieer-knop als fallback. Pas eventueel de CSS-selectors aan in de instellingen.", { width: 5526 }),
            ]}),
          ]
        }),

        new Paragraph({ spacing: { after: 200 }, children: [] }),

        // ── CONTACT ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Contact en ondersteuning")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun({
            text: "Bij technische problemen of vragen, neem contact op met de beheerder. Vermeld altijd welke browser je gebruikt, de foutmelding (indien aanwezig), en het tijdstip waarop het probleem optrad.",
            font: "Arial", size: 22,
          })]
        }),
      ]
    }
  ]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("VitaScribe-Installatiehandleiding.docx", buffer);
  console.log("Klaar: VitaScribe-Installatiehandleiding.docx");
});
