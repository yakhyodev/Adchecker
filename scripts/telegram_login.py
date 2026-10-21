"""Interactive phone/QR authentication; persist only the session in the host .env."""

import asyncio
import codecs
import getpass
import io
import os
from pathlib import Path
import re
import sys
import warnings

from dotenv import dotenv_values
from dotenv.parser import parse_stream
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    ApiIdInvalidError, AuthTokenExpiredError, FloodWaitError, PasswordHashInvalidError,
    PhoneCodeExpiredError, PhoneCodeInvalidError, PhoneNumberBannedError,
    PhoneNumberInvalidError, RPCError, SessionPasswordNeededError,
)

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
SESSION_KEY = "TELEGRAM_SESSION_STRING"


def hidden_input(prompt: str) -> str:
    # Refuse getpass's visible-input fallback when there is no secure TTY.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def update_session_in_env(env_path: Path, session: str) -> None:
    """Preserve unrelated text, BOM, newlines, and the file inode."""
    if not session or not re.fullmatch(r"[A-Za-z0-9_+/=-]+", session):
        raise ValueError("Invalid session encoding")
    # In-place update supports Docker's individual .env bind mount. Renaming
    # a temporary file over that mount would fail with EBUSY.
    with env_path.open("r+b") as env_file:
        original = env_file.read()
        bom = codecs.BOM_UTF8 if original.startswith(codecs.BOM_UTF8) else b""
        text = original.decode("utf-8-sig")
        newline = "\r\n" if "\r\n" in text else "\n"
        parts = []
        found = False
        for binding in parse_stream(io.StringIO(text)):
            if binding.error:
                raise ValueError("Invalid .env syntax")
            raw = binding.original.string
            if binding.key == SESSION_KEY:
                # Parse whole bindings so a fake key in another variable's
                # multiline value cannot be mistaken for the session setting.
                match = re.search(
                    r"(?m)^[ \t]*(?:export[ \t]+)?(?:TELEGRAM_SESSION_STRING|'TELEGRAM_SESSION_STRING')",
                    raw,
                )
                if match is None:
                    raise ValueError("Invalid session binding")
                ending = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
                raw = raw[:match.start()] + f'{SESSION_KEY}="{session}"' + ending
                found = True
            parts.append(raw)
        updated = "".join(parts)
        if not found:
            if updated and not updated.endswith(("\n", "\r")):
                updated += newline
            updated += f'{SESSION_KEY}="{session}"{newline}'
        payload = bom + updated.encode("utf-8")
        env_file.seek(0)
        env_file.write(payload)
        env_file.truncate()
        env_file.flush()
        os.fsync(env_file.fileno())


def render_qr(url: str) -> None:
    import qrcode

    qr = qrcode.QRCode(border=4)
    qr.add_data(url)
    qr.make(fit=True)
    print("\nTelegram → Sozlamalar → Qurilmalar → Qurilmani ulash orqali skanerlang.")
    print("Terminal oynasini QR qatorlari bo'linmaydigan darajada kengaytiring.")
    qr.print_ascii(out=sys.stdout, tty=sys.stdout.isatty(), invert=True)
    print(flush=True)


async def complete_2fa(client: TelegramClient) -> bool:
    print("🔒 Ikki bosqichli himoya yoqilgan. Parol terminalda ko'rinmaydi.")
    for _ in range(3):
        password = hidden_input("2FA parolingiz: ")
        if not password:
            print("❌ Parol bo'sh. Qaytadan kiriting.")
            continue
        try:
            await client.sign_in(password=password)
            return True
        except PasswordHashInvalidError:
            print("❌ 2FA paroli noto'g'ri. Qaytadan kiriting.")
    print("❌ Parolni kiritish urinishlari tugadi. Loginni qayta boshlang.")
    return False


async def login_phone(client: TelegramClient) -> bool:
    phone = input("Telegram telefon raqamingiz (+998...): ").strip()
    if not phone:
        print("❌ Telefon raqami kiritilmadi.")
        return False
    sent_code = await client.send_code_request(phone)
    print("Kod yetkazish turi:", type(sent_code.type).__name__)
    for _ in range(3):
        code = input("Telegram yuborgan tasdiqlash kodini kiriting: ").strip()
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent_code.phone_code_hash)
            return True
        except SessionPasswordNeededError:
            return await complete_2fa(client)
        except PhoneCodeInvalidError:
            print("❌ Tasdiqlash kodi noto'g'ri. Qaytadan kiriting.")
    print("❌ Kodni kiritish urinishlari tugadi. Loginni qayta boshlang.")
    return False


async def login_qr(client: TelegramClient) -> bool:
    qr = await client.qr_login()
    while True:
        # Install Telethon's listener before exposing the QR to a scanner.
        waiter = asyncio.create_task(qr.wait())
        try:
            await asyncio.sleep(0)
            render_qr(qr.url)
            await waiter
            return True
        except (asyncio.TimeoutError, AuthTokenExpiredError):
            print("⌛ QR-kod muddati tugadi.")
        except SessionPasswordNeededError:
            return await complete_2fa(client)
        finally:
            if not waiter.done():
                waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)

        while True:
            choice = input("Yangi QR-kod yarataymi? (y/n) [y]: ").strip().lower()
            if choice in ("n", "no", "yo'q", "0"):
                print("Login bekor qilindi.")
                return False
            if choice in ("", "y", "yes", "ha"):
                await qr.recreate()
                break
            print("❌ y yoki n kiriting.")


async def main(env_path: Path = ENV_PATH) -> int:
    print("IMKON ADS MONITORING — TELEGRAM LOGIN")
    print("1. Telefon kodi orqali kirish\n2. QR-kod orqali kirish\n0. Bekor qilish")
    client = None
    try:
        while True:
            choice = input("Login usulini tanlang (1/2/0): ").strip()
            if choice == "0":
                print("Login bekor qilindi.")
                return 1
            if choice in ("1", "2"):
                break
            print("❌ 1, 2 yoki 0 kiriting.")

        # Never display API hashes or existing sessions in prompts.
        content = env_path.read_text(encoding="utf-8-sig")
        values = dotenv_values(stream=io.StringIO(content), interpolate=False)
        api_id_raw = os.getenv("TELEGRAM_API_ID") or values.get("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH") or values.get("TELEGRAM_API_HASH")
        if not api_id_raw:
            api_id_raw = input("Telegram API_ID kiriting: ").strip()
        api_id = int(api_id_raw)
        if api_id <= 0:
            raise ValueError("Invalid API ID")
        if not api_hash:
            api_hash = hidden_input("Telegram API_HASH kiriting: ").strip()
        if not api_hash:
            print("❌ TELEGRAM_API_HASH kiritilishi shart.")
            return 1

        client = TelegramClient(StringSession(), api_id, api_hash)
        print("Telegram serverlariga ulanilmoqda...")
        await client.connect()
        if not await client.is_user_authorized():
            success = await (login_phone(client) if choice == "1" else login_qr(client))
            if not success:
                return 1
        if not await client.is_user_authorized():
            print("❌ Telegram avtorizatsiyani tasdiqlamadi. Loginni qayta boshlang.")
            return 1

        update_session_in_env(env_path, client.session.save())
        print("✅ Avtorizatsiya tugadi. TELEGRAM_SESSION_STRING .env fayliga saqlandi.")
        print("Boshqa .env qiymatlari o'zgartirilmadi. Sessiya terminalga chiqarilmaydi.")
        return 0
    except FileNotFoundError:
        print("❌ .env topilmadi. Loyiha papkasida .env yarating yoki Docker'ga ulang.")
    except ImportError:
        print("❌ QR kutubxonasi topilmadi. requirements.txt paketlarini o'rnating yoki Docker image'ni qayta yig'ing.")
    except getpass.GetPassWarning:
        print("❌ Terminal parolni yashira olmadi. Interaktiv SSH terminalidan foydalaning.")
    except ApiIdInvalidError:
        print("❌ Telegram API_ID yoki API_HASH noto'g'ri. .env sozlamalarini tekshiring.")
    except PhoneNumberInvalidError:
        print("❌ Telefon raqami noto'g'ri. Uni +998... shaklida kiriting.")
    except PhoneNumberBannedError:
        print("❌ Ushbu telefon raqami Telegram tomonidan bloklangan.")
    except PhoneCodeExpiredError:
        print("❌ Tasdiqlash kodi eskirgan. Loginni qayta boshlang.")
    except FloodWaitError as error:
        print(f"⏳ Telegram cheklovi: {error.seconds} soniyadan keyin qayta urinib ko'ring.")
    except (ConnectionError, asyncio.TimeoutError):
        print("❌ Telegram bilan aloqa uzildi yoki kutish vaqti tugadi. Qayta urinib ko'ring.")
    except OSError:
        print("❌ Tarmoq yoki .env fayliga yozish xatosi. Ulanish va fayl ruxsatlarini tekshiring.")
    except (ValueError, UnicodeError):
        print("❌ API_ID yoki .env formati noto'g'ri. UTF-8 va sozlamalarni tekshiring.")
    except RPCError:
        print("❌ Telegram login so'rovini rad etdi. Sozlamalarni tekshirib qayta urinib ko'ring.")
    except (EOFError, KeyboardInterrupt):
        print("Login bekor qilindi.")
    except Exception:
        # Exceptions may contain credentials or login tokens; never echo them.
        print("❌ Login bajarilmadi. Ulanish va sozlamalarni tekshirib qayta urinib ko'ring.")
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                print("⚠️ Telegram ulanishini yopib bo'lmadi.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nLogin bekor qilindi.")
        raise SystemExit(1)
