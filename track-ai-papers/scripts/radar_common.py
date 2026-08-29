#!/usr/bin/env python3
"""Shared helpers for the track-ai-papers skill."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = SKILL_ROOT / "assets" / "default-profile.json"
USER_AGENT = "track-ai-papers/1.0 (+https://github.com/ZeyuLing/research_autocode_skills)"
SUPPORTED_PROFILE_VERSIONS = {1, 2}
ARXIV_ID_RE = re.compile(
    r"(?:(?:arxiv\.org/(?:abs|pdf|html)/)|(?:arxiv:))?"
    r"(?P<id>(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)",
    re.IGNORECASE,
)


class RadarError(RuntimeError):
    """A user-actionable radar failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RadarError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RadarError(f"Invalid JSON in {path}: {exc}") from exc


def load_state(path: Path) -> dict[str, Any]:
    state = load_json(path)
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or not isinstance(state.get("seen"), dict)
    ):
        raise RadarError(f"{path} must use schema_version 1 and contain a seen object")
    return state


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    write_text(path, payload)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def profile_digest(profile: dict[str, Any]) -> str:
    encoded = json.dumps(profile, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError as exc:
        raise RadarError(f"Missing required file: {path}") from exc


def validate_profile(profile: dict[str, Any]) -> None:
    if not isinstance(profile, dict):
        raise RadarError("Profile must be a JSON object")
    required = {
        "profile_version",
        "name",
        "language",
        "timezone",
        "lookback_days",
        "max_candidates_per_topic",
        "max_review_candidates",
        "max_digest_papers",
        "max_per_topic",
        "relevance_threshold",
        "quality_threshold",
        "watch_threshold",
        "topics",
        "quality_policy",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise RadarError(f"Profile is missing fields: {', '.join(missing)}")
    if profile["profile_version"] not in SUPPORTED_PROFILE_VERSIONS or isinstance(profile["profile_version"], bool):
        raise RadarError("profile_version must be 1 or 2")
    if not isinstance(profile["name"], str) or not profile["name"].strip():
        raise RadarError("name must be a non-empty string")
    if not isinstance(profile["language"], str) or profile["language"] not in {"zh-CN", "en"}:
        raise RadarError("language must be 'zh-CN' or 'en'")
    if not isinstance(profile["timezone"], str) or not profile["timezone"].strip():
        raise RadarError("timezone must be a non-empty IANA timezone string")
    try:
        ZoneInfo(profile["timezone"])
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise RadarError(f"Unknown IANA timezone: {profile['timezone']!r}") from exc
    if not isinstance(profile["topics"], list) or not profile["topics"]:
        raise RadarError("Profile topics must be a non-empty list")
    ids: set[str] = set()
    for index, topic in enumerate(profile["topics"]):
        if not isinstance(topic, dict):
            raise RadarError(f"Topic {index} must be an object")
        needed = {"id", "label", "arxiv_categories", "query_terms", "include_any", "exclude_any"}
        absent = sorted(needed - set(topic))
        if absent:
            raise RadarError(f"Topic {index} is missing fields: {', '.join(absent)}")
        topic_id = topic["id"]
        if not isinstance(topic_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", topic_id):
            raise RadarError(f"Invalid topic id: {topic_id!r}")
        if topic_id in ids:
            raise RadarError(f"Duplicate topic id: {topic_id}")
        ids.add(topic_id)
        if not isinstance(topic["label"], str) or not topic["label"].strip():
            raise RadarError(f"Topic {topic_id}.label must be a non-empty string")
        for field in ("arxiv_categories", "query_terms", "include_any", "exclude_any"):
            values = topic[field]
            if not isinstance(values, list):
                raise RadarError(f"Topic {topic_id}.{field} must be a list")
            if field != "exclude_any" and not values:
                raise RadarError(f"Topic {topic_id}.{field} must not be empty")
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise RadarError(f"Topic {topic_id}.{field} must contain only non-empty strings")
        include_all_groups = topic.get("include_all_groups", [])
        if not isinstance(include_all_groups, list):
            raise RadarError(f"Topic {topic_id}.include_all_groups must be a list")
        for group_index, group in enumerate(include_all_groups):
            if (
                not isinstance(group, list)
                or not group
                or any(not isinstance(value, str) or not value.strip() for value in group)
            ):
                raise RadarError(
                    f"Topic {topic_id}.include_all_groups[{group_index}] must contain non-empty strings"
                )
    for field in (
        "lookback_days",
        "max_candidates_per_topic",
        "max_review_candidates",
        "max_digest_papers",
        "max_per_topic",
    ):
        if not isinstance(profile[field], int) or isinstance(profile[field], bool) or profile[field] <= 0:
            raise RadarError(f"{field} must be a positive integer")
    for field in ("relevance_threshold", "quality_threshold", "watch_threshold"):
        if (
            not isinstance(profile[field], (int, float))
            or isinstance(profile[field], bool)
            or not 0 <= profile[field] <= 100
        ):
            raise RadarError(f"{field} must be between 0 and 100")
    policy = profile["quality_policy"]
    if not isinstance(policy, dict):
        raise RadarError("quality_policy must be an object")
    expected_intrinsic = {"problem_importance", "method_novelty", "evidence_strength", "reproducibility"}
    expected_overall = {"relevance", "intrinsic_quality", "external_signal"}
    _validate_weights(policy.get("intrinsic_weights"), expected_intrinsic, "intrinsic_weights")
    _validate_weights(policy.get("overall_weights"), expected_overall, "overall_weights")
    if profile["profile_version"] == 2:
        _validate_v2_profile(profile, ids)


def _validate_v2_profile(profile: dict[str, Any], topic_ids: set[str]) -> None:
    lanes = profile.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise RadarError("profile_version 2 requires a non-empty lanes list")
    lane_ids: set[str] = set()
    minimum_total = 0
    for index, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            raise RadarError(f"Lane {index} must be an object")
        needed = {"id", "label", "artifact_types", "min_digest_items", "max_digest_items"}
        missing = sorted(needed - set(lane))
        if missing:
            raise RadarError(f"Lane {index} is missing fields: {', '.join(missing)}")
        lane_id = lane["id"]
        if not isinstance(lane_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", lane_id):
            raise RadarError(f"Invalid lane id: {lane_id!r}")
        if lane_id in lane_ids:
            raise RadarError(f"Duplicate lane id: {lane_id}")
        lane_ids.add(lane_id)
        if not isinstance(lane["label"], str) or not lane["label"].strip():
            raise RadarError(f"Lane {lane_id}.label must be a non-empty string")
        artifact_types = lane["artifact_types"]
        if (
            not isinstance(artifact_types, list)
            or not artifact_types
            or any(value not in {"paper", "model-release"} for value in artifact_types)
        ):
            raise RadarError(f"Lane {lane_id}.artifact_types is invalid")
        minimum = lane["min_digest_items"]
        maximum = lane["max_digest_items"]
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or minimum < 0
            or not isinstance(maximum, int)
            or isinstance(maximum, bool)
            or maximum <= 0
            or minimum > maximum
        ):
            raise RadarError(f"Lane {lane_id} must satisfy 0 <= min_digest_items <= max_digest_items")
        if "lookback_days" in lane and (
            not isinstance(lane["lookback_days"], int)
            or isinstance(lane["lookback_days"], bool)
            or lane["lookback_days"] <= 0
        ):
            raise RadarError(f"Lane {lane_id}.lookback_days must be a positive integer")
        minimum_total += minimum
    required_lanes = {"recent-paper", "classic-foundation", "open-model"}
    if not required_lanes.issubset(lane_ids):
        raise RadarError("profile_version 2 must define recent-paper, classic-foundation, and open-model lanes")
    if minimum_total > int(profile["max_digest_papers"]):
        raise RadarError("Lane minimums exceed max_digest_papers")
    topic_quotas = profile.get("topic_quotas")
    if not isinstance(topic_quotas, dict):
        raise RadarError("profile_version 2 requires a topic_quotas object")
    for topic_id, quota in topic_quotas.items():
        if topic_id not in topic_ids or not isinstance(quota, dict):
            raise RadarError(f"Invalid topic quota: {topic_id}")
        minimum = quota.get("min_if_eligible")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum <= 0:
            raise RadarError(f"Topic quota {topic_id}.min_if_eligible must be a positive integer")
        artifact_types = quota.get("artifact_types")
        if artifact_types is not None and (
            not isinstance(artifact_types, list)
            or not artifact_types
            or any(value not in {"paper", "model-release"} for value in artifact_types)
        ):
            raise RadarError(f"Topic quota {topic_id}.artifact_types is invalid")
        quota_lanes = quota.get("lanes")
        if quota_lanes is not None and (
            not isinstance(quota_lanes, list)
            or not quota_lanes
            or any(value not in lane_ids for value in quota_lanes)
        ):
            raise RadarError(f"Topic quota {topic_id}.lanes is invalid")
        require_primary = quota.get("require_primary_topic", False)
        if not isinstance(require_primary, bool):
            raise RadarError(f"Topic quota {topic_id}.require_primary_topic must be a boolean")
    source_config = profile.get("source_config")
    if not isinstance(source_config, dict):
        raise RadarError("profile_version 2 requires a source_config object")
    hf_models = source_config.get("hf_models")
    if not isinstance(hf_models, dict):
        raise RadarError("source_config.hf_models must be an object")
    for field in ("limit", "lookback_days"):
        value = hf_models.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RadarError(f"source_config.hf_models.{field} must be a positive integer")
    for field in ("require_weights", "require_explicit_license", "require_open_source_license", "allow_restrictive_open_weights"):
        if field in hf_models and not isinstance(hf_models[field], bool):
            raise RadarError(f"source_config.hf_models.{field} must be a boolean")
    fallback_topic = hf_models.get("fallback_topic")
    if not isinstance(fallback_topic, str) or fallback_topic not in topic_ids:
        raise RadarError("source_config.hf_models.fallback_topic must name a configured topic")
    include_any = hf_models.get("include_any")
    if (
        not isinstance(include_any, list)
        or not include_any
        or any(not isinstance(value, str) or not value.strip() for value in include_any)
    ):
        raise RadarError("source_config.hf_models.include_any must contain non-empty strings")
    exclude_any = hf_models.get("exclude_any", [])
    if (
        not isinstance(exclude_any, list)
        or any(not isinstance(value, str) or not value.strip() for value in exclude_any)
    ):
        raise RadarError("source_config.hf_models.exclude_any must contain only non-empty strings")


def _validate_weights(weights: Any, expected: set[str], name: str) -> None:
    if not isinstance(weights, dict) or set(weights) != expected:
        raise RadarError(f"{name} must contain exactly: {', '.join(sorted(expected))}")
    if any(
        not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0
        for value in weights.values()
    ):
        raise RadarError(f"{name} values must be non-negative numbers")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-6):
        raise RadarError(f"{name} values must sum to 1.0")


def ensure_workspace(workspace: Path, profile_path: Path | None = None, force: bool = False) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    destination = workspace / "profile.json"
    source = profile_path or DEFAULT_PROFILE
    if force or not destination.exists():
        profile = load_json(source)
        validate_profile(profile)
        write_json(destination, profile)
    else:
        profile = load_json(destination)
        validate_profile(profile)
    state_path = workspace / "state.json"
    if not state_path.exists():
        write_json(state_path, {"schema_version": 1, "seen": {}, "updated_at": utc_now()})
    else:
        load_state(state_path)
    return profile


def canonical_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    match = ARXIV_ID_RE.search(value.replace(".pdf", ""))
    if not match:
        return None
    return re.sub(r"v\d+$", "", match.group("id"), flags=re.IGNORECASE)


def normalized_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().lower()
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE)


def canonical_record_id(record: dict[str, Any]) -> str:
    artifact_type = clean_text(record.get("artifact_type") or "paper").lower()
    if artifact_type == "model-release":
        model_id = clean_text(record.get("model_id") or record.get("id"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", model_id):
            raise RadarError("Cannot create a model-release canonical ID without a namespaced model_id")
        return f"hf-model:{model_id.lower()}"
    arxiv_id = canonical_arxiv_id(
        str(record.get("arxiv_id") or record.get("id") or record.get("abs_url") or record.get("pdf_url") or "")
    )
    if arxiv_id:
        return f"arxiv:{arxiv_id.lower()}"
    title = normalized_title(str(record.get("title") or ""))
    if not title:
        raise RadarError("Cannot create a canonical ID for a record without arXiv ID or title")
    return f"title:{hashlib.sha256(title.encode('utf-8')).hexdigest()[:20]}"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def safe_http_url(value: Any) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    parsed = urllib.parse.urlparse(cleaned)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return cleaned


def clean_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    authors: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("user") or item.get("fullname")
        else:
            name = item
        cleaned = clean_text(name)
        if cleaned and cleaned not in authors:
            authors.append(cleaned)
    return authors


def normalized_match_text(value: Any) -> str:
    lowered = clean_text(value).lower()
    lowered = re.sub(r"[-_/]+", " ", lowered)
    return re.sub(r"[^\w]+", " ", lowered, flags=re.UNICODE).strip()


def match_topic(record: dict[str, Any], topic: dict[str, Any]) -> tuple[bool, list[str]]:
    searchable_parts: list[Any] = [
        record.get("title", ""),
        record.get("abstract", ""),
        record.get("model_id", ""),
        record.get("organization", ""),
        record.get("curation_summary", ""),
    ]
    tags = record.get("tags")
    if isinstance(tags, list):
        searchable_parts.extend(tags)
    haystack = normalized_match_text(" ".join(str(value or "") for value in searchable_parts))
    exclusions = [
        term for term in topic.get("exclude_any", []) if normalized_match_text(term) in haystack
    ]
    if exclusions:
        return False, [f"excluded:{term}" for term in exclusions]
    phrases = list(topic.get("include_any", [])) + list(topic.get("query_terms", []))
    matched = []
    for phrase in phrases:
        lowered = normalized_match_text(phrase)
        if lowered and lowered in haystack and lowered not in matched:
            matched.append(lowered)
    groups = topic.get("include_all_groups", [])
    group_matches: list[str] = []
    if groups:
        for group in groups:
            hit = next((normalized_match_text(term) for term in group if normalized_match_text(term) in haystack), None)
            if not hit:
                group_matches = []
                break
            group_matches.append(hit)
    for term in group_matches:
        if term not in matched:
            matched.append(term)
    return bool(matched or group_matches), matched


def matches_topic_quota_scope(record: dict[str, Any], topic_id: str, quota: dict[str, Any]) -> bool:
    """Return whether an artifact is in the configured topic-quota population.

    Primary-topic enforcement is intentionally left to the reviewed-item selector,
    because raw discovery candidates do not yet have a reviewer-assigned primary topic.
    """
    if topic_id not in record.get("topics", []):
        return False
    artifact_types = quota.get("artifact_types")
    if artifact_types and record.get("artifact_type", "paper") not in artifact_types:
        return False
    lanes = quota.get("lanes")
    if lanes and record.get("lane", "recent-paper") not in lanes:
        return False
    return True


def safe_nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def safe_nonnegative_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return max(0.0, parsed) if math.isfinite(parsed) else 0.0


def merge_candidate(target: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    for field in (
        "title",
        "abstract",
        "published",
        "updated",
        "abs_url",
        "pdf_url",
        "project_url",
        "code_url",
        "artifact_type",
        "lane",
        "entity_id",
        "event_id",
        "model_id",
        "organization",
        "released_at",
        "version_sha",
        "model_card_url",
        "weights_url",
        "license_id",
        "license_url",
        "openness_class",
        "pipeline_tag",
    ):
        current = target.get(field)
        proposed = incoming.get(field)
        if not current or (field in {"title", "abstract"} and len(str(proposed or "")) > len(str(current))):
            if proposed:
                target[field] = proposed
    target["authors"] = list(dict.fromkeys(list(target.get("authors", [])) + list(incoming.get("authors", []))))
    target["categories"] = sorted(set(target.get("categories", [])) | set(incoming.get("categories", [])))
    target["topics"] = sorted(set(target.get("topics", [])) | set(incoming.get("topics", [])))
    target["sources"] = sorted(set(target.get("sources", [])) | set(incoming.get("sources", [])))
    target_tags = target.get("tags") if isinstance(target.get("tags"), list) else []
    incoming_tags = incoming.get("tags") if isinstance(incoming.get("tags"), list) else []
    target["tags"] = sorted(set(target_tags) | set(incoming_tags))
    target.setdefault("topic_match_terms", {})
    for topic_id, terms in incoming.get("topic_match_terms", {}).items():
        target["topic_match_terms"][topic_id] = sorted(
            set(target["topic_match_terms"].get(topic_id, [])) | set(terms)
        )
    external = target.setdefault("external", {})
    incoming_external = incoming.get("external", {})
    for field in ("hf_upvotes", "hf_model_likes", "hf_model_downloads"):
        external[field] = max(safe_nonnegative_int(external.get(field)), safe_nonnegative_int(incoming_external.get(field)))
    external["hf_featured"] = bool(external.get("hf_featured") or incoming_external.get("hf_featured"))
    external["hf_trending_score"] = max(
        safe_nonnegative_float(external.get("hf_trending_score")),
        safe_nonnegative_float(incoming_external.get("hf_trending_score")),
    )
    return target


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> bytes:
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml, text/xml, */*"}
    if headers:
        request_headers.update(headers)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt + 1 >= retries:
                break
            retry_after = exc.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(min(delay, 10))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 >= retries:
                break
            time.sleep(2**attempt)
    raise RadarError(f"Request failed for {url}: {last_error}")


def request_json(url: str, **kwargs: Any) -> Any:
    raw = request_bytes(url, **kwargs)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RadarError(f"Source returned invalid JSON: {url}") from exc


def weighted_score(values: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(float(values[key]) * float(weight) for key, weight in weights.items()), 1)


def validate_score(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
        raise RadarError(f"{field} must be a number between 0 and 100")
    return float(value)


def derive_external_signal(candidate: dict[str, Any]) -> float:
    external = candidate.get("external", {})
    if candidate.get("artifact_type") == "model-release":
        likes = safe_nonnegative_int(external.get("hf_model_likes"))
        downloads = safe_nonnegative_int(external.get("hf_model_downloads"))
        trending = safe_nonnegative_float(external.get("hf_trending_score"))
        score = min(40.0, trending * 8.0)
        score += min(25.0, math.log2(likes + 1) * 3.0)
        score += min(20.0, math.log10(downloads + 1) * 4.0)
        if candidate.get("weights_url") and candidate.get("license_id"):
            score += 15.0
        return round(min(100.0, score), 1)
    upvotes = safe_nonnegative_int(external.get("hf_upvotes"))
    score = min(55.0, math.log2(upvotes + 1) * 9.0)
    if external.get("hf_featured"):
        score += 15
    if len(candidate.get("sources", [])) >= 2:
        score += 15
    if candidate.get("code_url") or candidate.get("project_url"):
        score += 15
    return round(min(100.0, score), 1)


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def unique_strings(items: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for item in items:
        cleaned = clean_text(item)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output
