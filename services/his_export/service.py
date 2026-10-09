"""
HIS Export Service
==================
Abstracte interface voor export naar Huisarts Informatie Systemen.
Ondersteunt meerdere HIS-systemen via een pluggable architectuur.
"""

import abc
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class HISType(str, Enum):
    """Ondersteunde HIS-systemen."""
    CLIPBOARD = "clipboard"
    CGM_HUISARTS = "cgm"          # CGM (CompuGroup Medical)
    MEDICOM = "medicom"            # PharmaPartners Medicom
    PROMEDICO = "promedico"        # ProMedico ASP
    CHIPSOFT_HIXONE = "chipsoft"   # ChipSoft HiX/ONE
    EDIFACT = "edifact"            # Standaard EDIFACT bericht
    FHIR = "fhir"                  # HL7 FHIR R4


@dataclass
class SOEPExportData:
    """SOEP data klaar voor export."""
    consult_id: str
    patient_hash: str
    practitioner_name: str
    practitioner_id: str
    timestamp: datetime
    s_text: str
    o_text: str
    e_text: str
    p_text: str
    icpc_code: str | None = None
    icpc_titel: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ExportResult:
    """Resultaat van een HIS export."""
    success: bool
    target: HISType
    export_id: str = ""
    message: str = ""
    export_text: str = ""
    raw_response: dict | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HISExporter(abc.ABC):
    """
    Abstracte base class voor HIS exporters.

    Implementeer export() voor elk HIS-systeem.
    """

    @abc.abstractmethod
    async def export(self, data: SOEPExportData) -> ExportResult:
        """Exporteer SOEP data naar het HIS."""
        ...

    @abc.abstractmethod
    def format_soep(self, data: SOEPExportData) -> str:
        """Formatteer SOEP data voor dit HIS-systeem."""
        ...

    @property
    @abc.abstractmethod
    def his_type(self) -> HISType:
        """Welk HIS-systeem is dit."""
        ...


class ClipboardExporter(HISExporter):
    """
    Export naar clipboard (kopieer/plak).
    Genereert geformatteerde tekst voor handmatige invoer.
    """

    @property
    def his_type(self) -> HISType:
        return HISType.CLIPBOARD

    def format_soep(self, data: SOEPExportData) -> str:
        lines = []
        lines.append(f"=== SOEP Dossiervoering ===")
        lines.append(f"Datum: {data.timestamp.strftime('%d-%m-%Y %H:%M')}")
        lines.append(f"Arts: {data.practitioner_name}")
        lines.append("")
        lines.append(f"S: {data.s_text}")
        lines.append(f"O: {data.o_text}")
        lines.append(f"E: {data.e_text}")
        lines.append(f"P: {data.p_text}")

        if data.icpc_code:
            lines.append("")
            lines.append(f"ICPC: {data.icpc_code} - {data.icpc_titel or ''}")

        return "\n".join(lines)

    async def export(self, data: SOEPExportData) -> ExportResult:
        export_text = self.format_soep(data)
        return ExportResult(
            success=True,
            target=self.his_type,
            export_id=str(uuid.uuid4()),
            message="Tekst klaar voor clipboard",
            export_text=export_text,
        )


class CGMExporter(HISExporter):
    """
    Export naar CGM (CompuGroup Medical) HIS.
    Gebruikt CGM's SOAP/REST API voor automatische invoer.
    """

    def __init__(self, api_url: str = "", api_key: str = "", timeout: int = 30):
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout

    @property
    def his_type(self) -> HISType:
        return HISType.CGM_HUISARTS

    def format_soep(self, data: SOEPExportData) -> str:
        """CGM-specifiek formaat met veldcodes."""
        return json.dumps({
            "journaalregel": {
                "datum": data.timestamp.strftime("%Y-%m-%d"),
                "tijd": data.timestamp.strftime("%H:%M"),
                "soort": "C",  # Consult
                "patient_id": data.patient_hash[:16],
                "medewerker": data.practitioner_name,
                "regels": [
                    {"type": "S", "tekst": data.s_text},
                    {"type": "O", "tekst": data.o_text},
                    {"type": "E", "tekst": data.e_text, "icpc": data.icpc_code or ""},
                    {"type": "P", "tekst": data.p_text},
                ],
            }
        }, ensure_ascii=False, indent=2)

    async def export(self, data: SOEPExportData) -> ExportResult:
        if not self.api_url:
            # Geen API geconfigureerd: genereer JSON voor handmatig import
            export_text = self.format_soep(data)
            return ExportResult(
                success=True,
                target=self.his_type,
                export_id=str(uuid.uuid4()),
                message="CGM JSON gegenereerd (geen API geconfigureerd)",
                export_text=export_text,
            )

        # API export
        try:
            payload = json.loads(self.format_soep(data))
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/api/journaal/invoer",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

                return ExportResult(
                    success=True,
                    target=self.his_type,
                    export_id=result.get("id", str(uuid.uuid4())),
                    message="Succesvol geexporteerd naar CGM",
                    export_text=self.format_soep(data),
                    raw_response=result,
                )
        except httpx.TimeoutException:
            logger.error("CGM export timeout", url=self.api_url)
            return ExportResult(
                success=False,
                target=self.his_type,
                message="CGM API timeout - probeer later opnieuw",
            )
        except httpx.HTTPStatusError as e:
            logger.error("CGM export HTTP fout", status=e.response.status_code)
            return ExportResult(
                success=False,
                target=self.his_type,
                message=f"CGM API fout: HTTP {e.response.status_code}",
                raw_response={"status": e.response.status_code},
            )
        except Exception as e:
            logger.error("CGM export mislukt", error=str(e))
            return ExportResult(
                success=False,
                target=self.his_type,
                message=f"CGM export fout: {str(e)}",
            )


class MedicomExporter(HISExporter):
    """
    Export naar PharmaPartners Medicom.
    Gebruikt Medicom's koppelingsprotocol.
    """

    def __init__(self, api_url: str = "", api_key: str = "", timeout: int = 30):
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout

    @property
    def his_type(self) -> HISType:
        return HISType.MEDICOM

    def format_soep(self, data: SOEPExportData) -> str:
        """Medicom-specifiek formaat."""
        return json.dumps({
            "episode": {
                "datum": data.timestamp.strftime("%Y-%m-%d"),
                "type": "consult",
                "icpc": data.icpc_code or "",
                "titel": data.icpc_titel or "",
            },
            "journaal": {
                "S": data.s_text,
                "O": data.o_text,
                "E": data.e_text,
                "P": data.p_text,
            },
            "metadata": {
                "bron": "AI-Consultassistent",
                "arts": data.practitioner_name,
                "tijdstip": data.timestamp.isoformat(),
            },
        }, ensure_ascii=False, indent=2)

    async def export(self, data: SOEPExportData) -> ExportResult:
        if not self.api_url:
            export_text = self.format_soep(data)
            return ExportResult(
                success=True,
                target=self.his_type,
                export_id=str(uuid.uuid4()),
                message="Medicom JSON gegenereerd (geen API geconfigureerd)",
                export_text=export_text,
            )

        try:
            payload = json.loads(self.format_soep(data))
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/koppeling/journaal",
                    json=payload,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                result = response.json()

                return ExportResult(
                    success=True,
                    target=self.his_type,
                    export_id=result.get("journaal_id", str(uuid.uuid4())),
                    message="Succesvol geexporteerd naar Medicom",
                    export_text=self.format_soep(data),
                    raw_response=result,
                )
        except Exception as e:
            logger.error("Medicom export mislukt", error=str(e))
            return ExportResult(
                success=False,
                target=self.his_type,
                message=f"Medicom export fout: {str(e)}",
            )


class FHIRExporter(HISExporter):
    """
    Export als HL7 FHIR R4 Encounter resource.
    Generiek formaat dat door moderne HIS-systemen ondersteund wordt.
    """

    def __init__(self, fhir_base_url: str = "", timeout: int = 30):
        self.fhir_base_url = fhir_base_url
        self.timeout = timeout

    @property
    def his_type(self) -> HISType:
        return HISType.FHIR

    def format_soep(self, data: SOEPExportData) -> str:
        """FHIR R4 Encounter + Composition resource."""
        composition = {
            "resourceType": "Composition",
            "id": data.consult_id,
            "status": "final",
            "type": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "11488-4",
                    "display": "Consult note",
                }],
            },
            "date": data.timestamp.isoformat(),
            "author": [{
                "display": data.practitioner_name,
            }],
            "title": f"Consult {data.timestamp.strftime('%d-%m-%Y')}",
            "section": [
                {
                    "title": "Subjectief",
                    "code": {"coding": [{"code": "S", "display": "Subjectief"}]},
                    "text": {"status": "generated", "div": f"<div>{data.s_text}</div>"},
                },
                {
                    "title": "Objectief",
                    "code": {"coding": [{"code": "O", "display": "Objectief"}]},
                    "text": {"status": "generated", "div": f"<div>{data.o_text}</div>"},
                },
                {
                    "title": "Evaluatie",
                    "code": {"coding": [{"code": "E", "display": "Evaluatie"}]},
                    "text": {"status": "generated", "div": f"<div>{data.e_text}</div>"},
                },
                {
                    "title": "Plan",
                    "code": {"coding": [{"code": "P", "display": "Plan"}]},
                    "text": {"status": "generated", "div": f"<div>{data.p_text}</div>"},
                },
            ],
        }

        if data.icpc_code:
            composition["event"] = [{
                "code": [{
                    "coding": [{
                        "system": "http://hl7.org/fhir/sid/icpc-2",
                        "code": data.icpc_code,
                        "display": data.icpc_titel or "",
                    }],
                }],
            }]

        return json.dumps(composition, ensure_ascii=False, indent=2)

    async def export(self, data: SOEPExportData) -> ExportResult:
        export_text = self.format_soep(data)

        if not self.fhir_base_url:
            return ExportResult(
                success=True,
                target=self.his_type,
                export_id=str(uuid.uuid4()),
                message="FHIR Composition gegenereerd (geen server geconfigureerd)",
                export_text=export_text,
            )

        try:
            composition = json.loads(export_text)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.fhir_base_url}/Composition",
                    json=composition,
                    headers={
                        "Content-Type": "application/fhir+json",
                        "Accept": "application/fhir+json",
                    },
                )
                response.raise_for_status()
                result = response.json()

                return ExportResult(
                    success=True,
                    target=self.his_type,
                    export_id=result.get("id", data.consult_id),
                    message="FHIR Composition succesvol aangemaakt",
                    export_text=export_text,
                    raw_response=result,
                )
        except Exception as e:
            logger.error("FHIR export mislukt", error=str(e))
            return ExportResult(
                success=False,
                target=self.his_type,
                message=f"FHIR export fout: {str(e)}",
            )


class HISExportService:
    """
    Factory + coordinator voor HIS exports.

    Gebruik:
        service = HISExportService(config)
        result = await service.export_soep(data, target="cgm")
    """

    def __init__(self, config=None):
        self.config = config
        self._exporters: dict[HISType, HISExporter] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Registreer standaard exporters."""
        self._exporters[HISType.CLIPBOARD] = ClipboardExporter()
        self._exporters[HISType.FHIR] = FHIRExporter()

        # CGM - configureerbaar
        cgm_url = ""
        cgm_key = ""
        if self.config:
            cgm_url = getattr(self.config, "cgm_api_url", "") if hasattr(self.config, "cgm_api_url") else ""
            cgm_key = getattr(self.config, "cgm_api_key", "") if hasattr(self.config, "cgm_api_key") else ""
        self._exporters[HISType.CGM_HUISARTS] = CGMExporter(api_url=cgm_url, api_key=cgm_key)

        # Medicom - configureerbaar
        medicom_url = ""
        medicom_key = ""
        if self.config:
            medicom_url = getattr(self.config, "medicom_api_url", "") if hasattr(self.config, "medicom_api_url") else ""
            medicom_key = getattr(self.config, "medicom_api_key", "") if hasattr(self.config, "medicom_api_key") else ""
        self._exporters[HISType.MEDICOM] = MedicomExporter(api_url=medicom_url, api_key=medicom_key)

    def register_exporter(self, exporter: HISExporter):
        """Registreer een custom exporter."""
        self._exporters[exporter.his_type] = exporter

    def get_available_targets(self) -> list[str]:
        """Lijst van beschikbare export targets."""
        return [t.value for t in self._exporters.keys()]

    async def export_soep(
        self, data: SOEPExportData, target: str = "clipboard"
    ) -> ExportResult:
        """
        Exporteer SOEP data naar het opgegeven HIS.

        Args:
            data: SOEP export data
            target: HIS type (clipboard, cgm, medicom, fhir)

        Returns:
            ExportResult
        """
        try:
            his_type = HISType(target)
        except ValueError:
            return ExportResult(
                success=False,
                target=HISType.CLIPBOARD,
                message=f"Onbekend HIS type: {target}. "
                        f"Beschikbaar: {', '.join(self.get_available_targets())}",
            )

        exporter = self._exporters.get(his_type)
        if not exporter:
            return ExportResult(
                success=False,
                target=his_type,
                message=f"Geen exporter geconfigureerd voor {target}",
            )

        logger.info("HIS export gestart", target=target, consult_id=data.consult_id)
        result = await exporter.export(data)
        logger.info("HIS export resultaat",
                     target=target,
                     success=result.success,
                     export_id=result.export_id)

        return result


# Singleton
his_export_service = HISExportService()
