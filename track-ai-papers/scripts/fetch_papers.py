#!/usr/bin/env python3
"""Initialize a paper-radar workspace and fetch recent multi-source candidates."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from radar_common import (
    DEFAULT_PROFILE,
    RadarError,
    canonical_arxiv_id,
    canonical_record_id,
    clean_authors,
    clean_text,
    ensure_workspace,
    load_json,
    load_state,
    match_topic,
    merge_candidate,
    normalized_match_text,
    parse_datetime,
    profile_digest,
    request_bytes,
    request_json,
    safe_nonnegative_float,
    safe_nonnegative_int,
    safe_http_url,
    utc_now,
    validate_profile,
    write_json,
)


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
HF_DAILY_ENDPOINT = "https://huggingface.co/api/daily_papers"
HF_MODELS_ENDPOINT = "https://huggingface.co/api/models"
DEFAULT_CLASSIC_CATALOG = Path(__file__).resolve().parents[1] / "assets" / "classic-foundations.json"
OPEN_SOURCE_LICENSES = {
    "apache-2.0",
    "mit",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "mpl-2.0",
    "cc0-1.0",
    "unlicense",
}
WEIGHT_SUFFIXES = (".safetensors", ".bin", ".gguf", ".pt", ".pth", ".onnx")
HF_AUXILIARY_BINARY_NAMES = {
    "training_args.bin",
    "optimizer.pt",
    "scheduler.pt",
    "scaler.pt",
    "rng_state.pth",
}
HF_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
ATOM = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def is_recent(record: dict[str, Any], cutoff: datetime, local_zone: ZoneInfo | None = None) -> bool:
    """Keep only papers with a parseable publication date inside the requested window."""
    raw_published = str(record.get("published") or "").strip()
    if len(raw_published) == 10:
        try:
            local_day = datetime.strptime(raw_published, "%Y-%m-%d").date()
            published = datetime.combine(
                local_day,
                datetime.min.time(),
                tzinfo=local_zone or timezone.utc,
            ).astimezone(timezone.utc)
        except ValueError:
            published = None
    else:
        published = parse_datetime(raw_published)
    return published is not None and published >= cutoff


def new_run_id(generated_at: str, digest: str) -> str:
    return f"{generated_at}-{digest}-{uuid.uuid4().hex[:12]}"


def _topic_query(topic: dict[str, Any]) -> str:
    terms = [f'all:"{term.replace(chr(34), "")}"' for term in topic["query_terms"]]
    groups = []
    for group in topic.get("include_all_groups", []):
        group_terms = [f'all:"{term.replace(chr(34), "")}"' for term in group]
        groups.append(f"({' OR '.join(group_terms)})")
    if groups:
        terms.append(f"({' AND '.join(groups)})")
    categories = [f"cat:{category}" for category in topic["arxiv_categories"]]
    return f"({' OR '.join(terms)}) AND ({' OR '.join(categories)})"


def _entry_text(entry: ET.Element, path: str) -> str:
    element = entry.find(path, ATOM)
    return clean_text(element.text if element is not None else "")


def fetch_arxiv_topic(
    topic: dict[str, Any], max_results: int
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    query = _topic_query(topic)
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"{ARXIV_ENDPOINT}?{params}"
    raw = request_bytes(url, headers={"Accept": "application/atom+xml"})
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise RadarError(f"arXiv returned invalid Atom XML for topic {topic['id']}") from exc
    entries = root.findall("atom:entry", ATOM)
    total_text = root.findtext("opensearch:totalResults", default="", namespaces=ATOM)
    try:
        total_results: int | None = int(total_text)
    except (TypeError, ValueError):
        total_results = None
    raw_published = [_entry_text(entry, "atom:published") for entry in entries]
    metadata = {
        "raw_returned": len(entries),
        "total_results": total_results,
        "oldest_returned_published": raw_published[-1] if raw_published else None,
    }
    output: list[dict[str, Any]] = []
    for entry in entries:
        entry_id = _entry_text(entry, "atom:id")
        arxiv_id = canonical_arxiv_id(entry_id)
        title = _entry_text(entry, "atom:title")
        if not arxiv_id or not title:
            continue
        links = {element.attrib.get("rel"): element.attrib.get("href") for element in entry.findall("atom:link", ATOM)}
        pdf_link = next(
            (element.attrib.get("href") for element in entry.findall("atom:link", ATOM) if element.attrib.get("title") == "pdf"),
            None,
        )
        authors = [_entry_text(author, "atom:name") for author in entry.findall("atom:author", ATOM)]
        categories = [element.attrib.get("term", "") for element in entry.findall("atom:category", ATOM)]
        record = {
            "artifact_type": "paper",
            "lane": "recent-paper",
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": _entry_text(entry, "atom:summary"),
            "authors": [author for author in authors if author],
            "published": _entry_text(entry, "atom:published"),
            "updated": _entry_text(entry, "atom:updated"),
            "categories": [value for value in categories if value],
            "primary_category": (
                entry.find("arxiv:primary_category", ATOM).attrib.get("term")
                if entry.find("arxiv:primary_category", ATOM) is not None
                else None
            ),
            "abs_url": links.get("alternate") or f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": pdf_link or f"https://arxiv.org/pdf/{arxiv_id}",
            "project_url": None,
            "code_url": None,
            "topics": [topic["id"]],
            "sources": ["arxiv"],
            "topic_match_terms": {},
            "external": {"hf_upvotes": 0, "hf_featured": False},
        }
        matched, match_terms = match_topic(record, topic)
        if not matched:
            continue
        record["topic_match_terms"][topic["id"]] = match_terms
        record["canonical_id"] = canonical_record_id(record)
        output.append(record)
    return output, url, metadata


def _first(mapping: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", []):
            return value
    return default


def _normalize_hf_item(item: Any, topics: list[dict[str, Any]], feed_date: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    nested = item.get("paper") if isinstance(item.get("paper"), dict) else {}
    merged = {**item, **nested}
    arxiv_id = canonical_arxiv_id(
        str(_first(merged, ("id", "arxiv_id", "arxivId", "paperId", "url", "paper_url"), ""))
    )
    title = clean_text(_first(merged, ("title", "name"), ""))
    abstract = clean_text(_first(merged, ("summary", "abstract", "description"), ""))
    if not title:
        return None
    authors = clean_authors(_first(merged, ("authors", "paper_authors"), []))
    project_url = _first(merged, ("projectPage", "project_page", "projectUrl", "website"))
    code_url = _first(merged, ("githubRepo", "github_repo", "codeUrl", "code_url", "repository"))
    upvotes = _first(merged, ("upvotes", "numUpvotes", "votes"), 0)
    try:
        upvotes = int(upvotes or 0)
    except (TypeError, ValueError):
        upvotes = 0
    record = {
        "artifact_type": "paper",
        "lane": "recent-paper",
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "published": clean_text(_first(merged, ("publishedAt", "published_at", "publicationDate"), "")),
        "updated": clean_text(_first(merged, ("submittedOnDailyAt", "updatedAt", "updated_at"), feed_date)),
        "categories": [],
        "primary_category": None,
        "abs_url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else safe_http_url(_first(merged, ("url", "paper_url"))),
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None,
        "project_url": safe_http_url(project_url),
        "code_url": safe_http_url(code_url),
        "topics": [],
        "sources": ["huggingface"],
        "topic_match_terms": {},
        "external": {
            "hf_upvotes": upvotes,
            "hf_featured": bool(_first(merged, ("featured", "isFeatured"), False)),
        },
        "discovered_on": feed_date,
    }
    for topic in topics:
        matched, terms = match_topic(record, topic)
        if matched:
            record["topics"].append(topic["id"])
            record["topic_match_terms"][topic["id"]] = terms
    if not record["topics"]:
        return None
    record["canonical_id"] = canonical_record_id(record)
    return record


def fetch_hf_day(
    feed_date: str, topics: list[dict[str, Any]], limit: int = 100
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    params = urllib.parse.urlencode({"p": 0, "limit": limit, "date": feed_date, "sort": "trending"})
    url = f"{HF_DAILY_ENDPOINT}?{params}"
    payload = request_json(url)
    if isinstance(payload, dict):
        items = payload.get("papers") or payload.get("items") or payload.get("results") or []
        total_value = payload.get("total") or payload.get("totalCount") or payload.get("count")
    else:
        items = payload
        total_value = None
    if not isinstance(items, list):
        raise RadarError(f"Unexpected Hugging Face daily-papers response shape for {feed_date}")
    records = []
    for item in items:
        record = _normalize_hf_item(item, topics, feed_date)
        if record:
            records.append(record)
    try:
        total_results: int | None = int(total_value) if total_value is not None else None
    except (TypeError, ValueError):
        total_results = None
    return records, url, {"raw_returned": len(items), "total_results": total_results}


def _classic_catalog_path(profile: dict[str, Any]) -> Path:
    configured = str(profile.get("source_config", {}).get("classic_catalog") or DEFAULT_CLASSIC_CATALOG.name)
    if Path(configured).name != configured:
        raise RadarError("source_config.classic_catalog must be a filename inside the skill assets directory")
    return DEFAULT_CLASSIC_CATALOG.parent / configured


def fetch_classics(profile: dict[str, Any]) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    path = _classic_catalog_path(profile)
    payload = load_json(path)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RadarError(f"Classic catalog has an unsupported schema: {path}")
    items = payload.get("papers")
    if not isinstance(items, list):
        raise RadarError(f"Classic catalog has no papers list: {path}")
    topic_ids = {topic["id"] for topic in profile["topics"]}
    records: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise RadarError(f"Classic catalog item {index} must be an object")
        arxiv_id = canonical_arxiv_id(str(item.get("arxiv_id") or ""))
        title = clean_text(item.get("title"))
        published = clean_text(item.get("published"))
        topics = [value for value in item.get("topics", []) if value in topic_ids]
        if not arxiv_id or not title or parse_datetime(published) is None or not topics:
            raise RadarError(f"Classic catalog item {index} is missing a valid ID, title, date, or topic")
        summary = clean_text(item.get("curation_summary"))
        family = clean_text(item.get("family"))
        if not summary or not family:
            raise RadarError(f"Classic catalog item {index} is missing family or curation_summary")
        record = {
            "artifact_type": "paper",
            "lane": "classic-foundation",
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": summary,
            "curation_summary": summary,
            "classic_family": family,
            "authors": clean_authors(item.get("authors", [])),
            "published": published,
            "updated": published,
            "categories": [],
            "primary_category": None,
            "abs_url": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            "project_url": None,
            "code_url": None,
            "topics": topics,
            "sources": ["curated-classics"],
            "topic_match_terms": {topic_id: [family] for topic_id in topics},
            "external": {"hf_upvotes": 0, "hf_featured": False},
        }
        record["canonical_id"] = canonical_record_id(record)
        records.append(record)
    return records, str(path.resolve()), {"raw_returned": len(items), "total_results": len(items)}


def _hf_license(item: dict[str, Any], tags: list[str]) -> tuple[str | None, str | None]:
    card_data = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    license_value = card_data.get("license")
    if isinstance(license_value, list):
        license_value = next((value for value in license_value if isinstance(value, str) and value.strip()), None)
    license_id = clean_text(license_value).lower()
    if license_id:
        if license_id == "other":
            license_name = clean_text(card_data.get("license_name")).lower()
            license_link = clean_text(card_data.get("license_link"))
            return (license_name or None), (license_link or None)
        return license_id, clean_text(card_data.get("license_link")) or None
    for tag in tags:
        if tag.lower().startswith("license:"):
            candidate = clean_text(tag.split(":", 1)[1]).lower()
            if candidate and candidate != "other":
                return candidate, None
    return None, None


def _hf_weight_files(item: dict[str, Any]) -> list[str]:
    siblings = item.get("siblings") if isinstance(item.get("siblings"), list) else []
    output = []
    for sibling in siblings:
        if not isinstance(sibling, dict):
            continue
        name = clean_text(sibling.get("rfilename") or sibling.get("path"))
        lowered = name.lower()
        basename = lowered.rsplit("/", 1)[-1]
        if basename in HF_AUXILIARY_BINARY_NAMES or "adapter" in basename:
            continue
        is_weight = lowered.endswith((".safetensors", ".gguf", ".onnx"))
        if lowered.endswith(".bin"):
            is_weight = bool(re.search(r"(?:pytorch_model|model|consolidated|weights?)(?:[-_.0-9]|$)", basename))
        elif lowered.endswith((".pt", ".pth")):
            is_weight = bool(re.search(r"(?:model|consolidated|checkpoint|weights?)(?:[-_.0-9]|$)", basename))
        if is_weight:
            output.append(name)
    return output


def _normalize_hf_model(
    item: Any,
    profile: dict[str, Any],
    cutoff: datetime,
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    model_id = clean_text(item.get("id") or item.get("modelId"))
    if not HF_MODEL_ID_RE.fullmatch(model_id) or item.get("private") is True:
        return None
    gated = item.get("gated")
    if gated not in (None, False, "false"):
        return None
    tags = [clean_text(value) for value in item.get("tags", []) if clean_text(value)] if isinstance(item.get("tags"), list) else []
    license_id, license_link = _hf_license(item, tags)
    weight_files = _hf_weight_files(item)
    config = profile.get("source_config", {}).get("hf_models", {})
    if config.get("require_explicit_license", True) and not license_id:
        return None
    if config.get("require_weights", True) and not weight_files:
        return None
    interest_terms = [normalized_match_text(value) for value in config.get("include_any", [])]
    searchable = normalized_match_text(" ".join([model_id, clean_text(item.get("pipeline_tag")), *tags]))
    padded_searchable = f" {searchable} "
    if interest_terms and not any(term and f" {term} " in padded_searchable for term in interest_terms):
        return None
    excluded_terms = [normalized_match_text(value) for value in config.get("exclude_any", [])]
    if any(term and f" {term} " in padded_searchable for term in excluded_terms):
        return None
    created_at = clean_text(item.get("createdAt") or item.get("created_at"))
    released = parse_datetime(created_at)
    if released is None or released < cutoff:
        return None
    card_data = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    summary = clean_text(
        card_data.get("summary")
        or card_data.get("description")
        or f"Hugging Face model release for {clean_text(item.get('pipeline_tag')) or 'generative AI'}; tags: {', '.join(tags[:20])}."
    )
    organization = model_id.split("/", 1)[0]
    version_sha = clean_text(item.get("sha"))
    model_url = f"https://huggingface.co/{model_id}"
    license_url = safe_http_url(urllib.parse.urljoin(f"{model_url}/", license_link)) if license_link else None
    openness_class = "open-source" if license_id in OPEN_SOURCE_LICENSES else "open-weights"
    if config.get("require_open_source_license", False) and openness_class != "open-source":
        return None
    if openness_class == "open-weights" and not config.get("allow_restrictive_open_weights", True):
        return None
    record: dict[str, Any] = {
        "artifact_type": "model-release",
        "lane": "open-model",
        "model_id": model_id,
        "organization": organization,
        "title": model_id,
        "abstract": summary,
        "authors": [organization],
        "published": created_at,
        "released_at": created_at,
        "updated": clean_text(item.get("lastModified") or item.get("last_modified") or created_at),
        "version_sha": version_sha or None,
        "categories": [],
        "primary_category": None,
        "abs_url": model_url,
        "pdf_url": None,
        "project_url": model_url,
        "code_url": None,
        "model_card_url": model_url,
        "weights_url": f"{model_url}/tree/main",
        "weight_files": weight_files,
        "license_id": license_id,
        "license_url": license_url,
        "openness_class": openness_class,
        "pipeline_tag": clean_text(item.get("pipeline_tag")) or None,
        "tags": tags,
        "topics": [],
        "sources": ["huggingface-models"],
        "topic_match_terms": {},
        "external": {
            "hf_upvotes": 0,
            "hf_featured": False,
            "hf_model_likes": safe_nonnegative_int(item.get("likes")),
            "hf_model_downloads": safe_nonnegative_int(item.get("downloads")),
            "hf_trending_score": safe_nonnegative_float(item.get("trendingScore")),
        },
    }
    for topic in profile["topics"]:
        matched, terms = match_topic(record, topic)
        if matched:
            record["topics"].append(topic["id"])
            record["topic_match_terms"][topic["id"]] = terms
    if not record["topics"]:
        fallback = clean_text(config.get("fallback_topic"))
        if fallback not in {topic["id"] for topic in profile["topics"]}:
            return None
        record["topics"] = [fallback]
        record["topic_match_terms"] = {fallback: ["verified-open-model-release"]}
    record["canonical_id"] = canonical_record_id(record)
    record["entity_id"] = record["canonical_id"]
    record["event_id"] = f"{record['canonical_id']}@{version_sha[:12]}" if version_sha else record["canonical_id"]
    return record


def fetch_hf_models(
    profile: dict[str, Any], local_now: datetime
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    config = profile.get("source_config", {}).get("hf_models", {})
    limit = int(config.get("limit") or 100)
    lookback_days = int(config.get("lookback_days") or 45)
    cutoff_local = datetime.combine(
        local_now.date() - timedelta(days=lookback_days - 1),
        datetime.min.time(),
        tzinfo=local_now.tzinfo,
    )
    cutoff = cutoff_local.astimezone(timezone.utc)
    params = urllib.parse.urlencode({"sort": "trendingScore", "direction": -1, "limit": limit})
    expanded_fields = (
        "author",
        "createdAt",
        "lastModified",
        "downloads",
        "likes",
        "pipeline_tag",
        "tags",
        "gated",
        "private",
        "sha",
        "cardData",
        "siblings",
    )
    params += "&" + "&".join(f"expand={urllib.parse.quote(field)}" for field in expanded_fields)
    url = f"{HF_MODELS_ENDPOINT}?{params}"
    payload = request_json(url)
    if not isinstance(payload, list):
        raise RadarError("Unexpected Hugging Face models response shape")
    records = []
    for item in payload:
        record = _normalize_hf_model(item, profile, cutoff)
        if record:
            records.append(record)
    return records, url, {
        "raw_returned": len(payload),
        "total_results": None,
        "requested_limit": limit,
        "lookback_days": lookback_days,
    }


def initialize(workspace: Path, profile_path: Path, force: bool) -> dict[str, Any]:
    profile = ensure_workspace(workspace, profile_path, force=force)
    return {
        "workspace": str(workspace.resolve()),
        "profile": str((workspace / "profile.json").resolve()),
        "profile_name": profile["name"],
        "state": str((workspace / "state.json").resolve()),
    }


def fetch(
    workspace: Path,
    lookback_days: int | None,
    per_topic: int | None,
    sources: set[str],
    include_seen: bool,
    arxiv_delay: float,
) -> dict[str, Any]:
    profile = ensure_workspace(workspace)
    validate_profile(profile)
    days = lookback_days or int(profile["lookback_days"])
    limit = per_topic or int(profile["max_candidates_per_topic"])
    local_zone = ZoneInfo(profile["timezone"])
    local_now = datetime.now(local_zone)
    cutoff_local = datetime.combine(local_now.date() - timedelta(days=days - 1), datetime.min.time(), tzinfo=local_zone)
    cutoff = cutoff_local.astimezone(timezone.utc)
    generated_at = utc_now()
    digest = profile_digest(profile)
    run_id = new_run_id(generated_at, digest)
    source_log: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "run_id": run_id,
        "profile_digest": digest,
        "window": {
            "lookback_days": days,
            "timezone": profile["timezone"],
            "local_start_date": cutoff_local.date().isoformat(),
            "cutoff_utc": cutoff.isoformat().replace("+00:00", "Z"),
        },
        "queries": [],
        "failures": [],
    }
    merged: dict[str, dict[str, Any]] = {}

    def add(records: list[dict[str, Any]], *, enforce_recent: bool = True) -> None:
        for record in records:
            if enforce_recent and not is_recent(record, cutoff, local_zone):
                continue
            key = record["canonical_id"]
            if key in merged:
                merge_candidate(merged[key], record)
            else:
                merged[key] = copy.deepcopy(record)

    if "arxiv" in sources:
        for index, topic in enumerate(profile["topics"]):
            try:
                records, url, metadata = fetch_arxiv_topic(topic, limit)
                add(records)
                oldest = parse_datetime(metadata.get("oldest_returned_published"))
                raw_returned = int(metadata.get("raw_returned") or 0)
                total_results = metadata.get("total_results")
                more_available = total_results > raw_returned if isinstance(total_results, int) else raw_returned >= limit
                potentially_truncated = bool(more_available and (oldest is None or oldest >= cutoff))
                source_log["queries"].append(
                    {
                        "source": "arxiv",
                        "topic": topic["id"],
                        "url": url,
                        "returned": len(records),
                        "raw_returned": raw_returned,
                        "requested_limit": limit,
                        "total_results": total_results,
                        "oldest_returned_published": metadata.get("oldest_returned_published"),
                        "potentially_truncated_window": potentially_truncated,
                        "status": "ok",
                    }
                )
            except RadarError as exc:
                source_log["failures"].append({"source": "arxiv", "topic": topic["id"], "error": str(exc)})
            if index + 1 < len(profile["topics"]) and arxiv_delay > 0:
                time.sleep(arxiv_delay)

    if "huggingface" in sources:
        for offset in range(days):
            feed_date = (local_now.date() - timedelta(days=offset)).isoformat()
            try:
                hf_limit = 100
                records, url, metadata = fetch_hf_day(feed_date, profile["topics"], hf_limit)
                add(records)
                raw_returned = int(metadata.get("raw_returned") or 0)
                total_results = metadata.get("total_results")
                potentially_truncated = bool(
                    total_results > raw_returned if isinstance(total_results, int) else raw_returned >= hf_limit
                )
                source_log["queries"].append(
                    {
                        "source": "huggingface",
                        "date": feed_date,
                        "url": url,
                        "returned": len(records),
                        "raw_returned": raw_returned,
                        "requested_limit": hf_limit,
                        "total_results": total_results,
                        "potentially_truncated_window": potentially_truncated,
                        "status": "ok",
                    }
                )
            except RadarError as exc:
                source_log["failures"].append({"source": "huggingface", "date": feed_date, "error": str(exc)})

    if "classics" in sources:
        try:
            records, location, metadata = fetch_classics(profile)
            add(records, enforce_recent=False)
            source_log["queries"].append(
                {
                    "source": "classics",
                    "lane": "classic-foundation",
                    "url": location,
                    "returned": len(records),
                    "raw_returned": metadata["raw_returned"],
                    "requested_limit": metadata["raw_returned"],
                    "total_results": metadata["total_results"],
                    "potentially_truncated_window": False,
                    "status": "ok",
                }
            )
        except RadarError as exc:
            source_log["failures"].append({"source": "classics", "lane": "classic-foundation", "error": str(exc)})

    if "hf-models" in sources:
        try:
            records, url, metadata = fetch_hf_models(profile, local_now)
            add(records, enforce_recent=False)
            raw_returned = int(metadata.get("raw_returned") or 0)
            requested_limit = int(metadata.get("requested_limit") or 100)
            source_log["queries"].append(
                {
                    "source": "hf-models",
                    "lane": "open-model",
                    "url": url,
                    "returned": len(records),
                    "raw_returned": raw_returned,
                    "requested_limit": requested_limit,
                    "total_results": metadata.get("total_results"),
                    "lookback_days": metadata.get("lookback_days"),
                    "potentially_truncated_window": raw_returned >= requested_limit,
                    "status": "ok",
                }
            )
        except RadarError as exc:
            source_log["failures"].append({"source": "hf-models", "lane": "open-model", "error": str(exc)})

    state = load_state(workspace / "state.json")
    seen = state["seen"]
    candidates = [record for key, record in merged.items() if include_seen or key not in seen]
    candidates.sort(
        key=lambda item: (
            parse_datetime(item.get("published")) or datetime.min.replace(tzinfo=timezone.utc),
            len(item.get("sources", [])),
            int(item.get("external", {}).get("hf_upvotes") or 0),
        ),
        reverse=True,
    )
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "run_id": run_id,
        "profile_name": profile["name"],
        "profile_digest": digest,
        "window": source_log["window"],
        "count": len(candidates),
        "candidates": candidates,
    }
    source_log["candidate_count"] = len(candidates)
    source_log["deduplicated_record_count"] = len(merged)
    source_log["seen_excluded_count"] = len(merged) - len(candidates) if not include_seen else 0
    source_log["potentially_truncated_query_count"] = sum(
        1 for entry in source_log["queries"] if entry.get("potentially_truncated_window")
    )
    write_json(workspace / "candidates.json", payload)
    write_json(workspace / "source-log.json", source_log)
    return {
        "workspace": str(workspace.resolve()),
        "candidate_count": len(candidates),
        "source_failures": len(source_log["failures"]),
        "candidates": str((workspace / "candidates.json").resolve()),
        "source_log": str((workspace / "source-log.json").resolve()),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="Create a radar workspace")
    init_parser.add_argument("--workspace", type=Path, required=True)
    init_parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    init_parser.add_argument("--force", action="store_true", help="Replace an existing workspace profile")
    fetch_parser = subparsers.add_parser("fetch", help="Fetch and normalize recent candidates")
    fetch_parser.add_argument("--workspace", type=Path, required=True)
    fetch_parser.add_argument("--lookback-days", type=int)
    fetch_parser.add_argument("--per-topic", type=int)
    fetch_parser.add_argument(
        "--sources",
        help=(
            "Comma-separated subset of arxiv,huggingface,classics,hf-models. "
            "Defaults to the two paper sources for v1 profiles and all four sources for v2 profiles."
        ),
    )
    fetch_parser.add_argument("--include-seen", action="store_true")
    fetch_parser.add_argument("--arxiv-delay", type=float, default=3.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        if args.command == "init":
            result = initialize(args.workspace, args.profile, args.force)
        else:
            if args.sources:
                sources = {value.strip().lower() for value in args.sources.split(",") if value.strip()}
            else:
                current_profile = load_json(args.workspace / "profile.json")
                sources = (
                    {"arxiv", "huggingface", "classics", "hf-models"}
                    if current_profile.get("profile_version") == 2
                    else {"arxiv", "huggingface"}
                )
            unknown = sources - {"arxiv", "huggingface", "classics", "hf-models"}
            if unknown or not sources:
                raise RadarError(f"Invalid sources: {', '.join(sorted(unknown or sources))}")
            if args.lookback_days is not None and args.lookback_days <= 0:
                raise RadarError("--lookback-days must be positive")
            if args.per_topic is not None and args.per_topic <= 0:
                raise RadarError("--per-topic must be positive")
            result = fetch(
                args.workspace,
                args.lookback_days,
                args.per_topic,
                sources,
                args.include_seen,
                max(0.0, args.arxiv_delay),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RadarError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
