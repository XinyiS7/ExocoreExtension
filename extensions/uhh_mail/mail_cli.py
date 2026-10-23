"""Local IMAP/SMTP CLI for the UHH mailbox.

Purpose: read and answer mail without opening the webmail.

Design notes
------------
* ``reply`` is the primary entry point. It is a thin wrapper that adds the five
  things a plain ``send`` would get wrong:
    1. recipient derived from ``Reply-To`` / ``From`` (``--all`` adds To+Cc)
    2. threading headers: ``In-Reply-To`` + ``References`` (appended, not replaced)
    3. ``AW:`` subject prefix, never stacked
    4. optional quoted original (``--quote``)
    5. copy of the sent message appended to ``INBOX/Sent`` (SMTP does not do this)
* ``send`` is the raw primitive for starting a new thread.
* Safe by default: ``reply`` / ``send`` print the message and exit unless
  ``--confirm`` is given. Nothing is transmitted on a dry run.
* Bodies are always fetched with ``BODY.PEEK``. The only flag writes are the
  explicit ones (``show`` without ``--peek``, ``seen``, and a confirmed reply).

Run as::

    python -m extensions.uhh_mail.mail_cli <command> ...

or directly::

    python extensions/uhh_mail/mail_cli.py <command> ...
"""

from __future__ import annotations

import argparse
import email
import email.utils
import imaplib
import os
import re
import smtplib
import ssl
import sys
import time
from pathlib import Path

# --- package bootstrap so the file also works when executed directly --------
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from extensions.uhh_mail import config  # type: ignore[no-redef]
    from extensions.uhh_mail.mail_client import (  # type: ignore[no-redef]
        decode_header_str,
        extract_links,
        extract_plain_text,
        load_env_credentials,
    )
else:
    from . import config
    from .mail_client import (
        decode_header_str,
        extract_links,
        extract_plain_text,
        load_env_credentials,
    )


# --- identity / server constants -------------------------------------------
FROM_NAME = os.environ.get("UHH_MAIL_FROM_NAME", "Tang, Xinyi")
FROM_ADDR = os.environ.get("UHH_MAIL_FROM", "xinyi.tang@studium.uni-hamburg.de")
SMTP_HOST = os.environ.get("UHH_SMTP_HOST", "public.uni-hamburg.de")
SMTP_PORT = int(os.environ.get("UHH_SMTP_PORT", 587))
SENT_MAILBOX = os.environ.get("UHH_SENT_MAILBOX", "INBOX/Sent")

DEFAULT_SIGNATURE = "Mit freundlichen Grüßen\n\nXinyi Tang"
SUBJECT_PREFIX = "AW: "
MAX_QUOTE_CHARS = 6000

_PREFIX_RE = re.compile(r"^\s*(?:AW|RE|FWD|WG)\s*:", re.IGNORECASE)


# --- helpers ---------------------------------------------------------------
def _say(msg: str = "") -> None:
    print(msg)


def _load_credentials() -> dict[str, str]:
    env_vars = load_env_credentials(config.ENV_PATH)
    user = os.environ.get("UHH_MAIL_USER") or env_vars.get("UHH_MAIL_USER", "").strip()
    password = os.environ.get("UHH_MAIL_PASS") or env_vars.get("UHH_MAIL_PASS", "").strip()
    host = os.environ.get("UHH_MAIL_HOST") or env_vars.get("UHH_MAIL_HOST", "public.uni-hamburg.de").strip()
    port = int(os.environ.get("UHH_MAIL_PORT") or env_vars.get("UHH_MAIL_PORT", 993))
    if not user or not password:
        raise SystemExit(f"UHH Mail credentials missing in {config.ENV_PATH}")
    return {"user": user, "password": password, "host": host, "port": port}


def _connect(creds: dict[str, str], mailbox: str = "INBOX") -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(creds["host"], creds["port"])
    client.login(creds["user"], creds["password"])
    status, _ = client.select(mailbox)
    if status != "OK":
        raise SystemExit(f"IMAP: cannot open mailbox {mailbox!r}")
    return client


def _literal(data: list) -> tuple | None:
    """Return the (envelope, literal) tuple from an IMAP FETCH response.

    The position is not stable: depending on which attributes are requested the
    server may return ``[b'<FLAGS>', (b'<attrs>', b'<literal>')]`` instead of the
    tuple first, so scan for it rather than trusting index 0.
    """
    for item in data or []:
        if isinstance(item, tuple) and len(item) >= 2:
            return item
    return None


def _saw_seen(data: list) -> bool:
    for item in data or []:
        if isinstance(item, bytes) and b"\\Seen" in item:
            return True
        if isinstance(item, tuple) and isinstance(item[0], bytes) and b"\\Seen" in item[0]:
            return True
    return False


def _fetch_raw(client: imaplib.IMAP4_SSL, msg_id: str) -> bytes:
    status, data = client.fetch(msg_id, "(BODY.PEEK[])")
    literal = _literal(data)
    if status != "OK" or literal is None:
        raise SystemExit(f"IMAP: cannot fetch message {msg_id}")
    return literal[1]


def _fetch_header_part(client: imaplib.IMAP4_SSL, msg_id: str) -> tuple[bytes, bool]:
    """Return raw header bytes and the current \\Seen state."""
    status, data = client.fetch(
        msg_id, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO CC REPLY-TO SUBJECT DATE MESSAGE-ID REFERENCES IN-REPLY-TO THREAD-INDEX THREAD-TOPIC)])"
    )
    literal = _literal(data)
    if status != "OK" or literal is None:
        raise SystemExit(f"IMAP: cannot fetch headers of {msg_id}")
    return literal[1], _saw_seen(data)


def _mark_seen(client: imaplib.IMAP4_SSL, msg_ids: list[str], seen: bool = True) -> None:
    op = "+FLAGS.SILENT" if seen else "-FLAGS.SILENT"
    for msg_id in msg_ids:
        client.store(msg_id, op, r"(\Seen)")


def _local_stamp(date_header: str | None) -> str:
    if not date_header:
        return "?"
    try:
        dt = email.utils.parsedate_to_datetime(date_header)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_header


def _one_line(text: str, width: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= width else text[: width - 1] + "…"


def _sender_short(from_header: str) -> str:
    name, addr = email.utils.parseaddr(from_header)
    return name or addr


def _apply_subject_prefix(subject: str, prefix: str = SUBJECT_PREFIX) -> str:
    subject = (subject or "").strip() or "(无主题)"
    if _PREFIX_RE.match(subject):
        return subject
    return f"{prefix}{subject}"


def _base_subject(subject: str) -> str:
    return _PREFIX_RE.sub("", subject or "").strip()


def _quote_stamp(date_header: str | None) -> str:
    """Timestamp format used by the UHH webmail quote header."""
    if not date_header:
        return "?"
    try:
        dt = email.utils.parsedate_to_datetime(date_header).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_header


def _quote_block(original: email.message.Message) -> str:
    """Reproduce the webmail quote layout:

        Am 2026-10-22 10:48, schrieb Kammer, Paula:

        > original body
    """
    body = extract_plain_text(original)
    if len(body) > MAX_QUOTE_CHARS:
        body = body[:MAX_QUOTE_CHARS] + "\n…(引用已截断)"
    name, addr = email.utils.parseaddr(original.get("From") or "")
    author = name or addr or "(未知发件人)"
    quoted = "\n".join(("> " + line) if line.strip() else ">" for line in body.splitlines())
    return f"Am {_quote_stamp(original.get('Date'))}, schrieb {author}:\n\n{quoted}"


def _addresses(header_value: str | None) -> list[str]:
    """Bare envelope addresses, used for SMTP delivery."""
    return [addr for _name, addr in email.utils.getaddresses([header_value or ""]) if addr]


def _format_address(pair: tuple[str, str]) -> str:
    name, addr = pair
    return email.utils.formataddr((name, addr)) if name else addr


def _recipients(original: email.message.Message, reply_all: bool, override: str | None) -> tuple[list[str], list[str]]:
    """Recipients keep their display names, so the Sent copy reads naturally."""
    if override:
        return [a.strip() for a in override.split(",") if a.strip()], []
    source = original.get("Reply-To") or original.get("From") or ""
    pairs = [(n, a) for n, a in email.utils.getaddresses([source]) if a][:1]
    to_list = [_format_address(p) for p in pairs]
    known = {addr.lower() for _n, addr in pairs}
    cc_list: list[str] = []
    if reply_all:
        for header in ("To", "Cc"):
            for name, addr in email.utils.getaddresses([original.get(header) or ""]):
                if not addr or addr.lower() == FROM_ADDR.lower() or addr.lower() in known:
                    continue
                known.add(addr.lower())
                cc_list.append(_format_address((name, addr)))
    return to_list, cc_list


def _compose(
    *,
    to_list: list[str],
    cc_list: list[str],
    subject: str,
    text: str,
    in_reply_to: str | None = None,
    references: str | None = None,
    thread_topic: str | None = None,
    thread_index: str | None = None,
) -> email.message.EmailMessage:
    msg = email.message.EmailMessage()
    msg["From"] = email.utils.formataddr((FROM_NAME, FROM_ADDR))
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=FROM_ADDR.split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    if thread_topic:
        msg["Thread-Topic"] = thread_topic
    if thread_index:
        # Best effort for Exchange clients. RFC threading relies on References;
        # this is copied verbatim rather than re-derived.
        msg["Thread-Index"] = thread_index
    msg.set_content(text, subtype="plain", charset="utf-8", cte="quoted-printable")
    return msg


def _send_message(creds: dict[str, str], msg: email.message.EmailMessage) -> bytes:
    raw = msg.as_bytes()
    recipients = _addresses(msg.get("To")) + _addresses(msg.get("Cc"))
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(creds["user"], creds["password"])
        smtp.sendmail(FROM_ADDR, recipients, raw)
    return raw


def _append_to_sent(creds: dict[str, str], raw: bytes) -> str:
    client = imaplib.IMAP4_SSL(creds["host"], creds["port"])
    try:
        client.login(creds["user"], creds["password"])
        status, data = client.append(
            SENT_MAILBOX,
            r"(\Seen)",
            imaplib.Time2Internaldate(time.time()),
            raw,
        )
        detail = data[0].decode(errors="replace") if data and isinstance(data[0], bytes) else ""
        return f"{status} {detail}".strip()
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _print_preview(msg: email.message.EmailMessage, note: str = "") -> None:
    _say("-" * 72)
    for header in ("From", "To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To", "References", "Thread-Topic", "Thread-Index"):
        value = msg.get(header)
        if value is None:
            continue
        _say(f"{header:13}: {_one_line(str(value), 160)}")
    _say("-" * 72)
    _say(msg.get_body(preferencelist=("plain",)).get_content())
    _say("-" * 72)
    if note:
        _say(note)


def _read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8").strip()
    if args.body is not None:
        return args.body.strip()
    raise SystemExit("需要 --body 或 --body-file")


def _apply_signature(text: str, include_signature: bool) -> str:
    if not include_signature:
        return text
    return f"{text}\n\n{DEFAULT_SIGNATURE}"


# --- commands --------------------------------------------------------------
def cmd_list(args: argparse.Namespace) -> int:
    creds = _load_credentials()
    client = _connect(creds)
    try:
        criteria: list[str] = []
        if args.unread:
            criteria.append("UNSEEN")
        if args.sender:
            criteria += ["FROM", f'"{args.sender}"']
        status, data = client.search(None, *criteria) if criteria else client.search(None, "ALL")
        if status != "OK":
            raise SystemExit("IMAP search failed")
        ids = data[0].split() if data and data[0] else []
        if not ids:
            _say("(没有匹配的邮件)")
            return 0
        ids = ids[-args.limit :]
        _say(f"{'id':>6}  {'状态':<4} {'时间':<16} {'发件人':<20} 主题")
        for msg_id in reversed(ids):
            raw, seen = _fetch_header_part(client, msg_id)
            hdr = email.message_from_bytes(raw)
            state = "已读" if seen else "未读"
            _say(
                f"{msg_id.decode():>6}  {state:<4} {_local_stamp(hdr.get('Date')):<16} "
                f"{_one_line(_sender_short(decode_header_str(hdr.get('From'))), 20):<20} "
                f"{_one_line(decode_header_str(hdr.get('Subject')), 60)}"
            )
        return 0
    finally:
        try:
            client.logout()
        except Exception:
            pass


def cmd_show(args: argparse.Namespace) -> int:
    creds = _load_credentials()
    client = _connect(creds)
    try:
        raw, was_seen = _fetch_header_part(client, args.id)
        hdr = email.message_from_bytes(raw)
        _say("-" * 72)
        for key in ("From", "To", "Cc", "Subject", "Date", "Message-ID", "References"):
            value = hdr.get(key)
            if value is None:
                continue
            _say(f"{key:13}: {_one_line(decode_header_str(value), 160)}")
        _say("-" * 72)
        full = email.message_from_bytes(_fetch_raw(client, args.id))
        body_text = extract_plain_text(full).strip()
        # Surface links first: a bare URL hides easily in a wall of text.
        links = extract_links(body_text)
        if links:
            _say("🔗 链接:")
            for link in links:
                _say(f"   {link}")
            _say("-" * 72)
        _say(body_text or "(无正文内容)")
        _say("-" * 72)
        if args.peek:
            if not was_seen:
                _say("（--peek：未改动已读状态）")
        else:
            _mark_seen(client, [args.id], True)
            _say("✔ 已标记为已读（--peek 可只看不改）" if not was_seen else "✔ 该邮件本来就是已读")
        return 0
    finally:
        try:
            client.logout()
        except Exception:
            pass


def cmd_seen(args: argparse.Namespace) -> int:
    creds = _load_credentials()
    client = _connect(creds)
    try:
        targets: list[str] = []
        if args.all:
            if not args.confirm:
                raise SystemExit("--all 会一次性改整箱状态，确认请加 --confirm")
            status, data = client.search(None, "UNSEEN" if args.unseen is False else "ALL")
            targets = [x.decode() for x in (data[0].split() if data and data[0] else [])]
        elif args.sender:
            status, data = client.search(None, "FROM", f'"{args.sender}"')
            targets = [x.decode() for x in (data[0].split() if data and data[0] else [])]
        elif args.ids:
            targets = args.ids
        else:
            raise SystemExit("需要指定 id，或 --sender，或 --all --confirm")

        if not targets:
            _say("(没有命中任何邮件)")
            return 0
        _mark_seen(client, targets, seen=not args.unseen)
        verb = "未读" if args.unseen else "已读"
        _say(f"✔ 已把 {len(targets)} 封标为{verb}: {', '.join(targets[:20])}{' …' if len(targets) > 20 else ''}")
        return 0
    finally:
        try:
            client.logout()
        except Exception:
            pass


def cmd_reply(args: argparse.Namespace) -> int:
    creds = _load_credentials()
    client = _connect(creds)
    try:
        raw, was_seen = _fetch_header_part(client, args.id)
        original = email.message_from_bytes(raw)
        full_original = email.message_from_bytes(_fetch_raw(client, args.id))

        orig_message_id = (original.get("Message-ID") or "").strip()
        if not orig_message_id:
            raise SystemExit("原邮件没有 Message-ID，无法建立线程；请改用 send")

        references = (original.get("References") or "").split()
        if orig_message_id not in references:
            references.append(orig_message_id)

        subject = _apply_subject_prefix(decode_header_str(original.get("Subject")), args.prefix)
        to_list, cc_list = _recipients(original, args.all, args.to)
        if not to_list:
            raise SystemExit("无法推导收件人，请用 --to 指定")

        text = _read_body(args)
        # Layout mirrors the UHH webmail: body, signature, then the quoted block.
        parts = [text]
        if not args.no_sign:
            parts.append(DEFAULT_SIGNATURE)
        if args.quote:
            parts.append(_quote_block(full_original))
        text = "\n\n".join(parts)

        msg = _compose(
            to_list=to_list,
            cc_list=cc_list,
            subject=subject,
            text=text,
            in_reply_to=orig_message_id,
            references=" ".join(references),
            thread_topic=_base_subject(decode_header_str(original.get("Subject"))),
            thread_index=(original.get("Thread-Index") or "").strip() or None,
        )

        _print_preview(msg)
        if not args.confirm:
            _say("⏸ DRY RUN：未发送。确认无误后加 --confirm 再执行。")
            return 0

        _send_message(creds, msg)
        _say(f"✔ 已发送 → {', '.join(to_list + cc_list)}")
        _say(f"✔ Sent 副本：{_append_to_sent(creds, msg.as_bytes())}")
        if not was_seen and not args.no_mark_read:
            _mark_seen(client, [args.id], True)
            _say("✔ 原邮件已标记为已读")
        return 0
    finally:
        try:
            client.logout()
        except Exception:
            pass


def cmd_send(args: argparse.Namespace) -> int:
    creds = _load_credentials()
    text = _apply_signature(_read_body(args), not args.no_sign)
    to_list = [a.strip() for a in args.to.split(",") if a.strip()]
    cc_list = [a.strip() for a in (args.cc or "").split(",") if a.strip()]
    msg = _compose(
        to_list=to_list,
        cc_list=cc_list,
        subject=_apply_subject_prefix(args.subject, args.prefix),
        text=text,
    )
    _print_preview(msg)
    if not args.confirm:
        _say("⏸ DRY RUN：未发送。确认无误后加 --confirm 再执行。")
        return 0
    _send_message(creds, msg)
    _say(f"✔ 已发送 → {', '.join(to_list + cc_list)}")
    _say(f"✔ Sent 副本：{_append_to_sent(creds, msg.as_bytes())}")
    return 0


# --- CLI -------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mail", description="UHH mailbox CLI (IMAP read + SMTP send)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出邮件（只读表头，不改状态）")
    p_list.add_argument("--unread", action="store_true", help="只看未读")
    p_list.add_argument("--from", dest="sender", help="按发件人过滤（模糊匹配）")
    p_list.add_argument("--limit", type=int, default=15, help="最多显示多少封（默认 15，取最新）")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="读一封邮件")
    p_show.add_argument("id")
    p_show.add_argument("--peek", action="store_true", help="只读预览，不改已读状态")
    p_show.set_defaults(func=cmd_show)

    p_seen = sub.add_parser("seen", help="批量/指定标记已读")
    p_seen.add_argument("ids", nargs="*", help="邮件 id（可多个）")
    p_seen.add_argument("--sender", help="把该发件人的邮件标为已读")
    p_seen.add_argument("--all", action="store_true", help="整箱操作（必须配 --confirm）")
    p_seen.add_argument("--unseen", action="store_true", help="反向：标为未读")
    p_seen.add_argument("--confirm", action="store_true", help="确认执行批量操作")
    p_seen.set_defaults(func=cmd_seen)

    p_reply = sub.add_parser("reply", help="回复一封邮件（默认 dry run）")
    p_reply.add_argument("id")
    p_reply.add_argument("--body")
    p_reply.add_argument("--body-file")
    p_reply.add_argument("--all", action="store_true", help="回复全部（带 To+Cc）")
    p_reply.add_argument("--to", help="强制指定收件人（逗号分隔）")
    p_reply.add_argument("--quote", action="store_true", help="引用原文")
    p_reply.add_argument("--no-sign", action="store_true", help="不加默认签名")
    p_reply.add_argument("--no-mark-read", action="store_true", help="发送后不把原信标为已读")
    p_reply.add_argument("--prefix", default=SUBJECT_PREFIX, help="主题前缀（默认 'AW: '）")
    p_reply.add_argument("--confirm", action="store_true", help="真的发出去")
    p_reply.set_defaults(func=cmd_reply)

    p_send = sub.add_parser("send", help="发一封新邮件（默认 dry run）")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--cc")
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body")
    p_send.add_argument("--body-file")
    p_send.add_argument("--no-sign", action="store_true")
    p_send.add_argument("--prefix", default=SUBJECT_PREFIX)
    p_send.add_argument("--confirm", action="store_true")
    p_send.set_defaults(func=cmd_send)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
