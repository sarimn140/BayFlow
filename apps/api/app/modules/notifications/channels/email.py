"""The e-mail channel (P1, D26; spec 01 "E-mail", spec 07 e-mail variables).

Only `ESTIMATE_SENT` and `VEHICLE_READY` are e-mailed, to the booking's customer, from after-commit
callbacks: one attempt, at most 10 s, best effort. `EMAIL_PROVIDER` picks the adapter:

- `none` (default): `NoopEmailSender`, nothing is sent;
- `smtp` (local Mailpit): `SmtpEmailSender`, `smtplib` in a worker thread; STARTTLS (certificate
  verified) and login only when `SMTP_USER` is set, since Mailpit needs neither;
- `http` (production; Railway Hobby blocks outbound SMTP): `HttpEmailSender`, Resend's
  `POST https://api.resend.com/emails` with `Authorization: Bearer <EMAIL_API_KEY>`, a JSON body
  `{from, to, subject, text}` and `Idempotency-Key: <notification id>` (kept 24 h by Resend, so a
  retried send never duplicates).

`deliver()` skips `none` and reserved/test domains (`.test`, `.example`, `.invalid`, `.localhost`,
plus RFC 2606's `example.com/.net/.org`; `app.shared.email`) and logs every outcome with the
notification id, **never the address**: failures are logged by exception type (and HTTP status)
only, because an SMTP error message can quote the recipient. It never raises.

One sender per app, built on first use from `state.settings` by `get_email_sender(state)` and
stored at `state.email_sender` (D90); there is no module-level state.
"""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid, parseaddr
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

import httpx
from starlette.datastructures import State

from app.core.config import Settings
from app.shared.clock import utcnow
from app.shared.email import is_reserved_domain

logger = logging.getLogger(__name__)

EMAIL_TIMEOUT_SECONDS = 10.0
RESEND_EMAILS_URL = "https://api.resend.com/emails"

type ProviderName = Literal["none", "smtp", "http"]


@dataclass(frozen=True, slots=True, kw_only=True)
class OutgoingEmail:
    """One plain-text message to one recipient."""

    to: str
    subject: str
    text: str
    idempotency_key: str  # the notification id: the HTTPS API never sends one twice


@runtime_checkable
class EmailSender(Protocol):
    """An `EMAIL_PROVIDER` adapter. `send` raises on failure; `deliver()` catches and logs."""

    @property
    def provider(self) -> ProviderName: ...

    async def send(self, email: OutgoingEmail) -> None: ...


class NoopEmailSender:
    """`EMAIL_PROVIDER=none`: e-mail is off (`deliver()` never calls `send`)."""

    @property
    def provider(self) -> ProviderName:
        return "none"

    async def send(self, email: OutgoingEmail) -> None:
        return None


class SmtpEmailSender:
    """`EMAIL_PROVIDER=smtp`: one SMTP session per message, run in a worker thread so no blocking
    I/O (connect, DNS, TLS) touches the event loop."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        timeout_seconds: float = EMAIL_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password or ""
        self._sender = sender
        self._timeout_seconds = timeout_seconds

    @property
    def provider(self) -> ProviderName:
        return "smtp"

    def build_message(self, email: OutgoingEmail) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Date"] = format_datetime(utcnow())
        # The sender's domain; never the local hostname (make_msgid would resolve it: DNS).
        _, at, domain = parseaddr(self._sender)[1].rpartition("@")
        message["Message-ID"] = make_msgid(domain=domain if at and domain else "localhost")
        message.set_content(email.text)
        return message

    def _send_blocking(self, email: OutgoingEmail) -> None:
        message = self.build_message(email)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as client:
            if self._username:
                client.starttls(context=ssl.create_default_context())
                client.login(self._username, self._password)
            client.send_message(message)

    async def send(self, email: OutgoingEmail) -> None:
        async with asyncio.timeout(self._timeout_seconds):
            await asyncio.to_thread(self._send_blocking, email)


class HttpEmailSender:
    """`EMAIL_PROVIDER=http`: Resend's `POST /emails`. `transport` lets tests use
    `httpx.MockTransport`; production uses httpx's default transport."""

    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = EMAIL_TIMEOUT_SECONDS,
        url: str = RESEND_EMAILS_URL,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._url = url

    @property
    def provider(self) -> ProviderName:
        return "http"

    async def send(self, email: OutgoingEmail) -> None:
        async with (
            asyncio.timeout(self._timeout_seconds),
            httpx.AsyncClient(transport=self._transport, timeout=self._timeout_seconds) as client,
        ):
            response = await client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Idempotency-Key": email.idempotency_key,
                },
                json={
                    "from": self._sender,
                    "to": [email.to],
                    "subject": email.subject,
                    "text": email.text,
                },
            )
        response.raise_for_status()  # any non-2xx is a failure (Resend answers 200 {"id"})


def build_email_sender(settings: Settings) -> EmailSender:
    """The adapter for `EMAIL_PROVIDER` (the settings are validated at start-up, spec 01)."""
    if settings.email_provider == "smtp":
        if not settings.smtp_host:
            msg = "EMAIL_PROVIDER=smtp requires SMTP_HOST"
            raise ValueError(msg)
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_pass.get_secret_value() if settings.smtp_pass else None,
            sender=settings.smtp_from,
        )
    if settings.email_provider == "http":
        if settings.email_api_key is None:
            msg = "EMAIL_PROVIDER=http requires EMAIL_API_KEY"
            raise ValueError(msg)
        return HttpEmailSender(
            api_key=settings.email_api_key.get_secret_value(), sender=settings.smtp_from
        )
    return NoopEmailSender()


def get_email_sender(state: State) -> EmailSender:
    """The app's sender, built on first use from `state.settings` and stored at
    `state.email_sender` (D90). There is no `await` between the check and the assignment."""
    existing = getattr(state, "email_sender", None)
    if existing is not None:
        if not isinstance(existing, EmailSender):
            msg = "app.state.email_sender is not an EmailSender"
            raise TypeError(msg)
        return existing
    settings = getattr(state, "settings", None)
    if not isinstance(settings, Settings):
        msg = "app.state.settings is not set: build the app with create_app()"
        raise RuntimeError(msg)
    sender = build_email_sender(settings)
    state.email_sender = sender
    return sender


def is_reserved_address(email: str) -> bool:
    """True for an address on a reserved/test domain, which is never e-mailed (D26)."""
    return is_reserved_domain(email)


class Delivery(StrEnum):
    """What `deliver()` did with one e-mail."""

    SENT = "SENT"
    SKIPPED_DISABLED = "SKIPPED_DISABLED"
    SKIPPED_RESERVED = "SKIPPED_RESERVED"
    SKIPPED_NO_ADDRESS = "SKIPPED_NO_ADDRESS"
    FAILED = "FAILED"


def log_skipped(notification_id: UUID, outcome: Delivery) -> Delivery:
    """Log a skipped e-mail with its notification id (never the address)."""
    logger.info(
        "email.skipped", extra={"notification_id": str(notification_id), "reason": str(outcome)}
    )
    return outcome


async def deliver(sender: EmailSender, email: OutgoingEmail, *, notification_id: UUID) -> Delivery:
    """One best-effort attempt: skip `none` and reserved domains, else send. Never raises."""
    if sender.provider == "none":
        return log_skipped(notification_id, Delivery.SKIPPED_DISABLED)
    if is_reserved_address(email.to):
        return log_skipped(notification_id, Delivery.SKIPPED_RESERVED)
    try:
        await sender.send(email)
    except Exception as exc:
        fields = {
            "notification_id": str(notification_id),
            "provider": sender.provider,
            "error": type(exc).__name__,
        }
        if isinstance(exc, httpx.HTTPStatusError):
            fields["status"] = str(exc.response.status_code)
        logger.warning("email.failed", extra=fields)
        return Delivery.FAILED
    logger.info(
        "email.sent", extra={"notification_id": str(notification_id), "provider": sender.provider}
    )
    return Delivery.SENT
