#!/usr/bin/env python3
"""Initialize a paper-radar workspace and fetch recent multi-source candidates."""

from __future__ import annotations

import argparse
import copy
import json
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
    parse_datetime,
    profile_digest,
    request_bytes,
    request_json,
    safe_http_url,
    utc_now,
    validate_profile,
    write_json,
)


ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"
HF_DAILY_ENDPOINT = "https://huggingface.co/api/daily_papers"
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

    def add(records: list[dict[str, Any]]) -> None:
        for record in records:
            if not is_recent(record, cutoff, local_zone):
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
        default="arxiv,huggingface",
        help="Comma-separated subset of arxiv,huggingface",
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
            sources = {value.strip().lower() for value in args.sources.split(",") if value.strip()}
            unknown = sources - {"arxiv", "huggingface"}
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
