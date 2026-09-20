"""UHH Mail Client & Content Processor.

Extracts unread emails from UHH IMAP, classifies by mail_rules.md,
cleans body text for high-priority items, and writes mail_brief.md to CacheContext.
Safe peek: never marks emails as read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import email
from email.header import decode_header
import html
import imaplib
import os
from pathlib import Path
import re
import sys
from typing import List, Tuple

from . import config


@dataclass
class FilterRules:
    senders: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class ProcessedEmail:
    msg_id: str
    subject: str
    sender: str
    date_str: str
    is_high_priority: bool = False
    matched_reasons: list[str] = field(default_factory=list)
    body_snippet: str = ""


def load_filter_rules(rules_path: Path) -> FilterRules:
    """Parse mail_rules.md for Senders and Keywords lists."""
    rules = FilterRules()
    if not rules_path.is_file():
        return rules

    current_section: str | None = None
    with rules_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("# "):
                continue

            if stripped.startswith("## "):
                header = stripped[3:].strip().lower()
                if "sender" in header:
                    current_section = "senders"
                elif "keyword" in header:
                    current_section = "keywords"
                else:
                    current_section = None
                continue

            if stripped.startswith("- ") and current_section:
                item = stripped[2:].strip().lower()
                # Ignore comments or empty items
                if item and not item.startswith("#"):
                    if current_section == "senders":
                        rules.senders.append(item)
                    elif current_section == "keywords":
                        rules.keywords.append(item)

    return rules


def load_env_credentials(env_path: Path) -> dict[str, str]:
    """Parse key=value pairs from a local .env file."""
    env_vars: dict[str, str] = {}
    if not env_path.is_file():
        return env_vars

    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip().strip("'\"")
    return env_vars


def decode_header_str(header_value: str | None) -> str:
    """Decode RFC 2047 encoded email headers."""
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = []
    for content, encoding in decoded_fragments:
        if isinstance(content, bytes):
            result.append(content.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(str(content))
    # Replace newlines in header with space
    return re.sub(r"\s+", " ", "".join(result)).strip()


def extract_plain_text(msg: email.message.Message) -> str:
    """Extract and clean plain text content from email message."""
    plain_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"

            if content_type == "text/plain":
                plain_parts.append(payload.decode(charset, errors="replace"))
            elif content_type == "text/html":
                html_parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    # Prefer plain text, fallback to HTML stripped
    raw_text = "\n".join(plain_parts) if plain_parts else ""
    if not raw_text.strip() and html_parts:
        raw_html = "\n".join(html_parts)
        # Simple HTML tag stripping
        clean_html = re.sub(r"<style[^>]*>.*?</style>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r"<script[^>]*>.*?</script>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
        clean_html = re.sub(r"<[^>]+>", " ", clean_html)
        raw_text = html.unescape(clean_html)

    # Normalize whitespace
    raw_text = re.sub(r"[ \t]+", " ", raw_text)
    raw_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw_text)
    return raw_text.strip()


def match_email(
    subject: str,
    sender: str,
    rules: FilterRules,
) -> tuple[bool, list[str]]:
    """Check if email matches sender or keyword rules."""
    reasons: list[str] = []
    lower_sender = sender.lower()
    lower_subject = subject.lower()

    for s in rules.senders:
        if s in lower_sender:
            reasons.append(f"发件人命中: `{s}`")
            break

    for k in rules.keywords:
        if k in lower_subject:
            reasons.append(f"关键词命中: `{k}`")
            break

    return (len(reasons) > 0, reasons)


def fetch_and_generate_brief() -> Path:
    """Connect to UHH mail, process unread emails, and generate mail_brief.md."""
    # 1. Load config & rules
    rules = load_filter_rules(config.RULES_PATH)
    env_vars = load_env_credentials(config.ENV_PATH)

    user = os.environ.get("UHH_MAIL_USER") or env_vars.get("UHH_MAIL_USER", "").strip()
    password = os.environ.get("UHH_MAIL_PASS") or env_vars.get("UHH_MAIL_PASS", "").strip()
    host = os.environ.get("UHH_MAIL_HOST") or env_vars.get("UHH_MAIL_HOST", "public.uni-hamburg.de").strip()
    port = int(os.environ.get("UHH_MAIL_PORT") or env_vars.get("UHH_MAIL_PORT", 993))

    if not user or not password:
        raise ValueError(f"UHH Mail credentials missing in {config.ENV_PATH}")

    # 2. Connect
    client = imaplib.IMAP4_SSL(host, port)
    try:
        client.login(user, password)
        client.select("INBOX", readonly=True)

        status, response = client.search(None, "UNSEEN")
        unread_ids = response[0].split() if response and response[0] else []
        total_unread = len(unread_ids)

        high_priority: list[ProcessedEmail] = []
        normal_list: list[ProcessedEmail] = []

        # Process the most recent emails (up to config.MAX_EMAILS_TO_SCAN)
        scan_ids = unread_ids[-config.MAX_EMAILS_TO_SCAN :]

        for b_id in reversed(scan_ids):
            msg_id = b_id.decode("utf-8") if isinstance(b_id, bytes) else str(b_id)

            # Peek header only first
            res, header_data = client.fetch(
                b_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"
            )
            if res != "OK" or not header_data:
                continue

            header_text = header_data[0][1]
            hdr_msg = email.message_from_bytes(header_text)
            subject = decode_header_str(hdr_msg.get("Subject")) or "(无主题)"
            sender = decode_header_str(hdr_msg.get("From")) or "(未知发件人)"
            date_str = hdr_msg.get("Date", "").strip()

            is_high, reasons = match_email(subject, sender, rules)

            if is_high:
                # Fetch full text safely with PEEK
                res, full_data = client.fetch(b_id, "(BODY.PEEK[])")
                body_text = ""
                if res == "OK" and full_data:
                    full_msg = email.message_from_bytes(full_data[0][1])
                    body_text = extract_plain_text(full_msg)
                    if len(body_text) > config.MAX_BODY_CHARS:
                        body_text = body_text[: config.MAX_BODY_CHARS] + "\n...(正文过长已截断)..."

                high_priority.append(
                    ProcessedEmail(
                        msg_id=msg_id,
                        subject=subject,
                        sender=sender,
                        date_str=date_str,
                        is_high_priority=True,
                        matched_reasons=reasons,
                        body_snippet=body_text,
                    )
                )
            else:
                normal_list.append(
                    ProcessedEmail(
                        msg_id=msg_id,
                        subject=subject,
                        sender=sender,
                        date_str=date_str,
                        is_high_priority=False,
                    )
                )

    finally:
        try:
            client.logout()
        except Exception:
            pass

    # 3. Render Markdown
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        "---",
        "type: mailbox",
        "source: uhh_mail",
        f"updated_at: {datetime.now().isoformat()}",
        f"total_unread: {total_unread}",
        f"high_priority_count: {len(high_priority)}",
        "---",
        f"# ⟨ Mailbox : UHH 邮件预读 ⟩",
        f"> 更新时间: {now_str} | 未读总数: {total_unread} 封 (🔴 重点关注: {len(high_priority)} 封 | ⚪ 常规通知: {len(normal_list)} 封)",
        "",
    ]

    # Section 1: High Priority
    if high_priority:
        lines.append("## 🔴 需关注邮件 (已命中规则并清洗正文)")
        for idx, item in enumerate(high_priority, 1):
            reasons_str = "、".join(item.matched_reasons)
            lines.append(f"### {idx}. {item.subject}")
            lines.append(f"- **发件人**: {item.sender}")
            lines.append(f"- **时  间**: {item.date_str}")
            lines.append(f"- **命中规则**: {reasons_str}")
            lines.append("- **正文提要**:")
            lines.append("```text")
            lines.append(item.body_snippet if item.body_snippet else "(无正文内容)")
            lines.append("```")
            lines.append("")
    else:
        lines.append("## 🔴 需关注邮件")
        lines.append("*（当前未读邮件中暂无命中关注规则的项目）*")
        lines.append("")

    # Section 2: Normal / Broadcast Summary
    lines.append(f"## ⚪ 常规通知与广播通报 (未命中规则，仅统计)")
    if normal_list:
        for item in normal_list:
            # Compact one-liner
            lines.append(f"- **{item.sender}**: {item.subject}")
    else:
        lines.append("*（无其他常规未读邮件）*")
    lines.append("")

    # 4. Save to CacheContext
    config.CACHE_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines)
    config.MAIL_BRIEF_PATH.write_text(content, encoding="utf-8")

    print(
        f"[UHH Mail] Synced {total_unread} unread emails ({len(high_priority)} high priority). "
        f"Saved to: {config.MAIL_BRIEF_PATH}"
    )
    return config.MAIL_BRIEF_PATH


if __name__ == "__main__":
    brief_path = fetch_and_generate_brief()
    print(f"Generated brief at: {brief_path}")
