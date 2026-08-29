#!/usr/bin/env python3
"""Validate reviews, rank papers, enforce diversity, and render Markdown/HTML."""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from radar_common import (
    RadarError,
    derive_external_signal,
    load_json,
    matches_topic_quota_scope,
    load_state,
    profile_digest,
    safe_http_url,
    sha256_text,
    truncate,
    unique_strings,
    utc_now,
    validate_score,
    weighted_score,
    write_json,
    write_text,
)


SCORE_FIELDS = (
    "scope_match",
    "user_fit",
    "problem_importance",
    "method_novelty",
    "evidence_strength",
    "reproducibility",
)


def _required_deep_read_content(review: dict[str, Any]) -> list[str]:
    missing = []
    if not str(review.get("scientific_problem") or "").strip():
        missing.append("scientific_problem")
    for field in ("previous_work_gap", "modules", "experimental_evidence", "limitations"):
        value = review.get(field)
        if not isinstance(value, list) or not value or (field != "modules" and not unique_strings(value)):
            missing.append(field)
    if not str(review.get("why_read") or "").strip():
        missing.append("why_read")
    modules = review.get("modules") if isinstance(review.get("modules"), list) else []
    required_module_fields = ("name", "what", "problem_addressed", "why_it_works", "evidence_anchors")
    for index, module in enumerate(modules):
        if not isinstance(module, dict):
            missing.append(f"modules[{index}]")
            continue
        for field in required_module_fields:
            value = module.get(field)
            if field == "evidence_anchors":
                if not isinstance(value, list) or not unique_strings(value):
                    missing.append(f"modules[{index}].{field}")
            elif not str(value or "").strip():
                missing.append(f"modules[{index}].{field}")
    return missing


def evaluate_review(
    review: dict[str, Any], candidate: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    canonical_id = candidate["canonical_id"]
    artifact_type = candidate.get("artifact_type", "paper")
    lane = candidate.get("lane", "recent-paper")
    values: dict[str, float] = {}
    errors: list[str] = []
    for field in SCORE_FIELDS:
        try:
            values[field] = validate_score(review.get(field), f"{canonical_id}.{field}")
        except RadarError as exc:
            errors.append(str(exc))
    external_value = review.get("external_signal")
    if external_value is None:
        external = derive_external_signal(candidate)
    else:
        try:
            external = validate_score(external_value, f"{canonical_id}.external_signal")
        except RadarError as exc:
            errors.append(str(exc))
            external = derive_external_signal(candidate)
    topic_ids = {topic["id"] for topic in profile["topics"]}
    primary_topic = review.get("primary_topic")
    if primary_topic not in topic_ids:
        errors.append(f"{canonical_id}.primary_topic is not in the profile")
    candidate_topics = set(candidate.get("topics", []))
    if primary_topic in topic_ids and primary_topic not in candidate_topics:
        errors.append(f"{canonical_id}.primary_topic is not matched by the candidate")
    matched_topics = review.get("matched_topics")
    if (
        not isinstance(matched_topics, list)
        or primary_topic not in matched_topics
        or not set(matched_topics).issubset(candidate_topics)
    ):
        errors.append(f"{canonical_id}.matched_topics must be a candidate-topic subset containing primary_topic")
    evidence_level = review.get("evidence_level")
    if evidence_level not in {"full-text", "partial-text", "abstract", "official-artifacts"}:
        errors.append(f"{canonical_id}.evidence_level is invalid")
    confidence = review.get("confidence")
    if confidence not in {"high", "medium", "low"}:
        errors.append(f"{canonical_id}.confidence is invalid")

    if errors:
        return {
            "canonical_id": canonical_id,
            "candidate": candidate,
            "review": review,
            "decision": "reject",
            "decision_reasons": ["incomplete_or_invalid_review"] + errors,
            "primary_topic": primary_topic if primary_topic in topic_ids else (candidate.get("topics") or [""])[0],
            "artifact_type": artifact_type,
            "lane": lane,
            "scores": None,
        }

    relevance = round(values["scope_match"] * 0.6 + values["user_fit"] * 0.4, 1)
    intrinsic = weighted_score(
        {field: values[field] for field in ("problem_importance", "method_novelty", "evidence_strength", "reproducibility")},
        profile["quality_policy"]["intrinsic_weights"],
    )
    overall = weighted_score(
        {"relevance": relevance, "intrinsic_quality": intrinsic, "external_signal": external},
        profile["quality_policy"]["overall_weights"],
    )
    scores = {
        "relevance": relevance,
        "intrinsic_quality": intrinsic,
        "external_signal": round(external, 1),
        "overall": overall,
        **{field: round(value, 1) for field, value in values.items()},
    }
    fatal = unique_strings(review.get("fatal_concerns", [])) if isinstance(review.get("fatal_concerns"), list) else ["fatal_concerns must be a list"]
    missing_content = _required_deep_read_content(review)
    highlight_reasons = []
    if relevance < float(profile["relevance_threshold"]):
        highlight_reasons.append("below_relevance_threshold")
    if intrinsic < float(profile["quality_threshold"]):
        highlight_reasons.append("below_quality_threshold")
    required_evidence = "official-artifacts" if artifact_type == "model-release" else "full-text"
    if evidence_level != required_evidence:
        highlight_reasons.append(f"requires_{required_evidence}")
    if artifact_type == "model-release":
        if candidate.get("openness_class") not in {"open-source", "open-weights"}:
            highlight_reasons.append("unverified_openness")
        if not candidate.get("license_id"):
            highlight_reasons.append("missing_model_license")
        if not candidate.get("weights_url") or not candidate.get("weight_files"):
            highlight_reasons.append("missing_downloadable_weights")
    if confidence == "low":
        highlight_reasons.append("low_confidence")
    if fatal:
        highlight_reasons.append("fatal_concern")
    if missing_content:
        highlight_reasons.append("missing_deep_read_fields:" + ",".join(missing_content))

    if not highlight_reasons:
        decision = "eligible-highlight"
        reasons = ["passed_relevance_quality_and_evidence_gates"]
    elif (
        evidence_level in {"abstract", "partial-text"}
        and relevance >= float(profile["watch_threshold"])
        and intrinsic >= max(0.0, float(profile["quality_threshold"]) - 10.0)
        and not fatal
    ):
        decision = "eligible-watchlist"
        reasons = highlight_reasons
    else:
        decision = "reject"
        reasons = highlight_reasons or ["below_watch_threshold"]
    return {
        "canonical_id": canonical_id,
        "candidate": candidate,
        "review": review,
        "decision": decision,
        "decision_reasons": reasons,
        "primary_topic": primary_topic,
        "artifact_type": artifact_type,
        "lane": lane,
        "scores": scores,
    }


def _diverse_select(
    eligible: list[dict[str, Any]],
    topic_ids: list[str],
    total_limit: int,
    per_topic_limit: int,
    initial_counts: Counter[str] | None = None,
    lane_limits: dict[str, int] | None = None,
    initial_lane_counts: Counter[str] | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for topic_id in topic_ids:
        bucket = [item for item in eligible if item["primary_topic"] == topic_id]
        buckets[topic_id] = sorted(bucket, key=lambda item: item["scores"]["overall"], reverse=True)
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter(initial_counts or {})
    lane_counts: Counter[str] = Counter(initial_lane_counts or {})
    while len(selected) < total_limit:
        progressed = False
        for topic_id in topic_ids:
            if counts[topic_id] >= per_topic_limit or not buckets[topic_id]:
                continue
            candidate_index = next(
                (
                    index
                    for index, item in enumerate(buckets[topic_id])
                    if lane_limits is None
                    or lane_counts[item.get("lane", "recent-paper")]
                    < lane_limits.get(item.get("lane", "recent-paper"), total_limit)
                ),
                None,
            )
            if candidate_index is None:
                continue
            candidate = buckets[topic_id].pop(candidate_index)
            selected.append(candidate)
            counts[topic_id] += 1
            lane_counts[candidate.get("lane", "recent-paper")] += 1
            progressed = True
            if len(selected) >= total_limit:
                break
        if not progressed:
            break
    return selected


def _quota_select_highlights(
    eligible: list[dict[str, Any]], profile: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    topic_ids = [topic["id"] for topic in profile["topics"]]
    total_limit = int(profile["max_digest_papers"])
    per_topic_limit = int(profile["max_per_topic"])
    if profile.get("profile_version") != 2:
        return (
            _diverse_select(eligible, topic_ids, total_limit, per_topic_limit),
            {"profile_version": 1, "lanes": {}, "topics": {}},
        )

    ranked = sorted(eligible, key=lambda item: item["scores"]["overall"], reverse=True)
    lane_config = {lane["id"]: lane for lane in profile.get("lanes", [])}
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    lane_counts: Counter[str] = Counter()
    topic_counts: Counter[str] = Counter()

    def can_take(item: dict[str, Any], *, enforce_topic_cap: bool = True) -> bool:
        if len(selected) >= total_limit or item["canonical_id"] in selected_ids:
            return False
        lane_id = item.get("lane", "recent-paper")
        lane = lane_config.get(lane_id)
        if lane and lane_counts[lane_id] >= int(lane["max_digest_items"]):
            return False
        if enforce_topic_cap and topic_counts[item["primary_topic"]] >= per_topic_limit:
            return False
        return True

    def take(item: dict[str, Any]) -> None:
        selected.append(item)
        selected_ids.add(item["canonical_id"])
        lane_counts[item.get("lane", "recent-paper")] += 1
        topic_counts[item["primary_topic"]] += 1

    def fill(predicate: Any, target_count: int, current_count: Any) -> None:
        for item in ranked:
            if len(selected) >= total_limit or current_count() >= target_count:
                return
            if predicate(item) and can_take(item, enforce_topic_cap=True):
                take(item)

    def topic_quota_match(item: dict[str, Any], topic_id: str, quota: dict[str, Any]) -> bool:
        if not matches_topic_quota_scope(item["candidate"], topic_id, quota):
            return False
        return not quota.get("require_primary_topic", False) or item["primary_topic"] == topic_id

    for topic_id, quota in profile.get("topic_quotas", {}).items():
        minimum = int(quota["min_if_eligible"])
        fill(
            lambda item, topic_id=topic_id, quota=quota: topic_quota_match(item, topic_id, quota),
            minimum,
            lambda topic_id=topic_id: sum(
                1
                for item in selected
                if topic_quota_match(item, topic_id, profile["topic_quotas"][topic_id])
            ),
        )

    for lane_id, lane in lane_config.items():
        minimum = int(lane["min_digest_items"])
        fill(
            lambda item, lane_id=lane_id: item.get("lane", "recent-paper") == lane_id,
            minimum,
            lambda lane_id=lane_id: lane_counts[lane_id],
        )

    while len(selected) < total_limit:
        progressed = False
        for topic_id in topic_ids:
            candidate = next(
                (
                    item
                    for item in ranked
                    if item["primary_topic"] == topic_id and can_take(item, enforce_topic_cap=True)
                ),
                None,
            )
            if candidate is None:
                continue
            take(candidate)
            progressed = True
            if len(selected) >= total_limit:
                break
        if not progressed:
            break

    quota_report = {
        "profile_version": 2,
        "lanes": {
            lane_id: {
                "eligible": sum(1 for item in eligible if item.get("lane", "recent-paper") == lane_id),
                "selected": lane_counts[lane_id],
                "minimum": int(lane["min_digest_items"]),
                "maximum": int(lane["max_digest_items"]),
                "minimum_met": lane_counts[lane_id] >= int(lane["min_digest_items"]),
            }
            for lane_id, lane in lane_config.items()
        },
        "topics": {
            topic_id: {
                "eligible": sum(
                    1 for item in eligible if topic_quota_match(item, topic_id, quota)
                ),
                "selected": sum(
                    1 for item in selected if topic_quota_match(item, topic_id, quota)
                ),
                "minimum_if_eligible": int(quota["min_if_eligible"]),
                "minimum_met": (
                    not any(topic_quota_match(item, topic_id, quota) for item in eligible)
                    or sum(1 for item in selected if topic_quota_match(item, topic_id, quota))
                    >= int(quota["min_if_eligible"])
                ),
            }
            for topic_id, quota in profile.get("topic_quotas", {}).items()
        },
    }
    return selected, quota_report


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _authors(candidate: dict[str, Any], unknown: str = "Unknown") -> str:
    authors = candidate.get("authors", [])
    if not authors:
        return unknown
    rendered = ", ".join(authors[:6])
    return rendered + (", et al." if len(authors) > 6 else "")


TEXT = {
    "zh-CN": {
        "title_suffix": "高质量研究雷达",
        "generated": "生成时间",
        "window": "检索窗口",
        "past_days": "过去 {days} 天",
        "pool": "候选池：{candidates} 篇；已完成结构化评审：{reviewed} 篇；未评审：{unreviewed} 篇",
        "selection": "重点推荐：{highlights} 条；证据观察：{watchlist} 条",
        "coverage": "来源覆盖",
        "score_note": "评分说明：总分 = 45% 相关性 + 45% 内在质量 + 10% 外部信号；外部热度不是质量替代品。",
        "shortlist": "覆盖声明：本轮是经过对应证据核查的 shortlist，不是对候选池的穷尽式质量排序。",
        "today": "今日结论",
        "passed": "共有 {count} 条研究条目通过相关性、内在质量和对应证据门槛：{coverage}。",
        "none_passed": "本轮没有条目同时通过相关性、内在质量和对应证据门槛；不要为了凑数降低标准。",
        "paper_count": "{label} {count} 篇",
        "authors": "作者",
        "unknown": "未知",
        "date": "日期",
        "artifact": "类型 / 通道",
        "paper_artifact": "论文",
        "model_artifact": "开放模型发布",
        "model_meta": "模型：{model_id}；开放性：{openness}；许可：{license}；版本：{version}",
        "scores": "分数：总分 **{overall:.1f}**；相关性 {relevance:.1f}；内在质量 {quality:.1f}；外部信号 {external:.1f}",
        "evidence": "证据级别：`{level}`；置信度：`{confidence}`；来源：{sources}",
        "project": "项目页",
        "code": "代码 / 开放资产",
        "weights": "模型权重",
        "license_link": "许可原文",
        "problem": "科学问题",
        "prior": "为什么 previous work 不够",
        "modules": "模块 / 策略与其解决的问题",
        "module_headers": ["模块或策略", "是什么", "解决什么问题", "为什么有效", "证据锚点"],
        "experiments": "实验与质量证据",
        "limitations": "局限",
        "why_read": "为什么值得读",
        "missing": "未填写",
        "watch": "证据不足观察区（不等同于高质量认证）",
        "none": "无。",
        "watch_line": "总分 {overall:.1f}，证据 `{level}`，置信度 `{confidence}`。观察原因：{reasons}。",
        "gaps": "来源与缺口",
        "failure": "来源失败：`{source}` / `{scope}` — {error}",
        "failure_warning": "因存在来源失败，本轮不能声称覆盖了该时间窗内的全部论文。",
        "source_ok": "{source}: {count} 次成功查询",
        "source_failures": "失败 {count} 次",
        "source_truncated": "潜在截断 {count} 次",
        "truncation": "查询上限风险：`{source}` / `{scope}` 返回原始 {raw} 条，请求上限 {limit}，来源总量 {total}。",
        "truncation_warning": "存在可能在当前时间窗内被查询上限截断的来源；本轮不能声称穷尽覆盖。",
    },
    "en": {
        "title_suffix": "High-Quality Research Radar",
        "generated": "Generated",
        "window": "Screening window",
        "past_days": "past {days} days",
        "pool": "Candidate pool: {candidates}; structured reviews: {reviewed}; unreviewed: {unreviewed}",
        "selection": "Highlights: {highlights}; evidence watchlist: {watchlist}",
        "coverage": "Source coverage",
        "score_note": "Scoring: 45% relevance + 45% intrinsic quality + 10% external signal. Popularity is not a substitute for quality.",
        "shortlist": "Coverage note: this is an evidence-verified shortlist, not an exhaustive quality ranking of the candidate pool.",
        "today": "Summary",
        "passed": "{count} research items passed the relevance, intrinsic-quality, and applicable evidence gates: {coverage}.",
        "none_passed": "No item passed all applicable gates in this run; do not lower the standard to fill a quota.",
        "paper_count": "{label}: {count}",
        "authors": "Authors",
        "unknown": "Unknown",
        "date": "Date",
        "artifact": "Artifact / lane",
        "paper_artifact": "Paper",
        "model_artifact": "Open-model release",
        "model_meta": "Model: {model_id}; openness: {openness}; license: {license}; version: {version}",
        "scores": "Scores: overall **{overall:.1f}**; relevance {relevance:.1f}; intrinsic quality {quality:.1f}; external signal {external:.1f}",
        "evidence": "Evidence: `{level}`; confidence: `{confidence}`; sources: {sources}",
        "project": "Project",
        "code": "Code / open artifacts",
        "weights": "Model weights",
        "license_link": "License text",
        "problem": "Scientific problem",
        "prior": "Why previous work falls short",
        "modules": "Module / strategy to problem mapping",
        "module_headers": ["Module or strategy", "What it is", "Problem addressed", "Why it works", "Evidence anchors"],
        "experiments": "Experimental and quality evidence",
        "limitations": "Limitations",
        "why_read": "Why read it",
        "missing": "Not provided",
        "watch": "Insufficient-evidence watchlist (not a quality certification)",
        "none": "None.",
        "watch_line": "Overall {overall:.1f}; evidence `{level}`; confidence `{confidence}`. Reasons: {reasons}.",
        "gaps": "Source coverage and gaps",
        "failure": "Source failure: `{source}` / `{scope}` — {error}",
        "failure_warning": "Because at least one source failed, this run cannot claim exhaustive coverage of the window.",
        "source_ok": "{source}: {count} successful queries",
        "source_failures": "{count} failures",
        "source_truncated": "{count} potentially truncated queries",
        "truncation": "Query-cap risk: `{source}` / `{scope}` returned {raw} raw items at a limit of {limit}; source total: {total}.",
        "truncation_warning": "At least one source may be truncated within the screening window; this run is not exhaustive.",
    },
}


def _strings(profile: dict[str, Any]) -> dict[str, Any]:
    return TEXT[profile.get("language", "zh-CN")]


def _source_summary(source_log: dict[str, Any], strings: dict[str, Any]) -> str:
    queries = source_log.get("queries", [])
    successful = Counter(entry.get("source", "unknown") for entry in queries if entry.get("status") == "ok")
    failures = source_log.get("failures", [])
    truncated = [entry for entry in queries if entry.get("potentially_truncated_window")]
    parts = [strings["source_ok"].format(source=source, count=count) for source, count in sorted(successful.items())]
    parts.append(strings["source_failures"].format(count=len(failures)))
    parts.append(strings["source_truncated"].format(count=len(truncated)))
    return "; ".join(parts)


def render_markdown(
    profile: dict[str, Any],
    highlights: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    source_log: dict[str, Any],
    generated_at: str,
    candidate_count: int,
    reviewed_count: int,
) -> str:
    topic_labels = {topic["id"]: topic["label"] for topic in profile["topics"]}
    s = _strings(profile)
    days = source_log.get("window", {}).get("lookback_days", profile["lookback_days"])
    cutoff = source_log.get("window", {}).get("cutoff_utc", "unknown")
    lines = [
        f"# {profile['name']} — {s['title_suffix']}",
        "",
        f"- {s['generated']}: {generated_at}",
        f"- {s['window']}: {s['past_days'].format(days=days)} (cutoff: {cutoff})",
        "- " + s["pool"].format(candidates=candidate_count, reviewed=reviewed_count, unreviewed=max(0, candidate_count - reviewed_count)),
        "- " + s["selection"].format(highlights=len(highlights), watchlist=len(watchlist)),
        f"- {s['coverage']}: {_source_summary(source_log, s)}",
        f"- {s['score_note']}",
    ]
    if reviewed_count < candidate_count:
        lines.append(f"- {s['shortlist']}")
    lines.extend(["", f"## {s['today']}", ""])
    if highlights:
        counts = Counter(item["primary_topic"] for item in highlights)
        coverage = "; ".join(
            s["paper_count"].format(label=topic_labels.get(topic_id, topic_id), count=count)
            for topic_id, count in counts.items()
        )
        lines.append(s["passed"].format(count=len(highlights), coverage=coverage))
    else:
        lines.append(s["none_passed"])
    lines.append("")

    for topic in profile["topics"]:
        topic_items = [item for item in highlights if item["primary_topic"] == topic["id"]]
        if not topic_items:
            continue
        lines.extend([f"## {topic['label']}", ""])
        for item in topic_items:
            candidate, review, scores = item["candidate"], item["review"], item["scores"]
            url = safe_http_url(candidate.get("abs_url")) or safe_http_url(candidate.get("pdf_url")) or "#"
            lines.extend(
                [
                    f"### [{candidate.get('title', 'Untitled')}]({url})",
                    "",
                    f"- {s['authors']}: {_authors(candidate, s['unknown'])}",
                    f"- {s['date']}: {candidate.get('published') or 'unknown'}",
                    f"- {s['artifact']}: {s['model_artifact'] if candidate.get('artifact_type') == 'model-release' else s['paper_artifact']} / `{candidate.get('lane', 'recent-paper')}`",
                    "- " + s["scores"].format(overall=scores["overall"], relevance=scores["relevance"], quality=scores["intrinsic_quality"], external=scores["external_signal"]),
                    "- " + s["evidence"].format(level=review.get("evidence_level"), confidence=review.get("confidence"), sources=", ".join(candidate.get("sources", []))),
                ]
            )
            if candidate.get("artifact_type") == "model-release":
                lines.append(
                    "- "
                    + s["model_meta"].format(
                        model_id=candidate.get("model_id") or s["unknown"],
                        openness=candidate.get("openness_class") or s["unknown"],
                        license=candidate.get("license_id") or s["unknown"],
                        version=candidate.get("version_sha") or s["unknown"],
                    )
                )
            project_url = safe_http_url(review.get("project_url")) or safe_http_url(candidate.get("project_url"))
            code_url = safe_http_url(review.get("code_url")) or safe_http_url(candidate.get("code_url"))
            if project_url:
                lines.append(f"- {s['project']}: {project_url}")
            if code_url:
                lines.append(f"- {s['code']}: {code_url}")
            if candidate.get("artifact_type") == "model-release":
                weights_url = safe_http_url(candidate.get("weights_url"))
                license_url = safe_http_url(candidate.get("license_url"))
                if weights_url:
                    lines.append(f"- {s['weights']}: {weights_url}")
                if license_url:
                    lines.append(f"- {s['license_link']}: {license_url}")
            lines.extend(["", f"**{s['problem']}**", "", str(review.get("scientific_problem") or s["missing"]), "", f"**{s['prior']}**", ""])
            for gap in unique_strings(review.get("previous_work_gap", [])):
                lines.append(f"- {gap}")
            headers = " | ".join(s["module_headers"])
            lines.extend(["", f"**{s['modules']}**", "", f"| {headers} |", "|---|---|---|---|---|"])
            for module in review.get("modules", []):
                anchors = ", ".join(unique_strings(module.get("evidence_anchors", [])))
                lines.append(
                    "| "
                    + " | ".join(
                        _md_cell(module.get(field))
                        for field in ("name", "what", "problem_addressed", "why_it_works")
                    )
                    + f" | {_md_cell(anchors)} |"
                )
            lines.extend(["", f"**{s['experiments']}**", ""])
            for evidence in unique_strings(review.get("experimental_evidence", [])):
                lines.append(f"- {evidence}")
            lines.extend(["", f"**{s['limitations']}**", ""])
            for limitation in unique_strings(review.get("limitations", [])):
                lines.append(f"- {limitation}")
            lines.extend(["", f"**{s['why_read']}:** {review.get('why_read') or s['missing']}", ""])

    lines.extend([f"## {s['watch']}", ""])
    if not watchlist:
        lines.append(s["none"])
    for item in watchlist:
        candidate, review, scores = item["candidate"], item["review"], item["scores"]
        url = safe_http_url(candidate.get("abs_url")) or safe_http_url(candidate.get("pdf_url")) or "#"
        lines.extend(
            [
                f"- [{candidate.get('title', 'Untitled')}]({url}) — {topic_labels.get(item['primary_topic'], item['primary_topic'])}; "
                + s["watch_line"].format(overall=scores["overall"], level=review.get("evidence_level"), confidence=review.get("confidence"), reasons="; ".join(item["decision_reasons"])),
            ]
        )
    lines.extend(["", f"## {s['gaps']}", "", f"- {_source_summary(source_log, s)}"])
    for failure in source_log.get("failures", []):
        lines.append("- " + s["failure"].format(source=failure.get("source"), scope=failure.get("topic") or failure.get("date") or failure.get("lane") or "unknown", error=truncate(str(failure.get("error")), 400)))
    truncated_queries = [
        entry for entry in source_log.get("queries", []) if entry.get("potentially_truncated_window")
    ]
    for entry in truncated_queries:
        lines.append(
            "- "
            + s["truncation"].format(
                source=entry.get("source"),
                scope=entry.get("topic") or entry.get("date") or entry.get("lane") or "unknown",
                raw=entry.get("raw_returned", "unknown"),
                limit=entry.get("requested_limit", "unknown"),
                total=entry.get("total_results") if entry.get("total_results") is not None else "unknown",
            )
        )
    if source_log.get("failures"):
        lines.append(f"- {s['failure_warning']}")
    if truncated_queries:
        lines.append(f"- {s['truncation_warning']}")
    lines.append("")
    return "\n".join(lines)


def render_html(
    profile: dict[str, Any],
    highlights: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    source_log: dict[str, Any],
    generated_at: str,
    candidate_count: int,
    reviewed_count: int,
) -> str:
    topic_labels = {topic["id"]: topic["label"] for topic in profile["topics"]}
    s = _strings(profile)
    language = profile.get("language", "zh-CN")
    days = source_log.get("window", {}).get("lookback_days", profile["lookback_days"])
    cutoff = source_log.get("window", {}).get("cutoff_utc", "unknown")

    def bullets(values: Any) -> str:
        items = unique_strings(values) if isinstance(values, list) else []
        if not items:
            items = [s["none"]]
        return "<ul>" + "".join(f"<li>{html.escape(value)}</li>" for value in items) + "</ul>"

    sections = []
    for topic in profile["topics"]:
        cards = []
        for item in [entry for entry in highlights if entry["primary_topic"] == topic["id"]]:
            candidate, review, scores = item["candidate"], item["review"], item["scores"]
            modules = "".join(
                "<tr>"
                + "".join(
                    f"<td>{html.escape(str(module.get(field) or ''))}</td>"
                    for field in ("name", "what", "problem_addressed", "why_it_works")
                )
                + f"<td>{html.escape(', '.join(unique_strings(module.get('evidence_anchors', []))))}</td></tr>"
                for module in review.get("modules", [])
            )
            link = html.escape(
                safe_http_url(candidate.get("abs_url")) or safe_http_url(candidate.get("pdf_url")) or "#",
                quote=True,
            )
            project_url = safe_http_url(review.get("project_url")) or safe_http_url(candidate.get("project_url"))
            code_url = safe_http_url(review.get("code_url")) or safe_http_url(candidate.get("code_url"))
            resource_links = []
            if project_url:
                resource_links.append(
                    f'<a href="{html.escape(str(project_url), quote=True)}">{html.escape(s["project"])}</a>'
                )
            if code_url:
                resource_links.append(
                    f'<a href="{html.escape(str(code_url), quote=True)}">{html.escape(s["code"])}</a>'
                )
            if candidate.get("artifact_type") == "model-release":
                weights_url = safe_http_url(candidate.get("weights_url"))
                license_url = safe_http_url(candidate.get("license_url"))
                if weights_url:
                    resource_links.append(
                        f'<a href="{html.escape(str(weights_url), quote=True)}">{html.escape(s["weights"])}</a>'
                    )
                if license_url:
                    resource_links.append(
                        f'<a href="{html.escape(str(license_url), quote=True)}">{html.escape(s["license_link"])}</a>'
                    )
            resources = f'<p class="meta">{" · ".join(resource_links)}</p>' if resource_links else ""
            module_headers = "".join(f"<th>{html.escape(label)}</th>" for label in s["module_headers"])
            artifact_label = s["model_artifact"] if candidate.get("artifact_type") == "model-release" else s["paper_artifact"]
            artifact_meta = (
                "<br>"
                + html.escape(
                    s["model_meta"].format(
                        model_id=candidate.get("model_id") or s["unknown"],
                        openness=candidate.get("openness_class") or s["unknown"],
                        license=candidate.get("license_id") or s["unknown"],
                        version=candidate.get("version_sha") or s["unknown"],
                    )
                )
                if candidate.get("artifact_type") == "model-release"
                else ""
            )
            cards.append(
                f"<article><h3><a href=\"{link}\">{html.escape(candidate.get('title', 'Untitled'))}</a></h3>"
                f"<p class=\"meta\">{html.escape(s['authors'])}: {html.escape(_authors(candidate, s['unknown']))} · "
                f"{html.escape(s['date'])}: {html.escape(candidate.get('published') or s['unknown'])}<br>"
                f"{html.escape(s['artifact'])}: {html.escape(artifact_label)} / {html.escape(candidate.get('lane', 'recent-paper'))}{artifact_meta}<br>"
                f"{html.escape(s['scores'].format(overall=scores['overall'], relevance=scores['relevance'], quality=scores['intrinsic_quality'], external=scores['external_signal']).replace('**', ''))}<br>"
                f"{html.escape(s['evidence'].format(level=review.get('evidence_level'), confidence=review.get('confidence'), sources=', '.join(candidate.get('sources', []))).replace('`', ''))}</p>"
                f"{resources}<p><strong>{html.escape(s['problem'])}:</strong> {html.escape(str(review.get('scientific_problem') or s['missing']))}</p>"
                f"<h4>{html.escape(s['prior'])}</h4>{bullets(review.get('previous_work_gap', []))}"
                f"<h4>{html.escape(s['modules'])}</h4><div class=\"table-wrap\"><table><thead><tr>{module_headers}</tr></thead>"
                f"<tbody>{modules}</tbody></table></div>"
                f"<h4>{html.escape(s['experiments'])}</h4>{bullets(review.get('experimental_evidence', []))}"
                f"<h4>{html.escape(s['limitations'])}</h4>{bullets(review.get('limitations', []))}"
                f"<p><strong>{html.escape(s['why_read'])}:</strong> {html.escape(str(review.get('why_read') or s['missing']))}</p></article>"
            )
        if cards:
            sections.append(f"<section><h2>{html.escape(topic['label'])}</h2>{''.join(cards)}</section>")
    watch = "".join(
        f"<li><a href=\"{html.escape(safe_http_url(item['candidate'].get('abs_url')) or '#', quote=True)}\">{html.escape(item['candidate'].get('title', 'Untitled'))}</a>"
        f" — {html.escape(topic_labels.get(item['primary_topic'], item['primary_topic']))}; "
        f"{html.escape(s['watch_line'].format(overall=item['scores']['overall'], level=item['review'].get('evidence_level'), confidence=item['review'].get('confidence'), reasons='; '.join(item['decision_reasons'])))}</li>"
        for item in watchlist
    ) or f"<li>{html.escape(s['none'])}</li>"
    failure_items = "".join(
        f"<li>{html.escape(str(item.get('source')))} / {html.escape(str(item.get('topic') or item.get('date') or item.get('lane') or 'unknown'))}: "
        f"{html.escape(truncate(str(item.get('error')), 400))}</li>"
        for item in source_log.get("failures", [])
    )
    truncated_queries = [
        entry for entry in source_log.get("queries", []) if entry.get("potentially_truncated_window")
    ]
    truncation_items = "".join(
        "<li>"
        + html.escape(
            s["truncation"].format(
                source=item.get("source"),
                scope=item.get("topic") or item.get("date") or item.get("lane") or "unknown",
                raw=item.get("raw_returned", "unknown"),
                limit=item.get("requested_limit", "unknown"),
                total=item.get("total_results") if item.get("total_results") is not None else "unknown",
            ).replace("`", "")
        )
        + "</li>"
        for item in truncated_queries
    )
    gaps = failure_items + truncation_items or f"<li>{html.escape(s['none'])}</li>"
    shortlist_note = f"<p>{html.escape(s['shortlist'])}</p>" if reviewed_count < candidate_count else ""
    failure_warning = (
        f"<p><strong>{html.escape(s['failure_warning'])}</strong></p>" if source_log.get("failures") else ""
    )
    truncation_warning = (
        f"<p><strong>{html.escape(s['truncation_warning'])}</strong></p>" if truncated_queries else ""
    )
    return f"""<!doctype html>
<html lang=\"{html.escape(language, quote=True)}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{html.escape(profile['name'])}</title><style>
body{{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1100px;margin:auto;padding:32px;color:#16202a;background:#f5f7fb;line-height:1.65}}
h1,h2,h3,h4{{line-height:1.25}} a{{color:#2457d6}} .meta{{color:#5a6573;font-size:.92rem}} article{{background:#fff;border:1px solid #dfe5ee;border-radius:14px;padding:22px;margin:18px 0;box-shadow:0 4px 18px #1f33500d}}
.summary{{background:#eaf1ff;border-left:5px solid #2457d6;padding:14px 18px;border-radius:8px}} table{{width:100%;border-collapse:collapse;font-size:.92rem}} th,td{{border:1px solid #dfe5ee;padding:8px;vertical-align:top}} th{{background:#eef3fa}} .table-wrap{{overflow-x:auto}}
</style></head><body><h1>{html.escape(profile['name'])} — {html.escape(s['title_suffix'])}</h1>
<div class=\"summary\"><p>{html.escape(s['generated'])}: {html.escape(generated_at)}<br>
{html.escape(s['window'])}: {html.escape(s['past_days'].format(days=days))} (cutoff: {html.escape(str(cutoff))})<br>
{html.escape(s['selection'].format(highlights=len(highlights), watchlist=len(watchlist)))}<br>
{html.escape(s['coverage'])}: {html.escape(_source_summary(source_log, s))}</p>
<p>{html.escape(s['pool'].format(candidates=candidate_count, reviewed=reviewed_count, unreviewed=max(0, candidate_count - reviewed_count)))}</p>
{shortlist_note}<p>{html.escape(s['score_note'])}</p></div>
{''.join(sections)}<section><h2>{html.escape(s['watch'])}</h2><ul>{watch}</ul></section>
<section><h2>{html.escape(s['gaps'])}</h2><ul>{gaps}</ul>{failure_warning}{truncation_warning}</section></body></html>"""


def build_digest(workspace: Path, mark_seen: bool = False) -> dict[str, Any]:
    profile = load_json(workspace / "profile.json")
    candidate_payload = load_json(workspace / "candidates.json")
    review_payload = load_json(workspace / "reviewed.json")
    source_log = load_json(workspace / "source-log.json")
    current_digest = profile_digest(profile)
    for label, payload in (
        ("candidates.json", candidate_payload),
        ("reviewed.json", review_payload),
        ("source-log.json", source_log),
    ):
        if payload.get("profile_digest") != current_digest:
            raise RadarError(f"{label} does not match profile.json; rerun fetch and review")
    run_id = candidate_payload.get("run_id")
    if not run_id or review_payload.get("run_id") != run_id or source_log.get("run_id") != run_id:
        raise RadarError("Candidates, reviews, and source log come from different runs")
    state: dict[str, Any] | None = None
    if mark_seen:
        state = load_state(workspace / "state.json")
    candidates = {item["canonical_id"]: item for item in candidate_payload.get("candidates", [])}
    reviews = review_payload.get("reviews", [])
    if not isinstance(reviews, list):
        raise RadarError("reviewed.json has no reviews list")
    evaluations: list[dict[str, Any]] = []
    duplicate_ids: set[str] = set()
    reviewed_ids: set[str] = set()
    for review in reviews:
        if not isinstance(review, dict) or not review.get("canonical_id"):
            continue
        canonical_id = review["canonical_id"]
        if canonical_id in reviewed_ids:
            duplicate_ids.add(canonical_id)
            continue
        reviewed_ids.add(canonical_id)
        candidate = candidates.get(canonical_id)
        if not candidate:
            evaluations.append(
                {
                    "canonical_id": canonical_id,
                    "candidate": {"canonical_id": canonical_id, "title": canonical_id},
                    "review": review,
                    "decision": "reject",
                    "decision_reasons": ["candidate_missing_from_candidates_json"],
                    "primary_topic": review.get("primary_topic", ""),
                    "artifact_type": review.get("artifact_type", "paper"),
                    "lane": review.get("lane", "recent-paper"),
                    "scores": None,
                }
            )
            continue
        evaluations.append(evaluate_review(review, candidate, profile))
    if duplicate_ids:
        raise RadarError("Duplicate review IDs: " + ", ".join(sorted(duplicate_ids)))
    completed_review_ids = {
        item["canonical_id"]
        for item in evaluations
        if item.get("scores") is not None and item["canonical_id"] in candidates
    }
    unreviewed_ids = sorted(set(candidates) - completed_review_ids)
    incomplete_review_ids = sorted((reviewed_ids & set(candidates)) - completed_review_ids)
    missing_review_ids = sorted(set(candidates) - reviewed_ids)
    source_truncations = [
        entry for entry in source_log.get("queries", []) if entry.get("potentially_truncated_window")
    ]
    topic_ids = [topic["id"] for topic in profile["topics"]]
    highlights, quota_report = _quota_select_highlights(
        [item for item in evaluations if item["decision"] == "eligible-highlight"],
        profile,
    )
    selected_ids = {item["canonical_id"] for item in highlights}
    watch_eligible = [
        item
        for item in evaluations
        if item["decision"] == "eligible-watchlist" and item["canonical_id"] not in selected_ids and item["scores"]
    ]
    lane_limits = None
    initial_lane_counts = None
    if profile.get("profile_version") == 2:
        lane_limits = {lane["id"]: int(lane["max_digest_items"]) for lane in profile.get("lanes", [])}
        initial_lane_counts = Counter(item.get("lane", "recent-paper") for item in highlights)
    watchlist = _diverse_select(
        watch_eligible,
        topic_ids,
        max(0, int(profile["max_digest_papers"]) - len(highlights)),
        int(profile["max_per_topic"]),
        Counter(item["primary_topic"] for item in highlights),
        lane_limits,
        initial_lane_counts,
    )
    if profile.get("profile_version") == 2:
        digest_lane_counts = Counter(item.get("lane", "recent-paper") for item in highlights + watchlist)
        for lane_id, lane_status in quota_report["lanes"].items():
            lane_status["digest_selected"] = digest_lane_counts[lane_id]
            lane_status["maximum_met"] = digest_lane_counts[lane_id] <= int(lane_status["maximum"])
    generated_at = utc_now()
    markdown_output = render_markdown(
        profile,
        highlights,
        watchlist,
        source_log,
        generated_at,
        len(candidates),
        len(completed_review_ids),
    )
    html_output = render_html(
        profile,
        highlights,
        watchlist,
        source_log,
        generated_at,
        len(candidates),
        len(completed_review_ids),
    )
    write_text(workspace / "digest.md", markdown_output)
    write_text(workspace / "digest.html", html_output)
    report = {
        "schema_version": 1,
        "generated_at": generated_at,
        "run_id": run_id,
        "profile_digest": current_digest,
        "profile_name": profile["name"],
        "artifacts": {
            "digest_markdown_sha256": sha256_text(markdown_output),
            "digest_html_sha256": sha256_text(html_output),
        },
        "counts": {
            "candidates": len(candidates),
            "review_records": len(reviews),
            "reviewed": len(completed_review_ids),
            "incomplete_reviews": len(incomplete_review_ids),
            "unreviewed_candidates": len(unreviewed_ids),
            "highlighted": len(highlights),
            "watchlisted": len(watchlist),
            "rejected_or_not_selected": len(evaluations) - len(highlights) - len(watchlist),
        },
        "highlight_ids": [item["canonical_id"] for item in highlights],
        "watchlist_ids": [item["canonical_id"] for item in watchlist],
        "quota_fulfillment": quota_report,
        "screening_coverage": {
            "exhaustive": not unreviewed_ids,
            "unreviewed_count": len(unreviewed_ids),
            "unreviewed_ids": unreviewed_ids,
            "missing_review_ids": missing_review_ids,
            "incomplete_review_ids": incomplete_review_ids,
            "reason": "missing_or_incomplete_review" if unreviewed_ids else None,
        },
        "retrieval_coverage": {
            "exhaustive": not source_log.get("failures") and not source_truncations,
            "failure_count": len(source_log.get("failures", [])),
            "potentially_truncated_query_count": len(source_truncations),
        },
        "overall_coverage_exhaustive": bool(
            not unreviewed_ids and not source_log.get("failures") and not source_truncations
        ),
        "evaluations": [
            {
                "canonical_id": item["canonical_id"],
                "decision": (
                    "highlight"
                    if item["canonical_id"] in {entry["canonical_id"] for entry in highlights}
                    else "watchlist"
                    if item["canonical_id"] in {entry["canonical_id"] for entry in watchlist}
                    else item["decision"]
                ),
                "primary_topic": item["primary_topic"],
                "artifact_type": item.get("artifact_type", "paper"),
                "lane": item.get("lane", "recent-paper"),
                "scores": item["scores"],
                "reasons": item["decision_reasons"],
            }
            for item in evaluations
        ],
        "source_failures": source_log.get("failures", []),
        "source_truncations": source_truncations,
        "marked_seen": False,
    }
    write_json(workspace / "selection-report.json", report)
    if mark_seen:
        state_path = workspace / "state.json"
        assert state is not None
        seen = state["seen"]
        for item in highlights + watchlist:
            seen[item["canonical_id"]] = {
                "first_seen_at": seen.get(item["canonical_id"], {}).get("first_seen_at", generated_at),
                "last_seen_at": generated_at,
                "title": item["candidate"].get("title"),
                "artifact_type": item["candidate"].get("artifact_type", "paper"),
                "lane": item["candidate"].get("lane", "recent-paper"),
                "entity_id": item["candidate"].get("entity_id") or item["canonical_id"],
                "event_id": item["candidate"].get("event_id") or item["canonical_id"],
                "decision": "highlight" if item in highlights else "watchlist",
                "delivery_mode": "local-acknowledged",
            }
        state["updated_at"] = generated_at
        try:
            write_json(state_path, state)
        except OSError as exc:
            raise RadarError("Failed to persist seen state; selection remains unacknowledged") from exc
        report["marked_seen"] = True
        write_json(workspace / "selection-report.json", report)
    return {
        "workspace": str(workspace.resolve()),
        "highlights": len(highlights),
        "watchlist": len(watchlist),
        "marked_seen": mark_seen,
        "digest_markdown": str((workspace / "digest.md").resolve()),
        "digest_html": str((workspace / "digest.html").resolve()),
        "selection_report": str((workspace / "selection-report.json").resolve()),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--mark-seen", action="store_true", help="Acknowledge an accepted local-only digest as consumed")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        print(json.dumps(build_digest(args.workspace, args.mark_seen), ensure_ascii=False, indent=2))
        return 0
    except RadarError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
