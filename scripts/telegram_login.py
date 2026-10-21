import asyncio
import os
import sys
import getpass
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
)

# Add parent directory to sys.path so app modules can be loaded if needed
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def main() -> None:
    print("=" * 60)
    print("   IMKON ADS MONITORING — TELEGRAM LOGIN (MTPROTO)")
    print("=" * 60)
    print("Ushbu skript Telegram MTProto akkauntingizni tizimga xavfsiz ulash")
    print("va sessiya (StringSession) yaratish uchun xizmat qiladi.\n")

    api_id_env = os.getenv("TELEGRAM_API_ID", "")
    api_hash_env = os.getenv("TELEGRAM_API_HASH", "")

    api_id_str = input(f"Telegram API_ID kiriting [{api_id_env}]: ").strip() or api_id_env
    api_hash_str = input(f"Telegram API_HASH kiriting [{api_hash_env}]: ").strip() or api_hash_env

    if not api_id_str or not api_hash_str:
        print("\n❌ Xatolik: API_ID va API_HASH kiritilishi shart!")
        print("Ularni https://my.telegram.org saytidan olishingiz mumkin.")
        return

    try:
        api_id = int(api_id_str)
    except ValueError:
        print("❌ API_ID raqam bo'lishi kerak!")
        return

    phone = input("\nTelegram telefon raqamingizni kiriting (+998901234567): ").strip()
    if not phone:
        print("❌ Telefon raqami kiritilmadi!")
        return

    print("\nTelegram serverlariga ulanilmoqda...")
    client = TelegramClient(StringSession(), api_id, api_hash_str)
    await client.connect()

    if not await client.is_user_authorized():
        print(f"Telegramga tasdiqlash kodi so'rovi yuborilmoqda: {phone}")
        try:
            sent_code = await client.send_code_request(phone)
        except Exception as e:
            print(f"❌ Kod yuborishda xatolik: {e}")
            await client.disconnect()
            return

        code = input("Telegram ilovangizga kelgan 5 xonali kodni kiriting: ").strip()

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            print("\n🔒 Ushbu akkauntda 2 bosqichli himoya (2FA) yoqilgan.")
            password = getpass.getpass("2FA parolingizni kiriting: ")
            try:
                await client.sign_in(password=password)
            except PasswordHashInvalidError:
                print("❌ 2FA paroli noto'g'ri kiritildi!")
                await client.disconnect()
                return
        except PhoneCodeInvalidError:
            print("❌ Telegram kodi noto'g'ri!")
            await client.disconnect()
            return
        except Exception as e:
            print(f"❌ Kirishda xatolik: {e}")
            await client.disconnect()
            return

    me = await client.get_me()
    session_string = client.session.save()
    await client.disconnect()

    print("\n" + "=" * 60)
    print("✅ Muvaffaqiyatli avtorizatsiyadan o'tildi!")
    print(f"👤 Akkaunt: {me.first_name} (@{me.username or 'username_yoq'})")
    print("=" * 60)
    print("\nSizning TELEGRAM_SESSION_STRING qiymatingiz:")
    print("-" * 60)
    print(session_string)
    print("-" * 60)

    save_env = input("\nUshbu sessiyani avtomatik .env fayliga saqlashni xohlaysizmi? (y/n) [y]: ").strip().lower()
    if save_env in ("", "y", "yes", "ha"):
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = []
        session_set = False
        api_id_set = False
        api_hash_set = False

        for line in lines:
            if line.startswith("TELEGRAM_SESSION_STRING="):
                new_lines.append(f'TELEGRAM_SESSION_STRING="{session_string}"\n')
                session_set = True
            elif line.startswith("TELEGRAM_API_ID="):
                new_lines.append(f"TELEGRAM_API_ID={api_id}\n")
                api_id_set = True
            elif line.startswith("TELEGRAM_API_HASH="):
                new_lines.append(f'TELEGRAM_API_HASH="{api_hash_str}"\n')
                api_hash_set = True
            else:
                new_lines.append(line)

        if not session_set:
            new_lines.append(f'TELEGRAM_SESSION_STRING="{session_string}"\n')
        if not api_id_set:
            new_lines.append(f"TELEGRAM_API_ID={api_id}\n")
        if not api_hash_set:
            new_lines.append(f'TELEGRAM_API_HASH="{api_hash_str}"\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        print(f"✅ .env fayli muvaffaqiyatli yangilandi: {os.path.abspath(env_path)}")

    print("\n🎉 Tabriklaymiz! Tizim monitoring uchun to'liq tayyor.")


if __name__ == "__main__":
    asyncio.run(main())
