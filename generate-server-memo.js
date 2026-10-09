const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, PageBreak, LevelFormat
} = require("docx");

// === COLORS ===
const DARK = "1A1A2E";
const ACCENT = "0F7B6C";
const ACCENT_LIGHT = "E8F5F1";
const GRAY = "F5F5F5";
const BORDER_COLOR = "CCCCCC";
const WHITE = "FFFFFF";

// === HELPERS ===
const border = { style: BorderStyle.SINGLE, size: 1, color: BORDER_COLOR };
const borders = { top: border, bottom: border, left: border, right: border };
const noBorders = {
  top: { style: BorderStyle.NONE, size: 0 },
  bottom: { style: BorderStyle.NONE, size: 0 },
  left: { style: BorderStyle.NONE, size: 0 },
  right: { style: BorderStyle.NONE, size: 0 },
};
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: ACCENT, type: ShadingType.CLEAR },
    margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, font: "Arial", size: 20, color: WHITE })] })],
  });
}

function cell(text, width, opts = {}) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: opts.shading ? { fill: opts.shading, type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: [new Paragraph({
      children: [new TextRun({ text, font: "Arial", size: 20, bold: opts.bold || false, color: opts.color || DARK })],
      alignment: opts.align || AlignmentType.LEFT,
    })],
  });
}

function spacer(size = 120) {
  return new Paragraph({ spacing: { after: size }, children: [] });
}

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 200 },
    children: [new TextRun({ text, bold: true, font: "Arial", size: 32, color: ACCENT })],
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 280, after: 160 },
    children: [new TextRun({ text, bold: true, font: "Arial", size: 26, color: DARK })],
  });
}

function bodyText(text) {
  return new Paragraph({
    spacing: { after: 160, line: 300 },
    children: [new TextRun({ text, font: "Arial", size: 21 })],
  });
}

function boldBodyText(label, text) {
  return new Paragraph({
    spacing: { after: 160, line: 300 },
    children: [
      new TextRun({ text: label, font: "Arial", size: 21, bold: true }),
      new TextRun({ text, font: "Arial", size: 21 }),
    ],
  });
}

// === DOCUMENT ===

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 21 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: ACCENT },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: DARK },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  sections: [
    // ===== TITLE PAGE =====
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      children: [
        spacer(2400),
        new Paragraph({
          alignment: AlignmentType.LEFT,
          children: [new TextRun({ text: "TECHNISCHE MEMO", font: "Arial", size: 52, bold: true, color: ACCENT })],
        }),
        spacer(200),
        new Paragraph({
          alignment: AlignmentType.LEFT,
          spacing: { after: 120 },
          children: [new TextRun({ text: "Eigen AI-server in de huisartsenpraktijk", font: "Arial", size: 36, color: DARK })],
        }),
        new Paragraph({
          alignment: AlignmentType.LEFT,
          spacing: { after: 120 },
          children: [new TextRun({ text: "Business case voor lokale AI-infrastructuur", font: "Arial", size: 26, color: "666666" })],
        }),
        spacer(600),
        new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 6, color: ACCENT, space: 1 } },
          spacing: { before: 200, after: 100 },
          children: [],
        }),
        new Paragraph({
          spacing: { after: 60 },
          children: [new TextRun({ text: "Auteur: A.K. Benna, huisarts", font: "Arial", size: 22, color: "444444" })],
        }),
        new Paragraph({
          spacing: { after: 60 },
          children: [new TextRun({ text: "Datum: april 2026", font: "Arial", size: 22, color: "444444" })],
        }),
        new Paragraph({
          spacing: { after: 60 },
          children: [new TextRun({ text: "Status: Intern werkdocument - niet voor publicatie", font: "Arial", size: 22, color: "444444" })],
        }),
        new Paragraph({
          spacing: { after: 60 },
          children: [new TextRun({ text: "Versie: 1.0", font: "Arial", size: 22, color: "444444" })],
        }),
      ],
    },

    // ===== MAIN CONTENT =====
    {
      properties: {
        page: {
          size: { width: 11906, height: 16838 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "Technische Memo - Eigen AI-server", font: "Arial", size: 16, color: "999999", italics: true })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [
              new TextRun({ text: "Pagina ", font: "Arial", size: 16, color: "999999" }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 16, color: "999999" }),
            ],
          })],
        }),
      },
      children: [
        // ===== 1. MANAGEMENTSAMENVATTING =====
        heading1("1. Managementsamenvatting"),
        bodyText(
          "Dit document onderbouwt de investering in een eigen AI-server voor de huisartsenpraktijk. " +
          "De server bedient meerdere producten - VitaScribe (consultdocumentatie), ProVita Care (telehealth/leefstijl), " +
          "website-AI en toekomstige toepassingen - vanuit \u00e9\u00e9n lokale machine. De kernvoordelen zijn: " +
          "volledige privacygarantie (geen pati\u00ebntdata verlaat het gebouw), onafhankelijkheid van externe leveranciers " +
          "en abonnementen, en structureel lagere kosten na de initi\u00eble investering."
        ),
        bodyText(
          "De geschatte eenmalige investering bedraagt \u20ac1.500\u2013\u20ac3.500 afhankelijk van de gekozen configuratie. " +
          "De doorlopende kosten zijn \u20ac15\u2013\u20ac25 per maand (elektriciteit). Ter vergelijking: commerci\u00eble " +
          "alternatieven kosten \u20ac100\u2013\u20ac300 per maand aan abonnementen, exclusief afhankelijkheid van derde partijen " +
          "voor de verwerking van medische data."
        ),

        // ===== 2. PRODUCTOVERZICHT =====
        heading1("2. Producten op de server"),

        heading2("2.1 VitaScribe - AI-Consultassistent"),
        bodyText(
          "VitaScribe neemt consultaudio op via een Chrome-extensie, transcribeert de spraak met Faster-Whisper " +
          "(Large v3 Turbo), en genereert SOEP-documentatie via een lokaal LLM (Ollama/Llama 3.3 8B). " +
          "De output wordt direct in Bricks HIS ge\u00efnjecteerd. De pipeline omvat spraakherkenning (STT), " +
          "sprekerdiarisatie (PyAnnote), medische extractie, SOEP-generatie, en rode-vlaggendetectie."
        ),
        boldBodyText("GPU-belasting: ", "Whisper Large v3 Turbo vereist ~6 GB VRAM. Llama 3.3 8B (Q4) vereist ~5\u20136 GB VRAM. " +
          "Verwerkingstijd per consult: 30\u201390 seconden (STT + LLM). Piekbelasting: sequentieel, niet continu."),

        heading2("2.2 ProVita Care - Telehealth Platform"),
        bodyText(
          "ProVita Care is een telehealth-platform voor leefstijlinterventies (GLI, CVRM, obesitas). " +
          "Het platform gebruikt AI voor het genereren van gepersonaliseerde behandelplannen op basis van " +
          "SCORE2/FINDRISC/EOSS-risicoscores. Momenteel draait de AI-component via de Claude API (cloud). " +
          "Door over te stappen op een lokaal LLM (bijv. Llama 3.3 70B of Qwen 32B) vervalt de " +
          "afhankelijkheid van Anthropic\u2019s cloud \u00e9n de bijbehorende API-kosten."
        ),
        boldBodyText("GPU-belasting: ", "Behandelplangeneratie is niet tijdkritisch (arts reviewt achteraf). " +
          "Een groter model (32B\u201370B) is hier wenselijk voor kwaliteit. Bij 70B Q4 is ~40 GB VRAM nodig - " +
          "dit past niet op een consumentenkaart. Met 32B Q4 (~20 GB VRAM) is een RTX 4090 of RTX 5070 Ti toereikend."),

        heading2("2.3 Website-AI - Pati\u00ebntcommunicatie"),
        bodyText(
          "Een AI-chatbot op de praktijkwebsite die veelgestelde vragen beantwoordt, triageinformatie geeft, " +
          "en pati\u00ebnten doorgeleidt naar de juiste zorgverlener. Dit vereist een lichtgewicht model (7\u20138B) " +
          "met lage latency. De chatbot draait als API-endpoint op dezelfde server en wordt via een widget " +
          "op de website aangeroepen."
        ),
        boldBodyText("GPU-belasting: ", "Minimaal. Korte prompts, korte antwoorden. Een 8B-model genereert een antwoord in <2 seconden. " +
          "Concurrent gebruik met VitaScribe is mogelijk omdat de website-chatbot kleine batches verwerkt."),

        heading2("2.4 Toekomstige toepassingen"),
        bodyText(
          "De server kan ook dienen als platform voor: automatische verwijsbrieven genereren op basis van het " +
          "dossier, e-learning contentgeneratie voor praktijkscholingen, analyse van declaratiedata en " +
          "praktijkstatistieken, en het draaien van een lokale RAG-pipeline (Retrieval Augmented Generation) " +
          "over NHG-standaarden en praktijkprotocollen. Al deze toepassingen gebruiken dezelfde LLM-infrastructuur."
        ),

        // ===== 3. HARDWARECONFIGURATIES =====
        heading1("3. Hardwareconfiguraties"),

        bodyText(
          "Hieronder drie configuraties, oplopend in capaciteit. De keuze hangt af van het aantal " +
          "producten dat gelijktijdig draait en de gewenste modelgrootte."
        ),

        // Config table
        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [2200, 2275, 2275, 2276],
          rows: [
            new TableRow({
              children: [
                headerCell("Component", 2200),
                headerCell("Basis (\u20ac1.500)", 2275),
                headerCell("Aanbevolen (\u20ac2.500)", 2275),
                headerCell("Pro (\u20ac3.500)", 2276),
              ],
            }),
            new TableRow({
              children: [
                cell("GPU", 2200, { bold: true }),
                cell("RTX 4060 Ti 16GB", 2275),
                cell("RTX 4070 Ti Super 16GB", 2275),
                cell("RTX 4090 24GB", 2276),
              ],
            }),
            new TableRow({
              children: [
                cell("VRAM", 2200, { bold: true }),
                cell("16 GB GDDR6", 2275, { shading: GRAY }),
                cell("16 GB GDDR6X", 2275, { shading: GRAY }),
                cell("24 GB GDDR6X", 2276, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("CPU", 2200, { bold: true }),
                cell("AMD Ryzen 5 7600", 2275),
                cell("AMD Ryzen 7 7700X", 2275),
                cell("AMD Ryzen 9 7900X", 2276),
              ],
            }),
            new TableRow({
              children: [
                cell("RAM", 2200, { bold: true }),
                cell("32 GB DDR5", 2275, { shading: GRAY }),
                cell("64 GB DDR5", 2275, { shading: GRAY }),
                cell("64 GB DDR5", 2276, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Opslag", 2200, { bold: true }),
                cell("1 TB NVMe SSD", 2275),
                cell("2 TB NVMe SSD", 2275),
                cell("2 TB NVMe + 2 TB backup", 2276),
              ],
            }),
            new TableRow({
              children: [
                cell("Formaat", 2200, { bold: true }),
                cell("Mini-ITX / SFF", 2275, { shading: GRAY }),
                cell("Micro-ATX", 2275, { shading: GRAY }),
                cell("ATX tower / rack", 2276, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Max. model", 2200, { bold: true }),
                cell("14B (Q4)", 2275),
                cell("14B (Q6) / 32B (Q4)", 2275),
                cell("32B (Q6) / 70B (Q4)", 2276),
              ],
            }),
            new TableRow({
              children: [
                cell("Whisper snelheid", 2200, { bold: true }),
                cell("~15x realtime", 2275, { shading: GRAY }),
                cell("~25x realtime", 2275, { shading: GRAY }),
                cell("~40x realtime", 2276, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("LLM snelheid (8B)", 2200, { bold: true }),
                cell("~35 tok/s", 2275),
                cell("~52 tok/s", 2275),
                cell("~104 tok/s", 2276),
              ],
            }),
            new TableRow({
              children: [
                cell("Stroomverbruik", 2200, { bold: true }),
                cell("~150W piek", 2275, { shading: GRAY }),
                cell("~250W piek", 2275, { shading: GRAY }),
                cell("~450W piek", 2276, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Geschikt voor", 2200, { bold: true }),
                cell("Solo/duo praktijk", 2275),
                cell("Groepspraktijk (3\u20135 artsen)", 2275),
                cell("Groepspraktijk + HAGRO", 2276),
              ],
            }),
          ],
        }),

        spacer(200),

        boldBodyText("Aanbeveling: ", "De middelste configuratie (RTX 4070 Ti Super, \u20ac2.500) biedt de beste " +
          "balans voor een gemiddelde huisartsenpraktijk. Ze draait VitaScribe en ProVita Care gelijktijdig, " +
          "ondersteunt modellen tot 32B parameters, en is stil genoeg voor een serverkast."),

        // ===== 4. GECOMBINEERDE WORKLOAD =====
        heading1("4. Gecombineerde workload-analyse"),

        bodyText(
          "De producten belasten de GPU niet gelijktijdig. VitaScribe verwerkt in bursts " +
          "(30\u201390 seconden per consult, daarna idle). ProVita Care genereert behandelplannen op verzoek " +
          "(niet tijdkritisch). De website-chatbot verwerkt korte interacties. Redis Streams fungeert als " +
          "wachtrij: als twee verzoeken tegelijk binnenkomen, wordt het tweede in de queue geplaatst."
        ),

        bodyText(
          "In de praktijk ziet een typische ochtend er zo uit: de arts draait 15 consulten tussen 8:00 en 12:00. " +
          "Na elk consult kost de VitaScribe-verwerking ~60 seconden GPU-tijd. Dat is 15 minuten GPU-belasting " +
          "over 4 uur - 6% bezettingsgraad. De overige 94% van de tijd staat de GPU beschikbaar voor " +
          "ProVita Care, de chatbot, of andere taken. Zelfs in een groepspraktijk met 3 artsen die tegelijk " +
          "afronden, is de wachttijd beperkt tot 2\u20133 minuten."
        ),

        // ===== 5. PRIVACY EN COMPLIANCE =====
        heading1("5. Privacy en compliance"),

        heading2("5.1 Lokaal vs. cloud: het fundamentele verschil"),
        bodyText(
          "Bij cloud-verwerking (Juvoly, Deepgram, OpenAI, Mistral) verlaat pati\u00ebntdata de praktijk. " +
          "Hoe goed versleuteld en gecertificeerd ook - er is een externe verwerker die toegang heeft " +
          "tot medische data. Dit vereist een verwerkersovereenkomst, een DPIA, en vertrouwen in de " +
          "leverancier en diens toeleveranciers."
        ),
        bodyText(
          "Bij lokale verwerking verlaat er niets. De audio wordt opgenomen op de werkplek, verstuurd over " +
          "het lokale netwerk (of zelfs via localhost), verwerkt door modellen die op de eigen server draaien, " +
          "en opgeslagen in een lokale database. Er is geen externe verwerker. Het medisch beroepsgeheim " +
          "wordt op geen enkel moment doorbroken richting een derde partij."
        ),

        heading2("5.2 NEN 7510 en AVG"),
        bodyText(
          "NEN 7510 vereist passende technische en organisatorische maatregelen voor de beveiliging van " +
          "gezondheidsgegevens. Een eigen server vereenvoudigt dit: er hoeft geen risicobeoordeling voor " +
          "dataoverdracht naar derden, geen verwerkersovereenkomst met AI-providers, en geen DPIA voor " +
          "grensoverschrijdende verwerking. De maatregelen beperken zich tot het beveiligen van de fysieke " +
          "server (afgesloten ruimte, toegangscontrole), het netwerk (firewall, geen publieke toegang), " +
          "en de software (updates, encryptie at-rest, audit logging)."
        ),

        heading2("5.3 Hybride optie: lokale STT, geanonimiseerde cloud-LLM"),
        bodyText(
          "Als tussenoplossing is het mogelijk om de spraakherkenning (het privacygevoeligste deel) " +
          "lokaal te draaien en alleen geanonimiseerde transcripten naar een cloud-LLM te sturen. " +
          "Een lokale anonimiseringslaag (SpaCy NER + regex) vervangt namen, BSN, geboortedata en " +
          "adressen door tokens. De cloud-LLM genereert de SOEP met tokens, die lokaal worden " +
          "terugvertaald. Audio verlaat het gebouw nooit, en de cloud ziet nooit herleidbare gegevens."
        ),

        // ===== 6. KOSTENANALYSE =====
        heading1("6. Kostenanalyse"),

        // Cost comparison table
        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [3000, 3013, 3013],
          rows: [
            new TableRow({
              children: [
                headerCell("Kostenpost", 3000),
                headerCell("Cloud/SaaS", 3013),
                headerCell("Eigen server", 3013),
              ],
            }),
            new TableRow({
              children: [
                cell("Eenmalige investering", 3000, { bold: true }),
                cell("\u20ac0", 3013),
                cell("\u20ac1.500 \u2013 \u20ac3.500", 3013),
              ],
            }),
            new TableRow({
              children: [
                cell("Juvoly (SOEP)", 3000, { bold: true }),
                cell("\u20ac75\u2013\u20ac125/maand", 3013, { shading: GRAY }),
                cell("\u20ac0", 3013, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Claude API (ProVita)", 3000, { bold: true }),
                cell("\u20ac30\u2013\u20ac80/maand", 3013),
                cell("\u20ac0", 3013),
              ],
            }),
            new TableRow({
              children: [
                cell("Deepgram STT", 3000, { bold: true }),
                cell("\u20ac20\u2013\u20ac50/maand", 3013, { shading: GRAY }),
                cell("\u20ac0", 3013, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Chatbot hosting", 3000, { bold: true }),
                cell("\u20ac10\u2013\u20ac30/maand", 3013),
                cell("\u20ac0", 3013),
              ],
            }),
            new TableRow({
              children: [
                cell("Railway hosting", 3000, { bold: true }),
                cell("\u20ac5\u2013\u20ac20/maand", 3013, { shading: GRAY }),
                cell("\u20ac0", 3013, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Elektriciteit server", 3000, { bold: true }),
                cell("n.v.t.", 3013),
                cell("\u20ac15\u2013\u20ac25/maand", 3013),
              ],
            }),
            new TableRow({
              children: [
                cell("Totaal per maand", 3000, { bold: true }),
                cell("\u20ac140\u2013\u20ac305/maand", 3013, { shading: ACCENT_LIGHT, bold: true }),
                cell("\u20ac15\u2013\u20ac25/maand", 3013, { shading: ACCENT_LIGHT, bold: true }),
              ],
            }),
            new TableRow({
              children: [
                cell("Totaal per jaar", 3000, { bold: true }),
                cell("\u20ac1.680\u2013\u20ac3.660/jaar", 3013, { bold: true }),
                cell("\u20ac180\u2013\u20ac300/jaar", 3013, { bold: true }),
              ],
            }),
          ],
        }),

        spacer(200),

        boldBodyText("Terugverdientijd: ", "Bij de aanbevolen configuratie (\u20ac2.500) en gemiddelde cloudkosten " +
          "(\u20ac200/maand) is de investering in 12\u201314 maanden terugverdiend. Daarna bespaart de praktijk " +
          "structureel \u20ac2.000\u2013\u20ac3.000 per jaar."),

        // ===== 7. NETWERKARCHITECTUUR =====
        heading1("7. Netwerkarchitectuur"),

        bodyText(
          "De server staat fysiek in de praktijk, verbonden met het lokale netwerk via ethernet (1 Gbps). " +
          "Alle werkplekken benaderen de server via het interne netwerk. Er is geen publieke internetverbinding " +
          "nodig voor de AI-verwerking. De server heeft wel internet nodig voor initieel downloaden van modellen " +
          "en software-updates, maar dit kan via een beperkte/gefilterde verbinding."
        ),

        heading2("7.1 Interne toegang"),
        bodyText(
          "De FastAPI-backend draait op een vast intern IP-adres (bijv. 192.168.1.100:8000). " +
          "De Chrome-extensie van VitaScribe wordt geconfigureerd met dit adres als API URL. " +
          "ProVita Care communiceert via dezelfde API. De website-chatbot wordt via een reverse proxy " +
          "(Nginx/Caddy) ontsloten, zodat alleen de chatbot-endpoint extern bereikbaar is - " +
          "de rest van de API blijft intern."
        ),

        heading2("7.2 Remote toegang (optioneel)"),
        bodyText(
          "Voor toegang buiten de praktijk (bijv. thuiswerkplek, waarneming) kan Tailscale of WireGuard " +
          "een VPN-tunnel opzetten. De arts installeert een kleine VPN-client op de laptop, en krijgt " +
          "toegang tot de server alsof deze lokaal is. Audio wordt dan versleuteld over de VPN-tunnel " +
          "verstuurd en verwerkt op de server in de praktijk. Er is geen cloudinfrastructuur nodig."
        ),

        // ===== 8. SOFTWARE-STACK =====
        heading1("8. Software-stack"),

        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [2200, 2413, 4413],
          rows: [
            new TableRow({
              children: [
                headerCell("Component", 2200),
                headerCell("Software", 2413),
                headerCell("Doel", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("Besturingssysteem", 2200, { bold: true }),
                cell("Ubuntu 22.04 LTS Server", 2413),
                cell("Stabiel, langetermijnondersteuning, NVIDIA-drivers goed ondersteund", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("Containerisatie", 2200, { bold: true }),
                cell("Docker Compose", 2413, { shading: GRAY }),
                cell("Alle services als containers, eenvoudig updaten en herstarten", 4413, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("GPU runtime", 2200, { bold: true }),
                cell("NVIDIA Container Toolkit", 2413),
                cell("GPU-toegang vanuit Docker containers", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("STT (spraak)", 2200, { bold: true }),
                cell("Faster-Whisper", 2413, { shading: GRAY }),
                cell("Whisper Large v3 Turbo, ~6 GB VRAM, sneller dan origineel Whisper", 4413, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Diarisatie", 2200, { bold: true }),
                cell("PyAnnote Audio 3.x", 2413),
                cell("Sprekerherkenning (arts vs. pati\u00ebnt)", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("LLM runtime", 2200, { bold: true }),
                cell("Ollama", 2413, { shading: GRAY }),
                cell("Eenvoudig lokaal LLM-management, model hot-swapping", 4413, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("LLM modellen", 2200, { bold: true }),
                cell("Llama 3.3 8B / Qwen 32B", 2413),
                cell("SOEP-generatie, behandelplannen, chatbot", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("API gateway", 2200, { bold: true }),
                cell("FastAPI (Python)", 2413, { shading: GRAY }),
                cell("REST API, async verwerking, orchestratie", 4413, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Database", 2200, { bold: true }),
                cell("PostgreSQL 16", 2413),
                cell("Consultaties, behandelplannen, audit logs, encryptie", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("Queue", 2200, { bold: true }),
                cell("Redis Streams", 2413, { shading: GRAY }),
                cell("Taakwachtrij voor verwerkingspieken", 4413, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Reverse proxy", 2200, { bold: true }),
                cell("Caddy / Nginx", 2413),
                cell("HTTPS intern, rate limiting, chatbot-endpoint extern", 4413),
              ],
            }),
            new TableRow({
              children: [
                cell("Monitoring", 2200, { bold: true }),
                cell("Uptime Kuma / Grafana", 2413, { shading: GRAY }),
                cell("Serverstatus, GPU-temperatuur, disk usage alerts", 4413, { shading: GRAY }),
              ],
            }),
          ],
        }),

        // ===== 9. RISICO'S EN MITIGATIE =====
        heading1("9. Risico\u2019s en mitigatie"),

        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [2500, 2500, 4026],
          rows: [
            new TableRow({
              children: [
                headerCell("Risico", 2500),
                headerCell("Impact", 2500),
                headerCell("Mitigatie", 4026),
              ],
            }),
            new TableRow({
              children: [
                cell("Hardwarestoring", 2500, { bold: true }),
                cell("Geen AI-documentatie tot reparatie", 2500),
                cell("Spare-onderdelen op voorraad; fallback naar cloud-API (Railway) bij storing; onderhoudscontract met lokale IT-partner", 4026),
              ],
            }),
            new TableRow({
              children: [
                cell("Stroomuitval", 2500, { bold: true }),
                cell("Server onbereikbaar", 2500, { shading: GRAY }),
                cell("UPS (noodstroomvoorziening, ~\u20ac150) voor graceful shutdown; PostgreSQL WAL-logging voorkomt dataverlies", 4026, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Geen eigen IT-kennis", 2500, { bold: true }),
                cell("Updates en troubleshooting", 2500),
                cell("Docker Compose maakt updates eenvoudig (docker compose pull && up -d); Ansible-playbook voor geautomatiseerd beheer; IT-partner voor escalaties", 4026),
              ],
            }),
            new TableRow({
              children: [
                cell("Modelkwaliteit onvoldoende", 2500, { bold: true }),
                cell("SOEP-kwaliteit lager dan commercieel", 2500, { shading: GRAY }),
                cell("Feedbackloop (zelflerend systeem): artscorrecties verbeteren prompts en uiteindelijk het model; grotere modellen beschikbaar bij meer VRAM", 4026, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Geluid in de praktijk", 2500, { bold: true }),
                cell("GPU-ventilator hoorbaar", 2500),
                cell("Server in afgesloten ruimte, serverkast of meterkast; aftermarket koeling of waterkoeling bij gevoelige locaties", 4026),
              ],
            }),
            new TableRow({
              children: [
                cell("Capaciteitstekort bij groei", 2500, { bold: true }),
                cell("Wachttijden bij >3 artsen tegelijk", 2500, { shading: GRAY }),
                cell("Tweede GPU toevoegen (dual-GPU setup); of upgraden naar krachtigere kaart; Redis-queue vangt pieken op", 4026, { shading: GRAY }),
              ],
            }),
          ],
        }),

        // ===== 10. VERGELIJKING MET JUVOLY =====
        heading1("10. Positionering t.o.v. Juvoly"),

        new Table({
          width: { size: 9026, type: WidthType.DXA },
          columnWidths: [2500, 3263, 3263],
          rows: [
            new TableRow({
              children: [
                headerCell("Aspect", 2500),
                headerCell("Juvoly", 3263),
                headerCell("Eigen server", 3263),
              ],
            }),
            new TableRow({
              children: [
                cell("Dataverwerking", 2500, { bold: true }),
                cell("Eigen servers NL (extern)", 3263),
                cell("In de praktijk (intern)", 3263),
              ],
            }),
            new TableRow({
              children: [
                cell("Audio verlaat praktijk", 2500, { bold: true }),
                cell("Ja (versleuteld)", 3263, { shading: GRAY }),
                cell("Nee", 3263, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Verwerkersovereenkomst nodig", 2500, { bold: true }),
                cell("Ja", 3263),
                cell("Nee", 3263),
              ],
            }),
            new TableRow({
              children: [
                cell("DPIA vereist", 2500, { bold: true }),
                cell("Ja (beschikbaar)", 3263, { shading: GRAY }),
                cell("Vereenvoudigd (geen extern dataverkeer)", 3263, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Certificeringen", 2500, { bold: true }),
                cell("ISO 27001, NEN 7510", 3263),
                cell("Eigen verantwoordelijkheid", 3263),
              ],
            }),
            new TableRow({
              children: [
                cell("STT-kwaliteit NL medisch", 2500, { bold: true }),
                cell("Eigen model (WER 2,6%)", 3263, { shading: GRAY }),
                cell("Whisper v3 Turbo (WER ~4,3%), verbeterbaar met finetuning", 3263, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Kosten per jaar", 2500, { bold: true }),
                cell("\u20ac900\u2013\u20ac1.500/jaar", 3263),
                cell("\u20ac180\u2013\u20ac300/jaar (na investering)", 3263),
              ],
            }),
            new TableRow({
              children: [
                cell("Leveranciersafhankelijkheid", 2500, { bold: true }),
                cell("Ja (overgenomen door Tandem Health SE)", 3263, { shading: GRAY }),
                cell("Nee", 3263, { shading: GRAY }),
              ],
            }),
            new TableRow({
              children: [
                cell("Multi-product platform", 2500, { bold: true }),
                cell("Nee (alleen SOEP)", 3263),
                cell("Ja (VitaScribe + ProVita + chatbot + meer)", 3263),
              ],
            }),
          ],
        }),

        // ===== 11. ROADMAP =====
        heading1("11. Implementatie-roadmap"),

        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 100, line: 300 },
          children: [
            new TextRun({ text: "Maand 1 - Hardware aanschaffen en OS installeren. ", bold: true, font: "Arial", size: 21 }),
            new TextRun({ text: "Ubuntu 22.04 LTS, NVIDIA-drivers, Docker, NVIDIA Container Toolkit.", font: "Arial", size: 21 }),
          ],
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 100, line: 300 },
          children: [
            new TextRun({ text: "Maand 1\u20132 - VitaScribe migreren naar lokale server. ", bold: true, font: "Arial", size: 21 }),
            new TextRun({ text: "Docker Compose stack deployen. Extensie configureren op intern IP. Testen met eigen consulten.", font: "Arial", size: 21 }),
          ],
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 100, line: 300 },
          children: [
            new TextRun({ text: "Maand 2\u20133 - Feedbackloop bouwen. ", bold: true, font: "Arial", size: 21 }),
            new TextRun({ text: "Correctie-UI, PostgreSQL feedback-tabel, promptoptimalisatie op basis van artscorrecties.", font: "Arial", size: 21 }),
          ],
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 100, line: 300 },
          children: [
            new TextRun({ text: "Maand 3\u20134 - ProVita Care lokaliseren. ", bold: true, font: "Arial", size: 21 }),
            new TextRun({ text: "Claude API vervangen door lokaal LLM. Behandelplangeneratie testen en kalibreren.", font: "Arial", size: 21 }),
          ],
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 100, line: 300 },
          children: [
            new TextRun({ text: "Maand 4\u20135 - Website-chatbot deployen. ", bold: true, font: "Arial", size: 21 }),
            new TextRun({ text: "RAG-pipeline over NHG-standaarden. Externe endpoint via reverse proxy.", font: "Arial", size: 21 }),
          ],
        }),
        new Paragraph({
          numbering: { reference: "numbers", level: 0 },
          spacing: { after: 100, line: 300 },
          children: [
            new TextRun({ text: "Maand 5\u20136 - Monitoring en hardening. ", bold: true, font: "Arial", size: 21 }),
            new TextRun({ text: "Uptime Kuma, automatische backups, UPS, beveiligingsaudit, documentatie voor IT-partner.", font: "Arial", size: 21 }),
          ],
        }),

        // ===== 12. CONCLUSIE =====
        heading1("12. Conclusie"),

        bodyText(
          "Een eigen AI-server is technisch haalbaar, financieel aantrekkelijk, en biedt een " +
          "privacyniveau dat geen enkele externe leverancier kan evenaren. De investering van " +
          "\u20ac1.500\u2013\u20ac3.500 verdient zich binnen anderhalf jaar terug en maakt de praktijk " +
          "eigenaar van haar eigen AI-infrastructuur. De server bedient niet \u00e9\u00e9n product maar " +
          "een heel ecosysteem - van consultdocumentatie tot telehealth tot pati\u00ebntcommunicatie - " +
          "en is uitbreidbaar naarmate nieuwe toepassingen zich aandienen."
        ),
        bodyText(
          "De belangrijkste strategische winst is onafhankelijkheid: geen abonnementen die jaarlijks stijgen, " +
          "geen leverancier die wordt overgenomen, geen data die het gebouw verlaat. " +
          "Voor een huisartsenpraktijk die AI wil inzetten op een manier die past bij de waarden van het vak - " +
          "privacy, autonomie, en zorg voor de pati\u00ebnt - is een eigen server de logische keuze."
        ),
      ],
    },
  ],
});

// === GENERATE ===
Packer.toBuffer(doc).then((buffer) => {
  const outPath = "AI-Server-Technische-Memo.docx";
  fs.writeFileSync(outPath, buffer);
  console.log(`Document gegenereerd: ${outPath} (${(buffer.length / 1024).toFixed(0)} KB)`);
});
