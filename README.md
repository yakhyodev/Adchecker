# 📊 IMKON Telegram Ads Monitoring System

O‘zbekistondagi **IMKON savdo markazi** uchun Telegram kanallardagi reklamalarni avtomatlashtirilgan monitoring qilish, statistikani to'plash va tahliliy Excel hisobotlar shakllantirish tizimi.

Ushbu tizim xodimlarning kanallardagi `@imkonhelpbot` manzili mavjud bo'lgan postlarni qo'lda qidirish, ko'rishlar sonini daftarga yoki Excelga qo'lda yozib borish jarayonini 100% avtomatlashtiradi.

---

## 🚀 ASOSIY IMKONIYATLAR

- 📢 **Kanallarni qulay boshqarish:** Telegram bot orqali istalgan ko'rinishdagi havola (`@kanal`, `https://t.me/kanal`, `https://t.me/s/kanal`) orqali kanal qo'shish, to'xtatish va o'chirish (soft-delete).
- 🔍 **Reklamalarni avtomatik aniqlash:** `@imkonhelpbot` kaliti orqali barcha postlar, rasm/video izohlari (caption) va bosiladigan havola (entity) lardan reklamalarni aniqlash.
- ⏱ **Dinamik statistika tarixi:** Har bir postning ko'rishlar (views), reaksiyalar (reactions) va forwardlar sonini vaqtlar kesimida (`view_snapshots`) saqlash va 24 soatlik o'sish dinamikasini hisoblash.
- 📊 **Professional Excel Generator:** 4 varaqdan iborat (Reklamalar, Kanallar statistikasi, Umumiy hisobot, Kunlik statistika) IMKON brendi ranglaridagi formatlangan Excel hisobot.
- 📈 **Davriy hisobotlar:** Oxirgi 7 kunlik, 30 kunlik, 365 kunlik va istalgan maxsus sana oralig'i (`YYYY-MM-DD`) bo'yicha tahlil.
- 💵 **CPM va reyting:** Kanallar kesimida reklama xarajati bo'yicha CPM (*Cost Per Mille* - 1,000 ko'rish narxi) va eng samarali kanallar reytingi.
- 🔔 **Tezkor bildirishnoma:** Yangi reklama joylanganda administratorlarga bir zumda xabar berish.
- 🛡 **Ko'p bosqichli xavfsizlik:** Rolli kirish nazorati (Superadmin, Admin, Viewer), Excel formula injection himoyasi, Telegram FloodWait cheklovlarini to'g'ri boshqarish.

---

## 🛠 TEXNOLOGIYALAR

- **Python 3.12+** (Asinxron arxitektura `asyncio`)
- **aiogram 3.x** — Telegram Bot API
- **Telethon** — Telegram MTProto Client API (kanallar tarixini o'qish uchun)
- **PostgreSQL** — Asosiy ma'lumotlar bazasi
- **SQLAlchemy 2.x (Async)** & **Alembic** — ORM va migratsiyalar
- **APScheduler** — Asinxron fon monitoringi (Background worker)
- **openpyxl** & **pandas** — Excel fayllarini shakllantirish
- **Docker** & **Docker Compose** — Konteynerizatsiya va oson deployment
- **pytest** — Avtomatlashtirilgan testlar to'plami

---

## 📋 BOSQICHMA-BOSQICH O'RNATISH YO'RIQNOMASI

### 1-qadam: Telegram Bot yaratish (BotFather)
1. Telegramda [@BotFather](https://t.me/BotFather) botiga kiring.
2. `/newbot` buyrug'ini yuboring.
3. Botingizga nom (masalan, `IMKON Ads Monitor`) va username bering.
4. Berilgan `BOT_TOKEN` ni nusxalab oling.

### 2-qadam: Telegram Developer API ma'lumotlarini olish
1. [my.telegram.org](https://my.telegram.org) saytiga shaxsiy Telegram raqamingiz bilan kiring.
2. **API development tools** bo'limiga o'ting.
3. Yangi ilova yarating (masalan, `imkon_monitor`).
4. **App api_id** va **App api_hash** ma'lumotlarini nusxalab oling.

### 3-qadam: Administrator Telegram ID sini aniqlash
1. Telegramda [@userinfobot](https://t.me/userinfobot) ga `/start` yuboring.
2. O'zingizning raqamli `Id` raqamingizni oling (masalan, `123456789`).

### 4-qadam: Konfiguratsiya (.env fayli)
Loyihaning asosiy papkasida `.env.example` faylidan nusxa olib, `.env` faylini yarating:

```bash
cp .env.example .env
```

`.env` faylini ochib, ma'lumotlarni kiriting:
```ini
BOT_TOKEN="sizning_bot_tokeningiz"
ADMIN_IDS="123456789"
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH="sizning_api_hash"
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/imkon_ads"
```

### 5-qadam: Telegram Akkauntga kirish (Telethon Sessiyasi)
Telegram akkauntiga server terminalida bir marta xavfsiz autentifikatsiya qilinadi:

```bash
python scripts/telegram_login.py
```
- Telefon raqamingizni kiriting (`+99890...`).
- Telegram ilovangizga kelgan 5 xonali tasdiqlash kodini kiriting.
- Agar 2FA (ikki bosqichli parol) yoqilgan bo'lsa, parolni kiriting.
- Skript sessiyani avtomatik `.env` faylidagi `TELEGRAM_SESSION_STRING` parametriga saqlab beradi.

---

## 🐳 DOCKER COMPOSE ORQALI ISHGA TUSHIRISH (Tavsiya etiladi)

Docker va Docker Compose o'rnatilgan serverda bitta buyruq bilan ishga tushirish:

```bash
# Konteynerlarni yig'ish va fonda ishga tushirish
docker compose up -d --build

# Loglarni kuzatish
docker compose logs -f bot
```

Konteyner to'xtatilganda yoki qayta yuklanganda ma'lumotlar bazasi (`pg_data`) va sessiyalar to'liq saqlanib qoladi.

---

## 💻 LOKAL MUHITDA ISHGA TUSHIRISH (DOCKER'SIZ)

1. Python virtual muhitini yarating va faollashtiring:
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
```

2. Kerakli kutubxonalarni o'rnating:
```bash
pip install -r requirements.txt
```

3. Ma'lumotlar bazasi migratsiyalarini qo'llang:
```bash
alembic upgrade head
```

4. Dasturni ishga tushiring:
```bash
python app/main.py
```

---

## 🧪 TESTLARNI ISHGA TUSHIRISH

Loyiha 100% testlar bilan ta'minlangan. Barcha 24 ta avtomatlashtirilgan testlarni ishga tushirish uchun:

```bash
pytest -v
```

Testlar quyidagilarni to'liq tekshiradi:
- Havolalarni to'g'ri normalizatsiya qilish.
- Takroriy kanal va reklamalarning oldini olish (idempotency).
- `@imkonhelpbot` kalitini katta-kichik harflardan qat'i nazar aniqlash.
- Media caption va entity linklaridan qidiruv.
- Haftalik, oylik, yillik va maxsus davr hisobotlari.
- 4 varaqli Excel hisobot strukturasi va formula inyektsiyasiga qarshi himoya.
- Telegram FloodWait xatoliklarini to'g'ri qayta ishlash.
- Ruxsatsiz foydalanuvchilarni rad etish.
- Snapshotlar orqali 24 soatlik o'sish dinamikasi.

---

## 📱 BOTDAN FOYDALANISH VA BUYRUQLAR

Telegram botda `/` belgisi yozilishi bilanoq quyidagi buyruqlar avtomatik tavsiya etiladi:

| Buyruq | Tavsif |
| :--- | :--- |
| `/start` | Asosiy menyuni ochish |
| `/recent` | Oxirgi joylashtirilgan reklamalar (sahifalash bilan) |
| `/channels` | Reklama kanallarini boshqarish va yangi kanal qo'shish |
| `/stats_week` | Oxirgi 7 kunlik statistika xulosasi |
| `/stats_month` | Oxirgi 30 kunlik kengaytirilgan hisobot |
| `/stats_year` | Oxirgi 365 kunlik dinamika |
| `/custom_range` | Foydalanuvchi tanlagan sana oralig'i bo'yicha hisobot |
| `/excel` | Professional Excel hisobotni (.xlsx) yuklab olish |
| `/refresh` | Ko'rishlar statistikasini majburiy yangilash |
| `/settings` | Tizim holati, kalit so'zlar va monitoring sozlamalari |
| `/help` | Botdan foydalanish yo'riqnomasi |

---

## 💾 BAZANI ZAXIRALASH (BACKUP & RESTORE)

### Zaxira nusxa olish (Backup):
```bash
docker exec -t imkon_ads_postgres pg_dump -U postgres imkon_ads > backup_$(date +%Y%m%d).sql
```

### Zaxiradan tiklash (Restore):
```bash
cat backup_20261021.sql | docker exec -i imkon_ads_postgres psql -U postgres -d imkon_ads
```

---

## 🔒 XAVFSIZLIK VA PRIVACY

- Tizim maxfiy ma'lumotlarni (`API_HASH`, `BOT_TOKEN`, `TELEGRAM_SESSION_STRING`) loglarda avtomatik filtrlaydi (`[REDACTED_SECRET]`).
- Tashqi foydalanuvchilar botga kira olmaydi (`AuthMiddleware` bloklaydi).
- Excel fayllaridagi ma'lumotlar CSV/Excel Formula Injection dan tozalangan holda yoziladi.
- Telegram so'rovlari limitlarga qat'iy rioya qiladi va hisobning bloklanishiga yo'l qo'ymaydi.
