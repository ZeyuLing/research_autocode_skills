#!/usr/bin/env python3
"""Deliver a rendered paper digest through configured notification channels."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from radar_common import (
    RadarError,
    load_json,
    load_state,
    profile_digest,
    sha256_file,
    truncate,
    utc_now,
    write_json,
)


CHANNELS = {"email", "telegram", "slack", "feishu", "wecom"}
REQUIRED_ENV = {
    "email": (
        "PAPER_RADAR_SMTP_HOST",
        "PAPER_RADAR_SMTP_USER",
        "PAPER_RADAR_SMTP_PASSWORD",
        "PAPER_RADAR_EMAIL_FROM",
        "PAPER_RADAR_EMAIL_TO",
    ),
    "telegram": ("PAPER_RADAR_TELEGRAM_BOT_TOKEN", "PAPER_RADAR_TELEGRAM_CHAT_ID"),
    "slack": ("PAPER_RADAR_SLACK_WEBHOOK_URL",),
    "feishu": ("PAPER_RADAR_FEISHU_WEBHOOK_URL",),
    "wecom": ("PAPER_RADAR_WECOM_WEBHOOK_URL",),
}


CHANNEL_CHUNK_LIMITS = {
    "telegram": (3500, False),
    "slack": (10000, False),
    "feishu": (6000, True),
    "wecom": (1800, True),
}


class PartialDeliveryError(RadarError):
    """A channel accepted part, but not all, of the requested delivery."""


def _utf8_prefix(text: str, byte_limit: int) -> str:
    raw = text.encode("utf-8")[:byte_limit]
    while raw:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            raw = raw[:-1]
    return text[:1]


def _chunks(text: str, limit: int = 3500, by_utf8_bytes: bool = False) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        within_limit = len(remaining.encode("utf-8")) <= limit if by_utf8_bytes else len(remaining) <= limit
        if within_limit:
            chunks.append(remaining)
            break
        prefix = _utf8_prefix(remaining, limit) if by_utf8_bytes else remaining[:limit]
        split_at = prefix.rfind("\n")
        if split_at < len(prefix) // 2:
            split_at = len(prefix)
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks or [""]


def _channel_chunks(channel: str, text: str) -> list[str]:
    limit, by_bytes = CHANNEL_CHUNK_LIMITS[channel]
    return _chunks(text, limit, by_bytes)


def _validate_webhook_response(channel: str, response_body: bytes) -> None:
    text_body = response_body.decode("utf-8", errors="replace").strip()
    if channel == "slack":
        if text_body and text_body.lower() != "ok":
            raise RadarError(f"slack returned a business error: {truncate(text_body, 300)}")
        return
    try:
        payload = json.loads(text_body)
    except json.JSONDecodeError as exc:
        raise RadarError(f"{channel} returned a non-JSON response: {truncate(text_body, 300)}") from exc
    if not isinstance(payload, dict):
        raise RadarError(f"{channel} returned an unexpected JSON response shape")
    if channel == "telegram" and payload.get("ok") is not True:
        raise RadarError(f"telegram returned a business error: {truncate(text_body, 300)}")
    if channel == "feishu":
        code = payload.get("code", payload.get("StatusCode"))
        if str(code) != "0":
            raise RadarError(f"feishu returned a business error: {truncate(text_body, 300)}")
    if channel == "wecom" and str(payload.get("errcode")) != "0":
        raise RadarError(f"wecom returned a business error: {truncate(text_body, 300)}")


def _post_json(url: str, payload: dict[str, Any], channel: str) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "track-ai-papers/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response_raw = response.read(4000)
            response_body = response_raw.decode("utf-8", errors="replace")
            if not 200 <= response.status < 300:
                raise RadarError(f"{channel} returned HTTP {response.status}: {truncate(response_body, 300)}")
            _validate_webhook_response(channel, response_raw)
    except urllib.error.HTTPError as exc:
        response_body = exc.read(1000).decode("utf-8", errors="replace")
        raise RadarError(f"{channel} returned HTTP {exc.code}: {truncate(response_body, 300)}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RadarError(f"{channel} request failed: {type(exc).__name__}") from exc
    except (http.client.HTTPException, ValueError) as exc:
        raise RadarError(f"{channel} request configuration is invalid: {type(exc).__name__}") from None


def _redact_secrets(value: str) -> str:
    redacted = value
    for name in {item for fields in REQUIRED_ENV.values() for item in fields}:
        secret = os.environ.get(name)
        if secret:
            for sensitive in sorted(
                {secret, *(part.strip() for part in secret.split(",") if part.strip())},
                key=len,
                reverse=True,
            ):
                redacted = redacted.replace(sensitive, "[REDACTED]")
    return redacted


def _send_email(markdown: str, html_body: str, subject: str) -> int:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.environ["PAPER_RADAR_EMAIL_FROM"]
    recipients = [item.strip() for item in os.environ["PAPER_RADAR_EMAIL_TO"].split(",") if item.strip()]
    if not recipients:
        raise RadarError("PAPER_RADAR_EMAIL_TO contains no recipient")
    message["To"] = ", ".join(recipients)
    message.set_content(markdown)
    message.add_alternative(html_body, subtype="html")
    host = os.environ["PAPER_RADAR_SMTP_HOST"]
    port = int(os.environ.get("PAPER_RADAR_SMTP_PORT", "465"))
    username = os.environ["PAPER_RADAR_SMTP_USER"]
    password = os.environ["PAPER_RADAR_SMTP_PASSWORD"]
    use_ssl = os.environ.get("PAPER_RADAR_SMTP_SSL", "true").lower() not in {"0", "false", "no"}
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as client:
            client.login(username, password)
            refused = client.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as client:
            client.starttls(context=ssl.create_default_context())
            client.login(username, password)
            refused = client.send_message(message)
    if refused:
        raise PartialDeliveryError(f"email delivery refused {len(refused)} recipient(s)")
    return 1


def _send_channel(channel: str, markdown: str, html_body: str, subject: str) -> int:
    if channel == "email":
        return _send_email(markdown, html_body, subject)
    chunks = _channel_chunks(channel, markdown)
    if channel == "telegram":
        token = os.environ["PAPER_RADAR_TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["PAPER_RADAR_TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        for index, chunk in enumerate(chunks, 1):
            prefix = f"[{index}/{len(chunks)}] " if len(chunks) > 1 else ""
            _post_json(url, {"chat_id": chat_id, "text": prefix + chunk, "disable_web_page_preview": True}, channel)
        return len(chunks)
    if channel == "slack":
        url = os.environ["PAPER_RADAR_SLACK_WEBHOOK_URL"]
        for index, chunk in enumerate(chunks, 1):
            prefix = f"[{index}/{len(chunks)}]\n" if len(chunks) > 1 else ""
            _post_json(url, {"text": prefix + chunk}, channel)
        return len(chunks)
    if channel == "feishu":
        url = os.environ["PAPER_RADAR_FEISHU_WEBHOOK_URL"]
        for index, chunk in enumerate(chunks, 1):
            prefix = f"[{index}/{len(chunks)}]\n" if len(chunks) > 1 else ""
            _post_json(url, {"msg_type": "text", "content": {"text": prefix + chunk}}, channel)
        return len(chunks)
    if channel == "wecom":
        url = os.environ["PAPER_RADAR_WECOM_WEBHOOK_URL"]
        for index, chunk in enumerate(chunks, 1):
            prefix = f"[{index}/{len(chunks)}]\n" if len(chunks) > 1 else ""
            _post_json(url, {"msgtype": "text", "text": {"content": prefix + chunk}}, channel)
        return len(chunks)
    raise RadarError(f"Unsupported channel: {channel}")


def _validate_delivery_run(workspace: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = load_json(workspace / "profile.json")
    selection = load_json(workspace / "selection-report.json")
    candidate_payload = load_json(workspace / "candidates.json")
    current_digest = profile_digest(profile)
    if candidate_payload.get("profile_digest") != current_digest:
        raise RadarError("candidates.json does not match the current profile.json")
    for field in ("profile_digest", "run_id"):
        if not candidate_payload.get(field) or selection.get(field) != candidate_payload.get(field):
            raise RadarError(f"selection-report.json and candidates.json have different {field} values")
    candidate_ids = {item.get("canonical_id") for item in candidate_payload.get("candidates", [])}
    selected_ids = set(selection.get("highlight_ids", [])) | set(selection.get("watchlist_ids", []))
    missing = sorted(identifier for identifier in selected_ids if identifier not in candidate_ids)
    if missing:
        raise RadarError("selection-report.json contains IDs absent from candidates.json: " + ", ".join(missing))
    artifacts = selection.get("artifacts")
    expected_artifacts = {
        "digest_markdown_sha256": sha256_file(workspace / "digest.md"),
        "digest_html_sha256": sha256_file(workspace / "digest.html"),
    }
    if not isinstance(artifacts, dict) or any(
        artifacts.get(name) != digest for name, digest in expected_artifacts.items()
    ):
        raise RadarError("digest artifacts do not match selection-report.json; rerender before delivery")
    return selection, candidate_payload


def _load_valid_state(workspace: Path) -> dict[str, Any]:
    return load_state(workspace / "state.json")


def _mark_delivered(workspace: Path, channels: list[str], delivered_at: str) -> int:
    selection, candidate_payload = _validate_delivery_run(workspace)
    state_path = workspace / "state.json"
    state = _load_valid_state(workspace)
    titles = {item["canonical_id"]: item.get("title") for item in candidate_payload.get("candidates", [])}
    decisions = {identifier: "highlight" for identifier in selection.get("highlight_ids", [])}
    decisions.update({identifier: "watchlist" for identifier in selection.get("watchlist_ids", [])})
    seen = state.setdefault("seen", {})
    for identifier, decision in decisions.items():
        previous = seen.get(identifier, {}) if isinstance(seen.get(identifier, {}), dict) else {}
        seen[identifier] = {
            **previous,
            "first_seen_at": previous.get("first_seen_at", delivered_at),
            "last_seen_at": delivered_at,
            "first_delivered_at": previous.get("first_delivered_at", delivered_at),
            "last_delivered_at": delivered_at,
            "title": titles.get(identifier) or previous.get("title"),
            "decision": decision,
            "delivery_mode": "external",
            "channels": channels,
        }
    state["updated_at"] = delivered_at
    write_json(state_path, state)
    return len(decisions)


def deliver(
    workspace: Path,
    channels: list[str],
    dry_run: bool = False,
    subject: str | None = None,
    mark_seen: bool = False,
) -> dict[str, Any]:
    digest_path = workspace / "digest.md"
    html_path = workspace / "digest.html"
    try:
        markdown = digest_path.read_text(encoding="utf-8")
        html_body = html_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RadarError("Render digest.md and digest.html before delivery") from exc
    title_line = next((line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("# ")), "AI Paper Radar")
    email_subject = subject or title_line
    _validate_delivery_run(workspace)
    if mark_seen and not dry_run:
        _load_valid_state(workspace)
    missing_by_channel = {
        channel: [name for name in REQUIRED_ENV[channel] if not os.environ.get(name)] for channel in channels
    }
    blocked_by_missing_config = not dry_run and any(missing_by_channel.values())
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "dry_run": dry_run,
        "digest": str(digest_path.resolve()),
        "channels": [],
    }
    for channel in channels:
        missing = missing_by_channel[channel]
        entry: dict[str, Any] = {"channel": channel, "missing_environment": missing}
        if missing:
            entry.update({"status": "skipped_missing_config", "messages": 0})
        elif blocked_by_missing_config:
            entry.update({"status": "skipped_preflight_failed", "messages": 0})
        elif dry_run:
            entry.update({"status": "dry_run_ready", "messages": len(_channel_chunks(channel, markdown)) if channel != "email" else 1})
        else:
            try:
                entry.update({"status": "sent", "messages": _send_channel(channel, markdown, html_body, email_subject)})
            except (RadarError, smtplib.SMTPException, ValueError, OSError) as exc:
                entry.update(
                    {
                        "status": "failed",
                        "messages": 0,
                        "partial_delivery_possible": channel != "email" or isinstance(exc, PartialDeliveryError),
                        "error": truncate(_redact_secrets(str(exc)), 500),
                    }
                )
        report["channels"].append(entry)
    report["all_sent"] = bool(report["channels"]) and all(item["status"] == "sent" for item in report["channels"])
    report["all_ready_or_sent"] = bool(report["channels"]) and all(
        item["status"] in {"sent", "dry_run_ready"} for item in report["channels"]
    )
    report["marked_seen"] = False
    report["marked_seen_count"] = 0
    if mark_seen and not dry_run and report["all_sent"]:
        delivered_at = utc_now()
        try:
            report["marked_seen_count"] = _mark_delivered(workspace, channels, delivered_at)
            report["marked_seen"] = True
        except (RadarError, OSError) as exc:
            report["delivery_state"] = "sent_but_state_update_failed"
            report["state_update_error"] = truncate(_redact_secrets(str(exc)), 500)
    elif mark_seen:
        report["mark_seen_reason"] = "requires a non-dry run with every requested channel sent"
    report["partial_delivery"] = bool(
        any(item["status"] == "sent" for item in report["channels"]) and not report["all_sent"]
    ) or any(item.get("partial_delivery_possible") for item in report["channels"])
    report["delivery_complete"] = bool(report["all_sent"] and (not mark_seen or report["marked_seen"]))
    write_json(workspace / "delivery-report.json", report)
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--channels", required=True, help="Comma-separated channels: email,telegram,slack,feishu,wecom")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mark-seen", action="store_true", help="Consume papers only after every requested channel succeeds")
    parser.add_argument("--subject")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        channels = list(dict.fromkeys(value.strip().lower() for value in args.channels.split(",") if value.strip()))
        unknown = set(channels) - CHANNELS
        if unknown or not channels:
            raise RadarError(f"Invalid channels: {', '.join(sorted(unknown or set(channels)))}")
        result = deliver(args.workspace, channels, args.dry_run, args.subject, args.mark_seen)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.dry_run:
            return 0
        return 0 if result["delivery_complete"] else 3
    except RadarError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
