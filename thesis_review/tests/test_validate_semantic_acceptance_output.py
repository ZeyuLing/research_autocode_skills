from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pypdf
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


SKILL_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = SKILL_ROOT / "scripts" / "validate_semantic_acceptance_output.py"
MATERIALIZER_PATH = SKILL_ROOT / "scripts" / "materialize_semantic_acceptance_gate.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module(VALIDATOR_PATH, "test_semantic_acceptance_validator")
MATERIALIZER_MODULE = load_module(
    MATERIALIZER_PATH, "test_semantic_acceptance_materializer"
)
SHARED = MODULE.load_shared_validator()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_csv(path: Path, headers: list[str] | tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers))
        writer.writeheader()
        writer.writerows(rows)


def add_ascii_text(writer: PdfWriter, page: object, text: str) -> None:
    escaped_lines = [
        line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        for line in text.splitlines() or [""]
    ]
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    resources = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    stream = DecodedStreamObject()
    commands = ["BT /F1 12 Tf 72 720 Td"]
    for index, escaped in enumerate(escaped_lines):
        if index:
            commands.append("0 -18 Td")
        commands.append(f"({escaped}) Tj")
    commands.append("ET")
    stream.set_data(" ".join(commands).encode("ascii"))
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = writer._add_object(stream)


def remove_ephemeral_sa_view_rules(root: Path) -> None:
    for name in (
        "SKILL.md",
        "clean-room-orchestration.md",
        "china-policy.md",
        "grading-and-verdicts.md",
        "review-rubric.md",
        "reviewer-panels.md",
        "report-template.md",
        "ledger-validation.md",
        "rendered-pagination-audit.md",
        "citation-audit.md",
        "ai-style-audit.md",
    ):
        (root / name).unlink(missing_ok=True)
    shutil.rmtree(root / "rules", ignore_errors=True)


def retain_scoped_actor_view(
    root: Path, process: dict[str, object], target: str
) -> None:
    keep = set(MODULE.canonical_sa_opened_inputs(root, process, target, []))
    keep.update({f"SA-{target}.md", f"SA-{target}.csv"})
    allowed_dirs = {
        Path(item).parts[0]
        for item in keep
        if len(Path(item).parts) > 1
    }
    for path in list(root.iterdir()):
        if path.is_file() and path.name not in keep:
            path.unlink()
        elif path.is_dir() and path.name not in allowed_dirs:
            shutil.rmtree(path)


def overwrite_same_length_and_restore_mtime(path: Path) -> None:
    metadata = path.stat()
    payload = bytearray(path.read_bytes())
    index = next(
        index
        for index in range(len(payload) - 1, -1, -1)
        if payload[index] not in {10, 13}
    )
    payload[index] = ord("!") if payload[index] != ord("!") else ord("?")
    with path.open("r+b") as handle:
        handle.seek(0)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))


class SemanticAcceptanceFixture:
    endpoint = "https://example.org/source"

    def __init__(self, root: Path, degree: str = "masters") -> None:
        self.root = root
        self.degree = degree
        self.targets = ["R1", "R2", "R3", "AI"] if degree == "masters" else [
            "R1", "R2", "R3", "R4", "R5", "AI"
        ]
        self.pdf_name = "frozen-thesis.pdf"
        writer = PdfWriter()
        abstract_pages = [
            (
                "CHINESE ABSTRACT\nSynthetic Chinese abstract prose states the "
                "research task, method, and principal result. It contains sustained "
                "explanatory evidence; the prose is long enough for independent "
                "semantic inspection."
            ),
            (
                "ABSTRACT\nSynthetic English abstract prose states the research "
                "task, method, and principal result. It contains sustained explanatory "
                "evidence; the prose is long enough for independent semantic inspection."
            ),
        ]
        for text_value in abstract_pages:
            page = writer.add_blank_page(width=595, height=842)
            add_ascii_text(writer, page, text_value)
        for number, title in ((1, "Introduction"), (2, "Methods"), (3, "Results")):
            page = writer.add_blank_page(width=595, height=842)
            add_ascii_text(
                writer,
                page,
                f"CHAPTER {number}\n{title}\n{number}.1 Section",
            )
        bibliography_page = writer.add_blank_page(width=595, height=842)
        add_ascii_text(
            writer,
            bibliography_page,
            "REFERENCES\n[1] Synthetic Reference Title. Example venue, 2026.",
        )
        with (root / self.pdf_name).open("wb") as handle:
            writer.write(handle)
        self.pdf_hash = digest(root / self.pdf_name)
        prompt_actors = [
            "P",
            *(f"R{index}" for index in range(1, 6 if degree == "doctorate" else 4)),
            "AI",
            *(f"SA-R{index}" for index in range(1, 6 if degree == "doctorate" else 4)),
            "SA-AI",
            "C",
            "S",
        ]
        self.process = {
            "round_id": "round-clean",
            "retry_id": "retry-clean",
            "frozen_pdf_file": self.pdf_name,
            "selected_pdf_sha256": self.pdf_hash,
            "physical_page_count": 6,
            "frozen_at": "2026-09-01T00:00:00+08:00",
            "degree_level": degree,
            "degree_type": "academic",
            "institution": "Example University",
            "school_or_department": "Example School",
            "discipline": "Computer Science",
            "expected_submission_year": 2026,
            "artifact_type": "blind-copy",
            "review_mode": "fresh-rereview",
            "output_language": "zh-CN",
            "governing_rule_urls": [],
            "governing_local_files": [],
            "decision_regime_status": "skill-default",
            "actor_prompt_sha256": {
                actor: hashlib.sha256(f"prompt-{actor}".encode()).hexdigest().upper()
                for actor in prompt_actors
            },
        }
        (root / "00-process-parameters.json").write_text(
            json.dumps(self.process, indent=2), encoding="utf-8"
        )
        for name in (
            "SKILL.md",
            "clean-room-orchestration.md",
            "china-policy.md",
            "grading-and-verdicts.md",
            "review-rubric.md",
            "reviewer-panels.md",
            "report-template.md",
            "ledger-validation.md",
            "rendered-pagination-audit.md",
            "citation-audit.md",
            "ai-style-audit.md",
        ):
            (root / name).write_text(f"fixture {name}\n", encoding="utf-8")
        rules_scripts = root / "rules" / "scripts"
        rules_scripts.mkdir(parents=True)
        for name in (
            "validate_review_bundle.py",
            "validate_semantic_acceptance_output.py",
        ):
            (rules_scripts / name).write_text(f"fixture {name}\n", encoding="utf-8")
        (root / "00-manifest.md").write_text(
            "# Manifest\n\n## Objective inventories and locations\n\n"
            "- Sections: 1.1=physical p.3; 2.1=physical p.4; 3.1=physical p.5\n"
            "- Authored-prose navigation pages: physical p.1-5\n"
            f"- PDF extraction runtime: pypdf={pypdf.__version__}\n",
            encoding="utf-8",
        )
        (root / "01-policy-basis.md").write_text(
            "# Policy basis\n\nSkill-default regime.\n", encoding="utf-8"
        )
        write_csv(
            root / "00-page-inventory.csv",
            ["PageID", "Region"],
            [
                {"PageID": "P0001", "Region": "front"},
                {"PageID": "P0002", "Region": "front"},
                {"PageID": "P0003", "Region": "chapter 1"},
                {"PageID": "P0004", "Region": "chapter 2"},
                {"PageID": "P0005", "Region": "chapter 3"},
                {"PageID": "P0006", "Region": "references"},
            ],
        )
        write_csv(
            root / "00-bibliography-inventory.csv",
            SHARED.BIB_INVENTORY_COLUMNS,
            [
                {
                    "ReferenceID": "REF0001",
                    "DisplayedLabel": "[1]",
                    "RenderedEntry": "Synthetic Reference Title. Example venue, 2026.",
                    "Cited": "yes",
                    "PDFSHA256": self.pdf_hash,
                }
            ],
        )
        write_csv(root / "00-citation-candidate-ledger.csv", ["CandidateID"], [{"CandidateID": "BC0001"}])
        write_csv(root / "00-unmatched-bracket-ledger.csv", ["GlyphID"], [{"GlyphID": "UBG0001"}])
        write_csv(
            root / "00-citation-inventory.csv",
            SHARED.CITATION_INVENTORY_COLUMNS,
            [
                {
                    "PairID": "C0001-S01",
                    "OccurrenceID": "C0001",
                    "PDFLocation": "physical p.3",
                    "DisplayedReferenceID": "REF0001",
                    "AdjacentPDFText": "Prior work motivates the method [1].",
                    "PDFSHA256": self.pdf_hash,
                }
            ],
        )
        write_csv(
            root / "02-page-layout-ledger.csv",
            ["PageID"],
            [
                {"PageID": "P0001"},
                {"PageID": "P0002"},
                {"PageID": "P0003"},
                {"PageID": "P0004"},
                {"PageID": "P0005"},
                {"PageID": "P0006"},
            ],
        )
        (root / "02-page-layout-ledger.md").write_text("layout\n", encoding="utf-8")
        write_csv(
            root / "03-bibliography-audit-ledger.csv",
            SHARED.BIB_LEDGER_COLUMNS,
            [
                {
                    "ReferenceID": "REF0001",
                    "DisplayedLabel": "[1]",
                    "Cited": "yes",
                    "Field": field,
                    "RenderedValue": f"rendered-{field}-value",
                    "CanonicalValue": f"canonical-{field}-value",
                    "Verdict": "exact",
                    "EvidenceEndpoint": self.endpoint,
                    "EndpointType": "publisher",
                    "CheckedAt": "2026-09-01T00:00:00+08:00",
                    "EvidenceNote": "checked authoritative record",
                    "FindingDisposition": "reasoned non-finding: exact field match",
                    "PDFSHA256": self.pdf_hash,
                }
                for field in SHARED.BIB_FIELD_ORDER
            ],
        )
        (root / "03-bibliography-audit-ledger.md").write_text(
            self.target_receipt(), encoding="utf-8"
        )
        write_csv(
            root / "04-citation-claim-audit-ledger.csv",
            SHARED.CITATION_LEDGER_COLUMNS,
            [
                {
                    "PairID": "C0001-S01",
                    "OccurrenceID": "C0001",
                    "PDFLocation": "physical p.3",
                    "ExactAttachedProposition": "Prior work defines a high-level objective for this method.",
                    "ReferenceID": "REF0001",
                    "PublicIdentifier": "doi:10.0000/example",
                    "ContentSourceOpened": self.endpoint,
                    "ExactSourceLocator": "Section 2",
                    "Support": "direct",
                    "MetadataStatus": "verified",
                    "SeverityFinding": "none",
                    "DispositionEvidence": "reasoned non-finding: checked source",
                    "PDFSHA256": self.pdf_hash,
                }
            ],
        )
        (root / "04-citation-claim-audit-ledger.md").write_text(
            self.target_receipt(), encoding="utf-8"
        )
        render_dir = root / "page-renders"
        render_dir.mkdir()
        for page_id in ("P0001", "P0002", "P0003", "P0004", "P0005", "P0006"):
            (render_dir / f"{page_id}.png").write_bytes(
                f"synthetic png {page_id}".encode()
            )
        for target in self.targets:
            report = root / MODULE.actor_report_name(target)
            if target == "AI":
                report_body = "# AI style assessment\n\n## Findings\n\nnone\n"
            else:
                report_body = self.reviewer_report_body(target)
            report.write_text(
                self.target_receipt() + "\n" + report_body,
                encoding="utf-8",
            )

    def reviewer_report_body(self, target: str) -> str:
        header = "| " + " | ".join(SHARED.REVIEWER_ASSESSMENT_HEADERS) + " |"
        separator = "|" + "|".join("---" for _ in SHARED.REVIEWER_ASSESSMENT_HEADERS) + "|"
        gate_rows = "\n".join(
            f"| {gate} | baseline | adequate | physical p.3, inspected thesis passage for Gate {gate} | none | high confidence within the frozen PDF |"
            for gate in "ABCDEFGHI"
        )
        synthesis = "\n".join(
            f"- {label}: Parsed synthesis statement {index} connects the complete thesis argument to its frozen evidence and bounded conclusion."
            for index, label in enumerate(MODULE.SYNTHESIS_PROJECTION_LABELS, start=1)
        )
        return f"""# Reviewer {target}

## Role, scope, and independence

- Persona assignment: fixture persona for {target}
- Persona emphasis: fixture holistic emphasis for {target}

## Verdict

- Decision regime: skill-default
- Official category: N/A
- Official defense recommendation: N/A
- Governing source: N/A
- Academic grade: A
- Defense recommendation: {SHARED.DEFAULT_RECOMMENDATIONS['A']}
- Confidence: high
- One-paragraph whole-thesis rationale: The complete frozen thesis presents a coherent synthetic argument whose reported claims are proportionately connected to the inspected evidence and stated limitations.

## Whole-thesis synthesis

{synthesis}

## Whole-thesis assessment

{header}
{separator}
{gate_rows}

## Findings

none

## Questions, not findings

| Question ID | Exact PDF anchor | Question | Why unresolved | Needed clarification/evidence |
|---|---|---|---|---|
"""

    def install_reviewer_finding(self, target: str) -> dict[str, str]:
        reviewer_index = int(target[1:])
        finding_id = f"{target}-F01"
        fields = {
            "Observation": (
                "The rendered paragraph makes a bounded unsupported statement."
            ),
            "Required action": (
                "Narrow the wording and add the missing PDF-visible qualification."
            ),
        }
        block = f"""## Findings

### {finding_id} — Bounded finding
- Primary gate: A
- Secondary gates: none
- Scope: local
- Severity: S2
- S0 subtype: N/A
- Remedy: W
- Required for the current defense conclusion: yes, because the claim is central
- Location: physical p.3
- Observation: {fields['Observation']}
- Why it matters: The statement changes how the method contribution is interpreted.
- Evidence: The exact paragraph and neighboring method definition expose the gap.
- Required action: {fields['Required action']}
- Verification: Re-read the revised paragraph and its surrounding definition carefully.
- Confidence: high
"""
        report_path = self.root / f"R{reviewer_index}-comprehensive-review.md"
        text = report_path.read_text(encoding="utf-8")
        text = text.replace("## Findings\n\nnone\n", block).replace(
            f"| A | baseline | adequate | physical p.3, inspected thesis passage for Gate A | none | high confidence within the frozen PDF |",
            f"| A | baseline | concern | physical p.3, inspected thesis passage for Gate A | {finding_id} | high confidence within the frozen PDF |",
        )
        report_path.write_text(text, encoding="utf-8")
        return fields

    def target_receipt(self) -> str:
        return (
            "- Input-receipt/access declaration: received=[operational prompt]; "
            f"opened=[dummy]; public_endpoints=[{self.endpoint}]; "
            "no unlisted substantive assertion was received; "
            "no prohibited context/artifact was used; neighboring paths were not enumerated\n"
        )

    def acceptance_rows(self, target: str) -> list[dict[str, str]]:
        errors: list[str] = []
        report_units, report_anchors = MODULE.authoritative_report_units(
            self.root, self.process, target, SHARED, errors
        )
        units = MODULE.expected_units(
            self.root,
            self.process,
            target,
            errors,
            SHARED,
            report_units=report_units,
        )
        if errors:
            raise AssertionError(errors)
        artifacts = MODULE.target_artifacts(self.root, self.process, target, errors)
        if errors:
            raise AssertionError(errors)
        report = MODULE.actor_report_name(target)
        reviewer_profile = (
            {}
            if target == "AI"
            else MODULE.reviewer_semantic_target_profile(
                self.root,
                self.process,
                target,
                SHARED,
                errors,
            )
        )
        if errors:
            raise AssertionError(errors)
        rows: list[dict[str, str]] = []
        for index, (unit_type, unit_id) in enumerate(units, start=1):
            if unit_type == "page":
                artifact = MODULE.required_artifact_for_unit(target, unit_type, unit_id)
                anchor = f"physical p.{int(unit_id[1:])}, visible page content"
                basis = f"Page-specific inspection confirms the rendered content for {unit_id} is represented accurately."
            elif unit_type == "bibliography-field":
                artifact = "03-bibliography-audit-ledger.csv"
                field = unit_id.split("/", 1)[1]
                rendered_value = f"rendered-{field}-value"
                canonical_value = f"canonical-{field}-value"
                anchor = (
                    f"physical p.6, {self.endpoint}, official record: {field}"
                )
                field_basis = {
                    "type": "Publisher metadata identifies the document category, which agrees with the audited rendered entry.",
                    "title": "The authority displays the complete work title; word order and substantive punctuation match the ledger.",
                    "ordered_authors": "The opened record supplies an ordered creator list, and the ledger preserves that sequence exactly.",
                    "year": "The publication year shown by the authority is the same year transcribed from the bibliography.",
                    "venue": "Proceedings metadata names the publication venue, allowing a direct comparison with the rendered venue text.",
                    "publication_status": "The official record establishes the work's publication state and supports the row's status disposition.",
                    "volume": "Volume metadata is checked as its own scalar, including whether the authority legitimately omits it.",
                    "issue": "Issue information is compared independently rather than inferred from a neighboring bibliographic field.",
                    "pages_or_article_number": "The authority's pagination or article identifier is reconciled with the exact rendered locator.",
                    "doi": "The DOI field is tested against the persistent identifier exposed by the official metadata record.",
                    "arxiv_id": "The preprint identifier is verified only when the opened authority explicitly exposes that identifier.",
                    "arxiv_version": "Version state is checked separately from the base preprint identifier and is not silently inferred.",
                    "url": "The complete governing URL is compared character by character with the cross-page rendered address.",
                    "access_date": "The access-date disposition follows whether this bibliography style and rendered entry require such a date.",
                    "isbn_or_other_persistent_id": "A book or alternate persistent identifier is accepted only when the authoritative record supplies it.",
                    "existence": "The opened publication record demonstrates that the cited work exists as the identified scholarly object.",
                    "retraction_withdrawal_correction_superseding": "Current publisher status is inspected for retraction, withdrawal, correction, or superseding notices.",
                }[field]
                basis = (
                    f"rendered cue: {rendered_value}; authority cue: "
                    f"{canonical_value}; audited verdict: exact; {field_basis}"
                )
            elif unit_type == "citation-pair":
                artifact = "04-citation-claim-audit-ledger.csv"
                citation_rows = MODULE.read_generic_csv(
                    self.root / "04-citation-claim-audit-ledger.csv", []
                )
                citation_row = next(
                    row for row in citation_rows if row.get("PairID") == unit_id
                )
                proposition = citation_row["ExactAttachedProposition"]
                source_locator = citation_row["ExactSourceLocator"]
                inventory_rows = MODULE.read_generic_csv(
                    self.root / "00-citation-inventory.csv", []
                )
                inventory_row = next(
                    row for row in inventory_rows if row.get("PairID") == unit_id
                )
                rendered_reference_ids = {
                    row.get("ReferenceID", "")
                    for row in MODULE.read_generic_csv(
                        self.root / "00-bibliography-inventory.csv", []
                    )
                }
                reference_id = citation_row["ReferenceID"]
                dangling = reference_id not in rendered_reference_ids
                support = citation_row["Support"].casefold()
                metadata_status = citation_row["MetadataStatus"].casefold()
                disposition_evidence = citation_row["DispositionEvidence"]
                if dangling:
                    marker_match = re.fullmatch(r"REF(\d+)", reference_id)
                    marker = (
                        f"[{int(marker_match.group(1))}]"
                        if marker_match is not None else reference_id
                    )
                    gap = (
                        f"{reference_id} has "
                        f"{SHARED.DANGLING_REFERENCE_SENTINEL}"
                    )
                    anchor = (
                        f"{inventory_row['PDFLocation']}, displayed marker "
                        f"{marker} and rendered bibliography gap"
                    )
                    basis = (
                        f"PDF-visible location: {inventory_row['PDFLocation']}; "
                        f"displayed marker: {marker}; rendered reference gap: "
                        f"{gap}; audited support: {support}; audited metadata "
                        f"status: {metadata_status}; authoritative 04 disposition: "
                        f"{disposition_evidence}; the exact thesis proposition "
                        f"{proposition} is attached to this unresolved marker."
                    )
                elif (
                    support == "unverifiable"
                    and not citation_row["ContentSourceOpened"]
                    and not source_locator
                ):
                    anchor = (
                        f"{inventory_row['PDFLocation']}, exact citation "
                        "occurrence with no opened content source"
                    )
                    basis = (
                        f"audited support: {support}; audited metadata status: "
                        f"{metadata_status}; authority access limitation: "
                        f"{disposition_evidence}; the exact thesis proposition "
                        f"{proposition} remains bound to {unit_id}, while this "
                        "acceptance claims only the documented access limitation "
                        "and no source-content support."
                    )
                else:
                    anchor = (
                        f"{citation_row['ContentSourceOpened']}, {source_locator}, "
                        f"{inventory_row['PDFLocation']}"
                    )
                    basis = (
                        f"{source_locator} of the opened source supports the exact "
                        f"thesis proposition {proposition} bound to {unit_id}."
                    )
            elif unit_type == "finding":
                artifact = MODULE.required_artifact_for_unit(target, unit_type, unit_id)
                target_page = report_anchors[(unit_type, unit_id)]
                fields = reviewer_profile["findings"][unit_id]
                anchor = (
                    f"physical p.{target_page}, exact target finding and supporting passage"
                )
                basis = json.dumps({
                    "assessment_standard": MODULE.REASONABLE_SUPPORT_STANDARD,
                    "premise_class": "explicit-positive",
                    "target_premise": fields["Observation"],
                    "supporting_pdf_evidence": f"physical p.{target_page}, the exact observed passage supports the bounded finding",
                    "whole_pdf_resolution": {
                        "status": "responsive-passages-reviewed",
                        "pages": [f"physical p.{target_page}"],
                        "search_concepts": ["the finding's bounded proposition and its relevant terminology"],
                        "detail": "The responsive passage was reviewed in the context of the complete frozen PDF.",
                    },
                    "residual_gap": {
                        "status": MODULE.REASONABLY_SUPPORTED,
                        "detail": "A reasonable reviewer could retain the stated limitation within the target finding's documented scope even if another reviewer would assign it less weight.",
                    },
                    "action_delta": {
                        "status": "same-as-target-required-action",
                        "detail": fields["Required action"],
                        "independent_reason": "The PDF evidence leaves the target remedy necessary without broadening it.",
                    },
                    "admissibility_result": MODULE.REASONABLY_SUPPORTED,
                }, ensure_ascii=False, separators=(",", ":"))
            elif unit_type in {
                "gate", "chapter", "question", "ai-finding"
            }:
                artifact = MODULE.required_artifact_for_unit(target, unit_type, unit_id)
                if unit_type == "chapter":
                    anchor = (
                        f"physical p.{int(unit_id.split('-', 1)[1]) + 2}, "
                        "exact chapter passage"
                    )
                elif (unit_type, unit_id) in report_anchors:
                    anchor = (
                        f"physical p.{report_anchors[(unit_type, unit_id)]}, "
                        "exact target-unit passage"
                    )
                else:
                    anchor = "physical p.1-5, representative exact thesis clauses"
                if unit_type == "gate":
                    gate = reviewer_profile["gates"][unit_id]
                    gate_concept = {
                        "Gate-A": "problem formulation and research significance",
                        "Gate-B": "technical correctness and methodological validity",
                        "Gate-C": "novelty and contribution boundaries",
                        "Gate-D": "experimental design and comparative evidence",
                        "Gate-E": "claim calibration and inferential support",
                        "Gate-F": "thesis organization and cross-chapter continuity",
                        "Gate-G": "terminology clarity and scholarly expression",
                        "Gate-H": "citation attachment and bibliographic integrity",
                        "Gate-I": "submission readiness and defense risk",
                    }[unit_id]
                    basis = json.dumps({
                        "assessment_standard": MODULE.REASONABLE_SUPPORT_STANDARD,
                        "gate_id": unit_id,
                        "target_disposition": gate["target_disposition"],
                        "target_decisive_evidence": gate["target_decisive_evidence"],
                        "target_related_finding_ids": gate["target_related_finding_ids"],
                        "independent_pdf_assessment": {
                            "supporting_pdf_evidence": f"{gate['target_decisive_evidence']}, independently checked for {gate_concept}",
                            "counterevidence_reviewed": f"physical p.4, neighboring discussion bearing on {gate_concept} was checked for an answer or qualification.",
                            "admissibility_reason": f"The cited {gate_concept} evidence makes this bounded Gate disposition reasonably supportable even if another reviewer would assign different weight.",
                        },
                        "admissibility_result": MODULE.REASONABLY_SUPPORTED,
                    }, ensure_ascii=False, separators=(",", ":"))
                elif unit_type == "chapter":
                    basis = (
                        f"Chapter-wide PDF reading for {unit_id} traces its methods, "
                        "experiments, limitations, and the target review's treatment."
                    )
                elif unit_type == "question":
                    question = reviewer_profile["questions"][unit_id]
                    basis = json.dumps({
                        "assessment_standard": MODULE.REASONABLE_SUPPORT_STANDARD,
                        "target_question": question["target_question"],
                        "target_why_unresolved": question["target_why_unresolved"],
                        "target_needed_evidence": question["target_needed_evidence"],
                        "target_page": question["target_page"],
                        "whole_pdf_resolution": {
                            "status": "responsive-passages-reviewed",
                            "pages": [question["target_page"]],
                            "search_concepts": ["the protocol choice and the terminology used by the unresolved question"],
                            "detail": "The responsive passages were checked across the frozen PDF and still leave the bounded clarification reasonably open.",
                        },
                        "admissibility_result": MODULE.REASONABLY_SUPPORTED,
                    }, ensure_ascii=False, separators=(",", ":"))
                else:
                    basis = (
                        f"Item-level frozen-PDF verification for {unit_id} confirms "
                        f"the bounded {unit_type} conclusion against its cited passage."
                    )
            elif unit_type == "verdict":
                artifact = MODULE.required_artifact_for_unit(target, unit_type, unit_id)
                anchor = "physical p.1-5, target report verdict and frozen-PDF synthesis"
                basis = json.dumps({
                    key: reviewer_profile[key]
                    for key in MODULE.VERDICT_SEMANTIC_BASIS_LABELS
                }, ensure_ascii=False, separators=(",", ":"))
            else:
                artifact = MODULE.required_artifact_for_unit(target, unit_type, unit_id)
                anchor = "physical p.1-5, target report verdict and frozen-PDF synthesis"
                basis = f"The target conclusion for {unit_id} is internally consistent with its complete accepted evidence."
            rows.append(
                {
                    "AcceptanceRowID": f"SA{index:06d}",
                    "TargetUnitType": unit_type,
                    "TargetUnitID": unit_id,
                    "TargetArtifact": artifact,
                    "TargetArtifactSHA256": digest(self.root / artifact),
                    "CheckClass": MODULE.CHECK_CLASS_BY_UNIT_TYPE[unit_type],
                    "AcceptanceDisposition": "pass",
                    "EvidenceAnchor": anchor,
                    "SemanticBasis": basis,
                }
            )
        return rows

    def write_acceptance(self, target: str, directory: Path) -> None:
        rows = self.acceptance_rows(target)
        errors: list[str] = []
        opened = MODULE.canonical_sa_opened_inputs(
            self.root, self.process, target, errors
        )
        artifacts = MODULE.target_artifacts(self.root, self.process, target, errors)
        if errors:
            raise AssertionError(errors)
        allowed_public = MODULE.target_public_endpoints(
            self.root, self.process, target, SHARED, errors
        )
        public = "; ".join(sorted(allowed_public)) if allowed_public else "none"
        receipt = (
            "received=[operational prompt]; opened=["
            + "; ".join(opened)
            + f"]; public_endpoints=[{public}]; "
            "no unlisted substantive assertion was received; "
            "no prohibited context/artifact was used; neighboring paths were not enumerated"
        )
        hashes = ";".join(
            f"{name}@{digest(self.root / name)}" for name in artifacts
        )
        markdown = f"""# Semantic acceptance — {target}

## Identity and access

- Actor ID: SA-{target}
- Target actor ID: {target}
- Review round ID: {self.process['round_id']}
- Review retry ID: {self.process['retry_id']}
- Operational prompt SHA-256: {self.process['actor_prompt_sha256'][f'SA-{target}']}
- Frozen PDF SHA-256 at start and end: {self.pdf_hash}; {self.pdf_hash}
- Fresh-context declaration: {MODULE.FRESH_CONTEXT_SENTENCE}
- Input-receipt/access declaration: {receipt}
- Semantic-acceptance boundary: {MODULE.BOUNDARY_SENTENCE}

## Target hash binding and coverage

- Target artifact hashes: {hashes}
- Coverage row count: {len(rows)}

## Acceptance result

- Overall semantic acceptance: PASS
- Acceptance failure count: 0
- Limitations: Semantic acceptance is bounded to the frozen PDF, target outputs, and declared public authority.
"""
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"SA-{target}.md").write_text(markdown, encoding="utf-8")
        write_csv(directory / f"SA-{target}.csv", MODULE.CSV_COLUMNS, rows)

class ValidateSemanticAcceptanceOutputTests(unittest.TestCase):
    def run_validator(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys_executable(), "-B", str(VALIDATOR_PATH), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def run_materializer(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys_executable(), "-B", str(MATERIALIZER_PATH), str(root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_single_actor_view_passes_and_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            # Remove artifacts that are outside the canonical single-R1 view.
            keep = set(MODULE.canonical_sa_opened_inputs(root, fixture.process, "R1", []))
            keep.update({"SA-R1.md", "SA-R1.csv"})
            for path in list(root.iterdir()):
                if path.is_file() and path.name not in keep:
                    path.unlink()
                elif path.is_dir() and path.name not in {
                    Path(item).parts[0]
                    for item in keep
                    if len(Path(item).parts) > 1
                }:
                    import shutil

                    shutil.rmtree(path)
            before = {path.name: digest(path) for path in root.iterdir() if path.is_file()}
            errors, result = MODULE.validate_actor(
                root, "R1", SHARED, enforce_closed_view=True
            )
            cli = self.run_validator(str(root), "R1")
            after = {path.name: digest(path) for path in root.iterdir() if path.is_file()}
            self.assertEqual([], errors)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(0, cli.returncode, cli.stdout + cli.stderr)
            self.assertTrue(cli.stdout.startswith("PASS\n"), cli.stdout)
            self.assertEqual(before, after)

    def test_actor_terminal_closure_rejects_post_preflight_late_drift(self) -> None:
        for mutation_kind in ("hardlink", "topology", "bytes"):
            with (
                self.subTest(mutation_kind=mutation_kind),
                tempfile.TemporaryDirectory() as directory,
            ):
                base = Path(directory)
                root = base / "actor-view"
                root.mkdir()
                fixture = SemanticAcceptanceFixture(root)
                fixture.write_acceptance("R1", root)
                retain_scoped_actor_view(root, fixture.process, "R1")
                target = root / "SA-R1.md"
                alias = base / "SA-R1-late-alias.md"
                original_preflight = MODULE.preflight_tree_no_reparse
                calls = 0

                def mutate_after_terminal_preflight(*args, **kwargs):
                    nonlocal calls
                    snapshot = original_preflight(*args, **kwargs)
                    calls += 1
                    if calls == 2:
                        if mutation_kind == "hardlink":
                            os.link(target, alias)
                        elif mutation_kind == "topology":
                            (root / "late-extra.txt").write_text(
                                "late topology drift\n", encoding="utf-8"
                            )
                        else:
                            overwrite_same_length_and_restore_mtime(target)
                    return snapshot

                with mock.patch.object(
                    MODULE,
                    "preflight_tree_no_reparse",
                    side_effect=mutate_after_terminal_preflight,
                ):
                    errors, result = MODULE.validate_actor(
                        root, "R1", SHARED, enforce_closed_view=True
                    )
                self.assertEqual(2, calls)
                self.assertIsNone(result)
                self.assertTrue(errors)
                expected_error = (
                    "terminal topology closure mismatch"
                    if mutation_kind == "topology"
                    else "terminal file identity or bytes closure mismatch"
                )
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )
                if mutation_kind == "hardlink":
                    self.assertEqual(2, target.stat().st_nlink)

    def test_ordinary_acceptance_requires_every_rendered_body_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            rows = MODULE.read_csv_rows(root / "SA-R1.csv", [])
            chapter_units = [
                row["TargetUnitID"]
                for row in rows
                if row["TargetUnitType"] == "chapter"
            ]
            self.assertEqual(["Chapter-1", "Chapter-2", "Chapter-3"], chapter_units)
            self.assertEqual(
                [("gate", f"Gate-{letter}") for letter in "ABCDEFGHI"],
                [
                    (row["TargetUnitType"], row["TargetUnitID"])
                    for row in rows[:9]
                ],
            )
            rows = [row for row in rows if row["TargetUnitID"] != "Chapter-2"]
            write_csv(root / "SA-R1.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("coverage sequence mismatch" in error for error in errors), errors)

    def test_chapter_row_must_anchor_its_own_rendered_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            csv_path = root / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            chapter_three = next(
                row
                for row in rows
                if row["TargetUnitType"] == "chapter"
                and row["TargetUnitID"] == "Chapter-3"
            )
            chapter_three["EvidenceAnchor"] = "physical p.1-4, generic whole-thesis range"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("Chapter-3" in error and "rendered physical p.5-5" in error for error in errors),
                errors,
            )

    def test_reference_page_chapter_like_title_is_not_a_body_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "frozen.pdf"
            writer = PdfWriter()
            for number in (1, 2, 3, 99):
                page = writer.add_blank_page(width=595, height=842)
                add_ascii_text(
                    writer,
                    page,
                    f"CHAPTER {number}\nRendered title\n{number}.1 Section",
                )
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            write_csv(
                root / "00-page-inventory.csv",
                ["PageID", "Region"],
                [
                    {"PageID": "P0001", "Region": "chapter 1"},
                    {"PageID": "P0002", "Region": "chapter 2"},
                    {"PageID": "P0003", "Region": "chapter 3"},
                    {"PageID": "P0004", "Region": "references"},
                ],
            )
            errors: list[str] = []
            intervals = MODULE.rendered_chapter_intervals(
                root, {"frozen_pdf_file": pdf_path.name}, SHARED, errors
            )
            self.assertEqual([], errors)
            self.assertEqual(
                [("Chapter-1", 1, 1), ("Chapter-2", 2, 2), ("Chapter-3", 3, 3)],
                intervals,
            )

    def test_ai_coverage_uses_authored_prose_pages_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("AI", root)
            rows = MODULE.read_csv_rows(root / "SA-AI.csv", [])
            page_units = [
                row["TargetUnitID"]
                for row in rows
                if row["TargetUnitType"] == "page"
            ]
            self.assertEqual(
                ["P0001", "P0002", "P0003", "P0004", "P0005"],
                page_units,
            )
            errors, _ = MODULE.validate_actor(root, "AI", SHARED)
            self.assertEqual([], errors)

            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "physical p.1-5", "physical p.2"
                ),
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_actor(root, "AI", SHARED)
            self.assertTrue(
                any("omit mandatory" in error for error in errors), errors
            )

    def test_ai_lower_bound_includes_both_abstracts_and_substantive_appendix_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "scope.pdf"
            writer = PdfWriter()
            texts = [
                "THESIS COVER\nCandidate metadata only",
                "CONTENTS\nChapter 1 ........ 1\nChapter 2 ........ 5",
                (
                    "CHINESE ABSTRACT\nThis abstract explains the research question, "
                    "method, and principal result. It contains sustained authored prose; "
                    "the evidence is intentionally long enough for semantic inspection."
                ),
                (
                    "ABSTRACT\nThis abstract explains the research question, method, and "
                    "principal result. It contains sustained authored prose; the evidence "
                    "is intentionally long enough for semantic inspection."
                ),
                "CHAPTER 1\nIntroduction\n1.1 Section",
                (
                    "APPENDIX A\nThis appendix explains an additional derivation, its "
                    "assumptions, and the interpretation of the result. It contains "
                    "sustained authored prose; therefore it must remain in the AI audit."
                ),
                "CURRICULUM VITAE\nName\nEducation\nPublication list",
            ]
            for text_value in texts:
                page = writer.add_blank_page(width=595, height=842)
                add_ascii_text(writer, page, text_value)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            pages = MODULE.detect_rendered_abstract_and_appendix_pages(
                pdf_path, SHARED, errors
            )
            self.assertEqual([], errors)
            self.assertEqual({3, 4, 6}, pages)

    def test_ai_abstract_headings_embedded_in_a_chapter_are_not_independent_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "embedded-abstracts.pdf"
            writer = PdfWriter()
            for text_value in (
                (
                    "CONTENTS\nCHINESE ABSTRACT\nABSTRACT\nThis table-of-contents "
                    "page has enough nearby prose and punctuation to fool a loose "
                    "heading scan; it is still navigation, not an abstract section."
                ),
                (
                    "CHAPTER 1\nIntroduction\nCHINESE ABSTRACT\nThis long chapter "
                    "paragraph imitates a Chinese abstract heading. It has enough "
                    "words and punctuation; nevertheless it is rendered inside the body."
                    "\nABSTRACT\nThis second long paragraph is also inside Chapter 1. "
                    "It must not establish an independent English abstract page."
                ),
                "CHAPTER 2\nMethods\n2.1 Section",
            ):
                page = writer.add_blank_page(width=595, height=842)
                add_ascii_text(writer, page, text_value)
            with pdf_path.open("wb") as handle:
                writer.write(handle)
            errors: list[str] = []
            pages = MODULE.detect_rendered_abstract_and_appendix_pages(
                pdf_path, SHARED, errors
            )
            self.assertEqual(set(), pages)
            self.assertTrue(
                any("pre-body Chinese abstract" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("pre-body English abstract" in error for error in errors),
                errors,
            )

    def test_chapter_coverage_is_pdf_derived_when_manifest_has_no_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "1.1=physical p.3; 2.1=physical p.4; 3.1=physical p.5",
                    "none detected",
                ),
                encoding="utf-8",
            )
            fixture.write_acceptance("R1", root)
            rows = MODULE.read_csv_rows(root / "SA-R1.csv", [])
            self.assertEqual(
                ["Chapter-1", "Chapter-2", "Chapter-3"],
                [
                    row["TargetUnitID"]
                    for row in rows
                    if row["TargetUnitType"] == "chapter"
                ],
            )
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertEqual([], errors)

    def test_pdf_extraction_runtime_mismatch_fails_before_pdf_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            manifest = root / "00-manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    f"pypdf={pypdf.__version__}", "pypdf=0.0.invalid"
                ),
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("PDF extraction runtime" in error for error in errors), errors
            )

    def test_every_sa_public_endpoint_must_be_exactly_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            for target in fixture.targets:
                with self.subTest(target=target, mode="positive"):
                    fixture.write_acceptance(target, root)
                    self.assertEqual(
                        set(),
                        MODULE.target_public_endpoints(
                            root, fixture.process, target, SHARED, []
                        ),
                    )
                    errors, _ = MODULE.validate_actor(root, target, SHARED)
                    self.assertEqual([], errors)

            for target in ("R1", "R3", "AI"):
                with self.subTest(target=target, mode="forged"):
                    fixture.write_acceptance(target, root)
                    report = root / f"SA-{target}.md"
                    report.write_text(
                        report.read_text(encoding="utf-8").replace(
                            "public_endpoints=[none]",
                            f"public_endpoints=[{fixture.endpoint}]",
                        ),
                        encoding="utf-8",
                    )
                    errors, _ = MODULE.validate_actor(root, target, SHARED)
                    self.assertTrue(
                        any(
                            "all SA public_endpoints must be exactly [none]" in error
                            for error in errors
                        ),
                        errors,
                    )

    def test_page_anchor_bounds_extra_csv_cell_and_render_subdirectory_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            csv_path = root / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            gate_row = next(row for row in rows if row["TargetUnitType"] == "gate")
            gate_row["EvidenceAnchor"] = "physical p.999, impossible page"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("outside 1..6" in error for error in errors), errors)

            lines = csv_path.read_text(encoding="utf-8").splitlines()
            lines[1] += ",smuggled-extra-cell"
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            csv_errors: list[str] = []
            MODULE.read_csv_rows(csv_path, csv_errors)
            self.assertTrue(any("beyond the exact CSV schema" in error for error in csv_errors), csv_errors)

            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            lines = csv_path.read_text(encoding="utf-8").splitlines()
            lines[1] += ","
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            empty_extra_errors: list[str] = []
            MODULE.read_csv_rows(csv_path, empty_extra_errors)
            self.assertTrue(
                any("cell beyond the exact CSV schema" in error for error in empty_extra_errors),
                empty_extra_errors,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R3", root)
            (root / "page-renders" / "unexpected").mkdir()
            errors, _ = MODULE.validate_actor(
                root, "R3", SHARED, enforce_closed_view=True
            )
            self.assertTrue(
                any("page-renders file set mismatch" in error for error in errors),
                errors,
            )

    def test_peer_input_and_target_hash_drift_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            report = root / "SA-R1.md"
            text = report.read_text(encoding="utf-8")
            text = text.replace(
                "R1-comprehensive-review.md]",
                "R1-comprehensive-review.md; R2-comprehensive-review.md]",
            )
            report.write_text(text, encoding="utf-8")
            (root / "R1-comprehensive-review.md").write_text("changed", encoding="utf-8")
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("opened list" in error for error in errors), errors)
            self.assertTrue(any("target artifact hash mismatch" in error for error in errors), errors)

    def test_coverage_failure_and_template_monoculture_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R3", root)
            csv_path = root / "SA-R3.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            rows.pop()
            for row in rows:
                row["SemanticBasis"] = (
                    f"Template evidence for {row['TargetUnitID']} checks the target "
                    "and declares that the same generic semantic relation is valid."
                )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(any("coverage sequence mismatch" in error for error in errors), errors)
            self.assertTrue(any("repeated identity-stripped" in error for error in errors), errors)

    def test_template_threshold_covers_minimal_reviewer_universe_without_small_cluster_false_positive(
        self,
    ) -> None:
        def row(index: int, basis: str) -> dict[str, str]:
            return {
                "TargetUnitID": f"Gate-{chr(65 + index)}",
                "SemanticBasis": basis,
            }

        for row_count in range(1, 12):
            with self.subTest(contract="distinct rows remain valid", row_count=row_count):
                rows = [
                    row(
                        index,
                        f"Distinct semantic rationale token{chr(65 + index)} "
                        f"uses independently bounded evidence word{chr(90 - index)}.",
                    )
                    for index in range(row_count)
                ]
                errors: list[str] = []
                MODULE.validate_template_diversity(rows, errors)
                self.assertEqual([], errors)

        repeated = (
            "Independent semantic validation compares the frozen thesis evidence "
            "with this target conclusion and confirms the same generic support."
        )
        minimal_reviewer_rows = [row(index, repeated) for index in range(11)]
        exact_errors: list[str] = []
        MODULE.validate_template_diversity(minimal_reviewer_rows, exact_errors)
        self.assertTrue(
            any("repeated identity-stripped" in error for error in exact_errors),
            exact_errors,
        )

        near_duplicate_rows = [
            row(
                index,
                "Independent semantic validation compares the complete frozen thesis "
                "evidence against the target conclusion and confirms coherent support "
                f"from UniqueSource{chr(65 + index)}.",
            )
            for index in range(11)
        ]
        near_errors: list[str] = []
        MODULE.validate_template_diversity(near_duplicate_rows, near_errors)
        self.assertTrue(
            any(
                "repeated long SemanticBasis language shingle" in error
                or "singleton-stripped generic language skeleton" in error
                or "fuzzy near-duplicate SemanticBasis" in error
                for error in near_errors
            ),
            near_errors,
        )

        five_similar_rows = [row(index, repeated) for index in range(5)]
        five_similar_rows.extend(
            row(
                index,
                f"Independent bounded analysis vocabulary{chr(65 + index)} "
                f"examines a distinct criterion evidence{chr(90 - index)}.",
            )
            for index in range(5, 11)
        )
        small_cluster_errors: list[str] = []
        MODULE.validate_template_diversity(
            five_similar_rows, small_cluster_errors
        )
        self.assertEqual([], small_cluster_errors)

    def test_long_shingle_rejects_cross_unit_title_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            csv_path = root / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            for index, row in enumerate(rows):
                row["SemanticBasis"] = (
                    "Independent semantic validation compares this target claim "
                    "against the complete frozen thesis evidence and confirms "
                    f"coherent support from Source{chr(65 + index // 26)}{chr(65 + index % 26)}."
                )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("repeated long SemanticBasis language shingle" in error for error in errors),
                errors,
            )

            for index, row in enumerate(rows):
                source = f"Source{chr(65 + index // 26)}{chr(65 + index % 26)}"
                row["SemanticBasis"] = (
                    "Independent semantic validation compares the complete frozen thesis "
                    f"{source} against bounded evidence and checks proportional target reasoning "
                    f"{source} before confirming internal support and scope consistency."
                )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("singleton-stripped generic language skeleton" in error for error in errors),
                errors,
            )

    def test_fuzzy_cluster_rejects_rotating_small_token_bank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            csv_path = root / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            generic_words = (
                "independent semantic validation compares complete frozen thesis "
                "evidence against target conclusion checks proportional support scope "
                "consistency counterevidence limitations internal reasoning before "
                "bounded acceptance"
            ).split()
            token_banks = (
                ("SourceAlpha", "RecordAlpha", "LocatorAlpha"),
                ("SourceBeta", "RecordBeta", "LocatorBeta"),
                ("SourceGamma", "RecordGamma", "LocatorGamma"),
            )
            for row_index, row in enumerate(rows):
                tokens: list[str] = []
                bank = token_banks[row_index % len(token_banks)]
                for block_index in range(0, len(generic_words), 7):
                    tokens.extend(generic_words[block_index:block_index + 7])
                    tokens.extend(bank)
                row["SemanticBasis"] = " ".join(tokens) + "."
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("fuzzy near-duplicate SemanticBasis" in error for error in errors),
                errors,
            )

    def test_template_diversity_rejects_repetition_across_hundreds_of_rows(self) -> None:
        repeated = (
            "Independent semantic validation checks the permitted evidence and "
            "confirms the same generic bounded support relation."
        )
        templated_rows = [
            {
                "TargetUnitID": f"C{index:04d}-S01",
                "TargetUnitType": "citation-pair",
                "SemanticBasis": f"{repeated} C{index:04d}-S01.",
            }
            for index in range(300)
        ]
        templated_errors: list[str] = []
        MODULE.validate_template_diversity(templated_rows, templated_errors)
        self.assertEqual(12, MODULE.template_cluster_threshold(len(templated_rows)))
        self.assertTrue(
            any(
                "repeated identity-stripped SemanticBasis" in error
                for error in templated_errors
            ),
            templated_errors,
        )

    def test_unit_type_is_bound_to_its_authoritative_target_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R3", root)
            csv_path = root / "SA-R3.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            pair_row = next(
                row for row in rows if row["TargetUnitType"] == "citation-pair"
            )
            pair_row["TargetArtifact"] = "R3-comprehensive-review.md"
            pair_row["TargetArtifactSHA256"] = digest(
                root / "R3-comprehensive-review.md"
            )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("must bind TargetArtifact" in error for error in errors), errors
            )

    def test_report_unit_universe_and_pass_anchors_come_from_canonical_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            report = root / "R1-comprehensive-review.md"
            finding_block = (
                "## Findings\n\n"
                "### R1-F01 — Bounded finding\n"
                "- Primary gate: A\n"
                "- Secondary gates: none\n"
                "- Scope: local\n"
                "- Severity: S2\n"
                "- S0 subtype: N/A\n"
                "- Remedy: W\n"
                "- Required for the current defense conclusion: yes, because the claim is central\n"
                "- Location: physical p.3\n"
                "- Observation: The rendered paragraph makes a bounded unsupported statement.\n"
                "- Why it matters: The statement changes how the method contribution is interpreted.\n"
                "- Evidence: The exact paragraph and neighboring method definition expose the gap.\n"
                "- Required action: Narrow the wording and add the missing PDF-visible qualification.\n"
                "- Verification: Re-read the revised paragraph and its surrounding definition carefully.\n"
                "- Confidence: high\n"
            )
            question_block = (
                "## Questions, not findings\n\n"
                "| Question ID | Exact PDF anchor | Question | Why unresolved | Needed clarification/evidence |\n"
                "|---|---|---|---|---|\n"
                "| R1-Q01 | physical p.4 | Which protocol variant is used in the reported result? | The rendered methods text leaves two variants possible. | State the selected variant in the revised PDF. |\n"
            )
            report_text = (
                fixture.target_receipt()
                + "\n"
                + fixture.reviewer_report_body("R1")
            )
            report_text = report_text.replace(
                "# Reviewer R1\n",
                "# Reviewer R1\n\nNarrative-only fake IDs R1-F99 and R1-Q99.\n",
            ).replace(
                "## Findings\n\nnone\n",
                finding_block,
            ).replace(
                "## Questions, not findings\n\n"
                "| Question ID | Exact PDF anchor | Question | Why unresolved | Needed clarification/evidence |\n"
                "|---|---|---|---|---|\n",
                question_block,
            ).replace(
                "| A | baseline | adequate | physical p.3, inspected thesis passage for Gate A | none | high confidence within the frozen PDF |",
                "| A | baseline | concern | physical p.3, inspected thesis passage for Gate A | R1-F01 | high confidence within the frozen PDF |",
            )
            report.write_text(
                report_text,
                encoding="utf-8",
            )
            fixture.write_acceptance("R1", root)
            rows = MODULE.read_csv_rows(root / "SA-R1.csv", [])
            ids = [
                row["TargetUnitID"]
                for row in rows
                if row["TargetUnitType"] in {"finding", "question"}
            ]
            self.assertEqual(["R1-F01", "R1-Q01"], ids)
            self.assertNotIn("R1-F99", ids)
            finding = next(row for row in rows if row["TargetUnitID"] == "R1-F01")
            question = next(row for row in rows if row["TargetUnitID"] == "R1-Q01")
            finding["EvidenceAnchor"] = "physical p.4, unrelated passage"
            question["EvidenceAnchor"] = "physical p.3, unrelated passage"
            write_csv(root / "SA-R1.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("R1-F01" in error and "physical p.3" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("R1-Q01" in error and "physical p.4" in error for error in errors),
                errors,
            )

            question["EvidenceAnchor"] = "physical p.4, exact target question passage"
            finding["AcceptanceDisposition"] = "fail"
            write_csv(root / "SA-R1.csv", MODULE.CSV_COLUMNS, rows)
            acceptance_md = root / "SA-R1.md"
            acceptance_md.write_text(
                acceptance_md.read_text(encoding="utf-8")
                .replace("Overall semantic acceptance: PASS", "Overall semantic acceptance: FAIL")
                .replace("Acceptance failure count: 0", "Acceptance failure count: 1"),
                encoding="utf-8",
            )
            errors, result = MODULE.validate_actor(root, "R1", SHARED)
            self.assertFalse(any("R1-F01" in error and "target's exact" in error for error in errors), errors)
            self.assertEqual("FAIL", result["status"])

    def test_passing_finding_requires_closed_structured_semantic_binding(self) -> None:
        def run_mutation(mutator):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                fields = fixture.install_reviewer_finding("R1")
                fixture.write_acceptance("R1", root)
                csv_path = root / "SA-R1.csv"
                rows = MODULE.read_csv_rows(csv_path, [])
                finding = next(
                    row for row in rows if row["TargetUnitType"] == "finding"
                )
                mutator(finding, fields)
                write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
                errors, _ = MODULE.validate_actor(root, "R1", SHARED)
                return errors

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.install_reviewer_finding("R1")
            fixture.write_acceptance("R1", root)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertEqual([], errors)

        def rewrite(finding, changes, labels=MODULE.FINDING_SEMANTIC_BASIS_LABELS):
            parse_errors: list[str] = []
            parsed = MODULE.parse_closed_ordered_semantic_basis(
                finding["SemanticBasis"],
                MODULE.FINDING_SEMANTIC_BASIS_LABELS,
                "fixture",
                parse_errors,
            )
            if parse_errors:
                raise AssertionError(parse_errors)
            parsed.update(changes)
            ordered = {label: parsed[label] for label in labels}
            finding["SemanticBasis"] = json.dumps(
                ordered, ensure_ascii=False, separators=(",", ":")
            )

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {},
                (
                    "target_premise",
                    "premise_class",
                    *MODULE.FINDING_SEMANTIC_BASIS_LABELS[2:],
                ),
            )
        )
        self.assertTrue(any("exact closed key order" in error for error in errors), errors)

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row, {"assessment_standard": "independent-concurrence"}
            )
        )
        self.assertTrue(
            any("assessment_standard must be exactly" in error for error in errors),
            errors,
        )

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row, {"admissibility_result": "reviewer-agrees"}
            )
        )
        self.assertTrue(
            any("admissibility_result must be exactly" in error for error in errors),
            errors,
        )

        errors = run_mutation(
            lambda row, _fields: rewrite(row, {"premise_class": "free-form"})
        )
        self.assertTrue(any("premise class must be exactly" in error for error in errors), errors)

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {"target_premise": "A different premise that is absent from the target finding."},
            )
        )
        self.assertTrue(any("must exactly bind" in error for error in errors), errors)

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {
                    "premise_class": "absence-after-search",
                    "residual_gap": {"status": "present", "detail": "N/A because no detail was recorded"},
                },
            )
        )
        self.assertTrue(any("residual_gap detail" in error for error in errors), errors)

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {
                    "residual_gap": {
                        "status": "present",
                        "detail": "The bounded concern remains after whole-PDF review.",
                    }
                },
            )
        )
        self.assertTrue(
            any("residual_gap status" in error for error in errors), errors
        )

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row, {"supporting_pdf_evidence": "N/A because evidence was not copied"}
            )
        )
        self.assertTrue(
            any("supporting_pdf_evidence" in error and "cannot be N/A" in error for error in errors),
            errors,
        )

        errors = run_mutation(
            lambda row, _fields: rewrite(row, {"residual_gap": {"status": "present", "detail": "无：未记录"}})
        )
        self.assertTrue(any("residual_gap detail" in error for error in errors), errors)

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {
                    "supporting_pdf_evidence": (
                        "physical p.4, a passage unrelated to the target finding page"
                    )
                },
            )
        )
        self.assertTrue(
            any("supporting PDF evidence" in error and "physical p.3" in error for error in errors),
            errors,
        )

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {
                    "supporting_pdf_evidence": (
                        "physical p.1-3, a range contains but does not exactly anchor the target page"
                    )
                },
            )
        )
        self.assertTrue(
            any("exact singleton physical p.3" in error for error in errors),
            errors,
        )

        for label, invalid_pages in (
            ("mixed invalid", ["physical p.3", "not-a-page"]),
            ("out of range", ["physical p.3", "physical p.999"]),
            ("range", ["physical p.3-4"]),
            ("duplicate", ["physical p.3", "physical p.3"]),
        ):
            with self.subTest(finding_page_array=label):
                errors = run_mutation(
                    lambda row, _fields, invalid_pages=invalid_pages: rewrite(
                        row,
                        {
                            "whole_pdf_resolution": {
                                "status": "responsive-passages-reviewed",
                                "pages": invalid_pages,
                                "search_concepts": [
                                    "the bounded proposition throughout the frozen PDF"
                                ],
                                "detail": "The responsive passages were inspected independently in context.",
                            }
                        },
                    )
                )
                self.assertTrue(
                    any(
                        "whole_pdf_resolution pages" in error
                        and (
                            "canonical" in error
                            or "outside" in error
                            or "duplicate-free" in error
                        )
                        for error in errors
                    ),
                    errors,
                )

        errors = run_mutation(
            lambda row, fields: rewrite(
                row,
                {"action_delta": {
                    "status": "same-as-target-required-action",
                    "detail": fields["Required action"],
                    "independent_reason": "Independent PDF inspection confirms that the same bounded action remains necessary.",
                }},
            )
        )
        self.assertEqual([], errors)

    def test_passing_finding_nested_values_and_action_delta_contract(self) -> None:
        def run_mutation(mutator):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                fields = fixture.install_reviewer_finding("R1")
                fixture.write_acceptance("R1", root)
                csv_path = root / "SA-R1.csv"
                rows = MODULE.read_csv_rows(csv_path, [])
                finding = next(
                    row for row in rows if row["TargetUnitType"] == "finding"
                )
                mutator(finding, fields)
                write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
                errors, _ = MODULE.validate_actor(root, "R1", SHARED)
                return errors

        def rewrite(finding, changes):
            parse_errors: list[str] = []
            parsed = MODULE.parse_closed_ordered_semantic_basis(
                finding["SemanticBasis"],
                MODULE.FINDING_SEMANTIC_BASIS_LABELS,
                "fixture",
                parse_errors,
            )
            if parse_errors:
                raise AssertionError(parse_errors)
            parsed.update(changes)
            finding["SemanticBasis"] = json.dumps(
                {
                    label: parsed[label]
                    for label in MODULE.FINDING_SEMANTIC_BASIS_LABELS
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )

        for label, changes in (
            (
                "whole_pdf_resolution detail",
                {"whole_pdf_resolution": {
                    "status": "responsive-passages-reviewed",
                    "pages": ["physical p.3"],
                    "search_concepts": ["concrete responsive concept across the thesis"],
                    "detail": {"not": "a string"},
                }},
            ),
            (
                "whole_pdf_resolution search_concepts",
                {"whole_pdf_resolution": {
                    "status": "responsive-passages-reviewed",
                    "pages": ["physical p.3"],
                    "search_concepts": [{"not": "a string"}],
                    "detail": "The responsive passage was independently inspected in context.",
                }},
            ),
            (
                "residual_gap detail",
                {"residual_gap": {
                    "status": MODULE.REASONABLY_SUPPORTED,
                    "detail": ["not", "a", "string"],
                }},
            ),
            (
                "action_delta independent_reason",
                {"action_delta": {
                    "status": "different-from-target-required-action",
                    "detail": "Add one narrowly scoped clarification at the cited passage.",
                    "independent_reason": {"not": "a string"},
                }},
            ),
        ):
            with self.subTest(non_string_nested_value=label):
                errors = run_mutation(
                    lambda row, _fields, changes=changes: rewrite(row, changes)
                )
                self.assertTrue(any(label in error for error in errors), errors)

        errors = run_mutation(
            lambda row, fields: rewrite(
                row,
                {"action_delta": {
                    "status": "narrower-than-target-required-action",
                    "detail": fields["Required action"],
                    "independent_reason": "The independent inspection supports a genuinely narrower correction.",
                }},
            )
        )
        self.assertTrue(any("must not copy the Required action" in error for error in errors), errors)

        for wrapped_action in (
            lambda action: f"Narrower prefix: {action}",
            lambda action: f"{action} with a trailing clarification",
        ):
            errors = run_mutation(
                lambda row, fields, wrapped_action=wrapped_action: rewrite(
                    row,
                    {"action_delta": {
                        "status": "different-from-target-required-action",
                        "detail": wrapped_action(fields["Required action"]),
                        "independent_reason": "The independent inspection supports a genuinely different correction.",
                    }},
                )
            )
            self.assertTrue(
                any("must not copy the Required action" in error for error in errors),
                errors,
            )

        errors = run_mutation(
            lambda row, fields: rewrite(
                row,
                {"action_delta": {
                    "status": "same-as-target-required-action",
                    "detail": fields["Required action"],
                    "independent_reason": fields["Required action"],
                }},
            )
        )
        self.assertTrue(any("independent_reason must not copy" in error for error in errors), errors)

        for reason_source in ("required", "detail"):
            errors = run_mutation(
                lambda row, fields, reason_source=reason_source: rewrite(
                    row,
                    {"action_delta": {
                        "status": "different-from-target-required-action",
                        "detail": "Add one narrowly scoped clarification at the cited passage.",
                        "independent_reason": "Independent reason: " + (
                            fields["Required action"]
                            if reason_source == "required"
                            else "Add one narrowly scoped clarification at the cited passage."
                        ),
                    }},
                )
            )
            self.assertTrue(
                any("independent_reason must not copy" in error for error in errors),
                errors,
            )

        errors = run_mutation(
            lambda row, _fields: rewrite(
                row,
                {
                    "premise_class": "bounded-inference",
                    "whole_pdf_resolution": {
                        "status": "no-responsive-passage-found",
                        "pages": [],
                        "search_concepts": ["the bounded proposition and relevant terminology throughout the PDF"],
                        "detail": "The complete search found no additional responsive passage beyond the local evidence.",
                    },
                },
            )
        )
        self.assertEqual([], errors)

    def test_passing_gate_requires_exact_target_binding_and_independent_pdf_basis(self) -> None:
        def run_mutation(mutator):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                fixture.install_reviewer_finding("R1")
                fixture.write_acceptance("R1", root)
                csv_path = root / "SA-R1.csv"
                rows = MODULE.read_csv_rows(csv_path, [])
                gate = next(
                    row
                    for row in rows
                    if row["TargetUnitType"] == "gate"
                    and row["TargetUnitID"] == "Gate-A"
                )
                mutator(gate)
                write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
                errors, _ = MODULE.validate_actor(root, "R1", SHARED)
                return errors

        def rewrite(gate, changes):
            parse_errors: list[str] = []
            parsed = MODULE.parse_closed_ordered_semantic_basis(
                gate["SemanticBasis"],
                MODULE.GATE_SEMANTIC_BASIS_LABELS,
                "fixture",
                parse_errors,
            )
            if parse_errors:
                raise AssertionError(parse_errors)
            parsed.update(changes)
            gate["SemanticBasis"] = json.dumps(
                {
                    label: parsed[label]
                    for label in MODULE.GATE_SEMANTIC_BASIS_LABELS
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.install_reviewer_finding("R1")
            fixture.write_acceptance("R1", root)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertEqual([], errors)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            report = root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "| A | baseline | adequate | physical p.3, inspected thesis passage for Gate A | none | high confidence within the frozen PDF |",
                    "| A | baseline | N/A | physical p.3, inspected thesis passage for Gate A | none | high confidence within the frozen PDF |",
                ),
                encoding="utf-8",
            )
            fixture.write_acceptance("R1", root)
            rows = MODULE.read_csv_rows(root / "SA-R1.csv", [])
            gate_a = next(row for row in rows if row["TargetUnitID"] == "Gate-A")
            parsed = json.loads(gate_a["SemanticBasis"])
            self.assertEqual("n/a", parsed["target_disposition"])
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertEqual([], errors)
            parsed["target_disposition"] = "adequate"
            gate_a["SemanticBasis"] = json.dumps(
                {
                    label: parsed[label]
                    for label in MODULE.GATE_SEMANTIC_BASIS_LABELS
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            write_csv(root / "SA-R1.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("target_disposition" in error for error in errors), errors)

        for label, changes in (
            ("target disposition", {"target_disposition": "adequate"}),
            (
                "target decisive evidence",
                {
                    "target_decisive_evidence": (
                        "physical p.4, unrelated evidence from a different page"
                    )
                },
            ),
            ("related finding IDs", {"target_related_finding_ids": []}),
        ):
            with self.subTest(binding=label):
                errors = run_mutation(
                    lambda row, changes=changes: rewrite(row, changes)
                )
                self.assertTrue(
                    any("exactly bind" in error for error in errors), errors
                )

        errors = run_mutation(
            lambda row: row.update(
                {
                    "SemanticBasis": (
                        "Gate-specific independent inspection says this looks "
                        "reasonable after reading the thesis."
                    )
                }
            )
        )
        self.assertTrue(any("canonical JSON" in error for error in errors), errors)

        def replace_support_page(row):
            parse_errors: list[str] = []
            parsed = MODULE.parse_closed_ordered_semantic_basis(
                row["SemanticBasis"],
                MODULE.GATE_SEMANTIC_BASIS_LABELS,
                "fixture",
                parse_errors,
            )
            if parse_errors:
                raise AssertionError(parse_errors)
            assessment = dict(parsed["independent_pdf_assessment"])
            assessment["supporting_pdf_evidence"] = (
                "physical p.4, unrelated passage after an independent check"
            )
            rewrite(row, {"independent_pdf_assessment": assessment})

        errors = run_mutation(replace_support_page)
        self.assertTrue(
            any("recheck at least one page" in error for error in errors), errors
        )

    def test_passing_question_requires_exact_target_binding_and_whole_pdf_resolution(self) -> None:
        def install_question(fixture):
            report = fixture.root / "R1-comprehensive-review.md"
            report.write_text(
                report.read_text(encoding="utf-8")
                + (
                    "| R1-Q01 | physical p.4 | Which protocol variant is used "
                    "in the reported result? | The rendered methods text leaves "
                    "two variants possible. | State the selected variant in the "
                    "revised PDF. |\n"
                ),
                encoding="utf-8",
            )

        def run_mutation(mutator):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                install_question(fixture)
                fixture.write_acceptance("R1", root)
                csv_path = root / "SA-R1.csv"
                rows = MODULE.read_csv_rows(csv_path, [])
                question = next(
                    row for row in rows if row["TargetUnitType"] == "question"
                )
                mutator(question)
                write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
                errors, _ = MODULE.validate_actor(root, "R1", SHARED)
                return errors

        def rewrite(question, changes):
            parse_errors: list[str] = []
            parsed = MODULE.parse_closed_ordered_semantic_basis(
                question["SemanticBasis"],
                MODULE.QUESTION_SEMANTIC_BASIS_LABELS,
                "fixture",
                parse_errors,
            )
            if parse_errors:
                raise AssertionError(parse_errors)
            parsed.update(changes)
            question["SemanticBasis"] = json.dumps(
                {
                    label: parsed[label]
                    for label in MODULE.QUESTION_SEMANTIC_BASIS_LABELS
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )

        for label, changes in (
            ("question", {"target_question": "A different unresolved question."}),
            ("why", {"target_why_unresolved": "A different reason."}),
            ("needed evidence", {"target_needed_evidence": "Different evidence."}),
            ("page", {"target_page": "physical p.3"}),
        ):
            with self.subTest(binding=label):
                errors = run_mutation(
                    lambda row, changes=changes: rewrite(row, changes)
                )
                self.assertTrue(
                    any("exactly bind" in error for error in errors), errors
                )

        errors = run_mutation(
            lambda row: row.update(
                {
                    "SemanticBasis": (
                        "The question remains reasonable after a general PDF read."
                    )
                }
            )
        )
        self.assertTrue(any("canonical JSON" in error for error in errors), errors)

        errors = run_mutation(
            lambda row: rewrite(
                row,
                {
                    "whole_pdf_resolution": {
                        "status": "no-responsive-passage-found",
                        "pages": ["physical p.4"],
                        "search_concepts": ["the bounded unresolved protocol choice"],
                        "detail": "The stated search did not locate a responsive passage.",
                    }
                },
            )
        )
        self.assertTrue(
            any("requires empty pages" in error for error in errors), errors
        )

        for label, invalid_pages in (
            ("mixed invalid", ["physical p.4", "not-a-page"]),
            ("out of range", ["physical p.4", "physical p.999"]),
            ("range", ["physical p.3-4"]),
            ("duplicate", ["physical p.4", "physical p.4"]),
        ):
            with self.subTest(question_page_array=label):
                errors = run_mutation(
                    lambda row, invalid_pages=invalid_pages: rewrite(
                        row,
                        {
                            "whole_pdf_resolution": {
                                "status": "responsive-passages-reviewed",
                                "pages": invalid_pages,
                                "search_concepts": [
                                    "the bounded unresolved protocol choice"
                                ],
                                "detail": "The responsive passages were checked across the frozen PDF.",
                            }
                        },
                    )
                )
                self.assertTrue(
                    any(
                        "question whole_pdf_resolution pages" in error
                        and (
                            "canonical" in error
                            or "outside" in error
                            or "duplicate-free" in error
                        )
                        for error in errors
                    ),
                    errors,
                )

    def test_passing_verdict_exactly_projects_report_profiles_and_coherence(self) -> None:
        for cue_label in MODULE.VERDICT_SEMANTIC_BASIS_LABELS:
            with self.subTest(cue_label=cue_label), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                fixture.write_acceptance("R1", root)
                csv_path = root / "SA-R1.csv"
                rows = MODULE.read_csv_rows(csv_path, [])
                verdict = next(
                    row for row in rows if row["TargetUnitType"] == "verdict"
                )
                parse_errors: list[str] = []
                parsed = MODULE.parse_closed_ordered_semantic_basis(
                    verdict["SemanticBasis"],
                    MODULE.VERDICT_SEMANTIC_BASIS_LABELS,
                    "fixture",
                    parse_errors,
                )
                self.assertEqual([], parse_errors)
                parsed[cue_label] += "X"
                verdict["SemanticBasis"] = json.dumps(
                    parsed, ensure_ascii=False, separators=(",", ":")
                )
                write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
                errors, _ = MODULE.validate_actor(root, "R1", SHARED)
                self.assertTrue(
                    any(f"verdict {cue_label}" in error for error in errors),
                    errors,
                )

        for disposition in ("adequate", "unverifiable"):
            with self.subTest(non_concern=disposition), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                fixture.install_reviewer_finding("R1")
                report_path = root / "R1-comprehensive-review.md"
                report_path.write_text(
                    report_path.read_text(encoding="utf-8").replace(
                        "| A | baseline | concern | physical p.3, inspected thesis passage for Gate A | R1-F01 | high confidence within the frozen PDF |",
                        f"| A | baseline | {disposition} | physical p.3, inspected thesis passage for Gate A | R1-F01 | high confidence within the frozen PDF |",
                    ),
                    encoding="utf-8",
                )
                fixture.write_acceptance("R1", root)
                errors, _ = MODULE.validate_actor(root, "R1", SHARED)
                self.assertTrue(
                    any("mechanically incoherent" in error for error in errors),
                    errors,
                )

    def test_finding_canonical_json_preserves_literal_legacy_delimiter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fields = fixture.install_reviewer_finding("R1")
            report = root / "R1-comprehensive-review.md"
            observation = fields["Observation"] + " It literally contains || without splitting fields."
            report.write_text(
                report.read_text(encoding="utf-8").replace(fields["Observation"], observation),
                encoding="utf-8",
            )
            fixture.write_acceptance("R1", root)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertEqual([], errors)

    def test_verdict_ai_judgment_and_ai_finding_require_physical_target_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            rows = MODULE.read_csv_rows(root / "SA-R1.csv", [])
            verdict = next(row for row in rows if row["TargetUnitType"] == "verdict")
            verdict["EvidenceAnchor"] = "target report synthesis without a PDF page"
            write_csv(root / "SA-R1.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(
                any("verdict row requires a physical p.<n> anchor" in error for error in errors),
                errors,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            (root / "05-ai-style-assessment.md").write_text(
                "# AI style assessment\n\n## Findings\n\n"
                "### AI-F01 — Recurrent transition pattern\n"
                "- Impact: local\n"
                "- Location: physical p.2\n"
                "- Recurrent evidence: Several prose spans repeat the same transition structure.\n"
                "- Reader impact: The repetition makes otherwise distinct claims sound mechanically uniform.\n"
                "- Minimum safe editing strategy: Vary only the repeated transitions while preserving all claims.\n"
                "- Closure test: Re-read every cited span and confirm the repeated structure no longer dominates.\n",
                encoding="utf-8",
            )
            fixture.write_acceptance("AI", root)
            rows = MODULE.read_csv_rows(root / "SA-AI.csv", [])
            finding = next(row for row in rows if row["TargetUnitType"] == "ai-finding")
            judgment = next(row for row in rows if row["TargetUnitType"] == "ai-judgment")
            finding["EvidenceAnchor"] = "physical p.3, unrelated style passage"
            judgment["EvidenceAnchor"] = "overall style synthesis without physical evidence"
            write_csv(root / "SA-AI.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "AI", SHARED)
            self.assertTrue(
                any("AI-F01" in error and "physical p.2" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("ai-judgment row requires a physical p.<n> anchor" in error for error in errors),
                errors,
            )

    def test_owner_rows_require_their_own_endpoint_and_exact_locator(self) -> None:
        policy_endpoint = "https://policy.example/rule"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.process["governing_rule_urls"] = [policy_endpoint]
            (root / "00-process-parameters.json").write_text(
                json.dumps(fixture.process, indent=2), encoding="utf-8"
            )
            fixture.write_acceptance("R3", root)
            report = root / "SA-R3.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    f"public_endpoints=[{fixture.endpoint}]",
                    f"public_endpoints=[{fixture.endpoint}; {policy_endpoint}]",
                ),
                encoding="utf-8",
            )
            csv_path = root / "SA-R3.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            pair_row = next(row for row in rows if row["TargetUnitType"] == "citation-pair")
            pair_row["EvidenceAnchor"] = f"{policy_endpoint}, section"
            bibliography_row = next(
                row for row in rows if row["TargetUnitType"] == "bibliography-field"
            )
            bibliography_row["EvidenceAnchor"] = f"{policy_endpoint}, section"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("citation-pair evidence URL" in error for error in errors), errors
            )
            self.assertTrue(
                any("citation-pair requires a numbered/named exact source locator" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("bibliography-field evidence URL" in error for error in errors), errors
            )
            self.assertTrue(
                any("bibliography-field requires a numbered/named exact" in error for error in errors),
                errors,
            )

    def test_documented_unopened_unverifiable_pair_binds_exact_04_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            ledger_path = root / "04-citation-claim-audit-ledger.csv"
            ledger_rows = MODULE.read_generic_csv(ledger_path, [])
            ledger_rows[0]["ContentSourceOpened"] = ""
            ledger_rows[0]["ExactSourceLocator"] = ""
            ledger_rows[0]["Support"] = "unverifiable"
            ledger_rows[0]["MetadataStatus"] = "unverifiable"
            ledger_rows[0]["DispositionEvidence"] = (
                "reasoned non-finding: the official full-text route was attempted "
                "but remained inaccessible; source content could not be inspected"
            )
            write_csv(ledger_path, SHARED.CITATION_LEDGER_COLUMNS, ledger_rows)

            fixture.write_acceptance("R3", root)
            rows = MODULE.read_csv_rows(root / "SA-R3.csv", [])
            pair_row = next(
                row for row in rows if row["TargetUnitType"] == "citation-pair"
            )
            self.assertNotIn("https://", pair_row["EvidenceAnchor"])
            self.assertIn(
                "audited support: unverifiable;", pair_row["SemanticBasis"]
            )
            self.assertIn(
                "audited metadata status: unverifiable;",
                pair_row["SemanticBasis"],
            )
            self.assertIn(
                "authority access limitation: reasoned non-finding:",
                pair_row["SemanticBasis"],
            )
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertEqual([], errors)

            pair_row["SemanticBasis"] = (
                "The exact thesis proposition Prior work defines a high-level "
                "objective for this method is retained, but the source was unavailable."
            )
            write_csv(root / "SA-R3.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any(
                    "documented unopened unverifiable citation-pair" in error
                    and "SemanticBasis" in error
                    for error in errors
                ),
                errors,
            )

            ledger_rows[0]["Support"] = "direct"
            ledger_rows[0]["MetadataStatus"] = "verified"
            write_csv(ledger_path, SHARED.CITATION_LEDGER_COLUMNS, ledger_rows)
            fixture.write_acceptance("R3", root)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("lacks an exact source locator" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any(
                    "primary ContentSourceOpened public endpoint" in error
                    for error in errors
                ),
                errors,
            )

    def test_dangling_pair_requires_exact_pdf_gap_and_04_state_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            inventory_path = root / "00-citation-inventory.csv"
            inventory_rows = MODULE.read_generic_csv(inventory_path, [])
            inventory_rows[0]["DisplayedReferenceID"] = "REF0002"
            write_csv(
                inventory_path, SHARED.CITATION_INVENTORY_COLUMNS, inventory_rows
            )
            ledger_path = root / "04-citation-claim-audit-ledger.csv"
            ledger_rows = MODULE.read_generic_csv(ledger_path, [])
            ledger_rows[0].update(
                {
                    "ReferenceID": "REF0002",
                    "PublicIdentifier": SHARED.DANGLING_REFERENCE_SENTINEL,
                    "ContentSourceOpened": "",
                    "ExactSourceLocator": "",
                    "Support": "unverifiable",
                    "MetadataStatus": "mismatch",
                    "DispositionEvidence": (
                        "displayed citation has no rendered bibliography entry"
                    ),
                }
            )
            write_csv(ledger_path, SHARED.CITATION_LEDGER_COLUMNS, ledger_rows)

            fixture.write_acceptance("R3", root)
            rows = MODULE.read_csv_rows(root / "SA-R3.csv", [])
            pair_row = next(
                row for row in rows if row["TargetUnitType"] == "citation-pair"
            )
            self.assertIn("displayed marker: [2];", pair_row["SemanticBasis"])
            self.assertIn(
                "rendered reference gap: REF0002 has no rendered bibliography entry;",
                pair_row["SemanticBasis"],
            )
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertEqual([], errors)

            pair_row["SemanticBasis"] = (
                "The exact thesis proposition Prior work defines a high-level "
                "objective for this method is attached to a dangling citation."
            )
            write_csv(root / "SA-R3.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any(
                    "exact PDF-visible marker/reference-gap" in error
                    for error in errors
                ),
                errors,
            )

    def test_citation_occurrence_and_bibliography_rendered_side_are_exactly_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R3", root)
            csv_path = root / "SA-R3.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            pair_row = next(row for row in rows if row["TargetUnitType"] == "citation-pair")
            pair_row["EvidenceAnchor"] = pair_row["EvidenceAnchor"].replace(
                "physical p.3", "physical p.4"
            )
            bibliography_row = next(
                row for row in rows if row["TargetUnitID"] == "REF0001/type"
            )
            bibliography_row["EvidenceAnchor"] = (
                f"{fixture.endpoint}, official record: type"
            )
            bibliography_row["SemanticBasis"] = (
                "authority cue: canonical-type-value; audited verdict: exact; "
                "The official record alone is asserted to be sufficient for this field."
            )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("C0001-S01" in error and "singleton physical p.3" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("REF0001/type" in error and "rendered entry" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("REF0001/type" in error and "rendered cue" in error for error in errors),
                errors,
            )

            pair_row["EvidenceAnchor"] = pair_row["EvidenceAnchor"].replace(
                "physical p.4", "physical p.3"
            )
            bibliography_row["EvidenceAnchor"] = (
                f"physical p.6, {fixture.endpoint}, official record: type"
            )
            bibliography_row["SemanticBasis"] = (
                "rendered cue: canonical-type-value; authority cue: "
                "rendered-type-value; audited verdict: exact; The two sides "
                "are deliberately swapped rather than independently compared."
            )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("REF0001/type" in error and "rendered field value" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("REF0001/type" in error and "canonical authority value" in error for error in errors),
                errors,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            ledger_path = root / "04-citation-claim-audit-ledger.csv"
            ledger_rows = MODULE.read_generic_csv(ledger_path, [])
            ledger_rows[0]["PDFLocation"] = "physical p.4"
            write_csv(ledger_path, SHARED.CITATION_LEDGER_COLUMNS, ledger_rows)
            fixture.write_acceptance("R3", root)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("04 PDFLocation" in error and "authoritative 00" in error for error in errors),
                errors,
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            auxiliary = "https://auxiliary.example/attempt"
            citation_path = root / "04-citation-claim-audit-ledger.csv"
            citation_rows = MODULE.read_generic_csv(citation_path, [])
            citation_rows[0]["DispositionEvidence"] += (
                f"; accessed endpoint: {auxiliary}"
            )
            write_csv(citation_path, SHARED.CITATION_LEDGER_COLUMNS, citation_rows)
            bibliography_path = root / "03-bibliography-audit-ledger.csv"
            bibliography_rows = MODULE.read_generic_csv(bibliography_path, [])
            bibliography_rows[0]["EvidenceNote"] += (
                f"; accessed endpoint: {auxiliary}"
            )
            write_csv(bibliography_path, SHARED.BIB_LEDGER_COLUMNS, bibliography_rows)
            fixture.write_acceptance("R3", root)
            rows = MODULE.read_csv_rows(root / "SA-R3.csv", [])
            pair_row = next(row for row in rows if row["TargetUnitType"] == "citation-pair")
            pair_row["EvidenceAnchor"] = pair_row["EvidenceAnchor"].replace(
                fixture.endpoint, auxiliary
            )
            bibliography_row = next(
                row for row in rows if row["TargetUnitID"] == "REF0001/type"
            )
            bibliography_row["EvidenceAnchor"] = bibliography_row["EvidenceAnchor"].replace(
                fixture.endpoint, auxiliary
            )
            write_csv(root / "SA-R3.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("primary ContentSourceOpened" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("primary EvidenceEndpoint" in error for error in errors),
                errors,
            )

    def test_abstract_only_locator_cannot_accept_detailed_citation_responsibility(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            ledger_path = root / "04-citation-claim-audit-ledger.csv"
            ledger_rows = MODULE.read_generic_csv(ledger_path, [])
            ledger_rows[0]["ExactAttachedProposition"] = (
                "Table 3 value is 91.2% for the reported algorithm step."
            )
            ledger_rows[0]["ExactSourceLocator"] = "Abstract, lines 2-4"
            write_csv(ledger_path, SHARED.CITATION_LEDGER_COLUMNS, ledger_rows)
            fixture.write_acceptance("R3", root)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("Abstract-only locator" in error for error in errors),
                errors,
            )

            rows = MODULE.read_csv_rows(root / "SA-R3.csv", [])
            pair_row = next(row for row in rows if row["TargetUnitType"] == "citation-pair")
            pair_row["AcceptanceDisposition"] = "fail"
            write_csv(root / "SA-R3.csv", MODULE.CSV_COLUMNS, rows)
            acceptance_md = root / "SA-R3.md"
            acceptance_md.write_text(
                acceptance_md.read_text(encoding="utf-8")
                .replace("Overall semantic acceptance: PASS", "Overall semantic acceptance: FAIL")
                .replace("Acceptance failure count: 0", "Acceptance failure count: 1"),
                encoding="utf-8",
            )
            errors, result = MODULE.validate_actor(root, "R3", SHARED)
            self.assertFalse(any("Abstract-only locator" in error for error in errors), errors)
            self.assertEqual("FAIL", result["status"])

    def test_bibliography_na_and_unverifiable_rows_bind_both_closed_cues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            ledger_path = root / "03-bibliography-audit-ledger.csv"
            ledger_rows = MODULE.read_generic_csv(ledger_path, [])
            type_row = next(row for row in ledger_rows if row["Field"] == "type")
            type_row["RenderedValue"] = "not present"
            type_row["CanonicalValue"] = "not applicable"
            type_row["Verdict"] = "legitimate n/a"
            title_row = next(row for row in ledger_rows if row["Field"] == "title")
            title_row["RenderedValue"] = "rendered title value"
            title_row["CanonicalValue"] = "authority unavailable"
            title_row["Verdict"] = "unverifiable"
            title_row["EvidenceNote"] = "publisher route failed before field verification"
            write_csv(ledger_path, SHARED.BIB_LEDGER_COLUMNS, ledger_rows)
            fixture.write_acceptance("R3", root)
            rows = MODULE.read_csv_rows(root / "SA-R3.csv", [])
            type_acceptance = next(
                row for row in rows if row["TargetUnitID"] == "REF0001/type"
            )
            type_acceptance["SemanticBasis"] = (
                "rendered cue: not present; authority cue: not applicable; "
                "audited verdict: legitimate n/a; The visible rendered absence "
                "is not applicable under the governing bibliography style."
            )
            title_acceptance = next(
                row for row in rows if row["TargetUnitID"] == "REF0001/title"
            )
            title_acceptance["SemanticBasis"] = (
                "rendered cue: rendered title value; authority cue: authority unavailable; "
                "audited verdict: unverifiable; publisher route failed before field "
                "verification, so the concrete authority limitation remains explicit."
            )
            write_csv(root / "SA-R3.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertEqual([], errors)

            type_acceptance["SemanticBasis"] = (
                "rendered cue: not present-plus; authority cue: not applicable; "
                "audited verdict: legitimate n/a-plus; The visible rendered absence "
                "is not applicable under the governing bibliography style."
            )
            write_csv(root / "SA-R3.csv", MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("does not bind its rendered field value" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("does not bind the authoritative audited verdict" in error for error in errors),
                errors,
            )

    def test_target_report_endpoint_is_not_sa_authority(self) -> None:
        extra_endpoint = "https://unrecorded.example/source"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            target_report = root / "R3-comprehensive-review.md"
            target_report.write_text(
                target_report.read_text(encoding="utf-8").replace(
                    f"public_endpoints=[{fixture.endpoint}]",
                    f"public_endpoints=[{fixture.endpoint}; {extra_endpoint}]",
                ),
                encoding="utf-8",
            )
            fixture.write_acceptance("R3", root)
            acceptance_report = root / "SA-R3.md"
            self.assertIn(
                "public_endpoints=[none]",
                acceptance_report.read_text(encoding="utf-8"),
            )
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertEqual([], errors)
            acceptance_report.write_text(
                acceptance_report.read_text(encoding="utf-8").replace(
                    "public_endpoints=[none]",
                    f"public_endpoints=[{extra_endpoint}]",
                ),
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any(
                    "all SA public_endpoints must be exactly [none]" in error
                    for error in errors
                ),
                errors,
            )

    def test_canonical_sa_allowlists_are_literal_and_target_scoped(self) -> None:
        common_reviewer_rules = [
            "00-process-parameters.json",
            "SKILL.md",
            "clean-room-orchestration.md",
            "china-policy.md",
            "grading-and-verdicts.md",
            "review-rubric.md",
            "reviewer-panels.md",
            "report-template.md",
            "ledger-validation.md",
            "rendered-pagination-audit.md",
            "citation-audit.md",
            "ai-style-audit.md",
            "rules/scripts/validate_review_bundle.py",
            "rules/scripts/validate_semantic_acceptance_output.py",
        ]
        neutral_packet = [
            "00-manifest.md",
            "01-policy-basis.md",
            "00-page-inventory.csv",
            "00-bibliography-inventory.csv",
            "00-citation-candidate-ledger.csv",
            "00-unmatched-bracket-ledger.csv",
            "00-citation-inventory.csv",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            masters = SemanticAcceptanceFixture(root, degree="masters")
            masters.process["governing_local_files"] = [
                {"neutral_file": "rule-01.txt", "official_title": "Rule 1", "sha256": "A" * 64},
                {"neutral_file": "rule-02.txt", "official_title": "Rule 2", "sha256": "B" * 64},
            ]
            self.assertEqual(
                [
                    *common_reviewer_rules,
                    "rule-01.txt",
                    "rule-02.txt",
                    "frozen-thesis.pdf",
                    *neutral_packet,
                    "R1-comprehensive-review.md",
                ],
                MODULE.canonical_sa_opened_inputs(
                    root, masters.process, "R1", []
                ),
            )
            self.assertEqual(
                [
                    "00-process-parameters.json",
                    "SKILL.md",
                    "clean-room-orchestration.md",
                    "report-template.md",
                    "ledger-validation.md",
                    "ai-style-audit.md",
                    "rules/scripts/validate_review_bundle.py",
                    "rules/scripts/validate_semantic_acceptance_output.py",
                    "frozen-thesis.pdf",
                    "00-manifest.md",
                    "00-page-inventory.csv",
                    "05-ai-style-assessment.md",
                ],
                MODULE.canonical_sa_opened_inputs(
                    root, masters.process, "AI", []
                ),
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doctorate = SemanticAcceptanceFixture(root, degree="doctorate")
            self.assertEqual(
                [
                    *common_reviewer_rules,
                    "frozen-thesis.pdf",
                    *neutral_packet,
                    "R5-comprehensive-review.md",
                    "02-page-layout-ledger.md",
                    "02-page-layout-ledger.csv",
                    "03-bibliography-audit-ledger.md",
                    "03-bibliography-audit-ledger.csv",
                    "page-renders/P0001.png",
                    "page-renders/P0002.png",
                    "page-renders/P0003.png",
                    "page-renders/P0004.png",
                    "page-renders/P0005.png",
                    "page-renders/P0006.png",
                ],
                MODULE.canonical_sa_opened_inputs(
                    root, doctorate.process, "R5", []
                ),
            )

    def test_set_mode_requires_every_declared_target_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            artifacts = MODULE.target_artifacts(
                root, fixture.process, "R3", []
            )
            for relative in artifacts:
                path = root / relative
                original = path.read_bytes()
                path.unlink()
                errors, _ = MODULE.validate_set(root, SHARED, require_gate=False)
                self.assertTrue(
                    any(relative in error and "missing or unsafe" in error for error in errors),
                    (relative, errors),
                )
                path.write_bytes(original)

    @unittest.skipUnless(os.name == "nt", "NTFS junction regression is Windows-specific")
    def test_set_mode_rejects_required_and_unrelated_ntfs_junctions(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external_directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)

            render_link = root / "page-renders"
            render_target = Path(external_directory) / "render-copy"
            shutil.copytree(render_link, render_target)
            shutil.rmtree(render_link)
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(render_link), str(render_target)],
                text=True,
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest(created.stdout + created.stderr)
            try:
                errors, _ = MODULE.validate_set(root, SHARED, require_gate=False)
                self.assertTrue(any("reparse/symlink" in error for error in errors), errors)
            finally:
                os.rmdir(render_link)

            shutil.copytree(render_target, render_link)
            unrelated_target = Path(external_directory) / "unrelated"
            unrelated_target.mkdir()
            unrelated_link = root / "unrelated-junction"
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(unrelated_link), str(unrelated_target)],
                text=True,
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest(created.stdout + created.stderr)
            try:
                errors, _ = MODULE.validate_set(root, SHARED, require_gate=False)
                self.assertTrue(any("unrelated-junction" in error for error in errors), errors)
            finally:
                os.rmdir(unrelated_link)

    def test_materializer_removes_gate_on_dependency_and_closure_exceptions(self) -> None:
        class LoadFailure:
            @staticmethod
            def load_shared_validator():
                raise RuntimeError("shared load failed")

        class ClosureFailure:
            calls = 0

            @staticmethod
            def load_shared_validator():
                return object()

            @classmethod
            def validate_set(
                cls,
                root: Path,
                shared: object,
                *,
                require_gate: bool,
                derived_cache: dict[str, object] | None = None,
            ):
                cls.calls += 1
                if cls.calls == 1:
                    return [], {"schema": "test", "status": "PASS"}
                raise RuntimeError("post-write closure failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gate = root / MATERIALIZER_MODULE.GATE_FILE
            gate.write_text('{"status":"PASS"}', encoding="utf-8")
            errors = MATERIALIZER_MODULE.materialize(root, LoadFailure())
            self.assertTrue(any("shared load failed" in error for error in errors), errors)
            self.assertFalse(gate.exists())

            gate.write_text('{"status":"PASS"}', encoding="utf-8")
            ClosureFailure.calls = 0
            errors = MATERIALIZER_MODULE.materialize(root, ClosureFailure())
            self.assertTrue(any("post-write closure failed" in error for error in errors), errors)
            self.assertFalse(gate.exists())

    def test_closed_markdown_and_evidence_inputs_reject_adjudication_and_peers(self) -> None:
        for instruction in (
            "The Chair ought to reject this target.",
            "This evidence warrants grade B.",
            "The defense ought not proceed.",
        ):
            self.assertIsNotNone(
                MODULE.ADJUDICATION_INSTRUCTION_RE.search(instruction),
                instruction,
            )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            report = root / "SA-R1.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "# Semantic acceptance — R1\n",
                    "# Semantic acceptance — R1\nThis preamble assigns Official grade A.\n",
                ).replace(
                    "- Overall semantic acceptance: PASS",
                    "- Overall semantic acceptance: PASS\n- Official grade: A and defense approved",
                ).replace(
                    "Semantic acceptance is bounded to the frozen PDF, target outputs, and declared public authority.",
                    "Official grade A is assigned and the Chair should reject this thesis after defense.",
                ),
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("H1-to-first-H2 gap" in error for error in errors), errors)
            self.assertTrue(any("field order/set" in error for error in errors), errors)
            self.assertTrue(any("attempts to grade/adjudicate" in error for error in errors), errors)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            csv_path = root / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            rows[0]["SemanticBasis"] = (
                "R2-comprehensive-review.md and ../secret.tex and secret.py "
                "supply the decisive evidence for this acceptance row."
            )
            rows[1]["SemanticBasis"] = (
                "private/00-manifest.md is used as an unreceipted alternate packet."
            )
            rows[2]["EvidenceAnchor"] = (
                "physical p.3, Chair must reject the defense and create a new finding"
            )
            rows[3]["SemanticBasis"] = (
                "The evidence is treated as an official grade and recommends a defense decision."
            )
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("peer actor evidence input" in error for error in errors), errors)
            self.assertTrue(any("prohibited evidence input/path" in error for error in errors), errors)
            self.assertTrue(any("secret.py" in error for error in errors), errors)
            self.assertTrue(any("private/00-manifest.md" in error for error in errors), errors)
            self.assertTrue(
                any("EvidenceAnchor attempts to grade/adjudicate" in error for error in errors),
                errors,
            )
            self.assertTrue(
                any("SemanticBasis attempts to grade/adjudicate" in error for error in errors),
                errors,
            )

    def test_process_shape_and_exact_lowercase_disposition_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            csv_path = root / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            rows[0]["AcceptanceDisposition"] = "PASS"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("disposition must be pass or fail" in error for error in errors), errors)

            rows[0]["AcceptanceDisposition"] = "pass"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            report = root / "SA-R1.md"
            report.write_text(
                report.read_text(encoding="utf-8").replace(
                    "- Overall semantic acceptance: PASS",
                    "- Overall semantic acceptance: pass",
                ),
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("must be PASS" in error for error in errors), errors)

            fixture.process["physical_page_count"] = "6"
            (root / "00-process-parameters.json").write_text(
                json.dumps(fixture.process, indent=2), encoding="utf-8"
            )
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("positive integer" in error for error in errors), errors)

    def test_duplicate_json_keys_fail_for_process_and_materialized_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            process_path = root / "00-process-parameters.json"
            process_text = process_path.read_text(encoding="utf-8")
            process_path.write_text(
                process_text.replace(
                    '"degree_level": "masters",',
                    '"degree_level": "masters",\n  "degree_level": "doctorate",',
                    1,
                ),
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_actor(root, "R1", SHARED)
            self.assertTrue(any("duplicate JSON key 'degree_level'" in error for error in errors), errors)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            result = self.run_materializer(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            gate_path = root / MODULE.GATE_FILE
            gate_value = json.loads(gate_path.read_text(encoding="utf-8"))
            gate_value.pop("status")
            prefix = json.dumps(gate_value, ensure_ascii=False)[:-1]
            gate_path.write_text(
                prefix + ', "status": "FAIL", "status": "PASS"}\n',
                encoding="utf-8",
            )
            errors, _ = MODULE.validate_set(root, SHARED, require_gate=True)
            self.assertTrue(any("duplicate JSON key 'status'" in error for error in errors), errors)

    def test_full_set_and_materializer_cache_pdf_derivations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            actual_reader = pypdf.PdfReader
            reader_calls = 0

            def counted_reader(*args: object, **kwargs: object):
                nonlocal reader_calls
                reader_calls += 1
                return actual_reader(*args, **kwargs)

            with mock.patch.object(pypdf, "PdfReader", new=counted_reader):
                errors, _ = MODULE.validate_set(root, SHARED, require_gate=False)
            self.assertEqual([], errors)
            self.assertLessEqual(reader_calls, 6, reader_calls)

            reader_calls = 0
            with mock.patch.object(pypdf, "PdfReader", new=counted_reader):
                errors = MATERIALIZER_MODULE.materialize(root, MODULE)
            self.assertEqual([], errors)
            self.assertLessEqual(reader_calls, 7, reader_calls)

    def test_owner_row_universes_are_bound_to_stage_p_masters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R3", root)

            write_csv(root / "04-citation-claim-audit-ledger.csv", ["PairID"], [])
            page_rows = MODULE.read_generic_csv(root / "02-page-layout-ledger.csv", [])
            write_csv(root / "02-page-layout-ledger.csv", ["PageID"], page_rows[:1])
            bibliography_rows = MODULE.read_generic_csv(
                root / "03-bibliography-audit-ledger.csv", []
            )
            write_csv(
                root / "03-bibliography-audit-ledger.csv",
                SHARED.BIB_LEDGER_COLUMNS,
                bibliography_rows[:-1],
            )
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(any("02-page-layout" in error and "universe" in error for error in errors), errors)
            self.assertTrue(any("03-bibliography" in error and "universe" in error for error in errors), errors)
            self.assertTrue(any("04-citation" in error and "universe" in error for error in errors), errors)

    def test_page_unit_requires_its_exact_integer_page_not_a_substring(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R3", root)
            csv_path = root / "SA-R3.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            page_row = next(
                row
                for row in rows
                if row["TargetUnitType"] == "page"
                and row["TargetUnitID"] == "P0002"
            )
            page_row["EvidenceAnchor"] = "physical p.1-6, generic containing range"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("page unit P0002 must include an exact singleton physical p.2" in error for error in errors),
                errors,
            )
            page_row["EvidenceAnchor"] = "physical p.2xyz, malformed token suffix"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            errors, _ = MODULE.validate_actor(root, "R3", SHARED)
            self.assertTrue(
                any("page unit P0002 must include an exact singleton physical p.2" in error for error in errors),
                errors,
            )

    def test_round_set_materializes_and_detects_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            result = self.run_materializer(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith("MATERIALIZED\n"), result.stdout)
            gate = root / MODULE.GATE_FILE
            self.assertTrue(gate.is_file())
            errors, expected = MODULE.validate_set(root, SHARED, require_gate=True)
            self.assertEqual([], errors)
            gate_value = json.loads(gate.read_text(encoding="utf-8"))
            self.assertEqual(expected, gate_value)
            self.assertEqual(
                "thesis-review-semantic-acceptance-gate-v2",
                gate_value["schema"],
            )
            self.assertEqual(digest(root / "00-process-parameters.json"), gate_value["process_sha256"])
            self.assertEqual(
                {
                    f"SA-{target}": fixture.process["actor_prompt_sha256"][f"SA-{target}"]
                    for target in fixture.targets
                },
                gate_value["sa_actor_prompt_sha256"],
            )
            (root / "R2-comprehensive-review.md").write_text("drift", encoding="utf-8")
            errors, _ = MODULE.validate_set(root, SHARED, require_gate=True)
            self.assertTrue(any("target artifact hash mismatch" in error for error in errors), errors)
            self.assertTrue(any("gate content/hash closure mismatch" in error for error in errors), errors)

    def test_finalized_set_rejects_hardlinked_acceptance_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "round"
            root.mkdir()
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            os.link(acceptance_dir / "SA-R1.md", base / "SA-R1-alias.md")
            errors, expected = MODULE.validate_set(
                root, SHARED, require_gate=False
            )
            self.assertIsNone(expected)
            self.assertTrue(
                any("single-link" in error for error in errors), errors
            )

    def test_set_terminal_closure_rejects_post_preflight_late_drift(self) -> None:
        for mutation_kind in ("hardlink", "topology", "bytes", "target-bytes"):
            with (
                self.subTest(mutation_kind=mutation_kind),
                tempfile.TemporaryDirectory() as directory,
            ):
                base = Path(directory)
                root = base / "round"
                root.mkdir()
                fixture = SemanticAcceptanceFixture(root)
                acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
                for target_name in fixture.targets:
                    fixture.write_acceptance(target_name, acceptance_dir)
                remove_ephemeral_sa_view_rules(root)
                materialized = MATERIALIZER_MODULE.materialize(root, MODULE)
                self.assertEqual([], materialized)
                target = (
                    root / "R1-comprehensive-review.md"
                    if mutation_kind == "target-bytes"
                    else acceptance_dir / "SA-R1.md"
                )
                alias = base / "SA-R1-late-set-alias.md"
                original_preflight = MODULE.preflight_tree_no_reparse
                calls = 0

                def mutate_after_set_terminal_preflight(*args, **kwargs):
                    nonlocal calls
                    snapshot = original_preflight(*args, **kwargs)
                    calls += 1
                    if calls == 10:
                        if mutation_kind == "hardlink":
                            os.link(target, alias)
                        elif mutation_kind == "topology":
                            (root / "late-set-extra.txt").write_text(
                                "late set topology drift\n", encoding="utf-8"
                            )
                        else:
                            overwrite_same_length_and_restore_mtime(target)
                    return snapshot

                with mock.patch.object(
                    MODULE,
                    "preflight_tree_no_reparse",
                    side_effect=mutate_after_set_terminal_preflight,
                ):
                    errors, expected = MODULE.validate_set(
                        root, SHARED, require_gate=True
                    )
                self.assertEqual(10, calls)
                self.assertIsNone(expected)
                self.assertTrue(errors)
                expected_error = (
                    "terminal topology closure mismatch"
                    if mutation_kind == "topology"
                    else "terminal file identity or bytes closure mismatch"
                )
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )
                if mutation_kind == "hardlink":
                    self.assertEqual(2, target.stat().st_nlink)

    def test_materializer_rejects_second_set_terminal_hardlink_and_removes_gate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "round"
            root.mkdir()
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target_name in fixture.targets:
                fixture.write_acceptance(target_name, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            target = acceptance_dir / "SA-R1.md"
            alias = base / "SA-R1-late-materializer-alias.md"
            original_preflight = MODULE.preflight_tree_no_reparse
            calls = 0

            def hardlink_after_second_set_terminal_preflight(*args, **kwargs):
                nonlocal calls
                snapshot = original_preflight(*args, **kwargs)
                calls += 1
                if calls == 20:
                    os.link(target, alias)
                return snapshot

            with mock.patch.object(
                MODULE,
                "preflight_tree_no_reparse",
                side_effect=hardlink_after_second_set_terminal_preflight,
            ):
                errors = MATERIALIZER_MODULE.materialize(root, MODULE)
            self.assertEqual(20, calls)
            self.assertTrue(errors)
            self.assertTrue(
                any(
                    "terminal file identity or bytes closure mismatch" in error
                    for error in errors
                ),
                errors,
            )
            self.assertFalse((root / MODULE.GATE_FILE).exists())
            self.assertEqual(2, target.stat().st_nlink)

    @unittest.skipUnless(os.name == "nt", "NTFS stream test is Windows-specific")
    def test_finalized_set_rejects_named_streams_on_pair_and_gate(self) -> None:
        for target_kind in ("pair", "gate"):
            with self.subTest(target_kind=target_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
                for target in fixture.targets:
                    fixture.write_acceptance(target, acceptance_dir)
                remove_ephemeral_sa_view_rules(root)
                require_gate = target_kind == "gate"
                if require_gate:
                    materialized = self.run_materializer(root)
                    self.assertEqual(
                        0,
                        materialized.returncode,
                        materialized.stdout + materialized.stderr,
                    )
                    target = root / MODULE.GATE_FILE
                else:
                    target = acceptance_dir / "SA-R2.csv"
                stream = Path(f"{target}:semantic-set-regression")
                try:
                    stream.write_bytes(b"hidden semantic-acceptance stream\n")
                except OSError as exc:
                    self.skipTest(
                        f"fixture volume cannot create NTFS named streams: {exc}"
                    )
                errors, _ = MODULE.validate_set(
                    root, SHARED, require_gate=require_gate
                )
                self.assertTrue(errors)
                self.assertTrue(
                    any("NTFS named" in error or "unsafe" in error for error in errors),
                    errors,
                )

    def test_finalized_set_rejects_late_pair_and_target_identity_replacement(self) -> None:
        for target_kind in ("pair", "target"):
            with self.subTest(target_kind=target_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixture = SemanticAcceptanceFixture(root)
                acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
                for target in fixture.targets:
                    fixture.write_acceptance(target, acceptance_dir)
                remove_ephemeral_sa_view_rules(root)
                replacement_target = (
                    acceptance_dir / "SA-R1.md"
                    if target_kind == "pair"
                    else root / "R1-comprehensive-review.md"
                )
                original_expected_gate = MODULE.expected_gate

                def replace_after_gate_projection(*args, **kwargs):
                    result = original_expected_gate(*args, **kwargs)
                    payload = replacement_target.read_bytes()
                    replacement_target.unlink()
                    replacement_target.write_bytes(payload)
                    return result

                with mock.patch.object(
                    MODULE,
                    "expected_gate",
                    side_effect=replace_after_gate_projection,
                ):
                    errors, _ = MODULE.validate_set(
                        root, SHARED, require_gate=False
                    )
                self.assertTrue(errors)
                self.assertTrue(
                    any(
                        "identity or bytes changed" in error
                        or "topology changed" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_round_set_rejects_root_level_actor_output_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            (root / "SA-R1.md").write_text("leaked private-view output", encoding="utf-8")

            errors, expected = MODULE.validate_set(root, SHARED, require_gate=False)
            self.assertIsNone(expected)
            self.assertTrue(
                any("SA actor outputs must exist only inside" in error for error in errors),
                errors,
            )

            gate = root / MODULE.GATE_FILE
            gate.write_text('{"status":"PASS"}', encoding="utf-8")
            result = self.run_materializer(root)
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertFalse(gate.exists())

    def test_doctorate_complete_set_materializes_all_six_target_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root, degree="doctorate")
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            result = self.run_materializer(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            gate = json.loads((root / MODULE.GATE_FILE).read_text(encoding="utf-8"))
            self.assertEqual(
                {"R1", "R2", "R3", "R4", "R5", "AI"},
                set(gate["targets"]),
            )
            self.assertTrue(
                all(item["status"] == "PASS" for item in gate["targets"].values())
            )
            errors, expected = MODULE.validate_set(
                root, SHARED, require_gate=True
            )
            self.assertEqual([], errors)
            self.assertEqual(gate, expected)

    def test_fail_row_prevents_gate_and_removes_stale_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            first = self.run_materializer(root)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            csv_path = acceptance_dir / "SA-R1.csv"
            rows = MODULE.read_csv_rows(csv_path, [])
            rows[0]["AcceptanceDisposition"] = "fail"
            write_csv(csv_path, MODULE.CSV_COLUMNS, rows)
            second = self.run_materializer(root)
            self.assertNotEqual(0, second.returncode)
            self.assertTrue(second.stdout.startswith("FAIL\n"), second.stdout)
            self.assertFalse((root / MODULE.GATE_FILE).exists())

    def test_scoped_cli_returns_nonzero_for_an_internally_consistent_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            fixture.write_acceptance("R1", root)
            rows = MODULE.read_csv_rows(root / "SA-R1.csv", [])
            rows[0]["AcceptanceDisposition"] = "fail"
            write_csv(root / "SA-R1.csv", MODULE.CSV_COLUMNS, rows)
            acceptance_md = root / "SA-R1.md"
            acceptance_md.write_text(
                acceptance_md.read_text(encoding="utf-8")
                .replace("Overall semantic acceptance: PASS", "Overall semantic acceptance: FAIL")
                .replace("Acceptance failure count: 0", "Acceptance failure count: 1"),
                encoding="utf-8",
            )
            keep = set(
                MODULE.canonical_sa_opened_inputs(root, fixture.process, "R1", [])
            )
            keep.update({"SA-R1.md", "SA-R1.csv"})
            allowed_dirs = {
                Path(item).parts[0]
                for item in keep
                if len(Path(item).parts) > 1
            }
            for path in list(root.iterdir()):
                if path.is_file() and path.name not in keep:
                    path.unlink()
                elif path.is_dir() and path.name not in allowed_dirs:
                    shutil.rmtree(path)
            errors, result = MODULE.validate_actor(
                root, "R1", SHARED, enforce_closed_view=True
            )
            self.assertEqual([], errors)
            self.assertEqual("FAIL", result["status"])
            cli = self.run_validator(str(root), "R1")
            self.assertEqual(3, cli.returncode)
            self.assertTrue(cli.stdout.startswith("VALID-FAIL\n"), cli.stdout)
            self.assertIn("do not promote", cli.stdout)
            self.assertIn("quarantine", cli.stdout)

    def test_acceptance_directory_rejects_extra_or_missing_actor_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = SemanticAcceptanceFixture(root)
            acceptance_dir = root / MODULE.ACCEPTANCE_DIRECTORY
            for target in fixture.targets:
                fixture.write_acceptance(target, acceptance_dir)
            remove_ephemeral_sa_view_rules(root)
            (acceptance_dir / "old-review.md").write_text("old", encoding="utf-8")
            (acceptance_dir / "SA-AI.csv").unlink()
            errors, _ = MODULE.validate_set(root, SHARED, require_gate=False)
            self.assertTrue(
                any(
                    "file set mismatch" in error
                    or "missing or unsafe semantic-acceptance resident input" in error
                    for error in errors
                ),
                errors,
            )


def sys_executable() -> str:
    import sys

    return sys.executable


if __name__ == "__main__":
    unittest.main()
