"""The e-mail channel (D26): NOT-19 (the `http` adapter's request through `httpx.MockTransport`:
URL, Bearer key, JSON body, `Idempotency-Key`; a reserved domain makes no request), the `smtp`
adapter against a fake `smtplib.SMTP`, one best-effort attempt within 10 s, `none`, the adapter
choice from the settings, D90's per-app sender, and logs that never carry an address."""

import asyncio
import json
import logging
import smtplib
import ssl
import threading
import uuid
from typing import Any, ClassVar

import httpx
import pytest
from pydantic import SecretStr
from starlette.datastructures import State

from app.core.config import Settings
from app.modules.notifications.channels import email as channel
from app.modules.notifications.channels.email import (
    EMAIL_TIMEOUT_SECONDS,
    RESEND_EMAILS_URL,
    Delivery,
    HttpEmailSender,
    NoopEmailSender,
    OutgoingEmail,
    SmtpEmailSender,
    build_email_sender,
    deliver,
    get_email_sender,
    is_reserved_address,
)
from tests.conftest import make_settings

NOTIFICATION = uuid.UUID("0a8f6b9e-4c1d-4e2a-9b3c-5d6e7f8a9b0c")
ADDRESS = "ahmed@mail.com"
EMAIL = OutgoingEmail(
    to=ADDRESS,
    subject="Your vehicle is ready for pick-up",
    text="Booking BF-7KQ2MX at Lahore Auto Care is ready for pick-up.\n\nOpen in BayFlow: x",
    idempotency_key=str(NOTIFICATION),
)


def no_address_in(caplog: pytest.LogCaptureFixture) -> None:
    for record in caplog.records:
        assert ADDRESS not in record.getMessage() + json.dumps(vars(record), default=str)


class Outbox:
    def __init__(self, response: httpx.Response | Exception | None = None) -> None:
        self.response = response or httpx.Response(200, json={"id": "re_123"})
        self.requests: list[httpx.Request] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def http_sender(outbox: Outbox, **kwargs: Any) -> HttpEmailSender:
    return HttpEmailSender(
        api_key="re_secret_key",
        sender="BayFlow <no-reply@bayflow.app>",
        transport=httpx.MockTransport(outbox.handler),
        **kwargs,
    )


# --- NOT-19: the http adapter (Resend) ------------------------------------------------------------


async def test_not19_http_request_shape(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    outbox = Outbox()

    result = await deliver(http_sender(outbox), EMAIL, notification_id=NOTIFICATION)

    assert result == Delivery.SENT
    [request] = outbox.requests
    assert request.method == "POST"
    assert str(request.url) == RESEND_EMAILS_URL == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_secret_key"
    assert request.headers["idempotency-key"] == str(NOTIFICATION)
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "from": "BayFlow <no-reply@bayflow.app>",
        "to": [ADDRESS],
        "subject": EMAIL.subject,
        "text": EMAIL.text,
    }
    [sent] = [r for r in caplog.records if r.getMessage() == "email.sent"]
    assert (sent.notification_id, sent.provider) == (str(NOTIFICATION), "http")
    no_address_in(caplog)


@pytest.mark.parametrize(
    "address",
    [
        "ayesha.customer@bayflow.test",
        "someone@shop.example",
        "x@nowhere.invalid",
        "root@localhost",
        "a@b.LOCALHOST",
        "a@b.test.",
        "demo@example.com",
        "demo@mail.example.org",
    ],
)
async def test_not19_a_reserved_domain_makes_no_request(
    address: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    outbox = Outbox()
    email = OutgoingEmail(to=address, subject="s", text="t", idempotency_key="k")

    result = await deliver(http_sender(outbox), email, notification_id=NOTIFICATION)

    assert result == Delivery.SKIPPED_RESERVED
    assert outbox.requests == []
    [skipped] = [r for r in caplog.records if r.getMessage() == "email.skipped"]
    assert (skipped.notification_id, skipped.reason) == (str(NOTIFICATION), "SKIPPED_RESERVED")
    for record in caplog.records:
        assert address not in record.getMessage() + json.dumps(vars(record), default=str)


@pytest.mark.parametrize(
    ("address", "reserved"),
    [
        ("ahmed@mail.com", False),
        ("owner@lahoreautocare.pk", False),
        ("x@test.com", False),  # only the last label counts
        ("x@example.co", False),
        ("x@bayflow.test", True),
        ("x@sub.domain.example", True),
        ("x@domain.invalid", True),
        ("x@localhost", True),
        ("x@example.net", True),
    ],
)
def test_is_reserved_address(address: str, reserved: bool) -> None:
    assert is_reserved_address(address) is reserved


@pytest.mark.parametrize("status", [400, 401, 403, 422, 429, 500, 503, 302])
async def test_any_non_2xx_answer_is_a_logged_failure(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    outbox = Outbox(httpx.Response(status, json={"message": f"refused {ADDRESS}"}))

    result = await deliver(http_sender(outbox), EMAIL, notification_id=NOTIFICATION)

    assert result == Delivery.FAILED
    assert len(outbox.requests) == 1  # one attempt, no retry
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert (failure.status, failure.error, failure.provider) == (
        str(status),
        "HTTPStatusError",
        "http",
    )
    no_address_in(caplog)


async def test_a_network_error_is_a_logged_failure(caplog: pytest.LogCaptureFixture) -> None:
    outbox = Outbox(httpx.ConnectError(f"cannot reach the API for {ADDRESS}"))
    assert await deliver(http_sender(outbox), EMAIL, notification_id=NOTIFICATION) == (
        Delivery.FAILED
    )
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert failure.error == "ConnectError"
    no_address_in(caplog)


async def test_the_http_send_gives_up_after_its_timeout(caplog: pytest.LogCaptureFixture) -> None:
    class Slow(Outbox):
        async def handler(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            await asyncio.sleep(3600)
            raise AssertionError  # pragma: no cover

    outbox = Slow()
    async with asyncio.timeout(2):
        result = await deliver(
            http_sender(outbox, timeout_seconds=0.05), EMAIL, notification_id=NOTIFICATION
        )
    assert result == Delivery.FAILED
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert failure.error == "TimeoutError"


def test_the_e_mail_timeout_is_ten_seconds() -> None:
    assert EMAIL_TIMEOUT_SECONDS == 10.0


# --- none -----------------------------------------------------------------------------------------


async def test_provider_none_never_sends(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)

    class Spy(NoopEmailSender):
        async def send(self, email: OutgoingEmail) -> None:
            pytest.fail("EMAIL_PROVIDER=none must not send")

    assert await deliver(Spy(), EMAIL, notification_id=NOTIFICATION) == Delivery.SKIPPED_DISABLED
    [skipped] = [r for r in caplog.records if r.getMessage() == "email.skipped"]
    assert skipped.reason == "SKIPPED_DISABLED"
    await NoopEmailSender().send(EMAIL)  # harmless when called directly


# --- smtp -----------------------------------------------------------------------------------------


class FakeSmtp:
    sessions: ClassVar[list["FakeSmtp"]] = []
    refuse: ClassVar[bool] = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[Any] = []
        self.thread = threading.current_thread()
        FakeSmtp.sessions.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *args: object) -> None:
        self.calls.append("quit")

    def starttls(self, *, context: ssl.SSLContext) -> None:
        self.calls.append(("starttls", context.verify_mode, context.check_hostname))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user, password))

    def send_message(self, message: Any) -> None:
        if FakeSmtp.refuse:
            raise smtplib.SMTPRecipientsRefused({ADDRESS: (550, b"no such user")})
        self.calls.append(("send", message))


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSmtp]:
    FakeSmtp.sessions = []
    FakeSmtp.refuse = False
    monkeypatch.setattr(channel.smtplib, "SMTP", FakeSmtp)
    return FakeSmtp


def smtp_sender(**kwargs: Any) -> SmtpEmailSender:
    values: dict[str, Any] = {
        "host": "localhost",
        "port": 1025,
        "username": None,
        "password": None,
        "sender": "BayFlow <no-reply@bayflow.app>",
    }
    values.update(kwargs)
    return SmtpEmailSender(**values)


async def test_smtp_without_a_user_skips_starttls_and_login(fake_smtp: type[FakeSmtp]) -> None:
    assert await deliver(smtp_sender(), EMAIL, notification_id=NOTIFICATION) == Delivery.SENT

    [session] = fake_smtp.sessions
    assert (session.host, session.port, session.timeout) == ("localhost", 1025, 10.0)
    assert session.thread is not threading.main_thread()  # asyncio.to_thread: no blocking I/O
    send, quit_ = session.calls
    assert (send[0], quit_) == ("send", "quit")
    message = send[1]
    assert message["From"] == "BayFlow <no-reply@bayflow.app>"
    assert message["To"] == ADDRESS
    assert message["Subject"] == EMAIL.subject
    assert message["Date"]
    assert message["Message-ID"].endswith("@bayflow.app>")
    assert message.get_content() == EMAIL.text + "\n"


async def test_smtp_with_a_user_uses_verified_starttls_then_login(
    fake_smtp: type[FakeSmtp],
) -> None:
    sender = smtp_sender(host="smtp.mail.example", port=587, username="bayflow", password="pw")

    assert await deliver(sender, EMAIL, notification_id=NOTIFICATION) == Delivery.SENT

    [session] = fake_smtp.sessions
    starttls, login, send, quit_ = session.calls
    assert starttls == ("starttls", ssl.CERT_REQUIRED, True)  # certificate verified
    assert login == ("login", "bayflow", "pw")
    assert send[0] == "send"
    assert quit_ == "quit"


async def test_an_smtp_refusal_is_logged_without_the_address(
    fake_smtp: type[FakeSmtp], caplog: pytest.LogCaptureFixture
) -> None:
    fake_smtp.refuse = True
    assert await deliver(smtp_sender(), EMAIL, notification_id=NOTIFICATION) == Delivery.FAILED
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert (failure.error, failure.provider) == ("SMTPRecipientsRefused", "smtp")
    no_address_in(caplog)


async def test_an_unreachable_smtp_server_is_a_logged_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError

    monkeypatch.setattr(channel.smtplib, "SMTP", refuse)
    assert await deliver(smtp_sender(), EMAIL, notification_id=NOTIFICATION) == Delivery.FAILED
    [failure] = [r for r in caplog.records if r.getMessage() == "email.failed"]
    assert failure.error == "ConnectionRefusedError"


def test_the_message_id_domain_comes_from_the_sender_address() -> None:
    for sender, domain in (
        ("no-reply@bayflow.test", "@bayflow.test>"),
        ("BayFlow <hello@shop.pk>", "@shop.pk>"),
        ("not-an-address", "@localhost>"),
    ):
        message = smtp_sender(sender=sender).build_message(EMAIL)
        assert message["Message-ID"].endswith(domain)


async def test_an_unusable_sender_address_is_a_logged_failure(
    fake_smtp: type[FakeSmtp], caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed `SMTP_FROM` makes every message fail (logged), never the action."""
    sender = smtp_sender(sender="broken@")
    assert await deliver(sender, EMAIL, notification_id=NOTIFICATION) == Delivery.FAILED
    assert fake_smtp.sessions == []  # refused before any connection
    no_address_in(caplog)


# --- The adapter per EMAIL_PROVIDER, one per app (D90) --------------------------------------------


def test_build_email_sender_follows_the_provider() -> None:
    assert isinstance(build_email_sender(make_settings()), NoopEmailSender)
    smtp = build_email_sender(
        make_settings(
            email_provider="smtp",
            smtp_host="mailpit",
            smtp_port=1025,
            smtp_user="u",
            smtp_pass="p",
        )
    )
    assert isinstance(smtp, SmtpEmailSender)
    assert smtp.provider == "smtp"
    http = build_email_sender(make_settings(email_provider="http", email_api_key="re_key"))
    assert isinstance(http, HttpEmailSender)
    assert http.provider == "http"


def test_build_email_sender_refuses_an_incomplete_configuration() -> None:
    valid = make_settings()
    no_host = Settings.model_construct(
        **{**dict(valid), "email_provider": "smtp", "smtp_host": None}
    )
    no_key = Settings.model_construct(
        **{**dict(valid), "email_provider": "http", "email_api_key": None}
    )
    with pytest.raises(ValueError, match="SMTP_HOST"):
        build_email_sender(no_host)
    with pytest.raises(ValueError, match="EMAIL_API_KEY"):
        build_email_sender(no_key)


async def test_the_http_key_is_read_from_the_secret_setting() -> None:
    sender = build_email_sender(
        make_settings(email_provider="http", email_api_key=SecretStr("re_k"))
    )
    assert isinstance(sender, HttpEmailSender)


def test_get_email_sender_is_built_once_per_app_from_its_settings() -> None:
    state = State()
    state.settings = make_settings(email_provider="http", email_api_key="re_key")
    sender = get_email_sender(state)
    assert isinstance(sender, HttpEmailSender)
    assert state.email_sender is sender
    assert get_email_sender(state) is sender
    other = State()
    other.settings = make_settings()
    assert isinstance(get_email_sender(other), NoopEmailSender)


def test_get_email_sender_needs_the_app_settings() -> None:
    with pytest.raises(RuntimeError, match="settings"):
        get_email_sender(State())
    state = State()
    state.email_sender = object()
    with pytest.raises(TypeError, match="EmailSender"):
        get_email_sender(state)
