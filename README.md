# Telegram reklama qidiruvi

Bot bazada **oldindan saqlangan faol kanallardan** foydalanuvchi kiritgan kalit
so'z va davr bo'yicha reklamalarni ulangan Telegram akkaunti orqali bevosita qidiradi.
Akkaunt a'zo bo'lgan boshqa kanallarning postlari tekshirilmaydi.

## Foydalanish

1. `/start` yuboring.
2. **📢 Kanallar → ➕ Kanal qo'shish** orqali bir yoki ko'p havola yuboring.
   Bo'shliq va yangi qator bilan ajratish mumkin:

   ```text
   @kanal_bir https://t.me/kanal_ikki
   https://t.me/s/kanal_uch @kanal_tort
   ```

   Har kanal Telegram ID bilan saqlanadi. Bitta kanalning turli havolalari yoki
   yangi username'i ikkinchi yozuv yaratmaydi; bazadagi Telegram ID ustunida
   `UNIQUE` cheklovi mavjud. Xato havola qolgan to'g'ri kanallarni saqlashni to'xtatmaydi.
   Natijada saqlangan, avval mavjud va saqlanmagan havolalar alohida ko'rsatiladi.
   Telegram FloodWait bersa, oldingi muvaffaqiyatli kanallar saqlanadi;
   qolganlarini ko'rsatilgan kutish vaqtidan keyin qayta yuborish mumkin.
3. **🆕 Oxirgi reklamalar**, **🗓 Shu oy** yoki **📆 Sana bo‘yicha** ni tanlang.
4. Kalit so'z yoki iborani yuboring, masalan `@imkonhelpbot`, `chegirma` yoki
   `IMKON savdo`. Bo'shliqlar ibora ichida saqlanadi. Bir nechta muqobil kalitni
   vergul yoki yangi qator bilan ajrating: ulardan bittasi mos kelsa post olinadi.
5. Natijalarni botda sahifalab ko'ring va yuborilgan Excel hisobotni oching.

**Oxirgi reklamalar** har kanaldan eng yangi mos bitta reklamani qaytaradi.
**Shu oy** Toshkent vaqti bilan oyning 1-kuni 00:00 dan so'rov vaqtigacha bo'lgan
barcha mos reklamalarni oladi. Maxsus sana oralig'ining boshlanish va tugash
kunlari ham hisobga olinadi. Kelajakdagi sanalar qabul qilinmaydi.

Kanallar ro'yxatida kanalni **o'chirish**, qidiruvdan vaqtincha chiqarish yoki
faollashtirish mumkin. O'chirilgan va faol bo'lmagan kanallar qidirilmaydi.
O'chirish Telegram kanalidan chiqib ketmaydi va mavjud eski reklama tarixini o'chirmaydi.
O'chirilgan kanal qayta qo'shilsa, o'sha ID li yozuv tiklanadi.

## Hisobot shakli

`Top Reklama Tg.xlsx` namunasidagi jadval tartibi qo'llanadi:

- har kanal bitta qatorda;
- boshida **VILOYAT**, **Kanal nomi**, kanal havolasi va aloqa havolasi;
- aloqa ustuni namunadagi kabi yashirilgan, Excel orqali ochish mumkin;
- davriy qidiruvda har sanaga **reklama havolasi / ko'rilishlar / ulashishlar**
  ustunlari yonma-yon; bir kunda bir nechta mos post bo'lsa alohida bloklar;
- sana bo'yicha natijalar bir xil ustunlarga joylashadi, yo'q reklama katagi **qizil**;
- oxirgi reklama rejimida bitta havola bloki va reklama sanasi;
- kanalga kirish, aloqa yoki Telegram cheklovi sabab tugamagan tekshiruv **sariq**;
- ko'rilishlar namunadagi kabi `60.2k` ko'rinishida, ichki qiymati haqiqiy son;
- Telegram bermagan son bo'sh qoladi, haqiqiy `0` esa nol sifatida saqlanadi;
- pastda qidirilgan kalitlar, davr va statistikani olish vaqti.

Namunadagi hudud va aloqa qiymatlari `app/reports/channel_report_reference.json`
faylida saqlanadi. Dastlab kanal username'i bilan moslanib, kanal qo'shish yoki
tekshirish paytida Telegram ID ga bog'lab saqlanadi. Nom, username va havola
o'zgarganda mavjud kanal yozuvi yangilanadi;
namunada bo'lmagan kanalning hududi va aloqasi bo'sh qoladi. Bu ma'lumotnoma
kanalni qidirish manbasi emas: postlar faqat bazada saqlangan **Telegram ID** orqali olinadi.
Namunaning eski postlari va ko'rilishlari yangi natija sifatida ishlatilmaydi.

## Qidiruv qanday ishlaydi

Matn, media izohi va yashirin havolalar katta-kichik harflarni ajratmasdan
tekshiriladi. Bir media albomidagi mos xabarlar bitta reklama hisoblanadi.
Avval Telegram serverining qidiruvidan nomzod postlar olinadi (har kalit uchun
1000 tagacha), so'ng 500 tagacha so'nggi xabar orqali yashirin havola va
indeksga tushmagan matnlar ham tekshiriladi. To'liq tasdiqlanmagan natija sariq
rangda **Qisman tekshirildi** deb ko'rsatiladi. **To'liq tekshirish** tugmasi
shu kanallarning tanlangan davrdagi tarixini cheklovsiz tekshiradi va natijani
avvalgi hisobot bilan birlashtiradi. Katta tarixning to'liq tekshiruvi vaqt olishi mumkin.

Username yoki kanal nomi almashsa ham saqlangan ID ishlatiladi. Sessiyada
kanalning access hash'i bo'lmasa, akkaunt dialoglarining metama'lumotlari olinib,
faqat saqlangan ID lar ajratiladi; boshqa kanallarning postlari qidirilmaydi.
Hisobotda Telegram qaytargan hozirgi nom va havola ishlatiladi.

Qidiruv reklamalar, snapshotlar yoki skanerlash checkpointlarini bazaga yozmaydi.
Fon monitoringi ishga tushmaydi, hatto eski `.env` yoki bazada avtomatik monitoring
yoqilgan bo'lsa ham. Mavjud tarixiy jadvallar saqlanadi. Baza kanal ro'yxati,
administratorlar va mavjud sozlamalar uchun ishlatiladi.

Natijalar Excelni qayta yuklash va sahifalash uchun faqat jarayon xotirasida
30 daqiqa turadi (jami eng ko'pi 8 ta hisobot). Natija tugmalari faqat hisobotni
olgan foydalanuvchi va chat uchun ishlaydi. Yangi qidiruv statistikani qaytadan oladi.
Bir vaqtda ikkita Telegram qidiruvi ishlaydi; qolganlari bekor qilish mumkin
bo'lgan navbatga qo'shiladi. **/cancel**, **/start** yoki bosh menyu qidiruv va
kanal qo'shishni to'xtatadi. Eski jarayon to'xtagach yangi menyu boshlanadi.
Kanal qo'shishda tugagan har bir yozuv alohida saqlanadi: bekor qilish oldin
saqlangan kanallarni o'chirmaydi, kutayotgan va qolgan havolalarni to'xtatadi.
Kanallarni tekshirish natijasi beshtadan sahifalanadi. Bot API 429 cheklovida
Telegram ko'rsatgan vaqt kutilib, yuborish uch martagacha qayta uriniladi;
jarayon holati xabari xatosi qidiruv natijalarini bekor qilmaydi.

## Post hisoboti

Yangi **📋 Post hisoboti** bo'limi mavjud reklama qidiruvidan mustaqil ishlaydi.
Bo'limga post havolasini yuboring yoki `/post https://t.me/imkonsavdomarkazi/5644`
buyrug'idan foydalaning. Bosh menyuda post havolasining o'zini yuborish ham mumkin.
Bo'lim faqat **imkonsavdomarkazi** kanalidagi postlar uchun ishlaydi; yangi environment
sozlamasi talab qilinmaydi. `/c/` ko'rinishidagi havola ham shu kanalning Telegram ID
qiymatiga tekshiriladi. Ulangan akkauntning boshqa yopiq kanallariga bu bo'limdan kirib bo'lmaydi.

Statistika bot tokenidan emas, mavjud **Telethon akkaunti** orqali olinadi.
Public shares statistikasi uchun shu akkaunt asosiy kanalda admin bo'lishi kerak;
Telegram statistikaga kirishni ham ochgan bo'lishi kerak. Botning o'zini admin qilish
akkauntga bu huquqni bermaydi.

Hisobot Telegram ayni so'rovda bergan post, public forwardlar va hisoblagichlardan
tuziladi. Public ro'yxatning barcha sahifalari olinadi; boshqa kanallarning tarixi
skanerlanmaydi. Telegram qaytargan kanal/guruh postlari uchun havola, sana-vaqt,
obunachi/a'zolar, ko'rishlar, reaksiyalar, ulashishlar va izohlar soni ko'rsatiladi.
Telegram taqdim etmagan guruh/manzillar mustaqil qidirilmaydi. Storislar va shaxsiy
chatlar ro'yxatga kiritilmaydi.

**Private Shares** Telegram Desktop kabi `jami ulashishlar − Telegram public jami`
orqali olinadi. Filtrlangan yoki hali to'liq yuklanmagan ro'yxat uzunligi bu hisobda
ishlatilmaydi. Kerakli hisoblagich yo'q yoki qiymatlar bir-biriga zid bo'lsa, qiymat
taxmin qilinmaydi. Public ro'yxat to'liq olinmasa, bot xabarida bu ko'rsatiladi.
FloodWait, tarmoq/server muammosi yoki so'rovning 30 soniyalik kutish muddati tugasa,
olingan ma'lumotlar saqlanib, qisman hisobot beriladi. Asosiy post hali olinmagan
bo'lsa, texnik muammo alohida bildiriladi va "topilmadi" bilan almashtirilmaydi.
Holat xabarini tahrirlashdagi muammo Excel yuborilishini to'xtatmaydi.
Qisman natijada Excel fayli va public forwardlar varag'i nomida **qisman** belgisi
bo'ladi; jadvaldan tashqari qo'shimcha yozuv yoki grafik qo'shilmaydi.

Excel'da faqat **Asosiy post** va **Public forwardlar** jadvallari bor; grafiklar,
izoh varaqlari va qo'shimcha yozuvlar yo'q. Sanalar Toshkent vaqtida, sonlar haqiqiy
raqam sifatida saqlanadi. Yo'q qiymatlar **Ma'lumot topilmadi**, haqiqiy nol esa `0`.
Ma'lumot yo'qligi yoki statistikaga ruxsat bo'lmasligi logga INFO sifatida tushadi;
haqiqiy tarmoq/server muammolari bundan alohida ko'rsatiladi.

Hisobot bazaga yozilmaydi, fon monitoringi yoki obunachilarni mustaqil kuzatish
qo'shilmagan. `/cancel`, `/start` va bosh menyu davom etayotgan so'rovni to'xtatadi.

## Ishga tushirish

Python 3.12+, PostgreSQL va Telegram akkaunti sessiyasi kerak.
Post hisoboti uchun Telethon 1.45+ talab qilinadi (`requirements.txt` ichida ko'rsatilgan).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`.env` ichida `BOT_TOKEN`, `ADMIN_IDS`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
va `DATABASE_URL` ni to'ldiring. Lokal baza uchun host `localhost`, Docker
Compose uchun `postgres`. Namunaviy token/API qiymatlari bilan bot ishga tushmaydi.

Akkaunt saqlanadigan kanallarga kirish huquqiga ega bo'lishi kerak. Yopiq kanalning
taklif havolasi faqat akkaunt avvaldan a'zo bo'lsa qabul qilinadi; bot avtomatik a'zo bo'lmaydi.

```powershell
python -u scripts/telegram_login.py
alembic upgrade head
python -m app.main
```

Login skripti telefon kodi yoki QR orqali kirishni, yashirin 2FA parolini va
sessiyani mavjud `.env` ga saqlashni qo'llaydi. Sessiya va parollar logga chiqarilmaydi.
Bot uchun mavjud `admin` / `superadmin` kanallarni boshqara oladi;
`viewer` qidirishi va hisobot olishi mumkin.

Docker Compose:

```bash
docker compose up -d --build
docker compose logs --tail=60 bot
```

Serverda interaktiv login uchun loyiha papkasidagi `.env` faylini ulang:

```bash
docker compose run --rm --no-deps -v "$PWD/.env:/app/.env" bot python -u scripts/telegram_login.py
docker compose up -d --no-deps --force-recreate bot
```

Yangi sessiyani yuklash uchun konteynerni qayta yaratish kerak; `restart`ning
o'zi yangi `.env` qiymatlarini yuklamaydi.

## Buyruqlar

| Buyruq | Amal |
| --- | --- |
| `/start` | Asosiy menyu |
| `/channels` | Kanal qo'shish, ro'yxat, faollik va o'chirish |
| `/recent` | Har kanaldagi eng oxirgi mos reklama |
| `/stats_month` | Shu oydagi reklamalar |
| `/custom_range` | Ikki sana oralig'idagi reklamalar |
| `/search`, `/excel` | Davrni tanlab yangi qidiruv |
| `/post` | Post havolasi bo'yicha statistika va public forwardlar |
| `/cancel` | Amalni yoki qidiruvni bekor qilish |
| `/help` | Yo'riqnoma |

## Tekshiruvlar

```powershell
python -m pytest -q
```

Testlar SQLite va Telegram/Bot API mocklari bilan ishlaydi. Ular kanal ID bo'yicha
takrorlanmaslik, ko'p kanalni birdan saqlash, o'chirish va tiklash, nom/username
o'zgarishi, sanalar chegaralari, albom va havolalar, xatolar/FloodWait, bekor qilish,
bot menyu oqimi va Excel jadvalini tekshiradi. Eski modullar testlari ham saqlangan.
Bu tekshiruvlar haqiqiy Telegram akkaunti, PostgreSQL yoki serverda ishlash tasdig'i emas.
