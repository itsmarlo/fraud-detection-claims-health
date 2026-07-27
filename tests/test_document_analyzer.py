from datetime import date

from app.services.document_analyzer import DocumentAnalyzer
from tests.test_health_fraud_agent import base_claim


def test_extracts_labelled_dates_and_amounts_from_pdf_text():
    analyzer = DocumentAnalyzer()
    text = """
    Treatment date: 2026-05-01
    Admission date: 30.04.2026
    Discharge date: 02.05.2026
    Grand total: EUR 1,234.56
    """

    assert analyzer._extract_dates(text) == {
        "treatment_date": date(2026, 5, 1),
        "admission_date": date(2026, 4, 30),
        "discharge_date": date(2026, 5, 2),
    }
    assert analyzer._extract_amounts(text) == [1234.56]


def test_detects_identifier_mismatch_in_extracted_text():
    analyzer = DocumentAnalyzer()

    mismatches = analyzer._identifier_mismatches(
        base_claim(),
        "Claim ID: CLM-OTHER\nMember ID: MBR-1\nProvider ID: NPI-1",
    )

    assert mismatches == ["Extracted claim id does not match the claim"]
