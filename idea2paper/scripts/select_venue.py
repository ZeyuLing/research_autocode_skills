#!/usr/bin/env python3
"""Select the nearest verified, suitable, still-open top conference."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TIER_RANK = {"flagship": 0, "top": 1}
DEFAULT_POOL_DEFINITIONS = {
    "eccv": ("ECCV", "European Conference on Computer Vision", (), "flagship"),
    "iccv": ("ICCV", "IEEE/CVF International Conference on Computer Vision", (), "flagship"),
    "cvpr": ("CVPR", "IEEE/CVF Conference on Computer Vision and Pattern Recognition", (), "flagship"),
    "neurips": ("NeurIPS", "Conference on Neural Information Processing Systems", ("NIPS",), "flagship"),
    "icml": ("ICML", "International Conference on Machine Learning", (), "flagship"),
    "iclr": ("ICLR", "International Conference on Learning Representations", (), "flagship"),
    "aaai": ("AAAI", "AAAI Conference on Artificial Intelligence", (), "flagship"),
    "ijcai": ("IJCAI", "International Joint Conference on Artificial Intelligence", (), "flagship"),
    "acmmm": ("ACM MM", "ACM International Conference on Multimedia", ("ACMMM", "ACM Multimedia"), "top"),
    "acl": ("ACL", "Annual Meeting of the Association for Computational Linguistics", (), "flagship"),
    "emnlp": ("EMNLP", "Conference on Empirical Methods in Natural Language Processing", (), "flagship"),
}
DEFAULT_POOL_IDS = frozenset(DEFAULT_POOL_DEFINITIONS)
SELECTION_RULE = (
    "strict default pool, scope_fit>=threshold, nearest open abstract/full-paper deadline, "
    "fit desc, tier desc"
)


def parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError(f"Deadline must include a timezone: {value}")
    return parsed


def load_candidates(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return payload["candidates"]
    raise ValueError("Candidate file must be a JSON list or an object with a candidates list")


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("strict_default_pool") is not True:
        raise ValueError("Venue registry must declare strict_default_pool=true")
    venues = payload.get("venues")
    if not isinstance(venues, list):
        raise ValueError("Venue registry must contain a venues list")
    venue_ids = [str(item.get("id", "")).strip().casefold() for item in venues if isinstance(item, dict)]
    if len(venue_ids) != len(venues) or len(venue_ids) != len(set(venue_ids)):
        raise ValueError("Venue registry contains a malformed or duplicate venue ID")
    if set(venue_ids) != DEFAULT_POOL_IDS:
        missing = sorted(DEFAULT_POOL_IDS - set(venue_ids))
        extra = sorted(set(venue_ids) - DEFAULT_POOL_IDS)
        raise ValueError(
            "Venue registry must contain exactly the strict default pool "
            f"(missing={missing}, extra={extra})"
        )
    registry: dict[str, dict[str, Any]] = {}
    for item in venues:
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError(f"Venue registry aliases must be a list for {item.get('id')}")
        if not item.get("name") or str(item.get("tier", "")).casefold() not in TIER_RANK:
            raise ValueError(f"Venue registry entry is malformed: {item.get('id')}")
        venue_id = str(item["id"]).strip().casefold()
        expected_name, expected_full_name, expected_aliases, expected_tier = DEFAULT_POOL_DEFINITIONS[venue_id]
        normalized_aliases = {" ".join(str(alias).strip().casefold().split()) for alias in aliases}
        expected_normalized_aliases = {
            " ".join(alias.strip().casefold().split()) for alias in expected_aliases
        }
        if (
            " ".join(str(item.get("name", "")).strip().casefold().split())
            != expected_name.casefold()
            or " ".join(str(item.get("full_name", "")).strip().casefold().split())
            != expected_full_name.casefold()
            or normalized_aliases != expected_normalized_aliases
            or str(item.get("tier", "")).strip().casefold() != expected_tier
        ):
            raise ValueError(f"Venue registry metadata differs from the immutable pool for {venue_id}")
        canonical_item = dict(item)
        canonical_item.update(
            {
                "id": venue_id,
                "name": expected_name,
                "full_name": expected_full_name,
                "aliases": list(expected_aliases),
                "tier": expected_tier,
            }
        )
        names = [venue_id, expected_name, expected_full_name, *expected_aliases]
        for name in names:
            key = " ".join(str(name or "").strip().casefold().split())
            if not key:
                continue
            previous = registry.get(key)
            if previous is not None and previous.get("id") != venue_id:
                raise ValueError(f"Duplicate venue registry alias: {name}")
            registry[key] = canonical_item
    return registry


def evaluate(
    candidate: dict[str, Any],
    registry: dict[str, dict[str, Any]],
    as_of: datetime,
    min_fit: float,
    allow_tentative: bool,
    max_check_age_hours: float,
) -> tuple[bool, str, datetime | None, dict[str, Any]]:
    item = dict(candidate)
    name = str(item.get("name", "")).strip()
    if not name or not item.get("edition") or not item.get("track"):
        return False, "name, edition, and track are required", None, item
    if " ".join(str(item.get("track", "")).strip().casefold().split()) != "main":
        return False, "automatic selection only allows the main track", None, item
    registry_key = " ".join(name.casefold().split())
    registry_item = registry.get(registry_key)
    if registry_item is None:
        return False, "not in the strict default top-conference pool", None, item
    item["submitted_name"] = name
    item["name"] = registry_item["name"]
    item["registry_id"] = registry_item["id"]
    item["tier"] = registry_item["tier"]

    tier = str(item.get("tier", "")).lower()
    if tier not in TIER_RANK:
        return False, "tier is not flagship/top", None, item
    try:
        scope_fit = float(item.get("scope_fit", 0))
    except (TypeError, ValueError):
        scope_fit = 0
    if scope_fit < min_fit:
        return False, f"scope_fit {scope_fit:g} is below {min_fit:g}", None, item
    required_fit_fields = ("idea_version", "fit_reason", "scope_evidence_url")
    missing_fit_fields = [field for field in required_fit_fields if not item.get(field)]
    if missing_fit_fields:
        return False, f"missing fit evidence fields: {', '.join(missing_fit_fields)}", None, item
    if not isinstance(item.get("idea_tags"), list) or not item["idea_tags"]:
        return False, "idea_tags must be a non-empty list", None, item
    if not item.get("official_url") or not item.get("deadline_source_url") or not item.get("checked_at"):
        return False, "missing official_url, deadline_source_url, or checked_at", None, item
    try:
        checked_at = parse_datetime(str(item["checked_at"]))
    except ValueError as exc:
        return False, f"invalid checked_at: {exc}", None, item
    check_age = as_of.astimezone(timezone.utc) - checked_at.astimezone(timezone.utc)
    if check_age.total_seconds() < -300:
        return False, "checked_at is after the evaluation time", None, item
    if check_age.total_seconds() > max_check_age_hours * 3600:
        return False, f"official-source check is older than {max_check_age_hours:g} hours", None, item

    if "deadline_status" not in item:
        return False, "deadline_status is required", None, item
    status = str(item["deadline_status"]).lower()
    if status not in {"confirmed", "tentative"}:
        return False, "deadline_status must be confirmed or tentative", None, item
    if status != "confirmed" and not allow_tentative:
        return False, "deadline is not confirmed", None, item

    has_separate_abstract = item.get("has_separate_abstract_deadline")
    if not isinstance(has_separate_abstract, bool):
        return False, "has_separate_abstract_deadline must be an explicit boolean", None, item
    if has_separate_abstract is True and not item.get("abstract_deadline"):
        return False, "separate abstract deadline is declared but missing", None, item
    if has_separate_abstract is False and item.get("abstract_deadline"):
        return False, "abstract_deadline must be empty when no separate abstract deadline exists", None, item
    if not item.get("paper_deadline"):
        return False, "paper_deadline is required", None, item
    try:
        paper_deadline = parse_datetime(str(item["paper_deadline"]))
    except ValueError as exc:
        return False, str(exc), None, item
    if has_separate_abstract is True:
        deadline_key = "abstract_deadline"
    elif has_separate_abstract is False:
        deadline_key = "paper_deadline"
    else:
        deadline_key = "abstract_deadline" if item.get("abstract_deadline") else "paper_deadline"
    deadline_value = item.get(deadline_key)
    if not deadline_value:
        return False, "missing effective deadline", None, item
    try:
        deadline = parse_datetime(str(deadline_value))
    except ValueError as exc:
        return False, str(exc), None, item
    if has_separate_abstract is True and paper_deadline <= deadline:
        return False, "paper deadline must be later than the separate abstract deadline", None, item
    if deadline.astimezone(timezone.utc) <= as_of.astimezone(timezone.utc):
        label = "abstract" if deadline_key == "abstract_deadline" else "paper"
        return False, f"{label} deadline has passed", deadline, item

    item["effective_deadline"] = deadline.isoformat()
    item["effective_deadline_kind"] = deadline_key
    item["scope_fit"] = scope_fit
    return True, "eligible", deadline, item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--output", "-o", type=Path, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--as-of", help="Timezone-aware ISO timestamp for deterministic evaluation")
    parser.add_argument("--min-fit", type=float, default=4.0)
    parser.add_argument("--allow-tentative", action="store_true")
    parser.add_argument(
        "--max-check-age-hours",
        type=float,
        default=24.0,
        help="Maximum age of the official-source verification at selection time",
    )
    args = parser.parse_args()

    script_root = Path(__file__).resolve().parents[1]
    registry_path = args.registry or script_root / "references/venue-registry.json"
    registry = load_registry(registry_path)
    as_of = parse_datetime(args.as_of) if args.as_of else datetime.now(timezone.utc)

    eligible: list[tuple[datetime, dict[str, Any]]] = []
    excluded: list[dict[str, Any]] = []
    for candidate in load_candidates(args.candidates):
        ok, reason, deadline, normalized = evaluate(
            candidate,
            registry,
            as_of,
            args.min_fit,
            args.allow_tentative,
            args.max_check_age_hours,
        )
        if ok and deadline is not None:
            eligible.append((deadline, normalized))
        else:
            excluded.append({"name": normalized.get("name", "unknown"), "reason": reason})

    if args.allow_tentative and any(
        str(item.get("deadline_status", "")).lower() == "confirmed" for _, item in eligible
    ):
        eligible = [
            pair for pair in eligible if str(pair[1].get("deadline_status", "")).lower() == "confirmed"
        ]

    eligible.sort(
        key=lambda pair: (
            pair[0].astimezone(timezone.utc),
            -float(pair[1].get("scope_fit", 0)),
            TIER_RANK.get(str(pair[1].get("tier", "")).lower(), 99),
            str(pair[1].get("name", "")).lower(),
        )
    )
    if not eligible:
        payload = {
            "schema_version": 1,
            "status": "no_eligible_venue",
            "selection_mode": "auto",
            "as_of": as_of.isoformat(),
            "selected": None,
            "eligible": [],
            "excluded": excluded,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    selected = eligible[0][1]
    payload = {
        "schema_version": 1,
        "status": "selected" if selected.get("deadline_status", "confirmed") == "confirmed" else "tentative",
        "selection_mode": "auto",
        "as_of": as_of.isoformat(),
        "selection_rule": SELECTION_RULE,
        "selected": selected,
        "eligible": [item for _, item in eligible],
        "excluded": excluded,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"selected": selected.get("name"), "effective_deadline": selected.get("effective_deadline")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
