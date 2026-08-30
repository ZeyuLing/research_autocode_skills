# Scheduling and delivery

## Preferred recurring setup

When running inside Codex, use the host application's recurring automation facility to invoke `$track-ai-papers` on the desired schedule. The automation prompt should include:

- the profile or five topic labels
- timezone and delivery time
- lookback window
- maximum papers per topic
- delivery channels
- instruction to disclose source failures and keep abstract-only items in the watchlist
- for v2 profiles, instruction to preserve the classic/open-model lane quotas and the audiovisual minimum without lowering any quality or evidence gate
- instruction to run the independent first-party `organization-release` lane, preserve its machine-readable coverage audit, and report `no_release`, partial, failed, and uncovered sources separately

Do not silently create a recurring task. Confirm the cadence and external delivery target unless the user already specified them.

Example task prompt:

```text
Use $track-ai-papers every weekday. Fetch the configured recent-paper window plus the v2 classic and open-model lanes for <workspace>/profile.json, and run the independent first-party organization technical-release lane using its extensible coverage matrix. Review candidates that can clear the artifact-appropriate quality gate, preserve lane/topic quotas only among eligible highlights, render the digest and organization-release coverage audit, and deliver them to the configured Telegram channel with --mark-seen. Report no-release, partial, failed and uncovered organization sources separately from other source or delivery failures, and consume artifacts only after every requested channel succeeds.
```

## Supported channels

`notify_digest.py` reads secrets from environment variables only.

### Email

- `PAPER_RADAR_SMTP_HOST`
- `PAPER_RADAR_SMTP_PORT` (default `465`)
- `PAPER_RADAR_SMTP_USER`
- `PAPER_RADAR_SMTP_PASSWORD`
- `PAPER_RADAR_EMAIL_FROM`
- `PAPER_RADAR_EMAIL_TO` (comma-separated)
- `PAPER_RADAR_SMTP_SSL` (`true` by default; set `false` for STARTTLS)

### Telegram

- `PAPER_RADAR_TELEGRAM_BOT_TOKEN`
- `PAPER_RADAR_TELEGRAM_CHAT_ID`

Long digests are sent as numbered text chunks. Markdown parsing is deliberately disabled to avoid malformed-message failures.

### Slack

- `PAPER_RADAR_SLACK_WEBHOOK_URL`

### Feishu / Lark

- `PAPER_RADAR_FEISHU_WEBHOOK_URL`

### WeCom

- `PAPER_RADAR_WECOM_WEBHOOK_URL`

## Safe rollout

1. Render Markdown and HTML locally.
2. Run notification with `--dry-run` and inspect `delivery-report.json`.
3. Send to one test channel.
4. Send the accepted digest with `--mark-seen`; the notifier updates state only if every requested channel succeeds.
5. Only then enable a recurring automation.

A missing secret is `skipped_missing_config`, not success. A non-2xx response or a 2xx webhook response carrying a platform-level error code is a failure; the response body is recorded in truncated form. Never print secret values in logs.

Before any delivery or dry run, the notifier validates the current profile/run/selection binding and the SHA-256 hashes of both rendered artifacts. For real sends it also checks the seen-state schema when `--mark-seen` is requested and verifies configuration for every requested channel. A known missing channel blocks all real sends so an early channel cannot be delivered and then duplicated on retry. Partial webhook chunks or partially refused email recipients are reported as partial delivery and never mark the batch seen.

If a digest renders but notification fails, retain the digest and retry delivery without refetching. The papers remain unseen, so a failed push cannot silently consume them.
