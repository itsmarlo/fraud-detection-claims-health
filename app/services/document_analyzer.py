from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from threading import Lock

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader

from app.core.config import Settings, get_settings
from app.models.health_claim_schema import HealthClaimInput, UploadedDocumentFinding


ALLOWED_MEDIA_TYPES = {"application/pdf", "image/jpeg", "image/png"}
ROLE_LABELS = {
    "hospital_bill": "hospital bill",
    "discharge_summary": "discharge summary",
    "prescription": "prescription",
    "medical_report": "medical report",
    "lab_or_test_results": "lab or test results",
}
DATE_PATTERNS = {
    "treatment_date": re.compile(
        r"(?:treatment|service|procedure)\s*date\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.IGNORECASE,
    ),
    "medical_report_date": re.compile(
        r"(?:medical\s+)?report\s*date\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.IGNORECASE,
    ),
    "admission_date": re.compile(
        r"admission\s*date\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.IGNORECASE,
    ),
    "discharge_date": re.compile(
        r"discharge\s*date\s*[:\-]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        re.IGNORECASE,
    ),
}
AMOUNT_PATTERN = re.compile(
    r"(?:grand\s+total|total\s+(?:amount|due)|amount\s+(?:billed|due))\s*[:\-]?\s*(?:[$€£]|EUR|USD|GBP)?\s*([0-9][0-9., ]*)",
    re.IGNORECASE,
)
IDENTIFIER_PATTERNS = {
    "claim_id": re.compile(r"claim\s*(?:id|number|no\.?)[\s:#-]*([A-Z0-9][A-Z0-9_-]{2,})", re.IGNORECASE),
    "member_id": re.compile(r"member\s*(?:id|number|no\.?)[\s:#-]*([A-Z0-9][A-Z0-9_-]{2,})", re.IGNORECASE),
    "provider_id": re.compile(r"provider\s*(?:id|number|no\.?)[\s:#-]*([A-Z0-9][A-Z0-9_-]{2,})", re.IGNORECASE),
}


@dataclass
class DocumentAnalysis:
    claim: HealthClaimInput
    findings: list[UploadedDocumentFinding]
    warnings: list[str]


class DocumentAnalyzer:
    """Inspect uploaded evidence without retaining the source files."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._fingerprints: OrderedDict[str, str] = OrderedDict()
        self._fingerprint_lock = Lock()

    async def analyze(
        self, claim: HealthClaimInput, uploads: dict[str, UploadFile | None]
    ) -> DocumentAnalysis:
        findings: list[UploadedDocumentFinding] = []
        warnings: list[str] = []
        document_updates: dict[str, object] = {}
        current_hashes: set[str] = set()
        duplicate_found = False

        for role, upload in uploads.items():
            if upload is None or not upload.filename:
                continue
            finding, digest, extracted_text = await self._inspect(role, upload)
            findings.append(finding)
            document_updates[role] = True

            if digest in current_hashes:
                duplicate_found = True
                finding.signals.append("Exact duplicate also uploaded with this claim")
            current_hashes.add(digest)

            with self._fingerprint_lock:
                previous_claim = self._fingerprints.get(digest)
                if previous_claim and previous_claim != claim.claim_id:
                    duplicate_found = True
                    finding.signals.append("Exact document seen in a previous assessment")
                self._fingerprints[digest] = claim.claim_id
                self._fingerprints.move_to_end(digest)
                if len(self._fingerprints) > 10_000:
                    self._fingerprints.popitem(last=False)

            if "Low-resolution image" in finding.signals:
                document_updates["low_resolution_image"] = True

            for key, extracted_date in finding.extracted_dates.items():
                current_value = getattr(claim.documents, key)
                if current_value is None:
                    document_updates[key] = extracted_date
                elif current_value != extracted_date:
                    document_updates["document_identifier_mismatch"] = True
                    finding.signals.append(
                        f"Extracted {key.replace('_', ' ')} conflicts with supplied evidence metadata"
                    )

            identifier_mismatches = self._identifier_mismatches(claim, extracted_text)
            if identifier_mismatches:
                document_updates["document_identifier_mismatch"] = True
                finding.signals.extend(identifier_mismatches)

            if role == "hospital_bill" and finding.extracted_amounts:
                tolerance = max(1.0, claim.billed_amount * 0.01)
                if all(abs(amount - claim.billed_amount) > tolerance for amount in finding.extracted_amounts):
                    document_updates["document_amount_mismatch"] = True
                    finding.signals.append("Document total does not match the supplied billed amount")

            if finding.status == "LIMITED_ANALYSIS":
                warnings.append(f"{finding.filename}: content analysis was limited.")

        if duplicate_found:
            document_updates["duplicate_document_found"] = True

        enriched_documents = claim.documents.model_copy(update=document_updates)
        enriched_claim = claim.model_copy(update={"documents": enriched_documents})
        return DocumentAnalysis(enriched_claim, findings, warnings)

    async def _inspect(
        self, role: str, upload: UploadFile
    ) -> tuple[UploadedDocumentFinding, str, str]:
        data = await upload.read(self.settings.max_document_size_mb * 1024 * 1024 + 1)
        await upload.close()
        max_bytes = self.settings.max_document_size_mb * 1024 * 1024
        if not data:
            raise HTTPException(status_code=422, detail=f"{upload.filename} is empty.")
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{upload.filename} exceeds the {self.settings.max_document_size_mb} MB limit.",
            )

        media_type = self._verified_media_type(data, upload.content_type)
        safe_name = Path(upload.filename or f"{role}.bin").name
        digest = hashlib.sha256(data).hexdigest()
        notes: list[str] = []
        signals: list[str] = []
        text = ""
        status = "ANALYZED"

        if media_type == "application/pdf":
            try:
                reader = PdfReader(BytesIO(data))
                if reader.is_encrypted:
                    status = "LIMITED_ANALYSIS"
                    notes.append("Encrypted PDF; text could not be inspected")
                else:
                    text = "\n".join((page.extract_text() or "") for page in reader.pages[:25])
                    if not text.strip():
                        status = "LIMITED_ANALYSIS"
                        notes.append("No machine-readable PDF text; OCR is required for scanned pages")
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"{safe_name} is not a readable PDF.") from exc
        else:
            try:
                with Image.open(BytesIO(data)) as image:
                    width, height = image.size
                    notes.append(f"Image dimensions: {width} × {height}")
                    if width < 1000 or height < 1000:
                        signals.append("Low-resolution image")
                    image.verify()
                status = "LIMITED_ANALYSIS"
                notes.append("Image integrity and resolution checked; OCR is not enabled")
            except (UnidentifiedImageError, OSError) as exc:
                raise HTTPException(status_code=422, detail=f"{safe_name} is not a readable image.") from exc

        extracted_dates = self._extract_dates(text)
        extracted_amounts = self._extract_amounts(text)
        if text:
            notes.append(f"Extracted {len(text)} characters of machine-readable text")

        return (
            UploadedDocumentFinding(
                role=ROLE_LABELS[role],
                filename=safe_name,
                media_type=media_type,
                size_bytes=len(data),
                fingerprint=digest[:12],
                status=status,
                extracted_dates=extracted_dates,
                extracted_amounts=extracted_amounts,
                signals=signals,
                notes=notes,
            ),
            digest,
            text,
        )

    def _verified_media_type(self, data: bytes, declared: str | None) -> str:
        if data.startswith(b"%PDF-"):
            detected = "application/pdf"
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            detected = "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            detected = "image/jpeg"
        else:
            raise HTTPException(status_code=415, detail="Only PDF, PNG, and JPEG documents are supported.")
        if declared and declared not in ALLOWED_MEDIA_TYPES and declared != "application/octet-stream":
            raise HTTPException(status_code=415, detail=f"Unsupported declared file type: {declared}.")
        return detected

    def _extract_dates(self, text: str) -> dict[str, date]:
        extracted: dict[str, date] = {}
        for label, pattern in DATE_PATTERNS.items():
            match = pattern.search(text)
            if not match:
                continue
            parsed = self._parse_date(match.group(1))
            if parsed:
                extracted[label] = parsed
        return extracted

    def _parse_date(self, raw: str) -> date | None:
        normalized = raw.strip().replace("/", "-").replace(".", "-")
        formats = ("%Y-%m-%d", "%d-%m-%Y", "%m-%d-%Y")
        for date_format in formats:
            try:
                return datetime.strptime(normalized, date_format).date()
            except ValueError:
                continue
        return None

    def _extract_amounts(self, text: str) -> list[float]:
        values: list[float] = []
        for match in AMOUNT_PATTERN.finditer(text):
            raw = match.group(1).replace(" ", "")
            if "," in raw and "." in raw:
                raw = raw.replace(",", "")
            elif raw.count(",") == 1 and len(raw.rsplit(",", 1)[1]) == 2:
                raw = raw.replace(",", ".")
            else:
                raw = raw.replace(",", "")
            try:
                values.append(round(float(raw), 2))
            except ValueError:
                continue
        return values[:10]

    def _identifier_mismatches(self, claim: HealthClaimInput, text: str) -> list[str]:
        mismatches: list[str] = []
        if not text:
            return mismatches
        for field, pattern in IDENTIFIER_PATTERNS.items():
            match = pattern.search(text)
            if match and match.group(1).upper() != str(getattr(claim, field)).upper():
                mismatches.append(f"Extracted {field.replace('_', ' ')} does not match the claim")
        return mismatches
