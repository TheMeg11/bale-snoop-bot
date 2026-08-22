# -*- coding: utf-8 -*-
"""
tasks.py — تعریف ۲۰۰ ماموریت یکباره برای ربات فضول‌یاب

این ماموریت‌ها جدا از پاداش‌های تکرارشونده (XP_RECURRING در config.py) هستند.
هر ماموریت فقط یک‌بار به کاربر XP می‌دهد.

⚠️ مهم: برای جلوگیری از نمایش ماموریت‌های مرحله‌ای به‌صورت زنجیره‌ای،
از مفهوم "milestone" استفاده شده است. تسک‌های با یک نوع پیش‌شرط (مثل "فضول یکتا")
به‌صورت گروهی تعریف می‌شوند و فقط کمترین مرحله‌ای که هنوز انجام نشده نمایش داده می‌شود.

ساختار هر تسک:
{
    "id": "unique_id",         # شناسه یکتا
    "name": "نام ماموریت",     # نام کوتاه برای نمایش در لیست
    "desc": "توضیحات",         # توضیحات کامل (در popup نمایش داده می‌شود)
    "xp": 50,                  # پاداش XP
    "category": "easy",        # دسته: easy | medium | hard
    "group": "snoop_count",    # گروه milestone (اختیاری) — تسک‌های هم‌گروه فقط یک مرحله فعال دارند
    "threshold": 10,           # مقدار آستانه (برای گروه‌های عددی)
    "check": callable,         # تابع بررسی: (db, user_id) -> bool (آیا انجام شده؟)
}

ترتیب تسک‌ها در هر دسته از آسان به سخت مرتب شده است.
"""

# ====== تعریف ۲۰۰ ماموریت ======
# برچسب‌های دسته‌بندی:
#   easy   (آسان)   — ۶۰ تسک، XP بین ۲۰ تا ۱۰۰
#   medium (متوسط) — ۸۰ تسک، XP بین ۱۰۰ تا ۴۰۰
#   hard   (سخت)   — ۶۰ تسک، XP بین ۴۰۰ تا ۳۰۰۰

TASKS = [
    # ====== آسان (۶۰ تسک) ======
    {"id": "e01", "name": "اولین کلیک دریافت", "desc": "اولین کلیک روی لینک شما انجام شود.", "xp": 50, "category": "easy",
     "group": "click_count", "threshold": 1,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 1},
    {"id": "e02", "name": "۱۰ کلیک دریافتی", "desc": "مجموعاً ۱۰ کلیک روی لینک شما انجام شود.", "xp": 50, "category": "easy",
     "group": "click_count", "threshold": 10,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 10},
    {"id": "e03", "name": "۲۵ کلیک دریافتی", "desc": "مجموعاً ۲۵ کلیک روی لینک شما انجام شود.", "xp": 50, "category": "easy",
     "group": "click_count", "threshold": 25,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 25},
    {"id": "e04", "name": "۵۰ کلیک دریافتی", "desc": "مجموعاً ۵۰ کلیک روی لینک شما انجام شود.", "xp": 50, "category": "easy",
     "group": "click_count", "threshold": 50,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 50},

    {"id": "e05", "name": "اولین فضول گرفتار", "desc": "اولین فضول یکتا در دام شما بیفتد.", "xp": 50, "category": "easy",
     "group": "snoop_count", "threshold": 1,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 1},
    {"id": "e06", "name": "۳ فضول یکتا", "desc": "۳ فضول یکتا در دام شما بیفتند.", "xp": 50, "category": "easy",
     "group": "snoop_count", "threshold": 3,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 3},
    {"id": "e07", "name": "۵ فضول یکتا", "desc": "۵ فضول یکتا در دام شما بیفتند.", "xp": 50, "category": "easy",
     "group": "snoop_count", "threshold": 5,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 5},
    {"id": "e08", "name": "۸ فضول یکتا", "desc": "۸ فضول یکتا در دام شما بیفتند.", "xp": 60, "category": "easy",
     "group": "snoop_count", "threshold": 8,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 8},


    {"id": "e13", "name": "تنظیم لقب", "desc": "برای یکی از فضول‌هایتان یک لقب تنظیم کنید.", "xp": 50, "category": "easy",
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] > 0},
    {"id": "e14", "name": "۳ لقب به فضول‌ها", "desc": "به ۳ فضول مختلف لقب بدهید.", "xp": 50, "category": "easy",
     "group": "nickname_count", "threshold": 3,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 3},

    {"id": "e15", "name": "تنظیم متن خوش‌آمدگویی", "desc": "یک متن خوش‌آمدگویی برای فضول‌ها تنظیم کنید (VIP).", "xp": 50, "category": "easy",
     "check": lambda db, uid: db.get_welcome_text(uid) is not None},
    {"id": "e16", "name": "تنظیم عکس خوش‌آمدگویی", "desc": "یک عکس خوش‌آمدگویی برای فضول‌ها تنظیم کنید (VIP).", "xp": 50, "category": "easy",
     "check": lambda db, uid: db.get_welcome_photo(uid) is not None},
    {"id": "e17", "name": "تنظیم نقاب کارآگاهی", "desc": "یک نقاب کارآگاهی تنظیم کنید (VIP).", "xp": 50, "category": "easy",
     "check": lambda db, uid: db.get_user_mask(uid) is not None},

    {"id": "e18", "name": "۱ پیام ناشناس ارسال", "desc": "یک پیام ناشناس به یکی از فضول‌ها بفرستید.", "xp": 50, "category": "easy",
     "group": "anon_sent", "threshold": 1,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 1},

    {"id": "e19", "name": "۱ روز فعالیت", "desc": "حداقل یک روز از ثبت‌نام شما بگذرد.", "xp": 50, "category": "easy",
     "group": "days_active", "threshold": 1,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 1},
    {"id": "e20", "name": "۳ روز فعالیت", "desc": "حداقل ۳ روز از ثبت‌نام شما بگذرد.", "xp": 50, "category": "easy",
     "group": "days_active", "threshold": 3,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 3},
    {"id": "e21", "name": "۷ روز فعالیت", "desc": "حداقل ۷ روز از ثبت‌نام شما بگذرد.", "xp": 50, "category": "easy",
     "group": "days_active", "threshold": 7,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 7},

    {"id": "e22", "name": "۵۰ پیام دریافتی ناشناس", "desc": "۵۰ پیام ناشناس از دیگران دریافت کنید.", "xp": 80, "category": "easy",
     "group": "anon_received", "threshold": 50,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE receiver_id=?", (uid,)).fetchone()[0] >= 50},
    {"id": "e23", "name": "۱۰ بار بی‌صدا کردن", "desc": "نوتیفیکیشن ۱۰ فضول مختلف را قطع کنید.", "xp": 100, "category": "easy",
     "group": "mute_count", "threshold": 10,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM muted_snoops WHERE owner_id=?", (uid,)).fetchone()[0] >= 10},
    {"id": "e24", "name": "۱۰ بار بلاک ناشناس", "desc": "۱۰ کاربر را از پیام ناشناس بلاک کنید.", "xp": 100, "category": "easy",
     "group": "block_count", "threshold": 10,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM blocked_anon WHERE blocker_id=?", (uid,)).fetchone()[0] >= 10},
    {"id": "e25", "name": "تنظیم کامل پروفایل VIP", "desc": "همزمان متن، عکس و نقاب تنظیم کنید.", "xp": 100, "category": "easy",
     "check": lambda db, uid: db.get_welcome_text(uid) is not None and db.get_welcome_photo(uid) is not None and db.get_user_mask(uid) is not None},

    {"id": "e26", "name": "اولین ورود روزانه", "desc": "اولین بار، XP ورود روزانه را دریافت کنید.", "xp": 50, "category": "easy",
     "check": lambda db, uid: db.conn.execute("SELECT last_active_date FROM users WHERE user_id=?", (uid,)).fetchone()[0] is not None},

    {"id": "e27", "name": "بی‌صدا کردن ۱ فضول", "desc": "نوتیفیکیشن یک فضول مزاحم را قطع کنید.", "xp": 50, "category": "easy",
     "group": "mute_count", "threshold": 1,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM muted_snoops WHERE owner_id=?", (uid,)).fetchone()[0] >= 1},
    {"id": "e28", "name": "بلاک ۱ کاربر ناشناس", "desc": "یک کاربر را از ارسال پیام ناشناس بلاک کنید.", "xp": 50, "category": "easy",
     "group": "block_count", "threshold": 1,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM blocked_anon WHERE blocker_id=?", (uid,)).fetchone()[0] >= 1},

    {"id": "e29", "name": "۱ کد هدیه استفاده", "desc": "یک کد هدیه فعال کنید.", "xp": 100, "category": "easy",
     "group": "gift_used", "threshold": 1,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 1},
    {"id": "e30", "name": "۲ کد هدیه استفاده", "desc": "۲ کد هدیه فعال کنید.", "xp": 100, "category": "easy",
     "group": "gift_used", "threshold": 2,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 2},

    # ----- تسک‌های آسان اضافی (۳۱-۶۰) -----
    {"id": "e31", "name": "اولین خرید VIP", "desc": "اولین بار اشتراک VIP بخرید.", "xp": 150, "category": "easy",
     "group": "vip_purchase", "threshold": 1,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 1},
    {"id": "e32", "name": "اولین هدیه VIP", "desc": "اولین بار VIP به دیگری هدیه دهید.", "xp": 100, "category": "easy",
     "group": "vip_gift", "threshold": 1,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 1},

    # کلیک‌های بیشتر (با threshold های جدید)
    {"id": "e33", "name": "۷۵ کلیک دریافتی", "desc": "مجموعاً ۷۵ کلیک روی لینک شما انجام شود.", "xp": 60, "category": "easy",
     "group": "click_count", "threshold": 75,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 75},
    {"id": "e34", "name": "۱۰۰ کلیک دریافتی", "desc": "مجموعاً ۱۰۰ کلیک روی لینک شما انجام شود.", "xp": 70, "category": "easy",
     "group": "click_count", "threshold": 100,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 100},

    # فضول‌های یکتای بیشتر
    {"id": "e35", "name": "۱۰ فضول یکتا", "desc": "۱۰ فضول یکتا در دام شما بیفتند.", "xp": 80, "category": "easy",
     "group": "snoop_count", "threshold": 10,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 10},

    # دعوت‌های بیشتر

    # پیام ناشناس
    {"id": "e37", "name": "۵ پیام ناشناس", "desc": "۵ پیام ناشناس به فضول‌ها بفرستید.", "xp": 70, "category": "easy",
     "group": "anon_sent", "threshold": 5,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 5},

    # لقب
    {"id": "e38", "name": "۵ لقب به فضول‌ها", "desc": "به ۵ فضول مختلف لقب بدهید.", "xp": 80, "category": "easy",
     "group": "nickname_count", "threshold": 5,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 5},

    # روزهای فعالیت بیشتر
    {"id": "e39", "name": "۱۰ روز فعالیت", "desc": "حداقل ۱۰ روز از ثبت‌نام شما بگذرد.", "xp": 60, "category": "easy",
     "group": "days_active", "threshold": 10,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 10},

    # تنظیمات مختلف
    {"id": "e40", "name": "تنظیم پروفایل کامل", "desc": "هم متن و هم عکس خوش‌آمدگویی را تنظیم کنید.", "xp": 100, "category": "easy",
     "check": lambda db, uid: db.get_welcome_text(uid) is not None and db.get_welcome_photo(uid) is not None},

    # تسک‌های متفرقه آسان
    {"id": "e41", "name": "۲۵ پیام دریافتی ناشناس", "desc": "۲۵ پیام ناشناس از دیگران دریافت کنید.", "xp": 60, "category": "easy",
     "group": "anon_received", "threshold": 25,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE receiver_id=?", (uid,)).fetchone()[0] >= 25},
    {"id": "e42", "name": "۵ پیام دریافتی ناشناس", "desc": "۵ پیام ناشناس از دیگران دریافت کنید.", "xp": 50, "category": "easy",
     "group": "anon_received", "threshold": 5,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE receiver_id=?", (uid,)).fetchone()[0] >= 5},
    {"id": "e43", "name": "اولین پیام دریافتی ناشناس", "desc": "اولین پیام ناشناس از دیگری دریافت کنید.", "xp": 50, "category": "easy",
     "group": "anon_received", "threshold": 1,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE receiver_id=?", (uid,)).fetchone()[0] >= 1},

    # کلیک‌های اضافی
    {"id": "e44", "name": "۱۵۰ کلیک دریافتی", "desc": "مجموعاً ۱۵۰ کلیک روی لینک شما انجام شود.", "xp": 80, "category": "easy",
     "group": "click_count", "threshold": 150,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 150},

    # فضول یکتای بیشتر
    {"id": "e45", "name": "۱۲ فضول یکتا", "desc": "۱۲ فضول یکتا در دام شما بیفتند.", "xp": 90, "category": "easy",
     "group": "snoop_count", "threshold": 12,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 12},

    # دعوت بیشتر

    # پیام ناشناس
    {"id": "e47", "name": "۱۰ پیام ناشناس", "desc": "۱۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 100, "category": "easy",
     "group": "anon_sent", "threshold": 10,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 10},

    # لقب بیشتر
    {"id": "e48", "name": "۷ لقب به فضول‌ها", "desc": "به ۷ فضول مختلف لقب بدهید.", "xp": 90, "category": "easy",
     "group": "nickname_count", "threshold": 7,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 7},

    # روز فعالیت
    {"id": "e49", "name": "۱۴ روز فعالیت", "desc": "حداقل ۱۴ روز از ثبت‌نام شما بگذرد.", "xp": 80, "category": "easy",
     "group": "days_active", "threshold": 14,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 14},

    # بی‌صدا کردن بیشتر
    {"id": "e50", "name": "بی‌صدا کردن ۲ فضول", "desc": "نوتیفیکیشن ۲ فضول مزاحم را قطع کنید.", "xp": 70, "category": "easy",
     "group": "mute_count", "threshold": 2,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM muted_snoops WHERE owner_id=?", (uid,)).fetchone()[0] >= 2},

    # بلاک بیشتر
    {"id": "e51", "name": "بلاک ۲ کاربر ناشناس", "desc": "۲ کاربر را از ارسال پیام ناشناس بلاک کنید.", "xp": 70, "category": "easy",
     "group": "block_count", "threshold": 2,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM blocked_anon WHERE blocker_id=?", (uid,)).fetchone()[0] >= 2},

    # کد هدیه بیشتر
    {"id": "e52", "name": "۳ کد هدیه استفاده", "desc": "۳ کد هدیه فعال کنید.", "xp": 100, "category": "easy",
     "group": "gift_used", "threshold": 3,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 3},

    # خرید VIP بیشتر
    {"id": "e53", "name": "۲ خرید VIP", "desc": "۲ بار اشتراک VIP بخرید.", "xp": 100, "category": "easy",
     "group": "vip_purchase", "threshold": 2,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 2},

    # هدیه VIP بیشتر
    {"id": "e54", "name": "۲ هدیه VIP", "desc": "۲ بار VIP به دیگران هدیه دهید.", "xp": 100, "category": "easy",
     "group": "vip_gift", "threshold": 2,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 2},

    # کلیک بیشتر
    {"id": "e55", "name": "۲۰۰ کلیک دریافتی", "desc": "مجموعاً ۲۰۰ کلیک روی لینک شما انجام شود.", "xp": 90, "category": "easy",
     "group": "click_count", "threshold": 200,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 200},

    # فضول یکتای بیشتر
    {"id": "e56", "name": "۱۵ فضول یکتا", "desc": "۱۵ فضول یکتا در دام شما بیفتند.", "xp": 100, "category": "easy",
     "group": "snoop_count", "threshold": 15,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 15},

    # دعوت بیشتر

    # لقب بیشتر
    {"id": "e58", "name": "۱۰ لقب به فضول‌ها", "desc": "به ۱۰ فضول مختلف لقب بدهید.", "xp": 100, "category": "easy",
     "group": "nickname_count", "threshold": 10,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 10},

    # روز فعالیت
    {"id": "e59", "name": "۲۱ روز فعالیت", "desc": "حداقل ۲۱ روز از ثبت‌نام شما بگذرد.", "xp": 100, "category": "easy",
     "group": "days_active", "threshold": 21,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 21},

    # پیام ناشناس
    {"id": "e60", "name": "۱۵ پیام ناشناس", "desc": "۱۵ پیام ناشناس به فضول‌ها بفرستید.", "xp": 100, "category": "easy",
     "group": "anon_sent", "threshold": 15,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 15},

    # ====== متوسط (۸۰ تسک) ======
    # فضول یکتا (مراحل بعدی)
    {"id": "m01", "name": "۲۰ فضول یکتا", "desc": "۲۰ فضول یکتا در دام شما بیفتند.", "xp": 150, "category": "medium",
     "group": "snoop_count", "threshold": 20,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 20},
    {"id": "m02", "name": "۲۵ فضول یکتا", "desc": "۲۵ فضول یکتا در دام شما بیفتند.", "xp": 170, "category": "medium",
     "group": "snoop_count", "threshold": 25,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 25},
    {"id": "m03", "name": "۳۰ فضول یکتا", "desc": "۳۰ فضول یکتا در دام شما بیفتند.", "xp": 200, "category": "medium",
     "group": "snoop_count", "threshold": 30,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 30},
    {"id": "m04", "name": "۳۵ فضول یکتا", "desc": "۳۵ فضول یکتا در دام شما بیفتند.", "xp": 220, "category": "medium",
     "group": "snoop_count", "threshold": 35,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 35},
    {"id": "m05", "name": "۴۰ فضول یکتا", "desc": "۴۰ فضول یکتا در دام شما بیفتند.", "xp": 250, "category": "medium",
     "group": "snoop_count", "threshold": 40,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 40},
    {"id": "m06", "name": "۴۵ فضول یکتا", "desc": "۴۵ فضول یکتا در دام شما بیفتند.", "xp": 270, "category": "medium",
     "group": "snoop_count", "threshold": 45,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 45},
    {"id": "m07", "name": "۵۰ فضول یکتا", "desc": "۵۰ فضول یکتا در دام شما بیفتند.", "xp": 300, "category": "medium",
     "group": "snoop_count", "threshold": 50,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 50},

    # دعوت موفق (مراحل بعدی)

    # کلیک دریافتی
    {"id": "m14", "name": "۳۰۰ کلیک دریافتی", "desc": "مجموعاً ۳۰۰ کلیک روی لینک شما انجام شود.", "xp": 200, "category": "medium",
     "group": "click_count", "threshold": 300,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 300},
    {"id": "m15", "name": "۴۰۰ کلیک دریافتی", "desc": "مجموعاً ۴۰۰ کلیک روی لینک شما انجام شود.", "xp": 250, "category": "medium",
     "group": "click_count", "threshold": 400,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 400},
    {"id": "m16", "name": "۵۰۰ کلیک دریافتی", "desc": "مجموعاً ۵۰۰ کلیک روی لینک شما انجام شود.", "xp": 300, "category": "medium",
     "group": "click_count", "threshold": 500,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 500},
    {"id": "m17", "name": "۶۰۰ کلیک دریافتی", "desc": "مجموعاً ۶۰۰ کلیک روی لینک شما انجام شود.", "xp": 320, "category": "medium",
     "group": "click_count", "threshold": 600,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 600},
    {"id": "m18", "name": "۷۰۰ کلیک دریافتی", "desc": "مجموعاً ۷۰۰ کلیک روی لینک شما انجام شود.", "xp": 350, "category": "medium",
     "group": "click_count", "threshold": 700,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 700},

    # خرید VIP
    {"id": "m19", "name": "۳ خرید VIP", "desc": "۳ بار اشتراک VIP بخرید.", "xp": 250, "category": "medium",
     "group": "vip_purchase", "threshold": 3,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 3},
    {"id": "m20", "name": "۴ خرید VIP", "desc": "۴ بار اشتراک VIP بخرید.", "xp": 280, "category": "medium",
     "group": "vip_purchase", "threshold": 4,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 4},
    {"id": "m21", "name": "۵ خرید VIP", "desc": "۵ بار اشتراک VIP بخرید.", "xp": 320, "category": "medium",
     "group": "vip_purchase", "threshold": 5,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 5},
    {"id": "m22", "name": "۶ خرید VIP", "desc": "۶ بار اشتراک VIP بخرید.", "xp": 350, "category": "medium",
     "group": "vip_purchase", "threshold": 6,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 6},

    # هدیه VIP
    {"id": "m23", "name": "۳ هدیه VIP", "desc": "۳ بار VIP به دیگران هدیه دهید.", "xp": 200, "category": "medium",
     "group": "vip_gift", "threshold": 3,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 3},
    {"id": "m24", "name": "۴ هدیه VIP", "desc": "۴ بار VIP به دیگران هدیه دهید.", "xp": 250, "category": "medium",
     "group": "vip_gift", "threshold": 4,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 4},
    {"id": "m25", "name": "۵ هدیه VIP", "desc": "۵ بار VIP به دیگران هدیه دهید.", "xp": 300, "category": "medium",
     "group": "vip_gift", "threshold": 5,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 5},

    # پیام ناشناس
    {"id": "m26", "name": "۲۵ پیام ناشناس", "desc": "۲۵ پیام ناشناس به فضول‌ها بفرستید.", "xp": 250, "category": "medium",
     "group": "anon_sent", "threshold": 25,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 25},
    {"id": "m27", "name": "۵۰ پیام ناشناس", "desc": "۵۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 350, "category": "medium",
     "group": "anon_sent", "threshold": 50,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 50},

    # لقب
    {"id": "m28", "name": "۱۵ لقب به فضول‌ها", "desc": "به ۱۵ فضول مختلف لقب بدهید.", "xp": 250, "category": "medium",
     "group": "nickname_count", "threshold": 15,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 15},
    {"id": "m29", "name": "۲۰ لقب به فضول‌ها", "desc": "به ۲۰ فضول مختلف لقب بدهید.", "xp": 300, "category": "medium",
     "group": "nickname_count", "threshold": 20,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 20},

    # روز فعالیت
    {"id": "m30", "name": "۳۰ روز فعالیت", "desc": "حداقل ۳۰ روز از ثبت‌نام شما بگذرد.", "xp": 200, "category": "medium",
     "group": "days_active", "threshold": 30,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 30},
    {"id": "m31", "name": "۴۵ روز فعالیت", "desc": "حداقل ۴۵ روز از ثبت‌نام شما بگذرد.", "xp": 250, "category": "medium",
     "group": "days_active", "threshold": 45,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 45},
    {"id": "m32", "name": "۶۰ روز فعالیت", "desc": "حداقل ۶۰ روز از ثبت‌نام شما بگذرد.", "xp": 300, "category": "medium",
     "group": "days_active", "threshold": 60,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 60},

    # کد هدیه
    {"id": "m33", "name": "۵ کد هدیه استفاده", "desc": "۵ کد هدیه فعال کنید.", "xp": 200, "category": "medium",
     "group": "gift_used", "threshold": 5,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 5},
    {"id": "m34", "name": "۷ کد هدیه استفاده", "desc": "۷ کد هدیه فعال کنید.", "xp": 250, "category": "medium",
     "group": "gift_used", "threshold": 7,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 7},
    {"id": "m35", "name": "۱۰ کد هدیه استفاده", "desc": "۱۰ کد هدیه فعال کنید.", "xp": 300, "category": "medium",
     "group": "gift_used", "threshold": 10,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 10},

    # بی‌صدا و بلاک
    {"id": "m36", "name": "بی‌صدا کردن ۵ فضول", "desc": "نوتیفیکیشن ۵ فضول مزاحم را قطع کنید.", "xp": 150, "category": "medium",
     "group": "mute_count", "threshold": 5,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM muted_snoops WHERE owner_id=?", (uid,)).fetchone()[0] >= 5},
    {"id": "m37", "name": "بلاک ۵ کاربر ناشناس", "desc": "۵ کاربر را از ارسال پیام ناشناس بلاک کنید.", "xp": 150, "category": "medium",
     "group": "block_count", "threshold": 5,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM blocked_anon WHERE blocker_id=?", (uid,)).fetchone()[0] >= 5},

    # ----- تسک‌های متوسط اضافی (۳۸-۸۰) -----
    # کلیک دریافتی
    {"id": "m38", "name": "۸۰۰ کلیک دریافتی", "desc": "مجموعاً ۸۰۰ کلیک روی لینک شما انجام شود.", "xp": 380, "category": "medium",
     "group": "click_count", "threshold": 800,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 800},
    {"id": "m39", "name": "۹۰۰ کلیک دریافتی", "desc": "مجموعاً ۹۰۰ کلیک روی لینک شما انجام شود.", "xp": 400, "category": "medium",
     "group": "click_count", "threshold": 900,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 900},

    # دعوت موفق

    # فضول یکتا
    {"id": "m41", "name": "۵۵ فضول یکتا", "desc": "۵۵ فضول یکتا در دام شما بیفتند.", "xp": 320, "category": "medium",
     "group": "snoop_count", "threshold": 55,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 55},
    {"id": "m42", "name": "۶۰ فضول یکتا", "desc": "۶۰ فضول یکتا در دام شما بیفتند.", "xp": 350, "category": "medium",
     "group": "snoop_count", "threshold": 60,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 60},
    {"id": "m43", "name": "۶۵ فضول یکتا", "desc": "۶۵ فضول یکتا در دام شما بیفتند.", "xp": 380, "category": "medium",
     "group": "snoop_count", "threshold": 65,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 65},

    # خرید VIP
    {"id": "m44", "name": "۷ خرید VIP", "desc": "۷ بار اشتراک VIP بخرید.", "xp": 380, "category": "medium",
     "group": "vip_purchase", "threshold": 7,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 7},
    {"id": "m45", "name": "۸ خرید VIP", "desc": "۸ بار اشتراک VIP بخرید.", "xp": 400, "category": "medium",
     "group": "vip_purchase", "threshold": 8,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 8},

    # هدیه VIP
    {"id": "m46", "name": "۶ هدیه VIP", "desc": "۶ بار VIP به دیگران هدیه دهید.", "xp": 320, "category": "medium",
     "group": "vip_gift", "threshold": 6,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 6},

    # پیام ناشناس
    {"id": "m47", "name": "۷۵ پیام ناشناس", "desc": "۷۵ پیام ناشناس به فضول‌ها بفرستید.", "xp": 380, "category": "medium",
     "group": "anon_sent", "threshold": 75,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 75},

    # لقب
    {"id": "m48", "name": "۲۵ لقب به فضول‌ها", "desc": "به ۲۵ فضول مختلف لقب بدهید.", "xp": 350, "category": "medium",
     "group": "nickname_count", "threshold": 25,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 25},

    # روز فعالیت
    {"id": "m49", "name": "۷۵ روز فعالیت", "desc": "حداقل ۷۵ روز از ثبت‌نام شما بگذرد.", "xp": 320, "category": "medium",
     "group": "days_active", "threshold": 75,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 75},
    {"id": "m50", "name": "۹۰ روز فعالیت", "desc": "حداقل ۹۰ روز از ثبت‌نام شما بگذرد.", "xp": 380, "category": "medium",
     "group": "days_active", "threshold": 90,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 90},

    # کد هدیه
    {"id": "m51", "name": "۱۲ کد هدیه استفاده", "desc": "۱۲ کد هدیه فعال کنید.", "xp": 320, "category": "medium",
     "group": "gift_used", "threshold": 12,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 12},

    # بی‌صدا و بلاک بیشتر
    {"id": "m52", "name": "بی‌صدا کردن ۲۰ فضول", "desc": "نوتیفیکیشن ۲۰ فضول مزاحم را قطع کنید.", "xp": 200, "category": "medium",
     "group": "mute_count", "threshold": 20,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM muted_snoops WHERE owner_id=?", (uid,)).fetchone()[0] >= 20},
    {"id": "m53", "name": "بلاک ۲۰ کاربر ناشناس", "desc": "۲۰ کاربر را از ارسال پیام ناشناس بلاک کنید.", "xp": 200, "category": "medium",
     "group": "block_count", "threshold": 20,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM blocked_anon WHERE blocker_id=?", (uid,)).fetchone()[0] >= 20},

    # کلیک دریافتی
    {"id": "m54", "name": "۱۵۰۰ کلیک دریافتی", "desc": "مجموعاً ۱۵۰۰ کلیک روی لینک شما انجام شود.", "xp": 380, "category": "medium",
     "group": "click_count", "threshold": 1500,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 1500},

    # دعوت

    # فضول
    {"id": "m56", "name": "۷۰ فضول یکتا", "desc": "۷۰ فضول یکتا در دام شما بیفتند.", "xp": 380, "category": "medium",
     "group": "snoop_count", "threshold": 70,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 70},

    # خرید VIP
    {"id": "m57", "name": "۹ خرید VIP", "desc": "۹ بار اشتراک VIP بخرید.", "xp": 380, "category": "medium",
     "group": "vip_purchase", "threshold": 9,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 9},

    # هدیه VIP
    {"id": "m58", "name": "۷ هدیه VIP", "desc": "۷ بار VIP به دیگران هدیه دهید.", "xp": 350, "category": "medium",
     "group": "vip_gift", "threshold": 7,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 7},

    # پیام ناشناس
    {"id": "m59", "name": "۱۰۰ پیام ناشناس", "desc": "۱۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 400, "category": "medium",
     "group": "anon_sent", "threshold": 100,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 100},

    # لقب
    {"id": "m60", "name": "۳۰ لقب به فضول‌ها", "desc": "به ۳۰ فضول مختلف لقب بدهید.", "xp": 380, "category": "medium",
     "group": "nickname_count", "threshold": 30,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 30},

    # روز فعالیت
    {"id": "m61", "name": "۱۰۰ روز فعالیت", "desc": "حداقل ۱۰۰ روز از ثبت‌نام شما بگذرد.", "xp": 350, "category": "medium",
     "group": "days_active", "threshold": 100,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 100},

    # کد هدیه
    {"id": "m62", "name": "۱۵ کد هدیه استفاده", "desc": "۱۵ کد هدیه فعال کنید.", "xp": 350, "category": "medium",
     "group": "gift_used", "threshold": 15,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 15},

    # کلیک دریافتی
    {"id": "m63", "name": "۲۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۲۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 400, "category": "medium",
     "group": "click_count", "threshold": 2000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 2000},

    # دعوت

    # فضول
    {"id": "m65", "name": "۸۰ فضول یکتا", "desc": "۸۰ فضول یکتا در دام شما بیفتند.", "xp": 400, "category": "medium",
     "group": "snoop_count", "threshold": 80,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 80},

    # خرید VIP
    {"id": "m66", "name": "۱۰ خرید VIP", "desc": "۱۰ بار اشتراک VIP بخرید.", "xp": 400, "category": "medium",
     "group": "vip_purchase", "threshold": 10,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 10},

    # هدیه VIP
    {"id": "m67", "name": "۸ هدیه VIP", "desc": "۸ بار VIP به دیگران هدیه دهید.", "xp": 380, "category": "medium",
     "group": "vip_gift", "threshold": 8,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 8},

    # پیام ناشناس
    {"id": "m68", "name": "۱۵۰ پیام ناشناس", "desc": "۱۵۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 400, "category": "medium",
     "group": "anon_sent", "threshold": 150,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 150},

    # لقب
    {"id": "m69", "name": "۴۰ لقب به فضول‌ها", "desc": "به ۴۰ فضول مختلف لقب بدهید.", "xp": 400, "category": "medium",
     "group": "nickname_count", "threshold": 40,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 40},

    # روز فعالیت
    {"id": "m70", "name": "۱۲۰ روز فعالیت", "desc": "حداقل ۱۲۰ روز از ثبت‌نام شما بگذرد.", "xp": 380, "category": "medium",
     "group": "days_active", "threshold": 120,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 120},

    # کد هدیه
    {"id": "m71", "name": "۲۰ کد هدیه استفاده", "desc": "۲۰ کد هدیه فعال کنید.", "xp": 400, "category": "medium",
     "group": "gift_used", "threshold": 20,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 20},

    # کلیک
    {"id": "m72", "name": "۳۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۳۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 400, "category": "medium",
     "group": "click_count", "threshold": 3000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 3000},

    # دعوت

    # فضول
    {"id": "m74", "name": "۹۰ فضول یکتا", "desc": "۹۰ فضول یکتا در دام شما بیفتند.", "xp": 400, "category": "medium",
     "group": "snoop_count", "threshold": 90,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 90},

    # خرید VIP
    {"id": "m75", "name": "۱۲ خرید VIP", "desc": "۱۲ بار اشتراک VIP بخرید.", "xp": 400, "category": "medium",
     "group": "vip_purchase", "threshold": 12,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 12},

    # هدیه VIP
    {"id": "m76", "name": "۱۰ هدیه VIP", "desc": "۱۰ بار VIP به دیگران هدیه دهید.", "xp": 400, "category": "medium",
     "group": "vip_gift", "threshold": 10,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 10},

    # پیام ناشناس
    {"id": "m77", "name": "۲۰۰ پیام ناشناس", "desc": "۲۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 400, "category": "medium",
     "group": "anon_sent", "threshold": 200,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 200},

    # لقب
    {"id": "m78", "name": "۵۰ لقب به فضول‌ها", "desc": "به ۵۰ فضول مختلف لقب بدهید.", "xp": 400, "category": "medium",
     "group": "nickname_count", "threshold": 50,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 50},

    # روز فعالیت
    {"id": "m79", "name": "۱۵۰ روز فعالیت", "desc": "حداقل ۱۵۰ روز از ثبت‌نام شما بگذرد.", "xp": 400, "category": "medium",
     "group": "days_active", "threshold": 150,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 150},

    # کد هدیه
    {"id": "m80", "name": "۲۵ کد هدیه استفاده", "desc": "۲۵ کد هدیه فعال کنید.", "xp": 400, "category": "medium",
     "group": "gift_used", "threshold": 25,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 25},

    # ====== سخت (۶۰ تسک) ======
    # فضول یکتا
    {"id": "h01", "name": "۱۰۰ فضول یکتا", "desc": "۱۰۰ فضول یکتا در دام شما بیفتند.", "xp": 800, "category": "hard",
     "group": "snoop_count", "threshold": 100,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 100},
    {"id": "h02", "name": "۱۲۰ فضول یکتا", "desc": "۱۲۰ فضول یکتا در دام شما بیفتند.", "xp": 900, "category": "hard",
     "group": "snoop_count", "threshold": 120,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 120},
    {"id": "h03", "name": "۱۵۰ فضول یکتا", "desc": "۱۵۰ فضول یکتا در دام شما بیفتند.", "xp": 1000, "category": "hard",
     "group": "snoop_count", "threshold": 150,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 150},
    {"id": "h04", "name": "۲۰۰ فضول یکتا", "desc": "۲۰۰ فضول یکتا در دام شما بیفتند.", "xp": 1500, "category": "hard",
     "group": "snoop_count", "threshold": 200,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 200},
    {"id": "h05", "name": "۲۵۰ فضول یکتا", "desc": "۲۵۰ فضول یکتا در دام شما بیفتند.", "xp": 1800, "category": "hard",
     "group": "snoop_count", "threshold": 250,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 250},
    {"id": "h06", "name": "۳۰۰ فضول یکتا", "desc": "۳۰۰ فضول یکتا در دام شما بیفتند.", "xp": 2000, "category": "hard",
     "group": "snoop_count", "threshold": 300,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 300},
    {"id": "h07", "name": "۴۰۰ فضول یکتا", "desc": "۴۰۰ فضول یکتا در دام شما بیفتند.", "xp": 2500, "category": "hard",
     "group": "snoop_count", "threshold": 400,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 400},
    {"id": "h08", "name": "۵۰۰ فضول یکتا", "desc": "۵۰۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 500,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 500},

    # دعوت موفق

    # کلیک دریافتی
    {"id": "h14", "name": "۵۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۵۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 2000, "category": "hard",
     "group": "click_count", "threshold": 5000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 5000},
    {"id": "h15", "name": "۱۰۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۱۰۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 3000, "category": "hard",
     "group": "click_count", "threshold": 10000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 10000},

    # خرید VIP
    {"id": "h16", "name": "۲۰ خرید VIP", "desc": "۲۰ بار اشتراک VIP بخرید.", "xp": 1000, "category": "hard",
     "group": "vip_purchase", "threshold": 20,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 20},
    {"id": "h17", "name": "۳۰ خرید VIP", "desc": "۳۰ بار اشتراک VIP بخرید.", "xp": 1500, "category": "hard",
     "group": "vip_purchase", "threshold": 30,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 30},
    {"id": "h18", "name": "۵۰ خرید VIP", "desc": "۵۰ بار اشتراک VIP بخرید.", "xp": 2000, "category": "hard",
     "group": "vip_purchase", "threshold": 50,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 50},

    # هدیه VIP
    {"id": "h19", "name": "۲۰ هدیه VIP", "desc": "۲۰ بار VIP به دیگران هدیه دهید.", "xp": 1500, "category": "hard",
     "group": "vip_gift", "threshold": 20,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 20},
    {"id": "h20", "name": "۳۰ هدیه VIP", "desc": "۳۰ بار VIP به دیگران هدیه دهید.", "xp": 2000, "category": "hard",
     "group": "vip_gift", "threshold": 30,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 30},

    # پیام ناشناس
    {"id": "h21", "name": "۵۰۰ پیام ناشناس", "desc": "۵۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 1500, "category": "hard",
     "group": "anon_sent", "threshold": 500,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 500},
    {"id": "h22", "name": "۱۰۰۰ پیام ناشناس", "desc": "۱۰۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 2000, "category": "hard",
     "group": "anon_sent", "threshold": 1000,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 1000},

    # لقب
    {"id": "h23", "name": "۱۰۰ لقب به فضول‌ها", "desc": "به ۱۰۰ فضول مختلف لقب بدهید.", "xp": 1500, "category": "hard",
     "group": "nickname_count", "threshold": 100,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 100},

    # روز فعالیت
    {"id": "h24", "name": "۳۶۵ روز فعالیت", "desc": "حداقل ۳۶۵ روز (یک سال) از ثبت‌نام شما بگذرد.", "xp": 2000, "category": "hard",
     "group": "days_active", "threshold": 365,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 365},

    # کد هدیه
    {"id": "h25", "name": "۵۰ کد هدیه استفاده", "desc": "۵۰ کد هدیه فعال کنید.", "xp": 1500, "category": "hard",
     "group": "gift_used", "threshold": 50,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 50},

    # ----- تسک‌های سخت اضافی (۲۶-۶۰) -----
    # فضول یکتا
    {"id": "h26", "name": "۶۰۰ فضول یکتا", "desc": "۶۰۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 600,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 600},
    {"id": "h27", "name": "۷۵۰ فضول یکتا", "desc": "۷۵۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 750,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 750},
    {"id": "h28", "name": "۱۰۰۰ فضول یکتا", "desc": "۱۰۰۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 1000,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 1000},

    # دعوت موفق

    # کلیک دریافتی
    {"id": "h31", "name": "۲۰۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۲۰۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 3000, "category": "hard",
     "group": "click_count", "threshold": 20000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 20000},
    {"id": "h32", "name": "۵۰۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۵۰۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 3000, "category": "hard",
     "group": "click_count", "threshold": 50000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 50000},

    # خرید VIP
    {"id": "h33", "name": "۱۰۰ خرید VIP", "desc": "۱۰۰ بار اشتراک VIP بخرید.", "xp": 3000, "category": "hard",
     "group": "vip_purchase", "threshold": 100,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 100},

    # هدیه VIP
    {"id": "h34", "name": "۵۰ هدیه VIP", "desc": "۵۰ بار VIP به دیگران هدیه دهید.", "xp": 3000, "category": "hard",
     "group": "vip_gift", "threshold": 50,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 50},

    # پیام ناشناس
    {"id": "h35", "name": "۲۰۰۰ پیام ناشناس", "desc": "۲۰۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 3000, "category": "hard",
     "group": "anon_sent", "threshold": 2000,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 2000},

    # لقب
    {"id": "h36", "name": "۲۰۰ لقب به فضول‌ها", "desc": "به ۲۰۰ فضول مختلف لقب بدهید.", "xp": 3000, "category": "hard",
     "group": "nickname_count", "threshold": 200,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 200},

    # روز فعالیت
    {"id": "h37", "name": "۷۳۰ روز فعالیت", "desc": "حداقل ۷۳۰ روز (دو سال) از ثبت‌نام شما بگذرد.", "xp": 3000, "category": "hard",
     "group": "days_active", "threshold": 730,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 730},

    # کد هدیه
    {"id": "h38", "name": "۱۰۰ کد هدیه استفاده", "desc": "۱۰۰ کد هدیه فعال کنید.", "xp": 3000, "category": "hard",
     "group": "gift_used", "threshold": 100,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 100},

    # ترکیبی‌ها (سخت)
    {"id": "h40", "name": "کارآگاه تمام‌عیار", "desc": "۱۰۰ فضول یکتا و ۱۰۰۰ کلیک دریافتی داشته باشید.", "xp": 2500, "category": "hard",
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 100 and db.get_clicks_count(uid) >= 1000},
    {"id": "h41", "name": "حامی بزرگ", "desc": "۲۰ بار خرید VIP و ۲۰ بار هدیه VIP داشته باشید.", "xp": 2500, "category": "hard",
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 20 and db.get_user_gift_count(uid) >= 20},

    # تسک‌های طولانی‌مدت

    # پیام ناشناس
    {"id": "h43", "name": "۳۰۰۰ پیام ناشناس", "desc": "۳۰۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 3000, "category": "hard",
     "group": "anon_sent", "threshold": 3000,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 3000},

    # لقب
    {"id": "h44", "name": "۳۰۰ لقب به فضول‌ها", "desc": "به ۳۰۰ فضول مختلف لقب بدهید.", "xp": 3000, "category": "hard",
     "group": "nickname_count", "threshold": 300,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 300},

    # روز فعالیت
    {"id": "h45", "name": "۱۰۰۰ روز فعالیت", "desc": "حداقل ۱۰۰۰ روز (بیش از ۲ سال) از ثبت‌نام شما بگذرد.", "xp": 3000, "category": "hard",
     "group": "days_active", "threshold": 1000,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 1000},

    # فضول
    {"id": "h46", "name": "۱۵۰۰ فضول یکتا", "desc": "۱۵۰۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 1500,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 1500},
    {"id": "h47", "name": "۲۰۰۰ فضول یکتا", "desc": "۲۰۰۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 2000,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 2000},

    # دعوت

    # کلیک
    {"id": "h49", "name": "۱۰۰۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۱۰۰۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 3000, "category": "hard",
     "group": "click_count", "threshold": 100000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 100000},

    # خرید VIP
    {"id": "h50", "name": "۲۰۰ خرید VIP", "desc": "۲۰۰ بار اشتراک VIP بخرید.", "xp": 3000, "category": "hard",
     "group": "vip_purchase", "threshold": 200,
     "check": lambda db, uid: db.get_user_purchase_count(uid) >= 200},

    # هدیه VIP
    {"id": "h51", "name": "۱۰۰ هدیه VIP", "desc": "۱۰۰ بار VIP به دیگران هدیه دهید.", "xp": 3000, "category": "hard",
     "group": "vip_gift", "threshold": 100,
     "check": lambda db, uid: db.get_user_gift_count(uid) >= 100},

    # پیام ناشناس
    {"id": "h52", "name": "۵۰۰۰ پیام ناشناس", "desc": "۵۰۰۰ پیام ناشناس به فضول‌ها بفرستید.", "xp": 3000, "category": "hard",
     "group": "anon_sent", "threshold": 5000,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM anon_logs WHERE sender_id=?", (uid,)).fetchone()[0] >= 5000},

    # لقب
    {"id": "h53", "name": "۵۰۰ لقب به فضول‌ها", "desc": "به ۵۰۰ فضول مختلف لقب بدهید.", "xp": 3000, "category": "hard",
     "group": "nickname_count", "threshold": 500,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM nicknames WHERE owner_id=?", (uid,)).fetchone()[0] >= 500},

    # روز فعالیت
    {"id": "h54", "name": "۲۰۰۰ روز فعالیت", "desc": "حداقل ۲۰۰۰ روز (بیش از ۵ سال) از ثبت‌نام شما بگذرد.", "xp": 3000, "category": "hard",
     "group": "days_active", "threshold": 2000,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 2000},

    # کد هدیه
    {"id": "h55", "name": "۲۰۰ کد هدیه استفاده", "desc": "۲۰۰ کد هدیه فعال کنید.", "xp": 3000, "category": "hard",
     "group": "gift_used", "threshold": 200,
     "check": lambda db, uid: db.conn.execute("SELECT COUNT(*) FROM gift_usage WHERE user_id=?", (uid,)).fetchone()[0] >= 200},

    # ترکیبی‌های سخت

    # فضول
    {"id": "h57", "name": "۳۰۰۰ فضول یکتا", "desc": "۳۰۰۰ فضول یکتا در دام شما بیفتند.", "xp": 3000, "category": "hard",
     "group": "snoop_count", "threshold": 3000,
     "check": lambda db, uid: db.get_distinct_snoop_count(uid) >= 3000},

    # دعوت

    # کلیک
    {"id": "h59", "name": "۲۰۰۰۰۰ کلیک دریافتی", "desc": "مجموعاً ۲۰۰۰۰۰ کلیک روی لینک شما انجام شود.", "xp": 3000, "category": "hard",
     "group": "click_count", "threshold": 200000,
     "check": lambda db, uid: db.get_clicks_count(uid) >= 200000},

    # روز فعالیت
    {"id": "h60", "name": "۳۶۵۰ روز فعالیت", "desc": "حداقل ۳۶۵۰ روز (۱۰ سال) از ثبت‌نام شما بگذرد.", "xp": 3000, "category": "hard",
     "group": "days_active", "threshold": 3650,
     "check": lambda db, uid: db.conn.execute("SELECT julianday('now') - julianday(created_at) FROM users WHERE user_id=?", (uid,)).fetchone()[0] >= 3650},
]

# ====== ثابت‌های کمکی ======
CATEGORY_INFO = {
    "easy":   {"name": "آسان",   "emoji": "🟢"},
    "medium": {"name": "متوسط",  "emoji": "🟡"},
    "hard":   {"name": "سخت",    "emoji": "🔴"},
}

def get_tasks_by_category(category):
    return [t for t in TASKS if t["category"] == category]

def get_task_by_id(task_id):
    for t in TASKS:
        if t["id"] == task_id:
            return t
    return None

def get_active_milestones(tasks_list):
    """برای هر group، فقط کمترین threshold که هنوز انجام نشده رو برمی‌گردانه.
    تسک‌های بدون group همگی فعال هستند.
    خروجی: list of task dicts که باید نمایش داده شوند."""
    # گروه‌بندی بر اساس group
    groups = {}
    no_group = []
    for t in tasks_list:
        if "group" in t and t["group"]:
            groups.setdefault(t["group"], []).append(t)
        else:
            no_group.append(t)

    result = list(no_group)
    for group_name, group_tasks in groups.items():
        # مرتب‌سازی بر اساس threshold
        sorted_tasks = sorted(group_tasks, key=lambda x: x.get("threshold", 0))
        # اولین تسکی که هنوز انجام نشده رو پیدا کن
        # (این تابع فقط فیلتر می‌کنه؛ چک کردن done بودن در فراخوانی انجام می‌شود)
        # اما اینجا فقط یک تسک از هر گروه برمی‌گردانیم (اولین)
        if sorted_tasks:
            result.append(sorted_tasks[0])
    return result

TOTAL_TASKS = len(TASKS)
