# 🤖 ربات فضول‌یاب — نسخه Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/YOUR-TEMPLATE-SLUG?referralCode=uTN7AS&utm_medium=integration&utm_source=template&utm_campaign=generic)

> دکمه بالا بعد از ساخت قالب در Railway فعال می‌شود (بخش «ساخت دکمه دیپلوی» پایین).

ربات بله با سیستم لینک فضول‌یابی، XP، سطح، ماموریت و اشتراک VIP — آماده استقرار روی Railway.

## ✨ امکانات

- لینک تله اختصاصی برای هر کاربر + شناسایی فضول‌ها
- سیستم XP و سطح با ۲۰۰ ماموریت یکباره
- اشتراک VIP با پرداخت درون‌برنامه‌ای بله (IRT)
- پنل ادمین کامل: پخش همگانی، مدیریت قیمت، آمار، کانال اجباری
- گزارش روزانه خودکار به ادمین

## 🚀 استقرار روی Railway

### پیش‌نیازها

1. توکن ربات از [@BotFather](https://t.me/BotFather) در بله
2. شناسه عددی حساب ادمین (از ربات‌های شناسه‌یاب در بله قابل دریافت است)

### مراحل

1. **ریپو را به Railway وصل کنید:** New Project → Deploy from GitHub repo → این ریپو
2. **متغیرهای محیطی** (تب Variables):

   | متغیر | اجباری؟ | توضیح |
   |---|---|---|
   | `BOT_TOKEN` | ✅ | توکن ربات از BotFather بله |
   | `ADMIN_ID` | ✅ | شناسه عددی ادمین (مثلاً `123456789`) |
   | `PROVIDER_TOKEN` | اختیاری | توکن درگاه پرداخت — بدون آن پرداخت VIP غیرفعال می‌شود |
   | `DB_PATH` | خودکار | به صورت پیش‌فرض `/data/bot_data.db` ست شده (در railway.toml) |
   | `VIP_PRICE_7` / `VIP_PRICE_30` / `VIP_PRICE_90` | اختیاری | قیمت پلن‌ها به **ریال** |

3. **Volume بسازید** (خیلی مهم — بدون آن دیتابیس با هر دیپلوی پاک می‌شود):
   - تب Settings → Volumes → New Volume
   - Mount path: `/data`
4. **Deploy** بزنید. لاگ‌ها باید این را نشان دهند:
   ```
   ✅ Health server روی پورت 8080 فعال شد.
   🚀 ربات @username راه‌اندازی شد.
   ```

### بازیابی دیتابیس موجود

اگر قبلاً فایل `bot_data.db` دارید:

```bash
# با Railway CLI (بعد از railway link)
railway volume cp bot_data.db /data/bot_data.db
```

یا اگر Volume متصل نیست، موقتاً DB_PATH را روی مسیر پیش‌فرض بگذارید، فایل را با scp/پنل آپلود کنید و بعد Volume را وصل کنید.

## 💻 اجرای محلی (برای تست)

```bash
pip install -r requirements.txt
export BOT_TOKEN="توکن"
export ADMIN_ID="123456789"
python main.py
```

## ⚠️ نکته‌های مهم Railway

- **پلن Trial رایگان** فقط ~۵ دلار اعتبار ۳۰ روزه است؛ برای کاربران فعال حدوداً یک هفته دوام می‌آورد. پلن Hobby (۵$/ماه) برای همین حجم کافی است.
- ربات با polling کار می‌کند؛ نیازی به Set Webhook و دامنه عمومی ندارد.
- ری‌استارت خودکار روشن است (`restartPolicyType = always`) — اگر polling قطع شود ربات دوباره بالا می‌آید.

## 📁 ساختار پروژه

| فایل | توضیح |
|---|---|
| `main.py` | منطق اصلی ربات (~۶۱۵۰ خط) |
| `texts.py` | متن‌های پیام‌ها |
| `tasks.py` | تعریف ۲۰۰ ماموریت XP |
| `config.py` | تنظیمات — از متغیرهای محیطی می‌خواند |
| `Dockerfile` | بیلد قطعی روی python:3.12-slim |
| `railway.toml` | تنظیمات Railway (healthcheck، volume الزامی `/data`، ری‌استارت) |

## 🔘 ساخت دکمه دیپلوی (Deploy Button)

دکمه دیپلوی ریلوی به یک «قالب» (Template) وصل می‌شود که متغیرها را **قبل از دیپلوی** از کاربر می‌گیرد. یک‌بار این مراحل را انجام دهید:

1. وارد [railway.com](https://railway.com) شوید → صفحه Workspace → تب **Templates** → **New Template**
2. **Add a service → GitHub Repo** → ریپو `bale-snoop-bot` را انتخاب کنید
3. در همان سرویس: تب **Variables** → این متغیرها را به عنوان **Required** اضافه کنید:
   - `BOT_TOKEN` — توکن ربات از BotFather بله
   - `ADMIN_ID` — شناسه عددی ادمین
   - `PROVIDER_TOKEN` *(اختیاری)* — توکن درگاه پرداخت
4. Volume را در قالب هم اضافه کنید: Settings سرویس → Volumes → mount path `/data`
5. **Create Template** → آدرس قالب را کپی کنید
6. لینک داخل badge بالا (بخش اول README) را با slug قالب خودتان عوض کنید:

```markdown
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/SLUG-TEMPLATE-SHOMA?referralCode=uTN7AS&utm_medium=integration&utm_source=template&utm_campaign=generic)
```

از این به بعد هر کسی دکمه را بزند، فرم متغیرها را پر می‌کند و ریلوی خودش Volume را وصل کرده و deploy می‌کند — بدون هیچ تنظیم دستی بعد از دیپلوی.
