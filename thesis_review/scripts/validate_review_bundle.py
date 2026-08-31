#!/usr/bin/env python3
"""Mechanically validate one clean-room thesis-review bundle.

The validator checks bundle identity, complete CSV contracts, referential
integrity, clean-context receipts, helper provenance, and exact Stage-C to
Stage-S reconciliation. It deliberately does not replace the reviewers'
semantic judgments or certify that an observation is scientifically correct.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import stat
import struct
import sys
import tempfile
import unicodedata
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit, urlunsplit


HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEX64_FIND_RE = re.compile(r"(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])")
PUBLIC_URL_RE = re.compile(r"https?://[^\s;,\[\]`\"<>]+", re.IGNORECASE)
DOI_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])10\.\d{4,9}/[^\s\[\]`\"]+",
    re.IGNORECASE,
)
ARXIV_ID_RE = re.compile(
    r"(?:arxiv\s*:?\s*|arxiv\.org/(?:abs|pdf)/)"
    r"([A-Za-z.-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?",
    re.IGNORECASE,
)
ACCESS_ENDPOINT_MARKER_RE = re.compile(
    r"(?i)(?:^|[;\n])\s*accessed endpoint\s*:\s*"
    r"(https?://[^\s;,\[\]`\"<>]+)"
    r"(?=[ \t]*(?:;|\n|$))"
)
BIB_MISMATCH_EXEMPTION_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"none|clean|n[./]?a|"
    r"no[ -]+(?:(?:actionable[ -]+)?findings?|issues?|action(?:[ -]+required)?)|"
    r"non[ -]+findings?|not[ -]+(?:applicable|required|a[ -]+finding)"
    r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
SOURCE_LOCATOR_RE = re.compile(
    r"(?:"
    r"\b(?:p{1,2}\.?|pages?|section|sec\.?|table|figure|equation|"
    r"theorem|lemma|appendix|supplement|paragraph|heading|lines?|anchor)"
    r"\s*[#§:]?\s*[A-Za-z]?\d+(?:\.\d+)*(?:\s*[-–]\s*\d+(?:\.\d+)*)?\b"
    r"|\b(?:abstract|introduction|conclusion|methods?|results?)\b"
    r"|\b(?:metadata|publisher|proceedings|official)\s+record\s*[:#]?\s*\S+"
    r"|§\s*\d+(?:\.\d+)*"
    r"|第\s*\d+(?:\.\d+)*\s*[页节]"
    r"|[表图式]\s*\(?\s*\d+(?:\.\d+)*(?:-\d+)?\s*\)?"
    r"|附录\s*[A-Za-z0-9]+"
    r")",
    re.IGNORECASE,
)


def ordered_unique(values: Iterable[str]) -> list[str]:
    """Return exact non-empty strings once, preserving first-observed order."""

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def governing_rule_public_endpoint_sequence(process: dict[str, Any]) -> list[str]:
    """Return process-bound governing URLs in deterministic receipt order."""

    values = process.get("governing_rule_urls", [])
    if not isinstance(values, list):
        return []
    return ordered_unique(value for value in values if isinstance(value, str))


def bibliography_ledger_public_endpoint_sequence(
    bibliography_ledger: Iterable[dict[str, Any]],
) -> list[str]:
    """Return bibliography access endpoints in authoritative CSV row order."""

    endpoints: list[str] = []
    for row in bibliography_ledger:
        endpoint = row.get("EvidenceEndpoint", "")
        if isinstance(endpoint, str) and endpoint.strip():
            endpoints.append(endpoint.strip())
        note = row.get("EvidenceNote", "")
        if isinstance(note, str):
            endpoints.extend(
                match.group(1)
                for match in ACCESS_ENDPOINT_MARKER_RE.finditer(note)
            )
    return ordered_unique(endpoints)


def bibliography_ledger_public_endpoints(
    bibliography_ledger: Iterable[dict[str, Any]],
) -> set[str]:
    """Return the exact set form used by bibliography receipt validation."""

    return set(bibliography_ledger_public_endpoint_sequence(bibliography_ledger))


def citation_ledger_public_endpoint_sequence(
    citation_ledger: Iterable[dict[str, Any]],
) -> list[str]:
    """Return endpoints explicitly recorded as opened in canonical ``04`` order.

    ``ContentSourceOpened`` stores the one source endpoint used for the support
    verdict.  Redirects, failed official routes, and fallback attempts are
    access evidence only when ``DispositionEvidence`` labels each one with the
    closed marker ``accessed endpoint: <URL>``.  URLs in propositions or
    ``PublicIdentifier`` identify text or a work; they do not prove access.
    The Markdown receipt is never scanned, so it cannot authorize itself.
    """

    endpoints: list[str] = []
    for row in citation_ledger:
        content = row.get("ContentSourceOpened", "")
        if isinstance(content, str):
            content = content.strip()
            if content and PUBLIC_URL_RE.fullmatch(content):
                endpoints.append(content)
        disposition = row.get("DispositionEvidence", "")
        if isinstance(disposition, str):
            endpoints.extend(
                match.group(1)
                for match in ACCESS_ENDPOINT_MARKER_RE.finditer(disposition)
            )
    return ordered_unique(endpoints)


def citation_ledger_public_endpoints(
    citation_ledger: Iterable[dict[str, Any]],
) -> set[str]:
    """Return the exact set form used by citation receipt validation."""

    return set(citation_ledger_public_endpoint_sequence(citation_ledger))


def validate_bibliography_endpoint_records(
    bibliography_ledger: Iterable[dict[str, Any]],
    filename: str,
    errors: list[str],
) -> None:
    """Validate auxiliary bibliography routes recorded in ``EvidenceNote``.

    ``EvidenceEndpoint`` remains the authoritative endpoint for the field
    verdict. Any additional redirect, failed official route, or fallback that
    was actually opened is written with the same closed marker used by the
    citation ledger: ``accessed endpoint: <URL>``. This makes the actor receipt
    mechanically derivable without treating arbitrary metadata URLs as access.
    """

    for line, row in enumerate(bibliography_ledger, start=2):
        note = row.get("EvidenceNote", "")
        if not isinstance(note, str):
            continue
        marked = [
            match.group(1)
            for match in ACCESS_ENDPOINT_MARKER_RE.finditer(note)
        ]
        marker_count = len(re.findall(r"(?i)accessed\s+endpoint\s*:", note))
        if marker_count != len(marked):
            errors.append(
                f"{filename}:{line}: every 'accessed endpoint:' marker in "
                "EvidenceNote must contain one complete http(s) URL and be "
                "delimited by the start of the field, a semicolon, or a newline"
            )
        note_urls = {match.group(0) for match in PUBLIC_URL_RE.finditer(note)}
        unmarked = sorted(note_urls - set(marked))
        if unmarked:
            errors.append(
                f"{filename}:{line}: EvidenceNote URL(s) must use the closed "
                f"'accessed endpoint: <URL>' marker; unmarked={unmarked}"
            )


def validate_citation_endpoint_records(
    citation_ledger: Iterable[dict[str, Any]],
    filename: str,
    errors: list[str],
) -> None:
    """Validate the closed source/auxiliary endpoint recording grammar."""

    for line, row in enumerate(citation_ledger, start=2):
        content = row.get("ContentSourceOpened", "")
        if isinstance(content, str):
            content = content.strip()
        else:
            content = ""
        if content and PUBLIC_URL_RE.fullmatch(content) is None:
            errors.append(
                f"{filename}:{line}: ContentSourceOpened must be exactly one "
                "complete http(s) endpoint"
            )
        disposition = row.get("DispositionEvidence", "")
        if not isinstance(disposition, str):
            continue
        marked = [
            match.group(1)
            for match in ACCESS_ENDPOINT_MARKER_RE.finditer(disposition)
        ]
        marker_count = len(
            re.findall(r"(?i)accessed\s+endpoint\s*:", disposition)
        )
        if marker_count != len(marked):
            errors.append(
                f"{filename}:{line}: every 'accessed endpoint:' marker must "
                "contain one complete http(s) URL and be delimited by the "
                "start of the field, a semicolon, or a newline"
            )
        disposition_urls = {
            match.group(0) for match in PUBLIC_URL_RE.finditer(disposition)
        }
        unmarked = sorted(disposition_urls - set(marked))
        if unmarked:
            errors.append(
                f"{filename}:{line}: DispositionEvidence URL(s) must use the "
                f"closed 'accessed endpoint: <URL>' marker; unmarked={unmarked}"
            )


def normalized_doi_tokens(value: str) -> set[str]:
    """Extract complete DOI tokens for identity comparison.

    DOI suffixes are not restricted to the common Crossref character subset;
    historical DOI forms legitimately contain characters such as ``<``, ``>``,
    ``&``, and ``=``. Percent decoding is applied to the DOI token only, after
    its raw span is identified. For a token inside an HTTP(S) URL, an unescaped
    ``?`` or ``#`` starts the URL query/fragment and is not part of the DOI;
    outside a URL it remains a legal DOI suffix character. Only terminal prose
    punctuation is removed.
    """

    raw_value = value or ""
    url_spans = [match.span() for match in PUBLIC_URL_RE.finditer(raw_value)]
    tokens: set[str] = set()
    for match in DOI_TOKEN_RE.finditer(raw_value):
        raw_token = match.group(0)
        if any(start <= match.start() < end for start, end in url_spans):
            raw_token = raw_token.split("?", 1)[0].split("#", 1)[0]
        token = unquote(raw_token).rstrip(".,;:").casefold()
        if token:
            tokens.add(token)
    return tokens


def normalized_arxiv_ids(value: str) -> set[str]:
    """Extract version-insensitive arXiv work identifiers."""

    decoded = unquote(value or "")
    return {
        match.group(1).casefold()
        for match in ARXIV_ID_RE.finditer(decoded)
    }


def normalized_rendered_urls(value: str) -> set[str]:
    """Extract rendered URL identities without erasing path/query case.

    URL schemes and host names are case-insensitive; paths and queries are not.
    The latter therefore remain byte-for-byte case-sensitive, including
    percent-encoded reserved characters. Decoding ``%2F`` into ``/`` would
    conflate two resources that an HTTP server may route differently.
    """

    identities: set[str] = set()
    for match in PUBLIC_URL_RE.finditer(value or ""):
        raw = match.group(0).rstrip(".,;:")
        if not raw:
            continue
        parts = urlsplit(raw)
        identities.add(
            urlunsplit(
                (
                    parts.scheme.casefold(),
                    parts.netloc.casefold(),
                    parts.path,
                    parts.query,
                    parts.fragment,
                )
            )
        )
    return identities


def validate_citation_source_identity(
    citation_ledger: Iterable[dict[str, Any]],
    bibliography_inventory_by_id: dict[str, dict[str, Any]],
    filename: str,
    errors: list[str],
) -> None:
    """Bind every auditable citation endpoint to the complete rendered identity.

    A syntactically valid URL is not enough. When the rendered bibliography
    exposes a DOI, arXiv ID, or official URL, ``PublicIdentifier`` must preserve
    that complete identity and ``ContentSourceOpened`` must resolve through the
    same identity (or an exact official URL also rendered for the work). This
    prevents a truncated DOI prefix from masquerading as an inaccessible source.

    References with no mechanically recoverable persistent identifier remain a
    semantic reviewer responsibility; dangling references are validated by their
    separate closed contract.
    """

    for line, row in enumerate(citation_ledger, start=2):
        reference_id = str(row.get("ReferenceID", ""))
        inventory_row = bibliography_inventory_by_id.get(reference_id)
        if inventory_row is None:
            continue
        rendered = str(inventory_row.get("RenderedEntry", ""))
        expected_dois = normalized_doi_tokens(rendered)
        expected_arxiv = normalized_arxiv_ids(rendered)
        expected_urls = normalized_rendered_urls(rendered)
        if not (expected_dois or expected_arxiv or expected_urls):
            continue

        public_identifier = str(row.get("PublicIdentifier", "")).strip()
        content_source = str(row.get("ContentSourceOpened", "")).strip()
        public_dois = normalized_doi_tokens(public_identifier)
        public_arxiv = normalized_arxiv_ids(public_identifier)
        public_urls = normalized_rendered_urls(public_identifier)
        content_dois = normalized_doi_tokens(content_source)
        content_arxiv = normalized_arxiv_ids(content_source)
        content_urls = normalized_rendered_urls(content_source)
        location = f"{filename}:{line}"

        if expected_dois:
            if not (expected_dois & public_dois):
                errors.append(
                    f"{location}: PublicIdentifier does not preserve the complete "
                    f"rendered DOI for {reference_id}; expected one of "
                    f"{sorted(expected_dois)}"
                )
            if content_source and not (
                (expected_dois & content_dois) or (expected_urls & content_urls)
            ):
                errors.append(
                    f"{location}: ContentSourceOpened is not bound to the complete "
                    f"rendered DOI or exact rendered official URL for {reference_id}"
                )
        elif expected_arxiv:
            if not (expected_arxiv & public_arxiv):
                errors.append(
                    f"{location}: PublicIdentifier does not preserve the complete "
                    f"rendered arXiv ID for {reference_id}; expected one of "
                    f"{sorted(expected_arxiv)}"
                )
            if content_source and not (
                (expected_arxiv & content_arxiv) or (expected_urls & content_urls)
            ):
                errors.append(
                    f"{location}: ContentSourceOpened is not bound to the complete "
                    f"rendered arXiv ID or exact rendered official URL for "
                    f"{reference_id}"
                )
        elif not (expected_urls & public_urls):
            errors.append(
                f"{location}: PublicIdentifier does not equal an official URL "
                f"rendered for {reference_id}"
            )
        elif content_source and not (expected_urls & content_urls):
            errors.append(
                f"{location}: ContentSourceOpened does not equal an official URL "
                f"rendered for {reference_id}"
            )


def validate_bibliography_source_identity(
    bibliography_ledger: Iterable[dict[str, Any]],
    bibliography_inventory_by_id: dict[str, dict[str, Any]],
    filename: str,
    errors: list[str],
) -> None:
    """Bind every bibliography evidence route to the complete rendered work.

    ``unverifiable`` is a metadata verdict, not permission to skip an audit.
    Every field row must therefore record the one complete authoritative route
    that was actually attempted. When the rendered reference exposes a DOI,
    arXiv identifier, or official URL, that route must preserve the complete
    identity rather than a syntactically valid but truncated prefix.

    Entries without a machine-recoverable persistent identifier still require
    a non-empty authoritative route; deciding whether a title-query or
    proceedings record is genuinely work-specific remains the reviewer's
    semantic responsibility.
    """

    for line, row in enumerate(bibliography_ledger, start=2):
        reference_id = str(row.get("ReferenceID", ""))
        endpoint = str(row.get("EvidenceEndpoint", "")).strip()
        location = f"{filename}:{line}"
        if not endpoint:
            errors.append(
                f"{location}: every bibliography field, including an "
                "unverifiable verdict, must record the complete authoritative "
                "EvidenceEndpoint actually attempted"
            )
            continue

        inventory_row = bibliography_inventory_by_id.get(reference_id)
        if inventory_row is None:
            continue
        rendered = str(inventory_row.get("RenderedEntry", ""))
        expected_dois = normalized_doi_tokens(rendered)
        expected_arxiv = normalized_arxiv_ids(rendered)
        expected_urls = normalized_rendered_urls(rendered)
        endpoint_dois = normalized_doi_tokens(endpoint)
        endpoint_arxiv = normalized_arxiv_ids(endpoint)
        endpoint_urls = normalized_rendered_urls(endpoint)

        if expected_dois and not (
            (expected_dois & endpoint_dois) or (expected_urls & endpoint_urls)
        ):
            errors.append(
                f"{location}: EvidenceEndpoint is not bound to the complete "
                f"rendered DOI or exact rendered official URL for {reference_id}; "
                f"expected one of {sorted(expected_dois)}"
            )
        elif expected_arxiv and not (
            (expected_arxiv & endpoint_arxiv) or (expected_urls & endpoint_urls)
        ):
            errors.append(
                f"{location}: EvidenceEndpoint is not bound to the complete "
                f"rendered arXiv ID or exact rendered official URL for "
                f"{reference_id}; expected one of {sorted(expected_arxiv)}"
            )
        elif (
            not expected_dois
            and not expected_arxiv
            and expected_urls
            and not (expected_urls & endpoint_urls)
        ):
            errors.append(
                f"{location}: EvidenceEndpoint does not equal an official URL "
                f"rendered for {reference_id}"
            )


PAGE_ID_RE = re.compile(r"^P(\d{4})$")
REFERENCE_ID_RE = re.compile(r"^REF(\d{4})$")
OCCURRENCE_ID_RE = re.compile(r"^C(\d{4})$")
PAIR_ID_RE = re.compile(r"^C(\d{4})-S(\d{2,4})$")
PAIR_ID_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])C\d{4}-S\d{2,4}(?![A-Za-z0-9])"
)
BRACKET_CANDIDATE_ID_RE = re.compile(r"^BC(\d{4})$")
NUMERIC_BRACKET_RE = re.compile(
    r"\[(?P<items>\d{1,4}(?:\s*[-–—]\s*\d{1,4})?"
    r"(?:\s*[,，]\s*\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)*)\]"
)
NUMERIC_BRACKET_SPAN_RE = re.compile(r"\[[^\[\]]+\]")

PAGE_INVENTORY_COLUMNS = [
    "PageID", "PhysicalPage", "PrintedPage", "Region",
    "MechanicalSignals", "PDFSHA256",
]
PAGE_LEDGER_COLUMNS = [
    "PageID", "PhysicalPage", "PrintedPage", "Region", "DominantContent",
    "Signals", "InspectionModeScale", "RenderDPI", "RenderArtifactIDHash",
    "NeighborPagesChecked", "Disposition", "Evidence", "PDFSHA256",
]
PAGE_MARKDOWN_HEADERS = [
    "Page ID", "Physical page", "Printed page", "Region",
    "Dominant content", "Signals", "Inspection mode/scale", "Render DPI",
    "Render artifact ID/hash", "Neighbor pages checked", "Disposition",
    "Evidence",
]
PAGE_MARKDOWN_FIELDS = [
    "PageID", "PhysicalPage", "PrintedPage", "Region", "DominantContent",
    "Signals", "InspectionModeScale", "RenderDPI", "RenderArtifactIDHash",
    "NeighborPagesChecked", "Disposition", "Evidence",
]
BIB_INVENTORY_COLUMNS = [
    "ReferenceID", "DisplayedLabel", "RenderedEntry", "Cited", "PDFSHA256",
]
BIB_LEDGER_COLUMNS = [
    "ReferenceID", "DisplayedLabel", "Cited", "Field", "RenderedValue",
    "CanonicalValue", "Verdict", "EvidenceEndpoint", "EndpointType",
    "CheckedAt", "EvidenceNote", "FindingDisposition", "PDFSHA256",
]
BIB_MARKDOWN_HEADERS = [
    "Reference ID", "Displayed label", "Cited?", "Type", "Title",
    "Ordered authors", "Year", "Venue", "Publication status",
    "Volume/issue", "Pages/article no.",
    "Persistent IDs/URL/access date", "Existence",
    "Retraction/correction/superseding", "Finding/disposition",
]
CITATION_CANDIDATE_COLUMNS = [
    "CandidateID", "PhysicalPage", "Marker", "ExpandedNumbers",
    "Classification", "ClassificationEvidence", "MappedOccurrenceID",
    "AdjacentPDFText", "PDFSHA256",
]
UNMATCHED_BRACKET_COLUMNS = [
    "GlyphID", "PhysicalPage", "Glyph", "AdjacentPDFText", "Disposition",
    "PDFSHA256",
]
CITATION_INVENTORY_COLUMNS = [
    "PairID", "OccurrenceID", "PDFLocation", "DisplayedReferenceID",
    "AdjacentPDFText", "PDFSHA256",
]
CITATION_LEDGER_COLUMNS = [
    "PairID", "OccurrenceID", "PDFLocation", "ExactAttachedProposition",
    "ReferenceID", "PublicIdentifier", "ContentSourceOpened",
    "ExactSourceLocator", "Support", "MetadataStatus", "SeverityFinding",
    "DispositionEvidence", "PDFSHA256",
]
CITATION_MARKDOWN_HEADERS = [
    "Pair ID", "Occurrence ID", "PDF location",
    "Exact attached proposition", "Reference ID", "Displayed label",
    "Public source/identifier", "Content source opened and exact locator",
    "Support", "Metadata/status", "Severity/finding",
    "Disposition/evidence",
]
DANGLING_REFERENCE_SENTINEL = "no rendered bibliography entry"
REVIEWER_ASSESSMENT_HEADERS = [
    "Gate",
    "Review depth (`baseline` / `emphasized` / `primary`)",
    "Disposition (`adequate` / `concern` / `unverifiable` / `N/A`)",
    "Decisive evidence and exact locations",
    "Related finding IDs or `none`",
    "Confidence/limitation",
]
OWNED_LEDGER_DECLARATION_LABELS = (
    "Actor ID",
    "Review round ID",
    "Review retry ID",
    "Fresh-context declaration",
    "Operational prompt SHA-256",
    "Input-receipt/access declaration",
    "Frozen PDF SHA-256 at start and end",
)
ACADEMIC_LEDGER_COLUMNS = [
    "LedgerID", "Priority", "ChairFindingID", "SourceReviewerFindingIDs",
    "Severity", "S0Subtype", "Remedy", "ExactPDFAnchor", "DirectObservation",
    "EvidenceStatus", "MinimumEditEvidence", "Dependency", "Owner", "Status",
    "Verification",
]
AI_LEDGER_COLUMNS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "Status", "Verification",
]
ACADEMIC_SUMMARY_COLUMNS = [
    "LedgerID", "Priority", "ChairFindingID", "SourceReviewerFindingIDs",
    "Severity", "S0Subtype", "Remedy", "ExactPDFAnchor", "DirectObservation",
    "EvidenceStatus", "MinimumEditEvidence", "Dependency", "Owner", "Status",
    "Verification",
]
AI_SUMMARY_COLUMNS = [
    "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
    "MinimumEditingAction", "Status", "Verification",
]
EVIDENCE_ITEM_COLUMNS = [
    "EvidenceItemID", "LedgerID", "ChairFindingID", "Remedy", "Item",
    "ClaimThatDependsOnIt", "WhyWritingIsInsufficient",
    "MinimumViableEvidence", "ConsequenceIfUnavailable",
]
PRIOR_ISSUES_COLUMNS = [
    "PriorFindingID", "PriorPDFSHA256", "PriorPDFAnchor", "Finding",
    "RequiredClosureEvidence",
]

BIB_FIELD_ORDER = (
    "type", "title", "ordered_authors", "year", "venue",
    "publication_status", "volume", "issue", "pages_or_article_number",
    "doi", "arxiv_id", "arxiv_version", "url", "access_date",
    "isbn_or_other_persistent_id", "existence",
    "retraction_withdrawal_correction_superseding",
)
BIB_FIELDS = set(BIB_FIELD_ORDER)
BIB_MARKDOWN_FIELD_GROUPS = (
    ("Type", ("type",)),
    ("Title", ("title",)),
    ("Ordered authors", ("ordered_authors",)),
    ("Year", ("year",)),
    ("Venue", ("venue",)),
    ("Publication status", ("publication_status",)),
    ("Volume/issue", ("volume", "issue")),
    ("Pages/article no.", ("pages_or_article_number",)),
    (
        "Persistent IDs/URL/access date",
        (
            "doi", "arxiv_id", "arxiv_version", "url", "access_date",
            "isbn_or_other_persistent_id",
        ),
    ),
    ("Existence", ("existence",)),
    (
        "Retraction/correction/superseding",
        ("retraction_withdrawal_correction_superseding",),
    ),
)
BIB_VERDICTS = {"exact", "mismatch", "legitimate n/a", "unverifiable"}
SUPPORT_VALUES = {
    "direct", "partial", "context-only", "mismatch", "unverifiable",
    "not-needed",
}
METADATA_STATUS_VALUES = {"verified", "mismatch", "unverifiable"}
CLOSED_STATUSES = {
    "closed", "resolved", "not required", "not applicable", "n/a",
}
STATUS_VALUES = CLOSED_STATUSES | {"open"}
ACADEMIC_SEVERITIES = {"s0", "s1", "s2", "s3"}
ACADEMIC_REMEDIES = {"w", "e", "n", "p"}
ACADEMIC_PRIORITIES = {"p0", "p1", "p2", "p3"}
AI_ACTION_IMPACTS = {"material", "local"}
EVIDENCE_ITEM_ID_RE = re.compile(r"^N(\d{2,4})$")
PLACEHOLDERS = {
    "pending", "unchecked", "...", "…", "todo", "tbd",
    "placeholder", "not checked", "not verified", "x",
}
NON_SIGNAL_VALUES = {
    "none", "clean", "no signal", "no signals", "n/a", "not applicable",
}
AI_REQUIRED_DISCLAIMER = (
    "This is a prose-style assessment, not a determination of AI use, "
    "authorship, plagiarism, or misconduct."
)
AI_ALLOWED_STRUCTURED_LABELS = {
    "Actor ID", "Review round ID", "Review retry ID", "Frozen artifact",
    "Reviewer-visible inputs", "Excluded material", "Fresh-context declaration",
    "Independence declaration", "Operational prompt SHA-256",
    "Input-receipt/access declaration", "Frozen PDF SHA-256 at start and end",
    "Required disclaimer", "AI-style signal", "Confidence", "Rationale",
    "Physical pages inspected", "Authored sections inspected",
    "Recurrent-pattern queries/statistics", "Corpus exclusions", "Impact",
    "Location", "Recurrent evidence", "Reader impact",
    "Minimum safe editing strategy", "Closure test",
}
INSPECTION_MODE_PREFIXES = ("individual", "small-legible-group", "full-scale")

PROCESS_KEYS = {
    "round_id", "retry_id", "frozen_pdf_file", "selected_pdf_sha256",
    "physical_page_count", "frozen_at", "degree_level", "degree_type", "institution",
    "school_or_department", "discipline", "expected_submission_year",
    "artifact_type", "review_mode", "output_language",
    "governing_rule_urls", "governing_local_files",
    "decision_regime_status", "actor_prompt_sha256",
}
HELPER_PROVENANCE_KEYS = {
    "actor_id", "round_id", "retry_id", "prompt_sha256",
    "fresh_context_declaration", "input_receipt_access_declaration",
    "received_blocks", "opened_inputs", "tool", "version",
    "command_or_query", "pdf_sha256_start", "pdf_sha256_end", "outputs",
    "limitations", "recipient_stages",
}
HELPER_OUTPUT_KEYS = {"file", "sha256"}

CANDIDATE_CLASSIFICATIONS = {"citation", "non-citation"}
DEFAULT_RECOMMENDATIONS = {
    "A": "同意答辩",
    "B": "小修后可答辩",
    "C": "大修后重新送审，复审通过后方可答辩",
    "D": "不同意答辩",
}
PERSONA_ASSIGNMENTS = {
    "doctorate": {
        1: "R1 technical/methods/experiments",
        2: "R2 contribution/novelty/positioning",
        3: "R3 thesis architecture/narrative",
        4: "R4 evidence/reproducibility/integrity/citation",
        5: "R5 format/bibliography/layout",
    },
    "masters": {
        1: "R1 technical/methods/experiments",
        2: "R2 contribution/positioning + thesis architecture/narrative",
        3: "R3 evidence/integrity/citation + format/bibliography/layout",
    },
}

SKILL_REFERENCE_FILES = [
    "clean-room-orchestration.md", "china-policy.md",
    "grading-and-verdicts.md", "review-rubric.md", "reviewer-panels.md",
    "report-template.md", "ledger-validation.md", "rendered-pagination-audit.md",
    "citation-audit.md", "ai-style-audit.md",
]
R5_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/materialize_owner_outputs.py",
    "rules/scripts/validate_r5_output.py",
]
ORDINARY_REVIEWER_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_reviewer_output.py",
]
R4_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/materialize_owner_outputs.py",
    "rules/scripts/validate_r5_output.py",
    "rules/scripts/validate_r4_output.py",
]
MASTER_R3_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/materialize_owner_outputs.py",
    "rules/scripts/validate_r5_output.py",
    "rules/scripts/validate_master_r3_output.py",
]
AI_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_ai_output.py",
]
CHAIR_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/materialize_owner_outputs.py",
    "rules/scripts/validate_chair_output.py",
]
SUMMARY_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/materialize_owner_outputs.py",
    "rules/scripts/validate_summary_output.py",
]
P_VALIDATOR_RULE_INPUTS = [
    "rules/scripts/validate_review_bundle.py",
    "rules/scripts/validate_stage_p_output.py",
]


def portable_basename_key(value: str) -> str:
    """Return the collision key used by case-insensitive Win32 filesystems."""

    return unicodedata.normalize("NFC", value).rstrip(" .").casefold()


def is_neutral_portable_basename(value: str) -> bool:
    """Reject path tricks and platform aliases from a closed review root."""

    if (
        not value
        or value != value.strip()
        or value != value.rstrip(" .")
        or unicodedata.normalize("NFC", value) != value
        or Path(value).name != value
        or len(value) > 255
        or re.search(r'[<>:"/\\|?*;`\[\]\x00-\x1f]', value)
    ):
        return False
    stem = value.split(".", 1)[0].casefold()
    if stem in {"con", "prn", "aux", "nul"}:
        return False
    if re.fullmatch(r"(?:com|lpt)[1-9]", stem):
        return False
    return True


def is_link_or_reparse(path: Path) -> bool:
    """Detect symlinks, NTFS junctions, and other reparse-point aliases."""

    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    except OSError:
        return False


def validate_write_report_destination(
    root: Path, requested_report: Path, errors: list[str]
) -> Path | None:
    """Accept only the canonical absent or single-link regular report file."""

    expected_report = root / "95-bundle-validation.md"
    if (
        requested_report.parent != root
        or requested_report.name != expected_report.name
    ):
        errors.append(
            "--write-report must target exactly the in-root regular file "
            f"{expected_report}"
        )
        return None
    try:
        metadata = expected_report.lstat()
    except FileNotFoundError:
        return expected_report
    except OSError as exc:
        errors.append(
            "--write-report cannot safely inspect the canonical destination "
            f"{expected_report}: {exc}"
        )
        return None

    attributes = getattr(metadata, "st_file_attributes", 0)
    is_reparse = bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    if (
        stat.S_ISLNK(metadata.st_mode)
        or is_reparse
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        errors.append(
            "--write-report must target exactly the in-root regular file "
            f"{expected_report}; an existing destination must be a regular, "
            "non-symlink, non-junction/reparse, single-link file "
            "(st_nlink == 1)"
        )
        return None
    return expected_report


def atomic_write_validation_report(path: Path, text: str) -> str | None:
    """Replace the canonical report without following an existing path alias."""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".95-bundle-validation-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
        temporary_path = None
        return None
    except OSError as exc:
        return f"--write-report could not safely replace {path}: {exc}"
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def preflight_reparse_boundary(root: Path, errors: list[str]) -> bool:
    """Refuse link-like entries before any round artifact is opened."""

    if is_link_or_reparse(root):
        errors.append("round directory itself is a symlink/junction/reparse point")
        return False
    try:
        root_entries = list(root.iterdir())
    except OSError as exc:
        errors.append(f"cannot enumerate round directory for boundary preflight: {exc}")
        return False
    invalid: list[str] = []
    for entry in root_entries:
        if is_link_or_reparse(entry):
            invalid.append(entry.name)
            continue
        if entry.is_dir():
            try:
                children = list(entry.iterdir())
            except OSError as exc:
                errors.append(
                    f"cannot enumerate {entry.name!r} for boundary preflight: {exc}"
                )
                continue
            invalid.extend(
                f"{entry.name}/{child.name}"
                for child in children
                if is_link_or_reparse(child)
            )
    if invalid:
        errors.append(
            "closed current-round boundary contains symlink/junction/reparse "
            f"entries: {sorted(invalid)}"
        )
        return False
    return not errors

# These basenames already identify skill instructions, generated round artifacts,
# or closed-root directories. Reusing one for a governing file or the frozen PDF
# would make basename-only opened-input receipts ambiguous even when the bytes hash.
RESERVED_ROUND_BASENAMES = {
    "00-process-parameters.json", "SKILL.md", *SKILL_REFERENCE_FILES,
    *(Path(value).name for value in (
        *P_VALIDATOR_RULE_INPUTS,
        *ORDINARY_REVIEWER_VALIDATOR_RULE_INPUTS,
        *R4_VALIDATOR_RULE_INPUTS,
        *MASTER_R3_VALIDATOR_RULE_INPUTS,
        *R5_VALIDATOR_RULE_INPUTS,
        *AI_VALIDATOR_RULE_INPUTS,
        *CHAIR_VALIDATOR_RULE_INPUTS,
        *SUMMARY_VALIDATOR_RULE_INPUTS,
    )),
    "00-manifest.md", "00-page-inventory.csv",
    "00-bibliography-inventory.csv", "00-citation-candidate-ledger.csv",
    "00-unmatched-bracket-ledger.csv", "00-citation-inventory.csv",
    "01-policy-basis.md", "02-page-layout-ledger.md",
    "02-page-layout-ledger.csv", "03-bibliography-audit-ledger.md",
    "03-bibliography-audit-ledger.csv", "04-citation-claim-audit-ledger.md",
    "04-citation-claim-audit-ledger.csv", "05-ai-style-assessment.md",
    "90-chair-synthesis.md", "91-revision-ledger.md",
    "91-revision-ledger.csv", "91-ai-actionable-ledger.csv",
    "92-new-evidence-or-experiments.md",
    "92-new-evidence-or-experiments.csv", "93-user-facing-summary.md",
    "93-current-actionable-items.csv", "93-current-ai-actionable-items.csv",
    "94-post-freeze-prior-issue-closure.md", "95-bundle-validation.md",
    *(f"R{index}-comprehensive-review.md" for index in range(1, 6)),
    "page-renders", "helpers", "stage-v-inputs",
}
RESERVED_ROUND_BASENAME_KEYS = {
    portable_basename_key(value) for value in RESERVED_ROUND_BASENAMES
}
RENDER_ARTIFACT_BASENAME_RE = re.compile(r"^P\d{4}\.png$", re.IGNORECASE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def markdown_visible_text(text: str) -> str:
    """Remove fenced code and HTML comments before structural validation.

    Newlines are preserved so locations and Markdown block boundaries remain stable.
    Required declarations, headings, labels, and tables inside non-rendered blocks
    must never satisfy the review-bundle contract.
    """

    text = re.sub(
        r"(?s)<!--.*?(?:-->|\Z)",
        lambda match: "\n" * match.group(0).count("\n"),
        text,
    )
    output: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if fence is None and marker:
            token = marker.group(1)
            fence = (token[0], len(token))
            output.append("\n" if line.endswith(("\n", "\r")) else "")
            continue
        if fence is not None:
            closing = re.match(rf"{re.escape(fence[0])}{{{fence[1]},}}[ \t]*$", stripped.rstrip("\r\n"))
            output.append("\n" if line.endswith(("\n", "\r")) else "")
            if closing:
                fence = None
            continue
        if re.match(r"^(?: {4,}|\t)", line):
            output.append("\n" if line.endswith(("\n", "\r")) else "")
            continue
        output.append(line)
    return "".join(output)


def validate_pdf_structure_and_pages(
    path: Path, declared_pages: int, errors: list[str]
) -> list[tuple[float, float]]:
    try:
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                errors.append(f"{path.name}: invalid PDF header")
                return []
    except OSError as exc:
        errors.append(f"{path.name}: cannot read PDF header: {exc}")
        return []
    try:
        from pypdf import PdfReader
    except ImportError:
        errors.append(
            "validator dependency missing: install pypdf or use the bundled "
            "workspace Python runtime"
        )
        return []
    try:
        reader = PdfReader(str(path), strict=False)
        actual_pages = len(reader.pages)
        page_sizes: list[tuple[float, float]] = []
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if int(page.rotation or 0) % 180:
                width, height = height, width
            page_sizes.append((width, height))
    except Exception as exc:  # pypdf exposes several parser exception types
        errors.append(f"{path.name}: cannot parse frozen PDF: {exc}")
        return []
    if actual_pages < 1:
        errors.append(f"{path.name}: parsed PDF has no pages")
    if declared_pages and actual_pages != declared_pages:
        errors.append(
            f"{path.name}: parsed page count {actual_pages} != "
            f"physical_page_count {declared_pages}"
        )
    return page_sizes


def normalize_numeric_marker(value: str) -> str:
    """Normalize only layout variants while preserving the numeric grammar."""
    return (
        re.sub(r"\s+", "", value)
        .replace("，", ",")
        .replace("–", "-")
        .replace("—", "-")
    )


def normalize_extracted_text(value: str) -> str:
    """Use one deterministic whitespace normalization for every PDF anchor."""
    return re.sub(r"\s+", " ", value).strip()


def expand_numeric_marker(value: str) -> list[int] | None:
    match = NUMERIC_BRACKET_RE.fullmatch(value.strip())
    if not match:
        return None
    expanded: list[int] = []
    for token in re.split(r"[,，]", match.group("items")):
        token = token.strip()
        range_match = re.fullmatch(r"(\d{1,4})\s*[-–—]\s*(\d{1,4})", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            step = 1 if end >= start else -1
            expanded.extend(range(start, end + step, step))
        else:
            expanded.append(int(token))
    return expanded


def extract_numeric_bracket_candidates(
    pdf_path: Path,
    reference_pages: set[int],
    errors: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Re-extract the closed Stage-P candidate universe from the frozen PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception as exc:
        errors.append(f"cannot extract citation candidates from frozen PDF: {exc}")
        return [], []
    candidates: list[dict[str, Any]] = []
    unmatched_glyphs: list[dict[str, Any]] = []
    for physical_page, page in enumerate(reader.pages, start=1):
        if physical_page in reference_pages:
            continue
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            errors.append(
                "citation-candidate extraction failed on physical page "
                f"{physical_page}: {exc}"
            )
            continue
        opening_stack: list[int] = []
        unmatched_positions: list[tuple[int, str]] = []
        for offset, character in enumerate(text):
            if character == "[":
                opening_stack.append(offset)
            elif character == "]":
                if opening_stack:
                    opening_stack.pop()
                else:
                    unmatched_positions.append((offset, character))
        unmatched_positions.extend((offset, "[") for offset in opening_stack)
        for offset, glyph in sorted(unmatched_positions):
            start = max(0, offset - 160)
            end = min(len(text), offset + 161)
            unmatched_glyphs.append({
                "PhysicalPage": physical_page,
                "Glyph": glyph,
                "Adjacent": normalize_extracted_text(text[start:end]),
            })
        for match in NUMERIC_BRACKET_SPAN_RE.finditer(text):
            if not re.search(r"\d", match.group(0)):
                continue
            start = max(0, match.start() - 160)
            end = min(len(text), match.end() + 160)
            candidates.append({
                "PhysicalPage": physical_page,
                "Marker": normalize_numeric_marker(match.group(0)),
                "Expanded": expand_numeric_marker(match.group(0)),
                "Adjacent": normalize_extracted_text(text[start:end]),
                "Prefix": text[max(0, match.start() - 100):match.start()],
            })
    return candidates, unmatched_glyphs


def obvious_non_citation_reason(candidate: dict[str, Any]) -> str | None:
    """Reject high-certainty numeric-bracket lookalikes mechanically."""
    if candidate["Expanded"] is None:
        return "numeric bracket is not a pure integer citation marker"
    numbers = list(candidate["Expanded"])
    if 0 in numbers:
        return "zero-bearing numeric interval/vector"
    if len(numbers) != len(set(numbers)):
        return "duplicate-number vector/array"
    prefix = re.sub(r"\s+", " ", str(candidate["Prefix"])).strip()
    if re.search(r"(?:∈|\\in)\s*$", prefix):
        return "mathematical set/interval membership"
    if re.search(
        r"(?:档数(?:依次)?为|量化(?:档|级别)(?:依次)?为|数组(?:为)?|"
        r"向量(?:为)?|形状(?:为)?|尺寸(?:为)?|维度(?:为)?|大小(?:为)?|"
        r"levels?\s*(?:are|=)|array\s*(?:is|=)|vector\s*(?:is|=)|"
        r"(?:tensor\s+)?shape\s*(?:is|=)|size\s*(?:is|=)|=)\s*$",
        prefix,
        flags=re.IGNORECASE,
    ):
        return "explicit numeric vector/array introduction"
    if re.search(
        r"(?:\b(?:interval|range|domain|shape|sizes?|levels?|array|vector)"
        r"(?:\s+(?:is|are|of))?|区间|范围|集合|形状|大小|尺寸|维度)\s*$",
        prefix,
        flags=re.IGNORECASE,
    ):
        return "explicit interval/vector grammatical role"
    if re.search(
        r"\b(?:tensor|array|vector|matrix)\s+[A-Za-z_]\w*\s*$",
        prefix,
        flags=re.IGNORECASE,
    ):
        return "tensor/array index notation"
    return None


def derive_and_validate_reference_pages(
    pdf_path: Path,
    declared_reference_pages: set[int],
    bibliography_rows: list[dict[str, str]],
    errors: list[str],
) -> set[int]:
    """Bind the bibliography region to the rendered [1]...[N] entry run."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception as exc:
        errors.append(f"cannot derive rendered bibliography pages: {exc}")
        return set()
    expected_labels: list[int] = []
    for line, row in enumerate(bibliography_rows, start=2):
        match = re.fullmatch(r"\[(\d{1,4})\]", row.get("DisplayedLabel", ""))
        if not match:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: invalid DisplayedLabel"
            )
            continue
        expected_labels.append(int(match.group(1)))
    expected_sequence = list(range(1, len(bibliography_rows) + 1))
    if expected_labels != expected_sequence:
        errors.append(
            "00-bibliography-inventory.csv: DisplayedLabel sequence is not [1]..[N]"
        )
    page_texts: dict[int, str] = {}
    events: list[tuple[int, int, int, int]] = []
    for physical_page, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            errors.append(
                f"bibliography extraction failed on physical page {physical_page}: {exc}"
            )
            continue
        page_texts[physical_page] = text
        events.extend(
            (
                physical_page,
                int(match.group(1)),
                match.start(),
                match.end(),
            )
            for match in re.finditer(r"(?m)^\s*\[(\d{1,4})\]", text)
        )
    all_runs: list[list[tuple[int, int, int, int]]] = []
    length = len(expected_sequence)
    if length:
        for start, (_page, number, _offset_start, _offset_end) in enumerate(events):
            if number != 1:
                continue
            candidate = [events[start]]
            cursor = start + 1
            expected_next = 2
            while cursor < len(events) and events[cursor][1] == expected_next:
                candidate.append(events[cursor])
                cursor += 1
                expected_next += 1
            all_runs.append(candidate)
    longest_length = max((len(run) for run in all_runs), default=0)
    runs = [run for run in all_runs if len(run) == longest_length]
    if len(runs) != 1 or longest_length != length:
        errors.append(
            "frozen PDF must contain exactly one longest rendered line-start "
            f"bibliography run and its length must equal the {length} inventory "
            f"rows; longest_length={longest_length}, tied_longest_runs={len(runs)}"
        )
        return set()
    rendered_run = runs[0]
    first_page = rendered_run[0][0]
    last_page = rendered_run[-1][0]
    first_page_text = page_texts.get(first_page, "")
    if not re.search(
        r"(?im)(?:^|\n)\s*(?:参考文献|references|bibliography)\s*(?:\n|$)",
        first_page_text,
    ):
        errors.append(
            "rendered bibliography run is not anchored by a References/参考文献 "
            f"heading on physical page {first_page}"
        )
        return set()
    derived_pages = set(range(first_page, last_page + 1))
    if declared_reference_pages != derived_pages:
        errors.append(
            "00-page-inventory.csv: reference Region pages do not equal the "
            f"rendered bibliography span; declared={sorted(declared_reference_pages)}, "
            f"derived={sorted(derived_pages)}"
        )
    expected_entries: list[str] = []
    for index, (current_page, _number, _start, current_end) in enumerate(
        rendered_run
    ):
        if index + 1 < len(rendered_run):
            next_page, _next_number, next_start, _next_end = rendered_run[index + 1]
        else:
            next_page = last_page
            next_start = len(page_texts.get(last_page, ""))
        chunks: list[str] = []
        if current_page == next_page:
            chunks.append(page_texts.get(current_page, "")[current_end:next_start])
        else:
            chunks.append(page_texts.get(current_page, "")[current_end:])
            chunks.extend(
                page_texts.get(page_number, "")
                for page_number in range(current_page + 1, next_page)
            )
            chunks.append(page_texts.get(next_page, "")[:next_start])
        expected_entries.append(normalize_extracted_text("\n".join(chunks)))
    for line, (row, expected_entry) in enumerate(
        zip(bibliography_rows, expected_entries), start=2
    ):
        if row.get("RenderedEntry", "") != expected_entry:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: RenderedEntry does not "
                "exactly equal the deterministic frozen-PDF entry slice"
            )
    return derived_pages


def parse_physical_page_locator(value: str) -> int | None:
    match = re.search(
        r"(?i)(?:\bphysical\s+(?:page\s*)?p?\.?\s*0*(\d+)\b"
        r"|物理(?:页面|页)\s*[:：]?\s*0*(\d+)"
        r"|物理第\s*0*(\d+)\s*页)",
        value,
    )
    if match is None:
        return None
    return int(next(group for group in match.groups() if group is not None))


def parse_canonical_physical_page_locator(value: str) -> int | None:
    """Return the first canonical blind-review locator, ``physical p.<n>``."""

    match = re.search(
        r"(?i)(?<![A-Za-z0-9])physical[ \t]+p\.[ \t]*0*(\d+)"
        r"(?![A-Za-z0-9])",
        value,
    )
    return int(match.group(1)) if match is not None else None


def contains_persona_signal(value: str, signal: str) -> bool:
    """Match a role signal without accepting accidental Latin substrings."""
    if re.search(r"[\u3400-\u9fff]", signal):
        return signal.casefold() in value.casefold()
    return bool(re.search(
        rf"(?<![0-9A-Za-z_]){re.escape(signal)}(?![0-9A-Za-z_])",
        value,
        re.I,
    ))


def validate_iso_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def parse_markdown_pipe_row(line: str) -> list[str] | None:
    """Parse one pipe-table source row using backslash-parity escaping.

    A pipe is a delimiter when preceded by an even number of consecutive
    backslashes and a literal cell character when preceded by an odd number.
    For an escaped pipe, the canonical source encoding uses ``2k+1``
    backslashes to preserve ``k`` logical backslashes immediately before that
    pipe. This round-trips even the otherwise ambiguous ``\\|`` value.
    """

    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return None
    source = stripped[1:-1]
    cells: list[str] = []
    current: list[str] = []
    for character in source:
        if character != "|":
            current.append(character)
            continue
        preceding_backslashes = 0
        for previous in reversed(current):
            if previous != "\\":
                break
            preceding_backslashes += 1
        if preceding_backslashes % 2:
            del current[-preceding_backslashes:]
            current.extend("\\" for _ in range((preceding_backslashes - 1) // 2))
            current.append("|")
            continue
        cells.append("".join(current).strip())
        current = []
    cells.append("".join(current).strip())
    return cells


def validate_markdown_id_projection(
    path: Path,
    expected_ids: set[str],
    id_pattern: re.Pattern[str],
    id_header_aliases: set[str],
    label: str,
    errors: list[str],
    *,
    required_headers: set[str] | None = None,
    same_row_id_headers: set[str] | None = None,
    reference_id_headers: set[str] | None = None,
    reference_id_values: set[str] | None = None,
    section_heading: str | None = None,
) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path.name}: cannot read Markdown master: {exc}")
        return
    text = markdown_visible_text(text)
    if section_heading is not None:
        scoped = markdown_section_body_raw(text, section_heading)
        if scoped is None:
            errors.append(
                f"{path.name}: missing unique Markdown section {section_heading!r} "
                f"for {label} projection"
            )
            return
        text = scoped
    if len(text.strip()) < 32:
        errors.append(f"{path.name}: Markdown master is empty or shell-only")

    def is_separator_row(cells: list[str], width: int) -> bool:
        return (
            len(cells) == width
            and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)
        )

    lines = text.splitlines()
    target_tables: list[tuple[int, list[str], int]] = []
    folded_aliases = {alias.casefold() for alias in id_header_aliases}
    for index in range(len(lines) - 1):
        header = parse_markdown_pipe_row(lines[index])
        separator = parse_markdown_pipe_row(lines[index + 1])
        if header is None or separator is None or not is_separator_row(separator, len(header)):
            continue
        id_columns = [
            column
            for column, cell in enumerate(header)
            if cell.casefold() in folded_aliases
        ]
        if len(id_columns) == 1:
            target_tables.append((index, header, id_columns[0]))
    if len(target_tables) != 1:
        errors.append(
            f"{path.name}: expected exactly one complete Markdown table with "
            f"ID header {sorted(id_header_aliases)}, found {len(target_tables)}"
        )
        compare_sets(f"{label} Markdown projection", expected_ids, set(), errors)
        return

    header_index, header, id_column = target_tables[0]
    if required_headers is not None:
        actual_headers = {cell.casefold() for cell in header}
        missing_headers = sorted(
            value for value in required_headers
            if value.casefold() not in actual_headers
        )
        if missing_headers:
            errors.append(
                f"{path.name}: target Markdown table is missing required "
                f"headers {missing_headers}"
            )
    row_counts: Counter[str] = Counter()
    folded_same_row_headers = {
        value.casefold() for value in (same_row_id_headers or set())
    }
    folded_reference_headers = {
        value.casefold() for value in (reference_id_headers or set())
    }
    data_row_count = 0
    target_data_lines: set[int] = set()
    for line_number in range(header_index + 2, len(lines)):
        cells = parse_markdown_pipe_row(lines[line_number])
        if cells is None:
            break
        target_data_lines.add(line_number)
        data_row_count += 1
        if len(cells) != len(header):
            errors.append(
                f"{path.name}:{line_number + 1}: Markdown table row has "
                f"{len(cells)} cells; expected {len(header)}"
            )
            continue
        identifier = cells[id_column]
        if not id_pattern.fullmatch(identifier):
            errors.append(
                f"{path.name}:{line_number + 1}: ID-column value "
                f"{identifier!r} does not match the required ID format"
            )
            continue
        row_counts[identifier] += 1
        for column, cell in enumerate(cells):
            if column == id_column:
                continue
            misplaced = sorted(set(id_pattern.findall(cell)))
            if (
                misplaced
                and header[column].casefold() in folded_same_row_headers
                and misplaced == [identifier]
            ):
                continue
            if misplaced and header[column].casefold() in folded_reference_headers:
                allowed_references = (
                    expected_ids
                    if reference_id_values is None
                    else reference_id_values
                )
                unknown = sorted(set(misplaced) - allowed_references)
                if not unknown:
                    continue
                errors.append(
                    f"{path.name}:{line_number + 1}: cross-reference column "
                    f"contains unknown IDs {unknown}"
                )
                continue
            if misplaced:
                errors.append(
                    f"{path.name}:{line_number + 1}: IDs must occur only in "
                    f"the designated ID column, found {misplaced}"
                )
    if data_row_count == 0 and expected_ids:
        errors.append(f"{path.name}: target Markdown table has no data rows")
    for line_number, line in enumerate(lines):
        if line_number in target_data_lines:
            continue
        outside_ids = sorted(set(id_pattern.findall(line)))
        if outside_ids:
            errors.append(
                f"{path.name}:{line_number + 1}: IDs outside the target "
                f"Markdown table are forbidden: {outside_ids}"
            )
    actual_ids = set(row_counts)
    compare_sets(f"{label} Markdown projection", expected_ids, actual_ids, errors)
    duplicates = sorted(identifier for identifier, count in row_counts.items() if count != 1)
    if duplicates:
        errors.append(
            f"{path.name}: IDs must occur in exactly one Markdown table row: {duplicates}"
        )


def validate_academic_dependency_references(
    rows: list[dict[str, str]], filename: str, errors: list[str]
) -> None:
    """Treat ``Dependency`` LedgerIDs as closed, non-self, acyclic foreign keys."""

    known = {row.get("LedgerID", "") for row in rows if row.get("LedgerID", "")}
    token_pattern = re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])")
    graph: dict[str, set[str]] = {identifier: set() for identifier in known}
    for line, row in enumerate(rows, start=2):
        ledger_id = row.get("LedgerID", "")
        tokens = token_pattern.findall(row.get("Dependency", ""))
        unknown = sorted(set(tokens) - known)
        if unknown:
            errors.append(
                f"{filename}:{line}: Dependency contains unknown LedgerID "
                f"references {unknown}"
            )
        if ledger_id and ledger_id in tokens:
            errors.append(
                f"{filename}:{line}: Dependency cannot reference its own "
                f"LedgerID {ledger_id}"
            )
        repeated = sorted(
            identifier for identifier, count in Counter(tokens).items() if count > 1
        )
        if repeated:
            errors.append(
                f"{filename}:{line}: Dependency repeats LedgerID references "
                f"{repeated}"
            )
        if ledger_id in graph:
            graph[ledger_id].update(
                token for token in tokens
                if token in known and token != ledger_id
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str, trail: list[str]) -> None:
        if identifier in visited:
            return
        if identifier in visiting:
            start = trail.index(identifier) if identifier in trail else 0
            cycle = [*trail[start:], identifier]
            errors.append(
                f"{filename}: Dependency cycle is forbidden: "
                + " -> ".join(cycle)
            )
            return
        visiting.add(identifier)
        trail.append(identifier)
        for dependency in sorted(graph.get(identifier, set())):
            visit(dependency, trail)
        trail.pop()
        visiting.discard(identifier)
        visited.add(identifier)

    for identifier in sorted(graph):
        visit(identifier, [])


def parse_markdown_table_by_header(
    text: str,
    required_first_header: str,
    filename: str,
    errors: list[str],
) -> tuple[list[str], list[list[str]]] | None:
    """Return one exact pipe table selected by its first header cell."""

    lines = markdown_visible_text(text).splitlines()
    matches: list[tuple[list[str], list[list[str]]]] = []
    for index in range(len(lines) - 1):
        header = parse_markdown_pipe_row(lines[index])
        separator = parse_markdown_pipe_row(lines[index + 1])
        if (
            not header
            or header[0].casefold() != required_first_header.casefold()
            or separator is None
            or len(separator) != len(header)
            or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        ):
            continue
        rows: list[list[str]] = []
        for row_line in lines[index + 2:]:
            row = parse_markdown_pipe_row(row_line)
            if row is None:
                break
            rows.append(row)
        matches.append((header, rows))
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one Markdown table whose first "
            f"header is {required_first_header!r}, found {len(matches)}"
        )
        return None
    header, rows = matches[0]
    for index, row in enumerate(rows, start=1):
        if len(row) != len(header):
            errors.append(
                f"{filename}: selected table row {index} has {len(row)} "
                f"cells; expected {len(header)}"
            )
    return header, rows


def parse_markdown_table_by_exact_headers(
    text: str,
    expected_headers: list[str],
    filename: str,
    errors: list[str],
    *,
    case_sensitive: bool = False,
) -> list[list[str]] | None:
    """Select exactly one pipe table by its complete ordered header schema."""

    expected_schema = (
        expected_headers
        if case_sensitive
        else [value.casefold() for value in expected_headers]
    )
    lines = markdown_visible_text(text).splitlines()
    matches: list[list[list[str]]] = []
    for index in range(len(lines) - 1):
        header = parse_markdown_pipe_row(lines[index])
        separator = parse_markdown_pipe_row(lines[index + 1])
        if (
            header is None
            or (
                header
                if case_sensitive
                else [value.casefold() for value in header]
            ) != expected_schema
            or separator is None
            or len(separator) != len(header)
            or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        ):
            continue
        rows: list[list[str]] = []
        for row_line in lines[index + 2:]:
            row = parse_markdown_pipe_row(row_line)
            if row is None:
                break
            rows.append(row)
        matches.append(rows)
    if len(matches) != 1:
        errors.append(
            f"{filename}: expected exactly one Markdown table with schema "
            f"{expected_headers}, found {len(matches)}"
        )
        return None
    rows = matches[0]
    for index, row in enumerate(rows, start=1):
        if len(row) != len(expected_headers):
            errors.append(
                f"{filename}: selected table row {index} has {len(row)} "
                f"cells; expected {len(expected_headers)}"
            )
    return rows


def validate_declarations_before_main_table(
    text: str,
    expected_headers: list[str],
    filename: str,
    errors: list[str],
) -> None:
    """Require every owned-ledger declaration above its canonical main table."""

    visible = markdown_visible_text(text)
    expected_schema = [value.casefold() for value in expected_headers]
    table_offset: int | None = None
    offset = 0
    for line in visible.splitlines(keepends=True):
        row = parse_markdown_pipe_row(line)
        if row is not None and [value.casefold() for value in row] == expected_schema:
            table_offset = offset
            break
        offset += len(line)
    if table_offset is None:
        return

    late_labels: list[str] = []
    for label in OWNED_LEDGER_DECLARATION_LABELS:
        if label in {
            "Fresh-context declaration", "Input-receipt/access declaration",
        }:
            pattern = (
                rf"(?im)^[ ]{{0,3}}-[ \t]+(?:[A-Za-z-]+[ \t]+)?"
                rf"{re.escape(label)}[ \t]*:[ \t]*(.*?)[ \t]*$"
            )
        elif label == "Frozen PDF SHA-256 at start and end":
            pattern = (
                rf"(?im)^[ ]{{0,3}}(?:-[ \t]+)?{re.escape(label)}"
                rf"[ \t]*:[^\r\n]*$"
            )
        else:
            pattern = (
                rf"(?im)^[ ]{{0,3}}-[ \t]+{re.escape(label)}[ \t]*:"
                rf"[ \t]*(.*?)[ \t]*$"
            )
        matches = list(re.finditer(pattern, visible))
        if any(match.start() >= table_offset for match in matches):
            late_labels.append(label)
    if late_labels:
        errors.append(
            f"{filename}: all required declarations must precede the first "
            f"canonical main table header; late fields {late_labels}"
        )


def count_complete_markdown_pipe_tables(text: str) -> int:
    """Count rendered pipe tables with a header and separator row."""

    lines = markdown_visible_text(text).splitlines()
    count = 0
    for index in range(len(lines) - 1):
        header = parse_markdown_pipe_row(lines[index])
        separator = parse_markdown_pipe_row(lines[index + 1])
        if (
            header is not None
            and separator is not None
            and len(separator) == len(header)
            and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
        ):
            count += 1
    return count


def markdown_projection_scalar(value: str) -> str:
    """Return the deterministic logical Markdown-cell form of a CSV scalar."""

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    # JSON string escaping, without the surrounding quotes, distinguishes real
    # line breaks/backslashes from literal ``\\n`` text while retaining readable
    # ordinary values. This is a logical cell value; source-delimiter escaping is
    # deliberately performed only by ``render_markdown_pipe_table`` below.
    return json.dumps(normalized, ensure_ascii=False)[1:-1]


def markdown_projection_row(
    row: dict[str, str], fields: Iterable[str],
) -> list[str]:
    """Project one authoritative CSV row into logical Markdown cells."""

    return [markdown_projection_scalar(row.get(field, "")) for field in fields]


def markdown_projection_rows(
    rows: Iterable[dict[str, str]], fields: Iterable[str],
) -> list[list[str]]:
    """Project authoritative CSV rows without changing their source order."""

    ordered_fields = tuple(fields)
    return [markdown_projection_row(row, ordered_fields) for row in rows]


def render_markdown_pipe_table(
    headers: list[str], rows: Iterable[Iterable[str]],
) -> str:
    """Render one canonical pipe table from logical cell values.

    The parser decodes the canonical odd-backslash escape back to a literal
    pipe while preserving any logical backslashes immediately before it.
    Keeping this source transformation in production code prevents a pipe
    inside a title, author list, URL, or evidence note from changing the table
    width.
    """

    rendered_rows = [list(row) for row in rows]
    width = len(headers)
    if not headers or any(len(row) != width for row in rendered_rows):
        raise ValueError("Markdown table rows must exactly match the header width")

    def source_cell(value: str) -> str:
        output: list[str] = []
        index = 0
        while index < len(value):
            if value[index] != "\\":
                output.append(r"\|" if value[index] == "|" else value[index])
                index += 1
                continue
            run_end = index
            while run_end < len(value) and value[run_end] == "\\":
                run_end += 1
            count = run_end - index
            if run_end < len(value) and value[run_end] == "|":
                output.append("\\" * (2 * count + 1))
                output.append("|")
                index = run_end + 1
            else:
                output.append("\\" * count)
                index = run_end
        return "".join(output)

    header = "| " + " | ".join(source_cell(value) for value in headers) + " |\n"
    separator = "|" + "|".join("---" for _ in headers) + "|\n"
    body = "".join(
        "| " + " | ".join(source_cell(value) for value in row) + " |\n"
        for row in rendered_rows
    )
    return header + separator + body


def compact_projection_json(value: Any) -> str:
    """Serialize a composite projection with fixed insertion order and no gaps."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def page_markdown_projection_rows(
    page_ledger: list[dict[str, str]],
) -> list[list[str]]:
    return markdown_projection_rows(
        sorted(page_ledger, key=lambda item: item.get("PageID", "")),
        PAGE_MARKDOWN_FIELDS,
    )


def bibliography_markdown_projection_rows(
    bibliography_inventory: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
) -> list[list[str]]:
    """Project the long-form bibliography CSV into its deterministic summary."""

    by_key = {
        (row.get("ReferenceID", ""), row.get("Field", "")): row
        for row in bibliography_ledger
    }

    def field_payload(reference_id: str, field: str) -> dict[str, str]:
        row = by_key.get((reference_id, field), {})
        return {
            "field": field,
            "rendered": row.get("RenderedValue", ""),
            "canonical": row.get("CanonicalValue", ""),
            "verdict": row.get("Verdict", ""),
            "evidence_endpoint": row.get("EvidenceEndpoint", ""),
            "endpoint_type": row.get("EndpointType", ""),
            "checked_at": row.get("CheckedAt", ""),
            "evidence_note": row.get("EvidenceNote", ""),
        }

    rows: list[list[str]] = []
    for inventory_row in sorted(
        bibliography_inventory, key=lambda item: item.get("ReferenceID", "")
    ):
        reference_id = inventory_row.get("ReferenceID", "")
        projected = [
            markdown_projection_scalar(reference_id),
            markdown_projection_scalar(inventory_row.get("DisplayedLabel", "")),
            markdown_projection_scalar(inventory_row.get("Cited", "")),
        ]
        for _, fields in BIB_MARKDOWN_FIELD_GROUPS:
            payloads = [field_payload(reference_id, field) for field in fields]
            projected.append(compact_projection_json(
                payloads[0] if len(payloads) == 1 else payloads
            ))
        projected.append(compact_projection_json([
            {
                "field": field,
                "finding_disposition": by_key.get(
                    (reference_id, field), {}
                ).get("FindingDisposition", ""),
            }
            for field in BIB_FIELD_ORDER
        ]))
        rows.append(projected)
    return rows


def pair_id_sort_key(value: str) -> tuple[int, int, str]:
    match = PAIR_ID_RE.fullmatch(value)
    if match is None:
        return (10_000, 10_000, value)
    return (int(match.group(1)), int(match.group(2)), value)


def displayed_label_for_reference_id(
    reference_id: str,
    bibliography_inventory_by_id: dict[str, dict[str, str]],
) -> str:
    """Project a rendered label, including a PDF-bound dangling marker."""

    inventory_row = bibliography_inventory_by_id.get(reference_id)
    if inventory_row is not None:
        return inventory_row.get("DisplayedLabel", "")
    match = REFERENCE_ID_RE.fullmatch(reference_id)
    return f"[{int(match.group(1))}]" if match is not None else ""


def validate_dangling_citation_audit_row(
    row: dict[str, str],
    bibliography_inventory_by_id: dict[str, dict[str, str]],
    line: int,
    errors: list[str],
) -> None:
    """Keep a dangling citation as an auditable finding, not an I/O error."""

    reference_id = row.get("ReferenceID", "")
    if reference_id in bibliography_inventory_by_id:
        return
    location = f"04-citation-claim-audit-ledger.csv:{line}"
    if row.get("Support", "").casefold() != "unverifiable":
        errors.append(
            f"{location}: dangling {reference_id!r} requires Support=unverifiable"
        )
    if row.get("MetadataStatus", "").casefold() != "mismatch":
        errors.append(
            f"{location}: dangling {reference_id!r} requires MetadataStatus=mismatch"
        )
    if row.get("PublicIdentifier", "") != DANGLING_REFERENCE_SENTINEL:
        errors.append(
            f"{location}: dangling {reference_id!r} requires PublicIdentifier="
            f"{DANGLING_REFERENCE_SENTINEL!r}"
        )
    if row.get("ContentSourceOpened", "") or row.get("ExactSourceLocator", ""):
        errors.append(
            f"{location}: dangling {reference_id!r} must leave content source and "
            "locator blank unless a rendered bibliography identity exists"
        )


def validate_citation_pair_row_order(
    citation_inventory: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
    errors: list[str],
) -> None:
    """Bind the semantic audit's source order to the PDF-derived inventory."""

    inventory_pair_order = [row.get("PairID", "") for row in citation_inventory]
    ledger_pair_order = [row.get("PairID", "") for row in citation_ledger]
    if ledger_pair_order != inventory_pair_order:
        errors.append(
            "04-citation-claim-audit-ledger.csv: PairID row order must exactly "
            "match 00-citation-inventory.csv reading/source order"
        )


def citation_markdown_projection_rows(
    citation_ledger: list[dict[str, str]],
    bibliography_inventory_by_id: dict[str, dict[str, str]],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in sorted(
        citation_ledger,
        key=lambda item: pair_id_sort_key(item.get("PairID", "")),
    ):
        reference_id = row.get("ReferenceID", "")
        content_projection = compact_projection_json({
            "content_source_opened": row.get("ContentSourceOpened", ""),
            "exact_source_locator": row.get("ExactSourceLocator", ""),
        })
        rows.append([
            markdown_projection_scalar(row.get("PairID", "")),
            markdown_projection_scalar(row.get("OccurrenceID", "")),
            markdown_projection_scalar(row.get("PDFLocation", "")),
            markdown_projection_scalar(row.get("ExactAttachedProposition", "")),
            markdown_projection_scalar(reference_id),
            markdown_projection_scalar(
                displayed_label_for_reference_id(
                    reference_id, bibliography_inventory_by_id
                )
            ),
            markdown_projection_scalar(row.get("PublicIdentifier", "")),
            content_projection,
            markdown_projection_scalar(row.get("Support", "")),
            markdown_projection_scalar(row.get("MetadataStatus", "")),
            markdown_projection_scalar(row.get("SeverityFinding", "")),
            markdown_projection_scalar(row.get("DispositionEvidence", "")),
        ])
    return rows


def validate_markdown_csv_projection(
    path: Path,
    expected_headers: list[str],
    expected_rows: list[list[str]],
    label: str,
    errors: list[str],
) -> None:
    """Require exact schema, deterministic order, and field-wise CSV equality."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"{path.name}: cannot read Markdown master: {exc}")
        return
    rows = parse_markdown_table_by_exact_headers(
        text,
        expected_headers,
        path.name,
        errors,
        case_sensitive=True,
    )
    if rows is None:
        return
    if len(rows) != len(expected_rows):
        errors.append(
            f"{path.name}: deterministic {label} projection row count "
            f"{len(rows)} != authoritative CSV row count {len(expected_rows)}"
        )
    for position, (actual, expected) in enumerate(
        zip(rows, expected_rows), start=1
    ):
        if len(actual) != len(expected_headers):
            continue
        expected_id = expected[0] if expected else f"row {position}"
        if actual[0] != expected_id:
            errors.append(
                f"{path.name}: deterministic row order mismatch at row "
                f"{position}; expected {expected_id!r}, got {actual[0]!r}"
            )
        for column, header in enumerate(expected_headers):
            if column >= len(expected) or actual[column] == expected[column]:
                continue
            errors.append(
                f"{path.name}: Markdown/CSV value mismatch for "
                f"{expected_id}/{header}: expected {expected[column]!r}, "
                f"got {actual[column]!r}"
            )


def read_valid_png_dimensions(path: Path, errors: list[str]) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        errors.append(f"{path.name}: cannot read render PNG: {exc}")
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        errors.append(f"{path.name}: invalid PNG signature")
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_idat = False
    saw_iend = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            errors.append(f"{path.name}: truncated PNG chunk")
            return None
        payload = data[offset + 8:offset + 8 + length]
        declared_crc = struct.unpack(">I", data[offset + 8 + length:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if declared_crc != actual_crc:
            errors.append(f"{path.name}: PNG chunk CRC mismatch")
            return None
        if chunk_type == b"IHDR":
            if length != 13 or dimensions is not None:
                errors.append(f"{path.name}: invalid PNG IHDR")
                return None
            dimensions = struct.unpack(">II", payload[:8])
        elif chunk_type == b"IDAT":
            saw_idat = True
        elif chunk_type == b"IEND":
            saw_iend = True
            break
        offset = chunk_end
    if dimensions is None or not saw_idat or not saw_iend:
        errors.append(f"{path.name}: incomplete PNG render")
        return None
    try:
        from PIL import Image
    except ImportError:
        errors.append(
            "validator dependency missing: install Pillow or use the bundled "
            "workspace Python runtime"
        )
        return None
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            decoded_dimensions = image.size
    except Exception as exc:  # Pillow exposes several decoder exception types
        errors.append(f"{path.name}: PNG pixels cannot be decoded: {exc}")
        return None
    if decoded_dimensions != dimensions:
        errors.append(
            f"{path.name}: decoded PNG dimensions {decoded_dimensions} do not "
            f"match IHDR {dimensions}"
        )
        return None
    return dimensions


def is_placeholder(value: str) -> bool:
    return value.strip().casefold() in PLACEHOLDERS


def valid_candidate_classification_evidence(value: str) -> bool:
    """Accept only a concrete contextual reason, identically in every gate."""

    stripped = value.strip()
    return (
        len(stripped) >= 12
        and not is_placeholder(stripped)
        and stripped.casefold()
        not in {"citation", "non-citation", "checked", "verified"}
    )


def require_value(
    row: dict[str, str],
    field: str,
    location: str,
    errors: list[str],
    *,
    allow_blank: bool = False,
) -> None:
    value = row.get(field, "").strip()
    if not value and not allow_blank:
        errors.append(f"{location}: blank mandatory field {field}")
    elif (
        value
        and is_placeholder(value)
        and not (field == "PrintedPage" and value == "X")
    ):
        errors.append(f"{location}: placeholder in mandatory field {field}: {value!r}")


def read_csv(
    path: Path,
    expected_columns: list[str],
    errors: list[str],
    *,
    require_rows: bool,
) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"missing CSV: {path.name}")
        return []
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if headers != expected_columns:
                errors.append(
                    f"{path.name}: schema mismatch; expected {expected_columns}, got {headers}"
                )
            rows: list[dict[str, str]] = []
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    errors.append(
                        f"{path.name}:{line_number}: values exceed declared header"
                    )
                # Preserve cell bytes apart from the cross-platform newline
                # convention.  Callers explicitly strip only fields whose
                # contract is semantic rather than an exact PDF/ledger anchor;
                # globally stripping here would conceal drift in Marker,
                # AdjacentPDFText, RenderedEntry, IDs, and signed projections.
                normalized = {
                    key: (row.get(key) or "")
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                    for key in expected_columns
                }
                rows.append(normalized)
            if require_rows and not rows:
                errors.append(f"{path.name}: header-only or empty ledger is not complete")
            return rows
    except (OSError, csv.Error) as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
        return []


def index_unique(
    rows: list[dict[str, str]],
    field: str,
    filename: str,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for line, row in enumerate(rows, start=2):
        value = row.get(field, "")
        require_value(row, field, f"{filename}:{line}", errors)
        if value:
            if value in result:
                errors.append(f"{filename}: duplicate {field} {value!r}")
            else:
                result[value] = row
    return result


def compare_sets(
    label: str, expected: set[str], actual: set[str], errors: list[str]
) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"{label}: missing IDs {missing}")
    if extra:
        errors.append(f"{label}: extra IDs {extra}")


def validate_pdf_hash(
    rows: list[dict[str, str]],
    filename: str,
    expected: str,
    errors: list[str],
) -> None:
    for line, row in enumerate(rows, start=2):
        value = row.get("PDFSHA256", "").upper()
        if not HEX64_RE.fullmatch(value):
            errors.append(f"{filename}:{line}: PDFSHA256 is not 64 hexadecimal characters")
        elif value != expected:
            errors.append(
                f"{filename}:{line}: PDFSHA256 {value} does not equal frozen PDF {expected}"
            )


def extract_hashes_from_labeled_line(text: str, label_pattern: str) -> list[str]:
    for line in text.splitlines():
        if re.search(label_pattern, line, flags=re.IGNORECASE):
            return [match.upper() for match in HEX64_FIND_RE.findall(line)]
    return []


def helper_inputs_for_recipient(root: Path | None, actor_id: str) -> list[str]:
    """Project hash-bound helper provenance/output paths for one recipient actor."""

    if root is None:
        return []
    helpers = root / "helpers"
    if is_link_or_reparse(helpers) or not helpers.is_dir():
        return []
    projected: list[str] = []
    for provenance_path in sorted(helpers.glob("H??-provenance.json")):
        if is_link_or_reparse(provenance_path) or not provenance_path.is_file():
            continue
        try:
            data = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        recipients = data.get("recipient_stages")
        if not isinstance(recipients, list) or actor_id not in recipients:
            continue
        projected.append(f"helpers/{provenance_path.name}")
        outputs = data.get("outputs")
        if not isinstance(outputs, list):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            filename = output.get("file")
            if isinstance(filename, str) and is_neutral_portable_basename(filename):
                projected.append(f"helpers/{filename}")
    return projected


def canonical_stage_opened_inputs(
    process: dict[str, Any], reviewer_count: int, actor_id: str,
    root: Path | None = None,
) -> list[str]:
    """Return the only ordered local rule/input paths a substantive actor may open."""

    governing = [
        str(item.get("neutral_file"))
        for item in process.get("governing_local_files", [])
        if isinstance(item, dict) and item.get("neutral_file")
    ]
    frozen = str(process.get("frozen_pdf_file", ""))
    degree_level = process.get("degree_level")
    reviewer_validator_rules: list[str] = []
    if re.fullmatch(r"R\d+", actor_id):
        if degree_level == "masters" and actor_id == "R3":
            reviewer_validator_rules = MASTER_R3_VALIDATOR_RULE_INPUTS
        elif degree_level == "doctorate" and actor_id == "R4":
            reviewer_validator_rules = R4_VALIDATOR_RULE_INPUTS
        elif degree_level == "doctorate" and actor_id == "R5":
            reviewer_validator_rules = R5_VALIDATOR_RULE_INPUTS
        else:
            reviewer_validator_rules = ORDINARY_REVIEWER_VALIDATOR_RULE_INPUTS
    p_validator_rules = P_VALIDATOR_RULE_INPUTS if actor_id == "P" else []
    chair_validator_rules = CHAIR_VALIDATOR_RULE_INPUTS if actor_id == "C" else []
    base_rules = [
        "00-process-parameters.json", "SKILL.md", *SKILL_REFERENCE_FILES,
        *p_validator_rules, *reviewer_validator_rules,
        *chair_validator_rules, *governing, frozen,
    ]
    packet = [
        "00-manifest.md", "01-policy-basis.md", "00-page-inventory.csv",
        "00-bibliography-inventory.csv", "00-citation-candidate-ledger.csv",
        "00-unmatched-bracket-ledger.csv", "00-citation-inventory.csv",
    ]
    if actor_id == "P":
        # Stage P is the packet builder and has no upstream helper inputs.  Its
        # scoped validator must not probe or enumerate the helpers directory.
        return base_rules
    # Stage S is never a helper recipient: it receives only the frozen
    # current-round summary sources.  Avoid even probing ``helpers/`` while
    # deriving its receipt.
    helper_inputs = (
        [] if actor_id == "S" else helper_inputs_for_recipient(root, actor_id)
    )
    if re.fullmatch(r"R\d+", actor_id):
        return [*base_rules, *packet, *helper_inputs]
    if actor_id == "AI":
        return [
            "00-process-parameters.json", "SKILL.md",
            "clean-room-orchestration.md", "report-template.md",
            "ai-style-audit.md", *AI_VALIDATOR_RULE_INPUTS,
            frozen, "00-manifest.md",
            "00-page-inventory.csv", *helper_inputs,
        ]
    if actor_id == "C":
        return [
            *base_rules, *packet,
            "02-page-layout-ledger.md", "02-page-layout-ledger.csv",
            "03-bibliography-audit-ledger.md",
            "03-bibliography-audit-ledger.csv",
            "04-citation-claim-audit-ledger.md",
            "04-citation-claim-audit-ledger.csv",
            *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
            "05-ai-style-assessment.md", *helper_inputs,
        ]
    if actor_id == "S":
        return [
            "00-process-parameters.json", "SKILL.md",
            "clean-room-orchestration.md", "report-template.md",
            *SUMMARY_VALIDATOR_RULE_INPUTS,
            *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
            "05-ai-style-assessment.md", "90-chair-synthesis.md",
            "91-revision-ledger.md", "91-revision-ledger.csv",
            "91-ai-actionable-ledger.csv",
            "92-new-evidence-or-experiments.md",
            "92-new-evidence-or-experiments.csv", *helper_inputs,
        ]
    return []


def parse_receipt_list(receipt: str, key: str) -> list[str] | None:
    match = re.search(rf"(?i)(?:^|;)[ \t]*{re.escape(key)}=\[([^\]]*)\]", receipt)
    if match is None:
        return None
    return [
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", match.group(1))
        if token.strip()
    ]


def parse_closed_access_receipt(
    receipt: str, filename: str, errors: list[str]
) -> dict[str, list[str]] | None:
    """Parse the one canonical receipt grammar with no duplicate/extra clauses."""

    match = re.fullmatch(
        r"received=\[([^\]]+)\]; opened=\[([^\]]+)\]; "
        r"public_endpoints=\[([^\]]+)\]; "
        r"no unlisted substantive assertion was received; "
        r"no prohibited context/artifact was used; "
        r"neighboring paths were not enumerated",
        receipt,
    )
    if match is None:
        errors.append(
            f"{filename}: input receipt must use the exact closed grammar with "
            "one received, one opened, one public_endpoints, and only the three "
            "canonical clean-access confirmations"
        )
        return None

    def split(value: str) -> list[str]:
        return [
            token.strip().strip("`\"")
            for token in re.split(r"\s*;\s*", value)
            if token.strip()
        ]

    return {
        "received": split(match.group(1)),
        "opened": split(match.group(2)),
        "public_endpoints": split(match.group(3)),
    }


def extract_closed_access_receipt(
    text: str, filename: str, errors: list[str],
) -> dict[str, list[str]] | None:
    """Extract the one visible canonical access receipt from a Markdown artifact."""

    visible = markdown_visible_text(text)
    matches = list(re.finditer(
        r"(?im)^[ ]{0,3}-[ \t]+(?:[A-Za-z-]+[ \t]+)?"
        r"Input-receipt/access declaration[ \t]*:[ \t]*(.*)$",
        visible,
    ))
    if len(matches) != 1:
        errors.append(
            f"{filename}: input receipt field must occur exactly once for "
            "cross-artifact reconciliation"
        )
        return None
    return parse_closed_access_receipt(matches[0].group(1), filename, errors)


def validate_identical_actor_access_receipts(
    paths: Iterable[Path],
    expected_opened: list[str],
    allowed_public_sequence: Iterable[str],
    actor_id: str,
    errors: list[str],
) -> None:
    """Require one actor's signed artifacts to share one canonical receipt."""

    allowed_public = ordered_unique(
        value.strip()
        for value in allowed_public_sequence
        if isinstance(value, str) and value.strip()
    )
    allowed_public_set = set(allowed_public)
    baseline: dict[str, list[str]] | None = None
    baseline_filename = ""
    for path in paths:
        try:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(
                f"{path.name}: cannot read actor receipt for reconciliation: {exc}"
            )
            continue
        parsed = extract_closed_access_receipt(raw_text, path.name, errors)
        if parsed is None:
            continue
        if parsed.get("received") != ["operational prompt"]:
            errors.append(
                f"{path.name}: shared {actor_id} receipt received list must be "
                "exactly [operational prompt]"
            )
        if parsed.get("opened") != expected_opened:
            errors.append(
                f"{path.name}: shared {actor_id} receipt opened list must equal "
                "the canonical actor allowlist"
            )
        public_items = parsed.get("public_endpoints", [])
        normalized_public = (
            [] if public_items == ["none"]
            else [value for value in public_items if value.casefold() != "none"]
        )
        unknown = sorted(set(normalized_public) - allowed_public_set)
        canonical_subset = [
            value for value in allowed_public if value in set(normalized_public)
        ]
        canonical_public = canonical_subset or ["none"]
        if unknown or public_items != canonical_public:
            errors.append(
                f"{path.name}: shared {actor_id} public_endpoints must be a "
                "duplicate-free canonical-order subset of the actor endpoint "
                f"allowlist; unknown={unknown}"
            )
        if baseline is None:
            baseline = parsed
            baseline_filename = path.name
        elif parsed != baseline:
            errors.append(
                f"{path.name}: {actor_id} access receipt must exactly match "
                f"{baseline_filename} across received/opened/public_endpoints"
            )


def validate_declarations(
    path: Path,
    expected_pdf_hash: str,
    errors: list[str],
    *,
    process: dict[str, Any] | None = None,
    actor_id: str | None = None,
    reviewer_count: int = 0,
    allowed_public_endpoints: set[str] | None = None,
    required_public_endpoints: set[str] | None = None,
) -> str:
    if not path.is_file():
        return ""
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    hidden_constructs: list[str] = []
    if "<!--" in raw_text:
        hidden_constructs.append("HTML comment")
    if re.search(r"(?m)^[ ]{0,3}(?:`{3,}|~{3,})", raw_text):
        hidden_constructs.append("fenced code block")
    if re.search(r"(?m)^(?: {4,}|\t)\S", raw_text):
        hidden_constructs.append("indented code block")
    if re.search(
        r"(?im)^[ ]{0,3}</?[A-Za-z][A-Za-z0-9-]*"
        r"(?:[ \t]+[^>\r\n]*)?>",
        raw_text,
    ):
        hidden_constructs.append("raw HTML block")
    if hidden_constructs:
        errors.append(
            f"{path.name}: validated review Markdown cannot contain non-rendered "
            f"or raw block structures: {sorted(set(hidden_constructs))}"
        )
    text = markdown_visible_text(raw_text)
    lower = text.casefold()
    if re.search(
        r"(?m)^[ ]{0,3}[^#|\s][^\r\n]*\r?\n[ ]{0,3}[=-]{3,}[ \t]*$",
        text,
    ):
        errors.append(
            f"{path.name}: Setext headings are not allowed in the validated Markdown dialect"
        )
    required_fresh_boundary = (
        "no inherited user/thread/task turns beyond system/developer "
        "instructions and the exact operational prompt"
    )
    fresh_matches = list(re.finditer(
        r"(?im)^[ ]{0,3}-[ \t]+(?:[A-Za-z-]+[ \t]+)?"
        r"Fresh-context declaration[ \t]*:[ \t]*(.*)$",
        text,
    ))
    if len(fresh_matches) != 1:
        errors.append(f"{path.name}: fresh-context declaration field must occur exactly once")
    elif fresh_matches[0].group(1).strip() != required_fresh_boundary:
        errors.append(
            f"{path.name}: fresh-context declaration must exactly equal the "
            "canonical no-inherited-context sentence"
        )
    if "input-receipt/access declaration" not in lower:
        errors.append(f"{path.name}: missing input-receipt/access declaration")
    if "received" not in lower or "opened" not in lower:
        errors.append(f"{path.name}: input receipt does not name received/opened inputs")
    for description, alternatives in (
        ("no unlisted substantive assertion", (
            "no unlisted substantive assertion",
            "no unlisted substantive assertions",
        )),
        ("no prohibited context/artifact", (
            "no prohibited context/artifact",
            "no prohibited context or artifact",
            "no prohibited context and no prohibited artifact",
        )),
        ("no neighboring-path enumeration", (
            "neighboring paths were not enumerated",
            "neighboring paths not enumerated",
            "no neighboring-path enumeration",
            "no neighboring path enumeration",
        )),
    ):
        if not any(value in lower for value in alternatives):
            errors.append(
                f"{path.name}: input receipt does not state {description}"
            )
    prompt_hash_value = labeled_value(text, "Operational prompt SHA-256")
    if prompt_hash_value is None or not HEX64_RE.fullmatch(prompt_hash_value):
        errors.append(
            f"{path.name}: expected one unique Operational prompt SHA-256 field "
            "containing exactly 64 hexadecimal characters"
        )
    receipt_matches = list(re.finditer(
        r"(?im)^[ ]{0,3}-[ \t]+(?:[A-Za-z-]+[ \t]+)?"
        r"Input-receipt/access declaration[ \t]*:[ \t]*(.*)$",
        text,
    ))
    receipt = ""
    parsed_receipt: dict[str, list[str]] | None = None
    if len(receipt_matches) != 1:
        errors.append(f"{path.name}: input receipt field must occur exactly once")
    else:
        receipt = receipt_matches[0].group(1)
        parsed_receipt = parse_closed_access_receipt(receipt, path.name, errors)
        receipt_lower = receipt.casefold()
        for description, alternatives in (
            ("no unlisted substantive assertion", (
                "no unlisted substantive assertion",
                "no unlisted substantive assertions",
            )),
            ("no prohibited context/artifact", (
                "no prohibited context/artifact",
                "no prohibited context or artifact",
                "no prohibited context and no prohibited artifact",
            )),
            ("no neighboring-path enumeration", (
                "neighboring paths were not enumerated",
                "neighboring paths not enumerated",
                "no neighboring-path enumeration",
                "no neighboring path enumeration",
            )),
        ):
            if not any(value in receipt_lower for value in alternatives):
                errors.append(
                    f"{path.name}: input receipt field itself does not state {description}"
                )
    if process is not None and actor_id is not None:
        actor_value = labeled_value(text, "Actor ID")
        round_value = labeled_value(text, "Review round ID")
        retry_value = labeled_value(text, "Review retry ID")
        if actor_value != actor_id:
            errors.append(
                f"{path.name}: Actor ID must exactly equal {actor_id!r}"
            )
        if round_value != str(process.get("round_id", "")):
            errors.append(
                f"{path.name}: Review round ID does not equal the process envelope"
            )
        if retry_value != str(process.get("retry_id", "")):
            errors.append(
                f"{path.name}: Review retry ID does not equal the process envelope"
            )
        prompt_map = process.get("actor_prompt_sha256", {})
        expected_prompt_hash = (
            str(prompt_map.get(actor_id, "")) if isinstance(prompt_map, dict) else ""
        )
        if prompt_hash_value is not None and prompt_hash_value.upper() != expected_prompt_hash.upper():
            errors.append(
                f"{path.name}: Operational prompt SHA-256 does not match the "
                f"process-bound {actor_id} prompt hash"
            )
        received_items = (
            parsed_receipt.get("received") if parsed_receipt is not None else None
        )
        if received_items != ["operational prompt"]:
            errors.append(
                f"{path.name}: received receipt must be exactly [operational prompt]"
            )
        expected_opened = canonical_stage_opened_inputs(
            process, reviewer_count, actor_id, path.parent
        )
        opened_items = (
            parsed_receipt.get("opened") if parsed_receipt is not None else None
        )
        if opened_items != expected_opened:
            errors.append(
                f"{path.name}: opened receipt must exactly equal the canonical "
                f"ordered {actor_id} allowlist"
            )
        public_items = (
            parsed_receipt.get("public_endpoints")
            if parsed_receipt is not None else None
        )
        if public_items is None:
            public_items = []
        if (
            any(value.casefold() == "none" for value in public_items)
            and public_items != ["none"]
        ):
            errors.append(
                f"{path.name}: public_endpoints=[none] must not be combined "
                "with endpoint tokens"
            )
        normalized_public = [
            value for value in public_items if value.casefold() != "none"
        ]
        allowed_public = allowed_public_endpoints or set()
        required_public = required_public_endpoints or set()
        if (
            len(normalized_public) != len(set(normalized_public))
            or any(value not in allowed_public for value in normalized_public)
            or (not normalized_public and public_items != ["none"])
        ):
            errors.append(
                f"{path.name}: public_endpoints must be [none] or a duplicate-free "
                f"subset of the current {actor_id} authoritative endpoint allowlist"
            )
        missing_required_public = sorted(required_public - set(normalized_public))
        if missing_required_public:
            errors.append(
                f"{path.name}: public_endpoints omits authoritative endpoint(s) "
                f"that this {actor_id} artifact says were opened: "
                f"{missing_required_public}"
            )
    pdf_hashes = extract_hashes_from_labeled_line(
        text, r"frozen\s+pdf\s+sha-?256.*start.*end"
    )
    if len(pdf_hashes) != 2:
        errors.append(
            f"{path.name}: expected two 64-hex frozen PDF hashes on the start/end declaration"
        )
    elif any(value != expected_pdf_hash for value in pdf_hashes):
        errors.append(f"{path.name}: start/end PDF hash does not match frozen PDF")
    return text


def expected_report_regime(process_status: str | None) -> str | None:
    mapping = {
        "skill-default": "skill-default",
        "verified-institutional": "institutional",
    }
    return mapping.get(str(process_status or "").casefold())


def process_governing_sources(process: dict[str, Any]) -> set[str]:
    """Return the exact frozen-envelope identifiers reports may cite as rules."""
    sources = {
        value.strip()
        for value in process.get("governing_rule_urls", [])
        if isinstance(value, str) and value.strip()
    }
    for item in process.get("governing_local_files", []):
        if not isinstance(item, dict):
            continue
        title = item.get("official_title")
        if isinstance(title, str) and title.strip():
            sources.add(title.strip())
    return sources


def validate_governing_source_projection(
    value: str,
    allowed_sources: set[str],
    filename: str,
    label: str,
    errors: list[str],
) -> None:
    """Require an exact semicolon-separated subset of the frozen rule envelope."""
    tokens = [token.strip() for token in value.split(";") if token.strip()]
    if not tokens or len(tokens) != len(set(tokens)):
        errors.append(
            f"{filename}: {label} must be a nonempty duplicate-free "
            "semicolon-separated governing-source list"
        )
        return
    unknown = [token for token in tokens if token not in allowed_sources]
    if unknown:
        errors.append(
            f"{filename}: {label} contains source(s) absent from the frozen "
            f"process envelope: {unknown}"
        )


def reviewer_verdict_projection(text: str) -> dict[str, str]:
    role = markdown_section_body_raw(text, "Role, scope, and independence") or ""
    verdict = markdown_section_body_raw(text, "Verdict") or ""
    regime = (labeled_value(verdict, "Decision regime") or "").casefold()
    official_category = labeled_value(verdict, "Official category") or ""
    official_recommendation = (
        labeled_value(verdict, "Official defense recommendation") or ""
    )
    governing_source = labeled_value(verdict, "Governing source") or ""
    academic_grade = labeled_value(verdict, "Academic grade") or ""
    default_recommendation = labeled_value(verdict, "Defense recommendation") or ""
    if regime == "institutional":
        category = official_category
        recommendation = official_recommendation
        regime_source = f"institutional / {governing_source}" if governing_source else ""
    elif regime == "skill-default":
        category = academic_grade
        recommendation = default_recommendation
        regime_source = "skill-default"
    else:
        category = recommendation = regime_source = ""
    assignment = labeled_value(role, "Persona assignment") or ""
    emphasis = labeled_value(role, "Persona emphasis") or ""
    return {
        "persona_assignment": assignment,
        "persona_emphasis": emphasis,
        "persona": f"{assignment} — {emphasis}" if assignment and emphasis else "",
        "regime": regime,
        "category": category,
        "recommendation": recommendation,
        "regime_source": regime_source,
        "confidence": labeled_value(verdict, "Confidence") or "",
        "rationale": (
            labeled_value(verdict, "One-paragraph whole-thesis rationale") or ""
        ),
        "official_category": official_category,
        "official_recommendation": official_recommendation,
        "governing_source": governing_source,
        "academic_grade": academic_grade,
        "default_recommendation": default_recommendation,
    }


def chair_verdict_projection(text: str) -> dict[str, str]:
    section = markdown_section_body_raw(text, "Overall risk and recommendation") or ""
    regime = (labeled_value(section, "Decision regime") or "").casefold()
    official_category = labeled_value(section, "Overall official category") or ""
    official_recommendation = (
        labeled_value(section, "Overall official defense recommendation") or ""
    )
    governing_source = labeled_value(section, "Overall governing source") or ""
    academic_grade = labeled_value(section, "Overall academic grade") or ""
    default_recommendation = (
        labeled_value(section, "Overall defense recommendation") or ""
    )
    if regime == "institutional":
        category = official_category
        recommendation = official_recommendation
        regime_source = f"institutional / {governing_source}" if governing_source else ""
    elif regime == "skill-default":
        category = academic_grade
        recommendation = default_recommendation
        regime_source = "skill-default"
    else:
        category = recommendation = regime_source = ""
    return {
        "regime": regime,
        "category": category,
        "recommendation": recommendation,
        "regime_source": regime_source,
        "confidence": labeled_value(section, "Confidence") or "",
        "rationale": labeled_value(section, "Whole-thesis rationale") or "",
        "official_category": official_category,
        "official_recommendation": official_recommendation,
        "governing_source": governing_source,
        "academic_grade": academic_grade,
        "default_recommendation": default_recommendation,
    }


def closed_list_residual_is_empty(value: str) -> bool:
    """Accept only punctuation/whitespace and explicit list connectors."""

    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"(?i)(?<![A-Za-z0-9])and(?![A-Za-z0-9])", "", normalized)
    normalized = re.sub(r"[\s,;、/|+&`()\[\]{}:.及和与]+", "", normalized)
    return not normalized


def parse_secondary_gate_set(value: str) -> tuple[str, ...] | None:
    """Parse an unordered, non-duplicated A--I set or the exact literal none."""

    stripped = value.strip()
    if stripped == "none":
        return ()
    token_re = re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:gates?[ \t]+)?([A-I])(?![A-Za-z0-9])"
    )
    matches = list(token_re.finditer(unicodedata.normalize("NFKC", stripped)))
    if not matches:
        return None
    residual = token_re.sub("", unicodedata.normalize("NFKC", stripped))
    if not closed_list_residual_is_empty(residual):
        return None
    gates = tuple(match.group(1).upper() for match in matches)
    if len(set(gates)) != len(gates):
        return None
    return gates


def parse_related_finding_ids(value: str) -> tuple[str, ...] | None:
    """Parse a closed list of reviewer/chair/question IDs or exact literal none."""

    stripped = value.strip()
    if stripped == "none":
        return ()
    token_re = re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:R\d+-(?:F|Q)\d{2,4}|C-F\d{2,4}|AI-F\d{2,4})"
        r"(?![A-Za-z0-9])"
    )
    matches = list(token_re.finditer(unicodedata.normalize("NFKC", stripped)))
    if not matches:
        return None
    residual = token_re.sub("", unicodedata.normalize("NFKC", stripped))
    if not closed_list_residual_is_empty(residual):
        return None
    identifiers = tuple(match.group(0) for match in matches)
    if len(set(identifiers)) != len(identifiers):
        return None
    return identifiers


def normalized_duty_value(value: str) -> str:
    """Normalize a complete duty value without substring-style matching."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", " ", normalized).strip()


def parse_reviewer_findings(
    text: str,
    reviewer_index: int,
    filename: str,
    physical_page_count: int,
    errors: list[str],
) -> dict[str, dict[str, str]]:
    section = markdown_section_body_raw(text, "Findings") or ""
    heading_re = re.compile(
        rf"(?im)^[ ]{{0,3}}###[ \t]+(R{reviewer_index}-F\d{{2,4}})"
        rf"[ \t]+(?:—|-)[ \t]+([^\r\n]*?)(?:[ \t]+#+)?[ \t]*$"
    )
    matches = list(heading_re.finditer(section))
    if not matches:
        normalized = normalize_extracted_text(section).casefold()
        if not re.search(r"(?:\bnone\b|\bno\b.*\bfinding|无.{0,8}(?:发现|问题))", normalized):
            errors.append(
                f"{filename}: Findings must contain complete R{reviewer_index}-Fxx "
                "blocks or an explicit none statement"
            )
        return {}
    findings: dict[str, dict[str, str]] = {}
    ordered_numbers: list[int] = []
    required_labels = (
        "Primary gate", "Secondary gates", "Scope", "Severity", "S0 subtype",
        "Remedy", "Required for the current defense conclusion", "Location",
        "Observation", "Why it matters", "Evidence", "Required action",
        "Verification", "Confidence",
    )
    for offset, match in enumerate(matches):
        finding_id = match.group(1)
        block_end = matches[offset + 1].start() if offset + 1 < len(matches) else len(section)
        block = section[match.end():block_end]
        if finding_id in findings:
            errors.append(f"{filename}: duplicate reviewer finding ID {finding_id}")
            continue
        fields = {label: labeled_value(block, label) for label in required_labels}
        for label, value in fields.items():
            if value is None or not value or is_placeholder(value):
                errors.append(
                    f"{filename}: {finding_id} missing or duplicated field {label!r}"
                )
        normalized_fields = {key: (value or "").strip() for key, value in fields.items()}
        findings[finding_id] = normalized_fields
        ordered_numbers.append(int(re.search(r"(\d+)$", finding_id).group(1)))
        primary_gate = normalized_fields["Primary gate"].upper()
        if primary_gate not in set("ABCDEFGHI"):
            errors.append(f"{filename}: {finding_id} has invalid Primary gate")
        if parse_secondary_gate_set(normalized_fields["Secondary gates"]) is None:
            errors.append(
                f"{filename}: {finding_id} Secondary gates must be exact none or "
                "a non-duplicated set drawn only from Gate A--I"
            )
        scope = normalized_fields["Scope"].casefold()
        if scope not in {"thesis-wide", "cross-chapter", "chapter", "local"}:
            errors.append(f"{filename}: {finding_id} has invalid Scope")
        severity = normalized_fields["Severity"].casefold()
        if severity not in {"s0", "s1", "s2", "s3", "s4"}:
            errors.append(f"{filename}: {finding_id} has invalid Severity")
        subtype = normalized_fields["S0 subtype"].casefold()
        if severity == "s0":
            if subtype not in {"procedural", "integrity/foundational"}:
                errors.append(f"{filename}: {finding_id} has invalid S0 subtype")
        elif subtype not in {"n/a", "na", "not applicable"}:
            errors.append(
                f"{filename}: {finding_id} non-S0 finding requires S0 subtype N/A"
            )
        if normalized_fields["Remedy"].casefold() not in {"w", "e", "n", "p"}:
            errors.append(f"{filename}: {finding_id} has invalid Remedy")
        required = normalized_fields["Required for the current defense conclusion"].casefold()
        if not re.match(r"^(?:yes|no)\b", required):
            errors.append(
                f"{filename}: {finding_id} defense-conclusion field must start yes/no"
            )
        finding_page = parse_canonical_physical_page_locator(
            normalized_fields["Location"]
        )
        if (
            finding_page is None
            or finding_page < 1
            or finding_page > physical_page_count
        ):
            errors.append(
                f"{filename}: {finding_id} Location requires an in-range "
                "canonical physical p.<n> anchor"
            )
        if normalized_fields["Confidence"].casefold() not in {
            "high", "medium", "low"
        }:
            errors.append(f"{filename}: {finding_id} has invalid Confidence")
        for label in (
            "Observation", "Why it matters", "Evidence", "Required action",
            "Verification",
        ):
            if len(normalized_fields[label]) < 12:
                errors.append(f"{filename}: {finding_id} field {label!r} is shell-only")
    if ordered_numbers != list(range(1, len(ordered_numbers) + 1)):
        errors.append(
            f"{filename}: reviewer finding IDs must be continuous from F01 in report order"
        )
    return findings


def parse_reviewer_questions(
    text: str,
    reviewer_index: int,
    filename: str,
    physical_page_count: int,
    errors: list[str],
) -> dict[str, list[str]]:
    """Parse the canonical question table; an empty table is an explicit none."""

    section = markdown_section_body_raw(text, "Questions, not findings") or ""
    headers = [
        "Question ID", "Exact PDF anchor", "Question", "Why unresolved",
        "Needed clarification/evidence",
    ]
    rows = parse_markdown_table_by_exact_headers(section, headers, filename, errors)
    if rows is None:
        return {}
    result: dict[str, list[str]] = {}
    numbers: list[int] = []
    pattern = re.compile(rf"^R{reviewer_index}-Q(\d{{2,4}})$")
    for row in rows:
        if len(row) != len(headers):
            continue
        match = pattern.fullmatch(row[0])
        if match is None:
            errors.append(f"{filename}: invalid reviewer question ID {row[0]!r}")
            continue
        if row[0] in result:
            errors.append(f"{filename}: duplicate reviewer question ID {row[0]}")
            continue
        numbers.append(int(match.group(1)))
        result[row[0]] = row
        page = parse_canonical_physical_page_locator(row[1])
        if page is None or page < 1 or page > physical_page_count:
            errors.append(
                f"{filename}: {row[0]} Exact PDF anchor requires an in-range "
                "canonical physical p.<n> anchor"
            )
        if any(len(cell) < 8 or is_placeholder(cell) for cell in row[2:]):
            errors.append(f"{filename}: {row[0]} question row is incomplete")
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"{filename}: reviewer question IDs must be continuous from Q01")
    return result


def parse_count_integer_vector(value: str) -> tuple[int, ...] | None:
    """Extract signed count tokens, rejecting uncovered numeric material."""

    token_re = re.compile(
        r"(?<![A-Za-z0-9.,])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)"
        r"(?![A-Za-z0-9.,])"
    )
    matches = list(token_re.finditer(value))
    residual = list(value)
    for match in matches:
        residual[match.start():match.end()] = " " * (match.end() - match.start())
    if re.search(r"\d", "".join(residual)):
        return None
    return tuple(
        int(match.group(0).replace(",", "")) for match in matches
    )


def validate_reviewer_report(
    path: Path,
    expected_pdf_hash: str,
    reviewer_index: int,
    process: dict[str, Any],
    reviewer_count: int,
    allowed_public_endpoints: set[str],
    required_public_endpoints: set[str],
    degree_level: str | None,
    decision_regime_status: str | None,
    allowed_governing_sources: set[str],
    owner_expected_vectors: dict[
        str, dict[str, tuple[int, ...] | tuple[str, ...]]
    ],
    physical_page_count: int,
    errors: list[str],
) -> None:
    text = validate_declarations(
        path, expected_pdf_hash, errors,
        process=process, actor_id=f"R{reviewer_index}",
        reviewer_count=reviewer_count,
        allowed_public_endpoints=allowed_public_endpoints,
        required_public_endpoints=required_public_endpoints,
    )
    if not text:
        return
    owns_citation = (
        degree_level == "doctorate" and reviewer_index == 4
    ) or (degree_level == "masters" and reviewer_index == 3)
    owns_page_and_bib = (
        degree_level == "doctorate" and reviewer_index == 5
    ) or (degree_level == "masters" and reviewer_index == 3)
    audit_owner = owns_citation or owns_page_and_bib
    require_unique_level2_headings(text, (
        "Role, scope, and independence",
        "Verdict",
        "What I inspected",
        "Whole-thesis synthesis",
        "Whole-thesis assessment",
        "Persona-weighted deep review",
        "Strongest contributions",
        "Findings",
        "Questions, not findings",
        "Coverage and limitations",
    ), path.name, errors)
    assessment_offsets = level2_heading_offsets(text, "Whole-thesis assessment")
    deep_review_offsets = level2_heading_offsets(text, "Persona-weighted deep review")
    if (
        len(assessment_offsets) == 1
        and len(deep_review_offsets) == 1
        and assessment_offsets[0] >= deep_review_offsets[0]
    ):
        errors.append(
            f"{path.name}: Whole-thesis assessment must precede "
            "Persona-weighted deep review"
        )
    coverage_offsets = level2_heading_offsets(text, "Coverage and limitations")
    owner_headings = (
        (["Full citation-claim audit"] if owns_citation else [])
        + ([
            "Full rendered-page audit",
            "Full bibliography-integrity audit",
        ] if owns_page_and_bib else [])
    )
    if len(coverage_offsets) == 1:
        for heading in owner_headings:
            offsets = level2_heading_offsets(text, heading)
            if len(offsets) == 1 and offsets[0] <= coverage_offsets[0]:
                errors.append(
                    f"{path.name}: conditional owner section {heading!r} must "
                    "follow the final required base section 'Coverage and limitations'"
                )
    role_section = markdown_section_body_raw(text, "Role, scope, and independence") or ""
    verdict_section = markdown_section_body_raw(text, "Verdict") or ""
    mandate = labeled_value(role_section, "Whole-thesis mandate")
    if mandate is None or not re.search(r"Gate\s+A\s*(?:--|–|—|-)\s*I", mandate, re.I):
        errors.append(f"{path.name}: Whole-thesis mandate must explicitly cover Gate A--I")
    for label in (
        "Actor ID", "Review round ID", "Review retry ID",
        "Separate exhaustive audit duties, if any", "Fresh-context declaration",
        "Independence declaration", "Operational prompt SHA-256",
        "Input-receipt/access declaration", "Frozen PDF SHA-256 at start and end",
    ):
        value = labeled_value(role_section, label)
        minimum_length = (
            1 if label in {"Actor ID", "Review round ID", "Review retry ID"}
            else 3
        )
        if value is None or len(value) < minimum_length or is_placeholder(value):
            errors.append(
                f"{path.name}: Role section missing or duplicating required field {label!r}"
            )
    duty_value = labeled_value(role_section, "Separate exhaustive audit duties, if any")
    if audit_owner and duty_value is not None and normalized_duty_value(duty_value) in {
        "none", "n a", "na", "not assigned", "no duty", "no duties", "无",
    }:
        errors.append(
            f"{path.name}: assigned audit owner cannot disclaim Separate exhaustive "
            "audit duties"
        )
    persona = labeled_value(role_section, "Persona emphasis")
    persona_assignment = labeled_value(role_section, "Persona assignment")
    technical = (
        "technical", "method", "methods", "experiment", "experiments",
        "algorithm", "algorithms", "representation", "representations",
        "loss", "losses", "training", "inference", "data split", "data splits",
        "baseline", "baselines", "metric", "metrics", "ablation", "ablations",
        "uncertainty", "user study", "user studies", "resource fairness",
        "reproducibility", "reproducible", "技术", "方法", "实验", "算法", "表示", "损失",
        "训练", "推理", "数据划分", "基线", "指标", "消融", "不确定性",
        "用户研究", "资源公平", "复现",
    )
    contribution = (
        "contribution", "contributions", "novelty", "positioning",
        "field positioning", "贡献", "创新", "定位",
    )
    architecture = (
        "thesis architecture", "chapter architecture", "thesis logic",
        "thesis narrative", "cross-chapter narrative", "abstract, introduction",
        "abstract/introduction", "scientific question", "scientific-question",
        "roadmap alignment", "chapter roadmap", "chapter progression",
        "cross-chapter", "chapter mapping", "shared infrastructure",
        "thesis synthesis", "论文架构", "论文主线", "论文逻辑", "全文主线",
        "摘要与绪论", "科学问题", "章节路线", "章节推进", "跨章",
        "章节映射", "共享基础", "全文综合",
    )
    evidence = (
        "evidence", "reproducibility", "reproducible", "integrity", "citation",
        "citations", "证据", "复现", "完整性", "引用",
    )
    standards = (
        "format", "formatting", "bibliography", "bibliographic", "layout",
        "page", "pages", "standard", "standards", "格式", "参考文献", "版面", "规范",
    )
    persona_requirements = {
        "doctorate": {
            1: (technical,), 2: (contribution,), 3: (architecture,),
            4: (evidence,), 5: (standards,),
        },
        "masters": {
            1: (technical,), 2: (contribution, architecture),
            3: (evidence, standards),
        },
    }
    expected_families = persona_requirements.get(
        str(degree_level or "").casefold(), {}
    ).get(reviewer_index, ())
    expected_assignment = PERSONA_ASSIGNMENTS.get(
        str(degree_level or ""), {}
    ).get(reviewer_index)
    if persona_assignment != expected_assignment:
        errors.append(
            f"{path.name}: Persona assignment must exactly equal "
            f"{expected_assignment!r}"
        )
    if (
        persona is None
        or len(persona) < 12
        or not expected_families
        or not all(
            any(contains_persona_signal(persona, term) for term in family)
            for family in expected_families
        )
    ):
        errors.append(
            f"{path.name}: Persona emphasis is missing or does not match the "
            f"distinct R{reviewer_index} emphasis"
        )
    projection = reviewer_verdict_projection(text)
    expected_regime = expected_report_regime(decision_regime_status)
    if projection["regime"] not in {"institutional", "skill-default"}:
        errors.append(f"{path.name}: Decision regime must be institutional or skill-default")
    elif expected_regime is None or projection["regime"] != expected_regime:
        errors.append(
            f"{path.name}: Decision regime does not match the frozen process envelope"
        )
    if projection["confidence"].casefold() not in {"high", "medium", "low"}:
        errors.append(f"{path.name}: Confidence must be high, medium, or low")
    rationale = projection["rationale"]
    if len(rationale) < 60 or is_placeholder(rationale):
        errors.append(f"{path.name}: whole-thesis rationale is absent or shell-only")
    for heading, minimum_length in (
        ("What I inspected", 30),
        ("Persona-weighted deep review", 40),
        ("Strongest contributions", 20),
        ("Coverage and limitations", 20),
    ):
        body = markdown_section_body(text, heading) or ""
        if len(body) < minimum_length or is_placeholder(body):
            errors.append(f"{path.name}: section {heading!r} is empty or shell-only")
    synthesis_section = markdown_section_body_raw(text, "Whole-thesis synthesis") or ""
    synthesis_labels = (
        "Central thesis problem and overall answer",
        "Degree-level contribution judgment",
        "Strongest claim--evidence chain",
        "Weakest claim--evidence chain",
        "Cross-chapter coherence",
        "Overall integrity and submission fitness",
        "Most consequential conclusion outside the persona emphasis, or evidence that no material concern was found there",
    )
    for label in synthesis_labels:
        value = labeled_value(synthesis_section, label)
        if value is None or len(value) < 20 or is_placeholder(value):
            errors.append(
                f"{path.name}: Whole-thesis synthesis field {label!r} is missing or shell-only"
            )
    assessment_section = markdown_section_body_raw(text, "Whole-thesis assessment") or ""
    findings = parse_reviewer_findings(
        text, reviewer_index, path.name, physical_page_count, errors
    )
    table_count = count_complete_markdown_pipe_tables(assessment_section)
    if table_count != 1:
        errors.append(
            f"{path.name}: Whole-thesis assessment must contain exactly one "
            f"complete Markdown table, found {table_count}"
        )
    parsed_gate_rows = parse_markdown_table_by_exact_headers(
        assessment_section,
        REVIEWER_ASSESSMENT_HEADERS,
        path.name,
        errors,
        case_sensitive=True,
    )
    gate_rows = parsed_gate_rows or []
    if parsed_gate_rows is not None and len(gate_rows) != 9:
        errors.append(
            f"{path.name}: Whole-thesis assessment must contain exactly nine "
            f"Gate A--I rows, found {len(gate_rows)}"
        )
    gate_labels: list[str | None] = []
    for cells in gate_rows:
        match = re.fullmatch(
            r"([A-I])(?:\s*(?:—|–|-)\s*\S.*)?",
            cells[0] if cells else "",
        )
        gate_labels.append(match.group(1) if match else None)
    gate_counts = Counter(label for label in gate_labels if label is not None)
    for gate in "ABCDEFGHI":
        if gate_counts[gate] != 1:
            errors.append(
                f"{path.name}: Gate {gate} must appear exactly once as a matrix row"
            )
    expected_gate_order = list("ABCDEFGHI")
    if gate_labels != expected_gate_order:
        errors.append(
            f"{path.name}: Whole-thesis assessment gate order must be exactly "
            f"A,B,C,D,E,F,G,H,I; got {gate_labels}"
        )
    for position, cells in enumerate(gate_rows):
        gate = gate_labels[position] or f"row {position + 1}"
        if len(cells) != len(REVIEWER_ASSESSMENT_HEADERS):
            errors.append(f"{path.name}: Gate {gate} row must have exactly six cells")
            continue
        if cells[1].casefold() not in {"baseline", "emphasized", "primary"}:
            errors.append(f"{path.name}: Gate {gate} has invalid review depth")
        if cells[2].casefold() not in {"adequate", "concern", "unverifiable", "n/a"}:
            errors.append(f"{path.name}: Gate {gate} has invalid disposition")
        gate_page = parse_canonical_physical_page_locator(cells[3])
        if (
            len(cells[3]) < 5
            or is_placeholder(cells[3])
            or gate_page is None
            or gate_page < 1
            or gate_page > physical_page_count
        ):
            errors.append(
                f"{path.name}: Gate {gate} evidence requires an in-range "
                "canonical physical p.<n> anchor"
            )
        related_finding_ids = parse_related_finding_ids(cells[4])
        if (
            related_finding_ids is None
            or any(identifier not in findings for identifier in related_finding_ids)
        ):
            errors.append(
                f"{path.name}: Gate {gate} Related finding IDs must be exact none "
                f"or a non-duplicated list of actual current R{reviewer_index} findings"
            )
        if not cells[5] or is_placeholder(cells[5]):
            errors.append(f"{path.name}: Gate {gate} lacks confidence/limitation")
    if projection["regime"] == "skill-default":
        grade = projection["academic_grade"].upper()
        if grade not in DEFAULT_RECOMMENDATIONS:
            errors.append(
                f"{path.name}: missing explicit academic grade; skill-default "
                "Academic grade must be A/B/C/D"
            )
        elif projection["default_recommendation"] != DEFAULT_RECOMMENDATIONS[grade]:
            errors.append(
                f"{path.name}: skill-default grade/recommendation pairing is invalid"
            )
        for label, value in (
            ("Official category", projection["official_category"]),
            ("Official defense recommendation", projection["official_recommendation"]),
            ("Governing source", projection["governing_source"]),
        ):
            if value.casefold() not in {"n/a", "na", "not applicable"}:
                errors.append(
                    f"{path.name}: {label} must be N/A under skill-default"
                )
    elif projection["regime"] == "institutional":
        for label, value in (
            ("Official category", projection["official_category"]),
            ("Official defense recommendation", projection["official_recommendation"]),
            ("Governing source", projection["governing_source"]),
        ):
            if not value or is_placeholder(value) or value.casefold() in {"n/a", "na"}:
                errors.append(f"{path.name}: missing institutional {label}")
        if projection["academic_grade"].casefold() not in {"n/a", "na"}:
            errors.append(f"{path.name}: Academic grade must be N/A under institutional")
        if projection["default_recommendation"].casefold() not in {"n/a", "na"}:
            errors.append(
                f"{path.name}: Defense recommendation must be N/A under institutional"
            )
        validate_governing_source_projection(
            projection["governing_source"], allowed_governing_sources,
            path.name, "Governing source", errors,
        )
    parse_reviewer_questions(
        text, reviewer_index, path.name, physical_page_count, errors
    )
    if projection["regime"] == "skill-default":
        required_grade = "A"
        severities = {
            fields.get("Severity", "").casefold() for fields in findings.values()
        }
        integrity_s0 = any(
            fields.get("Severity", "").casefold() == "s0"
            and fields.get("S0 subtype", "").casefold() == "integrity/foundational"
            for fields in findings.values()
        )
        procedural_s0 = any(
            fields.get("Severity", "").casefold() == "s0"
            and fields.get("S0 subtype", "").casefold() == "procedural"
            for fields in findings.values()
        )
        mandatory_n = any(
            fields.get("Remedy", "").casefold() == "n"
            and re.match(
                r"^yes\b",
                fields.get("Required for the current defense conclusion", "").casefold(),
            )
            for fields in findings.values()
        )
        if integrity_s0:
            required_grade = "D"
        elif procedural_s0 or "s1" in severities or mandatory_n:
            required_grade = "C"
        elif "s2" in severities:
            required_grade = "B"
        if projection["academic_grade"].upper() != required_grade:
            errors.append(
                f"{path.name}: skill-default grade is inconsistent with the "
                f"unresolved finding severity/remedy profile; expected {required_grade}"
            )
    def check_owner_section(
        heading: str,
        count_labels: tuple[str, ...],
        master_filename: str,
        text_labels: tuple[str, ...] = (),
        exact_text_values: dict[str, str] | None = None,
    ) -> None:
        require_unique_level2_headings(text, (heading,), path.name, errors)
        section = markdown_section_body_raw(text, heading) or ""
        for label in count_labels:
            value = labeled_value(section, label)
            expected_vector = owner_expected_vectors.get(heading, {}).get(label)
            observed_vector = parse_count_integer_vector(value or "")
            if value is None or expected_vector is None:
                errors.append(
                    f"{path.name}: missing concrete {heading!r} count {label!r}"
                )
            elif observed_vector is None:
                errors.append(
                    f"{path.name}: {heading!r} count {label!r} contains "
                    "malformed or identifier-bound numeric material"
                )
            elif observed_vector != expected_vector:
                errors.append(
                    f"{path.name}: {heading!r} count {label!r} is "
                    f"{observed_vector}, expected exact ledger-derived {expected_vector}"
                )
        for label in text_labels:
            value = labeled_value(section, label)
            if value is None or len(value) < 4 or is_placeholder(value):
                errors.append(
                    f"{path.name}: missing concrete {heading!r} field {label!r}"
                )
        for label, expected_value in (exact_text_values or {}).items():
            value = labeled_value(section, label)
            if value is not None and value != expected_value:
                errors.append(
                    f"{path.name}: {heading!r} field {label!r} must exactly equal "
                    f"{expected_value!r}"
                )
        master = labeled_value(section, "Machine-readable master")
        master_count_text = (master or "").replace(master_filename, "", 1)
        master_counts = parse_count_integer_vector(master_count_text)
        if (
            master is None or master_filename not in master
            or master_counts != (0, 0, 0)
        ):
            errors.append(
                f"{path.name}: {heading!r} must name {master_filename} and "
                "report duplicate/missing/extra counts"
            )

    citation_count_labels = (
        "Active citation occurrences", "Citation--source pairs",
        "Unique cited keys", "Semantically verified pairs",
        "Partial-support pairs", "Context-only pairs", "Mismatch pairs",
        "Inaccessible/unverifiable pairs", "Ledger rows and unchecked rows",
    )
    page_count_labels = (
        "Physical pages / unchecked pages",
        "Suspect-page signals / resolved / unresolved",
        "Actionable layout findings",
    )
    bibliography_count_labels = (
        "Bibliography entries rendered in the frozen PDF",
        "Bibliography master rows / unchecked rows",
        "Title fields verified / mismatched / unverifiable",
        "Ordered-author fields verified / mismatched / unverifiable",
        "Year fields verified / mismatched / unverifiable",
        "Venue fields verified / mismatched / unverifiable",
        "Publication/acceptance-status fields verified / mismatched / unverifiable",
        "Volume/issue fields verified / mismatched / legitimate N/A / unverifiable",
        "Page-range or article-number fields verified / mismatched / legitimate N/A / unverifiable",
        "DOI/arXiv/version/URL/access-date fields verified / mismatched / legitimate N/A / unverifiable",
        "ISBN/other-persistent-ID fields verified / mismatched / legitimate N/A / unverifiable",
        "Retraction/withdrawal/correction/superseding-status fields verified / mismatched / legitimate N/A / unverifiable",
        "Suspected fabricated/nonexistent entries and adjudication status",
        "Metadata/status verified entries",
    )
    if owns_citation:
        check_owner_section(
            "Full citation-claim audit",
            citation_count_labels,
            "04-citation-claim-audit-ledger.csv",
        )
    if owns_page_and_bib:
        expected_layout_finding_ids = set(
            owner_expected_vectors.get("Full rendered-page audit", {}).get(
                "Actionable layout finding IDs", ()
            )
        )
        unknown_layout_finding_ids = sorted(
            expected_layout_finding_ids - set(findings)
        )
        if unknown_layout_finding_ids:
            errors.append(
                f"{path.name}: page-ledger layout dispositions reference "
                f"unknown current-review finding IDs {unknown_layout_finding_ids}"
            )
        check_owner_section(
            "Full rendered-page audit",
            page_count_labels,
            "02-page-layout-ledger.csv",
            ("Neighbor-page verification status", "Source-forcing cause"),
            {"Source-forcing cause": "not verifiable from the PDF"},
        )
        check_owner_section(
            "Full bibliography-integrity audit",
            bibliography_count_labels,
            "03-bibliography-audit-ledger.csv",
        )


def labeled_value(text: str, label: str) -> str | None:
    matches = list(
        re.finditer(
            rf"(?im)^[ ]{{0,3}}-[ \t]+{re.escape(label)}[ \t]*:"
            rf"[ \t]*(.*?)[ \t]*$",
            markdown_visible_text(text),
        )
    )
    return matches[0].group(1).strip() if len(matches) == 1 else None


def level2_heading_offsets(
    text: str, heading: str, *, prefix: bool = False
) -> list[int]:
    visible = markdown_visible_text(text)
    suffix = r"(?:[ \t]+.*)?" if prefix else ""
    return [
        match.start()
        for match in re.finditer(
            rf"(?im)^[ ]{{0,3}}##[ \t]+{re.escape(heading)}{suffix}"
            rf"(?:[ \t]+#+)?[ \t]*$",
            visible,
        )
    ]


def level2_heading_count(text: str, heading: str, *, prefix: bool = False) -> int:
    return len(level2_heading_offsets(text, heading, prefix=prefix))


def require_unique_level2_headings(
    text: str, headings: Iterable[str], filename: str, errors: list[str]
) -> None:
    for heading in headings:
        count = level2_heading_count(text, heading)
        if count != 1:
            errors.append(
                f"{filename}: required section {heading!r} must occur exactly once; "
                f"observed {count}"
            )


def validate_chair_report(
    path: Path,
    expected_pdf_hash: str,
    process: dict[str, Any],
    bibliography_inventory: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    citation_inventory: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
    academic_ledger: list[dict[str, str]],
    reviewer_finding_ids: set[str],
    reviewer_question_ids: set[str],
    reviewer_count: int,
    decision_regime_status: str | None,
    allowed_governing_sources: set[str],
    errors: list[str],
) -> set[str]:
    allowed_chair_public = {
        *(
            value for value in process.get("governing_rule_urls", [])
            if isinstance(value, str)
        ),
        *bibliography_ledger_public_endpoints(bibliography_ledger),
        *citation_ledger_public_endpoints(citation_ledger),
    }
    text = validate_declarations(
        path, expected_pdf_hash, errors,
        process=process, actor_id="C", reviewer_count=reviewer_count,
        allowed_public_endpoints=allowed_chair_public,
        required_public_endpoints={
            value for value in process.get("governing_rule_urls", [])
            if isinstance(value, str)
        },
    )
    if not text:
        return set()
    direct_rejected_finding_ids: set[str] = set()
    require_unique_level2_headings(text, (
        "Clean-room boundary",
        "Overall risk and recommendation",
        "Reviewer coverage validation",
        "Independent verdicts",
        "Standalone AI-style judgment",
        "AI-style actionable findings",
        "Contributions that survived review",
        "Adjudicated findings",
        "Mandatory citation cross-ledger consistency gate",
        "Disagreements and chair decisions",
        "Thesis-level narrative and chapter logic",
        "Policy and blind-copy status",
        "Optional suggestions",
        "Review limitations",
    ), path.name, errors)
    boundary_section = markdown_section_body_raw(text, "Clean-room boundary") or ""
    boundary_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", boundary_section
    )
    expected_boundary_labels = [
        "Actor ID",
        "Review round ID",
        "Review retry ID",
        "Chair fresh-context declaration",
        "Exact current-round input allowlist",
        "Operational prompt SHA-256",
        "Chair input-receipt/access declaration",
        "Frozen PDF SHA-256 at start and end",
    ]
    if boundary_labels != expected_boundary_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in boundary_section.splitlines()
    ):
        errors.append(
            f"{path.name}: Clean-room boundary must contain only the eight "
            "canonical single-line fields in order"
        )
    expected_chair_allowlist = canonical_stage_opened_inputs(
        process, reviewer_count, "C", path.parent
    )
    allowlist_value = labeled_value(
        boundary_section, "Exact current-round input allowlist"
    ) or ""
    observed_chair_allowlist = [
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", allowlist_value)
        if token.strip()
    ]
    if observed_chair_allowlist != expected_chair_allowlist:
        errors.append(
            f"{path.name}: Exact current-round input allowlist must equal the "
            "canonical ordered Chair allowlist with each basename once"
        )
    chair_receipt = labeled_value(
        boundary_section, "Chair input-receipt/access declaration"
    ) or ""
    opened_match = re.search(r"(?i)(?:^|;)[ \t]*opened=\[([^\]]*)\]", chair_receipt)
    opened_items = [
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", opened_match.group(1) if opened_match else "")
        if token.strip()
    ]
    if opened_items != expected_chair_allowlist:
        errors.append(
            f"{path.name}: Chair opened receipt must exactly equal its canonical "
            "current-round allowlist"
        )
    public_match = re.search(
        r"(?i)(?:^|;)[ \t]*public_endpoints=\[([^\]]*)\]", chair_receipt
    )
    declared_public = [
        token.strip()
        for token in re.split(
            r"\s*;\s*", public_match.group(1) if public_match else ""
        )
        if token.strip() and token.strip().casefold() != "none"
    ]
    allowed_public = {
        *(
            value.strip() for value in process.get("governing_rule_urls", [])
            if isinstance(value, str) and value.strip()
        ),
        *bibliography_ledger_public_endpoints(bibliography_ledger),
        *citation_ledger_public_endpoints(citation_ledger),
    }
    if len(declared_public) != len(set(declared_public)) or any(
        value not in allowed_public for value in declared_public
    ):
        errors.append(
            f"{path.name}: Chair public_endpoints must be a duplicate-free subset "
            "of current policy/citation endpoints"
        )
    coverage_headers = [
        "Reviewer", "Gate A", "B", "C", "D", "E", "F", "G", "H", "I",
        "Whole-thesis rationale", "Audit duty complete", "Eligible for adjudication",
    ]
    coverage_section = (
        markdown_section_body_raw(text, "Reviewer coverage validation") or ""
    )
    coverage_rows = parse_markdown_table_by_exact_headers(
        coverage_section, coverage_headers, path.name, errors
    )
    expected_reviewers = {f"R{index}" for index in range(1, reviewer_count + 1)}
    if coverage_rows is not None:
        coverage_counts = Counter(
            row[0] for row in coverage_rows if len(row) == len(coverage_headers)
        )
        duplicate_coverage = sorted(
            actor for actor, count in coverage_counts.items() if count != 1
        )
        if duplicate_coverage:
            errors.append(
                f"{path.name}: duplicate reviewer-coverage actors {duplicate_coverage}"
            )
        coverage_by_actor = {
            row[0]: row for row in coverage_rows if len(row) == len(coverage_headers)
        }
        compare_sets(
            "chair reviewer-coverage actors",
            expected_reviewers,
            set(coverage_by_actor),
            errors,
        )
        for actor, row in coverage_by_actor.items():
            if any(not cell or is_placeholder(cell) for cell in row[1:]):
                errors.append(f"{path.name}: reviewer-coverage row {actor} is incomplete")
            report_path = path.parent / f"{actor}-comprehensive-review.md"
            if report_path.is_file():
                report_text = markdown_visible_text(
                    report_path.read_text(encoding="utf-8", errors="replace")
                )
                assessment = markdown_section_body_raw(
                    report_text, "Whole-thesis assessment"
                ) or ""
                source_dispositions: dict[str, str] = {}
                for source_line in assessment.splitlines():
                    cells = parse_markdown_pipe_row(source_line)
                    if cells is None or len(cells) != 6:
                        continue
                    gate_match = re.fullmatch(
                        r"([A-I])(?:[ \t]*[—-][ \t]*.*)?", cells[0]
                    )
                    if gate_match is not None:
                        source_dispositions[gate_match.group(1)] = cells[2]
                expected_gate_values = tuple(
                    source_dispositions.get(gate, "") for gate in "ABCDEFGHI"
                )
                if tuple(row[1:10]) != expected_gate_values:
                    errors.append(
                        f"{path.name}: reviewer-coverage Gate cells for {actor} do "
                        "not exactly project the frozen reviewer matrix"
                    )
                if row[10].casefold() != "complete":
                    errors.append(
                        f"{path.name}: reviewer-coverage rationale status for {actor} "
                        "must be complete"
                    )
                actor_number = int(actor[1:])
                owns_audit = (
                    reviewer_count == 5 and actor_number in {4, 5}
                ) or (reviewer_count == 3 and actor_number == 3)
                expected_audit = "yes" if owns_audit else "not assigned"
                if row[11].casefold() != expected_audit:
                    errors.append(
                        f"{path.name}: reviewer-coverage Audit duty complete for "
                        f"{actor} must be {expected_audit!r}"
                    )
            if row[-1].casefold() != "yes":
                errors.append(f"{path.name}: reviewer {actor} is not eligible for adjudication")
    verdict_headers = [
        "Reviewer", "Persona", "Category/grade", "Defense recommendation",
        "Decision regime/source", "Confidence", "Decisive reason",
    ]
    verdict_section = markdown_section_body_raw(text, "Independent verdicts") or ""
    verdict_rows = parse_markdown_table_by_exact_headers(
        verdict_section, verdict_headers, path.name, errors
    )
    if verdict_rows is not None:
        verdict_counts = Counter(
            row[0] for row in verdict_rows if len(row) == len(verdict_headers)
        )
        duplicate_verdicts = sorted(
            actor for actor, count in verdict_counts.items() if count != 1
        )
        if duplicate_verdicts:
            errors.append(
                f"{path.name}: duplicate independent-verdict actors {duplicate_verdicts}"
            )
        verdict_by_actor = {
            row[0]: row for row in verdict_rows if len(row) == len(verdict_headers)
        }
        compare_sets(
            "chair independent-verdict actors",
            expected_reviewers,
            set(verdict_by_actor),
            errors,
        )
        for index in range(1, reviewer_count + 1):
            actor = f"R{index}"
            report_path = path.parent / f"{actor}-comprehensive-review.md"
            if actor not in verdict_by_actor or not report_path.is_file():
                continue
            report = markdown_visible_text(
                report_path.read_text(encoding="utf-8", errors="replace")
            )
            row = verdict_by_actor[actor]
            projection = reviewer_verdict_projection(report)
            expected = (
                projection["persona"], projection["category"],
                projection["recommendation"], projection["regime_source"],
                projection["confidence"], projection["rationale"],
            )
            if not all(expected):
                errors.append(
                    f"{path.name}: frozen reviewer verdict {actor} is ambiguous or incomplete"
                )
            if tuple(row[1:7]) != expected:
                errors.append(
                    f"{path.name}: chair independent-verdict row {actor} does "
                    "not exactly preserve the frozen reviewer verdict"
                )
            if len(row[1]) < 8 or len(row[6]) < 60:
                errors.append(f"{path.name}: chair verdict row {actor} is shell-only")
        category_counts = Counter(
            row[2] for row in verdict_by_actor.values()
            if len(row) == len(verdict_headers)
        )
        expected_distribution = "; ".join(
            f"{category}={category_counts[category]}"
            for category in sorted(category_counts)
        )
        distribution = labeled_value(verdict_section, "Category distribution")
        if distribution != expected_distribution:
            errors.append(
                f"{path.name}: Category distribution must equal "
                f"{expected_distribution!r}"
            )
        departure = labeled_value(
            verdict_section, "Modal/severe-minority departure explanation"
        )
        if departure is None or len(departure) < 30 or is_placeholder(departure):
            errors.append(
                f"{path.name}: missing modal/severe-minority departure explanation"
            )
    ai_section = markdown_section_body_raw(text, "Standalone AI-style judgment")
    if ai_section is not None:
        chair_signal = labeled_value(ai_section, "Signal")
        chair_ai_confidence = labeled_value(ai_section, "Confidence")
        ai_path = path.parent / "05-ai-style-assessment.md"
        if ai_path.is_file():
            ai_text = markdown_visible_text(
                ai_path.read_text(encoding="utf-8", errors="replace")
            )
            ai_judgment = markdown_section_body_raw(ai_text, "Overall judgment") or ""
            if chair_signal != (labeled_value(ai_judgment, "AI-style signal") or ""):
                errors.append(
                    f"{path.name}: standalone AI signal does not exactly preserve "
                    "the frozen AI assessment"
                )
            if chair_ai_confidence != (labeled_value(ai_judgment, "Confidence") or ""):
                errors.append(
                    f"{path.name}: standalone AI confidence does not exactly preserve "
                    "the frozen AI assessment"
                )
            ai_findings = parse_ai_findings(
                ai_text,
                ai_path.name,
                int(process.get("physical_page_count") or 0),
                [],
            )
            impact_counts = Counter(
                fields.get("Impact", "").casefold() for fields in ai_findings.values()
            )
            expected_ai_vector = (
                f"material={impact_counts['material']} ; "
                f"local={impact_counts['local']} ; "
                f"optional={impact_counts['optional']}"
            )
            observed_ai_vector = labeled_value(
                ai_section, "Material/local/optional findings"
            )
            if observed_ai_vector != expected_ai_vector:
                errors.append(
                    f"{path.name}: Material/local/optional findings must exactly "
                    f"equal {expected_ai_vector!r}"
                )
        separation = labeled_value(ai_section, "Separation statement")
        if separation is None or len(separation) < 12 or is_placeholder(separation):
            errors.append(f"{path.name}: standalone AI section missing 'Separation statement'")
    citation_gate_section = (
        markdown_section_body_raw(text, "Mandatory citation cross-ledger consistency gate")
        or ""
    )
    cross_headers = [
        "Rendered reference ID", "Displayed label", "Affected Pair IDs",
        "Citation-ledger identity/source projection",
        "Bibliography-ledger canonical identity projection",
        "Version/record agreement (`agree` / `disagree` / `not verifiable`)",
        "Conflict class (`none` / `local` / `substantive`)",
        "Chair finding ID(s)", "Resolution (`closed` / `open`)",
    ]
    cross_rows = parse_markdown_table_by_exact_headers(
        citation_gate_section, cross_headers, path.name, errors
    )
    cited_reference_order = list(dict.fromkeys(
        row["DisplayedReferenceID"] for row in citation_inventory
        if REFERENCE_ID_RE.fullmatch(row.get("DisplayedReferenceID", ""))
    ))
    cited_reference_set = set(cited_reference_order)
    bib_inventory_by_id = {
        row["ReferenceID"]: row for row in bibliography_inventory
        if row.get("ReferenceID")
    }
    citation_rows_by_ref: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in citation_ledger:
        citation_rows_by_ref[row.get("ReferenceID", "")].append(row)
    bib_rows_by_ref_field = {
        (row.get("ReferenceID", ""), row.get("Field", "")): row
        for row in bibliography_ledger
    }
    academic_by_chair_id = {
        row.get("ChairFindingID", ""): row for row in academic_ledger
        if row.get("ChairFindingID")
    }
    bib_identity_fields = (
        "title", "ordered_authors", "year", "venue", "publication_status",
        "doi", "arxiv_id", "arxiv_version", "url",
        "isbn_or_other_persistent_id", "existence",
    )
    derived_cross_counts = Counter()
    if cross_rows is not None:
        valid_rows = [row for row in cross_rows if len(row) == len(cross_headers)]
        expected_reference_order = [
            markdown_projection_scalar(reference_id)
            for reference_id in cited_reference_order
        ]
        observed_reference_order = [row[0] for row in valid_rows]
        if observed_reference_order != expected_reference_order:
            errors.append(
                f"{path.name}: citation cross-ledger row order must exactly "
                "follow the citation-inventory first-reference order"
            )
        reference_counts = Counter(row[0] for row in valid_rows)
        duplicates = sorted(
            reference_id for reference_id, count in reference_counts.items()
            if count != 1
        )
        if duplicates:
            errors.append(
                f"{path.name}: duplicate cross-ledger reference IDs {duplicates}"
            )
        compare_sets(
            "chair citation cross-ledger reference IDs",
            cited_reference_set,
            set(reference_counts),
            errors,
        )
        for row in valid_rows:
            reference_id = row[0]
            if not REFERENCE_ID_RE.fullmatch(reference_id):
                errors.append(
                    f"{path.name}: invalid cross-ledger ReferenceID {reference_id!r}"
                )
            inventory_row = bib_inventory_by_id.get(reference_id, {})
            expected_displayed_label = displayed_label_for_reference_id(
                reference_id, bib_inventory_by_id
            )
            if row[1] != markdown_projection_scalar(expected_displayed_label):
                errors.append(
                    f"{path.name}: {reference_id} Displayed label does not project "
                    "the rendered bibliography label or dangling citation marker"
                )
            source_rows = citation_rows_by_ref.get(reference_id, [])
            expected_pairs = markdown_projection_scalar(
                ", ".join(item.get("PairID", "") for item in source_rows)
            )
            if row[2] != expected_pairs:
                errors.append(
                    f"{path.name}: {reference_id} Affected Pair IDs do not exactly "
                    "project 04-citation-claim-audit-ledger.csv"
                )
            expected_citation_projection = markdown_projection_scalar(
                " ; ".join(
                    f"{item.get('PairID', '')}=>{item.get('PublicIdentifier', '')} @ "
                    f"{item.get('ContentSourceOpened', '') or 'N/A'}"
                    for item in source_rows
                )
            )
            if row[3] != expected_citation_projection:
                errors.append(
                    f"{path.name}: {reference_id} citation identity/source cell does "
                    "not exactly project the citation ledger"
                )
            missing_bibliography_entry = not inventory_row
            expected_bib_projection = markdown_projection_scalar(
                DANGLING_REFERENCE_SENTINEL
                if missing_bibliography_entry
                else " ; ".join(
                    f"{field}="
                    f"{bib_rows_by_ref_field.get((reference_id, field), {}).get('CanonicalValue', '')}"
                    for field in bib_identity_fields
                )
            )
            if row[4] != expected_bib_projection:
                errors.append(
                    f"{path.name}: {reference_id} bibliography identity cell does "
                    "not exactly project the bibliography ledger"
                )
            relevant_bib_rows = [
                bib_rows_by_ref_field.get((reference_id, field), {})
                for field in bib_identity_fields
            ]
            mechanically_disagrees = missing_bibliography_entry or any(
                item.get("Verdict", "").casefold() == "mismatch"
                for item in relevant_bib_rows
            ) or any(
                item.get("MetadataStatus", "").casefold() == "mismatch"
                for item in source_rows
            )
            mechanically_unverifiable = any(
                item.get("Verdict", "").casefold() == "unverifiable"
                for item in relevant_bib_rows
            ) or any(
                item.get("MetadataStatus", "").casefold() == "unverifiable"
                for item in source_rows
            )
            expected_agreement = (
                "disagree" if mechanically_disagrees else
                "not verifiable" if mechanically_unverifiable else "agree"
            )
            agreement = row[5].casefold()
            if agreement != expected_agreement:
                errors.append(
                    f"{path.name}: {reference_id} version/record agreement must be "
                    f"{expected_agreement!r} from the two ledgers"
                )
            conflict = row[6].casefold()
            if conflict not in {"none", "local", "substantive"}:
                errors.append(
                    f"{path.name}: invalid cross-ledger conflict class {row[6]!r}"
                )
            if expected_agreement == "disagree" and conflict == "none":
                errors.append(
                    f"{path.name}: {reference_id} ledger disagreement cannot use conflict none"
                )
            if missing_bibliography_entry and conflict != "substantive":
                errors.append(
                    f"{path.name}: dangling {reference_id} requires a substantive "
                    "cross-ledger conflict"
                )
            chair_ids = re.findall(r"C-F\d{2,4}", row[7])
            canonical_chair_ids = ", ".join(dict.fromkeys(chair_ids))
            if conflict == "none":
                if row[7].casefold() != "none" or row[8].casefold() != "closed":
                    errors.append(
                        f"{path.name}: {reference_id} conflict-none row requires "
                        "Chair finding ID(s)=none and Resolution=closed"
                    )
            else:
                if not chair_ids or row[7] != canonical_chair_ids:
                    errors.append(
                        f"{path.name}: {reference_id} conflict row requires a canonical "
                        "duplicate-free Chair finding ID list"
                    )
                unknown_chair_ids = sorted(set(chair_ids) - set(academic_by_chair_id))
                if unknown_chair_ids:
                    errors.append(
                        f"{path.name}: {reference_id} names unknown Chair finding IDs "
                        f"{unknown_chair_ids}"
                    )
                linked = [
                    academic_by_chair_id[value] for value in chair_ids
                    if value in academic_by_chair_id
                ]
                if conflict == "local" and any(
                    item.get("Severity", "").casefold() != "s3" for item in linked
                ):
                    errors.append(
                        f"{path.name}: {reference_id} local conflict must map only to S3"
                    )
                if conflict == "substantive" and any(
                    item.get("Severity", "").casefold() not in {"s0", "s1", "s2"}
                    for item in linked
                ):
                    errors.append(
                        f"{path.name}: {reference_id} substantive conflict requires S0-S2"
                    )
                expected_resolution = (
                    "open" if any(
                        item.get("Status", "").casefold() not in CLOSED_STATUSES
                        for item in linked
                    ) else "closed"
                )
                if row[8].casefold() != expected_resolution:
                    errors.append(
                        f"{path.name}: {reference_id} Resolution must equal linked "
                        f"chair-ledger status {expected_resolution!r}"
                    )
            derived_cross_counts["Identity-agreement count"] += agreement == "agree"
            derived_cross_counts["Version disagreements"] += agreement == "disagree"
            derived_cross_counts["Local conflicts"] += conflict == "local"
            derived_cross_counts["Substantive conflicts"] += conflict == "substantive"
            if conflict != "none":
                derived_cross_counts["Reclassified Pair IDs"] += len(source_rows)
            derived_cross_counts["Unresolved conflicts"] += (
                conflict != "none" and row[8].casefold() == "open"
            )
            if any(not cell or is_placeholder(cell) for cell in row[1:]):
                errors.append(
                    f"{path.name}: cross-ledger row {reference_id!r} is incomplete"
                )
    counts: dict[str, int] = {}
    for label in (
        "Unique cited rendered references joined",
        "Identity-agreement count",
        "Version disagreements",
        "Local conflicts",
        "Substantive conflicts",
        "Reclassified Pair IDs",
        "Unresolved conflicts",
    ):
        value = parse_count_label(citation_gate_section, label, path.name, errors)
        if value is not None:
            counts[label] = value
    joined = counts.get("Unique cited rendered references joined")
    if joined is not None and joined != len(cited_reference_set):
        errors.append(
            f"{path.name}: joined cited-reference count {joined} != "
            f"citation inventory unique-reference count {len(cited_reference_set)}"
        )
    for label in (
        "Identity-agreement count", "Version disagreements", "Local conflicts",
        "Substantive conflicts", "Reclassified Pair IDs", "Unresolved conflicts",
    ):
        if label in counts and counts[label] != derived_cross_counts[label]:
            errors.append(
                f"{path.name}: {label} {counts[label]} != row-derived "
                f"{derived_cross_counts[label]}"
            )
    gate = labeled_value(citation_gate_section, "Combined citation gate")
    if gate is None or gate.casefold() not in {"pass", "fail"}:
        errors.append(f"{path.name}: Combined citation gate must be pass or fail")
    elif gate.casefold() == "pass" and counts.get("Unresolved conflicts", 0) > 0:
        errors.append(
            f"{path.name}: Combined citation gate cannot pass with unresolved conflicts"
        )
    elif gate.casefold() == "fail" and counts.get("Unresolved conflicts", 0) == 0:
        errors.append(
            f"{path.name}: Combined citation gate must pass when no conflict remains open"
        )
    chair_projection = chair_verdict_projection(text)
    expected_regime = expected_report_regime(decision_regime_status)
    if chair_projection["regime"] not in {"institutional", "skill-default"}:
        errors.append(
            f"{path.name}: overall Decision regime must be institutional or skill-default"
        )
    elif expected_regime is None or chair_projection["regime"] != expected_regime:
        errors.append(
            f"{path.name}: overall Decision regime does not match the process envelope"
        )
    if chair_projection["confidence"].casefold() not in {"high", "medium", "low"}:
        errors.append(f"{path.name}: missing allowed chair confidence")
    chair_rationale = chair_projection["rationale"]
    if chair_rationale is None or len(chair_rationale) < 60:
        errors.append(f"{path.name}: chair whole-thesis rationale is absent or shell-only")
    if chair_projection["regime"] == "skill-default":
        grade = chair_projection["academic_grade"].upper()
        if grade not in DEFAULT_RECOMMENDATIONS:
            errors.append(f"{path.name}: overall skill-default grade must be A/B/C/D")
        elif chair_projection["default_recommendation"] != DEFAULT_RECOMMENDATIONS[grade]:
            errors.append(
                f"{path.name}: overall skill-default grade/recommendation pairing is invalid"
            )
        for label, value in (
            ("Overall official category", chair_projection["official_category"]),
            (
                "Overall official defense recommendation",
                chair_projection["official_recommendation"],
            ),
            ("Overall governing source", chair_projection["governing_source"]),
        ):
            if value.casefold() not in {"n/a", "na", "not applicable"}:
                errors.append(f"{path.name}: {label} must be N/A under skill-default")
    elif chair_projection["regime"] == "institutional":
        for label, value in (
            ("Overall official category", chair_projection["official_category"]),
            (
                "Overall official defense recommendation",
                chair_projection["official_recommendation"],
            ),
            ("Overall governing source", chair_projection["governing_source"]),
        ):
            if not value or is_placeholder(value) or value.casefold() in {"n/a", "na"}:
                errors.append(f"{path.name}: missing institutional {label}")
        if chair_projection["academic_grade"].casefold() not in {"n/a", "na"}:
            errors.append(
                f"{path.name}: Overall academic grade must be N/A under institutional"
            )
        if chair_projection["default_recommendation"].casefold() not in {"n/a", "na"}:
            errors.append(
                f"{path.name}: Overall defense recommendation must be N/A under institutional"
            )
        validate_governing_source_projection(
            chair_projection["governing_source"], allowed_governing_sources,
            path.name, "Overall governing source", errors,
        )
    for heading in ("Optional suggestions", "Review limitations"):
        body = markdown_section_body(text, heading)
        if body is None or not body:
            errors.append(f"{path.name}: missing or empty chair section {heading!r}")
    for heading, minimum_length in (
        ("Contributions that survived review", 20),
        ("Thesis-level narrative and chapter logic", 20),
        ("Policy and blind-copy status", 20),
    ):
        body = markdown_section_body(text, heading) or ""
        if len(body) < minimum_length or is_placeholder(body):
            errors.append(f"{path.name}: section {heading!r} is empty or shell-only")
    disagreements_section = markdown_section_body_raw(
        text, "Disagreements and chair decisions"
    ) or ""
    disagreement_headers = [
        "Decision ID", "Source item IDs", "Topic", "Positions",
        "Evidence checked", "Status", "Decision",
    ]
    disagreement_rows = parse_markdown_table_by_exact_headers(
        disagreements_section, disagreement_headers, path.name, errors
    )
    if disagreement_rows is not None:
        decision_numbers: list[int] = []
        source_counts: Counter[str] = Counter()
        for row in disagreement_rows:
            if len(row) != len(disagreement_headers) or any(
                len(cell) < 3 or is_placeholder(cell) for cell in row
            ):
                errors.append(f"{path.name}: disagreement row is incomplete")
                continue
            decision_match = re.fullmatch(r"D(\d{2,4})", row[0])
            if decision_match is None:
                errors.append(f"{path.name}: invalid disagreement Decision ID {row[0]!r}")
            else:
                decision_numbers.append(int(decision_match.group(1)))
            source_ids = re.findall(
                r"(?:R\d+-(?:F|Q)\d{2,4}|C-F\d{2,4})", row[1]
            )
            residue = re.sub(
                r"(?:R\d+-(?:F|Q)\d{2,4}|C-F\d{2,4})", "", row[1]
            )
            residue = re.sub(r"[\s,，;/|]+", "", residue)
            if not source_ids or residue:
                errors.append(
                    f"{path.name}: {row[0]} Source item IDs must contain only "
                    "canonical reviewer-finding, reviewer-question, or "
                    "chair-finding IDs"
                )
            source_counts.update(source_ids)
            status = row[5].casefold()
            if status not in {
                "resolved", "unresolved", "not verifiable", "rejected", "disputed",
            }:
                errors.append(f"{path.name}: {row[0]} has invalid disagreement Status")
            direct_finding_ids = [
                identifier for identifier in source_ids
                if re.fullmatch(r"R\d+-F\d{2,4}", identifier)
            ]
            if direct_finding_ids:
                if status != "rejected":
                    errors.append(
                        f"{path.name}: {row[0]} direct reviewer-finding sources "
                        "require Status=rejected"
                    )
                if len(direct_finding_ids) != len(source_ids):
                    errors.append(
                        f"{path.name}: {row[0]} direct reviewer-finding rejection "
                        "cannot mix Rn-Fxx with reviewer questions or Chair findings"
                    )
                if status == "rejected":
                    direct_rejected_finding_ids.update(direct_finding_ids)
        if decision_numbers != list(range(1, len(decision_numbers) + 1)):
            errors.append(f"{path.name}: disagreement Decision IDs must be continuous from D01")
        required_disagreement_ids = {
            row.get("ChairFindingID", "") for row in academic_ledger
            if row.get("EvidenceStatus", "").casefold() in {
                "not verifiable from submitted pdf", "disputed",
            }
        }
        required_sources = (
            required_disagreement_ids
            | reviewer_question_ids
            | direct_rejected_finding_ids
        )
        missing_disagreements = sorted(required_sources - set(source_counts))
        duplicate_disagreements = sorted(
            identifier for identifier, count in source_counts.items()
            if identifier in required_sources and count != 1
        )
        if missing_disagreements:
            errors.append(
                f"{path.name}: disagreements table omits chair dispositions "
                f"{missing_disagreements}"
            )
        if duplicate_disagreements:
            errors.append(
                f"{path.name}: disagreements table must disposition each required "
                f"source exactly once; repeated={duplicate_disagreements}"
            )
        unknown_question_sources = sorted(
            identifier for identifier in source_counts
            if re.fullmatch(r"R\d+-Q\d{2,4}", identifier)
            and identifier not in reviewer_question_ids
        )
        if unknown_question_sources:
            errors.append(
                f"{path.name}: disagreements table contains unknown reviewer questions "
                f"{unknown_question_sources}"
            )
        unknown_reviewer_finding_sources = sorted(
            identifier for identifier in source_counts
            if re.fullmatch(r"R\d+-F\d{2,4}", identifier)
            and identifier not in reviewer_finding_ids
        )
        if unknown_reviewer_finding_sources:
            errors.append(
                f"{path.name}: disagreements table contains unknown reviewer findings "
                f"{unknown_reviewer_finding_sources}"
            )
        known_chair_finding_ids = {
            row.get("ChairFindingID", "") for row in academic_ledger
        }
        unknown_chair_sources = sorted(
            identifier for identifier in source_counts
            if identifier.startswith("C-F")
            and identifier not in known_chair_finding_ids
        )
        if unknown_chair_sources:
            errors.append(
                f"{path.name}: disagreements table contains unknown chair findings "
                f"{unknown_chair_sources}"
            )
    return direct_rejected_finding_ids


def parse_count_label(
    text: str, label: str, filename: str, errors: list[str]
) -> int | None:
    value = labeled_value(text, label)
    if value is None or not re.fullmatch(r"\d+", value):
        errors.append(f"{filename}: reconciliation '{label}' must be a nonnegative integer")
        return None
    return int(value)


def parse_ai_findings(
    text: str, filename: str, physical_page_count: int, errors: list[str]
) -> dict[str, dict[str, str]]:
    section = markdown_section_body_raw(text, "Findings") or ""
    heading_re = re.compile(
        r"(?im)^[ ]{0,3}###[ \t]+(AI-F\d{2,4})[ \t]+(?:—|-)[ \t]+"
        r"([^\r\n]*?)(?:[ \t]+#+)?[ \t]*$"
    )
    matches = list(heading_re.finditer(section))
    if not matches:
        normalized = normalize_extracted_text(section).casefold()
        if not re.search(r"(?:\bnone\b|\bno\b.*\bfinding|无.{0,8}(?:发现|问题))", normalized):
            errors.append(
                f"{filename}: AI Findings must contain complete AI-Fxx blocks "
                "or an explicit none statement"
            )
        return {}
    required_labels = (
        "Impact", "Location", "Recurrent evidence", "Reader impact",
        "Minimum safe editing strategy", "Closure test",
    )
    findings: dict[str, dict[str, str]] = {}
    numbers: list[int] = []
    for offset, match in enumerate(matches):
        finding_id = match.group(1)
        block_end = matches[offset + 1].start() if offset + 1 < len(matches) else len(section)
        block = section[match.end():block_end]
        if finding_id in findings:
            errors.append(f"{filename}: duplicate AI finding ID {finding_id}")
            continue
        fields = {
            label: (labeled_value(block, label) or "") for label in required_labels
        }
        for label, value in fields.items():
            if not value or is_placeholder(value):
                errors.append(
                    f"{filename}: {finding_id} missing or duplicated field {label!r}"
                )
        findings[finding_id] = fields
        numbers.append(int(re.search(r"(\d+)$", finding_id).group(1)))
        if fields["Impact"].casefold() not in {"material", "local", "optional"}:
            errors.append(f"{filename}: {finding_id} has invalid Impact")
        finding_page = parse_physical_page_locator(fields["Location"])
        if (
            finding_page is None
            or finding_page < 1
            or finding_page > physical_page_count
        ):
            errors.append(f"{filename}: {finding_id} lacks a physical-PDF location")
        for label in (
            "Recurrent evidence", "Reader impact",
            "Minimum safe editing strategy", "Closure test",
        ):
            if len(fields[label]) < 12:
                errors.append(f"{filename}: {finding_id} field {label!r} is shell-only")
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"{filename}: AI finding IDs must be continuous from AI-F01")
    return findings


def validate_ai_report(
    path: Path,
    expected_pdf_hash: str,
    physical_page_count: int,
    process: dict[str, Any],
    reviewer_count: int,
    errors: list[str],
) -> None:
    text = validate_declarations(
        path, expected_pdf_hash, errors,
        process=process, actor_id="AI", reviewer_count=reviewer_count,
        allowed_public_endpoints=set(),
    )
    if not text:
        return
    if AI_REQUIRED_DISCLAIMER.casefold() not in text.casefold():
        errors.append(f"{path.name}: missing mandatory non-attribution disclaimer")
    require_unique_level2_headings(text, (
        "Boundary and independence",
        "Overall judgment",
        "Coverage and mechanical checks",
        "Signal-family summary and counter-evidence",
        "Findings",
        "Limitations",
        "Out-of-scope observations for chair verification",
    ), path.name, errors)
    boundary_section = markdown_section_body_raw(text, "Boundary and independence") or ""
    for label in (
        "Actor ID", "Review round ID", "Review retry ID",
        "Frozen artifact", "Reviewer-visible inputs", "Excluded material",
        "Fresh-context declaration", "Independence declaration",
        "Operational prompt SHA-256", "Input-receipt/access declaration",
        "Frozen PDF SHA-256 at start and end", "Required disclaimer",
    ):
        value = labeled_value(boundary_section, label)
        minimum_length = (
            1 if label in {"Actor ID", "Review round ID", "Review retry ID"}
            else 3
        )
        if value is None or len(value) < minimum_length or is_placeholder(value):
            errors.append(
                f"{path.name}: Boundary section missing or duplicating field {label!r}"
            )
    required_disclaimer = labeled_value(boundary_section, "Required disclaimer")
    if required_disclaimer != AI_REQUIRED_DISCLAIMER:
        errors.append(
            f"{path.name}: Required disclaimer must exactly equal the canonical "
            "non-attribution disclaimer"
        )
    forbidden_ai_labels = (
        "AI probability", "AI-generated probability", "Detector score",
        "Plagiarism probability", "Academic grade", "Defense recommendation",
        "Official category", "Official defense recommendation", "Decision regime",
        "Severity", "S0 subtype", "Remedy", "Misconduct determination",
        "Misconduct finding", "Authorship determination", "AI-use determination",
        "AI生成概率", "人工智能生成概率", "检测器得分", "检测分数",
        "学术等级", "学术评分", "答辩建议", "正式类别", "正式答辩建议",
        "决策规则", "严重程度", "S0子类型", "修复类型", "学术不端认定",
        "学术不端结论", "作者身份认定", "AI使用认定",
    )
    visible_text = markdown_visible_text(text)
    for label in forbidden_ai_labels:
        if re.search(
            rf"(?im)^[ ]{{0,3}}-[ \t]+{re.escape(label)}[ \t]*:",
            visible_text,
        ):
            errors.append(
                f"{path.name}: standalone AI-style report contains forbidden "
                f"academic/detector/misconduct field {label!r}"
            )
    bullet_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", visible_text
    )
    for raw_label in bullet_labels:
        if raw_label.strip() not in AI_ALLOWED_STRUCTURED_LABELS:
            errors.append(
                f"{path.name}: standalone AI-style report contains an "
                f"unrecognized structured bullet label {raw_label!r}; colon-labeled "
                "bullets are closed to the canonical report schema"
            )
    for raw_label in bullet_labels:
        compact = "".join(
            character
            for character in unicodedata.normalize("NFKC", raw_label).casefold()
            if character.isalnum()
        )
        ai_marker = any(token in compact for token in (
            "ai", "artificialintelligence", "人工智能", "机器生成", "模型生成",
        ))
        detector_marker = any(token in compact for token in (
            "detector", "detection", "检测器", "检测工具", "检测模型",
        ))
        probability_metric = any(token in compact for token in (
            "probability", "likelihood", "score", "estimate", "概率", "可能性",
            "得分", "评分", "估计", "置信率",
        ))
        generation_or_content_marker = any(token in compact for token in (
            "generated", "generation", "content", "生成", "内容",
        ))
        share_or_rate_metric = any(token in compact for token in (
            "percentage", "percent", "rate", "ratio", "share", "proportion",
            "百分比", "占比", "比例",
        ))
        detector_positive_metric = (
            detector_marker
            and any(token in compact for token in ("positive", "阳性"))
            and any(token in compact for token in (
                "percentage", "percent", "rate", "ratio", "share", "proportion",
                "百分比", "占比", "比例", "阳性率",
            ))
        )
        attribution_quantity = (
            probability_metric and (ai_marker or detector_marker)
        ) or (
            ai_marker and generation_or_content_marker and share_or_rate_metric
        ) or detector_positive_metric
        verdict_marker = any(token in compact for token in (
            "determination", "finding", "verdict", "conclusion",
            "认定", "结论", "判断", "判定",
        ))
        authorship_marker = "authorship" in compact or "作者身份" in compact
        ai_use_marker = any(token in compact for token in (
            "aiuse", "artificialintelligenceuse", "ai使用", "人工智能使用",
        ))
        academic_verdict = (
            ("academic" in compact and any(token in compact for token in ("grade", "rating")))
            or ("学术" in compact and any(token in compact for token in ("等级", "评分")))
            or ("defense" in compact and any(token in compact for token in ("recommendation", "verdict")))
            or ("答辩" in compact and any(token in compact for token in ("建议", "结论")))
        )
        misconduct_verdict = (
            ("misconduct" in compact and any(
                token in compact for token in ("determination", "finding", "verdict", "conclusion")
            ))
            or ("学术不端" in compact and any(token in compact for token in ("认定", "结论", "判断")))
            or (authorship_marker and verdict_marker)
            or (ai_use_marker and verdict_marker)
        )
        if (
            attribution_quantity
            or academic_verdict
            or misconduct_verdict
        ):
            errors.append(
                f"{path.name}: standalone AI-style report contains semantically "
                f"forbidden probability/detector/academic/misconduct label {raw_label!r}"
            )
    coverage_section = markdown_section_body_raw(text, "Coverage and mechanical checks") or ""
    inspected_pages = labeled_value(coverage_section, "Physical pages inspected")
    expected_page_coverage = f"{physical_page_count} / {physical_page_count}"
    if inspected_pages != expected_page_coverage:
        errors.append(
            f"{path.name}: Physical pages inspected must exactly equal "
            f"{expected_page_coverage!r}"
        )
    for label in (
        "Authored sections inspected", "Recurrent-pattern queries/statistics",
        "Corpus exclusions",
    ):
        value = labeled_value(coverage_section, label)
        if value is None or len(value) < 12 or is_placeholder(value):
            errors.append(f"{path.name}: missing concrete AI coverage field {label!r}")
    for heading, minimum_length in (
        ("Signal-family summary and counter-evidence", 40),
        ("Limitations", 20),
        ("Out-of-scope observations for chair verification", 3),
    ):
        body = markdown_section_body(text, heading) or ""
        if len(body) < minimum_length or is_placeholder(body):
            errors.append(f"{path.name}: section {heading!r} is empty or shell-only")
    judgment_section = markdown_section_body_raw(text, "Overall judgment") or ""
    signal = labeled_value(judgment_section, "AI-style signal")
    if signal is None or signal.casefold() not in {
        "low", "moderate", "high", "indeterminate"
    }:
        errors.append(f"{path.name}: missing allowed AI-style signal")
    confidence = labeled_value(judgment_section, "Confidence")
    rationale = labeled_value(judgment_section, "Rationale")
    if confidence is None or confidence.casefold() not in {"high", "medium", "low"}:
        errors.append(f"{path.name}: missing allowed AI confidence")
    if rationale is None or len(rationale) < 40:
        errors.append(f"{path.name}: AI rationale is absent or shell-only")
    parse_ai_findings(text, path.name, physical_page_count, errors)


def markdown_section_body_raw(text: str, heading: str) -> str | None:
    text = markdown_visible_text(text)
    matches = list(
        re.finditer(
            rf"(?ims)^[ ]{{0,3}}##[ \t]+{re.escape(heading)}"
            rf"(?:[ \t]+#+)?[ \t]*\r?\n"
            rf"(.*?)(?=^[ ]{{0,3}}#{{1,2}}(?:[ \t]+|$)|\Z)",
            text,
        )
    )
    return matches[0].group(1).strip() if len(matches) == 1 else None


def markdown_section_body(text: str, heading: str) -> str | None:
    body = markdown_section_body_raw(text, heading)
    return normalize_extracted_text(body) if body is not None else None


def validate_summary_markdown_values(
    path: Path,
    academic_rows: dict[str, dict[str, str]],
    ai_rows: dict[str, dict[str, str]],
    evidence_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    text = markdown_visible_text(
        path.read_text(encoding="utf-8", errors="replace")
    )
    specifications = (
        (
            "Current actionable items",
            "Ledger ID",
            academic_rows,
            [
                ("Ledger ID", "LedgerID"),
                ("Priority", "Priority"),
                ("Chair finding ID", "ChairFindingID"),
                ("Source reviewer finding IDs", "SourceReviewerFindingIDs"),
                ("Severity", "Severity"),
                ("S0 subtype", "S0Subtype"),
                ("Remedy", "Remedy"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct PDF-visible observation", "DirectObservation"),
                ("Evidence status", "EvidenceStatus"),
                ("Minimum required action", "MinimumEditEvidence"),
                ("Dependency", "Dependency"),
                ("Owner", "Owner"),
                ("Chair disposition", "Status"),
                ("Verification", "Verification"),
            ],
        ),
        (
            "Current AI-style actionable items — separate from academic grading",
            "AI finding ID",
            ai_rows,
            [
                ("AI finding ID", "AIFindingID"),
                ("Impact (`material` / `local`)", "Impact"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct style observation", "DirectStyleObservation"),
                ("Minimum editing action", "MinimumEditingAction"),
                ("Chair status", "Status"),
                ("Verification", "Verification"),
            ],
        ),
        (
            "Current new evidence or experiments (N)",
            "Evidence item ID",
            evidence_rows,
            [
                ("Evidence item ID", "EvidenceItemID"),
                ("Ledger ID", "LedgerID"),
                ("Chair finding ID", "ChairFindingID"),
                ("Remedy", "Remedy"),
                ("Item", "Item"),
                ("Claim that depends on it", "ClaimThatDependsOnIt"),
                ("Why writing is insufficient", "WhyWritingIsInsufficient"),
                ("Minimum viable evidence", "MinimumViableEvidence"),
                ("Consequence if unavailable", "ConsequenceIfUnavailable"),
            ],
        ),
    )
    for section_heading, first_header, csv_rows, mapping in specifications:
        section = markdown_section_body_raw(text, section_heading) or ""
        parsed = parse_markdown_table_by_header(section, first_header, path.name, errors)
        if parsed is None:
            continue
        headers, rows = parsed
        expected_headers = [header for header, _field in mapping]
        if [value.casefold() for value in headers] != [
            value.casefold() for value in expected_headers
        ]:
            continue
        valid_rows = [row for row in rows if len(row) == len(mapping)]
        observed_id_order = [row[0] for row in valid_rows]
        expected_id_order = [
            markdown_projection_scalar(identifier) for identifier in csv_rows
        ]
        if observed_id_order != expected_id_order:
            errors.append(
                f"{path.name}: {section_heading} row order must exactly project "
                f"the authoritative CSV order {expected_id_order}"
            )
        counts = Counter(row[0] for row in valid_rows)
        duplicates = sorted(key for key, count in counts.items() if count != 1)
        if duplicates:
            errors.append(f"{path.name}: duplicate summary row IDs {duplicates}")
        markdown_by_id = {row[0]: row for row in valid_rows}
        for identifier in sorted(set(csv_rows) & set(markdown_by_id)):
            markdown_row = markdown_by_id[identifier]
            csv_row = csv_rows[identifier]
            for index, (_header, field) in enumerate(mapping):
                expected_value = markdown_projection_scalar(csv_row[field])
                if markdown_row[index] != expected_value:
                    errors.append(
                        f"{path.name}: Markdown/CSV value mismatch for "
                        f"{identifier}/{field}: expected {expected_value!r}, "
                        f"got {markdown_row[index]!r}"
                    )


def validate_chair_ledger_markdown_values(
    path: Path,
    academic_rows: dict[str, dict[str, str]],
    ai_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    specifications = (
        (
            "Ledger ID", academic_rows,
            [
                ("Ledger ID", "LedgerID"), ("Priority", "Priority"),
                ("Chair finding ID", "ChairFindingID"),
                ("Source reviewer finding IDs", "SourceReviewerFindingIDs"),
                ("Severity", "Severity"), ("S0 subtype", "S0Subtype"),
                ("Remedy", "Remedy"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct observation", "DirectObservation"),
                ("Evidence status", "EvidenceStatus"),
                ("Minimum edit/evidence", "MinimumEditEvidence"),
                ("Dependency", "Dependency"), ("Owner", "Owner"),
                ("Status", "Status"), ("Verification", "Verification"),
            ],
        ),
        (
            "AI finding ID", ai_rows,
            [
                ("AI finding ID", "AIFindingID"),
                ("Impact (`material` / `local`)", "Impact"),
                ("Exact PDF anchor", "ExactPDFAnchor"),
                ("Direct style observation", "DirectStyleObservation"),
                ("Minimum editing action", "MinimumEditingAction"),
                ("Status", "Status"), ("Verification", "Verification"),
            ],
        ),
    )
    for first_header, csv_rows, mapping in specifications:
        parsed = parse_markdown_table_by_header(text, first_header, path.name, errors)
        if parsed is None:
            continue
        headers, rows = parsed
        expected_headers = [header for header, _field in mapping]
        if [value.casefold() for value in headers] != [
            value.casefold() for value in expected_headers
        ]:
            continue
        valid_rows = [row for row in rows if len(row) == len(mapping)]
        observed_id_order = [row[0] for row in valid_rows]
        expected_id_order = [
            markdown_projection_scalar(identifier) for identifier in csv_rows
        ]
        if observed_id_order != expected_id_order:
            errors.append(
                f"{path.name}: {first_header} row order must exactly project "
                f"the authoritative CSV order {expected_id_order}"
            )
        markdown_by_id = {
            row[0]: row for row in valid_rows
        }
        for identifier in sorted(set(csv_rows) & set(markdown_by_id)):
            markdown_row = markdown_by_id[identifier]
            csv_row = csv_rows[identifier]
            for index, (_header, field) in enumerate(mapping):
                expected_value = markdown_projection_scalar(csv_row[field])
                if markdown_row[index] != expected_value:
                    errors.append(
                        f"{path.name}: Markdown/CSV value mismatch for "
                        f"{identifier}/{field}: expected {expected_value!r}, "
                        f"got {markdown_row[index]!r}"
                    )


def validate_chair_finding_tables(
    path: Path,
    academic_rows: dict[str, dict[str, str]],
    ai_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    academic_headers = [
        "Chair finding ID", "Source reviewer finding IDs", "Severity", "S0 subtype", "Remedy",
        "Exact PDF anchor", "Direct observation", "Evidence status", "Owner",
        "Minimum required action", "Verification",
    ]
    academic_section = markdown_section_body_raw(text, "Adjudicated findings") or ""
    parsed_academic = parse_markdown_table_by_exact_headers(
        academic_section, academic_headers, path.name, errors
    )
    academic_by_chair_id = {
        row["ChairFindingID"]: row for row in academic_rows.values()
    }
    if parsed_academic is not None:
        valid_rows = [
            row for row in parsed_academic if len(row) == len(academic_headers)
        ]
        counts = Counter(row[0] for row in valid_rows)
        duplicates = sorted(key for key, count in counts.items() if count != 1)
        if duplicates:
            errors.append(f"{path.name}: duplicate chair finding IDs {duplicates}")
        markdown_by_id = {row[0]: row for row in valid_rows}
        compare_sets(
            "chair adjudicated-finding rows",
            set(academic_by_chair_id),
            set(markdown_by_id),
            errors,
        )
        mapping = [
            "ChairFindingID", "SourceReviewerFindingIDs", "Severity", "S0Subtype", "Remedy",
            "ExactPDFAnchor", "DirectObservation", "EvidenceStatus", "Owner",
            "MinimumEditEvidence", "Verification",
        ]
        expected_chair_order = [
            markdown_projection_scalar(row["ChairFindingID"])
            for row in academic_rows.values()
        ]
        if [row[0] for row in valid_rows] != expected_chair_order:
            errors.append(
                f"{path.name}: adjudicated-finding row order must exactly follow "
                "91-revision-ledger.csv"
            )
        for identifier in sorted(set(academic_by_chair_id) & set(markdown_by_id)):
            csv_row = academic_by_chair_id[identifier]
            markdown_row = markdown_by_id[identifier]
            for index, field in enumerate(mapping):
                expected_value = markdown_projection_scalar(csv_row[field])
                if markdown_row[index] != expected_value:
                    errors.append(
                        f"{path.name}: chair/91 value mismatch for "
                        f"{identifier}/{field}"
                    )
    ai_headers = [
        "AI finding ID", "Impact (`material` / `local`)", "Exact PDF anchor",
        "Direct style observation", "Minimum editing action", "Verification", "Status",
    ]
    ai_section = markdown_section_body_raw(text, "AI-style actionable findings") or ""
    parsed_ai = parse_markdown_table_by_exact_headers(
        ai_section, ai_headers, path.name, errors
    )
    if parsed_ai is not None:
        valid_rows = [row for row in parsed_ai if len(row) == len(ai_headers)]
        counts = Counter(row[0] for row in valid_rows)
        duplicates = sorted(key for key, count in counts.items() if count != 1)
        if duplicates:
            errors.append(f"{path.name}: duplicate chair AI finding IDs {duplicates}")
        markdown_by_id = {row[0]: row for row in valid_rows}
        compare_sets(
            "chair AI-actionable rows",
            set(ai_rows),
            set(markdown_by_id),
            errors,
        )
        mapping = [
            "AIFindingID", "Impact", "ExactPDFAnchor", "DirectStyleObservation",
            "MinimumEditingAction", "Verification", "Status",
        ]
        expected_ai_order = [
            markdown_projection_scalar(identifier) for identifier in ai_rows
        ]
        if [row[0] for row in valid_rows] != expected_ai_order:
            errors.append(
                f"{path.name}: AI-actionable row order must exactly follow "
                "91-ai-actionable-ledger.csv"
            )
        for identifier in sorted(set(ai_rows) & set(markdown_by_id)):
            csv_row = ai_rows[identifier]
            markdown_row = markdown_by_id[identifier]
            for index, field in enumerate(mapping):
                expected_value = markdown_projection_scalar(csv_row[field])
                if markdown_row[index] != expected_value:
                    errors.append(
                        f"{path.name}: chair/91 AI value mismatch for "
                        f"{identifier}/{field}"
                    )


def validate_summary_report(
    path: Path,
    expected_pdf_hash: str,
    process: dict[str, Any],
    reviewer_count: int,
    expected_academic_rows: int,
    expected_ai_rows: int,
    expected_evidence_rows: int,
    errors: list[str],
) -> None:
    text = validate_declarations(
        path, expected_pdf_hash, errors,
        process=process, actor_id="S", reviewer_count=reviewer_count,
        allowed_public_endpoints=set(),
    )
    if not text:
        return
    required_headings = (
        "Clean-room identity",
        "Independent and overall conclusions",
        "Current actionable items",
        "Current AI-style actionable items — separate from academic grading",
        "Current new evidence or experiments (N)",
        "Optional suggestions",
        "Unresolved questions",
        "Review limitations",
        "Reconciliation",
    )
    visible_heading_rows = []
    for match in re.finditer(
        r"(?im)^[ ]{0,3}(#{1,2})[ \t]+(.+?)[ \t]*$", text
    ):
        heading_text = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        visible_heading_rows.append((len(match.group(1)), heading_text))
    expected_heading_rows = [
        (1, "Current-round user-facing review summary"),
        *((2, heading) for heading in required_headings),
    ]
    if visible_heading_rows != expected_heading_rows:
        errors.append(
            f"{path.name}: H1/H2 structure must exactly equal the canonical "
            "Stage-S section sequence; extra, missing, duplicate, or reordered "
            "sections are forbidden"
        )
    first_h2 = re.search(r"(?im)^[ ]{0,3}##[ \t]+", text)
    title = re.search(
        r"(?im)^[ ]{0,3}#[ \t]+Current-round user-facing review summary"
        r"(?:[ \t]+#+)?[ \t]*$",
        text,
    )
    if title is None or (
        first_h2 is not None
        and text[title.end():first_h2.start()].strip()
    ):
        errors.append(f"{path.name}: prose outside the canonical Stage-S sections is forbidden")
    for heading in required_headings:
        count = level2_heading_count(text, heading)
        if count != 1:
            errors.append(
                f"{path.name}: section {heading!r} must occur exactly once; "
                f"observed {count}"
            )
    identity_section = markdown_section_body_raw(text, "Clean-room identity") or ""
    identity_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", identity_section
    )
    expected_identity_labels = [
        "Actor ID",
        "Review round ID",
        "Review retry ID",
        "Frozen PDF path and SHA-256",
        "Summary fresh-context declaration",
        "Exact current-round input allowlist",
        "Operational prompt SHA-256",
        "Summary input-receipt/access declaration",
        "Frozen PDF SHA-256 at start and end",
    ]
    if identity_labels != expected_identity_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in identity_section.splitlines()
    ):
        errors.append(
            f"{path.name}: Clean-room identity must contain only the nine "
            "canonical single-line fields in order"
        )
    round_id = labeled_value(identity_section, "Review round ID")
    if round_id != str(process.get("round_id", "")):
        errors.append(
            f"{path.name}: Review round ID does not equal the process envelope"
        )
    retry_id = labeled_value(identity_section, "Review retry ID")
    if retry_id != str(process.get("retry_id", "")):
        errors.append(
            f"{path.name}: Review retry ID does not equal the process envelope"
        )
    frozen_identity = labeled_value(identity_section, "Frozen PDF path and SHA-256") or ""
    frozen_name = str(process.get("frozen_pdf_file", ""))
    expected_frozen_identity = f"file={frozen_name} ; sha256={expected_pdf_hash}"
    if frozen_identity != expected_frozen_identity:
        errors.append(
            f"{path.name}: Frozen PDF path and SHA-256 must exactly equal "
            f"{expected_frozen_identity!r}"
        )
    allowlist_value = labeled_value(identity_section, "Exact current-round input allowlist") or ""
    expected_allowlist_order = canonical_stage_opened_inputs(
        process, reviewer_count, "S", path.parent
    )
    expected_allowlist = set(expected_allowlist_order)
    observed_allowlist = [
        token.strip().strip("`\"")
        for token in re.split(r"\s*;\s*", allowlist_value)
        if token.strip()
    ]
    observed_allowlist_set = set(observed_allowlist)
    if observed_allowlist_set != expected_allowlist:
        errors.append(
            f"{path.name}: Exact current-round input allowlist mismatch; "
            f"missing={sorted(expected_allowlist-observed_allowlist_set)}, "
            f"extra={sorted(observed_allowlist_set-expected_allowlist)}"
        )
    if observed_allowlist != expected_allowlist_order:
        errors.append(
            f"{path.name}: Exact current-round input allowlist must use the "
            "canonical order with each basename exactly once"
        )
    summary_receipt = labeled_value(
        identity_section, "Summary input-receipt/access declaration"
    ) or ""
    summary_opened_match = re.search(
        r"(?i)(?:^|;)[ \t]*opened=\[([^\]]*)\]", summary_receipt
    )
    summary_opened = [
        token.strip().strip("`\"")
        for token in re.split(
            r"\s*;\s*",
            summary_opened_match.group(1) if summary_opened_match else "",
        )
        if token.strip()
    ]
    if summary_opened != expected_allowlist_order:
        errors.append(
            f"{path.name}: Summary opened receipt must exactly equal the "
            "canonical ordered current-round input allowlist"
        )
    summary_received_match = re.search(
        r"(?i)(?:^|;)[ \t]*received=\[([^\]]*)\]", summary_receipt
    )
    if (
        summary_received_match is None
        or summary_received_match.group(1).strip().casefold() != "operational prompt"
    ):
        errors.append(
            f"{path.name}: Stage S received receipt must be exactly "
            "[operational prompt]"
        )
    summary_public_match = re.search(
        r"(?i)(?:^|;)[ \t]*public_endpoints=\[([^\]]*)\]", summary_receipt
    )
    if (
        summary_public_match is None
        or summary_public_match.group(1).strip().casefold() != "none"
    ):
        errors.append(f"{path.name}: Stage S public_endpoints must be [none]")
    conclusion_section = (
        markdown_section_body_raw(text, "Independent and overall conclusions") or ""
    )
    if any(
        line.strip() and not line.lstrip().startswith("|")
        for line in conclusion_section.splitlines()
    ):
        errors.append(
            f"{path.name}: Independent and overall conclusions may contain "
            "only the exact actor table"
        )
    for section_heading in (
        "Current actionable items",
        "Current AI-style actionable items — separate from academic grading",
        "Current new evidence or experiments (N)",
        "Unresolved questions",
    ):
        action_section = markdown_section_body_raw(text, section_heading) or ""
        if any(
            line.strip() and not line.lstrip().startswith("|")
            for line in action_section.splitlines()
        ):
            errors.append(
                f"{path.name}: {section_heading!r} may contain only its exact table"
            )
    conclusion_table = parse_markdown_table_by_header(
        conclusion_section, "Actor", path.name, errors
    )
    if conclusion_table is not None:
        headers, rows = conclusion_table
        expected_headers = [
            "Actor", "Persona/status", "Category or AI-style label",
            "Exact defense recommendation", "Decision regime/source", "Confidence",
            "Decisive current-round basis",
        ]
        if [value.casefold() for value in headers] != [
            value.casefold() for value in expected_headers
        ]:
            errors.append(f"{path.name}: independent-conclusion table schema mismatch")
        actor_rows: dict[str, list[str]] = {}
        for row in rows:
            if len(row) != len(headers):
                continue
            if row[0] in actor_rows:
                errors.append(f"{path.name}: duplicate conclusion actor {row[0]!r}")
            actor_rows[row[0]] = row
        expected_actors = {
            *(f"R{index}" for index in range(1, reviewer_count + 1)),
            "AI", "Chair",
        }
        compare_sets(
            "Stage-S independent-conclusion actors",
            expected_actors,
            set(actor_rows),
            errors,
        )
        expected_actor_order = [
            *(f"R{index}" for index in range(1, reviewer_count + 1)),
            "AI", "Chair",
        ]
        observed_actor_order = [
            row[0] for row in rows if len(row) == len(headers)
        ]
        if observed_actor_order != expected_actor_order:
            errors.append(
                f"{path.name}: independent-conclusion actor order must exactly be "
                f"{expected_actor_order}"
            )
        for actor, row in actor_rows.items():
            if len(row) == len(headers) and (len(row[1]) < 8 or len(row[6]) < 20):
                errors.append(f"{path.name}: {actor} conclusion row is shell-only")
        for index in range(1, reviewer_count + 1):
            actor = f"R{index}"
            report_path = path.parent / f"R{index}-comprehensive-review.md"
            if not report_path.is_file():
                continue
            report = markdown_visible_text(
                report_path.read_text(encoding="utf-8", errors="replace")
            )
            row = actor_rows.get(actor)
            if row:
                projection = reviewer_verdict_projection(report)
                expected_persona = projection["persona"]
                expected_grade = projection["category"]
                expected_rec = projection["recommendation"]
                expected_regime_source = projection["regime_source"]
                expected_conf = projection["confidence"]
                expected_basis = projection["rationale"]
                if not all(
                    (expected_persona, expected_grade, expected_rec,
                     expected_regime_source, expected_conf, expected_basis)
                ):
                    errors.append(
                        f"{path.name}: {actor} source verdict is ambiguous or incomplete"
                    )
                if (
                    row[1] != expected_persona
                    or row[2] != expected_grade
                    or row[3] != expected_rec
                    or row[4] != expected_regime_source
                    or row[5] != expected_conf
                    or row[6] != expected_basis
                ):
                    errors.append(
                        f"{path.name}: {actor} conclusion does not exactly copy "
                        "its independent current-round verdict"
                    )
        ai_text = markdown_visible_text(
            (path.parent / "05-ai-style-assessment.md").read_text(
                encoding="utf-8", errors="replace"
            )
        )
        ai_row = actor_rows.get("AI")
        if ai_row:
            ai_judgment = markdown_section_body_raw(ai_text, "Overall judgment") or ""
            expected_signal = labeled_value(ai_judgment, "AI-style signal") or ""
            expected_conf = labeled_value(ai_judgment, "Confidence") or ""
            expected_basis = labeled_value(ai_judgment, "Rationale") or ""
            if not all((expected_signal, expected_conf, expected_basis)):
                errors.append(
                    f"{path.name}: AI source judgment is ambiguous or incomplete"
                )
            if (
                ai_row[1] != "standalone AI-style assessment"
                or ai_row[2] != expected_signal
                or ai_row[3].casefold() != "n/a"
                or ai_row[4].casefold() != "n/a"
                or ai_row[5] != expected_conf
                or ai_row[6] != expected_basis
            ):
                errors.append(
                    f"{path.name}: AI conclusion does not exactly copy the "
                    "separate current-round style judgment"
                )
        chair_path = path.parent / "90-chair-synthesis.md"
        chair_text = markdown_visible_text(
            chair_path.read_text(encoding="utf-8", errors="replace")
        )
        chair_row = actor_rows.get("Chair")
        if chair_row:
            projection = chair_verdict_projection(chair_text)
            expected_grade = projection["category"]
            expected_rec = projection["recommendation"]
            expected_regime_source = projection["regime_source"]
            expected_conf = projection["confidence"]
            expected_basis = projection["rationale"]
            if not all((
                expected_grade, expected_rec, expected_regime_source,
                expected_conf, expected_basis,
            )):
                errors.append(
                    f"{path.name}: Chair source verdict is ambiguous or incomplete"
                )
            if (
                chair_row[1] != "chair adjudication"
                or chair_row[2] != expected_grade
                or chair_row[3] != expected_rec
                or chair_row[4] != expected_regime_source
                or chair_row[5] != expected_conf
                or chair_row[6] != expected_basis
            ):
                errors.append(
                    f"{path.name}: Chair conclusion does not exactly copy the "
                    "current-round chair verdict"
                )
        for summary_heading, chair_heading in (
            ("Optional suggestions", "Optional suggestions"),
            ("Review limitations", "Review limitations"),
        ):
            summary_body = markdown_section_body(text, summary_heading)
            chair_body = markdown_section_body(chair_text, chair_heading)
            if summary_body != chair_body:
                errors.append(
                    f"{path.name}: section {summary_heading!r} must be an "
                    f"exact current-round projection of chair section {chair_heading!r}"
                )
        disagreement_headers = [
            "Decision ID", "Source item IDs", "Topic", "Positions",
            "Evidence checked", "Status", "Decision",
        ]
        chair_disagreement_section = markdown_section_body_raw(
            chair_text, "Disagreements and chair decisions"
        ) or ""
        chair_disagreement_rows = parse_markdown_table_by_exact_headers(
            chair_disagreement_section, disagreement_headers, chair_path.name, errors
        )
        summary_unresolved_section = markdown_section_body_raw(
            text, "Unresolved questions"
        ) or ""
        summary_unresolved_rows = parse_markdown_table_by_exact_headers(
            summary_unresolved_section, disagreement_headers, path.name, errors
        )
        if chair_disagreement_rows is not None and summary_unresolved_rows is not None:
            expected_unresolved = [
                row for row in chair_disagreement_rows
                if len(row) == len(disagreement_headers)
                and row[5].casefold() in {"unresolved", "not verifiable", "disputed"}
            ]
            if summary_unresolved_rows != expected_unresolved:
                errors.append(
                    f"{path.name}: Unresolved questions must exactly project the "
                    "current unresolved/not-verifiable/disputed chair rows in order"
                )
    reconciliation_section = markdown_section_body_raw(text, "Reconciliation") or ""
    reconciliation_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:",
        reconciliation_section,
    )
    expected_reconciliation_labels = [
        "Open required rows in 91-revision-ledger.csv",
        "Rows in 93-current-actionable-items.csv",
        "Rows in Current actionable items Markdown table",
        "Missing ledger IDs",
        "Extra summary IDs",
        "Duplicate IDs",
        "Open AI rows in 91-ai-actionable-ledger.csv",
        "Rows in 93-current-ai-actionable-items.csv",
        "Rows in Current AI-style actionable items Markdown table",
        "Missing/extra/duplicate AI finding IDs",
        "Rows in 92-new-evidence-or-experiments.csv",
        "Rows in Current new evidence or experiments Markdown table",
        "Missing/extra/duplicate evidence item IDs",
        "Statement",
    ]
    if reconciliation_labels != expected_reconciliation_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in reconciliation_section.splitlines()
    ):
        errors.append(
            f"{path.name}: Reconciliation must contain only the fourteen "
            "canonical single-line fields in order"
        )
    academic_91 = parse_count_label(
        reconciliation_section,
        "Open required rows in 91-revision-ledger.csv",
        path.name,
        errors,
    )
    academic_93_csv = parse_count_label(
        reconciliation_section, "Rows in 93-current-actionable-items.csv", path.name, errors
    )
    academic_93_md = parse_count_label(
        reconciliation_section, "Rows in Current actionable items Markdown table", path.name, errors
    )
    ai_91 = parse_count_label(
        reconciliation_section,
        "Open AI rows in 91-ai-actionable-ledger.csv",
        path.name,
        errors,
    )
    ai_93_csv = parse_count_label(
        reconciliation_section,
        "Rows in 93-current-ai-actionable-items.csv",
        path.name,
        errors,
    )
    ai_93_md = parse_count_label(
        reconciliation_section,
        "Rows in Current AI-style actionable items Markdown table",
        path.name,
        errors,
    )
    evidence_92_csv = parse_count_label(
        reconciliation_section,
        "Rows in 92-new-evidence-or-experiments.csv",
        path.name,
        errors,
    )
    evidence_93_md = parse_count_label(
        reconciliation_section,
        "Rows in Current new evidence or experiments Markdown table",
        path.name,
        errors,
    )
    for observed, expected, label in (
        (academic_91, expected_academic_rows, "91 academic"),
        (academic_93_csv, expected_academic_rows, "93 academic CSV"),
        (academic_93_md, expected_academic_rows, "93 academic Markdown"),
        (ai_91, expected_ai_rows, "91 AI"),
        (ai_93_csv, expected_ai_rows, "93 AI CSV"),
        (ai_93_md, expected_ai_rows, "93 AI Markdown"),
        (evidence_92_csv, expected_evidence_rows, "92 evidence CSV"),
        (evidence_93_md, expected_evidence_rows, "93 evidence Markdown"),
    ):
        if observed is not None and observed != expected:
            errors.append(
                f"{path.name}: {label} reconciliation count {observed} != CSV count {expected}"
            )
    for label in (
        "Missing ledger IDs",
        "Extra summary IDs",
        "Duplicate IDs",
        "Missing/extra/duplicate AI finding IDs",
        "Missing/extra/duplicate evidence item IDs",
    ):
        value = labeled_value(reconciliation_section, label)
        if value is None or value.casefold() != "none":
            errors.append(f"{path.name}: reconciliation '{label}' must be none")
    statement = (
        "This summary introduces no new finding and uses no prior-round "
        "or author-side information."
    )
    if labeled_value(reconciliation_section, "Statement") != statement:
        errors.append(
            f"{path.name}: reconciliation Statement must exactly equal the "
            "canonical clean Stage-S non-invention statement"
        )


def parse_name_hash_list(
    value: str, filename: str, label: str, errors: list[str]
) -> list[tuple[str, str]]:
    """Parse a canonical `basename@SHA256 ; ...` identity list."""

    tokens = [token.strip() for token in value.split(";") if token.strip()]
    parsed: list[tuple[str, str]] = []
    for token in tokens:
        match = re.fullmatch(r"([^@/\\\s]+)@([0-9A-Fa-f]{64})", token)
        if match is None or Path(match.group(1)).name != match.group(1):
            errors.append(
                f"{filename}: {label} must be a canonical semicolon-separated "
                "basename@SHA-256 list"
            )
            return []
        parsed.append((match.group(1), match.group(2).upper()))
    names = [name for name, _digest in parsed]
    if not parsed or len(names) != len(set(names)):
        errors.append(
            f"{filename}: {label} must be nonempty and duplicate-free"
        )
    return parsed


def parse_optional_name_hash_list(
    value: str, filename: str, label: str, errors: list[str]
) -> list[tuple[str, str]]:
    """Parse `none` or a canonical nonempty basename/hash identity list."""

    if value.strip().casefold() == "none":
        return []
    return parse_name_hash_list(value, filename, label, errors)


def validate_stage_v_input_files(
    input_dir: Path,
    identities: list[tuple[str, str]],
    report_name: str,
    errors: list[str],
) -> set[str]:
    """Verify the exact closed set of copied, hash-bound Stage-V inputs."""

    names = [name for name, _digest in identities]
    duplicates = sorted(
        name for name, count in Counter(names).items() if count != 1
    )
    if duplicates:
        errors.append(
            f"{report_name}: Stage-V prior artifact identities must be globally "
            f"duplicate-free; repeated={duplicates}"
        )
    if is_link_or_reparse(input_dir) or not input_dir.is_dir():
        errors.append(
            f"{report_name}: missing Stage-V input directory {input_dir.name}"
        )
        for name in sorted(set(names)):
            errors.append(
                f"{report_name}: missing prior allowlisted artifact {name!r}"
            )
        return set()

    entries = list(input_dir.iterdir())
    actual_files = {
        entry.name for entry in entries
        if entry.is_file() and not is_link_or_reparse(entry)
    }
    nested_or_nonfiles = sorted(
        entry.name for entry in entries
        if not entry.is_file() or is_link_or_reparse(entry)
    )
    if nested_or_nonfiles:
        errors.append(
            f"{report_name}: {input_dir.name} may contain only regular input "
            f"files; invalid={nested_or_nonfiles}"
        )
    expected_names = set(names)
    unexpected = sorted(actual_files - expected_names)
    if unexpected:
        errors.append(
            f"{report_name}: unallowlisted artifact(s) in {input_dir.name} "
            f"{unexpected}"
        )

    verified: set[str] = set()
    expected_by_name: dict[str, str] = {}
    for name, digest in identities:
        expected_by_name.setdefault(name, digest.upper())
    for name, expected_digest in expected_by_name.items():
        artifact = input_dir / name
        if not artifact.is_file() or is_link_or_reparse(artifact):
            errors.append(
                f"{report_name}: missing prior allowlisted artifact {name!r}"
            )
            continue
        actual_digest = sha256(artifact)
        if actual_digest != expected_digest:
            errors.append(
                f"{report_name}: prior allowlisted artifact hash mismatch for "
                f"{name!r}; declared={expected_digest}, actual={actual_digest}"
            )
            continue
        verified.add(name)
    return verified


def validate_stage_v(
    path: Path,
    expected_pdf_hash: str,
    process: dict[str, Any],
    reviewer_count: int,
    current_finding_ids: set[str],
    current_reviewer_findings: dict[str, dict[str, str]],
    page_inventory: list[dict[str, str]],
    page_ledger: list[dict[str, str]],
    bibliography_inventory: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    citation_inventory: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
    academic_ledger: list[dict[str, str]],
    ai_ledger: list[dict[str, str]],
    errors: list[str],
) -> None:
    """Validate an optional post-freeze prior-issue closure artifact.

    Stage V is deliberately absent from the fresh review path.  When present,
    this gate proves that all current-round judgments were already frozen and
    that only explicitly hash-bound prior artifacts entered the later actor.
    """

    if not path.exists():
        return
    if not path.is_file():
        errors.append(f"{path.name}: Stage-V artifact is not a regular file")
        return
    text = validate_declarations(path, expected_pdf_hash, errors)
    if not text:
        return
    if process.get("review_mode") != "fresh-rereview":
        errors.append(
            f"{path.name}: Stage V is allowed only when review_mode=fresh-rereview"
        )
    required_headings = (
        "Boundary and frozen-current-round identity",
        "Prior-issue closure",
        "Longitudinal AI-style comparison — non-review",
        "Full longitudinal regression audit — non-review",
        "Iterative completion checklist",
    )
    visible_heading_rows: list[tuple[int, str]] = []
    for match in re.finditer(r"(?im)^[ ]{0,3}(#{1,2})[ \t]+(.+?)[ \t]*$", text):
        heading_text = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        visible_heading_rows.append((len(match.group(1)), heading_text))
    expected_heading_rows = [
        (1, "Post-freeze prior-issue closure verification"),
        *((2, heading) for heading in required_headings),
    ]
    if visible_heading_rows != expected_heading_rows:
        errors.append(
            f"{path.name}: H1/H2 structure must exactly equal the canonical "
            "Stage-V section sequence"
        )
    title = re.search(
        r"(?im)^[ ]{0,3}#[ \t]+Post-freeze prior-issue closure verification"
        r"(?:[ \t]+#+)?[ \t]*$",
        text,
    )
    first_h2 = re.search(r"(?im)^[ ]{0,3}##[ \t]+", text)
    if title is None or (
        first_h2 is not None and text[title.end():first_h2.start()].strip()
    ):
        errors.append(f"{path.name}: prose outside canonical Stage-V sections is forbidden")
    boundary = markdown_section_body_raw(
        text, "Boundary and frozen-current-round identity"
    ) or ""
    boundary_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", boundary
    )
    expected_boundary_labels = [
        "Actor ID",
        "Review round ID",
        "Review retry ID",
        "Current frozen PDF and round",
        "Current fresh reports/chair/summary already frozen",
        "Hash-bound prior-issues CSV",
        "Additional allowlisted prior artifacts",
        "Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested",
        "Full regression baseline",
        "Fresh-context declaration",
        "Operational prompt SHA-256",
        "Input-receipt/access declaration",
        "Frozen PDF SHA-256 at start and end",
    ]
    if boundary_labels != expected_boundary_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in boundary.splitlines()
    ):
        errors.append(
            f"{path.name}: Stage-V boundary must contain only the thirteen "
            "canonical single-line fields in order"
        )
    if labeled_value(boundary, "Actor ID") != "V":
        errors.append(f"{path.name}: Actor ID must exactly equal 'V'")
    if labeled_value(boundary, "Review round ID") != str(process.get("round_id", "")):
        errors.append(f"{path.name}: Review round ID does not equal the process envelope")
    if labeled_value(boundary, "Review retry ID") != str(process.get("retry_id", "")):
        errors.append(f"{path.name}: Review retry ID does not equal the process envelope")
    prompt_map = process.get("actor_prompt_sha256", {})
    expected_prompt_hash = (
        str(prompt_map.get("V", "")) if isinstance(prompt_map, dict) else ""
    )
    observed_prompt_hash = labeled_value(boundary, "Operational prompt SHA-256") or ""
    if observed_prompt_hash.upper() != expected_prompt_hash.upper():
        errors.append(
            f"{path.name}: Operational prompt SHA-256 does not match the "
            "process-bound V prompt hash"
        )
    expected_current = " ; ".join((
        f"round_id={process.get('round_id')}",
        f"retry_id={process.get('retry_id')}",
        f"file={process.get('frozen_pdf_file')}",
        f"sha256={expected_pdf_hash}",
    ))
    if labeled_value(boundary, "Current frozen PDF and round") != expected_current:
        errors.append(
            f"{path.name}: Current frozen PDF and round must exactly project "
            "the process envelope"
        )
    current_files = [
        "00-page-inventory.csv", "00-bibliography-inventory.csv",
        "00-citation-inventory.csv", "02-page-layout-ledger.csv",
        "03-bibliography-audit-ledger.csv",
        "04-citation-claim-audit-ledger.csv",
        *(f"R{index}-comprehensive-review.md" for index in range(1, reviewer_count + 1)),
        "05-ai-style-assessment.md", "90-chair-synthesis.md",
        "91-revision-ledger.md", "91-revision-ledger.csv",
        "91-ai-actionable-ledger.csv", "92-new-evidence-or-experiments.md",
        "92-new-evidence-or-experiments.csv",
        "93-user-facing-summary.md", "93-current-actionable-items.csv",
        "93-current-ai-actionable-items.csv",
    ]
    expected_current_identities = " ; ".join(
        f"{name}@{sha256(path.parent / name)}"
        for name in current_files if (path.parent / name).is_file()
    )
    current_identity_value = labeled_value(
        boundary, "Current fresh reports/chair/summary already frozen"
    ) or ""
    if len([name for name in current_files if (path.parent / name).is_file()]) != len(current_files):
        errors.append(f"{path.name}: a required current-round frozen artifact is missing")
    if current_identity_value != expected_current_identities:
        errors.append(
            f"{path.name}: current frozen artifact identity list must exactly "
            "match the canonical files and their hashes"
        )
    prior_issue_value = labeled_value(boundary, "Hash-bound prior-issues CSV") or ""
    prior_issue_identities = parse_name_hash_list(
        prior_issue_value, path.name, "Hash-bound prior-issues CSV", errors
    )
    if len(prior_issue_identities) != 1 or not all(
        name.casefold().endswith("prior-issues.csv")
        for name, _digest in prior_issue_identities
    ):
        errors.append(
            f"{path.name}: Hash-bound prior-issues CSV must identify exactly "
            "one *prior-issues.csv artifact"
        )
    additional_value = labeled_value(
        boundary, "Additional allowlisted prior artifacts"
    ) or ""
    additional_identities = parse_optional_name_hash_list(
        additional_value, path.name, "Additional allowlisted prior artifacts", errors
    )
    if any(
        name.casefold().endswith("prior-issues.csv")
        for name, _digest in additional_identities
    ):
        errors.append(
            f"{path.name}: additional prior artifacts cannot introduce a "
            "second prior-issues CSV"
        )

    prior_ai_boundary_value = labeled_value(
        boundary,
        "Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested",
    ) or ""
    prior_ai_identities: list[tuple[str, str]] = []
    if prior_ai_boundary_value.casefold() != "not run":
        prior_ai_identities = parse_name_hash_list(
            prior_ai_boundary_value,
            path.name,
            "Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested",
            errors,
        )
        if len(prior_ai_identities) != 1:
            errors.append(
                f"{path.name}: longitudinal AI comparison must identify exactly "
                "one prior AI report"
            )

    baseline_value = labeled_value(boundary, "Full regression baseline") or ""
    baseline_complete = baseline_value.startswith("run with complete prior baseline ; ")
    baseline_identities: list[tuple[str, str]] = []
    baseline_items: dict[str, str] = {}
    if baseline_value != "not run" and not baseline_complete:
        errors.append(
            f"{path.name}: Full regression baseline must be 'not run' or the "
            "canonical complete-baseline record"
        )
    if baseline_complete:
        required_baseline_keys = (
            "prior_pdf", "prior_page_inventory", "prior_page_ledger",
            "prior_bibliography_inventory", "prior_bibliography_ledger",
            "prior_citation_inventory", "prior_citation_ledger",
        )
        baseline_tail = baseline_value.split(" ; ")[1:]
        for item in baseline_tail:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            baseline_items[key] = value
        if (
            len(baseline_tail) != len(required_baseline_keys)
            or tuple(baseline_items) != required_baseline_keys
        ):
            errors.append(
                f"{path.name}: complete regression baseline must list the seven "
                "canonical identities in order"
            )
        for key in required_baseline_keys:
            parsed_identity = parse_name_hash_list(
                baseline_items.get(key, ""),
                path.name,
                f"complete-baseline identity {key}",
                errors,
            )
            if len(parsed_identity) != 1:
                errors.append(
                    f"{path.name}: invalid complete-baseline identity {key}"
                )
            else:
                baseline_identities.extend(parsed_identity)

    all_prior_identities = [
        *prior_issue_identities,
        *additional_identities,
        *prior_ai_identities,
        *baseline_identities,
    ]
    prior_names = [name for name, _digest in all_prior_identities]
    if any(
        name in current_files or name == process.get("frozen_pdf_file")
        for name in prior_names
    ):
        errors.append(f"{path.name}: prior allowlist reuses a current-round basename")
    verified_prior_names = validate_stage_v_input_files(
        path.parent / "stage-v-inputs", all_prior_identities, path.name, errors
    )

    receipt_match = re.search(
        r"(?im)^[ ]{0,3}-[ \t]+Input-receipt/access declaration[ \t]*:[ \t]*(.*)$",
        boundary,
    )
    if receipt_match is not None:
        receipt = receipt_match.group(1)
        parsed_receipt = parse_closed_access_receipt(receipt, path.name, errors)
        received_items = (
            parsed_receipt.get("received") if parsed_receipt is not None else None
        )
        if received_items != ["operational prompt"]:
            errors.append(
                f"{path.name}: Stage-V received receipt must be exactly "
                "[operational prompt]"
            )
        opened_items = (
            parsed_receipt.get("opened", []) if parsed_receipt is not None else []
        )
        expected_opened = [
            "00-process-parameters.json", "SKILL.md",
            "clean-room-orchestration.md", "grading-and-verdicts.md",
            "report-template.md", "ai-style-audit.md", "ledger-validation.md",
            str(process.get("frozen_pdf_file", "")),
            *current_files,
            *prior_names,
        ]
        if opened_items != expected_opened:
            errors.append(
                f"{path.name}: Stage-V opened receipt must exactly equal the "
                "canonical current/prior allowlist in order"
            )
        public_items = (
            parsed_receipt.get("public_endpoints")
            if parsed_receipt is not None else None
        )
        if public_items != ["none"]:
            errors.append(
                f"{path.name}: Stage-V public_endpoints must be exactly [none]"
            )

    prior_issue_rows: list[dict[str, str]] = []
    if len(prior_issue_identities) == 1:
        prior_issue_name = prior_issue_identities[0][0]
        if prior_issue_name in verified_prior_names:
            prior_issue_rows = read_csv(
                path.parent / "stage-v-inputs" / prior_issue_name,
                PRIOR_ISSUES_COLUMNS,
                errors,
                require_rows=True,
            )
            validate_rows_mandatory(
                prior_issue_rows,
                prior_issue_name,
                PRIOR_ISSUES_COLUMNS,
                errors,
            )
            prior_issue_ids: set[str] = set()
            prior_pdf_hashes: set[str] = set()
            for line, row in enumerate(prior_issue_rows, start=2):
                finding_id = row.get("PriorFindingID", "")
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,127}", finding_id):
                    errors.append(
                        f"{prior_issue_name}:{line}: invalid PriorFindingID "
                        f"{finding_id!r}"
                    )
                elif finding_id in prior_issue_ids:
                    errors.append(
                        f"{prior_issue_name}: duplicate PriorFindingID {finding_id!r}"
                    )
                prior_issue_ids.add(finding_id)
                prior_pdf_hash = row.get("PriorPDFSHA256", "")
                if not HEX64_RE.fullmatch(prior_pdf_hash):
                    errors.append(
                        f"{prior_issue_name}:{line}: PriorPDFSHA256 is not 64 hex"
                    )
                else:
                    prior_pdf_hashes.add(prior_pdf_hash.upper())
                prior_anchor = parse_physical_page_locator(
                    row.get("PriorPDFAnchor", "")
                )
                if prior_anchor is None or prior_anchor < 1:
                    errors.append(
                        f"{prior_issue_name}:{line}: PriorPDFAnchor must identify "
                        "a positive prior physical page"
                    )
            if len(prior_pdf_hashes) != 1:
                errors.append(
                    f"{prior_issue_name}: every row must bind to one identical "
                    "PriorPDFSHA256"
                )
            if baseline_complete and baseline_identities and prior_pdf_hashes:
                baseline_prior_pdf_hash = baseline_identities[0][1]
                if prior_pdf_hashes != {baseline_prior_pdf_hash}:
                    errors.append(
                        f"{prior_issue_name}: PriorPDFSHA256 does not match the "
                        "complete-baseline prior_pdf identity"
                    )
    closure_section = markdown_section_body_raw(text, "Prior-issue closure") or ""
    if any(
        line.strip() and not line.lstrip().startswith("|")
        for line in closure_section.splitlines()
    ):
        errors.append(f"{path.name}: Prior-issue closure may contain only its table")
    closure_headers = [
        "Prior finding", "Status", "Evidence in revised PDF",
        "Regression check", "Current-round related finding, if any",
    ]
    closure_rows = parse_markdown_table_by_exact_headers(
        closure_section, closure_headers, path.name, errors
    )
    if closure_rows is not None:
        if not closure_rows:
            errors.append(f"{path.name}: prior-issue closure table must contain a row")
        prior_findings = [row[0] for row in closure_rows if len(row) == len(closure_headers)]
        if len(prior_findings) != len(set(prior_findings)):
            errors.append(f"{path.name}: duplicate Prior finding rows")
        for row in closure_rows:
            if len(row) != len(closure_headers):
                continue
            if any(not cell or is_placeholder(cell) for cell in row):
                errors.append(f"{path.name}: prior-issue closure row is incomplete")
                continue
            if row[1].casefold() not in {
                "resolved", "unresolved", "not verifiable", "rejected",
                "superseded by current finding",
            }:
                errors.append(f"{path.name}: invalid prior-finding Status {row[1]!r}")
            evidence_page = parse_physical_page_locator(row[2])
            if (
                evidence_page is None
                or evidence_page < 1
                or evidence_page > int(process.get("physical_page_count") or 0)
            ):
                errors.append(
                    f"{path.name}: prior-finding evidence requires a current physical-page anchor"
                )
            regression = row[3].casefold()
            if regression not in {
                "not assessed", "no regression visible", "regression visible",
                "not comparable",
            }:
                errors.append(f"{path.name}: invalid Regression check {row[3]!r}")
            if not baseline_complete and regression != "not assessed":
                errors.append(
                    f"{path.name}: regression status cannot be asserted without "
                    "the complete prior baseline"
                )
            related = row[4]
            if related.casefold() != "none":
                related_ids = re.findall(r"(?:R\d+-F\d{2,4}|C-F\d{2,4}|AI-F\d{2,4})", related)
                residue = re.sub(
                    r"(?:R\d+-F\d{2,4}|C-F\d{2,4}|AI-F\d{2,4})", "", related
                )
                residue = re.sub(r"[\s,，;/|]+", "", residue)
                if residue or not related_ids or any(
                    identifier not in current_finding_ids for identifier in related_ids
                ):
                    errors.append(
                        f"{path.name}: Current-round related finding must contain "
                        "only existing current-round IDs or none"
                    )
        if prior_issue_rows:
            expected_prior_findings = [
                row.get("PriorFindingID", "") for row in prior_issue_rows
            ]
            expected_prior_set = set(expected_prior_findings)
            observed_prior_set = set(prior_findings)
            phantom_prior_ids = sorted(observed_prior_set - expected_prior_set)
            missing_prior_ids = sorted(expected_prior_set - observed_prior_set)
            if phantom_prior_ids:
                errors.append(
                    f"{path.name}: phantom prior finding IDs absent from the "
                    f"hash-bound prior-issues CSV {phantom_prior_ids}"
                )
            if missing_prior_ids:
                errors.append(
                    f"{path.name}: missing prior finding IDs required by the "
                    f"hash-bound prior-issues CSV {missing_prior_ids}"
                )
            if (
                not phantom_prior_ids
                and not missing_prior_ids
                and prior_findings != expected_prior_findings
            ):
                errors.append(
                    f"{path.name}: prior-issue closure rows must preserve the "
                    "prior-issues CSV row order"
                )
    ai_section = markdown_section_body_raw(
        text, "Longitudinal AI-style comparison — non-review"
    ) or ""
    ai_labels = [
        "Status", "Prior AI report identity/hash", "Current AI report identity/hash",
        "Prior open material/local AI-F IDs", "Current corresponding evidence/status",
        "New current AI-F IDs", "Limitations", "Separation statement",
    ]
    observed_ai_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", ai_section
    )
    if observed_ai_labels != ai_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in ai_section.splitlines()
    ):
        errors.append(f"{path.name}: longitudinal AI section label sequence mismatch")
    ai_status = (labeled_value(ai_section, "Status") or "").casefold()
    if ai_status not in {"not run", "run"}:
        errors.append(f"{path.name}: longitudinal AI Status must be not run or run")
    current_ai_identity = labeled_value(ai_section, "Current AI report identity/hash") or ""
    expected_ai_identity = (
        f"05-ai-style-assessment.md@{sha256(path.parent / '05-ai-style-assessment.md')}"
        if (path.parent / "05-ai-style-assessment.md").is_file() else ""
    )
    if ai_status == "run":
        prior_ai_identity = labeled_value(ai_section, "Prior AI report identity/hash") or ""
        if not re.fullmatch(r"[^@/\\\s]+@[0-9A-Fa-f]{64}", prior_ai_identity):
            errors.append(f"{path.name}: run AI comparison requires prior report identity/hash")
        if current_ai_identity != expected_ai_identity:
            errors.append(f"{path.name}: current AI report identity/hash is not current-round exact")
        if labeled_value(
            boundary,
            "Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested",
        ) != prior_ai_identity:
            errors.append(
                f"{path.name}: boundary prior AI identity must exactly equal the "
                "longitudinal AI section"
            )
    else:
        if (labeled_value(
            boundary,
            "Prior frozen AI-style report identity/hash, only if longitudinal style comparison requested",
        ) or "").casefold() != "not run":
            errors.append(f"{path.name}: not-run AI comparison requires boundary value not run")
        if (labeled_value(ai_section, "Prior AI report identity/hash") or "").casefold() != "n/a":
            errors.append(f"{path.name}: not-run AI comparison requires prior identity N/A")
        if current_ai_identity.casefold() != "n/a":
            errors.append(f"{path.name}: not-run AI comparison requires current identity N/A")
    separation = (
        "this comparison does not alter the current chair decision, grade, "
        "current ai report, 91 ledgers, or 93 summary."
    )
    if (labeled_value(ai_section, "Separation statement") or "").casefold() != separation:
        errors.append(f"{path.name}: longitudinal AI separation statement is not exact")
    regression_section = markdown_section_body_raw(
        text, "Full longitudinal regression audit — non-review"
    ) or ""
    regression_labels = [
        "Status", "Prior/current PDF identities and hashes",
        "Prior/current page, bibliography, citation inventory/ledger identities and hashes",
        "Demonstrated regressions on comparable objects",
        "Current fresh findings whose introduction time is not verifiable",
        "Limitations",
    ]
    observed_regression_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", regression_section
    )
    if observed_regression_labels != regression_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in regression_section.splitlines()
    ):
        errors.append(f"{path.name}: regression-audit label sequence mismatch")
    regression_status = labeled_value(regression_section, "Status") or ""
    expected_regression_status = (
        "run with complete prior baseline" if baseline_complete else "not run"
    )
    if regression_status != expected_regression_status:
        errors.append(
            f"{path.name}: regression-audit Status must equal {expected_regression_status!r}"
        )
    limitations = labeled_value(regression_section, "Limitations") or ""
    if baseline_complete:
        baseline_tokens = [
            value for item in baseline_value.split(" ; ")[1:]
            if "=" in item for _key, value in [item.split("=", 1)]
        ]
        regression_identity_text = " ".join((
            labeled_value(
                regression_section, "Prior/current PDF identities and hashes"
            ) or "",
            labeled_value(
                regression_section,
                "Prior/current page, bibliography, citation inventory/ledger identities and hashes",
            ) or "",
        ))
        missing_baseline_projection = [
            value for value in baseline_tokens if value not in regression_identity_text
        ]
        if expected_pdf_hash not in regression_identity_text or missing_baseline_projection:
            errors.append(
                f"{path.name}: regression identity fields do not project the "
                "complete prior baseline and current PDF"
            )
    if not baseline_complete:
        if "global regression not assessed" not in limitations.casefold():
            errors.append(
                f"{path.name}: missing exact 'global regression not assessed' limitation"
            )
        if re.search(
            r"(?i)(?:introduced|caused|created|newly added)\s+(?:by|during)\s+(?:the\s+)?revision",
            text,
        ):
            errors.append(
                f"{path.name}: revision-introduced regression cannot be inferred "
                "without a complete prior baseline"
            )
    checklist = markdown_section_body_raw(text, "Iterative completion checklist") or ""
    checklist_labels = [
        "Final page-ledger re-entry",
        "Final page and affected-neighbor recheck",
        "Final bibliography/citation re-entry and re-verification",
        "Empty S0--S3 status across all current reviewers",
        "Fresh isolated AI assessment status/signal/material remainder",
        "Remaining S4 suggestions or review limitations",
        "Prior unresolved or not-verifiable findings",
        "Iterative-loop completion gate",
    ]
    observed_checklist_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", checklist
    )
    if observed_checklist_labels != checklist_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in checklist.splitlines()
    ):
        errors.append(f"{path.name}: iterative completion checklist schema mismatch")

    page_unresolved = sum(
        any(
            token in row.get("Disposition", "").casefold()
            for token in ("pending", "unchecked", "recheck", "open", "unresolved")
        )
        for row in page_ledger
    )
    page_id_difference = len(
        {row.get("PageID", "") for row in page_inventory}
        ^ {row.get("PageID", "") for row in page_ledger}
    )
    page_neighbor_missing = sum(
        not row.get("NeighborPagesChecked", "").strip()
        or is_placeholder(row.get("NeighborPagesChecked", ""))
        for row in page_ledger
    )
    bibliography_verdicts = Counter(
        row.get("Verdict", "").casefold() for row in bibliography_ledger
    )
    citation_support = Counter(
        row.get("Support", "").casefold() for row in citation_ledger
    )
    citation_metadata = Counter(
        row.get("MetadataStatus", "").casefold() for row in citation_ledger
    )
    bibliography_id_difference = len(
        {row.get("ReferenceID", "") for row in bibliography_inventory}
        ^ {row.get("ReferenceID", "") for row in bibliography_ledger}
    )
    citation_id_difference = len(
        {row.get("PairID", "") for row in citation_inventory}
        ^ {row.get("PairID", "") for row in citation_ledger}
    )
    reviewer_s0_s3 = sum(
        fields.get("Severity", "").casefold() in ACADEMIC_SEVERITIES
        for fields in current_reviewer_findings.values()
    )
    open_academic_rows = sum(
        row.get("Status", "").casefold() not in CLOSED_STATUSES
        for row in academic_ledger
    )
    open_ai_rows = sum(
        row.get("Impact", "").casefold() in AI_ACTION_IMPACTS
        and row.get("Status", "").casefold() not in CLOSED_STATUSES
        for row in ai_ledger
    )
    current_ai_signal = ""
    current_ai_path = path.parent / "05-ai-style-assessment.md"
    if current_ai_path.is_file():
        current_ai_text = markdown_visible_text(
            current_ai_path.read_text(encoding="utf-8", errors="replace")
        )
        current_ai_judgment = markdown_section_body_raw(
            current_ai_text, "Overall judgment"
        ) or ""
        current_ai_signal = labeled_value(
            current_ai_judgment, "AI-style signal"
        ) or ""
    prior_unresolved = 0
    if closure_rows is not None:
        prior_unresolved = sum(
            len(row) == len(closure_headers)
            and row[1].casefold() in {"unresolved", "not verifiable"}
            for row in closure_rows
        )

    completion_pass = all((
        len(page_inventory) == int(process.get("physical_page_count") or 0),
        len(page_ledger) == int(process.get("physical_page_count") or 0),
        page_id_difference == 0,
        page_unresolved == 0,
        page_neighbor_missing == 0,
        bibliography_id_difference == 0,
        bibliography_verdicts["mismatch"] == 0,
        bibliography_verdicts["unverifiable"] == 0,
        citation_id_difference == 0,
        citation_support["mismatch"] == 0,
        citation_support["unverifiable"] == 0,
        citation_metadata["mismatch"] == 0,
        citation_metadata["unverifiable"] == 0,
        reviewer_s0_s3 == 0,
        open_academic_rows == 0,
        open_ai_rows == 0,
        prior_unresolved == 0,
    ))
    expected_checklist_values = {
        "Final page-ledger re-entry": (
            f"inventory_rows={len(page_inventory)} ; "
            f"ledger_rows={len(page_ledger)} ; "
            f"expected={int(process.get('physical_page_count') or 0)} ; "
            f"missing_or_extra_page_ids={page_id_difference} ; "
            f"unchecked_or_unresolved={page_unresolved}"
        ),
        "Final page and affected-neighbor recheck": (
            f"rows_missing_neighbor_record={page_neighbor_missing}"
        ),
        "Final bibliography/citation re-entry and re-verification": (
            f"bibliography_inventory_rows={len(bibliography_inventory)} ; "
            f"bibliography_audit_rows={len(bibliography_ledger)} ; "
            f"bibliography_missing_or_extra_ids={bibliography_id_difference} ; "
            f"bibliography_mismatch={bibliography_verdicts['mismatch']} ; "
            f"bibliography_unverifiable={bibliography_verdicts['unverifiable']} ; "
            f"citation_inventory_rows={len(citation_inventory)} ; "
            f"citation_audit_rows={len(citation_ledger)} ; "
            f"citation_missing_or_extra_ids={citation_id_difference} ; "
            f"citation_support_mismatch={citation_support['mismatch']} ; "
            f"citation_support_unverifiable={citation_support['unverifiable']} ; "
            f"citation_metadata_mismatch={citation_metadata['mismatch']} ; "
            f"citation_metadata_unverifiable={citation_metadata['unverifiable']}"
        ),
        "Empty S0--S3 status across all current reviewers": (
            f"{'yes' if reviewer_s0_s3 == 0 else 'no'} ; "
            f"reviewer_s0_s3={reviewer_s0_s3} ; "
            f"open_academic_rows={open_academic_rows}"
        ),
        "Fresh isolated AI assessment status/signal/material remainder": (
            f"run ; signal={current_ai_signal} ; "
            f"open_material_or_local_rows={open_ai_rows}"
        ),
        "Prior unresolved or not-verifiable findings": (
            f"count={prior_unresolved}"
        ),
        "Iterative-loop completion gate": (
            "pass" if completion_pass else "fail"
        ),
    }
    for label, expected_value in expected_checklist_values.items():
        value = labeled_value(checklist, label) or ""
        if value != expected_value:
            errors.append(
                f"{path.name}: checklist field {label!r} contradicts current "
                f"CSV/report state; expected {expected_value!r}"
            )
    remaining_value = labeled_value(
        checklist, "Remaining S4 suggestions or review limitations"
    ) or ""
    if len(remaining_value) < 3 or is_placeholder(remaining_value):
        errors.append(
            f"{path.name}: checklist field 'Remaining S4 suggestions or review "
            "limitations' is shell-only"
        )


def validate_helper_bundle(
    root: Path,
    expected_pdf_hash: str,
    process: dict[str, Any],
    reviewer_count: int,
    errors: list[str],
) -> None:
    helpers = root / "helpers"
    if not helpers.exists():
        return
    if is_link_or_reparse(helpers) or not helpers.is_dir():
        errors.append("helpers exists but is not a directory")
        return
    entries = list(helpers.iterdir())
    if not entries:
        errors.append("helpers: empty directory must be omitted")
        return
    files = sorted(
        path for path in entries
        if path.is_file() and not is_link_or_reparse(path)
    )
    invalid_entries = sorted(
        path.name for path in entries
        if is_link_or_reparse(path) or not path.is_file()
    )
    if invalid_entries:
        errors.append(
            "helpers: only in-root regular files are allowed; invalid="
            f"{invalid_entries}"
        )
    provenance_files = [
        path for path in files
        if re.fullmatch(r"H\d{2}-provenance\.json", path.name)
    ]
    registered: Counter[str] = Counter()
    registered_portable_names: dict[str, str] = {}
    process_prompt_hashes = {
        str(value).upper() for value in (
            process.get("actor_prompt_sha256", {}).values()
            if isinstance(process.get("actor_prompt_sha256"), dict) else []
        )
    }
    helper_prompt_hashes: set[str] = set()
    helper_allowed_opened = canonical_stage_opened_inputs(
        process, reviewer_count, "R1"
    )
    allowed_recipients = {
        "P", "AI", "C",
        *(f"R{index}" for index in range(1, reviewer_count + 1)),
    }
    for provenance_path in provenance_files:
        try:
            data = json.loads(provenance_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{provenance_path.name}: invalid provenance JSON: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{provenance_path.name}: provenance root must be an object")
            continue
        keys = set(data)
        if keys != HELPER_PROVENANCE_KEYS:
            errors.append(
                f"{provenance_path.name}: provenance schema mismatch; "
                f"missing={sorted(HELPER_PROVENANCE_KEYS-keys)}, "
                f"extra={sorted(keys-HELPER_PROVENANCE_KEYS)}"
            )
        for field in (
            "actor_id", "round_id", "retry_id", "fresh_context_declaration",
            "input_receipt_access_declaration", "tool", "version",
            "command_or_query",
        ):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip() or is_placeholder(value):
                errors.append(f"{provenance_path.name}: invalid/blank {field}")
        expected_actor = provenance_path.name.removesuffix("-provenance.json")
        if data.get("actor_id") != expected_actor:
            errors.append(
                f"{provenance_path.name}: actor_id must equal {expected_actor!r}"
            )
        if data.get("round_id") != process.get("round_id"):
            errors.append(f"{provenance_path.name}: round_id does not match process")
        if data.get("retry_id") != process.get("retry_id"):
            errors.append(f"{provenance_path.name}: retry_id does not match process")
        expected_fresh = (
            "no inherited user/thread/task turns beyond system/developer instructions "
            "and the exact operational prompt"
        )
        if str(data.get("fresh_context_declaration", "")).casefold() != expected_fresh:
            errors.append(
                f"{provenance_path.name}: fresh_context_declaration must exactly "
                "equal the canonical clean-context boundary"
            )
        receipt_text = str(data.get("input_receipt_access_declaration", "")).casefold()
        for required_phrase in (
            "no unlisted substantive assertion", "no prohibited context/artifact",
            "neighboring paths were not enumerated",
        ):
            if required_phrase not in receipt_text:
                errors.append(
                    f"{provenance_path.name}: helper receipt omits {required_phrase!r}"
                )
        for field in (
            "received_blocks", "opened_inputs", "limitations", "recipient_stages",
        ):
            value = data.get(field)
            if not isinstance(value, list):
                errors.append(f"{provenance_path.name}: {field} must be an array")
            elif field in {
                "received_blocks", "opened_inputs", "recipient_stages",
            } and not value:
                errors.append(f"{provenance_path.name}: {field} must be non-empty")
        received_blocks = data.get("received_blocks")
        if received_blocks != ["operational prompt"]:
            errors.append(
                f"{provenance_path.name}: received_blocks must exactly equal "
                "['operational prompt']"
            )
        opened_inputs = data.get("opened_inputs")
        if isinstance(opened_inputs, list):
            if (
                any(not isinstance(value, str) for value in opened_inputs)
                or len(opened_inputs) != len(set(
                    value for value in opened_inputs if isinstance(value, str)
                ))
                or any(value not in helper_allowed_opened for value in opened_inputs)
                or opened_inputs != [
                    value for value in helper_allowed_opened if value in opened_inputs
                ]
            ):
                errors.append(
                    f"{provenance_path.name}: opened_inputs must be a duplicate-free "
                    "canonical-order subset of the PDF/packet allowlist"
                )
        recipient_stages = data.get("recipient_stages")
        if isinstance(recipient_stages, list) and (
            any(not isinstance(value, str) for value in recipient_stages)
            or len(recipient_stages) != len(set(
                value for value in recipient_stages if isinstance(value, str)
            ))
            or any(value not in allowed_recipients for value in recipient_stages)
        ):
            errors.append(
                f"{provenance_path.name}: recipient_stages contains a duplicate "
                "or non-current substantive stage"
            )
        if (
            received_blocks == ["operational prompt"]
            and isinstance(opened_inputs, list)
            and all(isinstance(value, str) for value in opened_inputs)
        ):
            expected_receipt = (
                "received=[operational prompt]; opened=["
                + "; ".join(opened_inputs)
                + "]; no unlisted substantive assertion was received; no prohibited "
                "context/artifact was used; neighboring paths were not enumerated"
            )
            if data.get("input_receipt_access_declaration") != expected_receipt:
                errors.append(
                    f"{provenance_path.name}: input_receipt_access_declaration must "
                    "exactly project received_blocks/opened_inputs and the canonical "
                    "clean-access declarations"
                )
        prompt_hash = str(data.get("prompt_sha256") or "").upper()
        if not HEX64_RE.fullmatch(prompt_hash):
            errors.append(f"{provenance_path.name}: prompt_sha256 is not 64 hex")
        elif prompt_hash in process_prompt_hashes or prompt_hash in helper_prompt_hashes:
            errors.append(
                f"{provenance_path.name}: prompt_sha256 must be unique to this helper"
            )
        else:
            helper_prompt_hashes.add(prompt_hash)
        for field in ("pdf_sha256_start", "pdf_sha256_end"):
            if str(data.get(field) or "").upper() != expected_pdf_hash:
                errors.append(f"{provenance_path.name}: {field} does not match frozen PDF")
        outputs = data.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            errors.append(f"{provenance_path.name}: outputs must be a non-empty array")
            continue
        for index, output in enumerate(outputs):
            if not isinstance(output, dict) or set(output) != HELPER_OUTPUT_KEYS:
                errors.append(
                    f"{provenance_path.name}: outputs[{index}] must contain exactly file,sha256"
                )
                continue
            filename = str(output.get("file") or "")
            if (
                not is_neutral_portable_basename(filename)
                or portable_basename_key(filename).endswith("-provenance.json")
            ):
                errors.append(
                    f"{provenance_path.name}: outputs[{index}].file must be a neutral sidecar basename"
                )
                continue
            registered[filename] += 1
            filename_key = portable_basename_key(filename)
            prior_spelling = registered_portable_names.get(filename_key)
            if prior_spelling is not None:
                errors.append(
                    f"{provenance_path.name}: helper output {filename!r} "
                    f"duplicates portable basename {prior_spelling!r}"
                )
            else:
                registered_portable_names[filename_key] = filename
            output_path = helpers / filename
            declared_hash = str(output.get("sha256") or "").upper()
            if not output_path.is_file():
                errors.append(f"{provenance_path.name}: missing helper output {filename}")
            elif not HEX64_RE.fullmatch(declared_hash):
                errors.append(f"{provenance_path.name}: invalid hash for {filename}")
            elif sha256(output_path) != declared_hash:
                errors.append(f"{provenance_path.name}: hash mismatch for {filename}")
    non_provenance = {
        path.name for path in files
        if not re.fullmatch(r"H\d{2}-provenance\.json", path.name)
    }
    if non_provenance and not provenance_files:
        errors.append("helpers: sidecars exist without any Hxx-provenance.json")
    for filename in sorted(non_provenance):
        count = registered.get(filename, 0)
        if count != 1:
            errors.append(
                f"helpers: {filename} must be registered exactly once; observed {count}"
            )
    for filename, count in sorted(registered.items()):
        if filename not in non_provenance:
            errors.append(f"helpers: registered output is absent: {filename}")
        if count > 1:
            errors.append(f"helpers: {filename} is multiply registered ({count})")


def manifest_process_projection(process: dict[str, Any]) -> dict[str, str]:
    """Build the canonical neutral process fields copied into the manifest."""

    def neutral(value: Any) -> str:
        return "null" if value is None else str(value)

    governing_sources = sorted(process_governing_sources(process))
    return {
        "Degree/institution/discipline": " ; ".join((
            f"degree_level={neutral(process.get('degree_level'))}",
            f"degree_type={neutral(process.get('degree_type'))}",
            f"institution={neutral(process.get('institution'))}",
            f"school_or_department={neutral(process.get('school_or_department'))}",
            f"discipline={neutral(process.get('discipline'))}",
            f"expected_submission_year={neutral(process.get('expected_submission_year'))}",
        )),
        "Review round and purpose": " ; ".join((
            f"round_id={neutral(process.get('round_id'))}",
            f"retry_id={neutral(process.get('retry_id'))}",
            f"review_mode={neutral(process.get('review_mode'))}",
            f"artifact_type={neutral(process.get('artifact_type'))}",
            f"output_language={neutral(process.get('output_language'))}",
        )),
        "Frozen PDF path, SHA-256, frozen_at timestamp, and pages": " ; ".join((
            f"file={neutral(process.get('frozen_pdf_file'))}",
            f"sha256={neutral(process.get('selected_pdf_sha256')).upper()}",
            f"frozen_at={neutral(process.get('frozen_at'))}",
            f"pages={neutral(process.get('physical_page_count'))}",
        )),
        "Governing template/rules": " ; ".join((
            "template=thesis-review/SKILL.md",
            f"decision_regime_status={neutral(process.get('decision_regime_status'))}",
            "sources=" + (" | ".join(governing_sources) if governing_sources else "none"),
        )),
    }


def validate_manifest(
    path: Path,
    expected_pdf_hash: str,
    process: dict[str, Any],
    citation_candidates: list[dict[str, str]],
    extracted_unmatched_glyphs: list[dict[str, Any]],
    root: Path,
    reviewer_count: int,
    errors: list[str],
) -> None:
    """Validate the packet-builder's closed, neutral Stage-P manifest."""

    text = validate_declarations(
        path, expected_pdf_hash, errors,
        process=process, actor_id="P", reviewer_count=reviewer_count,
        allowed_public_endpoints={
            value for value in process.get("governing_rule_urls", [])
            if isinstance(value, str)
        },
        required_public_endpoints={
            value for value in process.get("governing_rule_urls", [])
            if isinstance(value, str)
        },
    )
    if not text:
        return
    required_headings = (
        "Thesis structure",
        "Thesis-stated questions and contributions — neutral navigation only",
        "Objective inventories and locations",
    )
    visible_heading_rows: list[tuple[int, str]] = []
    for match in re.finditer(r"(?im)^[ ]{0,3}(#{1,2})[ \t]+(.+?)[ \t]*$", text):
        heading_text = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        visible_heading_rows.append((len(match.group(1)), heading_text))
    expected_heading_rows = [
        (1, "Frozen evidence manifest"),
        *((2, heading) for heading in required_headings),
    ]
    if visible_heading_rows != expected_heading_rows:
        errors.append(
            f"{path.name}: H1/H2 structure must exactly equal the canonical "
            "manifest sequence"
        )
    first_h2 = re.search(r"(?im)^[ ]{0,3}##[ \t]+", text)
    title = re.search(
        r"(?im)^[ ]{0,3}#[ \t]+Frozen evidence manifest"
        r"(?:[ \t]+#+)?[ \t]*$",
        text,
    )
    if title is None:
        errors.append(f"{path.name}: missing canonical manifest H1")
        identity_section = ""
    else:
        identity_section = text[
            title.end():(first_h2.start() if first_h2 is not None else len(text))
        ].strip()
    identity_labels = re.findall(
        r"(?im)^[ ]{0,3}-[ \t]+([^:\r\n]+?)[ \t]*:", identity_section
    )
    expected_identity_labels = [
        "Process-parameter file and SHA-256",
        "Actor ID",
        "Review round ID",
        "Review retry ID",
        "Packet-builder fresh-context declaration",
        "Packet-builder input-receipt/access declaration",
        "Operational prompt SHA-256",
        "Frozen PDF SHA-256 at start and end",
        "Frozen at",
        "Degree/institution/discipline",
        "Review round and purpose",
        "Frozen PDF path, SHA-256, frozen_at timestamp, and pages",
        "Governing template/rules",
        "Reviewer-visible artifact",
        "Permitted public citation-verification sources",
        "Prohibited context and artifacts",
        "Items explicitly out of scope",
    ]
    if identity_labels != expected_identity_labels or any(
        line.strip() and not re.match(r"^[ ]{0,3}-[ \t]+", line)
        for line in identity_section.splitlines()
    ):
        errors.append(
            f"{path.name}: manifest identity block must contain only the "
            "seventeen canonical single-line fields in order"
        )
    process_path = root / "00-process-parameters.json"
    process_identity = labeled_value(
        identity_section, "Process-parameter file and SHA-256"
    ) or ""
    expected_process_identity = (
        f"00-process-parameters.json / {sha256(process_path)}"
        if process_path.is_file() else ""
    )
    if process_identity != expected_process_identity:
        errors.append(
            f"{path.name}: Process-parameter file and SHA-256 must exactly bind "
            "00-process-parameters.json"
        )
    frozen_at = labeled_value(identity_section, "Frozen at")
    if frozen_at != str(process.get("frozen_at", "")):
        errors.append(
            f"{path.name}: Frozen at must exactly equal process-envelope frozen_at"
        )
    for label, expected_value in manifest_process_projection(process).items():
        if labeled_value(identity_section, label) != expected_value:
            errors.append(
                f"{path.name}: {label} must exactly project the process envelope"
            )
    frozen_name = str(process.get("frozen_pdf_file", ""))
    expected_artifact = f"exactly one frozen thesis PDF: {frozen_name}"
    if labeled_value(identity_section, "Reviewer-visible artifact") != expected_artifact:
        errors.append(
            f"{path.name}: Reviewer-visible artifact must equal "
            f"{expected_artifact!r}"
        )
    permitted = labeled_value(
        identity_section, "Permitted public citation-verification sources"
    ) or ""
    if (
        len(permitted) < 20
        or is_placeholder(permitted)
        or not re.search(r"(?i)(?:authoritative|official|publisher|doi)", permitted)
    ):
        errors.append(
            f"{path.name}: permitted public citation sources are absent or shell-only"
        )
    prohibited = (
        labeled_value(identity_section, "Prohibited context and artifacts") or ""
    ).casefold()
    for required_term in (
        "conversation", "earlier assistant", "thesis source", ".bib",
        "git history", "sibling repositories", "old rounds", "author-side",
    ):
        if required_term not in prohibited:
            errors.append(
                f"{path.name}: prohibited-context field omits {required_term!r}"
            )
    out_of_scope = labeled_value(identity_section, "Items explicitly out of scope") or ""
    if len(out_of_scope) < 20 or is_placeholder(out_of_scope):
        errors.append(f"{path.name}: Items explicitly out of scope is shell-only")
    for heading in required_headings:
        body = markdown_section_body(text, heading) or ""
        if len(body) < 20 or is_placeholder(body):
            errors.append(f"{path.name}: section {heading!r} is empty or shell-only")
    for heading in required_headings[:2]:
        body = markdown_section_body(text, heading) or ""
        if parse_physical_page_locator(body) is None:
            errors.append(
                f"{path.name}: section {heading!r} requires a neutral physical-page anchor"
            )
    objective_section = markdown_section_body_raw(
        text, "Objective inventories and locations"
    ) or ""
    for required_name in (
        "00-page-inventory.csv", "00-bibliography-inventory.csv",
        "00-citation-candidate-ledger.csv", "00-citation-inventory.csv",
        "00-unmatched-bracket-ledger.csv",
    ):
        if required_name not in objective_section:
            errors.append(
                f"{path.name}: objective inventory section omits {required_name}"
            )
    manifest_counts = {
        "Numeric-bracket candidate rows": len(citation_candidates),
        "Citation-classified candidate rows": sum(
            row["Classification"].strip().casefold() == "citation"
            for row in citation_candidates
        ),
        "Non-citation-classified candidate rows": sum(
            row["Classification"].strip().casefold() == "non-citation"
            for row in citation_candidates
        ),
        "Unmatched square-bracket glyphs": len(extracted_unmatched_glyphs),
    }
    for label, expected_count in manifest_counts.items():
        observed = parse_count_label(objective_section, label, path.name, errors)
        if observed is not None and observed != expected_count:
            errors.append(
                f"{path.name}: {label} {observed} != validated {expected_count}"
            )
    unmatched_disposition = labeled_value(
        objective_section, "Unmatched glyph dispositions"
    )
    if (
        not unmatched_disposition
        or len(unmatched_disposition) < 12
        or is_placeholder(unmatched_disposition)
    ):
        errors.append(
            f"{path.name}: Unmatched glyph dispositions must record a concrete "
            "rendered-context audit result"
        )
    elif not extracted_unmatched_glyphs:
        if not re.search(r"(?i)(?:\bnone\b|no unmatched|\b0\b)", unmatched_disposition):
            errors.append(
                f"{path.name}: zero unmatched glyphs require an explicit none-found disposition"
            )
    elif (
        re.search(r"(?i)(?:\bnone\b|no unmatched|none found|\bzero\b)", unmatched_disposition)
        or "00-unmatched-bracket-ledger.csv" not in unmatched_disposition
        or not re.search(
            rf"(?<!\d){len(extracted_unmatched_glyphs)}(?!\d)",
            unmatched_disposition,
        )
    ):
        errors.append(
            f"{path.name}: positive unmatched-glyph count requires its exact count "
            "and 00-unmatched-bracket-ledger.csv"
        )


def validate_process(
    root: Path,
    errors: list[str],
    *,
    enforce_single_reviewer_pdf: bool = True,
    validate_governing_file_bytes: bool = True,
    validate_frozen_pdf_bytes: bool = True,
    stage_v_present_override: bool | None = None,
    process_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path, str, int, int, list[tuple[float, float]]]:
    if process_override is None:
        process_path = root / "00-process-parameters.json"
        try:
            process = json.loads(process_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read 00-process-parameters.json: {exc}")
            return {}, root / "__missing__.pdf", "", 0, 0, []
    else:
        # Scoped gates preflight exact paths from this same frozen parse.  Reuse
        # it so a second read cannot select a different PDF/governing allowlist.
        process = process_override
    if not isinstance(process, dict):
        errors.append("00-process-parameters.json root must be an object")
        return {}, root / "__missing__.pdf", "", 0, 0, []
    keys = set(process)
    if keys != PROCESS_KEYS:
        errors.append(
            "process envelope schema mismatch; "
            f"missing={sorted(PROCESS_KEYS-keys)}, extra={sorted(keys-PROCESS_KEYS)}"
        )
    for key in ("round_id", "retry_id", "output_language"):
        value = process.get(key)
        if not isinstance(value, str) or not value.strip() or is_placeholder(value):
            errors.append(f"process envelope has invalid/blank {key}")
    enum_contracts = {
        "degree_type": {"academic", "professional", None},
        "artifact_type": {"author-copy", "blind-copy", "unknown"},
        "review_mode": {"initial", "fresh-rereview"},
        "output_language": {"zh-CN"},
    }
    for key, allowed in enum_contracts.items():
        value = process.get(key)
        if value not in allowed:
            errors.append(
                f"process envelope {key} must be one of "
                f"{sorted(str(item) for item in allowed)}"
            )
    for key in ("institution", "school_or_department", "discipline"):
        value = process.get(key)
        if value is not None and (
            not isinstance(value, str) or not value.strip() or is_placeholder(value)
        ):
            errors.append(f"process envelope {key} must be a nonblank string or null")
    year = process.get("expected_submission_year")
    if year is not None and (
        not isinstance(year, int) or isinstance(year, bool) or year < 1900 or year > 2200
    ):
        errors.append(
            "process envelope expected_submission_year must be a four-digit year or null"
        )
    regime_status = str(process.get("decision_regime_status") or "").casefold()
    if regime_status not in {
        "verified-institutional", "skill-default", "undetermined"
    }:
        errors.append(
            "decision_regime_status must be verified-institutional, "
            "skill-default, or undetermined"
        )
    elif regime_status == "undetermined":
        errors.append(
            "a complete review bundle cannot use an undetermined decision regime"
        )
    frozen_at = process.get("frozen_at")
    if not isinstance(frozen_at, str) or not frozen_at.strip():
        errors.append("process envelope has invalid/blank frozen_at")
    else:
        try:
            parsed_frozen_at = datetime.fromisoformat(
                frozen_at.strip().replace("Z", "+00:00")
            )
            if parsed_frozen_at.tzinfo is None:
                errors.append("frozen_at must include an explicit timezone")
        except ValueError:
            errors.append("frozen_at must be an ISO-8601 datetime with timezone")
    local_files = process.get("governing_local_files")
    if not isinstance(local_files, list):
        errors.append("governing_local_files must be a list")
    else:
        seen_local_files: set[str] = set()
        for index, item in enumerate(local_files):
            if not isinstance(item, dict):
                errors.append(f"governing_local_files[{index}] must be an object")
                continue
            if set(item) != {"neutral_file", "official_title", "sha256"}:
                errors.append(
                    f"governing_local_files[{index}] must contain exactly "
                    "neutral_file,official_title,sha256"
                )
            filename = str(item.get("neutral_file") or "")
            if not is_neutral_portable_basename(filename):
                errors.append(
                    f"governing_local_files[{index}].neutral_file must be a neutral "
                    "portable basename without filesystem aliases"
                )
                continue
            filename_key = portable_basename_key(filename)
            if (
                filename_key in RESERVED_ROUND_BASENAME_KEYS
                or RENDER_ARTIFACT_BASENAME_RE.fullmatch(filename)
            ):
                errors.append(
                    f"governing_local_files[{index}].neutral_file {filename!r} "
                    "collides with a reserved skill/round basename"
                )
            if filename_key in seen_local_files:
                errors.append(
                    f"duplicate governing_local_files neutral_file {filename!r}"
                )
            seen_local_files.add(filename_key)
            rule_path = root / filename
            declared = str(item.get("sha256") or "").upper()
            if validate_governing_file_bytes:
                if not rule_path.is_file():
                    errors.append(f"missing neutral governing file: {filename}")
                elif not HEX64_RE.fullmatch(declared) or sha256(rule_path) != declared:
                    errors.append(f"neutral governing file hash mismatch: {filename}")
            elif not HEX64_RE.fullmatch(declared):
                errors.append(
                    f"governing_local_files[{index}].sha256 must be 64 "
                    "hexadecimal characters"
                )
            title = item.get("official_title")
            if not isinstance(title, str) or not title.strip():
                errors.append(f"governing_local_files[{index}].official_title is blank")
    rule_urls = process.get("governing_rule_urls")
    if not isinstance(rule_urls, list):
        errors.append("governing_rule_urls must be a list")
    else:
        seen_urls: set[str] = set()
        for index, value in enumerate(rule_urls):
            if (
                not isinstance(value, str)
                or PUBLIC_URL_RE.fullmatch(value.strip()) is None
            ):
                errors.append(
                    f"governing_rule_urls[{index}] must be one nonblank http(s) URL"
                )
                continue
            normalized = value.strip()
            if normalized in seen_urls:
                errors.append(f"duplicate governing_rule_urls entry {normalized!r}")
            seen_urls.add(normalized)
    if regime_status == "verified-institutional" and not (
        isinstance(rule_urls, list)
        and rule_urls
    ) and not (isinstance(local_files, list) and local_files):
        errors.append(
            "verified-institutional decision regime requires at least one "
            "frozen official URL or local governing file"
        )
    frozen_name = str(process.get("frozen_pdf_file") or "")
    if not is_neutral_portable_basename(frozen_name):
        errors.append(
            "frozen_pdf_file must be one neutral portable basename without "
            "filesystem aliases"
        )
        frozen_path = root / "__missing__.pdf"
    else:
        frozen_path = root / frozen_name
    governing_basenames = {
        portable_basename_key(str(item.get("neutral_file")))
        for item in (local_files if isinstance(local_files, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("neutral_file"), str)
    }
    frozen_name_key = portable_basename_key(frozen_name)
    if (
        frozen_name_key in RESERVED_ROUND_BASENAME_KEYS
        or RENDER_ARTIFACT_BASENAME_RE.fullmatch(frozen_name)
    ):
        errors.append(
            f"frozen_pdf_file {frozen_name!r} collides with a reserved "
            "skill/round basename"
        )
    if frozen_name and frozen_name_key in governing_basenames:
        errors.append(
            f"frozen_pdf_file {frozen_name!r} collides with a governing local file"
        )
    if enforce_single_reviewer_pdf:
        reviewer_visible_pdfs = sorted(
            path.name for path in root.iterdir()
            if path.is_file()
            and path.suffix.casefold() == ".pdf"
            and portable_basename_key(path.name) not in governing_basenames
        )
        if reviewer_visible_pdfs != [frozen_name]:
            errors.append(
                "round directory must contain exactly the one process-selected "
                f"reviewer-visible thesis PDF; observed={reviewer_visible_pdfs}"
            )
    elif frozen_name and Path(frozen_name).suffix.casefold() != ".pdf":
        errors.append("frozen_pdf_file must name the process-selected PDF")
    expected_hash = str(process.get("selected_pdf_sha256") or "").upper()
    if not HEX64_RE.fullmatch(expected_hash):
        errors.append("selected_pdf_sha256 must be 64 hexadecimal characters")
    if validate_frozen_pdf_bytes:
        if not frozen_path.is_file():
            errors.append(f"missing frozen PDF: {frozen_name or '<unspecified>'}")
        elif HEX64_RE.fullmatch(expected_hash):
            actual = sha256(frozen_path)
            if actual != expected_hash:
                errors.append(
                    f"frozen PDF hash mismatch: expected {expected_hash}, got {actual}"
                )
    page_count_raw = process.get("physical_page_count")
    if (
        not isinstance(page_count_raw, int)
        or isinstance(page_count_raw, bool)
        or page_count_raw < 1
    ):
        errors.append("physical_page_count must be a positive integer")
        page_count = 0
    else:
        page_count = page_count_raw
    pdf_page_sizes = []
    if validate_frozen_pdf_bytes and frozen_path.is_file():
        pdf_page_sizes = validate_pdf_structure_and_pages(
            frozen_path, page_count, errors
        )
    degree_value = process.get("degree_level")
    degree = degree_value if isinstance(degree_value, str) else ""
    if degree not in {"doctorate", "masters"}:
        errors.append("degree_level must be doctorate or masters for a complete panel")
        reviewer_count = 0
    else:
        reviewer_count = 5 if degree == "doctorate" else 3
    prompt_map = process.get("actor_prompt_sha256")
    expected_prompt_actors = {
        "P", "AI", "C", "S",
        *(f"R{index}" for index in range(1, reviewer_count + 1)),
    }
    if not isinstance(prompt_map, dict):
        errors.append("actor_prompt_sha256 must be an object")
    else:
        observed_prompt_actors = set(prompt_map)
        stage_v_present = (
            (root / "94-post-freeze-prior-issue-closure.md").is_file()
            if stage_v_present_override is None
            else stage_v_present_override
        )
        required_prompt_actors = (
            expected_prompt_actors | {"V"} if stage_v_present
            else expected_prompt_actors
        )
        if observed_prompt_actors != required_prompt_actors:
            errors.append(
                "actor_prompt_sha256 actor set mismatch; "
                f"missing={sorted(required_prompt_actors-observed_prompt_actors)}, "
                f"extra={sorted(observed_prompt_actors-required_prompt_actors)}"
            )
        prompt_values: list[str] = []
        for actor, value in prompt_map.items():
            if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
                errors.append(
                    f"actor_prompt_sha256[{actor!r}] must be exactly 64 hexadecimal characters"
                )
            else:
                prompt_values.append(value.upper())
        if len(prompt_values) != len(set(prompt_values)):
            errors.append("actor_prompt_sha256 values must be unique across actors")
    return (
        process, frozen_path, expected_hash, page_count, reviewer_count,
        pdf_page_sizes,
    )


def validate_rows_mandatory(
    rows: list[dict[str, str]],
    filename: str,
    mandatory_fields: Iterable[str],
    errors: list[str],
    *,
    blank_allowed: set[str] | None = None,
) -> None:
    allowed = blank_allowed or set()
    for line, row in enumerate(rows, start=2):
        for field in mandatory_fields:
            require_value(
                row, field, f"{filename}:{line}", errors,
                allow_blank=field in allowed,
            )


def validate_reference_ids_only_in_id_column(
    rows: list[dict[str, str]], filename: str, errors: list[str]
) -> None:
    """Keep canonical REFnnnn tokens exclusively in the ReferenceID column."""

    token_re = re.compile(r"(?<![A-Za-z0-9])REF\d{4}(?![A-Za-z0-9])")
    for line, row in enumerate(rows, start=2):
        for field, value in row.items():
            if field != "ReferenceID" and token_re.search(value or ""):
                errors.append(
                    f"{filename}:{line}: REFnnnn tokens are allowed only in the "
                    f"ReferenceID column; found one in {field}"
                )


def page_layout_finding_ids(
    page_ledger: list[dict[str, str]],
) -> set[str]:
    """Return distinct finding IDs from exact final page-disposition values."""

    result: set[str] = set()
    for row in page_ledger:
        match = re.fullmatch(
            r"(?i)finding[ \t]+([A-Z][A-Z0-9]*-F\d{2,4})",
            row.get("Disposition", "").strip(),
        )
        if match is not None:
            result.add(match.group(1).upper())
    return result


def build_owner_expected_vectors(
    page_inventory: list[dict[str, str]],
    page_ledger: list[dict[str, str]],
    bibliography_inventory: list[dict[str, str]],
    bibliography_ledger: list[dict[str, str]],
    citation_inventory: list[dict[str, str]],
    citation_ledger: list[dict[str, str]],
) -> dict[str, dict[str, tuple[int, ...] | tuple[str, ...]]]:
    """Derive every owner-report count from its authoritative CSV rows."""
    suspect_pages = 0
    unresolved_pages = 0
    actionable_layout_finding_ids = page_layout_finding_ids(page_ledger)
    page_inventory_by_id = {
        row.get("PageID", ""): row for row in page_inventory
    }
    for row in page_ledger:
        signals = row.get("Signals", "").casefold()
        mechanical = page_inventory_by_id.get(row.get("PageID", ""), {}).get(
            "MechanicalSignals", ""
        ).casefold()
        if any(
            value and value not in NON_SIGNAL_VALUES
            for value in (signals, mechanical)
        ):
            suspect_pages += 1
        if any(
            token in row.get("Disposition", "").casefold()
            for token in ("pending", "unchecked", "recheck", "open", "unresolved")
        ):
            unresolved_pages += 1

    def bib_counts(fields: tuple[str, ...], include_na: bool) -> tuple[int, ...]:
        rows = [row for row in bibliography_ledger if row.get("Field") in fields]
        counts = Counter(row.get("Verdict", "").casefold() for row in rows)
        values = [counts["exact"], counts["mismatch"]]
        if include_na:
            values.append(counts["legitimate n/a"])
        values.append(counts["unverifiable"])
        return tuple(values)

    identity_fields = {
        "title", "ordered_authors", "year", "venue", "publication_status",
        "doi", "arxiv_id", "arxiv_version", "url",
        "isbn_or_other_persistent_id", "existence",
    }
    rows_by_ref: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in bibliography_ledger:
        rows_by_ref[row.get("ReferenceID", "")].append(row)
    metadata_verified_entries = sum(
        all(
            row.get("Verdict", "").casefold() not in {"mismatch", "unverifiable"}
            for row in rows if row.get("Field") in identity_fields
        )
        for ref, rows in rows_by_ref.items() if ref
    )
    existence_mismatches = [
        row for row in bibliography_ledger
        if row.get("Field") == "existence"
        and row.get("Verdict", "").casefold() == "mismatch"
    ]
    unresolved_existence = sum(
        not re.search(
            r"(?i)\b(?:closed|resolved|not required|no finding|n/a)\b",
            row.get("FindingDisposition", ""),
        )
        for row in existence_mismatches
    )
    support_counts = Counter(
        row.get("Support", "").casefold() for row in citation_ledger
    )
    unique_occurrences = {
        row.get("OccurrenceID", "") for row in citation_inventory
        if row.get("OccurrenceID")
    }
    unique_cited_refs = {
        row.get("ReferenceID", "") for row in citation_ledger
        if row.get("ReferenceID")
    }
    return {
        "Full rendered-page audit": {
            "Physical pages / unchecked pages": (
                len(page_ledger), unresolved_pages,
            ),
            "Suspect-page signals / resolved / unresolved": (
                suspect_pages, suspect_pages - unresolved_pages, unresolved_pages,
            ),
            # The page ledger is authoritative. Gate I also covers equations,
            # citations, and references, so Gate-I report findings cannot be
            # treated as layout findings unless a page disposition links them.
            "Actionable layout findings": (
                len(actionable_layout_finding_ids),
            ),
            "Actionable layout finding IDs": tuple(
                sorted(actionable_layout_finding_ids)
            ),
        },
        "Full bibliography-integrity audit": {
            "Bibliography entries rendered in the frozen PDF": (
                len(bibliography_inventory),
            ),
            "Bibliography master rows / unchecked rows": (
                len(bibliography_ledger), 0,
            ),
            "Title fields verified / mismatched / unverifiable": bib_counts(("title",), False),
            "Ordered-author fields verified / mismatched / unverifiable": bib_counts(("ordered_authors",), False),
            "Year fields verified / mismatched / unverifiable": bib_counts(("year",), False),
            "Venue fields verified / mismatched / unverifiable": bib_counts(("venue",), False),
            "Publication/acceptance-status fields verified / mismatched / unverifiable": bib_counts(("publication_status",), False),
            "Volume/issue fields verified / mismatched / legitimate N/A / unverifiable": bib_counts(("volume", "issue"), True),
            "Page-range or article-number fields verified / mismatched / legitimate N/A / unverifiable": bib_counts(("pages_or_article_number",), True),
            "DOI/arXiv/version/URL/access-date fields verified / mismatched / legitimate N/A / unverifiable": bib_counts(("doi", "arxiv_id", "arxiv_version", "url", "access_date"), True),
            "ISBN/other-persistent-ID fields verified / mismatched / legitimate N/A / unverifiable": bib_counts(("isbn_or_other_persistent_id",), True),
            "Retraction/withdrawal/correction/superseding-status fields verified / mismatched / legitimate N/A / unverifiable": bib_counts(("retraction_withdrawal_correction_superseding",), True),
            "Suspected fabricated/nonexistent entries and adjudication status": (
                len(existence_mismatches), unresolved_existence,
            ),
            "Metadata/status verified entries": (metadata_verified_entries,),
        },
        "Full citation-claim audit": {
            "Active citation occurrences": (len(unique_occurrences),),
            "Citation--source pairs": (len(citation_ledger),),
            "Unique cited keys": (len(unique_cited_refs),),
            "Semantically verified pairs": (
                support_counts["direct"] + support_counts["not-needed"],
            ),
            "Partial-support pairs": (support_counts["partial"],),
            "Context-only pairs": (support_counts["context-only"],),
            "Mismatch pairs": (support_counts["mismatch"],),
            "Inaccessible/unverifiable pairs": (support_counts["unverifiable"],),
            "Ledger rows and unchecked rows": (len(citation_ledger), 0),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("round_directory", type=Path)
    parser.add_argument("--write-report", type=Path)
    parser.add_argument(
        "--pre-stage-s",
        action="store_true",
        help=(
            "validate the frozen Stage-C bundle before Stage S exists; the "
            "three Stage-S outputs are forbidden and only their validations "
            "are omitted"
        ),
    )
    args = parser.parse_args(argv)
    if args.pre_stage_s and args.write_report is not None:
        parser.error("--write-report is forbidden with --pre-stage-s")
    root = args.round_directory.absolute()
    errors: list[str] = []
    warnings: list[str] = []
    validation_report_path: Path | None = None
    if args.write_report:
        validation_report_path = validate_write_report_destination(
            root, args.write_report.absolute(), errors
        )
        if validation_report_path is None:
            report = "\n".join([
                "# Mechanical thesis-review bundle validation", "",
                "- Result: **FAIL**",
                f"- Round directory: {root}",
                "- Frozen PDF SHA-256: not opened (invalid report destination)",
                f"- Errors: {len(errors)}", "- Warnings: 0",
                "- Boundary: validation did not mutate the round.",
                "", "## Errors", "", *(f"- {item}" for item in errors),
                "", "## Warnings", "", "- none", "",
            ])
            print(report)
            return 1
    if not preflight_reparse_boundary(root, errors):
        report = "\n".join([
            "# Mechanical thesis-review bundle validation", "",
            "- Result: **FAIL**",
            f"- Round directory: {root}",
            "- Frozen PDF SHA-256: not opened (boundary preflight failed)",
            f"- Errors: {len(errors)}",
            "- Warnings: 0",
            "- Boundary: no round artifact was opened after the unsafe "
            "filesystem alias was detected.",
            "", "## Errors", "",
            *(f"- {item}" for item in errors),
            "", "## Warnings", "", "- none", "",
        ])
        print(report)
        return 1
    process, frozen_path, expected_hash, page_count, reviewer_count, pdf_page_sizes = (
        validate_process(root, errors)
    )
    required_files = {
        "00-manifest.md", "00-page-inventory.csv",
        "00-bibliography-inventory.csv", "00-citation-candidate-ledger.csv",
        "00-unmatched-bracket-ledger.csv", "00-citation-inventory.csv",
        "01-policy-basis.md", "02-page-layout-ledger.md",
        "02-page-layout-ledger.csv", "03-bibliography-audit-ledger.md",
        "03-bibliography-audit-ledger.csv",
        "04-citation-claim-audit-ledger.md",
        "04-citation-claim-audit-ledger.csv",
        "05-ai-style-assessment.md", "90-chair-synthesis.md",
        "91-revision-ledger.md", "91-revision-ledger.csv",
        "91-ai-actionable-ledger.csv", "92-new-evidence-or-experiments.md",
        "92-new-evidence-or-experiments.csv",
    }
    if not args.pre_stage_s:
        required_files.update({
            "93-user-facing-summary.md", "93-current-actionable-items.csv",
            "93-current-ai-actionable-items.csv",
        })
    required_files.update(
        f"R{i}-comprehensive-review.md" for i in range(1, reviewer_count + 1)
    )
    for filename in sorted(required_files):
        if not (root / filename).is_file():
            errors.append(f"missing required file: {filename}")
    governing_root_files = {
        str(item.get("neutral_file"))
        for item in process.get("governing_local_files", [])
        if isinstance(item, dict) and item.get("neutral_file")
    }
    optional_stage_v = "94-post-freeze-prior-issue-closure.md"
    allowed_root_files = {
        "00-process-parameters.json", str(process.get("frozen_pdf_file", "")),
        *required_files, *governing_root_files,
    }
    if not args.pre_stage_s:
        allowed_root_files.add("95-bundle-validation.md")
    if not args.pre_stage_s and (root / optional_stage_v).is_file():
        allowed_root_files.add(optional_stage_v)
    allowed_root_directories = {"page-renders", "helpers"}
    if not args.pre_stage_s and (root / optional_stage_v).is_file():
        allowed_root_directories.add("stage-v-inputs")
    unexpected_root_files: list[str] = []
    unexpected_root_directories: list[str] = []
    invalid_root_entries: list[str] = []
    try:
        root_entries = list(root.iterdir())
    except OSError as exc:
        errors.append(f"cannot enumerate closed round root: {exc}")
        root_entries = []
    for entry in root_entries:
        if is_link_or_reparse(entry):
            invalid_root_entries.append(entry.name)
        elif entry.is_file() and entry.name not in allowed_root_files:
            unexpected_root_files.append(entry.name)
        elif entry.is_dir() and entry.name not in allowed_root_directories:
            unexpected_root_directories.append(entry.name)
        elif not entry.is_file() and not entry.is_dir():
            invalid_root_entries.append(entry.name)
    if unexpected_root_files:
        errors.append(
            "closed current-round root contains unallowlisted file(s): "
            f"{sorted(unexpected_root_files)}"
        )
    if unexpected_root_directories:
        errors.append(
            "closed current-round root contains unallowlisted directories: "
            f"{sorted(unexpected_root_directories)}"
        )
    if invalid_root_entries:
        errors.append(
            "closed current-round root contains symlink/special entries: "
            f"{sorted(invalid_root_entries)}"
        )

    page_inventory = read_csv(
        root / "00-page-inventory.csv", PAGE_INVENTORY_COLUMNS, errors,
        require_rows=True,
    )
    page_ledger = read_csv(
        root / "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS, errors,
        require_rows=True,
    )
    validate_rows_mandatory(
        page_inventory, "00-page-inventory.csv", PAGE_INVENTORY_COLUMNS,
        errors, blank_allowed={"PrintedPage"},
    )
    validate_rows_mandatory(
        page_ledger, "02-page-layout-ledger.csv", PAGE_LEDGER_COLUMNS,
        errors, blank_allowed={"PrintedPage"},
    )
    validate_pdf_hash(page_inventory, "00-page-inventory.csv", expected_hash, errors)
    validate_pdf_hash(page_ledger, "02-page-layout-ledger.csv", expected_hash, errors)
    page_inv_by_id = index_unique(
        page_inventory, "PageID", "00-page-inventory.csv", errors
    )
    page_led_by_id = index_unique(
        page_ledger, "PageID", "02-page-layout-ledger.csv", errors
    )
    compare_sets("page ledger", set(page_inv_by_id), set(page_led_by_id), errors)
    for index, row in enumerate(page_inventory, start=1):
        expected_page_id = f"P{index:04d}"
        if row["PageID"] != expected_page_id:
            errors.append(
                "00-page-inventory.csv: PageID sequence mismatch at row "
                f"{index + 1}; expected {expected_page_id}, got {row['PageID']!r}"
            )
    if page_count and len(page_inventory) != page_count:
        errors.append(
            f"00-page-inventory.csv: row count {len(page_inventory)} "
            f"!= physical_page_count {page_count}"
        )
    if page_count and len(page_ledger) != page_count:
        errors.append(
            f"02-page-layout-ledger.csv: row count {len(page_ledger)} "
            f"!= physical_page_count {page_count}"
        )
    physical_inventory: list[int] = []
    physical_ledger: list[int] = []
    render_dir = root / "page-renders"
    if is_link_or_reparse(render_dir) or not render_dir.is_dir():
        errors.append("missing required page-renders directory")
        render_files: dict[str, Path] = {}
    else:
        render_files = {
            path.stem: path for path in render_dir.glob("*.png")
            if path.is_file() and not is_link_or_reparse(path)
        }
        unexpected = sorted(
            path.name for path in render_dir.iterdir()
            if (
                is_link_or_reparse(path)
                or not path.is_file()
                or path.suffix.casefold() != ".png"
            )
        )
        if unexpected:
            errors.append(f"page-renders: unexpected entries {unexpected}")
    compare_sets(
        "page render files", set(page_inv_by_id), set(render_files), errors
    )
    for line, row in enumerate(page_inventory, start=2):
        try:
            physical_page_number = int(row["PhysicalPage"])
            physical_inventory.append(physical_page_number)
            page_match = PAGE_ID_RE.fullmatch(row["PageID"])
            if page_match and physical_page_number != int(page_match.group(1)):
                errors.append(
                    f"00-page-inventory.csv:{line}: {row['PageID']} must map "
                    f"to PhysicalPage {int(page_match.group(1))}, got "
                    f"{physical_page_number}"
                )
        except ValueError:
            errors.append(
                f"00-page-inventory.csv:{line}: invalid PhysicalPage "
                f"{row['PhysicalPage']!r}"
            )
    for line, row in enumerate(page_ledger, start=2):
        physical_page_number: int | None = None
        try:
            physical_page_number = int(row["PhysicalPage"])
            physical_ledger.append(physical_page_number)
            page_match = PAGE_ID_RE.fullmatch(row["PageID"])
            if page_match and physical_page_number != int(page_match.group(1)):
                errors.append(
                    f"02-page-layout-ledger.csv:{line}: {row['PageID']} must map "
                    f"to PhysicalPage {int(page_match.group(1))}, got "
                    f"{physical_page_number}"
                )
        except ValueError:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid PhysicalPage "
                f"{row['PhysicalPage']!r}"
            )
        mode = row["InspectionModeScale"].casefold()
        if not mode.startswith(INSPECTION_MODE_PREFIXES):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: invalid "
                f"InspectionModeScale {row['InspectionModeScale']!r}"
            )
        signals = row["Signals"].casefold()
        mechanical = page_inv_by_id.get(row["PageID"], {}).get(
            "MechanicalSignals", ""
        ).casefold()
        suspect = any(
            value and value not in NON_SIGNAL_VALUES
            for value in (signals, mechanical)
        )
        if suspect and not mode.startswith("full-scale"):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: suspect page "
                f"{row['PageID']} was not inspected full-scale"
            )
        disposition_value = row["Disposition"].strip()
        disposition = disposition_value.casefold()
        page_owner_id = (
            "R5" if process.get("degree_level") == "doctorate" else "R3"
        )
        valid_layout_finding = re.fullmatch(
            rf"(?i)finding[ \t]+{page_owner_id}-F\d{{2,4}}",
            disposition_value,
        )
        if disposition not in {"clean", "intentional"} and valid_layout_finding is None:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: Disposition must be exactly "
                f"clean, intentional, or finding {page_owner_id}-Fxx; "
                "recheck after edit is not a valid final disposition"
            )
        if any(
            token in disposition
            for token in ("pending", "unchecked", "recheck", "open", "unresolved")
        ):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: unresolved disposition "
                f"{row['Disposition']!r}"
            )
        render_dpi: int | None = None
        try:
            render_dpi = int(row["RenderDPI"])
            if render_dpi < 120 or render_dpi > 600:
                raise ValueError
        except ValueError:
            errors.append(
                f"02-page-layout-ledger.csv:{line}: RenderDPI must be "
                "an integer in the auditable range 120..600"
            )
        render_pattern = re.compile(
            rf"^(?:{re.escape(row['PageID'])}[:/| -])?[0-9a-fA-F]{{64}}$"
        )
        if not render_pattern.fullmatch(row["RenderArtifactIDHash"]):
            errors.append(
                f"02-page-layout-ledger.csv:{line}: "
                "RenderArtifactIDHash must be a 64-hex hash, optionally "
                "prefixed by the matching PageID"
            )
        render_path = render_files.get(row["PageID"])
        if render_path is not None:
            declared_match = HEX64_FIND_RE.search(row["RenderArtifactIDHash"])
            if declared_match and sha256(render_path) != declared_match.group(1).upper():
                errors.append(
                    f"02-page-layout-ledger.csv:{line}: render-file hash mismatch "
                    f"for {row['PageID']}"
                )
            dimensions = read_valid_png_dimensions(render_path, errors)
            if (
                dimensions is not None
                and render_dpi is not None
                and physical_page_number is not None
                and 1 <= physical_page_number <= len(pdf_page_sizes)
            ):
                width_points, height_points = pdf_page_sizes[physical_page_number - 1]
                expected_width = round(width_points * render_dpi / 72.0)
                expected_height = round(height_points * render_dpi / 72.0)
                if (
                    abs(dimensions[0] - expected_width) > 2
                    or abs(dimensions[1] - expected_height) > 2
                ):
                    errors.append(
                        f"{render_path.name}: pixel dimensions {dimensions} do not "
                        f"match page {physical_page_number} at {render_dpi} dpi "
                        f"({expected_width}, {expected_height})"
                    )
    expected_pages = list(range(1, page_count + 1)) if page_count else []
    if page_count and sorted(physical_inventory) != expected_pages:
        errors.append(
            "00-page-inventory.csv: PhysicalPage values are not exactly 1..N"
        )
    if page_count and sorted(physical_ledger) != expected_pages:
        errors.append(
            "02-page-layout-ledger.csv: PhysicalPage values are not exactly 1..N"
        )
    for page_id in sorted(set(page_inv_by_id) & set(page_led_by_id)):
        inv = page_inv_by_id[page_id]
        led = page_led_by_id[page_id]
        for field in ("PhysicalPage", "PrintedPage", "Region"):
            if inv[field] != led[field]:
                errors.append(
                    f"page mapping mismatch for {page_id}: {field} "
                    f"inventory={inv[field]!r}, ledger={led[field]!r}"
                )
    validate_markdown_id_projection(
        root / "02-page-layout-ledger.md",
        set(page_inv_by_id),
        re.compile(r"(?<![A-Za-z0-9])P\d{4}(?![A-Za-z0-9])"),
        {"Page ID", "PageID"},
        "page ledger",
        errors,
        required_headers={
            "Page ID", "Physical page", "Printed page", "Region",
            "Dominant content", "Signals", "Inspection mode/scale",
            "Render DPI", "Render artifact ID/hash", "Neighbor pages checked",
            "Disposition", "Evidence",
        },
        same_row_id_headers={"Render artifact ID/hash"},
        reference_id_headers={"Neighbor pages checked", "Evidence"},
    )
    validate_markdown_csv_projection(
        root / "02-page-layout-ledger.md",
        PAGE_MARKDOWN_HEADERS,
        page_markdown_projection_rows(page_ledger),
        "page-ledger",
        errors,
    )

    bib_inventory = read_csv(
        root / "00-bibliography-inventory.csv", BIB_INVENTORY_COLUMNS,
        errors, require_rows=True,
    )
    validate_rows_mandatory(
        bib_inventory, "00-bibliography-inventory.csv",
        BIB_INVENTORY_COLUMNS, errors,
    )
    validate_pdf_hash(
        bib_inventory, "00-bibliography-inventory.csv", expected_hash, errors
    )

    citation_candidates = read_csv(
        root / "00-citation-candidate-ledger.csv",
        CITATION_CANDIDATE_COLUMNS,
        errors,
        require_rows=True,
    )
    validate_rows_mandatory(
        citation_candidates,
        "00-citation-candidate-ledger.csv",
        CITATION_CANDIDATE_COLUMNS,
        errors,
    )
    validate_pdf_hash(
        citation_candidates,
        "00-citation-candidate-ledger.csv",
        expected_hash,
        errors,
    )
    reference_pages: set[int] = set()
    for row in page_inventory:
        region = row.get("Region", "").strip().casefold()
        if (
            "reference" in region
            or "bibliograph" in region
            or "参考文献" in region
        ):
            try:
                reference_pages.add(int(row["PhysicalPage"]))
            except (TypeError, ValueError):
                pass
    reference_pages = derive_and_validate_reference_pages(
        frozen_path,
        reference_pages,
        bib_inventory,
        errors,
    ) if frozen_path.is_file() else set()
    extracted_candidates, extracted_unmatched_glyphs = (
        extract_numeric_bracket_candidates(frozen_path, reference_pages, errors)
        if frozen_path.is_file()
        else ([], [])
    )
    unmatched_rows = read_csv(
        root / "00-unmatched-bracket-ledger.csv",
        UNMATCHED_BRACKET_COLUMNS,
        errors,
        require_rows=bool(extracted_unmatched_glyphs),
    )
    validate_rows_mandatory(
        unmatched_rows,
        "00-unmatched-bracket-ledger.csv",
        UNMATCHED_BRACKET_COLUMNS,
        errors,
    )
    validate_pdf_hash(
        unmatched_rows,
        "00-unmatched-bracket-ledger.csv",
        expected_hash,
        errors,
    )
    if len(unmatched_rows) != len(extracted_unmatched_glyphs):
        errors.append(
            "00-unmatched-bracket-ledger.csv: row count does not equal the "
            "validator's frozen-PDF unmatched-glyph extraction; "
            f"ledger={len(unmatched_rows)}, extracted={len(extracted_unmatched_glyphs)}"
        )
    for index, row in enumerate(unmatched_rows, start=1):
        line = index + 1
        expected_id = f"UBG{index:04d}"
        if row["GlyphID"] != expected_id:
            errors.append(
                f"00-unmatched-bracket-ledger.csv:{line}: GlyphID must be "
                f"{expected_id}, got {row['GlyphID']!r}"
            )
        if index <= len(extracted_unmatched_glyphs):
            extracted = extracted_unmatched_glyphs[index - 1]
            try:
                physical_page = int(row["PhysicalPage"])
            except (TypeError, ValueError):
                physical_page = -1
            if physical_page != extracted["PhysicalPage"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: PhysicalPage "
                    "does not match the frozen-PDF extraction"
                )
            if row["Glyph"] != extracted["Glyph"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: Glyph does not "
                    "match the frozen-PDF extraction"
                )
            if row["AdjacentPDFText"] != extracted["Adjacent"]:
                errors.append(
                    f"00-unmatched-bracket-ledger.csv:{line}: AdjacentPDFText "
                    "does not exactly match the deterministic extraction window"
                )
        disposition = row["Disposition"].strip().casefold()
        if (
            len(disposition) < 12
            or is_placeholder(disposition)
            or re.search(r"\b(?:none|no unmatched|zero)\b", disposition)
        ):
            errors.append(
                f"00-unmatched-bracket-ledger.csv:{line}: Disposition must "
                "give a concrete non-contradictory glyph adjudication"
            )
    if len(citation_candidates) != len(extracted_candidates):
        errors.append(
            "00-citation-candidate-ledger.csv: row count does not equal the "
            "validator's frozen-PDF extraction; "
            f"ledger={len(citation_candidates)}, extracted={len(extracted_candidates)}"
        )
    candidate_occurrence_numbers: dict[str, list[int]] = {}
    candidate_occurrence_pages: dict[str, int] = {}
    candidate_occurrence_contexts: dict[str, str] = {}
    citation_candidate_count = 0
    for index, row in enumerate(citation_candidates, start=1):
        line = index + 1
        expected_id = f"BC{index:04d}"
        if row["CandidateID"] != expected_id:
            errors.append(
                "00-citation-candidate-ledger.csv: CandidateID sequence mismatch "
                f"at row {line}; expected {expected_id}, got {row['CandidateID']!r}"
            )
        if not BRACKET_CANDIDATE_ID_RE.fullmatch(row["CandidateID"]):
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid CandidateID"
            )
        try:
            physical_page = int(row["PhysicalPage"])
        except (TypeError, ValueError):
            physical_page = -1
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid PhysicalPage"
            )
        marker = normalize_numeric_marker(row["Marker"])
        if row["Marker"] != marker:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: Marker must equal "
                "its canonical whitespace/comma/dash normalization"
            )
        parsed_numbers = expand_numeric_marker(row["Marker"])
        if parsed_numbers is None:
            declared_numbers: list[int] | None = None
            if row["ExpandedNumbers"] != "N/A":
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: mixed/decimal "
                    "numeric bracket must use ExpandedNumbers=N/A"
                )
        else:
            try:
                declared_numbers = [
                    int(item) for item in row["ExpandedNumbers"].split(";")
                ]
            except (TypeError, ValueError):
                declared_numbers = []
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: ExpandedNumbers "
                    "must be a semicolon-separated integer sequence"
                )
            canonical_expansion = ";".join(
                str(value) for value in parsed_numbers
            )
            if row["ExpandedNumbers"] != canonical_expansion:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: ExpandedNumbers "
                    f"must equal canonical expansion {canonical_expansion!r}"
                )
            if declared_numbers != parsed_numbers:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: numeric expansion "
                    "does not match Marker"
                )
        if index <= len(extracted_candidates):
            extracted = extracted_candidates[index - 1]
            if physical_page != extracted["PhysicalPage"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: PhysicalPage "
                    f"{physical_page} != extracted {extracted['PhysicalPage']}"
                )
            if row["Marker"] != extracted["Marker"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: Marker {row['Marker']!r} "
                    f"!= extracted {extracted['Marker']!r}"
                )
            if parsed_numbers != extracted["Expanded"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: expansion does "
                    "not equal the frozen-PDF extraction"
                )
            if row["AdjacentPDFText"] != extracted["Adjacent"]:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: AdjacentPDFText "
                    "does not exactly match the deterministic frozen-PDF window"
                )
        classification = row["Classification"].strip().casefold()
        if classification not in CANDIDATE_CLASSIFICATIONS:
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: invalid "
                f"Classification {row['Classification']!r}"
            )
        evidence = row["ClassificationEvidence"]
        if not valid_candidate_classification_evidence(evidence):
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: "
                "ClassificationEvidence is not a concrete contextual reason"
            )
        if index <= len(extracted_candidates):
            obvious_reason = obvious_non_citation_reason(
                extracted_candidates[index - 1]
            )
            if obvious_reason and classification != "non-citation":
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: obvious "
                    f"non-citation classified as citation ({obvious_reason})"
                )
        mapped = row["MappedOccurrenceID"].strip()
        if classification == "citation":
            citation_candidate_count += 1
            expected_occurrence = f"C{citation_candidate_count:04d}"
            if parsed_numbers is None:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: citation "
                    "classification requires a pure integer citation marker"
                )
            if mapped != expected_occurrence:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: citation "
                    f"candidate must map to {expected_occurrence}, got {mapped!r}"
                )
            if mapped in candidate_occurrence_numbers:
                errors.append(
                    f"00-citation-candidate-ledger.csv:{line}: duplicate "
                    f"MappedOccurrenceID {mapped}"
                )
            candidate_occurrence_numbers[mapped] = parsed_numbers or []
            candidate_occurrence_pages[mapped] = physical_page
            candidate_occurrence_contexts[mapped] = row["AdjacentPDFText"]
        elif classification == "non-citation" and mapped != "N/A":
            errors.append(
                f"00-citation-candidate-ledger.csv:{line}: non-citation must "
                "use MappedOccurrenceID=N/A"
            )

    bib_ledger = read_csv(
        root / "03-bibliography-audit-ledger.csv", BIB_LEDGER_COLUMNS,
        errors, require_rows=True,
    )
    validate_rows_mandatory(
        bib_ledger, "03-bibliography-audit-ledger.csv",
        BIB_LEDGER_COLUMNS, errors,
    )
    validate_bibliography_endpoint_records(
        bib_ledger, "03-bibliography-audit-ledger.csv", errors
    )
    validate_reference_ids_only_in_id_column(
        bib_ledger, "03-bibliography-audit-ledger.csv", errors
    )
    validate_pdf_hash(
        bib_ledger, "03-bibliography-audit-ledger.csv", expected_hash, errors
    )
    bib_inv_by_id = index_unique(
        bib_inventory, "ReferenceID", "00-bibliography-inventory.csv", errors
    )
    validate_bibliography_source_identity(
        bib_ledger,
        bib_inv_by_id,
        "03-bibliography-audit-ledger.csv",
        errors,
    )
    bib_refs_in_ledger = {
        row["ReferenceID"] for row in bib_ledger if row["ReferenceID"]
    }
    compare_sets(
        "bibliography ledger", set(bib_inv_by_id), bib_refs_in_ledger, errors
    )
    for index, row in enumerate(bib_inventory, start=1):
        expected_ref_id = f"REF{index:04d}"
        if row["ReferenceID"] != expected_ref_id:
            errors.append(
                "00-bibliography-inventory.csv: ReferenceID sequence mismatch "
                f"at row {index + 1}; expected {expected_ref_id}, "
                f"got {row['ReferenceID']!r}"
            )
    fields_by_ref: dict[str, set[str]] = defaultdict(set)
    bib_keys: Counter[tuple[str, str]] = Counter()
    degree_level = process.get("degree_level")
    bibliography_owner = 5 if degree_level == "doctorate" else 3
    citation_owner = 4 if degree_level == "doctorate" else 3
    bibliography_link_re = re.compile(
        rf"(?<![A-Za-z0-9])R{bibliography_owner}-(?:F|Q)\d{{2,4}}"
        rf"(?![A-Za-z0-9])"
    )
    citation_link_re = re.compile(
        rf"(?<![A-Za-z0-9])R{citation_owner}-(?:F|Q)\d{{2,4}}"
        rf"(?![A-Za-z0-9])"
    )
    reasoned_nonfinding_re = re.compile(
        r"(?is)\breasoned[ -]non-finding\s*:\s*\S.{19,}"
    )
    for line, row in enumerate(bib_ledger, start=2):
        ref = row["ReferenceID"]
        field = row["Field"]
        fields_by_ref[ref].add(field)
        bib_keys[(ref, field)] += 1
        verdict = row["Verdict"].casefold()
        if verdict not in BIB_VERDICTS:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid verdict "
                f"{row['Verdict']!r}"
            )
        if (
            row["EvidenceEndpoint"]
            and not PUBLIC_URL_RE.fullmatch(row["EvidenceEndpoint"])
        ):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "EvidenceEndpoint lacks an http(s) authoritative record or "
                "contains material outside one complete URL"
            )
        if not validate_iso_date(row["CheckedAt"]):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "CheckedAt must be an ISO-8601 date or datetime"
            )
        if field not in BIB_FIELDS:
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: invalid field {field!r}"
            )
        inv = bib_inv_by_id.get(ref)
        if inv:
            for ledger_field, inventory_field in (
                ("DisplayedLabel", "DisplayedLabel"), ("Cited", "Cited"),
            ):
                if row[ledger_field] != inv[inventory_field]:
                    errors.append(
                        f"bibliography mapping mismatch for {ref}/{field}: "
                        f"{ledger_field}={row[ledger_field]!r}, "
                        f"inventory={inv[inventory_field]!r}"
                    )
        if (
            verdict == "unverifiable"
            and row["EvidenceNote"].casefold() in {"n/a", "none"}
        ):
            errors.append(
                f"03-bibliography-audit-ledger.csv:{line}: "
                "unverifiable row lacks attempted-route note"
            )
        if verdict == "mismatch":
            finding_disposition = row["FindingDisposition"].strip()
            has_exact_bibliography_link = bool(
                bibliography_link_re.fullmatch(finding_disposition)
            )
            if not has_exact_bibliography_link:
                has_embedded_link = bool(
                    bibliography_link_re.search(finding_disposition)
                )
                if has_embedded_link and BIB_MISMATCH_EXEMPTION_RE.search(
                    finding_disposition
                ):
                    errors.append(
                        f"03-bibliography-audit-ledger.csv:{line}: mismatch "
                        "FindingDisposition cannot mix an owning-reviewer link "
                        "with a non-finding exemption phrase"
                    )
                    continue
                errors.append(
                    f"03-bibliography-audit-ledger.csv:{line}: {verdict} row must "
                    f"link an owning-reviewer R{bibliography_owner}-Fxx or "
                    f"R{bibliography_owner}-Qxx disposition; the whole cell must "
                    "be exactly one current owner ID with no prose or second ID"
                )
    duplicate_bib_keys = sorted(
        key for key, count in bib_keys.items() if count > 1
    )
    if duplicate_bib_keys:
        errors.append(
            "03-bibliography-audit-ledger.csv: duplicate "
            f"(ReferenceID,Field) keys {duplicate_bib_keys}"
        )
    for ref in sorted(bib_inv_by_id):
        actual_fields = fields_by_ref[ref]
        if actual_fields != BIB_FIELDS:
            errors.append(
                f"03-bibliography-audit-ledger.csv: {ref} field-set mismatch; "
                f"missing={sorted(BIB_FIELDS-actual_fields)}, "
                f"extra={sorted(actual_fields-BIB_FIELDS)}"
            )
    validate_markdown_id_projection(
        root / "03-bibliography-audit-ledger.md",
        set(bib_inv_by_id),
        re.compile(r"(?<![A-Za-z0-9])REF\d{4}(?![A-Za-z0-9])"),
        {"Reference ID", "ReferenceID"},
        "bibliography ledger",
        errors,
        required_headers={
            "Reference ID", "Displayed label", "Cited?", "Type", "Title",
            "Ordered authors", "Year", "Venue", "Publication status",
            "Volume/issue", "Pages/article no.",
            "Persistent IDs/URL/access date", "Existence",
            "Retraction/correction/superseding", "Finding/disposition",
        },
    )
    validate_markdown_csv_projection(
        root / "03-bibliography-audit-ledger.md",
        BIB_MARKDOWN_HEADERS,
        bibliography_markdown_projection_rows(bib_inventory, bib_ledger),
        "bibliography-ledger",
        errors,
    )

    citation_inventory = read_csv(
        root / "00-citation-inventory.csv", CITATION_INVENTORY_COLUMNS,
        errors, require_rows=True,
    )
    citation_ledger = read_csv(
        root / "04-citation-claim-audit-ledger.csv",
        CITATION_LEDGER_COLUMNS, errors, require_rows=True,
    )
    validate_rows_mandatory(
        citation_inventory, "00-citation-inventory.csv",
        CITATION_INVENTORY_COLUMNS, errors,
    )
    validate_rows_mandatory(
        citation_ledger, "04-citation-claim-audit-ledger.csv",
        CITATION_LEDGER_COLUMNS, errors,
        blank_allowed={"ContentSourceOpened", "ExactSourceLocator"},
    )
    validate_citation_endpoint_records(
        citation_ledger, "04-citation-claim-audit-ledger.csv", errors
    )
    validate_pdf_hash(
        citation_inventory, "00-citation-inventory.csv", expected_hash, errors
    )
    validate_pdf_hash(
        citation_ledger, "04-citation-claim-audit-ledger.csv",
        expected_hash, errors,
    )
    citation_inv_by_pair = index_unique(
        citation_inventory, "PairID", "00-citation-inventory.csv", errors
    )
    citation_led_by_pair = index_unique(
        citation_ledger, "PairID",
        "04-citation-claim-audit-ledger.csv", errors,
    )
    validate_citation_source_identity(
        citation_ledger,
        bib_inv_by_id,
        "04-citation-claim-audit-ledger.csv",
        errors,
    )
    compare_sets(
        "citation-claim ledger", set(citation_inv_by_pair),
        set(citation_led_by_pair), errors,
    )
    validate_citation_pair_row_order(citation_inventory, citation_ledger, errors)
    current_occurrence = 0
    current_source_ordinal = 0
    inventory_occurrence_numbers: dict[str, list[int]] = defaultdict(list)
    for line, row in enumerate(citation_inventory, start=2):
        occurrence_match = OCCURRENCE_ID_RE.fullmatch(row["OccurrenceID"])
        pair_match = PAIR_ID_RE.fullmatch(row["PairID"])
        if not occurrence_match or not pair_match:
            errors.append(
                f"00-citation-inventory.csv:{line}: invalid deterministic "
                "OccurrenceID/PairID format"
            )
            continue
        occurrence_number = int(occurrence_match.group(1))
        pair_occurrence = int(pair_match.group(1))
        source_ordinal = int(pair_match.group(2))
        if pair_occurrence != occurrence_number:
            errors.append(
                f"00-citation-inventory.csv:{line}: PairID occurrence does not "
                "match OccurrenceID"
            )
        if occurrence_number == current_occurrence:
            current_source_ordinal += 1
        elif occurrence_number == current_occurrence + 1:
            current_occurrence = occurrence_number
            current_source_ordinal = 1
        else:
            errors.append(
                f"00-citation-inventory.csv:{line}: occurrence IDs are not "
                "continuous in reading order"
            )
            current_occurrence = occurrence_number
            current_source_ordinal = 1
        if source_ordinal != current_source_ordinal:
            errors.append(
                f"00-citation-inventory.csv:{line}: source ordinals are not "
                "continuous within the occurrence"
            )
        expected_pair_id = (
            f"C{occurrence_number:04d}-S{current_source_ordinal:02d}"
        )
        if row["PairID"] != expected_pair_id:
            errors.append(
                f"00-citation-inventory.csv:{line}: PairID must equal canonical "
                f"reading-order ID {expected_pair_id}"
            )
        reference_match = REFERENCE_ID_RE.fullmatch(
            row["DisplayedReferenceID"]
        )
        if not reference_match:
            errors.append(
                f"00-citation-inventory.csv:{line}: invalid "
                "DisplayedReferenceID"
            )
        else:
            inventory_occurrence_numbers[row["OccurrenceID"]].append(
                int(reference_match.group(1))
            )
        expected_page = candidate_occurrence_pages.get(row["OccurrenceID"])
        located_page = parse_physical_page_locator(row["PDFLocation"])
        if located_page is None:
            errors.append(
                f"00-citation-inventory.csv:{line}: PDFLocation must contain "
                "an explicit physical page"
            )
        elif located_page < 1 or (page_count and located_page > page_count):
            errors.append(
                f"00-citation-inventory.csv:{line}: physical page "
                f"{located_page} is outside 1..{page_count}"
            )
        elif expected_page is not None and located_page != expected_page:
            errors.append(
                f"00-citation-inventory.csv:{line}: PDFLocation page "
                f"{located_page} != candidate page {expected_page}"
            )
        expected_context = candidate_occurrence_contexts.get(row["OccurrenceID"])
        if (
            expected_context is not None
            and row["AdjacentPDFText"] != expected_context
        ):
            errors.append(
                f"00-citation-inventory.csv:{line}: AdjacentPDFText does not "
                "exactly equal the mapped candidate's frozen-PDF context"
            )
    compare_sets(
        "citation candidate-to-inventory occurrence mapping",
        set(candidate_occurrence_numbers),
        set(inventory_occurrence_numbers),
        errors,
    )
    for occurrence_id in sorted(
        set(candidate_occurrence_numbers) & set(inventory_occurrence_numbers)
    ):
        if (
            candidate_occurrence_numbers[occurrence_id]
            != inventory_occurrence_numbers[occurrence_id]
        ):
            errors.append(
                "citation candidate-to-inventory number mismatch for "
                f"{occurrence_id}: candidate="
                f"{candidate_occurrence_numbers[occurrence_id]}, inventory="
                f"{inventory_occurrence_numbers[occurrence_id]}"
            )
    cited_reference_ids = {
        row["DisplayedReferenceID"] for row in citation_inventory
        if REFERENCE_ID_RE.fullmatch(row["DisplayedReferenceID"])
    }
    for line, row in enumerate(bib_inventory, start=2):
        expected_cited = "yes" if row["ReferenceID"] in cited_reference_ids else "no"
        if row["Cited"].strip().casefold() != expected_cited:
            errors.append(
                f"00-bibliography-inventory.csv:{line}: Cited must be "
                f"{expected_cited!r} from the reconciled citation inventory"
            )
    for pair_id in sorted(
        set(citation_inv_by_pair) & set(citation_led_by_pair)
    ):
        inv = citation_inv_by_pair[pair_id]
        led = citation_led_by_pair[pair_id]
        for ledger_field, inventory_field in (
            ("OccurrenceID", "OccurrenceID"),
            ("ReferenceID", "DisplayedReferenceID"),
            ("PDFLocation", "PDFLocation"),
        ):
            if led[ledger_field] != inv[inventory_field]:
                errors.append(
                    f"citation mapping mismatch for {pair_id}: "
                    f"{ledger_field}={led[ledger_field]!r}, "
                    f"inventory={inv[inventory_field]!r}"
                )
    for line, row in enumerate(citation_ledger, start=2):
        support = row["Support"].casefold()
        if support not in SUPPORT_VALUES:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: invalid support "
                f"{row['Support']!r}"
            )
        metadata_status = row["MetadataStatus"].casefold()
        if metadata_status not in METADATA_STATUS_VALUES:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: invalid MetadataStatus "
                f"{row['MetadataStatus']!r}"
            )
        if support in {"direct", "partial", "context-only", "mismatch"}:
            if (
                not row["ContentSourceOpened"]
                or row["ContentSourceOpened"].casefold() in {"n/a", "none"}
            ):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "substantive verdict lacks content source"
                )
            elif not PUBLIC_URL_RE.search(row["ContentSourceOpened"]):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "ContentSourceOpened lacks an http(s) content endpoint"
                )
            if (
                not row["ExactSourceLocator"]
                or row["ExactSourceLocator"].casefold() in {"n/a", "none"}
            ):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "substantive verdict lacks exact locator"
                )
            elif not SOURCE_LOCATOR_RE.search(row["ExactSourceLocator"]):
                errors.append(
                    f"04-citation-claim-audit-ledger.csv:{line}: "
                    "ExactSourceLocator lacks a page/section/content locator"
                )
        validate_dangling_citation_audit_row(
            row, bib_inv_by_id, line, errors
        )
        requires_disposition = (
            support in {
                "partial", "context-only", "mismatch", "unverifiable", "not-needed"
            }
            or metadata_status in {"mismatch", "unverifiable"}
        )
        disposition_text = f"{row['SeverityFinding']} {row['DispositionEvidence']}"
        has_owner_link = bool(citation_link_re.search(disposition_text))
        has_reasoned_nonfinding = bool(
            reasoned_nonfinding_re.search(row["DispositionEvidence"])
        )
        hard_mismatch = support == "mismatch" or metadata_status == "mismatch"
        if hard_mismatch and not has_owner_link:
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: mismatch row must "
                f"link an owning-reviewer R{citation_owner}-Fxx or "
                f"R{citation_owner}-Qxx disposition; a reasoned non-finding "
                "cannot waive a contradiction"
            )
        elif requires_disposition and not (has_owner_link or has_reasoned_nonfinding):
            errors.append(
                f"04-citation-claim-audit-ledger.csv:{line}: non-ideal support/metadata "
                f"row must link an owning-reviewer R{citation_owner}-Fxx or "
                f"R{citation_owner}-Qxx disposition, or use an explicit substantive "
                "'reasoned non-finding:' explanation"
            )
    validate_markdown_id_projection(
        root / "04-citation-claim-audit-ledger.md",
        set(citation_inv_by_pair),
        PAIR_ID_TOKEN_RE,
        {"Pair ID", "PairID"},
        "citation-claim ledger",
        errors,
        required_headers={
            "Pair ID", "Occurrence ID", "PDF location",
            "Exact attached proposition", "Reference ID", "Displayed label",
            "Public source/identifier",
            "Content source opened and exact locator", "Support",
            "Metadata/status", "Severity/finding", "Disposition/evidence",
        },
    )
    validate_markdown_csv_projection(
        root / "04-citation-claim-audit-ledger.md",
        CITATION_MARKDOWN_HEADERS,
        citation_markdown_projection_rows(citation_ledger, bib_inv_by_id),
        "citation-claim-ledger",
        errors,
    )

    academic_ledger = read_csv(
        root / "91-revision-ledger.csv", ACADEMIC_LEDGER_COLUMNS,
        errors, require_rows=False,
    )
    ai_ledger = read_csv(
        root / "91-ai-actionable-ledger.csv", AI_LEDGER_COLUMNS,
        errors, require_rows=False,
    )
    validate_rows_mandatory(
        academic_ledger, "91-revision-ledger.csv",
        ACADEMIC_LEDGER_COLUMNS, errors,
    )
    validate_rows_mandatory(
        ai_ledger, "91-ai-actionable-ledger.csv",
        AI_LEDGER_COLUMNS, errors,
    )
    academic_by_id = index_unique(
        academic_ledger, "LedgerID", "91-revision-ledger.csv", errors
    )
    validate_academic_dependency_references(
        academic_ledger, "91-revision-ledger.csv", errors
    )
    ai_by_id = index_unique(
        ai_ledger, "AIFindingID", "91-ai-actionable-ledger.csv", errors
    )
    chair_finding_counts: Counter[str] = Counter()
    ledger_numbers: list[int] = []
    chair_finding_numbers: list[int] = []
    for line, row in enumerate(academic_ledger, start=2):
        if not re.fullmatch(r"L\d{2,4}", row["LedgerID"]):
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid LedgerID {row['LedgerID']!r}"
            )
        else:
            ledger_numbers.append(int(row["LedgerID"][1:]))
        chair_id = row["ChairFindingID"]
        chair_match = re.fullmatch(r"C-F(\d{2,4})", chair_id)
        if chair_match is None:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid ChairFindingID {chair_id!r}"
            )
        else:
            chair_finding_numbers.append(int(chair_match.group(1)))
        chair_finding_counts[chair_id] += 1
        if row["Severity"].casefold() not in ACADEMIC_SEVERITIES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Severity "
                f"{row['Severity']!r}"
            )
        subtype = row["S0Subtype"].casefold()
        if row["Severity"].casefold() == "s0":
            if subtype not in {"procedural", "integrity/foundational"}:
                errors.append(
                    f"91-revision-ledger.csv:{line}: invalid S0Subtype "
                    f"{row['S0Subtype']!r} for S0"
                )
        elif subtype not in {"n/a", "na", "not applicable"}:
            errors.append(
                f"91-revision-ledger.csv:{line}: non-S0 row requires S0Subtype N/A"
            )
        if row["Remedy"].casefold() not in ACADEMIC_REMEDIES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Remedy "
                f"{row['Remedy']!r}"
            )
        if row["Priority"].casefold() not in ACADEMIC_PRIORITIES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Priority "
                f"{row['Priority']!r}"
            )
        if row["EvidenceStatus"].casefold() not in {
            "verified", "partially verified", "not verifiable from submitted pdf",
            "deduplicated", "disputed",
        }:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid EvidenceStatus "
                f"{row['EvidenceStatus']!r}"
            )
        if row["Status"].casefold() not in STATUS_VALUES:
            errors.append(
                f"91-revision-ledger.csv:{line}: invalid Status "
                f"{row['Status']!r}"
            )
        anchor_page = parse_physical_page_locator(row["ExactPDFAnchor"])
        if anchor_page is None or anchor_page < 1 or anchor_page > page_count:
            errors.append(
                f"91-revision-ledger.csv:{line}: ExactPDFAnchor must identify "
                "a physical page inside the frozen PDF"
            )
    duplicate_chair_ids = sorted(
        value for value, count in chair_finding_counts.items() if count != 1
    )
    if duplicate_chair_ids:
        errors.append(
            "91-revision-ledger.csv: ChairFindingID values must be unique; "
            f"duplicates={duplicate_chair_ids}"
        )
    if ledger_numbers != list(range(1, len(ledger_numbers) + 1)):
        errors.append("91-revision-ledger.csv: LedgerID values must be continuous from L01")
    if chair_finding_numbers != list(range(1, len(chair_finding_numbers) + 1)):
        errors.append(
            "91-revision-ledger.csv: ChairFindingID values must be continuous from C-F01"
        )
    for line, row in enumerate(ai_ledger, start=2):
        if not re.fullmatch(r"AI-F\d{2,4}", row["AIFindingID"]):
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: invalid AIFindingID "
                f"{row['AIFindingID']!r}"
            )
        if row["Impact"].casefold() not in AI_ACTION_IMPACTS:
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: invalid Impact "
                f"{row['Impact']!r}"
            )
        if row["Status"].casefold() not in STATUS_VALUES:
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: invalid Status "
                f"{row['Status']!r}"
            )
        anchor_page = parse_physical_page_locator(row["ExactPDFAnchor"])
        if anchor_page is None or anchor_page < 1 or anchor_page > page_count:
            errors.append(
                f"91-ai-actionable-ledger.csv:{line}: ExactPDFAnchor must identify "
                "a physical page inside the frozen PDF"
            )
    validate_markdown_id_projection(
        root / "91-revision-ledger.md",
        set(academic_by_id),
        re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
        {"Ledger ID", "LedgerID"},
        "chair academic revision ledger",
        errors,
        required_headers={
            "Ledger ID", "Priority", "Chair finding ID",
            "Source reviewer finding IDs", "Severity", "S0 subtype", "Remedy",
            "Exact PDF anchor", "Direct observation", "Evidence status", "Minimum edit/evidence",
            "Dependency", "Owner", "Status", "Verification",
        },
        reference_id_headers={"Dependency"},
    )
    validate_markdown_id_projection(
        root / "91-revision-ledger.md",
        set(ai_by_id),
        re.compile(r"(?<![A-Za-z0-9])AI-F\d{2,4}(?![A-Za-z0-9])"),
        {"AI finding ID", "AIFindingID"},
        "chair AI-actionable ledger",
        errors,
        required_headers={
            "AI finding ID", "Impact (`material` / `local`)",
            "Exact PDF anchor", "Direct style observation",
            "Minimum editing action", "Status", "Verification",
        },
    )
    validate_chair_ledger_markdown_values(
        root / "91-revision-ledger.md",
        academic_by_id,
        ai_by_id,
        errors,
    )
    validate_chair_finding_tables(
        root / "90-chair-synthesis.md",
        academic_by_id,
        ai_by_id,
        errors,
    )
    open_academic = {
        ledger_id: row for ledger_id, row in academic_by_id.items()
        if row["Status"].casefold() not in CLOSED_STATUSES
    }
    open_ai = {
        finding_id: row for finding_id, row in ai_by_id.items()
        if row["Status"].casefold() not in CLOSED_STATUSES
    }
    evidence_items = read_csv(
        root / "92-new-evidence-or-experiments.csv",
        EVIDENCE_ITEM_COLUMNS,
        errors,
        require_rows=any(
            row.get("Remedy", "").casefold() == "n"
            for row in open_academic.values()
        ),
    )
    validate_rows_mandatory(
        evidence_items, "92-new-evidence-or-experiments.csv",
        EVIDENCE_ITEM_COLUMNS, errors,
    )
    evidence_by_id = index_unique(
        evidence_items, "EvidenceItemID",
        "92-new-evidence-or-experiments.csv", errors,
    )
    evidence_numbers = [
        int(match.group(1))
        for row in evidence_items
        if (match := EVIDENCE_ITEM_ID_RE.fullmatch(row.get("EvidenceItemID", "")))
    ]
    invalid_evidence_ids = [
        row.get("EvidenceItemID", "") for row in evidence_items
        if not EVIDENCE_ITEM_ID_RE.fullmatch(row.get("EvidenceItemID", ""))
    ]
    if invalid_evidence_ids:
        errors.append(
            "92-new-evidence-or-experiments.csv: invalid EvidenceItemID values "
            f"{invalid_evidence_ids}"
        )
    if evidence_numbers != list(range(1, len(evidence_numbers) + 1)):
        errors.append(
            "92-new-evidence-or-experiments.csv: EvidenceItemID values must be "
            "continuous from N01 in row order"
        )
    open_n_rows = {
        ledger_id: row for ledger_id, row in open_academic.items()
        if row.get("Remedy", "").casefold() == "n"
    }
    evidence_by_ledger: dict[str, dict[str, str]] = {}
    duplicate_evidence_ledgers: list[str] = []
    for line, row in enumerate(evidence_items, start=2):
        ledger_id = row.get("LedgerID", "")
        if ledger_id in evidence_by_ledger:
            duplicate_evidence_ledgers.append(ledger_id)
        else:
            evidence_by_ledger[ledger_id] = row
        source = open_n_rows.get(ledger_id)
        if source is None:
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: LedgerID must refer "
                "to one open current 91 row with Remedy=N"
            )
            continue
        if row.get("ChairFindingID") != source.get("ChairFindingID"):
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: ChairFindingID does "
                "not match its linked 91 row"
            )
        if row.get("Remedy", "").casefold() != "n":
            errors.append(
                f"92-new-evidence-or-experiments.csv:{line}: Remedy must be N"
            )
    if duplicate_evidence_ledgers:
        errors.append(
            "92-new-evidence-or-experiments.csv: each open Remedy=N LedgerID "
            f"must occur once; repeated={sorted(set(duplicate_evidence_ledgers))}"
        )
    compare_sets(
        "92 evidence coverage of open Remedy=N rows",
        set(open_n_rows), set(evidence_by_ledger), errors,
    )
    if list(evidence_by_ledger) != list(open_n_rows):
        errors.append(
            "92-new-evidence-or-experiments.csv: LedgerID row order must exactly "
            "follow open Remedy=N rows in 91-revision-ledger.csv"
        )
    if not args.pre_stage_s:
        academic_summary = read_csv(
            root / "93-current-actionable-items.csv",
            ACADEMIC_SUMMARY_COLUMNS, errors,
            require_rows=bool(open_academic),
        )
        ai_summary = read_csv(
            root / "93-current-ai-actionable-items.csv",
            AI_SUMMARY_COLUMNS, errors, require_rows=bool(open_ai),
        )
        validate_rows_mandatory(
            academic_summary, "93-current-actionable-items.csv",
            ACADEMIC_SUMMARY_COLUMNS, errors,
        )
        validate_rows_mandatory(
            ai_summary, "93-current-ai-actionable-items.csv",
            AI_SUMMARY_COLUMNS, errors,
        )
        academic_summary_by_id = index_unique(
            academic_summary, "LedgerID",
            "93-current-actionable-items.csv", errors,
        )
        ai_summary_by_id = index_unique(
            ai_summary, "AIFindingID",
            "93-current-ai-actionable-items.csv", errors,
        )
        if [row.get("LedgerID", "") for row in academic_summary] != list(open_academic):
            errors.append(
                "93-current-actionable-items.csv: row order must exactly follow the "
                "open 91-revision-ledger.csv row order"
            )
        if [row.get("AIFindingID", "") for row in ai_summary] != list(open_ai):
            errors.append(
                "93-current-ai-actionable-items.csv: row order must exactly follow the "
                "open 91-ai-actionable-ledger.csv row order"
            )
        compare_sets(
            "current academic summary", set(open_academic),
            set(academic_summary_by_id), errors,
        )
        compare_sets(
            "current AI-actionable summary", set(open_ai),
            set(ai_summary_by_id), errors,
        )
        for ledger_id in sorted(set(open_academic) & set(academic_summary_by_id)):
            ledger = open_academic[ledger_id]
            summary = academic_summary_by_id[ledger_id]
            for field in ACADEMIC_SUMMARY_COLUMNS:
                if summary[field] != ledger[field]:
                    errors.append(
                        f"academic 91->93 mismatch for {ledger_id}/{field}: "
                        f"expected {ledger[field]!r}, got {summary[field]!r}"
                    )
        for finding_id in sorted(set(open_ai) & set(ai_summary_by_id)):
            ledger = open_ai[finding_id]
            summary = ai_summary_by_id[finding_id]
            for field in AI_SUMMARY_COLUMNS:
                if summary[field] != ledger[field]:
                    errors.append(
                        f"AI 91->93 mismatch for {finding_id}/{field}: "
                        f"expected {ledger[field]!r}, got {summary[field]!r}"
                    )
        validate_markdown_id_projection(
            root / "93-user-facing-summary.md",
            set(open_academic),
            re.compile(r"(?<![A-Za-z0-9])L\d{2,4}(?![A-Za-z0-9])"),
            {"Ledger ID", "LedgerID"},
            "Stage-S current academic summary",
            errors,
            required_headers={
                "Ledger ID", "Priority", "Chair finding ID",
                "Source reviewer finding IDs", "Severity", "S0 subtype",
                "Remedy", "Exact PDF anchor", "Direct PDF-visible observation",
                "Evidence status", "Minimum required action", "Dependency",
                "Owner", "Chair disposition", "Verification",
            },
            reference_id_headers={"Dependency"},
            reference_id_values=set(academic_by_id),
            section_heading="Current actionable items",
        )
        validate_markdown_id_projection(
            root / "93-user-facing-summary.md",
            set(open_ai),
            re.compile(r"(?<![A-Za-z0-9])AI-F\d{2,4}(?![A-Za-z0-9])"),
            {"AI finding ID", "AIFindingID"},
            "Stage-S current AI summary",
            errors,
            required_headers={
                "AI finding ID", "Impact (`material` / `local`)",
                "Exact PDF anchor", "Direct style observation",
                "Minimum editing action", "Chair status", "Verification",
            },
            section_heading=(
                "Current AI-style actionable items — separate from academic grading"
            ),
        )
        validate_markdown_id_projection(
            root / "93-user-facing-summary.md",
            set(evidence_by_id),
            re.compile(r"(?<![A-Za-z0-9])N\d{2,4}(?![A-Za-z0-9])"),
            {"Evidence item ID", "EvidenceItemID"},
            "Stage-S current N-evidence summary",
            errors,
            required_headers={
                "Evidence item ID", "Ledger ID", "Chair finding ID", "Remedy",
                "Item", "Claim that depends on it", "Why writing is insufficient",
                "Minimum viable evidence", "Consequence if unavailable",
            },
            section_heading="Current new evidence or experiments (N)",
        )
        validate_summary_markdown_values(
            root / "93-user-facing-summary.md",
            academic_summary_by_id,
            ai_summary_by_id,
            evidence_by_id,
            errors,
        )

    evidence_path = root / "92-new-evidence-or-experiments.md"
    if evidence_path.is_file():
        evidence_text = evidence_path.read_text(encoding="utf-8", errors="replace")
        for heading in (
            "No-new-experiment remedies (W/E/P)",
            "Genuine new experiments or unavailable evidence (N)",
        ):
            if not re.search(
                rf"(?im)^[ ]{{0,3}}##[ \t]+{re.escape(heading)}"
                rf"(?:[ \t]+#+)?[ \t]*$",
                markdown_visible_text(evidence_text),
            ):
                errors.append(f"{evidence_path.name}: missing required section {heading!r}")
        no_new_headers = [
            "Ledger ID", "Remedy", "Exact PDF anchor", "Minimum edit/evidence",
            "Verification",
        ]
        no_new_section = markdown_section_body_raw(
            evidence_text, "No-new-experiment remedies (W/E/P)"
        ) or ""
        no_new_rows = parse_markdown_table_by_exact_headers(
            no_new_section, no_new_headers, evidence_path.name, errors
        )
        expected_no_new_rows = [
            markdown_projection_row(
                row,
                (
                    "LedgerID", "Remedy", "ExactPDFAnchor",
                    "MinimumEditEvidence", "Verification",
                ),
            )
            for row in open_academic.values()
            if row.get("Remedy", "").casefold() in {"w", "e", "p"}
        ]
        if no_new_rows is not None and no_new_rows != expected_no_new_rows:
            errors.append(
                f"{evidence_path.name}: W/E/P table must exactly project all open "
                "non-N rows from 91-revision-ledger.csv in ledger order"
            )
        experiment_headers = [
            "Evidence item ID", "Ledger ID", "Chair finding ID", "Remedy", "Item",
            "Claim that depends on it", "Why writing is insufficient",
            "Minimum viable evidence", "Consequence if unavailable",
        ]
        experiment_section = markdown_section_body_raw(
            evidence_text, "Genuine new experiments or unavailable evidence (N)"
        ) or ""
        experiment_rows = parse_markdown_table_by_exact_headers(
            experiment_section, experiment_headers, evidence_path.name, errors
        )
        expected_experiment_rows = markdown_projection_rows(
            evidence_items, EVIDENCE_ITEM_COLUMNS
        )
        if experiment_rows is not None and experiment_rows != expected_experiment_rows:
            errors.append(
                f"{evidence_path.name}: N-evidence table must exactly project "
                "92-new-evidence-or-experiments.csv in row order"
            )

    if expected_hash:
        allowed_governing_sources = process_governing_sources(process)
        rule_public_endpoints = {
            value for value in process.get("governing_rule_urls", [])
            if isinstance(value, str)
        }
        bibliography_public_endpoints = bibliography_ledger_public_endpoints(
            bib_ledger
        )
        citation_public_endpoints = citation_ledger_public_endpoints(
            citation_ledger
        )
        page_bib_owner = "R5" if process.get("degree_level") == "doctorate" else "R3"
        citation_owner = "R4" if process.get("degree_level") == "doctorate" else "R3"
        owner_expected_vectors = build_owner_expected_vectors(
            page_inventory, page_ledger, bib_inventory, bib_ledger,
            citation_inventory, citation_ledger,
        )
        validate_manifest(
            root / "00-manifest.md",
            expected_hash,
            process,
            citation_candidates,
            extracted_unmatched_glyphs,
            root,
            reviewer_count,
            errors,
        )
        validate_declarations(
            root / "01-policy-basis.md", expected_hash, errors,
            process=process, actor_id="P", reviewer_count=reviewer_count,
            allowed_public_endpoints=rule_public_endpoints,
            required_public_endpoints=rule_public_endpoints,
        )
        owned_main_table_headers = {
            "02-page-layout-ledger.md": PAGE_MARKDOWN_HEADERS,
            "03-bibliography-audit-ledger.md": BIB_MARKDOWN_HEADERS,
            "04-citation-claim-audit-ledger.md": CITATION_MARKDOWN_HEADERS,
        }
        for owned_path, actor_id, public_endpoints, required_endpoints in (
            (
                "02-page-layout-ledger.md", page_bib_owner,
                rule_public_endpoints | bibliography_public_endpoints,
                set(),
            ),
            (
                "03-bibliography-audit-ledger.md", page_bib_owner,
                rule_public_endpoints | bibliography_public_endpoints,
                bibliography_public_endpoints,
            ),
            (
                "04-citation-claim-audit-ledger.md", citation_owner,
                rule_public_endpoints | citation_public_endpoints,
                citation_public_endpoints,
            ),
            (
                "91-revision-ledger.md", "C",
                rule_public_endpoints | bibliography_public_endpoints
                | citation_public_endpoints,
                set(),
            ),
            (
                "92-new-evidence-or-experiments.md", "C",
                rule_public_endpoints | bibliography_public_endpoints
                | citation_public_endpoints,
                set(),
            ),
        ):
            owned_text = validate_declarations(
                root / owned_path, expected_hash, errors,
                process=process, actor_id=actor_id,
                reviewer_count=reviewer_count,
                allowed_public_endpoints=public_endpoints,
                required_public_endpoints=required_endpoints,
            )
            expected_headers = owned_main_table_headers.get(owned_path)
            if owned_text and expected_headers is not None:
                validate_declarations_before_main_table(
                    owned_text, expected_headers, owned_path, errors
                )
        for index in range(1, reviewer_count + 1):
            reviewer_public = set(rule_public_endpoints)
            if f"R{index}" == page_bib_owner:
                reviewer_public |= bibliography_public_endpoints
            if f"R{index}" == citation_owner:
                reviewer_public |= citation_public_endpoints
            reviewer_required_public: set[str] = set(rule_public_endpoints)
            if f"R{index}" == page_bib_owner:
                reviewer_required_public |= bibliography_public_endpoints
            if f"R{index}" == citation_owner:
                reviewer_required_public |= citation_public_endpoints
            validate_reviewer_report(
                root / f"R{index}-comprehensive-review.md",
                expected_hash,
                index,
                process,
                reviewer_count,
                reviewer_public,
                reviewer_required_public,
                process.get("degree_level") if isinstance(process, dict) else None,
                (
                    process.get("decision_regime_status")
                    if isinstance(process, dict) else None
                ),
                allowed_governing_sources,
                owner_expected_vectors,
                page_count,
                errors,
            )
        current_reviewer_findings: dict[str, dict[str, str]] = {}
        current_reviewer_questions: dict[str, list[str]] = {}
        persona_emphases: dict[str, str] = {}
        for index in range(1, reviewer_count + 1):
            report_path = root / f"R{index}-comprehensive-review.md"
            if not report_path.is_file():
                continue
            report_text = markdown_visible_text(
                report_path.read_text(encoding="utf-8", errors="replace")
            )
            current_reviewer_findings.update(
                parse_reviewer_findings(
                    report_text, index, report_path.name, page_count, []
                )
            )
            current_reviewer_questions.update(
                parse_reviewer_questions(
                    report_text, index, report_path.name, page_count, []
                )
            )
            projection = reviewer_verdict_projection(report_text)
            persona_emphases[f"R{index}"] = projection.get("persona_emphasis", "")
        duplicate_persona_emphases = [
            emphasis for emphasis, count in Counter(
                value.casefold() for value in persona_emphases.values() if value
            ).items() if count > 1
        ]
        if duplicate_persona_emphases:
            errors.append(
                "reviewer Persona emphasis values must be role-specific and distinct "
                "across the panel"
            )
        current_reviewer_finding_ids = set(current_reviewer_findings)
        current_reviewer_question_ids = set(current_reviewer_questions)
        audit_link_ids = {
            match
            for row in bib_ledger
            for match in re.findall(
                r"R\d+-(?:F|Q)\d{2,4}", row.get("FindingDisposition", "")
            )
        } | {
            match
            for row in citation_ledger
            for field in ("SeverityFinding", "DispositionEvidence")
            for match in re.findall(r"R\d+-(?:F|Q)\d{2,4}", row.get(field, ""))
        }
        unknown_audit_links = sorted(
            audit_link_ids
            - current_reviewer_finding_ids
            - current_reviewer_question_ids
        )
        if unknown_audit_links:
            errors.append(
                "03/04 audit ledgers reference unknown current owning-reviewer "
                f"finding/question IDs {unknown_audit_links}"
            )
        mismatch_audit_links = {
            match
            for row in bib_ledger
            if row.get("Verdict", "").casefold() == "mismatch"
            for match in re.findall(
                r"R\d+-(?:F|Q)\d{2,4}", row.get("FindingDisposition", "")
            )
        } | {
            match
            for row in citation_ledger
            if (
                row.get("Support", "").casefold() == "mismatch"
                or row.get("MetadataStatus", "").casefold() == "mismatch"
            )
            for field in ("SeverityFinding", "DispositionEvidence")
            for match in re.findall(r"R\d+-(?:F|Q)\d{2,4}", row.get(field, ""))
        }
        s4_mismatch_links = sorted(
            finding_id
            for finding_id in mismatch_audit_links
            if finding_id in current_reviewer_findings
            and current_reviewer_findings[finding_id].get("Severity", "").casefold()
            == "s4"
        )
        if s4_mismatch_links:
            errors.append(
                "03/04 mismatch rows cannot be waived as optional S4 findings; "
                f"observed={s4_mismatch_links}"
            )
        required_reviewer_finding_ids = {
            finding_id for finding_id, fields in current_reviewer_findings.items()
            if fields.get("Severity", "").casefold() in {"s0", "s1", "s2", "s3"}
        }
        direct_rejected_finding_ids = validate_chair_report(
            root / "90-chair-synthesis.md",
            expected_hash,
            process,
            bib_inventory,
            bib_ledger,
            citation_inventory,
            citation_ledger,
            academic_ledger,
            required_reviewer_finding_ids,
            set(current_reviewer_questions),
            reviewer_count,
            (
                process.get("decision_regime_status")
                if isinstance(process, dict) else None
            ),
            allowed_governing_sources,
            errors,
        )
        source_id_counts: Counter[str] = Counter()
        def reviewer_finding_sort_key(value: str) -> tuple[int, int]:
            match = re.fullmatch(r"R(\d+)-F(\d{2,4})", value)
            return (
                int(match.group(1)) if match else 10**9,
                int(match.group(2)) if match else 10**9,
            )
        for ledger_id, row in academic_by_id.items():
            source_value = row.get("SourceReviewerFindingIDs", "")
            source_id_list = re.findall(r"R\d+-F\d{2,4}", source_value)
            source_ids = set(source_id_list)
            residue = re.sub(r"R\d+-F\d{2,4}", "", source_value)
            residue = re.sub(r"[\s,，;/|]+", "", residue)
            if not source_ids or residue:
                errors.append(
                    f"91-revision-ledger.csv:{ledger_id}: SourceReviewerFindingIDs "
                    "must contain only current Rn-Fxx IDs"
                )
            canonical_source_value = ", ".join(
                sorted(source_ids, key=reviewer_finding_sort_key)
            )
            if source_value != canonical_source_value:
                errors.append(
                    f"91-revision-ledger.csv:{ledger_id}: SourceReviewerFindingIDs "
                    "must be a canonical duplicate-free comma-space list"
                )
            source_id_counts.update(source_id_list)
            unknown = sorted(source_ids - current_reviewer_finding_ids)
            if unknown:
                errors.append(
                    f"91-revision-ledger.csv:{ledger_id}: unknown current reviewer "
                    f"finding IDs {unknown}"
                )
        missing_source_closure = sorted(
            required_reviewer_finding_ids
            - set(source_id_counts)
            - direct_rejected_finding_ids,
            key=reviewer_finding_sort_key,
        )
        duplicate_path_closure = sorted(
            set(source_id_counts) & direct_rejected_finding_ids,
            key=reviewer_finding_sort_key,
        )
        duplicate_source_closure = sorted(
            (
                finding_id for finding_id, count in source_id_counts.items()
                if count != 1
            ),
            key=reviewer_finding_sort_key,
        )
        if missing_source_closure:
            errors.append(
                "current reviewer findings omitted from Chair adjudication: each "
                "S0-S3 finding must enter 91 or one direct Status=rejected decision; "
                f"missing={missing_source_closure}"
            )
        if duplicate_path_closure:
            errors.append(
                "current reviewer findings cannot enter both 91 and a direct "
                f"Status=rejected decision; repeated={duplicate_path_closure}"
            )
        if duplicate_source_closure:
            errors.append(
                "91-revision-ledger.csv: reviewer finding IDs must be adjudicated "
                f"exactly once; repeated={duplicate_source_closure}"
            )
        validate_ai_report(
            root / "05-ai-style-assessment.md", expected_hash, page_count,
            process, reviewer_count, errors
        )
        ai_report_path = root / "05-ai-style-assessment.md"
        if ai_report_path.is_file():
            ai_report_text = markdown_visible_text(
                ai_report_path.read_text(encoding="utf-8", errors="replace")
            )
            ai_findings = parse_ai_findings(
                ai_report_text, ai_report_path.name, page_count, []
            )
            actionable_ai = {
                finding_id: fields for finding_id, fields in ai_findings.items()
                if fields.get("Impact", "").casefold() in {"material", "local"}
            }
            compare_sets(
                "chair AI-actionable source findings",
                set(actionable_ai),
                set(ai_by_id),
                errors,
            )
            for finding_id in sorted(set(actionable_ai) & set(ai_by_id)):
                source = actionable_ai[finding_id]
                ledger = ai_by_id[finding_id]
                expected_mapping = {
                    "Impact": source["Impact"],
                    "ExactPDFAnchor": source["Location"],
                    "DirectStyleObservation": source["Recurrent evidence"],
                    "MinimumEditingAction": source["Minimum safe editing strategy"],
                    "Verification": source["Closure test"],
                }
                for field, expected_value in expected_mapping.items():
                    if ledger[field] != expected_value:
                        errors.append(
                            f"91-ai-actionable-ledger.csv:{finding_id}: field {field} "
                            "does not exactly project the current AI finding"
                        )
                if ledger["Status"].casefold() != "open":
                    errors.append(
                        f"91-ai-actionable-ledger.csv:{finding_id}: current AI "
                        "finding must enter the chair ledger as open"
                    )
        validate_identical_actor_access_receipts(
            (
                root / "90-chair-synthesis.md",
                root / "91-revision-ledger.md",
                root / "92-new-evidence-or-experiments.md",
            ),
            canonical_stage_opened_inputs(process, reviewer_count, "C", root),
            (
                *governing_rule_public_endpoint_sequence(process),
                *bibliography_ledger_public_endpoint_sequence(bib_ledger),
                *citation_ledger_public_endpoint_sequence(citation_ledger),
            ),
            "C",
            errors,
        )
        chair_path = root / "90-chair-synthesis.md"
        if chair_path.is_file():
            chair_text = markdown_visible_text(
                chair_path.read_text(encoding="utf-8", errors="replace")
            )
            chair_projection = chair_verdict_projection(chair_text)
            if chair_projection["regime"] == "skill-default":
                unresolved_rows = [
                    row for row in academic_by_id.values()
                    if row.get("Status", "").casefold() not in CLOSED_STATUSES
                ]
                required_grade = "A"
                if any(
                    row.get("Severity", "").casefold() == "s0"
                    and row.get("S0Subtype", "").casefold()
                    == "integrity/foundational"
                    for row in unresolved_rows
                ):
                    required_grade = "D"
                elif any(
                    (
                        row.get("Severity", "").casefold() == "s0"
                        and row.get("S0Subtype", "").casefold() == "procedural"
                    )
                    or row.get("Severity", "").casefold() == "s1"
                    or row.get("Remedy", "").casefold() == "n"
                    for row in unresolved_rows
                ):
                    required_grade = "C"
                elif any(
                    row.get("Severity", "").casefold() == "s2"
                    for row in unresolved_rows
                ):
                    required_grade = "B"
                if chair_projection["academic_grade"].upper() != required_grade:
                    errors.append(
                        "90-chair-synthesis.md: overall skill-default grade is "
                        "inconsistent with the open adjudicated severity/remedy profile; "
                        f"expected {required_grade}"
                    )
        if not args.pre_stage_s:
            validate_summary_report(
                root / "93-user-facing-summary.md", expected_hash,
                process, reviewer_count, len(open_academic), len(open_ai),
                len(evidence_by_id), errors,
            )
            validate_stage_v(
                root / "94-post-freeze-prior-issue-closure.md",
                expected_hash,
                process,
                reviewer_count,
                (
                    current_reviewer_finding_ids
                    | {row.get("ChairFindingID", "") for row in academic_ledger}
                    | set(ai_by_id)
                ) - {""},
                current_reviewer_findings,
                page_inventory,
                page_ledger,
                bib_inventory,
                bib_ledger,
                citation_inventory,
                citation_ledger,
                academic_ledger,
                ai_ledger,
                errors,
            )
        validate_helper_bundle(
            root, expected_hash, process, reviewer_count, errors
        )

    if validation_report_path is not None:
        late_destination_errors: list[str] = []
        if validate_write_report_destination(
            root, validation_report_path, late_destination_errors
        ) is None:
            errors.extend(late_destination_errors)
            validation_report_path = None

    def render_report() -> str:
        status = "PASS" if not errors else "FAIL"
        lines = [
            "# Mechanical thesis-review bundle validation", "",
            f"- Result: **{status}**",
            f"- Round directory: {root}",
            f"- Frozen PDF SHA-256: {expected_hash or 'missing'}",
            f"- Errors: {len(errors)}",
            f"- Warnings: {len(warnings)}",
            "- Boundary: mechanical validation only; semantic reviewer sign-off "
            "remains mandatory.",
            "", "## Errors", "",
            *(f"- {item}" for item in errors),
            *(["- none"] if not errors else []),
            "", "## Warnings", "",
            *(f"- {item}" for item in warnings),
            *(["- none"] if not warnings else []), "",
        ]
        return "\n".join(lines)

    report = render_report()
    if validation_report_path is not None:
        write_error = atomic_write_validation_report(validation_report_path, report)
        if write_error is not None:
            errors.append(write_error)
            report = render_report()
    print(report)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
