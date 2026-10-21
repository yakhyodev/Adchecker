import asyncio
import codecs
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import warnings

from dotenv import dotenv_values
import pytest
from telethon.crypto import AuthKey
from telethon.sessions import StringSession
from telethon.errors import (
    ApiIdInvalidError, AuthTokenExpiredError, FloodWaitError,
    PasswordHashInvalidError, PhoneCodeExpiredError, PhoneCodeInvalidError,
    PhoneNumberBannedError, PhoneNumberInvalidError, SessionPasswordNeededError,
)
from telethon.tl.types.auth import SentCode, SentCodeTypeApp

from scripts import telegram_login as login


@pytest.fixture
def login_setup(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        '# Keep all existing settings\nTELEGRAM_API_ID=7654321\n'
        'TELEGRAM_API_HASH="synthetic_api_hash"\nBOT_TOKEN="keep_this_token"\n'
        'TELEGRAM_SESSION_STRING="OLD_SESSION_SECRET"\n'
        'DATABASE_URL="keep_this_database"\n', encoding="utf-8",
    )
    session = StringSession()
    session.set_dc(2, "127.0.0.1", 443)
    session.auth_key = AuthKey(bytes(range(256)))
    qr = SimpleNamespace(url="tg://login?token=TEST_QR_TOKEN", wait=AsyncMock(), recreate=AsyncMock())
    client = SimpleNamespace(
        connect=AsyncMock(), disconnect=AsyncMock(),
        is_user_authorized=AsyncMock(side_effect=[False, True]),
        session=session, qr_login=AsyncMock(return_value=qr),
        send_code_request=AsyncMock(return_value=SentCode(
            type=SentCodeTypeApp(length=5), phone_code_hash="synthetic_code_hash",
        )),
        sign_in=AsyncMock(),
    )
    constructor = Mock(return_value=client)
    monkeypatch.setattr(login, "TelegramClient", constructor)
    renders = []
    monkeypatch.setattr(login, "render_qr", renders.append)
    return SimpleNamespace(env=env, client=client, qr=qr, renders=renders, constructor=constructor)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["1", "2"])
@pytest.mark.parametrize("two_factor", [False, True])
async def test_phone_and_qr_save_real_string_session_without_exposing_it(
    monkeypatch, capsys, login_setup, mode, two_factor
):
    setup = login_setup
    before = setup.env.read_bytes()
    replies = iter([mode, "+998000000000", "12345"] if mode == "1" else [mode])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    password_input = Mock(return_value="synthetic_2fa_password")
    monkeypatch.setattr(login.getpass, "getpass", password_input)
    if two_factor:
        if mode == "1":
            setup.client.sign_in.side_effect = [SessionPasswordNeededError(None), None]
        else:
            setup.qr.wait.side_effect = SessionPasswordNeededError(None)
    assert await login.main(setup.env) == 0
    secret = setup.client.session.save()
    expected = before.replace(b'"OLD_SESSION_SECRET"', f'"{secret}"'.encode())
    assert setup.env.read_bytes() == expected
    parsed = dotenv_values(setup.env, interpolate=False)
    restored = StringSession(parsed[login.SESSION_KEY])
    assert restored.auth_key.key == setup.client.session.auth_key.key
    stdout = capsys.readouterr()
    for value in (secret, "OLD_SESSION_SECRET", "synthetic_api_hash", "synthetic_2fa_password"):
        assert value not in stdout.out + stdout.err
    assert password_input.call_count == int(two_factor)
    setup.client.disconnect.assert_awaited_once()
    assert isinstance(setup.constructor.call_args.args[0], StringSession)
    if mode == "2":
        setup.client.qr_login.assert_awaited_once()
        setup.client.send_code_request.assert_not_awaited()
        assert setup.renders == [setup.qr.url]
    else:
        setup.client.qr_login.assert_not_awaited()
        assert "Kod yetkazish turi: SentCodeTypeApp" in stdout.out
        assert setup.client.sign_in.await_args_list[0].kwargs["phone_code_hash"] == "synthetic_code_hash"


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [asyncio.TimeoutError(), AuthTokenExpiredError(None)])
async def test_expired_qr_can_be_recreated(monkeypatch, login_setup, expiry):
    setup = login_setup
    setup.qr.wait.side_effect = [expiry, None]
    async def recreate():
        setup.qr.url = "tg://login?token=RENEWED_TEST_QR"
    setup.qr.recreate.side_effect = recreate
    replies = iter(["2", "invalid", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    assert await login.main(setup.env) == 0
    setup.qr.recreate.assert_awaited_once()
    assert setup.renders == ["tg://login?token=TEST_QR_TOKEN", "tg://login?token=RENEWED_TEST_QR"]


@pytest.mark.asyncio
async def test_expired_qr_can_be_cancelled_without_changing_env(monkeypatch, login_setup):
    setup = login_setup
    original = setup.env.read_bytes()
    setup.qr.wait.side_effect = asyncio.TimeoutError()
    replies = iter(["2", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    assert await login.main(setup.env) == 1
    setup.qr.recreate.assert_not_awaited()
    assert setup.env.read_bytes() == original
    setup.client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_qr_wait_is_running_before_display_and_is_cleaned_up(monkeypatch, login_setup):
    setup = login_setup
    listening = asyncio.Event()
    removed = asyncio.Event()
    async def wait():
        listening.set()
        try:
            await asyncio.Event().wait()
        finally:
            removed.set()
    setup.qr.wait.side_effect = wait
    def broken_terminal(url):
        assert listening.is_set()
        raise OSError("terminal failed")
    monkeypatch.setattr(login, "render_qr", broken_terminal)
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    original = setup.env.read_bytes()
    assert await login.main(setup.env) == 1
    assert removed.is_set()
    assert setup.env.read_bytes() == original
    setup.client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["1", "2"])
async def test_wrong_2fa_password_can_be_retried(monkeypatch, login_setup, mode):
    setup = login_setup
    replies = iter([mode, "+998000000000", "12345"] if mode == "1" else [mode])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    monkeypatch.setattr(login.getpass, "getpass", Mock(side_effect=["wrong", "correct"]))
    password_error = PasswordHashInvalidError(None)
    if mode == "1":
        setup.client.sign_in.side_effect = [SessionPasswordNeededError(None), password_error, None]
    else:
        setup.qr.wait.side_effect = SessionPasswordNeededError(None)
        setup.client.sign_in.side_effect = [password_error, None]
    assert await login.main(setup.env) == 0


@pytest.mark.asyncio
async def test_2fa_exhaustion_keeps_existing_session(monkeypatch, login_setup):
    setup = login_setup
    original = setup.env.read_bytes()
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    monkeypatch.setattr(login.getpass, "getpass", lambda prompt: "wrong")
    setup.qr.wait.side_effect = SessionPasswordNeededError(None)
    setup.client.sign_in.side_effect = PasswordHashInvalidError(None)
    assert await login.main(setup.env) == 1
    assert setup.client.sign_in.await_count == 3
    assert setup.env.read_bytes() == original


@pytest.mark.asyncio
async def test_invalid_phone_code_is_retried_without_resending(monkeypatch, login_setup):
    setup = login_setup
    replies = iter(["1", "+998000000000", "wrong", "12345"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    setup.client.sign_in.side_effect = [PhoneCodeInvalidError(None), None]
    assert await login.main(setup.env) == 0
    setup.client.send_code_request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [
    (PhoneCodeExpiredError(None), "kodi eskirgan"),
    (PhoneNumberInvalidError(None), "Telefon raqami noto'g'ri"),
    (PhoneNumberBannedError(None), "bloklangan"),
    (ApiIdInvalidError(None), "API_ID yoki API_HASH noto'g'ri"),
    (ConnectionError("SESSION_SECRET"), "aloqa uzildi"),
    (RuntimeError("SESSION_SECRET"), "Login bajarilmadi"),
])
async def test_errors_are_uzbek_do_not_leak_or_modify_env(
    monkeypatch, capsys, login_setup, error, expected
):
    setup = login_setup
    original = setup.env.read_bytes()
    replies = iter(["1", "+998000000000"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(replies))
    setup.client.send_code_request.side_effect = error
    assert await login.main(setup.env) == 1
    output = capsys.readouterr()
    assert expected in output.out
    assert "SESSION_SECRET" not in output.out + output.err
    assert setup.env.read_bytes() == original
    setup.client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_flood_wait_is_reported_without_sleeping(monkeypatch, capsys, login_setup):
    setup = login_setup
    error = FloodWaitError(None)
    error.seconds = 42
    setup.client.connect.side_effect = error
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    assert await login.main(setup.env) == 1
    assert "42 soniyadan" in capsys.readouterr().out
    setup.client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_insecure_getpass_fallback_is_refused(monkeypatch, capsys, login_setup):
    setup = login_setup
    original = setup.env.read_bytes()
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    def insecure_getpass(prompt):
        warnings.warn("visible input", login.getpass.GetPassWarning)
        pytest.fail("Must not fall back to visible password input")
    monkeypatch.setattr(login.getpass, "getpass", insecure_getpass)
    setup.qr.wait.side_effect = SessionPasswordNeededError(None)
    assert await login.main(setup.env) == 1
    assert "parolni yashira olmadi" in capsys.readouterr().out
    assert setup.env.read_bytes() == original


@pytest.mark.asyncio
async def test_missing_env_fails_before_network(monkeypatch, login_setup):
    setup = login_setup
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    assert await login.main(setup.env.parent / "missing.env") == 1
    setup.constructor.assert_not_called()


@pytest.mark.parametrize("original,expected", [
    (b'A="keep"\nTELEGRAM_SESSION_STRING="old"\nB=keep\n',
     b'A="keep"\nTELEGRAM_SESSION_STRING="NEW_SESSION"\nB=keep\n'),
    (codecs.BOM_UTF8 + b'# keep\r\nexport TELEGRAM_SESSION_STRING = old\r\nA=keep\r\n',
     codecs.BOM_UTF8 + b'# keep\r\nTELEGRAM_SESSION_STRING="NEW_SESSION"\r\nA=keep\r\n'),
    (b'TELEGRAM_SESSION_STRING=old\nA=keep\nTELEGRAM_SESSION_STRING=duplicate',
     b'TELEGRAM_SESSION_STRING="NEW_SESSION"\nA=keep\nTELEGRAM_SESSION_STRING="NEW_SESSION"'),
    (b'A=keep', b'A=keep\nTELEGRAM_SESSION_STRING="NEW_SESSION"\n'),
    (b'', b'TELEGRAM_SESSION_STRING="NEW_SESSION"\n'),
    (b'OTHER="one\nTELEGRAM_SESSION_STRING=fake\nthree"\nTELEGRAM_SESSION_STRING="old"\n',
     b'OTHER="one\nTELEGRAM_SESSION_STRING=fake\nthree"\nTELEGRAM_SESSION_STRING="NEW_SESSION"\n'),
])
def test_env_update_preserves_unrelated_bytes_and_inode(tmp_path, original, expected):
    env = tmp_path / ".env"
    env.write_bytes(original)
    inode = env.stat().st_ino
    with env.open("rb") as mounted_file:
        login.update_session_in_env(env, "NEW_SESSION")
        assert mounted_file.read() == expected
    assert env.read_bytes() == expected
    assert env.stat().st_ino == inode


def test_malformed_env_is_never_overwritten(tmp_path):
    env = tmp_path / ".env"
    original = b'TELEGRAM_SESSION_STRING=old\nOTHER="unclosed\n'
    env.write_bytes(original)
    with pytest.raises(ValueError):
        login.update_session_in_env(env, "NEW_SESSION")
    assert env.read_bytes() == original


def test_qr_renders_terminal_blocks_without_printing_raw_token(capsys):
    # Use the actual encoder, rather than mocking the QR renderer.
    login.render_qr("tg://login?token=SYNTHETIC_QR_TEST_TOKEN")
    output = capsys.readouterr().out
    assert "█" in output
    assert "tg://" not in output
    assert "SYNTHETIC_QR_TEST_TOKEN" not in output


@pytest.mark.asyncio
async def test_cancel_during_qr_wait_disconnects_without_saving(monkeypatch, login_setup):
    setup = login_setup
    original = setup.env.read_bytes()
    listening = asyncio.Event()
    removed = asyncio.Event()
    async def wait():
        listening.set()
        try:
            await asyncio.Event().wait()
        finally:
            removed.set()
    setup.qr.wait.side_effect = wait
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    task = asyncio.create_task(login.main(setup.env))
    await listening.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert removed.is_set()
    assert setup.env.read_bytes() == original
    setup.client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_env_write_failure_is_reported_without_exposing_session(
    monkeypatch, capsys, login_setup
):
    setup = login_setup
    original = setup.env.read_bytes()
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    monkeypatch.setattr(login, "update_session_in_env", Mock(side_effect=PermissionError(
        setup.client.session.save()
    )))
    assert await login.main(setup.env) == 1
    output = capsys.readouterr()
    assert "fayl ruxsatlarini tekshiring" in output.out
    assert setup.client.session.save() not in output.out + output.err
    assert setup.env.read_bytes() == original
    setup.client.disconnect.assert_awaited_once()
