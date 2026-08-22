# -*- coding: utf-8 -*-
"""
config.py — تنظیمات ربات فضول‌یاب
---
همه مقادیر از متغیرهای محیطی خوانده می‌شوند (Railway Variables) و اگر ست نشده باشند
از مقادیر پیش‌فرض امن استفاده می‌شود. این یعنی:
  - روی Railway فقط BOT_TOKEN و ADMIN_ID لازم است؛ بقیه اختیاری‌اند.
  - هیچ توکن یا مقدار حساسی داخل کد هاردکد نشده.

متغیرهای محیطی پشتیبانی‌شده:
  BOT_TOKEN        (اجباری)   توکن ربات از BotFather بله
  ADMIN_ID         (اجباری)   شناسه عددی ادمین (مثلاً 123456789)
  PROVIDER_TOKEN   (اختیاری)  توکن درگاه پرداخت بله — بدون آن پرداخت VIP غیرفعال می‌شود
  DB_PATH          (اختیاری)  مسیر فایل دیتابیس — روی Railway باید /data/bot_data.db باشد

  قیمت پلن‌های VIP به ریال (اختیاری):
    VIP_PRICE_7, VIP_PRICE_30, VIP_PRICE_90

  آی‌دی فایل‌های رسانه‌ای قبلاً آپلودشده در بله (اختیاری — خالی = بدون عکس/ویدیو):
    LEADERBOARD_PHOTO_ID, SCARY_PHOTO_ID, PROMO_WELCOME_NEW_PHOTO_ID,
    PROMO_WELCOME_OLD_PHOTO_ID, REVIEW_PHOTO_ID, VIP_MAIN_PHOTO_ID,
    BUY_VIP_PHOTO_ID, LEVEL_UP_PHOTO_ID, LINK_TUTORIAL_VIDEO_ID
"""

import os


def _env_str(key: str, default: str = "") -> str:
    value = os.environ.get(key)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env_str(key, str(default)).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


# ---------- اجباری ----------
BOT_TOKEN = _env_str("BOT_TOKEN")
ADMIN_ID = _env_int("ADMIN_ID", 0)

# ---------- پرداخت (اختیاری) ----------
PROVIDER_TOKEN = _env_str("PROVIDER_TOKEN")

# ---------- دیتابیس ----------
# روی Railway با Volume متصل به /data مقدار DB_PATH=/data/bot_data.db را ست کنید
DB_PATH = _env_str("DB_PATH", "bot_data.db")

# ---------- پلن‌ها و قیمت VIP (ریال) ----------
VIP_PRICES_DEFAULT = {
    7: _env_int("VIP_PRICE_7", 99000),
    30: _env_int("VIP_PRICE_30", 290000),
    90: _env_int("VIP_PRICE_90", 690000),
}

# ---------- پخش همگانی ----------
BROADCAST_WORKERS = _env_int("BROADCAST_WORKERS", 8)
BROADCAST_BATCH_SIZE = _env_int("BROADCAST_BATCH_SIZE", 50)
BROADCAST_BATCH_DELAY = _env_int("BROADCAST_BATCH_DELAY", 2)  # ثانیه بین هر batch
BROADCAST_TIMEOUT = _env_int("BROADCAST_TIMEOUT", 3600)  # ثانیه — سقف زمان یک broadcast

# ---------- XP ----------
XP_BONUS_ONE_TIME = {
    "first_snoop": _env_int("XP_FIRST_SNOOP", 100),      # اولین فضول یکتا برای صاحب لینک
    "first_invite": _env_int("XP_FIRST_INVITE", 150),    # اولین دعوت موفق
    "first_buy_vip": _env_int("XP_FIRST_BUY_VIP", 200),  # اولین خرید VIP
    "first_gift_vip": _env_int("XP_FIRST_GIFT_VIP", 200),  # اولین هدیه VIP
}

XP_RECURRING = {
    "new_distinct_snoop": _env_int("XP_PER_SNOOP", 10),      # هر فضول یکتای جدید
    "successful_invite": _env_int("XP_PER_INVITE", 20),      # هر دعوت موفق
    "daily_login": _env_int("XP_DAILY_LOGIN", 5),            # ورود روزانه
    "buy_vip": _env_int("XP_BUY_VIP", 500),                  # خرید اشتراک ویژه
    "gift_vip": _env_int("XP_GIFT_VIP", 300),                # هدیه دادن VIP
}

# ---------- آی‌دی فایل‌های رسانه‌ای (اختیاری) ----------
LEADERBOARD_PHOTO_ID = _env_str("LEADERBOARD_PHOTO_ID")
SCARY_PHOTO_ID = _env_str("SCARY_PHOTO_ID")
PROMO_WELCOME_NEW_PHOTO_ID = _env_str("PROMO_WELCOME_NEW_PHOTO_ID")
PROMO_WELCOME_OLD_PHOTO_ID = _env_str("PROMO_WELCOME_OLD_PHOTO_ID")
REVIEW_PHOTO_ID = _env_str("REVIEW_PHOTO_ID")
VIP_MAIN_PHOTO_ID = _env_str("VIP_MAIN_PHOTO_ID")
BUY_VIP_PHOTO_ID = _env_str("BUY_VIP_PHOTO_ID")
LEVEL_UP_PHOTO_ID = _env_str("LEVEL_UP_PHOTO_ID")
LINK_TUTORIAL_VIDEO_ID = _env_str("LINK_TUTORIAL_VIDEO_ID")
