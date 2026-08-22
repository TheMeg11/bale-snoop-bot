import telebot
from telebot import apihelper, types
import os, sqlite3, datetime, time, threading, re, string, requests, random, logging, sys
from collections import defaultdict, deque
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# اضافه کردن مسیر site-packages کاربر برای دسترسی به jdatetime
# (روی Railway/لوکال jdatetime از requirements.txt نصب می‌شود؛ مسیر هاردکد حذف شد)
try:
    import jdatetime
    JDATE_OK = True
except ImportError:
    JDATE_OK = False
    print("⚠️ jdatetime نصب نیست — تاریخ‌ها میلادی نمایش داده می‌شوند.")
import texts
import tasks as tasks_module
import config
from telebot.apihelper import ApiTelegramException

# ====== لاگ‌گیری پایه ======
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ====== مسیرها ======
BASE_DIR = Path(__file__).parent
# مسیر دیتابیس: روی Railway با Volume متصل به /data، متغیر DB_PATH=/data/bot_data.db ست می‌شود
# تا دیتای کاربران با هر ری‌دیپلوی از بین نرود.
DB_PATH = Path(config.DB_PATH)
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ====== بارگذاری تنظیمات از config.py ======
TOKEN = config.BOT_TOKEN
ADMIN_ID = config.ADMIN_ID
PROVIDER_TOKEN = config.PROVIDER_TOKEN
VIP_PRICES = dict(config.VIP_PRICES_DEFAULT)  # کپی برای امکان تغییر در runtime

# فایل آی‌دی‌ها از config.py
LEADERBOARD_PHOTO_ID = config.LEADERBOARD_PHOTO_ID
SCARY_PHOTO_ID = config.SCARY_PHOTO_ID
PROMO_WELCOME_NEW_PHOTO_ID = config.PROMO_WELCOME_NEW_PHOTO_ID
PROMO_WELCOME_OLD_PHOTO_ID = config.PROMO_WELCOME_OLD_PHOTO_ID
REVIEW_PHOTO_ID = config.REVIEW_PHOTO_ID
VIP_MAIN_PHOTO_ID = config.VIP_MAIN_PHOTO_ID
BUY_VIP_PHOTO_ID = config.BUY_VIP_PHOTO_ID
LEVEL_UP_PHOTO_ID = config.LEVEL_UP_PHOTO_ID
LINK_TUTORIAL_VIDEO_ID = config.LINK_TUTORIAL_VIDEO_ID

# تنظیمات پخش همگانی
BROADCAST_WORKERS = config.BROADCAST_WORKERS
BROADCAST_BATCH_SIZE = config.BROADCAST_BATCH_SIZE
BROADCAST_BATCH_DELAY = config.BROADCAST_BATCH_DELAY
BROADCAST_TIMEOUT = config.BROADCAST_TIMEOUT

# تنظیمات XP
XP_BONUS_ONE_TIME = config.XP_BONUS_ONE_TIME
XP_RECURRING = config.XP_RECURRING

if not TOKEN or TOKEN == "TOKEN_ROBAT_RA_INJA_BENAVISID" or not ADMIN_ID:
    print("❌ توکن یا شناسه ادمین نامعتبر. لطفاً فایل config.py را ویرایش کنید.")
    exit(1)

apihelper.API_URL = "https://tapi.bale.ai/bot{0}/{1}"
bot = telebot.TeleBot(TOKEN, parse_mode=None)

# get_me در شروع اجرا با retry — تا خطای موقت شبکه/استارتاپ باعث کرش-لوپ روی Railway نشود
_bot_info = None
for _attempt in range(1, 6):
    try:
        _bot_info = bot.get_me()
        break
    except Exception as _e:
        logger.warning(f"get_me تلاش {_attempt}/5 ناموفق: {_e} — ۵ ثانیه دیگر...")
        time.sleep(5)
if _bot_info is None:
    raise SystemExit("❌ اتصال به API بله برقرار نشد. توکن را بررسی کنید.")
BOT_USERNAME = _bot_info.username

# ====== سازگاری با Bale: حذف reply_parameters از همه درخواست‌ها ======
# Bale API از پارامتر reply_parameters (معرفی‌شده در Telegram Bot API 7.0) پشتیبانی نمی‌کند.
# نسخه‌های جدید pyTelegramBotAPI (4.x+) به‌صورت پیش‌فرض از reply_parameters استفاده می‌کنند
# (حتی اگه reply_to_message_id پاس بدی، بازم به reply_parameters تبدیلش می‌کنه).
# این باعث خطای 404 "no such group or user" در Bale می‌شود.
# این patch همه درخواست‌ها رو intercept می‌کنه و reply_parameters رو به reply_to_message_id تبدیل می‌کنه.
import json as _json_module
_original_make_request = apihelper._make_request
def _bale_make_request(token, method_url, params=None, method='post'):
    """Patch برای سازگاری با Bale: reply_parameters → reply_to_message_id در همه درخواست‌ها."""
    if params and 'reply_parameters' in params:
        try:
            rp = params['reply_parameters']
            if isinstance(rp, str):
                rp_dict = _json_module.loads(rp)
            elif hasattr(rp, 'to_json'):
                rp_dict = _json_module.loads(rp.to_json())
            elif isinstance(rp, dict):
                rp_dict = rp
            else:
                rp_dict = {}
            # فقط message_id رو بردار و به‌عنوان reply_to_message_id اضافه کن
            if 'message_id' in rp_dict and 'reply_to_message_id' not in params:
                params['reply_to_message_id'] = rp_dict['message_id']
            params.pop('reply_parameters', None)
        except Exception:
            # اگه پارس نشد، فقط حذفش کن تا Bale به مشکل نخوره
            params.pop('reply_parameters', None)
    return _original_make_request(token, method_url, params=params, method=method)
apihelper._make_request = _bale_make_request

# ====== ابزارهای اعداد فارسی و تاریخ شمسی ======
PERSIAN_DIGITS = '۰۱۲۳۴۵۶۷۸۹'

def to_persian_digits(text):
    """تبدیل ارقام انگلیسی به فارسی در یک رشته."""
    if text is None:
        return ""
    s = str(text)
    for i, d in enumerate('0123456789'):
        s = s.replace(d, PERSIAN_DIGITS[i])
    return s

def to_persian_int(n):
    """تبدیل عدد به رشته فارسی با جداکنندهٔ هزارگان."""
    try:
        return to_persian_digits(f"{int(n):,}")
    except (ValueError, TypeError):
        return to_persian_digits(str(n))

def shamsi_date(dt=None, with_time=False):
    """تاریخ شمسی. اگر dt نبود، الان."""
    if not JDATE_OK:
        # Fallback: میلادی
        if dt is None: dt = datetime.datetime.now()
        if with_time:
            return dt.strftime("%Y/%m/%d - %H:%M")
        return dt.strftime("%Y/%m/%d")
    if dt is None:
        dt = datetime.datetime.now()
    try:
        if isinstance(dt, str):
            return dt  # از قبل تبدیل شده
        g_date = jdatetime.date.fromgregorian(date=dt.date() if hasattr(dt, 'date') else dt)
        if with_time and hasattr(dt, 'strftime'):
            return to_persian_digits(f"{g_date.strftime('%Y/%m/%d')} - {dt.strftime('%H:%M')}")
        return to_persian_digits(g_date.strftime('%Y/%m/%d'))
    except Exception as e:
        logger.error(f"shamsi_date error: {e}")
        return dt.strftime("%Y/%m/%d") if hasattr(dt, 'strftime') else str(dt)

def shamsi_today_str():
    """تاریخ شمسی امروز به صورت رشته (برای گزارش روزانه)."""
    if not JDATE_OK:
        return datetime.date.today().isoformat()
    g_today = datetime.date.today()
    j_today = jdatetime.date.fromgregorian(date=g_today)
    return to_persian_digits(j_today.strftime('%Y/%m/%d'))

def fmt_amount_rial(amount):
    """فرمت مبالغ به ریال فارسی."""
    return to_persian_int(amount) + " ریال"

def fmt_amount_toman(amount):
    """فرمت مبالغ به تومان فارسی."""
    return to_persian_int(amount // 10) + " تومان"

def pct_change(new, old):
    """محاسبهٔ درصد تغییر (new نسبت به old). برمی‌گرداند (علامت, عدد)."""
    if old == 0:
        # رفع باگ: استایل یکسان با بقیه موارد — استفاده از ایموجی
        return ('📈', '∞') if new > 0 else ('📉', '0')
    change = int(round((new - old) / old * 100))
    sign = '📈' if change >= 0 else '📉'
    return sign, to_persian_digits(abs(change))

def fetch_channel_info(channel_identifier):
    """اطلاعات کانال را از API دریافت می‌کند و شناسهٔ مناسب برای get_chat_member را برمی‌گرداند."""
    url = f"https://tapi.bale.ai/bot{TOKEN}/getChat"
    try:
        resp = requests.post(url, json={"chat_id": channel_identifier}, timeout=5)
        data = resp.json()
        if data.get("ok"):
            chat = data["result"]
            name = chat.get("title", str(channel_identifier))
            link = chat.get("invite_link", None)
            raw_id = chat.get("id")
            # تبدیل شناسه به فرمت صحیح منفی
            api_id = str(raw_id) if raw_id is not None else str(channel_identifier)
            return {"name": name, "link": link, "api_id": api_id}
    except Exception as e:
        logger.warning(f"fetch_channel_info error: {e}")
    return {"name": str(channel_identifier), "link": None, "api_id": channel_identifier}

# ====== پایگاه داده ======
class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def sync_user_profile(self, user_id, first_name, username):
        with self._lock:
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.conn.execute(
                "INSERT OR IGNORE INTO users (user_id, first_name, username, created_at) VALUES (?,?,?,?)",
                (user_id, first_name or "بی‌نام", username or "", now)
            )
            self.conn.execute(
                "UPDATE users SET first_name=?, username=? WHERE user_id=?",
                (first_name or "بی‌نام", username or "", user_id)
            )
            # اگه کاربر قبلاً ربات رو بلاک کرده بود (blocked_bot=1) ولی حالا پیام فرستاده،
            # یعنی آنبلاک کرده — پس فلگ رو پاک کن تا دوباره به صف پخش برگرده
            self.conn.execute(
                "UPDATE users SET blocked_bot=0 WHERE user_id=? AND blocked_bot=1",
                (user_id,)
            )
            self.conn.commit()

    def _migrate(self):
        with self._lock:
            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    blocked INTEGER DEFAULT 0,
                    welcome_text TEXT,
                    welcome_photo TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT
                );
                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    clicker_id INTEGER NOT NULL,
                    clicker_name TEXT,
                    clicker_username TEXT,
                    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_new_user INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS nicknames (
                    owner_id INTEGER NOT NULL,
                    clicker_id INTEGER NOT NULL,
                    nickname TEXT,
                    PRIMARY KEY (owner_id, clicker_id)
                );
                CREATE TABLE IF NOT EXISTS vip (
                    user_id INTEGER PRIMARY KEY,
                    expire_date TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS blocked_anon (
                    blocker_id INTEGER NOT NULL,
                    blocked_id INTEGER NOT NULL,
                    PRIMARY KEY (blocker_id, blocked_id)
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    days INTEGER DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS anon_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    receiver_id INTEGER NOT NULL,
                    text TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS gift_codes (
                    code TEXT PRIMARY KEY,
                    days INTEGER NOT NULL,
                    max_uses INTEGER NOT NULL,
                    used_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS gift_usage (
                    code TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (code, user_id)
                );
                CREATE TABLE IF NOT EXISTS user_mask (
                    user_id INTEGER PRIMARY KEY,
                    emoji TEXT,
                    mask_text TEXT
                );
                CREATE TABLE IF NOT EXISTS muted_snoops (
                    owner_id INTEGER NOT NULL,
                    clicker_id INTEGER NOT NULL,
                    PRIMARY KEY (owner_id, clicker_id)
                );
                CREATE TABLE IF NOT EXISTS channel_joins (
                    user_id INTEGER NOT NULL,
                    channel_username TEXT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, channel_username)
                );
                CREATE TABLE IF NOT EXISTS pending_snoops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    clicker_id INTEGER NOT NULL,
                    display_name TEXT,
                    t TEXT,
                    vip_owner INTEGER DEFAULT 0,
                    clicker_username TEXT,
                    repeat INTEGER DEFAULT 1,
                    gift_vip_given INTEGER DEFAULT 0,
                    photo_file_id TEXT
                );
                CREATE TABLE IF NOT EXISTS forced_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT UNIQUE NOT NULL,
                    channel_name TEXT,
                    invite_link TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_report_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_report_date TEXT
                );
                INSERT OR IGNORE INTO daily_report_state (id, last_report_date) VALUES (1, NULL);
                CREATE TABLE IF NOT EXISTS callback_stats (
                    callback_data TEXT PRIMARY KEY,
                    click_count INTEGER DEFAULT 0,
                    last_clicked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            ''')
            self.conn.commit()
            self._ensure_columns()
            self._create_indexes()

    def reset_warnings(self, user_id):
        with self._lock:
            self.conn.execute("UPDATE users SET warning_count = 0 WHERE user_id=?", (user_id,))
            row = self.conn.execute("SELECT blocked, blocked_by_admin FROM users WHERE user_id=?", (user_id,)).fetchone()
            if row and row['blocked'] and row['blocked_by_admin']:
                self.conn.execute("UPDATE users SET blocked=0, blocked_by_admin=0 WHERE user_id=?", (user_id,))
            self.conn.commit()

    def _ensure_columns(self):
        # موارد کاملاً بی‌خطر
        try: self.conn.execute("SELECT welcome_photo FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN welcome_photo TEXT"); self.conn.commit()
        try: self.conn.execute("SELECT is_new_user FROM clicks LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE clicks ADD COLUMN is_new_user INTEGER DEFAULT 0"); self.conn.commit()
        try: self.conn.execute("SELECT created_at FROM users LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
            self.conn.commit()
        try: self.conn.execute("SELECT source FROM users LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute("ALTER TABLE users ADD COLUMN source TEXT")
            self.conn.commit()
        # حذف: بخش خطرناک vip کاملاً پاک شده است (DROP TABLE آنجا انجام نمی‌شود)
        try: self.conn.execute("SELECT blocked_by_admin FROM users LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute("ALTER TABLE users ADD COLUMN blocked_by_admin INTEGER DEFAULT 0")
            self.conn.commit()
        try: self.conn.execute("SELECT warning_count FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN warning_count INTEGER DEFAULT 0"); self.conn.commit()
        try: self.conn.execute("SELECT hide_leaderboard FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN hide_leaderboard INTEGER DEFAULT 0"); self.conn.commit()
        # ستون‌های سیستم XP و سطح‌بندی
        try: self.conn.execute("SELECT xp FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0"); self.conn.commit()
        try: self.conn.execute("SELECT level_cached FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN level_cached INTEGER DEFAULT 1"); self.conn.commit()
        try: self.conn.execute("SELECT last_active_date FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN last_active_date TEXT"); self.conn.commit()
        # جدول ردیابی XP یکباره‌ها (جلوگیری از اعطای دوباره)
        try: self.conn.execute("SELECT user_id FROM xp_bonuses LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute('''
                CREATE TABLE IF NOT EXISTS xp_bonuses (
                    user_id INTEGER NOT NULL,
                    bonus_type TEXT NOT NULL,
                    awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, bonus_type)
                )
            ''')
            self.conn.commit()
        # ستون last_broadcast_blocked — کاربرانی که ربات رو بلاک کرده‌اند (برای حذف از پخش همگانی)
        try: self.conn.execute("SELECT blocked_bot FROM users LIMIT 1")
        except sqlite3.OperationalError: self.conn.execute("ALTER TABLE users ADD COLUMN blocked_bot INTEGER DEFAULT 0"); self.conn.commit()

    def increment_warning(self, user_id):
        with self._lock:
            self.conn.execute("UPDATE users SET warning_count = COALESCE(warning_count, 0) + 1 WHERE user_id=?", (user_id,))
            self.conn.commit()
            return self.conn.execute("SELECT warning_count FROM users WHERE user_id=?", (user_id,)).fetchone()['warning_count']

    def get_last_anon_log(self, sender_id, receiver_id):
        with self._lock:
            row = self.conn.execute(
                "SELECT text FROM anon_logs WHERE sender_id=? AND receiver_id=? ORDER BY timestamp DESC LIMIT 1",
                (sender_id, receiver_id)
            ).fetchone()
            return row['text'] if row else ""

    def get_user_warning_count(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT warning_count FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row['warning_count'] if row else 0

    def set_hide_leaderboard(self, user_id, hide):
        with self._lock:
            self.conn.execute("UPDATE users SET hide_leaderboard=? WHERE user_id=?", (1 if hide else 0, user_id))
            self.conn.commit()

    def is_hide_leaderboard(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT hide_leaderboard FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row and row['hide_leaderboard'] == 1

    def _create_indexes(self):
        with self._lock:
            self.conn.executescript('''
                CREATE INDEX IF NOT EXISTS idx_clicks_owner ON clicks(owner_id);
                CREATE INDEX IF NOT EXISTS idx_clicks_clicker ON clicks(clicker_id);
                CREATE INDEX IF NOT EXISTS idx_clicks_date ON clicks(clicked_at);
                CREATE INDEX IF NOT EXISTS idx_vip_expire ON vip(expire_date);
                CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
            ''')
            self.conn.commit()

    # ---------- متدهای اصلی ----------
    def add_click(self, owner_id, clicker_id, name, username, is_new=False):
        with self._lock:
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.conn.execute(
                "INSERT OR IGNORE INTO users (user_id, first_name, username, created_at) VALUES (?,?,?,?)",
                (owner_id, "", "", now))
            self.conn.execute(
                "INSERT OR IGNORE INTO users (user_id, first_name, username, created_at) VALUES (?,?,?,?)",
                (clicker_id, name, username, now))
            self.conn.execute(
                "UPDATE users SET first_name=?, username=? WHERE user_id=?",
                (name, username, clicker_id))
            self.conn.execute(
                "INSERT INTO clicks (owner_id, clicker_id, clicker_name, clicker_username, is_new_user) VALUES (?,?,?,?,?)",
                (owner_id, clicker_id, name, username, 1 if is_new else 0))
            self.conn.commit()
            return self.conn.execute(
                "SELECT COUNT(*) as cnt FROM clicks WHERE owner_id=? AND clicker_id=?",
                (owner_id, clicker_id)).fetchone()['cnt']

    def get_clicks_count(self, owner_id):
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) as cnt FROM clicks WHERE owner_id=?", (owner_id,)).fetchone()
            return row['cnt'] if row else 0

    def get_today_clicks_count(self, owner_id):
        with self._lock:
            today = datetime.date.today().isoformat()
            row = self.conn.execute("SELECT COUNT(*) as cnt FROM clicks WHERE owner_id=? AND date(clicked_at)=?", (owner_id, today)).fetchone()
            return row['cnt'] if row else 0

    def get_snoops(self, owner_id):
        with self._lock:
            q = '''SELECT c.clicker_id, c.clicker_name as name, c.clicker_username as username,
                         COUNT(*) as count, n.nickname
                  FROM clicks c LEFT JOIN nicknames n ON c.owner_id=n.owner_id AND c.clicker_id=n.clicker_id
                  WHERE c.owner_id=? GROUP BY c.clicker_id ORDER BY count DESC'''
            return [dict(r) for r in self.conn.execute(q, (owner_id,)).fetchall()]

    def set_nickname(self, owner_id, clicker_id, nick):
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO nicknames (owner_id, clicker_id, nickname) VALUES (?,?,?)", (owner_id, clicker_id, nick))
            self.conn.commit()

    def is_vip(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT expire_date FROM vip WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                return False
            try:
                exp = datetime.datetime.strptime(row['expire_date'], "%Y-%m-%d").date()
                if exp >= datetime.date.today():
                    return True
                # رفع باگ: رکورد VIP منقضی‌شده را حذف نکنیم — باعث می‌شود آمار (get_vip_stats) دقیق باشد
                # و admin بتواند تاریخچه VIPهای منقضی‌شده را ببیند. فقط False برمی‌گردانیم.
                return False
            except (ValueError, TypeError):
                return False

    def add_vip(self, user_id, days):
        with self._lock:
            row = self.conn.execute("SELECT expire_date FROM vip WHERE user_id=?", (user_id,)).fetchone()
            if row:
                try:
                    current_exp = datetime.datetime.strptime(row['expire_date'], "%Y-%m-%d").date()
                    if current_exp >= datetime.date.today(): new_exp = current_exp + datetime.timedelta(days=days)
                    else: new_exp = datetime.date.today() + datetime.timedelta(days=days)
                except: new_exp = datetime.date.today() + datetime.timedelta(days=days)
                self.conn.execute("UPDATE vip SET expire_date=? WHERE user_id=?", (new_exp.isoformat(), user_id))
            else:
                new_exp = datetime.date.today() + datetime.timedelta(days=days)
                self.conn.execute("INSERT INTO vip (user_id, expire_date) VALUES (?,?)", (user_id, new_exp.isoformat()))
            self.conn.commit()

    def get_vip_days_left(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT expire_date FROM vip WHERE user_id=?", (user_id,)).fetchone()
            if not row: return 0
            try:
                exp = datetime.datetime.strptime(row['expire_date'], "%Y-%m-%d").date()
                return max(0, (exp - datetime.date.today()).days)
            except (ValueError, TypeError):
                return 0

    def get_expiring_vips(self, days_left=1):
        with self._lock:
            target = (datetime.date.today() + datetime.timedelta(days=days_left)).isoformat()
            rows = self.conn.execute("SELECT user_id FROM vip WHERE expire_date = ?", (target,)).fetchall()
            return [r['user_id'] for r in rows]

    def block_user(self, user_id, by_admin=False):
        with self._lock:
            if by_admin:
                self.conn.execute("UPDATE users SET blocked=1, blocked_by_admin=1 WHERE user_id=?", (user_id,))
            else:
                self.conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (user_id,))
            self.conn.commit()

    def unblock_user(self, user_id):
        with self._lock:
            self.conn.execute("UPDATE users SET blocked=0, blocked_by_admin=0 WHERE user_id=?", (user_id,))
            self.conn.commit()

    def is_blocked(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT blocked FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row and row['blocked'] == 1

    def mark_user_blocked_bot(self, user_id):
        """کاربری که ربات را بلاک کرده (خطای 403 در ارسال) را علامت‌گذاری می‌کند."""
        with self._lock:
            self.conn.execute("UPDATE users SET blocked_bot=1 WHERE user_id=?", (user_id,))
            self.conn.commit()

    def unmark_user_blocked_bot(self, user_id):
        """کاربری که ربات را آنبلاک کرده را به صف پخش برمی‌گرداند.
        وقتی کاربر پیامی به ربات می‌فرستد، این متد صدا زده می‌شود."""
        with self._lock:
            self.conn.execute("UPDATE users SET blocked_bot=0 WHERE user_id=?", (user_id,))
            self.conn.commit()

    def get_broadcast_targets(self):
        """کاربرانی که واجد شرایط دریافت پخش همگانی هستند (بلاک نشده، حسابشان فعال است)."""
        with self._lock:
            return [r['user_id'] for r in self.conn.execute(
                "SELECT user_id FROM users WHERE (blocked=0 OR blocked IS NULL) AND (blocked_bot=0 OR blocked_bot IS NULL)"
            ).fetchall()]

    def set_welcome_text(self, user_id, text):
        with self._lock:
            self.conn.execute("UPDATE users SET welcome_text=? WHERE user_id=?", (text, user_id))
            self.conn.commit()

    def get_welcome_text(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT welcome_text FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row['welcome_text'] if row else None

    def set_welcome_photo(self, user_id, file_id):
        with self._lock:
            self.conn.execute("UPDATE users SET welcome_photo=? WHERE user_id=?", (file_id, user_id))
            self.conn.commit()

    def get_welcome_photo(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT welcome_photo FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row['welcome_photo'] if row else None

    def block_anon(self, blocker_id, blocked_id):
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO blocked_anon (blocker_id, blocked_id) VALUES (?,?)", (blocker_id, blocked_id))
            self.conn.commit()

    def unblock_anon(self, blocker_id, blocked_id):
        with self._lock:
            self.conn.execute("DELETE FROM blocked_anon WHERE blocker_id=? AND blocked_id=?", (blocker_id, blocked_id))
            self.conn.commit()

    def is_anon_blocked(self, blocker_id, blocked_id):
        with self._lock:
            row = self.conn.execute("SELECT 1 FROM blocked_anon WHERE blocker_id=? AND blocked_id=?", (blocker_id, blocked_id)).fetchone()
            return row is not None

    def search_users(self, query):
        with self._lock:
            if query.isdigit(): row = self.conn.execute("SELECT * FROM users WHERE user_id=?", (int(query),)).fetchone(); return [dict(row)] if row else []
            like = f"%{query}%"
            return [dict(r) for r in self.conn.execute("SELECT * FROM users WHERE first_name LIKE ? OR username LIKE ?", (like, like)).fetchall()]

    def get_active_users(self, include_blocked=False):
        with self._lock:
            if include_blocked:
                return [dict(r) for r in self.conn.execute("SELECT user_id FROM users").fetchall()]
            return [dict(r) for r in self.conn.execute("SELECT user_id FROM users WHERE blocked=0 OR blocked IS NULL").fetchall()]

    def get_user_detail(self, user_id):
        with self._lock:
            user = self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not user: return None
            total_clicks = self.conn.execute("SELECT COUNT(*) as cnt FROM clicks WHERE owner_id=?", (user_id,)).fetchone()['cnt']
            snoop_count = self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as cnt FROM clicks WHERE owner_id=?", (user_id,)).fetchone()['cnt']
            vip_row = self.conn.execute("SELECT expire_date FROM vip WHERE user_id=?", (user_id,)).fetchone()
            vip_status = "غیرفعال"
            if vip_row:
                try:
                    if datetime.datetime.strptime(vip_row['expire_date'], "%Y-%m-%d").date() >= datetime.date.today():
                        vip_status = "فعال"
                except (ValueError, TypeError):
                    pass
            return {'user': dict(user), 'total_clicks': total_clicks, 'snoop_count': snoop_count, 'vip_status': vip_status, 'vip_expire': vip_row['expire_date'] if vip_row else None}

    def get_all_users_paginated(self, offset=0, limit=20):
        """لیست کاربران — به ترتیب بیشترین فضول یکتا (بر اساس COUNT(DISTINCT clicker_id))."""
        with self._lock:
            # LEFT JOIN با clicks برای محاسبه تعداد فضول یکتا، سپس ORDER BY آن
            q = '''
                SELECT u.*, (
                    SELECT COUNT(DISTINCT c.clicker_id) FROM clicks c WHERE c.owner_id = u.user_id
                ) as snoop_count
                FROM users u
                ORDER BY snoop_count DESC, u.user_id ASC
                LIMIT ? OFFSET ?
            '''
            return [dict(r) for r in self.conn.execute(q, (limit, offset)).fetchall()]

    def count_all_users(self):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']

    def add_transaction(self, user_id, ttype, amount, days=0):
        with self._lock:
            self.conn.execute("INSERT INTO transactions (user_id, type, amount, days) VALUES (?,?,?,?)", (user_id, ttype, amount, days))
            self.conn.commit()

    def get_transactions_paginated(self, offset=0, limit=10):
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()]

    def count_transactions(self):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as cnt FROM transactions").fetchone()['cnt']

    def get_most_active_owners_by_unique(self, limit=10):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT c.owner_id, u.first_name, COUNT(DISTINCT c.clicker_id) as cnt FROM clicks c JOIN users u ON c.owner_id=u.user_id GROUP BY c.owner_id ORDER BY cnt DESC LIMIT ?", (limit,)).fetchall()]

    def get_leaderboard_top(self, limit=10):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT c.owner_id, u.first_name, COUNT(DISTINCT c.clicker_id) as cnt "
                "FROM clicks c JOIN users u ON c.owner_id=u.user_id "
                "WHERE u.hide_leaderboard = 0 AND u.blocked = 0 "
                "GROUP BY c.owner_id ORDER BY cnt DESC LIMIT ?", (limit,)).fetchall()]

    def get_user_rank_by_distinct(self, user_id):
        with self._lock:
            user_cnt = self.get_distinct_snoop_count(user_id)
            row = self.conn.execute(
                "SELECT COUNT(*) as higher FROM ("
                "SELECT owner_id, COUNT(DISTINCT clicker_id) as cnt FROM clicks GROUP BY owner_id"
                ") WHERE cnt > ?", (user_cnt,)).fetchone()
            return row['higher'] + 1

    def get_vip_stats(self):
        with self._lock:
            active = self.conn.execute("SELECT COUNT(*) as cnt FROM vip WHERE expire_date >= date('now')").fetchone()['cnt']
            expired = self.conn.execute("SELECT COUNT(*) as cnt FROM vip WHERE expire_date < date('now')").fetchone()['cnt']
            return active, expired

    def add_anon_log(self, sender, receiver, text):
        with self._lock:
            self.conn.execute("INSERT INTO anon_logs (sender_id, receiver_id, text) VALUES (?,?,?)", (sender, receiver, text))
            self.conn.commit()

    def get_anon_logs_paginated(self, offset=0, limit=10):
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM anon_logs ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()]

    def count_anon_logs(self):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as cnt FROM anon_logs").fetchone()['cnt']

    def create_gift_code(self, code, days, max_uses):
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO gift_codes (code, days, max_uses, used_count) VALUES (?, ?, ?, 0)", (code, days, max_uses))
            self.conn.commit()

    # اصلاح بحرانی ۲: redeem_gift اتمی بدون commit اضافی در add_vip
    def redeem_gift(self, code, user_id):
        with self._lock:
            row = self.conn.execute("SELECT * FROM gift_codes WHERE code=?", (code,)).fetchone()
            if not row: return False, "کد نامعتبر است."
            if row['used_count'] >= row['max_uses']: return False, "ظرفیت استفاده از این کد به پایان رسیده."
            usage = self.conn.execute("SELECT 1 FROM gift_usage WHERE code=? AND user_id=?", (code, user_id)).fetchone()
            if usage: return False, "شما قبلاً این کد را استفاده کرده‌اید."
            # افزایش مصرف
            self.conn.execute("UPDATE gift_codes SET used_count = used_count + 1 WHERE code=?", (code,))
            # ثبت استفاده
            self.conn.execute("INSERT INTO gift_usage (code, user_id) VALUES (?,?)", (code, user_id))
            # اعمال مستقیم VIP (بدون add_vip که commit جداگانه دارد)
            days = row['days']
            current = self.conn.execute("SELECT expire_date FROM vip WHERE user_id=?", (user_id,)).fetchone()
            if current:
                try:
                    cur_exp = datetime.datetime.strptime(current['expire_date'], "%Y-%m-%d").date()
                    if cur_exp >= datetime.date.today():
                        new_exp = cur_exp + datetime.timedelta(days=days)
                    else:
                        new_exp = datetime.date.today() + datetime.timedelta(days=days)
                except:
                    new_exp = datetime.date.today() + datetime.timedelta(days=days)
                self.conn.execute("UPDATE vip SET expire_date=? WHERE user_id=?", (new_exp.isoformat(), user_id))
            else:
                new_exp = datetime.date.today() + datetime.timedelta(days=days)
                self.conn.execute("INSERT INTO vip (user_id, expire_date) VALUES (?,?)", (user_id, new_exp.isoformat()))
            self.conn.commit()
            return True, days

    def get_all_gift_codes(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM gift_codes ORDER BY created_at DESC").fetchall()]

    def delete_gift_code(self, code):
        """حذف یک کد هدیه (و استفاده‌های مربوط به آن)."""
        with self._lock:
            self.conn.execute("DELETE FROM gift_usage WHERE code=?", (code,))
            self.conn.execute("DELETE FROM gift_codes WHERE code=?", (code,))
            self.conn.commit()

    def is_new_user(self, user_id):
        with self._lock:
            return self.conn.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone() is None

    def set_user_source(self, user_id, source):
        with self._lock:
            self.conn.execute("UPDATE users SET source=? WHERE user_id=?", (source, user_id))
            self.conn.commit()

    def upsert_user_basic(self, user_id, first_name, username, source=None):
        """ثبت/به‌روزرسانی کاربر. مهم: source همیشه UPDATE می‌شه (حتی اگه کاربر از قبل وجود داشته باشه)."""
        with self._lock:
            now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if source:
                # اول INSERT (اگه کاربر جدید باشه)
                self.conn.execute(
                    "INSERT OR IGNORE INTO users (user_id, first_name, username, source, created_at) VALUES (?,?,?,?,?)",
                    (user_id, first_name, username, source, now))
                # بعد UPDATE صریح source (برای کاربرانی که از قبل ثبت شدن ولی source خالی دارن)
                self.conn.execute(
                    "UPDATE users SET source=? WHERE user_id=? AND (source IS NULL OR source='' OR source='organic')",
                    (source, user_id))
            else:
                self.conn.execute(
                    "INSERT OR IGNORE INTO users (user_id, first_name, username, created_at) VALUES (?,?,?,?)",
                    (user_id, first_name, username, now))
            self.conn.commit()

    def get_user_basic(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT first_name, username FROM users WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_all_vips(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT user_id, expire_date FROM vip ORDER BY expire_date").fetchall()]

    def get_active_vips_paginated(self, offset=0, limit=20):
        """گرفتن VIPهای فعال (expire_date >= today) با صفحه‌بندی + نام کاربر."""
        with self._lock:
            q = '''SELECT v.user_id, v.expire_date, u.first_name
                   FROM vip v
                   LEFT JOIN users u ON v.user_id = u.user_id
                   WHERE v.expire_date >= date('now')
                   ORDER BY v.expire_date DESC
                   LIMIT ? OFFSET ?'''
            return [dict(r) for r in self.conn.execute(q, (limit, offset)).fetchall()]

    def count_active_vips(self):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as c FROM vip WHERE expire_date >= date('now')").fetchone()['c']

    def log_callback_click(self, callback_data):
        """ثبت آمار کلیک روی یک دکمه اینلاین."""
        try:
            with self._lock:
                self.conn.execute(
                    "INSERT INTO callback_stats (callback_data, click_count, last_clicked) VALUES (?, 1, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(callback_data) DO UPDATE SET click_count = click_count + 1, last_clicked = CURRENT_TIMESTAMP",
                    (callback_data,)
                )
                self.conn.commit()
        except: pass

    def get_callback_stats(self, limit=20):
        """گرفتن پراستفاده‌ترین دکمه‌ها."""
        with self._lock:
            try:
                return [dict(r) for r in self.conn.execute(
                    "SELECT callback_data, click_count, last_clicked FROM callback_stats "
                    "ORDER BY click_count DESC LIMIT ?", (limit,)
                ).fetchall()]
            except:
                return []

    def get_recent_activities(self, user_id, limit=5):
        """گرفتن آخرین فعالیت‌های کاربر از داده‌های موجود (بدون جدول جدید).
        منابع: clicks (دریافتی), transactions (vip/gift_vip), xp_bonuses (تسک‌ها)."""
        activities = []
        with self._lock:
            # آخرین کلیک‌های دریافتی (max 2)
            rows = self.conn.execute(
                "SELECT clicker_name, clicked_at FROM clicks WHERE owner_id=? "
                "ORDER BY clicked_at DESC LIMIT 2", (user_id,)
            ).fetchall()
            for r in rows:
                name = r['clicker_name'] or 'ناشناس'
                activities.append({
                    'type': 'click',
                    'name': name,
                    'timestamp': r['clicked_at']
                })

            # آخرین خرید VIP (max 1)
            rows = self.conn.execute(
                "SELECT days, timestamp FROM transactions WHERE user_id=? AND type='vip' "
                "ORDER BY timestamp DESC LIMIT 1", (user_id,)
            ).fetchall()
            for r in rows:
                activities.append({
                    'type': 'vip',
                    'days': r['days'],
                    'timestamp': r['timestamp']
                })

            # آخرین هدیه VIP (max 1)
            rows = self.conn.execute(
                "SELECT days, timestamp FROM transactions WHERE user_id=? AND type='gift_vip' "
                "ORDER BY timestamp DESC LIMIT 1", (user_id,)
            ).fetchall()
            for r in rows:
                activities.append({
                    'type': 'gift',
                    'days': r['days'],
                    'timestamp': r['timestamp']
                })

            # آخرین تسک‌های تکمیل‌شده (max 1)
            rows = self.conn.execute(
                "SELECT bonus_type, awarded_at FROM xp_bonuses WHERE user_id=? AND bonus_type LIKE 'task_%' "
                "ORDER BY awarded_at DESC LIMIT 1", (user_id,)
            ).fetchall()
            for r in rows:
                task_id = r['bonus_type'].replace('task_', '')
                task = tasks_module.get_task_by_id(task_id)
                if task:
                    activities.append({
                        'type': 'task',
                        'task_name': task['name'],
                        'timestamp': r['awarded_at']
                    })

        # مرتب‌سازی بر اساس timestamp (نزولی)
        activities.sort(key=lambda x: x['timestamp'] or '', reverse=True)
        return activities[:limit]

    def mute_snoop(self, owner_id, clicker_id):
        with self._lock:
            self.conn.execute("INSERT OR IGNORE INTO muted_snoops (owner_id, clicker_id) VALUES (?,?)", (owner_id, clicker_id))
            self.conn.commit()

    def unmute_snoop(self, owner_id, clicker_id):
        with self._lock:
            self.conn.execute("DELETE FROM muted_snoops WHERE owner_id=? AND clicker_id=?", (owner_id, clicker_id))
            self.conn.commit()

    def is_snoop_muted(self, owner_id, clicker_id):
        with self._lock:
            row = self.conn.execute("SELECT 1 FROM muted_snoops WHERE owner_id=? AND clicker_id=?", (owner_id, clicker_id)).fetchone()
            return row is not None

    def get_user_invite_count(self, user_id):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as cnt FROM clicks WHERE owner_id=? AND is_new_user=1", (user_id,)).fetchone()['cnt']

    def get_user_purchase_count(self, user_id):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as cnt FROM transactions WHERE user_id=? AND type='vip'", (user_id,)).fetchone()['cnt']

    def get_user_gift_count(self, user_id):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) as cnt FROM transactions WHERE user_id=? AND type='gift_vip'", (user_id,)).fetchone()['cnt']

    def get_distinct_snoop_count(self, user_id):
        with self._lock:
            return self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as cnt FROM clicks WHERE owner_id=?", (user_id,)).fetchone()['cnt']

    def clean_old_anon_logs(self, days=30):
        with self._lock:
            self.conn.execute("DELETE FROM anon_logs WHERE julianday('now') - julianday(timestamp) > ?", (days,))
            self.conn.commit()

    def get_daily_stats(self):
        with self._lock:
            today = datetime.date.today().isoformat()
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

            # --- کاربران ---
            total_users = self.conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()['cnt']
            new_today = self.conn.execute("SELECT COUNT(*) as cnt FROM users WHERE date(created_at)=?", (today,)).fetchone()['cnt']
            new_yesterday = self.conn.execute("SELECT COUNT(*) as cnt FROM users WHERE date(created_at)=?", (yesterday,)).fetchone()['cnt']
            active_today = self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as cnt FROM clicks WHERE date(clicked_at)=?", (today,)).fetchone()['cnt']

            # نرخ بازگشت: کاربران فعال امروز که حداقل یک بار قبل از امروز هم کلیک کرده‌اند
            returning_today = self.conn.execute(
                "SELECT COUNT(DISTINCT clicker_id) as cnt FROM clicks WHERE date(clicked_at)=? AND clicker_id IN (SELECT DISTINCT clicker_id FROM clicks WHERE date(clicked_at) < ?)",
                (today, today)
            ).fetchone()['cnt']
            return_rate = f"{int((returning_today / active_today * 100) if active_today else 0)}%"

            # --- منابع ورود (جدید) ---
            organic = self.conn.execute("SELECT COUNT(*) as cnt FROM users WHERE source='organic'").fetchone()['cnt']
            welcome = self.conn.execute("SELECT COUNT(*) as cnt FROM users WHERE source='welcome'").fetchone()['cnt']
            referral = self.conn.execute("SELECT COUNT(*) as cnt FROM users WHERE source='referral'").fetchone()['cnt']

            # --- کلیک‌ها ---
            total_clicks = self.conn.execute("SELECT COUNT(*) as cnt FROM clicks").fetchone()['cnt']
            distinct_clickers = self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as cnt FROM clicks").fetchone()['cnt']
            trap_owners = self.conn.execute("SELECT COUNT(DISTINCT owner_id) as cnt FROM clicks").fetchone()['cnt']
            # میانگین کلیک ۷ روز
            avg_7 = self.conn.execute(
                "SELECT ROUND(COUNT(*) / 7.0, 1) as cnt FROM clicks WHERE clicked_at >= date('now','-7 days')"
            ).fetchone()['cnt']

            # --- VIP و درآمد ---
            active_vip = self.conn.execute("SELECT COUNT(*) as cnt FROM vip WHERE expire_date >= date('now')").fetchone()['cnt']
            total_revenue = self.conn.execute("SELECT COALESCE(SUM(amount),0) as cnt FROM transactions WHERE type IN ('vip','gift_vip')").fetchone()['cnt']
            revenue_today = self.conn.execute("SELECT COALESCE(SUM(amount),0) as cnt FROM transactions WHERE date(timestamp)=? AND type IN ('vip','gift_vip')", (today,)).fetchone()['cnt']
            tx_today = self.conn.execute("SELECT COUNT(*) as cnt FROM transactions WHERE date(timestamp)=? AND type IN ('vip','gift_vip')", (today,)).fetchone()['cnt']
            tx_total = self.conn.execute("SELECT COUNT(*) as cnt FROM transactions WHERE type IN ('vip','gift_vip')").fetchone()['cnt']

            # --- کدهای هدیه ---
            gift_created = self.conn.execute("SELECT COUNT(*) as cnt FROM gift_codes").fetchone()['cnt']
            gift_used = self.conn.execute("SELECT COALESCE(SUM(used_count),0) as cnt FROM gift_codes").fetchone()['cnt']

            # --- پیام‌های ناشناس ---
            anon_total = self.conn.execute("SELECT COUNT(*) as cnt FROM anon_logs").fetchone()['cnt']

            # --- بلاک‌شده‌ها ---
            total_banned = self.conn.execute("SELECT COUNT(*) as cnt FROM users WHERE blocked=1").fetchone()['cnt']

            # --- کانال‌های اجباری (تعداد و مجموع عضویت) ---
            channels = self.get_all_forced_channels()
            channels_count = len(channels)
            total_joins = sum(self.get_channel_join_count(ch['channel_id']) for ch in channels)

            return {
                'total_users': total_users,
                'new_today': new_today,
                'new_yesterday': new_yesterday,
                'active_today': active_today,
                'return_rate': return_rate,
                'organic': organic,
                'welcome': welcome,
                'referral': referral,
                'total_clicks': total_clicks,
                'distinct_clickers': distinct_clickers,
                'trap_owners': trap_owners,
                'avg_7': avg_7,
                'active_vip': active_vip,
                'total_revenue': total_revenue,
                'revenue_today': revenue_today,
                'tx_today': tx_today,
                'tx_total': tx_total,
                'gift_created': gift_created,
                'gift_used': gift_used,
                'anon_total': anon_total,
                'total_banned': total_banned,
                'channels_count': channels_count,
                'total_joins': total_joins,
            }

    def set_user_mask(self, user_id, emoji, mask_text):
        with self._lock:
            self.conn.execute("INSERT OR REPLACE INTO user_mask (user_id, emoji, mask_text) VALUES (?,?,?)", (user_id, emoji, mask_text))
            self.conn.commit()

    # ----- سیستم XP و سطح‌بندی -----
    # فرمول: XP لازم برای رفتن از سطح (L-1) به L = 100 × L
    # XP تجمعی تا سطح L = 100 × L × (L+1) / 2
    def get_user_xp(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT xp FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row['xp'] if row and row['xp'] is not None else 0

    def get_user_level_cached(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT level_cached FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row['level_cached'] if row and row['level_cached'] is not None else 1

    @staticmethod
    def level_from_xp(xp):
        """محاسبهٔ سطح از روی XP تجمعی."""
        if xp < 100:
            return 1
        # حل: 100×L×(L+1)/2 = xp → L² + L - 2*xp/100 = 0 → L = (-1 + √(1 + 8*xp/100)) / 2
        import math
        L = int((-1 + math.sqrt(1 + 8 * xp / 100)) / 2)
        if L < 1: L = 1
        if L > 50: L = 50
        return L

    @staticmethod
    def xp_for_level(level):
        """XP تجمعی لازم برای رسیدن به سطح level."""
        return 100 * level * (level + 1) // 2

    @staticmethod
    def xp_for_next_level(current_level):
        """XP کل لازم برای رسیدن از سطح فعلی به سطح بعدی."""
        if current_level >= 50:
            return None
        return Database.xp_for_level(current_level + 1)

    def add_xp(self, user_id, amount):
        """افزودن XP به کاربر و به‌روزرسانی level_cached. برمی‌گرداند (xp_new, level_new, level_old)."""
        with self._lock:
            row = self.conn.execute("SELECT xp, level_cached FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                return 0, 1, 1
            xp_old = row['xp'] if row['xp'] is not None else 0
            level_old = row['level_cached'] if row['level_cached'] is not None else 1
            xp_new = xp_old + amount
            level_new = self.level_from_xp(xp_new)
            self.conn.execute("UPDATE users SET xp=?, level_cached=? WHERE user_id=?", (xp_new, level_new, user_id))
            self.conn.commit()
            return xp_new, level_new, level_old

    def has_bonus(self, user_id, bonus_type):
        with self._lock:
            row = self.conn.execute("SELECT 1 FROM xp_bonuses WHERE user_id=? AND bonus_type=?", (user_id, bonus_type)).fetchone()
            return row is not None

    def award_bonus_xp(self, user_id, bonus_type, amount):
        """اعطای XP یکباره (فقط اولین بار). برمی‌گرداند (awarded: bool, xp_new: int, level_new: int, level_old: int)."""
        with self._lock:
            existing = self.conn.execute("SELECT 1 FROM xp_bonuses WHERE user_id=? AND bonus_type=?", (user_id, bonus_type)).fetchone()
            if existing:
                row = self.conn.execute("SELECT xp, level_cached FROM users WHERE user_id=?", (user_id,)).fetchone()
                return False, (row['xp'] if row else 0), (row['level_cached'] if row else 1), (row['level_cached'] if row else 1)
            self.conn.execute("INSERT OR IGNORE INTO xp_bonuses (user_id, bonus_type) VALUES (?,?)", (user_id, bonus_type))
            xp_old_row = self.conn.execute("SELECT xp, level_cached FROM users WHERE user_id=?", (user_id,)).fetchone()
            xp_old = xp_old_row['xp'] if xp_old_row and xp_old_row['xp'] else 0
            level_old = xp_old_row['level_cached'] if xp_old_row and xp_old_row['level_cached'] else 1
            xp_new = xp_old + amount
            level_new = self.level_from_xp(xp_new)
            self.conn.execute("UPDATE users SET xp=?, level_cached=? WHERE user_id=?", (xp_new, level_new, user_id))
            self.conn.commit()
            return True, xp_new, level_new, level_old

    def touch_daily_active(self, user_id):
        """اگر اولین فعالیت روزانه است، XP روزانه می‌دهد. برمی‌گرداند (got_xp: bool)."""
        with self._lock:
            today = datetime.date.today().isoformat()
            row = self.conn.execute("SELECT last_active_date FROM users WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                return False
            if row['last_active_date'] == today:
                return False
            self.conn.execute("UPDATE users SET last_active_date=? WHERE user_id=?", (today, user_id))
            self.conn.commit()
            return True

    def get_top_users_by_xp(self, limit=10):
        with self._lock:
            return [dict(r) for r in self.conn.execute(
                "SELECT user_id, first_name, xp, level_cached FROM users "
                "WHERE hide_leaderboard=0 AND (blocked=0 OR blocked IS NULL) "
                "ORDER BY xp DESC LIMIT ?", (limit,)).fetchall()]

    # ----- مدیریت قیمت VIP -----
    def set_vip_price(self, days, amount):
        """تغییر قیمت VIP در دیتابیس برای حفظ پایداری."""
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (f"vip_price_{days}", str(amount))
            )
            self.conn.commit()

    def get_vip_price(self, days):
        with self._lock:
            try:
                row = self.conn.execute("SELECT value FROM settings WHERE key=?", (f"vip_price_{days}",)).fetchone()
                return int(row['value']) if row else None
            except sqlite3.OperationalError:
                return None

    def get_user_mask(self, user_id):
        with self._lock:
            row = self.conn.execute("SELECT emoji, mask_text FROM user_mask WHERE user_id=?", (user_id,)).fetchone()
            if row and (row['emoji'] or row['mask_text']): return (row['emoji'], row['mask_text'])
            return None

    # ----- متدهای جدید اد اجباری -----
    def record_channel_join(self, user_id, channel_username):
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO channel_joins (user_id, channel_username) VALUES (?,?)",
                (user_id, channel_username)
            )
            self.conn.commit()

    def get_channel_join_count(self, channel_username):
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM channel_joins WHERE channel_username=?",
                (channel_username,)
            ).fetchone()
            return row['cnt'] if row else 0

    # ----- مدیریت کانال‌های اجباری -----
    def add_forced_channel(self, channel_id, channel_name, invite_link):
        with self._lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO forced_channels (channel_id, channel_name, invite_link) VALUES (?,?,?)",
                (channel_id, channel_name, invite_link)
            )
            self.conn.commit()

    def remove_forced_channel(self, channel_id):
        with self._lock:
            self.conn.execute("DELETE FROM forced_channels WHERE channel_id=?", (channel_id,))
            self.conn.commit()

    def get_all_forced_channels(self):
        with self._lock:
            return [dict(r) for r in self.conn.execute("SELECT * FROM forced_channels ORDER BY added_at").fetchall()]

    # ----- pending snoops -----
    def save_pending_snoop(self, owner_id, clicker_id, display_name, t, vip_owner, clicker_username, repeat, gift_vip_given, photo_file_id):
        with self._lock:
            self.conn.execute("DELETE FROM pending_snoops WHERE owner_id=?", (owner_id,))
            self.conn.execute(
                "INSERT INTO pending_snoops (owner_id, clicker_id, display_name, t, vip_owner, clicker_username, repeat, gift_vip_given, photo_file_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (owner_id, clicker_id, display_name, t, vip_owner, clicker_username, repeat, gift_vip_given, photo_file_id)
            )
            self.conn.commit()

    def get_pending_snoop(self, owner_id):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM pending_snoops WHERE owner_id=? ORDER BY id DESC LIMIT 1", (owner_id,)
            ).fetchone()
            if row:
                self.conn.execute("DELETE FROM pending_snoops WHERE owner_id=?", (owner_id,))
                self.conn.commit()
                return dict(row)
            return None

    def get_last_daily_report_date(self):
        with self._lock:
            try:
                row = self.conn.execute("SELECT last_report_date FROM daily_report_state WHERE id=1").fetchone()
                return row['last_report_date'] if row else None
            except sqlite3.OperationalError:
                return None

    def set_last_daily_report_date(self, date_str):
        with self._lock:
            try:
                self.conn.execute("UPDATE daily_report_state SET last_report_date=? WHERE id=1", (date_str,))
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

    def get_daily_user_growth(self, days=30):
        """گرفتن تعداد کاربران جدید در هر روز برای N روز گذشته.
        برمی‌گرداند: لیست از (date_iso, count) — فقط روزهایی که حداقل ۱ کاربر جدید داشته‌اند.
        از قدیمی‌ترین به جدیدترین مرتب می‌شود."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT date(created_at) as d, COUNT(*) as c "
                "FROM users WHERE date(created_at) >= date('now', ?) "
                "GROUP BY date(created_at) ORDER BY d ASC",
                (f'-{days} days',)
            ).fetchall()
            return [(r['d'], r['c']) for r in rows]

    def get_full_daily_report_data(self):
        """داده‌های کامل برای گزارش روزانه ساعت ۲۳."""
        with self._lock:
            today = datetime.date.today().isoformat()
            yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

            # کاربران
            new_today = self.conn.execute("SELECT COUNT(*) as c FROM users WHERE date(created_at)=?", (today,)).fetchone()['c']
            new_yesterday = self.conn.execute("SELECT COUNT(*) as c FROM users WHERE date(created_at)=?", (yesterday,)).fetchone()['c']
            active_today = self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as c FROM clicks WHERE date(clicked_at)=?", (today,)).fetchone()['c']
            active_yesterday = self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as c FROM clicks WHERE date(clicked_at)=?", (yesterday,)).fetchone()['c']

            # کلیک‌ها
            clicks_today = self.conn.execute("SELECT COUNT(*) as c FROM clicks WHERE date(clicked_at)=?", (today,)).fetchone()['c']
            clicks_yesterday = self.conn.execute("SELECT COUNT(*) as c FROM clicks WHERE date(clicked_at)=?", (yesterday,)).fetchone()['c']
            distinct_today = self.conn.execute("SELECT COUNT(DISTINCT clicker_id) as c FROM clicks WHERE date(clicked_at)=?", (today,)).fetchone()['c']

            # صاحبان تلهٔ جدید امروز (اولین کلیک دریافتی)
            new_trap_owners = self.conn.execute(
                "SELECT COUNT(*) as c FROM (SELECT owner_id, MIN(date(clicked_at)) as first_click FROM clicks GROUP BY owner_id HAVING first_click=?)",
                (today,)).fetchone()['c']

            # پیام‌های ناشناس امروز
            anon_today = self.conn.execute("SELECT COUNT(*) as c FROM anon_logs WHERE date(timestamp)=?", (today,)).fetchone()['c']

            # گزارش‌های تخلف امروز (تقریبی: اخطارهای امروز)
            reports_today = 0  # پیاده‌سازی ساده؛ اخطارها در جدول users به‌صورت count هست

            # درآمد امروز و دیروز
            revenue_today = self.conn.execute(
                "SELECT COALESCE(SUM(amount),0) as c FROM transactions WHERE date(timestamp)=? AND type IN ('vip','gift_vip')",
                (today,)).fetchone()['c']
            revenue_yesterday = self.conn.execute(
                "SELECT COALESCE(SUM(amount),0) as c FROM transactions WHERE date(timestamp)=? AND type IN ('vip','gift_vip')",
                (yesterday,)).fetchone()['c']
            tx_today = self.conn.execute(
                "SELECT COUNT(*) as c FROM transactions WHERE date(timestamp)=? AND type IN ('vip','gift_vip')",
                (today,)).fetchone()['c']

            # VIP
            active_vip = self.conn.execute("SELECT COUNT(*) as c FROM vip WHERE expire_date >= date('now')").fetchone()['c']
            expiring_vips = self.conn.execute(
                "SELECT user_id FROM vip WHERE expire_date IN (?, ?)",
                (today, yesterday)).fetchall()
            # VIPهای جدید امروز (کسانی که امروز تراکنش vip داشته‌اند)
            new_vip_today_rows = self.conn.execute(
                "SELECT DISTINCT user_id FROM transactions WHERE date(timestamp)=? AND type='vip'", (today,)).fetchall()
            new_vip_today = [r['user_id'] for r in new_vip_today_rows]

            # کدهای هدیه استفاده‌شده امروز
            gift_used_today = self.conn.execute(
                "SELECT COUNT(*) as c FROM gift_usage WHERE date(used_at)=?", (today,)).fetchone()['c']
            active_gift_codes = self.conn.execute(
                "SELECT COUNT(*) as c FROM gift_codes WHERE used_count < max_uses").fetchone()['c']

            # کاربران مسدودشده امروز
            # (ستون updated_at نداریم؛ تقریبی: کل مسدودشده‌ها)
            total_banned = self.conn.execute("SELECT COUNT(*) as c FROM users WHERE blocked=1").fetchone()['c']
            # کاربرانی که ربات را بلاک کرده‌اند (از خطای 403)
            blocked_bot_count = self.conn.execute("SELECT COUNT(*) as c FROM users WHERE blocked_bot=1").fetchone()['c']

            # برترین شکارچیان امروز
            top_today = self.conn.execute(
                "SELECT c.owner_id, u.first_name, COUNT(DISTINCT c.clicker_id) as c FROM clicks c "
                "JOIN users u ON c.owner_id=u.user_id WHERE date(c.clicked_at)=? "
                "GROUP BY c.owner_id ORDER BY c DESC LIMIT 3", (today,)).fetchall()

            # کانال‌های اجباری مشکل‌دار
            broken = list(broken_channels) if 'broken_channels' in globals() else []

            # آخرین پخش همگانی
            last_broadcast_info = self.conn.execute(
                "SELECT value FROM settings WHERE key='last_broadcast_stats'").fetchone()
            last_broadcast = last_broadcast_info['value'] if last_broadcast_info else None

            return {
                'new_today': new_today,
                'new_yesterday': new_yesterday,
                'active_today': active_today,
                'active_yesterday': active_yesterday,
                'clicks_today': clicks_today,
                'clicks_yesterday': clicks_yesterday,
                'distinct_today': distinct_today,
                'new_trap_owners': new_trap_owners,
                'anon_today': anon_today,
                'revenue_today': revenue_today,
                'revenue_yesterday': revenue_yesterday,
                'tx_today': tx_today,
                'active_vip': active_vip,
                'expiring_vips': [r['user_id'] for r in expiring_vips],
                'new_vip_today': new_vip_today,
                'gift_used_today': gift_used_today,
                'active_gift_codes': active_gift_codes,
                'total_banned': total_banned,
                'blocked_bot_count': blocked_bot_count,
                'top_today': [dict(r) for r in top_today],
                'broken_channels': broken,
                'last_broadcast': last_broadcast,
            }

db = Database(str(DB_PATH))

# ====== بارگذاری قیمت‌های VIP از دیتابیس (اگر ادمین قبلاً تغییر داده) ======
for _days in VIP_PRICES.keys():
    saved = db.get_vip_price(_days)
    if saved and saved > 0:
        VIP_PRICES[_days] = saved

# ====== بارگذاری کانال‌های اجباری از دیتابیس ======
CHANNELS = []
channel_info = {}

def load_channels_from_db():
    global CHANNELS, channel_info
    CHANNELS.clear()
    channel_info.clear()
    for fc in db.get_all_forced_channels():
        ch_id = fc['channel_id']
        name = fc['channel_name'] if fc['channel_name'] else ch_id
        link = fc['invite_link'] if fc['invite_link'] else None
        channel_info[ch_id] = {"name": name, "link": link}
        # تست سریع
        try:
            bot.get_chat_member(ch_id, ADMIN_ID)
        except Exception as e:
            logger.error(f"⚠️ Cannot verify admin in channel {ch_id}: {e}")
        CHANNELS.append(ch_id)

load_channels_from_db()

print(f"✅ ربات @{BOT_USERNAME} | ادمین: {ADMIN_ID} | پرداخت: {'فعال' if PROVIDER_TOKEN else 'غیرفعال'} | کانال‌های اجباری: {CHANNELS}")

# ====== ثابت‌ها و توابع کمکی ======
# توجه: عناوین رتبه‌ها در texts.RANK_TIERS تعریف شده‌اند

# ========== عکس‌ها و فایل‌ها =============
# همه فایل آی‌دی‌ها در config.py تعریف شده‌اند

# ====== ابزار فرار از مارک‌داون ======
# توجه: چون parse_mode=None است، escape نیاز نیست. تابع به‌صورت identity نگه داشته شده
# تا کدهای موجود بدون تغییر کار کنند.
def escape_md(text: str) -> str:
    return text

# ====== کوتاه‌سازی شناسه (Base62) ======
BASE62_CHARS = string.digits + string.ascii_uppercase + string.ascii_lowercase
def rank_emoji_display(rank: int) -> str:
    if rank == 1: return "🥇"
    if rank == 2: return "🥈"
    if rank == 3: return "🥉"
    return "".join(f"{d}️⃣" for d in str(rank))

def generate_ghost_bar(cnt: int) -> str:
    # نوار پیشرفت ساده با کاراکترهای نوآر
    if cnt <= 30:
        return "🔍" * cnt
    return "🔍" * 20 + f" ... {to_persian_digits(cnt)}"
def encode_id(uid: int) -> str:
    if uid < 0:
        raise ValueError("شناسه منفی معتبر نیست")
    if uid == 0:
        return '0'
    res = []
    while uid > 0:
        uid, rem = divmod(uid, 62)
        res.append(BASE62_CHARS[rem])
    return ''.join(reversed(res))

def decode_id(code: str) -> int:
    code = code.strip()
    if not code:
        raise ValueError("کد خالی معتبر نیست")
    uid = 0
    for char in code:
        if char not in BASE62_CHARS:
            raise ValueError("کد نامعتبر")
        uid = uid * 62 + BASE62_CHARS.index(char)
    return uid

def sanitize_name(text: str) -> str:
    if re.search(r'(@|https?://|ble\.ir/|t\.me/)', text, flags=re.IGNORECASE):
        return "بی‌نام"
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned if cleaned else "بی‌نام"

# ====== فیلتر لینک‌های خارجی و فحاشی ======
# لیست کلمات ممنوعه (فحاشی و توهین)
PROFANITY_WORDS = [
    # --- لیست اولیه شما ---
    'کسده', 'کصده', 'کس ننه', 'کص ننه', 'کیر', 'کون', 'جنده', 'کونی', 'خارکسه',
    'بی‌عفت', 'بی عفت', 'احمق', 'ابله', 'مغز فلگ', 'چاقال', 'خنگ', 'کر',
    'عوضی', 'رو سیاه', 'روسیاه', 'گوه', 'گاید', 'گایده', 'شلفت', 'ننه کص',
    'کصشر', 'کسشر', 'ممه', 'کله کیری', 'بی‌شرف', 'بی شرف', 'دزد', 'لقmac',
    'fuck', 'shit', 'bitch', 'asshole', 'dick', 'pussy', 'cunt',

    # --- فحش‌های ناموسی و رکیک شدید (اضافه شده) ---
    'خارکصده', 'خارکسده', 'خواهرکصده', 'خواهرکسده', 'مادرکصده', 'مادرکسده',
    'ناموس', 'بی‌ناموس', 'بیناموس', 'لاشی', 'دیوث', 'دایوث', 'کیرم', 'کیرت',
    'کونده', 'کونته', 'کونی', 'ساکزن', 'جکشه', 'جاکش', 'باجناق', 'خوارکسه',
    'کسکش', 'کصکش', 'حرومزاده', 'حرامی', 'تخم سگ', 'تخمسگ', 'پدرسگ', 'پدر سگ',

    # --- کلمات و اصطلاحات جنسی و اندام‌ها (با املای مختلف) ---
    'کص', 'کس', 'دودول', 'بیضه', 'خایه', 'خایه‌مال', 'خایه مال', 'ساک', 'پستون',
    'ارضا', 'جلق', 'جق', 'جقی', 'حشری', 'سکسی', 'پورن', 'صیغه', 'همجنس‌باز',

    # --- مشتقات فعل گاییدن (بسیار رایج در توهین‌ها) ---
    'بگایی', 'بگام', 'بگات', 'بگاد', 'بگایید', 'بگاین', 'گاییدم', 'گاییدت', 'گاییدش',
    'میگام', 'میگات', 'میگاد', 'کون گشاد', 'کون لق',

    # --- توهین‌های عامیانه، تحقیرآمیز و کلمات سبک‌تر ---
    'عن', 'عنتر', 'شاش', 'شاشی', 'پفیوز', 'اسکل', 'اوسکل', 'اسکول', 'پلشت',
    'لاشخور', 'پفیوز', 'بیشعور', 'بی شعور', 'نفهم', 'وحشی', 'گاو', 'الاغ', 'خر',
    'دیوونه', 'دیوانه', 'روانی', 'عقده‌ای', 'جیره خور', 'خایه خور', 'مفت خور'
]

# الگوی تشخیص لینک‌های خارجی (هر چیزی که شبیه URL باشه)
URL_PATTERN = re.compile(
    r'(https?://[^\s]+|www\.[^\s]+|t\.me/[^\s]+|telegram\.me/[^\s]+|'
    r'telegram\.dog/[^\s]+|ble\.ir/[^\s]+|@[\w_]{5,})',
    re.IGNORECASE
)

def contains_external_link(text: str) -> bool:
    """بررسی آیا متن شامل لینک خارجی یا یوزرنیم تلگرام/بله هست."""
    if not text:
        return False
    # لینک‌های http/https/www
    if re.search(r'(https?://|www\.)', text, re.IGNORECASE):
        return True
    # لینک‌های تلگرام و بله
    if re.search(r'(t\.me/|telegram\.me/|telegram\.dog/|ble\.ir/)', text, re.IGNORECASE):
        return True
    # @username (۵ کاراکتر یا بیشتر — برای جلوگیری از false positive با ایموجی‌ها)
    if re.search(r'@[\w_]{5,}', text):
        return True
    return False

def contains_profanity(text: str) -> bool:
    """بررسی آیا متن شامل فحاشی یا توهین هست."""
    if not text:
        return False
    text_lower = text.lower()
    # نرمال‌سازی (حذف فاصله‌های اضافی)
    text_normalized = re.sub(r'\s+', ' ', text_lower).strip()
    for word in PROFANITY_WORDS:
        if word in text_normalized:
            return True
    return False

def is_inappropriate_content(text: str) -> tuple:
    """بررسی محتوای نامناسب.
    برمی‌گرداند: (is_inappropriate: bool, reason: str)"""
    if contains_external_link(text):
        return True, "لینک خارجی"
    if contains_profanity(text):
        return True, "محتوای نامناسب"
    return False, ""

# ====== دریافت عکس پروفایل با requests ======
def get_user_photo_file_id(user_id):
    try:
        url = f"https://tapi.bale.ai/bot{TOKEN}/getChat"
        resp = requests.post(url, json={"chat_id": user_id}, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and "photo" in data.get("result", {}):
                return data["result"]["photo"]["big_file_id"]
    except:
        pass
    return None

# ====== محدودیت‌ها ======
# برای کاربر عادی: یک دیکشنری جدا برای ردیابی روزانه
# برای VIP: همان deque مبتنی بر دقیقه
anon_rate_vip = defaultdict(lambda: deque(maxlen=200))  # VIP: per-minute tracking
anon_daily_normal = defaultdict(lambda: deque(maxlen=10))  # Normal: per-day tracking
click_rate = defaultdict(lambda: deque(maxlen=10))
gift_attempt_rate = defaultdict(lambda: deque(maxlen=5))

def can_send_anon(sender, receiver):
    """بررسی آیا کاربر می‌تواند پیام ناشناس بفرستد.
    - کاربر VIP: ۱۰ پیام در دقیقه (عملا نامحدود)
    - کاربر عادی: ۱ پیام در روز
    """
    now = time.time()
    if db.is_vip(sender):
        # VIP: 10 per minute
        key = (sender, receiver)
        while anon_rate_vip[key] and anon_rate_vip[key][0] < now - 60:
            anon_rate_vip[key].popleft()
        return len(anon_rate_vip[key]) < 10
    else:
        # Normal: 1 per day (86400 seconds)
        # ردیابی بر اساس sender فقط (نه per receiver)
        day_start = now - 86400
        while anon_daily_normal[sender] and anon_daily_normal[sender][0] < day_start:
            anon_daily_normal[sender].popleft()
        return len(anon_daily_normal[sender]) < 1

def reg_anon(sender, receiver):
    """ثبت یک ارسال پیام ناشناس."""
    now = time.time()
    if db.is_vip(sender):
        anon_rate_vip[(sender, receiver)].append(now)
    else:
        anon_daily_normal[sender].append(now)

def can_click(user_id):
    now = time.time()
    while click_rate[user_id] and click_rate[user_id][0] < now - 60:
        click_rate[user_id].popleft()
    return len(click_rate[user_id]) < 3

def reg_click(user_id):
    click_rate[user_id].append(time.time())

# ====== حالت‌ها (با Lock کامل) ======
awaiting = {}
state_lock = threading.Lock()
def clear_user_state(chat_id):
    with state_lock:
        awaiting.pop(chat_id, None)

def set_user_state(chat_id, state):
    with state_lock:
        awaiting[chat_id] = state

def get_user_state(chat_id):
    with state_lock:
        return awaiting.get(chat_id)

support_sessions = set()
support_partners = {}
admin_reply = {}
broken_channels = set()

# ====== شمارندهٔ پیام‌های ۲۴ ساعت ======
msg_times = deque()
msg_lock = threading.Lock()

def record_message(user_id: int = None):
    if user_id == ADMIN_ID:
        return
    now = time.time()
    with msg_lock:
        msg_times.append(now)

def get_messages_24h():
    now = time.time()
    with msg_lock:
        while msg_times and msg_times[0] < now - 86400:
            msg_times.popleft()
        return len(msg_times)

# ====== گزارش روزانه ساعت ۲۳:۰۰ به وقت تهران ======
TEHRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

def build_daily_report_text():
    """ساخت متن گزارش روزانه برای ادمین. قالب دقیقاً مطابق نمونهٔ کاربر."""
    s = db.get_full_daily_report_data()
    today_str = shamsi_today_str()
    uptime = uptime_str()

    # مقایسه با دیروز
    new_sign, new_pct = pct_change(s['new_today'], s['new_yesterday'])
    clicks_sign, clicks_pct = pct_change(s['clicks_today'], s['clicks_yesterday'])
    rev_sign, rev_pct = pct_change(s['revenue_today'], s['revenue_yesterday'])

    # ۳ شکارچی برتر امروز
    top_lines = []
    medals = ['🥇', '🥈', '🥉']
    for i, t in enumerate(s['top_today'][:3]):
        name = sanitize_name(t['first_name'] or "بی‌نام")
        top_lines.append(f"{medals[i]} بیشترین شکار: {escape_md(name)} ({to_persian_digits(t['c'])} نفر)")

    # VIPهای جدید امروز
    vip_new_lines = []
    for uid in s['new_vip_today'][:5]:
        u = db.get_user_basic(uid)
        nm = u['first_name'] if u and u['first_name'] else str(uid)
        vip_new_lines.append(f"🏅 VIP جدید: {escape_md(nm)}")

    # هشدارها
    warnings_lines = []
    if s['broken_channels']:
        warnings_lines.append(f"• {to_persian_digits(len(s['broken_channels']))} کانال اجباری مشکل‌دار ({', '.join(s['broken_channels'][:3])})")
    if s['expiring_vips']:
        warnings_lines.append(f"• {to_persian_digits(len(s['expiring_vips']))} VIP در شرف انقضا (امروز/فردا)")
    if s['total_banned'] > 0:
        warnings_lines.append(f"• {to_persian_digits(s['total_banned'])} کاربر مسدود شد")
    if s['blocked_bot_count'] > 0:
        warnings_lines.append(f"• {to_persian_digits(s['blocked_bot_count'])} کاربر ربات را بلاک کرده‌اند")
    if not warnings_lines:
        warnings_lines.append("• همه‌چیز رو به راه است ✅")

    # پیشنهادها
    suggestions_lines = []
    if s['active_vip'] > 0 and s['new_today'] > 0 and s['new_vip_today']:
        vip_conv = len(s['new_vip_today']) * 100 / max(s['active_vip'], 1)
        suggestions_lines.append(f"• نرخ تبدیل اشتراک ویژه: {to_persian_digits(int(vip_conv))}٪ (هدف ۵٪)")
    suggestions_lines.append(f"• موجودی کد هدیه: {to_persian_digits(s['active_gift_codes'])} کد فعال")
    if s['last_broadcast']:
        suggestions_lines.append(f"• آخرین پخش همگانی: {s['last_broadcast']}")

    text = (
        f"🌙 گزارش روزانه — {today_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 خلاصه امروز\n"
        f"👥 کاربران جدید: +{to_persian_digits(s['new_today'])} | فعال امروز: {to_persian_digits(s['active_today'])}\n"
        f"👣 کلیک‌ها: {to_persian_digits(s['clicks_today'])} | فضول یکتا: {to_persian_digits(s['distinct_today'])}\n"
        f"📂 صاحبان تلهٔ جدید: {to_persian_digits(s['new_trap_owners'])}\n"
        f"💬 پیام ناشناس: {to_persian_digits(s['anon_today'])}\n"
        f"💰 درآمد: {fmt_amount_rial(s['revenue_today'])} ({to_persian_digits(s['tx_today'])} تراکنش)\n\n"
        f"📈 مقایسه با دیروز\n"
        f"• کاربران جدید: {new_sign}{new_pct}٪\n"
        f"• کلیک‌ها: {clicks_sign}{clicks_pct}٪\n"
        f"• درآمد: {rev_sign}{rev_pct}٪\n\n"
        f"🏆 رکوردهای امروز\n"
        + ("\n".join(top_lines) + "\n" if top_lines else "")
        + ("\n".join(vip_new_lines) + "\n" if vip_new_lines else "")
        + f"🎁 کد هدیه استفاده‌شده: {to_persian_digits(s['gift_used_today'])} بار\n\n"
        f"⚠️ هشدارها\n"
        + "\n".join(warnings_lines) + "\n\n"
        f"💡 پیشنهادها\n"
        + "\n".join(suggestions_lines) + "\n\n"
        f"⏱️ وضعیت ربات\n"
        f"• آپ‌تایم: {uptime}\n"
        f"• پیام‌های ۲۴h: {to_persian_digits(get_messages_24h())}\n"
        + (f"• آخرین پخش همگانی: {s['last_broadcast']}\n" if s['last_broadcast'] else "")
        + f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕚 ارسال خودکار ساعت ۲۳:۰۰"
    )

    # افزودن بخش پراستفاده‌ترین دکمه‌ها
    try:
        top_callbacks = db.get_callback_stats(limit=5)
        if top_callbacks:
            text += "\n\n📱 *پراستفاده‌ترین دکمه‌ها:*\n"
            for cb in top_callbacks:
                text += f"• {cb['callback_data']}: {to_persian_int(cb['click_count'])} کلیک\n"
    except: pass

    return text

def daily_report_loop():
    """Thread که هر روز ساعت ۲۳:۰۰ تهران گزارش روزانه را به ادمین می‌فرستد."""
    while True:
        try:
            now_tehran = datetime.datetime.now(TEHRAN_TZ)
            # محاسبهٔ زمان بعدی ۲۳:۰۰ تهران
            target = now_tehran.replace(hour=23, minute=0, second=0, microsecond=0)
            if now_tehran >= target:
                target = target + datetime.timedelta(days=1)
            wait_seconds = (target - now_tehran).total_seconds()
            time.sleep(wait_seconds)

            # جلوگیری از ارسال دوبل اگر restart شده باشیم
            today_str = shamsi_today_str()
            last_report = db.get_last_daily_report_date()
            if last_report == today_str:
                # امروز فرستاده شده؛ صبر کن تا فردا
                time.sleep(60)
                continue

            try:
                report_text = build_daily_report_text()
                bot.send_message(ADMIN_ID, report_text)
                db.set_last_daily_report_date(today_str)
                logger.info("📊 Daily report sent to admin.")
            except Exception as e:
                logger.error(f"Daily report send error: {e}")
        except Exception as e:
            logger.error(f"Daily report loop error: {e}")
            time.sleep(60)
    
# ====== وضعیت پخش همگانی (با Lock) ======
broadcast_lock = threading.Lock()
broadcast_mode = False
broadcast_admin_chat = None
broadcast_preview_msg = None
broadcast_started_at = None
# NOTE: BROADCAST_TIMEOUT از config.py بارگذاری می‌شود؛ اینجا override نکنید

# Flag توقف پخش همگانی — ادمین می‌تواند وسط ارسال آن را متوقف کند
broadcast_stop_flag = threading.Event()

def set_broadcast_mode(val, chat=None, msg=None, started=None):
    global broadcast_mode, broadcast_admin_chat, broadcast_preview_msg, broadcast_started_at
    with broadcast_lock:
        broadcast_mode = val
        broadcast_admin_chat = chat
        broadcast_preview_msg = msg
        broadcast_started_at = started

# ====== پخش همگانی (نسخه پایدار — Sequential + نمونه مستقل TeleBot) ======

def _send_broadcast_single(broadcast_bot, uid, from_chat_id, message_id):
    """ارسال یک پیام broadcast به یک کاربر با نمونه مستقل TeleBot.
    برمی‌گرداند ('ok' | 'blocked' | 'failed')."""
    try:
        broadcast_bot.copy_message(uid, from_chat_id=from_chat_id, message_id=message_id)
        return 'ok'
    except ApiTelegramException as e:
        if e.error_code == 403:
            return 'blocked'
        if e.error_code == 429:
            # Rate limit — صبر و retry
            time.sleep(3)
            try:
                broadcast_bot.copy_message(uid, from_chat_id=from_chat_id, message_id=message_id)
                return 'ok'
            except:
                return 'failed'
        return 'failed'
    except Exception:
        return 'failed'

def _run_broadcast_async(admin_chat_id, preview_msg):
    """اجرای پخش همگانی در thread جداگانه.
    - نمونه مستقل TeleBot (جدا از ربات اصلی)
    - ارسال ترتیبی (sequential) با تأخیر ۰.۰۵ ثانیه
    - گزارش زنده هر ۱۰ ثانیه
    - هندلینگ 429 و 403"""
    # رفع باگ: try/except در سطح topLevel تا thread در صورت خطا سایلنت نشود
    try:
        _run_broadcast_async_impl(admin_chat_id, preview_msg)
    except Exception as e:
        logger.error(f"Broadcast async fatal error: {e}")
        try:
            broadcast_bot = telebot.TeleBot(TOKEN)
            broadcast_bot.send_message(admin_chat_id,
                f"❌ خطای بحرانی در پخش همگانی: {e}",
                reply_markup=admin_panel_back_markup())
        except Exception:
            pass

def _run_broadcast_async_impl(admin_chat_id, preview_msg):
    """پیاده‌سازی واقعی پخش همگانی."""
    global broadcast_stop_flag
    broadcast_stop_flag.clear()

    # ساخت نمونه مستقل TeleBot برای پخش همگانی
    try:
        broadcast_bot = telebot.TeleBot(TOKEN)
    except Exception as e:
        logger.error(f"Cannot create broadcast_bot: {e}")
        return

    # دریافت لیست کاربران
    users = db.get_broadcast_targets()
    total = len(users)
    if total == 0:
        try:
            broadcast_bot.send_message(admin_chat_id, "❌ هیچ کاربر فعالی برای ارسال وجود ندارد.",
                             reply_markup=admin_panel_back_markup())
        except: pass
        return

    # ارسال پیام پیشرفت
    try:
        progress_msg = broadcast_bot.send_message(admin_chat_id,
            f"📢 *شروع پخش همگانی*\n"
            f"👥 تعداد گیرنده‌ها: {to_persian_digits(total)}\n"
            f"📊 پیشرفت: 0٪\n"
            f"⏱️ در حال ارسال...",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("⏹️ توقف ارسال", callback_data="broadcast_stop")
            )
        )
        progress_msg_id = progress_msg.message_id
    except Exception as e:
        logger.error(f"Cannot send progress msg: {e}")
        progress_msg_id = None

    sent_cnt = 0
    blocked_cnt = 0
    failed_cnt = 0
    start_time = time.time()
    last_update = 0
    from_chat_id = preview_msg.chat.id
    message_id = preview_msg.message_id

    # ارسال ترتیبی
    for i, uid in enumerate(users):
        # چک توقف
        if broadcast_stop_flag.is_set():
            skipped_cnt = total - i
            break
        else:
            skipped_cnt = 0

        # ارسال به این کاربر
        result = _send_broadcast_single(broadcast_bot, uid, from_chat_id, message_id)
        if result == 'ok':
            sent_cnt += 1
        elif result == 'blocked':
            blocked_cnt += 1
            try:
                db.mark_user_blocked_bot(uid)
            except: pass
        else:
            failed_cnt += 1

        # به‌روزرسانی پیام پیشرفت هر ۱۰ ثانیه
        now = time.time()
        if progress_msg_id and (now - last_update) > 10:
            last_update = now
            processed = sent_cnt + blocked_cnt + failed_cnt + skipped_cnt
            pct = int(processed * 100 / total) if total else 100
            elapsed = now - start_time
            speed = processed / elapsed if elapsed > 0 else 0
            remaining = (total - processed) / speed if speed > 0 else 0
            try:
                broadcast_bot.edit_message_text(
                    f"📢 *پخش همگانی در حال اجرا...*\n"
                    f"👥 کل گیرنده‌ها: {to_persian_digits(total)}\n"
                    f"✅ ارسال موفق: {to_persian_digits(sent_cnt)}\n"
                    f"🚫 بلاک‌شده: {to_persian_digits(blocked_cnt)}\n"
                    f"⚠️ خطا: {to_persian_digits(failed_cnt)}\n"
                    f"📊 پیشرفت: {to_persian_digits(pct)}٪\n"
                    f"⚡️ سرعت: {to_persian_digits(int(speed))} پیام/ثانیه\n"
                    f"⏱️ زمان باقی‌مانده: ~{to_persian_digits(int(remaining))} ثانیه",
                    admin_chat_id, progress_msg_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("⏹️ توقف ارسال", callback_data="broadcast_stop")
                    )
                )
            except: pass

        # مکث کوتاه بین ارسال‌ها (۲۰ پیام در ثانیه)
        time.sleep(0.05)

    elapsed_total = time.time() - start_time
    was_stopped = broadcast_stop_flag.is_set()
    broadcast_stop_flag.clear()

    # حذف پیام پیشرفت
    if progress_msg_id:
        try:
            broadcast_bot.delete_message(admin_chat_id, progress_msg_id)
        except: pass

    # ذخیره آمار در دیتابیس
    success_rate = int(sent_cnt * 100 / total) if total else 0
    try:
        with db._lock:
            db.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("last_broadcast_stats", f"{sent_cnt}/{total} ({success_rate}%)")
            )
            db.conn.commit()
    except: pass

    # گزارش نهایی به ادمین
    summary = (
        f"{'⏹️ پخش همگانی متوقف شد' if was_stopped else '✅ پخش همگانی پایان یافت'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 کل گیرنده‌ها: {to_persian_digits(total)}\n"
        f"✅ ارسال موفق: {to_persian_digits(sent_cnt)}\n"
        f"🚫 بلاک‌کننده‌ها (کاربرانی که ربات را بلاک کرده‌اند): {to_persian_digits(blocked_cnt)}\n"
        f"⚠️ خطاهای دیگر: {to_persian_digits(failed_cnt)}\n"
        f"⏭️ رد‌شده (به‌خاطر توقف): {to_persian_digits(skipped_cnt)}\n"
        f"📊 نرخ موفقیت: {to_persian_digits(success_rate)}٪\n"
        f"⏱️ زمان کل: {to_persian_digits(int(elapsed_total))} ثانیه\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 کاربران بلاک‌کننده به‌صورت خودکار از پخش‌های بعدی حذف می‌شوند."
    )
    try:
        broadcast_bot.send_message(admin_chat_id, summary, reply_markup=admin_panel_back_markup())
    except: pass

# ====== سیستم سطح‌بندی XP ======
# XP لازم برای رفتن از سطح (L-1) به L = 100 × L
# XP تجمعی تا سطح L = 100 × L × (L+1) / 2
# پاداش‌ها در config.py تعریف شده‌اند (XP_BONUS_ONE_TIME, XP_RECURRING)

def get_rank_tier(level):
    """برگرداندن (title, emoji) برای یک سطح مشخص."""
    for tier in texts.RANK_TIERS:
        if tier["min_level"] <= level <= tier["max_level"]:
            return tier["title"], tier["emoji"]
    # سطح بیش از ۵۰ (نباید رخ دهد)
    if level >= 50:
        return texts.RANK_TIERS[-1]["title"], texts.RANK_TIERS[-1]["emoji"]
    return texts.RANK_TIERS[0]["title"], texts.RANK_TIERS[0]["emoji"]

def get_user_display(user_id, name=None):
    """نام نمایشی کاربر با نشان رتبهٔ فعلی."""
    if name is None:
        try:
            u = db.get_user_basic(user_id)
            name = u['first_name'] if u and u['first_name'] else "بی‌نام"
        except: name = "بی‌نام"
    level = db.get_user_level_cached(user_id)
    _, emoji = get_rank_tier(level)
    return f"{emoji} {name}" if emoji else name

def get_user_rank_emoji(user_id):
    """فقط ایموجی رتبه برای نمایش کنار نام."""
    level = db.get_user_level_cached(user_id)
    _, emoji = get_rank_tier(level)
    return emoji

def award_xp_with_level_up_notify(user_id, amount, recurring_type=None, bonus_type=None, bonus_amount=None, chat_id=None):
    """
    اعطای XP به کاربر با مدیریت خودکار ارتقای سطح.
    - اگر سطح بالا برود: پیام تبریک با عکس (LEVEL_UP_PHOTO_ID) ارسال می‌کند.
    - بررسی ماموریت‌ها: اگر ماموریتی تکمیل شده باشد، فقط از طریق answer_callback_query
      به‌صورت toast به کاربر اطلاع می‌دهد (برای جلوگیری از شلوغ شدن چت).

    recurring_type: کلید در XP_RECURRING (مثل 'new_distinct_snoop')
    bonus_type: کلید در XP_BONUS_ONE_TIME (مثل 'first_snoop')
    """
    total_xp = 0
    level_old = db.get_user_level_cached(user_id)

    # اعطای XP تکرارشونده
    if recurring_type and recurring_type in XP_RECURRING:
        total_xp += XP_RECURRING[recurring_type]

    # اعطای XP یکباره (فقط اولین بار)
    if bonus_type and bonus_type in XP_BONUS_ONE_TIME:
        awarded, _, _, _ = db.award_bonus_xp(user_id, bonus_type, XP_BONUS_ONE_TIME[bonus_type])
        if awarded:
            total_xp += XP_BONUS_ONE_TIME[bonus_type]

    if total_xp > 0:
        _, level_new, level_old = db.add_xp(user_id, total_xp)
        # بررسی ارتقا — فقط برای ارتقا پیام جداگانه با عکس می‌فرستیم
        if level_new > level_old:
            title, emoji = get_rank_tier(level_new)
            xp_next = db.xp_for_next_level(level_new)
            xp_current = db.get_user_xp(user_id)
            try:
                msg = texts.LEVEL_UP_MESSAGE.format(
                    level=to_persian_digits(level_new),
                    title=title,
                    emoji=emoji,
                    xp_current=to_persian_int(xp_current),
                    xp_next=to_persian_int(xp_next) if xp_next else "نهایتی"
                )
                target_chat = chat_id if chat_id else user_id
                try:
                    # ارسال با عکس (اگر LEVEL_UP_PHOTO_ID تنظیم شده باشد)
                    if LEVEL_UP_PHOTO_ID:
                        try:
                            bot.send_photo(target_chat, LEVEL_UP_PHOTO_ID, caption=msg)
                        except:
                            bot.send_message(target_chat, msg)
                    else:
                        bot.send_message(target_chat, msg)
                except Exception as e:
                    logger.error(f"Level-up notify error: {e}")
            except Exception as e:
                logger.error(f"Level-up message build error: {e}")

    # نکته: _check_and_award_tasks_xp فقط در show_tasks_page و show_task_detail_popup صدا زده می‌شه
    # (نه روی هر اکشن) برای جلوگیری از اسکن ۲۰۰ تسک در هر کلیک


def _check_and_award_tasks_xp(user_id):
    """بررسی تمام تسک‌ها — اگر تسکی تکمیل شده:
    1. XP آن را به کاربر اضافه می‌کند.
    2. اگر سطح بالا برود، پیام تبریک با عکس می‌فرستد.
    3. نوتیفیکیشن تکمیل تسک را در صف ذخیره می‌کند (برای ارسال بعدی به کاربر)."""
    newly_completed = []  # لیست تسک‌های تازه تکمیل‌شده

    for task in tasks_module.TASKS:
        task_id = task["id"]
        # اگر قبلاً این تسک پاداش گرفته، رد کن
        if db.has_bonus(user_id, f"task_{task_id}"):
            continue
        try:
            # بررسی آیا تسک انجام شده
            with db._lock:
                is_done = bool(task["check"](db, user_id))
            if is_done:
                # اعطای XP تسک به‌صورت bonus (یکباره)
                # level_old رو قبل از award ذخیره می‌کنیم تا بعداً چک کنیم
                level_before = db.get_user_level_cached(user_id)
                awarded, xp_new, level_new, _ = db.award_bonus_xp(user_id, f"task_{task_id}", task["xp"])
                if awarded:
                    newly_completed.append(task)
                    # اگر سطح بالا رفت، پیام ارتقا بفرست
                    if level_new > level_before:
                        try:
                            title, emoji = get_rank_tier(level_new)
                            xp_next = db.xp_for_next_level(level_new)
                            msg = texts.LEVEL_UP_MESSAGE.format(
                                level=to_persian_digits(level_new),
                                title=title,
                                emoji=emoji,
                                xp_current=to_persian_int(xp_new),
                                xp_next=to_persian_int(xp_next) if xp_next else "نهایتی"
                            )
                            try:
                                if LEVEL_UP_PHOTO_ID:
                                    try:
                                        bot.send_photo(user_id, LEVEL_UP_PHOTO_ID, caption=msg)
                                    except:
                                        bot.send_message(user_id, msg)
                                else:
                                    bot.send_message(user_id, msg)
                            except Exception as e:
                                logger.error(f"Level-up notify error: {e}")
                        except Exception as e:
                            logger.error(f"Level-up msg build error: {e}")
        except Exception as e:
            logger.error(f"Task check error for {task_id}: {e}")

    # ذخیره نوتیفیکیشن‌های تسک در صف (برای نمایش بعدی)
    if newly_completed:
        try:
            _append_pending_task_notifications(user_id, newly_completed)
        except Exception as e:
            logger.error(f"Append task notifications error: {e}")


# ====== صف نوتیفیکیشن‌های تسک (به‌جای ارسال فوری) ======
_pending_task_notifications = {}  # user_id -> list of task dicts
_pending_task_lock = threading.Lock()

def _append_pending_task_notifications(user_id, tasks_list):
    """افزودن تسک‌های تازه تکمیل‌شده به صف نوتیفیکیشن کاربر."""
    with _pending_task_lock:
        if user_id not in _pending_task_notifications:
            _pending_task_notifications[user_id] = []
        _pending_task_notifications[user_id].extend(tasks_list)

def _get_and_clear_pending_task_notifications(user_id):
    """گرفتن و پاک کردن نوتیفیکیشن‌های در انتظار کاربر."""
    with _pending_task_lock:
        notifs = _pending_task_notifications.get(user_id, [])
        _pending_task_notifications[user_id] = []
        return notifs

def maybe_daily_login_xp(user_id, chat_id=None):
    """اگر اولین فعالیت روزانه است، XP روزانه می‌دهد."""
    if db.touch_daily_active(user_id):
        award_xp_with_level_up_notify(user_id, 0, recurring_type='daily_login', chat_id=chat_id)

# ====== توابع کمکی ======
def fmt_id(uid, vip): return f"*{uid}*" if vip else "🔒 (فقط VIP)"
def fmt_uname(uname, vip): return f"@{uname}" if (vip and uname) else ("🔒 (فقط VIP)" if not vip else "ندارد")

def user_link(uid): return f"ble.ir/{BOT_USERNAME}?start={encode_id(uid)}"


# ====== پشتیبانی و پاسخ ادمین (Thread-Safe) ======
support_lock = threading.Lock()
support_sessions = set()
support_partners = {}
admin_reply = {}

def add_support_session(user_id: int):
    with support_lock:
        support_sessions.add(user_id)

def remove_support_session(user_id: int):
    with support_lock:
        support_sessions.discard(user_id)

def clear_support_session(user_id: int):
    with support_lock:
        support_sessions.discard(user_id)
        support_partners.pop(user_id, None)

def is_support_session(user_id: int) -> bool:
    with support_lock:
        return user_id in support_sessions

def set_support_partner(user_id: int, partner_id: int):
    with support_lock:
        support_partners[user_id] = partner_id

def get_support_partner(user_id: int):
    with support_lock:
        return support_partners.get(user_id)

def pop_support_partner(user_id: int):
    with support_lock:
        return support_partners.pop(user_id, None)

def set_admin_reply(user_id: int, target_id: int):
    with support_lock:
        admin_reply[user_id] = target_id

def get_admin_reply(user_id: int):
    with support_lock:
        return admin_reply.get(user_id)

def pop_admin_reply(user_id: int):
    with support_lock:
        return admin_reply.pop(user_id, None)
    
def get_support_sessions_list():
    """برگرداندن یک کپی از لیست جلسات پشتیبانی (امن برای پیمایش)"""
    with support_lock:
        return list(support_sessions)
    
def is_support_sessions_empty():
    with support_lock:
        return not support_sessions

# ====== توابع اد اجباری ======
# ====== کش عضویت کانال اجباری (۵ دقیقه) ======
_subscription_cache = {}  # user_id -> (is_subscribed: bool, timestamp: float)
_subscription_cache_lock = threading.Lock()
SUBSCRIPTION_CACHE_TTL = 300  # ۵ دقیقه

def is_subscribed(user_id):
    if not CHANNELS:
        return True

    # بررسی کش
    now = time.time()
    with _subscription_cache_lock:
        cached = _subscription_cache.get(user_id)
        if cached:
            is_sub, ts = cached
            if now - ts < SUBSCRIPTION_CACHE_TTL:
                return is_sub

    # چک واقعی
    for ch_id in CHANNELS:
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                # کش کردن نتیجه (غیرعضو)
                with _subscription_cache_lock:
                    _subscription_cache[user_id] = (False, now)
                return False
            db.record_channel_join(user_id, ch_id)

        except ApiTelegramException as e:
            # کاربر در کانال عضو نیست (عادی)
            if e.error_code == 400 and 'user not found' in str(e).lower():
                with _subscription_cache_lock:
                    _subscription_cache[user_id] = (False, now)
                return False

            # ربات به اعضا دسترسی ندارد (ادمین نیست)
            if e.error_code == 403:
                # فقط یک بار به ادمین اطلاع بده
                if ch_id not in broken_channels:
                    broken_channels.add(ch_id)
                    try:
                        bot.send_message(
                            ADMIN_ID,
                            f"⚠️ ربات نمی‌تواند اعضای کانال {ch_id} را بررسی کند (خطای 403).\n"
                            "ربات باید در کانال **ادمین** باشد.\n"
                            "تا زمان رفع مشکل، عضویت در این کانال اجباری است."
                        )
                    except:
                        pass
                # کاربر را غیرعضو فرض کن
                with _subscription_cache_lock:
                    _subscription_cache[user_id] = (False, now)
                return False

            # رفع باگ: سایر خطاهای API → غیرعضو، اما کش نکنیم (ممکن است transient باشد)
            logger.error(f"API error checking channel {ch_id}: {e}")
            return False

        except Exception as e:
            # رفع باگ: خطای شبکه و ... → غیرعضو، اما کش نکنیم تا در تلاش بعدی دوباره چک شود
            logger.error(f"General error checking channel {ch_id}: {e}")
            return False

    # همه چک‌ها موفق بود → عضو است
    with _subscription_cache_lock:
        _subscription_cache[user_id] = (True, now)
    return True

def clear_subscription_cache(user_id=None):
    """پاک کردن کش عضویت (برای وقتی کاربر روی «بررسی عضویت» می‌زنه)."""
    with _subscription_cache_lock:
        if user_id:
            _subscription_cache.pop(user_id, None)
        else:
            _subscription_cache.clear()

def build_channel_keyboard(original_callback, user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    any_unjoined = False
    for ch_id in CHANNELS:
        is_member = False
        try:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status in ['member', 'administrator', 'creator']:
                db.record_channel_join(user_id, ch_id)
                is_member = True
        except:
            pass    # اگر خطا داد، فرض می‌کنیم عضو نیست و کانال را نشان می‌دهیم

        if is_member:
            continue    # عضو است – نمایش نده

        any_unjoined = True
        info = channel_info.get(ch_id, {})
        ch_name = info.get("name", ch_id)
        ch_link = info.get("link")
        if not ch_link:
            if ch_id.startswith("@"):
                ch_link = f"https://ble.ir/{ch_id[1:]}"
            else:
                ch_link = f"https://ble.ir/joinchat/{ch_id}"
        markup.add(types.InlineKeyboardButton(f"📢 {ch_name}", url=ch_link))

    if any_unjoined:
        markup.add(types.InlineKeyboardButton(texts.FORCE_JOIN_BUTTON_CHECK, callback_data=f"checkjoin_{original_callback}"))
        return markup
    return None


def vip_info_text():
    prices_lines = "\n".join(
        f"• {to_persian_digits(days)} روز: {fmt_amount_toman(amount)}"
        for days, amount in VIP_PRICES.items()
    )
    return (
        "🏅 *اشتراک VIP کارآگاهی*\n\n"
        "قابلیت‌های ویژه:\n"
        "• 🆔 دیدن شناسه و آیدی فضول‌ها\n"
        "• ✉️ پیام ناشناس نامحدود (کاربران عادی فقط ۱ پیام در روز)\n"
        "• 🎭 نقاب کارآگاهی هنگام ارسال پیام ناشناس\n"
        "• 📝 تنظیم متن و عکس خوش‌آمدگویی برای فضول‌ها\n\n"
        f"💰 قیمت اشتراک:\n{prices_lines}\n\n"
        "🔍 یکی از کارآگاهان ویژه شو!"
    )

def vip_status_display(user_id):
    if not db.is_vip(user_id):
        return False, "غیرفعال"
    days = db.get_vip_days_left(user_id)
    if days == 0:
        return True, "فعال 🏅 (امروز آخرین روز)"
    else:
        return True, f"فعال 🏅 ({to_persian_digits(days)} روز اعتبار باقی‌مانده)"

def main_menu(user_id=None):
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🔍 تلهٔ من", callback_data="my_link_show"),
        types.InlineKeyboardButton("ℹ️ اطلاعات من", callback_data="my_info"),
        types.InlineKeyboardButton("📋 لیست فضول‌ها", callback_data="snooplist_page_1"),
        types.InlineKeyboardButton("⭐ ستاره‌ها", callback_data="leaderboard"),
        types.InlineKeyboardButton("📖 راهنما", callback_data="help"),
        types.InlineKeyboardButton("🏅 VIP", callback_data="vip_info"),
        types.InlineKeyboardButton("🎁 کد هدیه", callback_data="gift_code"),
        types.InlineKeyboardButton("📞 پشتیبانی", callback_data="support")
    )
    if user_id == ADMIN_ID:
        m.add(types.InlineKeyboardButton("🔐 پنل ادمین", callback_data="admin_panel"))
    return m

def home_markup():
    return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))

def cancel_markup():
    return types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_state"))

def admin_panel_back_markup():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🔐 پنل ادمین", callback_data="admin_panel"))
    m.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
    return m

def vip_menu_button():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🏅 بازگشت به منوی VIP", callback_data="vip_info"))
    m.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
    return m

VIP_EXPIRED_MSG = (
    "⛔ اشتراک VIP شما به پایان رسیده، بنابراین این قابلیت در حال حاضر غیرفعال است.\n"
    "👑 تنظیمات قبلی شما (در صورت وجود) حذف نشده‌اند و به‌محض فعال شدن دوباره‌ی VIP، خودکار فعال می‌شوند."
)

def build_dynamic_home_text(user_id):
    """ساخت متن پویای خانه بر اساس وضعیت کاربر.
    اولویت: VIP > returning user > recent clicks > no clicks > new user."""
    try:
        u = db.get_user_basic(user_id)
        name = u['first_name'] if u and u['first_name'] else "دوست"
    except:
        name = "دوست"

    # اگه کاربر جدید (سطح ۱ و XP=0 و بدون کلیک) → حالت ۱
    level = db.get_user_level_cached(user_id)
    xp = db.get_user_xp(user_id)
    total_clicks = db.get_clicks_count(user_id)
    snoop_count = db.get_distinct_snoop_count(user_id)
    today_clicks = db.get_today_clicks_count(user_id)
    is_vip = db.is_vip(user_id)
    vip_days = db.get_vip_days_left(user_id) if is_vip else 0

    # محاسبه روزهای گذشته از آخرین فعالیت
    try:
        last_active = db.conn.execute(
            "SELECT last_active_date FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        days_ago = None
        if last_active and last_active['last_active_date']:
            from datetime import date as dt_date
            last_date = dt_date.fromisoformat(last_active['last_active_date'])
            today = dt_date.today()
            days_ago = (today - last_date).days
    except:
        days_ago = None

    # محاسبه کلیک‌های جدید از آخرین فعالیت
    new_clicks = 0
    if days_ago and days_ago > 0:
        try:
            # کلیک‌های دریافتی در days_ago روز گذشته
            row = db.conn.execute(
                "SELECT COUNT(*) as c FROM clicks WHERE owner_id=? AND date(clicked_at) >= date('now', ?)",
                (user_id, f'-{days_ago} days')
            ).fetchone()
            new_clicks = row['c'] if row else 0
        except:
            new_clicks = 0

    title, emoji = get_rank_tier(level)

    if is_vip and vip_days > 0:
        # حالت ۴: VIP (اولویت اول)
        return texts.HOME_VIP.format(
            name=escape_md(name),
            level=to_persian_digits(level),
            title=title,
            snoop_count=to_persian_int(snoop_count),
            total_clicks=to_persian_int(total_clicks),
            days=to_persian_digits(vip_days),
            xp=to_persian_int(xp)
        )
    elif days_ago and days_ago >= 7 and new_clicks > 0:
        # حالت ۵: کاربر قدیمی برگشته
        return texts.HOME_RETURNING_USER.format(
            name=escape_md(name),
            days_ago=to_persian_digits(days_ago),
            level=to_persian_digits(level),
            title=title,
            snoop_count=to_persian_int(snoop_count),
            total_clicks=to_persian_int(total_clicks),
            vip_status=f"فعال ({to_persian_digits(vip_days)} روز)" if is_vip else "غیرفعال",
            new_clicks=to_persian_int(new_clicks)
        )
    elif today_clicks > 0:
        # حالت ۳: کلیک‌های اخیر
        vip_status = f"فعال ({to_persian_digits(vip_days)} روز)" if is_vip else "غیرفعال"
        return texts.HOME_WITH_RECENT_CLICKS.format(
            name=escape_md(name),
            level=to_persian_digits(level),
            title=title,
            snoop_count=to_persian_int(snoop_count),
            today_clicks=to_persian_int(today_clicks),
            total_clicks=to_persian_int(total_clicks),
            vip_status=vip_status
        )
    elif total_clicks == 0 and level == 1 and xp == 0:
        # حالت ۱: کاربر جدید
        return texts.HOME_NEW_USER.format(name=escape_md(name))
    else:
        # حالت ۲: تله فعال ولی بدون کلیک اخیر
        vip_status = f"فعال ({to_persian_digits(vip_days)} روز)" if is_vip else "غیرفعال"
        return texts.HOME_NO_CLICKS.format(
            name=escape_md(name),
            level=to_persian_digits(level),
            title=title,
            vip_status=vip_status
        )


def show_main_menu_for_callback(call, chat_id, user_id):
    home_text = build_dynamic_home_text(user_id)
    # اگه پیام عکس یا ویدیو باشه، edit_text خراب می‌شه — باید delete+resend کنیم
    if call.message.content_type in ('photo', 'video', 'document', 'animation'):
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        bot.send_message(chat_id, home_text, reply_markup=main_menu(user_id))
    else:
        try:
            bot.edit_message_text(home_text, chat_id, call.message.message_id, reply_markup=main_menu(user_id))
        except Exception:
            bot.send_message(chat_id, home_text, reply_markup=main_menu(user_id))

# ایموجی‌های نقاب کارآگاهی (تم نوآر)
MASK_EMOJIS = ["🎭", "🔍", "🕯️", "🌙", "📂", "🔦", "🕵️", "👁️", "🗒️", "📇", "🧥", "🎖️", "🏅", "📰", "☕", "🚬"]

# ====== توابع دستیار ادمین ======
def admin_panel_markup():
    """منوی اصلی ادمین — بازطراحی‌شده طبق درخواست کاربر."""
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("🔍 جستجوی کاربر", callback_data="admin_search_user"),
        types.InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_userlist_page_1"),
        types.InlineKeyboardButton("👑 VIP", callback_data="admin_vip_submenu"),
        types.InlineKeyboardButton("📬 لاگ ناشناس", callback_data="admin_anonlog_page_1"),
        types.InlineKeyboardButton("🎁 کدهای هدیه", callback_data="admin_gift_list"),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("📊 آمار کل", callback_data="admin_daily"),
        types.InlineKeyboardButton("📢 اد اجباری", callback_data="admin_forced_ads"),
    )
    m.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
    return m

def admin_vip_submenu_markup():
    """زیرمنوی VIP — طبق درخواست: تراکنش‌ها، تغییر قیمت، آمار VIP، مدیریت VIP."""
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("💰 تراکنش‌ها", callback_data="admin_transactions_page_1"),
        types.InlineKeyboardButton("💵 تغییر قیمت VIP", callback_data="admin_vip_prices"),
        types.InlineKeyboardButton("📊 آمار VIP", callback_data="admin_vip_stats"),
        types.InlineKeyboardButton("⚙️ مدیریت VIP", callback_data="admin_vip"),
    )
    m.add(types.InlineKeyboardButton("🔙 بازگشت به پنل ادمین", callback_data="admin_panel"))
    return m

def process_admin_addvip(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        # رفع باگ: بررسی تعداد آرگومان‌ها
        parts = message.text.split()
        if len(parts) != 2:
            bot.reply_to(message, "❌ فرمت اشتباه. مثال درست:\n123456789 30", reply_markup=admin_panel_back_markup())
            return
        uid, days = int(parts[0]), int(parts[1])
        if days <= 0 or days > 3650:
            bot.reply_to(message, "❌ تعداد روز باید بین ۱ و ۳۶۵۰ باشد.", reply_markup=admin_panel_back_markup())
            return
        db.add_vip(uid, days)
        bot.reply_to(message, f"✅ کاربر {uid} برای {days} روز VIP شد.", reply_markup=admin_panel_back_markup())
    except Exception:
        bot.reply_to(message, "❌ فرمت اشتباه. مثال درست:\n123456789 30", reply_markup=admin_panel_back_markup())

def process_admin_quick_vip(message, target_id):
    if message.from_user.id != ADMIN_ID: return
    try:
        days = int(message.text.strip())
        # رفع باگ: اعتبارسنجی بازه روز
        if days <= 0 or days > 3650:
            bot.reply_to(message, "❌ تعداد روز باید بین ۱ و ۳۶۵۰ باشد.", reply_markup=admin_panel_back_markup())
            return
        db.add_vip(target_id, days)
        bot.reply_to(message, f"✅ کاربر {target_id} برای {days} روز VIP شد.", reply_markup=admin_panel_back_markup())
    except Exception:
        bot.reply_to(message, "❌ تعداد روز نامعتبر.", reply_markup=admin_panel_back_markup())

def process_admin_search(message):
    if message.from_user.id != ADMIN_ID: return
    query = message.text.strip()
    results = db.search_users(query)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not results:
        markup.add(types.InlineKeyboardButton("🔐 پنل ادمین", callback_data="admin_panel"))
        markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        bot.reply_to(message, "❌ هیچ کاربری یافت نشد.", reply_markup=markup)
    else:
        lines = [f"🔍 نتایج جستجو برای '{query}':"]
        for u in results[:10]: lines.append(f"• {u['first_name'] or 'بی‌نام'} (ID: {u['user_id']})")
        for u in results[:10]:
            markup.add(types.InlineKeyboardButton(f"{u['first_name'] or u['user_id']}", callback_data=f"user_detail_{u['user_id']}"))
        markup.add(types.InlineKeyboardButton("🔐 پنل ادمین", callback_data="admin_panel"))
        bot.reply_to(message, "\n".join(lines), reply_markup=markup)

def show_admin_userlist(chat_id, page, message_id):
    limit = 20; offset = (page-1)*limit
    users = db.get_all_users_paginated(offset, limit)
    total = db.count_all_users(); total_pages = max(1, (total + limit - 1) // limit)
    lines = [texts.ADMIN_USER_LIST_HEADER.format(page=to_persian_digits(page))]
    for u in users:
        # نمایش تعداد فضول یکتا در کنار نام
        snoop_cnt = u.get('snoop_count', 0) if isinstance(u, dict) else 0
        snoop_str = f" — {to_persian_digits(snoop_cnt)} فضول" if snoop_cnt else ""
        lines.append(f"• {u['first_name'] or 'بی‌نام'} (ID: {to_persian_digits(u['user_id'])}){snoop_str}")
    markup = types.InlineKeyboardMarkup(row_width=2)
    # نمایش تعداد فضول در دکمه‌ها هم
    buttons = []
    for u in users:
        snoop_cnt = u.get('snoop_count', 0) if isinstance(u, dict) else 0
        btn_label = f"{u['first_name'] or str(u['user_id'])}"
        if snoop_cnt:
            btn_label += f" ({to_persian_digits(snoop_cnt)})"
        buttons.append(types.InlineKeyboardButton(btn_label, callback_data=f"user_detail_{u['user_id']}"))
    for i in range(0, len(buttons), 2):
        if i+1 < len(buttons): markup.add(buttons[i], buttons[i+1])
        else: markup.add(buttons[i])
    row = []
    if page > 1: row.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_userlist_page_{page-1}"))
    if page < total_pages: row.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"admin_userlist_page_{page+1}"))
    if row: markup.add(*row)
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
    bot.edit_message_text("\n".join(lines), chat_id, message_id, reply_markup=markup)

def show_user_detail(chat_id, target_id, message_id, info):
    user = info['user']
    vip_status = info['vip_status']
    if info['vip_expire'] and vip_status == "فعال":
        vip_status += f" (تا {info['vip_expire']})"
    warnings = db.get_user_warning_count(target_id)
    is_hidden = db.is_hide_leaderboard(target_id)
    leaderboard_status = "مخفی" if is_hidden else "عمومی"

    text = texts.ADMIN_USER_DETAIL.format(
        user_id=target_id, name=user['first_name'] or 'ندارد',
        username=user['username'] or 'ندارد',
        blocked="مسدود" if user['blocked'] else "فعال",
        vip_status=vip_status,
        total_clicks=info['total_clicks'],
        snoop_count=info['snoop_count'],
        join_date="نامشخص",
        warnings=warnings,
        leaderboard_status=leaderboard_status
    )

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚫 مسدود", callback_data=f"admin_action_block_{target_id}"),
        types.InlineKeyboardButton("✅ رفع مسدود", callback_data=f"admin_action_unblock_{target_id}"),
        types.InlineKeyboardButton("🏅 VIP", callback_data=f"admin_action_vip_{target_id}"),
        types.InlineKeyboardButton("✉️ پیام", callback_data=f"admin_action_message_{target_id}"),
        types.InlineKeyboardButton("🔄 بازنشانی اخطارها", callback_data=f"admin_resetwarns_{target_id}")
    )
    markup.add(types.InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="admin_userlist_page_1"))
    markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
    bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)

def show_admin_transactions(chat_id, page, message_id):
    limit = 10; offset = (page-1)*limit
    txns = db.get_transactions_paginated(offset, limit)
    total = db.count_transactions(); total_pages = max(1, (total + limit - 1) // limit)
    lines = [texts.ADMIN_TRANSACTION_LIST.format(page=page)]
    for t in txns: lines.append(f"👤 {t['user_id']} | {t['type']} | {t['amount']:,} ریال | {t['timestamp'][:16]}")
    markup = types.InlineKeyboardMarkup()
    row = []
    if page > 1: row.append(types.InlineKeyboardButton("⬅️", callback_data=f"admin_transactions_page_{page-1}"))
    if page < total_pages: row.append(types.InlineKeyboardButton("➡️", callback_data=f"admin_transactions_page_{page+1}"))
    if row: markup.row(*row)
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
    bot.edit_message_text("\n".join(lines), chat_id, message_id, reply_markup=markup)

def show_admin_anon_logs(chat_id, page, message_id):
    limit = 5; offset = (page-1)*limit
    logs = db.get_anon_logs_paginated(offset, limit)
    total = db.count_anon_logs(); total_pages = max(1, (total + limit - 1) // limit)
    lines = [texts.ADMIN_ANON_LOG_HEADER]
    for l in logs: lines.append(texts.ADMIN_ANON_LOG_ENTRY.format(sender=l['sender_id'], receiver=l['receiver_id'], text=l['text'][:100]))
    markup = types.InlineKeyboardMarkup(row_width=2)
    for l in logs:
        markup.add(
            types.InlineKeyboardButton("✉️ پیام", callback_data=f"anonlog_action_msg_{l['sender_id']}"),
            types.InlineKeyboardButton("🚫 بلاک", callback_data=f"anonlog_action_block_{l['sender_id']}"))
    row = []
    if page > 1: row.append(types.InlineKeyboardButton("⬅️", callback_data=f"admin_anonlog_page_{page-1}"))
    if page < total_pages: row.append(types.InlineKeyboardButton("➡️", callback_data=f"admin_anonlog_page_{page+1}"))
    if row: markup.row(*row)
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
    bot.edit_message_text("\n".join(lines), chat_id, message_id, reply_markup=markup)

# ====== ویزارد کاربر جدید ======
def _start_new_user_wizard(chat_id, name):
    """شروع ویزارد کاربر جدید — مرحله ۱: پیام خوش‌آمد بدون دکمه."""
    try:
        # مرحله ۱: پیام خوش‌آمد گرم (بدون دکمه)
        bot.send_message(chat_id, texts.WIZARD_WELCOME.format(name=escape_md(name)))
        # مرحله ۲: ویدیو + متن + دکمه‌ها (بدون تأخیر)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🔍 ساخت تله", callback_data="wizard_make_trap"))
        markup.add(types.InlineKeyboardButton("➡️ ادامه", callback_data="wizard_skip"))
        if LINK_TUTORIAL_VIDEO_ID:
            try:
                bot.send_video(chat_id, LINK_TUTORIAL_VIDEO_ID, caption=texts.WIZARD_TUTORIAL, reply_markup=markup)
            except:
                bot.send_message(chat_id, texts.WIZARD_TUTORIAL_NO_VIDEO, reply_markup=markup)
        else:
            bot.send_message(chat_id, texts.WIZARD_TUTORIAL_NO_VIDEO, reply_markup=markup)
    except Exception as e:
        logger.error(f"Wizard error: {e}")

# ====== /panel — نمایش منوی خانه ======
@bot.message_handler(commands=['panel'])
def panel_cmd(message):
    chat_id = message.chat.id
    if db.is_blocked(chat_id):
        return
    # نمایش منوی خانه (مثل وقتی که پیام نامفهوم ارسال می‌شه)
    home_text = build_dynamic_home_text(chat_id)
    # رفع باگ: wrap در try/except
    try:
        bot.reply_to(message, home_text, reply_markup=main_menu(chat_id))
    except ApiTelegramException as e:
        if e.error_code == 403:
            try: db.mark_user_blocked_bot(chat_id)
            except Exception: pass
        else:
            logger.error(f"panel_cmd send error: {e}")
    except Exception as e:
        logger.error(f"panel_cmd send error: {e}")

# ====== /start ======
@bot.message_handler(commands=['start'])
def start_cmd(message):
    chat_id = message.chat.id
    clear_user_state(chat_id)
    remove_support_session(chat_id)
    pop_support_partner(chat_id)
    pop_admin_reply(chat_id)

    if db.is_blocked(message.from_user.id):
        # رفع باگ: wrap در try/except
        try:
            bot.reply_to(message, "⛔ حساب شما مسدود شده است.")
        except Exception:
            pass
        return

    # مهم: باید is_new_user رو قبل از sync_user_profile چک کنیم
    # چون sync_user_profile کاربر رو در DB ثبت می‌کنه و بعدش is_new_user همیشه False برمی‌گرده
    user_id = message.from_user.id
    is_new = db.is_new_user(user_id)
    # حالا sync_user_profile رو صدا بزن (اگه کاربر جدید باشه، ثبت می‌شه)
    db.sync_user_profile(chat_id, message.from_user.first_name, message.from_user.username)
    args = message.text.split(' ', 1)

    if len(args) > 1 and args[1].strip():
        param = args[1].strip()  # رفع باگ: strip کردن پارامتر برای جلوگیری از مشکل فاصله‌های اضافی
        if param == "welcome":
            name = message.from_user.first_name or "رفیق"
            if is_new:
                # کاربر جدید — ثبت با source=welcome و شروع ویزارد
                db.upsert_user_basic(user_id, name, message.from_user.username, source="welcome")
                db.add_vip(user_id, 1)
                _start_new_user_wizard(chat_id, name)
            else:
                # کاربر قدیمی — پیام کوتاه
                caption = texts.ALREADY_MEMBER
                photo_id = PROMO_WELCOME_OLD_PHOTO_ID
                welcome_markup = types.InlineKeyboardMarkup(row_width=2)
                welcome_markup.add(
                    types.InlineKeyboardButton("🔍 تلهٔ من", callback_data="my_link_show"),
                    types.InlineKeyboardButton("ℹ️ اطلاعات من", callback_data="my_info"),
                    types.InlineKeyboardButton("📖 راهنما", callback_data="help"),
                    types.InlineKeyboardButton("🏅 VIP", callback_data="vip_info"),
                    types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu")
                )
                if photo_id:
                    try:
                        bot.send_photo(user_id, photo_id, caption=caption, reply_markup=welcome_markup)
                    except:
                        bot.reply_to(message, caption, reply_markup=welcome_markup)
                else:
                    bot.reply_to(message, caption, reply_markup=welcome_markup)
            return
        if not param.isdigit():
            try: owner_id = decode_id(param)
            except:
                bot.reply_to(message, "🔴 لینک نامعتبر.", reply_markup=main_menu(message.from_user.id)); return
        else: owner_id = int(param)
        clicker = message.from_user; clicker_id = clicker.id
        if clicker_id == owner_id:
            bot.reply_to(message, "🤨 روی لینک خودت نزن میفهمم😉", reply_markup=main_menu(message.from_user.id)); return
        if not can_click(clicker_id):
            bot.reply_to(message, "⏳ *کمی صبر کن و دوباره تلاش کن...*", reply_markup=main_menu(message.from_user.id)); return
        reg_click(clicker_id)
        clicker_name = clicker.first_name or "بی‌نام"; clicker_username = clicker.username
        # is_new از قبل محاسبه شده (clicker_id == user_id)
        if is_new:
            db.upsert_user_basic(clicker_id, clicker_name, clicker_username, source="referral")
            db.add_vip(clicker_id, 1)
            # شروع ویزارد برای کاربر جدید (بعد از ثبت کلیک)
            # ولی اول باید پیام‌های مربوط به کلیک رو بفرستیم
        photo_file_id = get_user_photo_file_id(clicker_id)
        try:
            chat_info = bot.get_chat(clicker_id)
            clicker_name = chat_info.first_name or clicker_name
            clicker_username = chat_info.username or clicker_username
        except: pass
        repeat = db.add_click(owner_id, clicker_id, clicker_name, clicker_username, is_new)
        vip_owner = db.is_vip(owner_id)
        t = datetime.datetime.now().strftime("%Y/%m/%d - %H:%M")
        display_name = get_user_display(clicker_id, clicker_name)

        gift_vip_given = False
        if is_new:
            db.add_vip(owner_id, 1)
            gift_vip_given = True

        # ----- اعطای XP به صاحب لینک -----
        # اگر این کلیک از یک فضول یکتاست (یعنی این clicker_id قبلاً روی این لینک کلیک نکرده)،
        # XP فضول جدید می‌گیره. همچنین اگر کاربر جدید بود، XP دعوت موفق.
        if repeat == 1:
            # اولین کلیک این clicker_id → فضول یکتای جدید
            bonus = 'first_snoop' if db.get_distinct_snoop_count(owner_id) == 1 else None
            award_xp_with_level_up_notify(
                owner_id, 0,
                recurring_type='new_distinct_snoop',
                bonus_type=bonus,
                chat_id=owner_id
            )
        if is_new:
            # دعوت موفق (کاربر جدید از لینک این شخص)
            bonus = 'first_invite' if db.get_user_invite_count(owner_id) == 1 else None
            award_xp_with_level_up_notify(
                owner_id, 0,
                recurring_type='successful_invite',
                bonus_type=bonus,
                chat_id=owner_id
            )
        # ----- اعطای XP روزانه به کلیک‌کننده -----
        maybe_daily_login_xp(clicker_id, chat_id=clicker_id)

        if db.is_snoop_muted(owner_id, clicker_id):
            scary_markup = types.InlineKeyboardMarkup(row_width=1)
            scary_markup.add(types.InlineKeyboardButton("🔍 ساخت تلهٔ من", callback_data="my_link_show"))
            scary_markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
            try:
                if SCARY_PHOTO_ID:
                    bot.send_photo(clicker_id, SCARY_PHOTO_ID, caption=texts.SCARY_TIMEOUT.format(link=user_link(clicker_id)), reply_markup=scary_markup)
                else:
                    bot.send_message(clicker_id, texts.SCARY_TIMEOUT.format(link=user_link(clicker_id)), reply_markup=scary_markup)
            except: pass
            return

        if is_subscribed(owner_id):
            msg = (f"🔔 *یه فضول روی لینک شما کلیک کرد!*\n"
                   f"🕒 {t}\n👤 {escape_md(display_name)}\n"
                   f"🆔 {fmt_id(clicker_id, vip_owner)}\n📎 {fmt_uname(clicker_username, vip_owner)}")
            if repeat > 3:
                msg += "\n🔥 *فضول حرفه‌ای شناسایی شد!*"
                msg += "\n\nاین فضول هی داره روی لینکت کلیک میکنه اگه اذیتت میکنه با دکمه بی‌صدا دهنشو ببند!"
            if gift_vip_given:
                msg += "\n\n🎁 *هدیه:* ۱ روز VIP به خاطر شکار یک کاربر جدید!"

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("🏷️ لقب دادن", callback_data=f"nick_{clicker_id}"),
                types.InlineKeyboardButton("✉️ پیام ناشناس", callback_data=f"anon_{clicker_id}"),
                types.InlineKeyboardButton("📊 اطلاعات فضول", callback_data=f"snoopdetail_{clicker_id}"),
                types.InlineKeyboardButton("🎁 هدیه به فضول", callback_data=f"giftvip_{clicker_id}"),
                types.InlineKeyboardButton("📋 لیست فضول‌ها", callback_data="snooplist_page_1"),
                types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu")
            )
            if repeat > 3:
                markup.add(types.InlineKeyboardButton("🔕 بی‌صدا", callback_data=f"mute_{clicker_id}"))

            if photo_file_id:
                try: bot.send_photo(owner_id, photo_file_id, caption=msg, reply_markup=markup)
                except:
                    try: bot.send_message(owner_id, msg, reply_markup=markup)
                    except: pass
            else:
                try: bot.send_message(owner_id, msg, reply_markup=markup)
                except: pass

            if db.is_vip(owner_id):
                welcome_photo = db.get_welcome_photo(owner_id); welcome_text = db.get_welcome_text(owner_id)
                if welcome_photo:
                    try: bot.send_photo(clicker_id, welcome_photo, caption=welcome_text or "")
                    except:
                        if welcome_text:
                            try: bot.send_message(clicker_id, welcome_text)
                            except: pass
                elif welcome_text:
                    try: bot.send_message(clicker_id, welcome_text)
                    except: pass
        else:
            db.save_pending_snoop(owner_id, clicker_id, display_name, t, vip_owner, clicker_username, repeat, gift_vip_given, photo_file_id)
            markup = build_channel_keyboard("show_pending_snoop", owner_id)
            # رفع باگ: اگر owner ربات را بلاک کرده، ارسال خطا می‌دهد و جریان clicker قطع می‌شود
            try:
                bot.send_message(owner_id, texts.SNOOP_CAUGHT_UNSUBSCRIBED, reply_markup=markup)
            except ApiTelegramException as e:
                if e.error_code == 403:
                    try:
                        db.mark_user_blocked_bot(owner_id)
                    except Exception:
                        pass
            except Exception:
                pass

        scary_markup = types.InlineKeyboardMarkup(row_width=1)
        scary_markup.add(types.InlineKeyboardButton("🔍 تلهٔ من", callback_data="my_link_show"))
        scary_markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        try:
            if SCARY_PHOTO_ID:
                bot.send_photo(clicker_id, SCARY_PHOTO_ID, caption=texts.SCARY_TIMEOUT.format(link=user_link(clicker_id)), reply_markup=scary_markup)
            else:
                bot.send_message(clicker_id, texts.SCARY_TIMEOUT.format(link=user_link(clicker_id)), reply_markup=scary_markup)
        except: pass

        # اگه کاربر جدید بود، بعد از پیام scary، ویزارد رو هم شروع کن
        if is_new:
            try:
                _start_new_user_wizard(clicker_id, clicker.first_name or "رفیق")
            except Exception as e:
                logger.error(f"Wizard start error: {e}")
        return
    else:
        # استارت بدون پارامتر — از is_new که در ابتدای تابع محاسبه شده استفاده می‌کنیم
        # رفع باگ: پارامتر باید strip شود تا فاصله‌های اضافی مشکلی نسازند
        name = message.from_user.first_name or "رفیق"

        if is_new:
            # کاربر جدید بدون پارامتر (از سرچ بله) — شروع ویزارد
            db.upsert_user_basic(user_id, name, message.from_user.username, source="organic")
            db.add_vip(user_id, 1)
            _start_new_user_wizard(chat_id, name)
            return

        if not is_subscribed(user_id):
            markup = build_channel_keyboard("main_menu", user_id)
            bot.reply_to(message, texts.FORCE_JOIN_PROMPT, reply_markup=markup if markup else main_menu(user_id))
        else:
            if db.is_vip(user_id):
                days_left = db.get_vip_days_left(user_id)   # بدون +1
                if days_left == 0:
                    days_str = "امروز آخرین روز"
                else:
                    days_str = f"{days_left} روز"
                bot.reply_to(message, texts.VIP_WELCOME.format(name=escape_md(name), days=days_str), reply_markup=main_menu(user_id))
            else:
                bot.reply_to(message, texts.WELCOME.format(link=user_link(user_id)), reply_markup=main_menu(user_id))

# ====== پخش همگانی (با استفاده از lock + کیبورد معمولی) ======
@bot.message_handler(func=lambda msg: broadcast_mode and msg.chat.id == broadcast_admin_chat
                     and not (msg.text and (msg.text.startswith('✅ تأیید و ارسال') or msg.text == '❌ لغو')),
                     content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'animation', 'video_note'])
def broadcast_handler(message):
    global broadcast_preview_msg
    with broadcast_lock:
        if not broadcast_mode:
            return
        if broadcast_started_at and (time.time() - broadcast_started_at > BROADCAST_TIMEOUT):
            set_broadcast_mode(False)
            # رفع باگ: wrap در try/except
            try:
                bot.reply_to(message, "⏱️ زمان حالت پخش همگانی قبلاً به پایان رسیده بود و خودکار لغو شد.")
            except Exception as e:
                logger.error(f"broadcast timeout notify error: {e}")
            return
        broadcast_preview_msg = message
        total_users = len(db.get_broadcast_targets())
    # کیبورد معمولی (Reply Keyboard) به‌جای اینلاین
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
    markup.add(
        types.KeyboardButton(f"✅ تأیید و ارسال ({total_users} کاربر)"),
        types.KeyboardButton("❌ لغو")
    )
    # رفع باگ: wrap در try/except
    try:
        bot.reply_to(message, f"📢 پیش‌نمایش پیام بالا. آیا برای {total_users} کاربر ارسال شود؟", reply_markup=markup)
    except Exception as e:
        logger.error(f"broadcast preview reply error: {e}")

def _send_anon_report_to_admin(sender_id, receiver_id, text, is_reply=False):
    try:
        s = db.get_user_basic(sender_id)
        s_name = s['first_name'] if s and s['first_name'] else "بی‌نام"
        s_username = s['username'] if s and s['username'] else "ندارد"
        r = db.get_user_basic(receiver_id)
        r_name = r['first_name'] if r and r['first_name'] else "بی‌نام"
        r_username = r['username'] if r and r['username'] else "ندارد"
        type_str = "پاسخ ناشناس" if is_reply else "پیام ناشناس"
        msg = (f"📬 *گزارش {type_str}*\n"
               f"از: {escape_md(s_name)} | 🆔 {sender_id} | @{s_username}\n"
               f"به: {escape_md(r_name)} | 🆔 {receiver_id} | @{r_username}\n\n"
               f"متن: {text}")
        bot.send_message(ADMIN_ID, msg)
    except Exception as e:
        logger.error(f"Anon report to admin error: {e}")

# ====== مدیریت پیام‌های متنی ======
@bot.message_handler(func=lambda msg: msg.text and not msg.text.startswith('/'), content_types=['text'])
def text_handler(message):
    chat_id = message.chat.id
    record_message(message.from_user.id)
    if db.is_blocked(chat_id):
        # رفع باگ: wrap در try/except
        try:
            bot.reply_to(message, "⛔ حساب شما مسدود شده است.")
        except Exception:
            pass
        return
    db.sync_user_profile(chat_id, message.from_user.first_name, message.from_user.username)
    text = message.text.strip()

    # ====== هندلینگ کیبورد معمولی پخش همگانی (تأیید/لغو) ======
    if chat_id == ADMIN_ID and broadcast_mode and broadcast_preview_msg:
        if text.startswith("✅ تأیید و ارسال"):
            # شروع ارسال
            preview_msg = broadcast_preview_msg
            set_broadcast_mode(False, None, preview_msg, None)
            # حذف کیبورد معمولی
            bot.send_message(chat_id, "🚀 شروع ارسال همگانی...", reply_markup=types.ReplyKeyboardRemove())
            # شروع ارسال در thread جداگانه با نمونه مستقل TeleBot
            threading.Thread(
                target=_run_broadcast_async,
                args=(chat_id, preview_msg),
                daemon=True
            ).start()
            return
        elif text == "❌ لغو":
            set_broadcast_mode(False)
            bot.send_message(chat_id, "❌ ارسال همگانی لغو شد.", reply_markup=types.ReplyKeyboardRemove())
            return

    state = get_user_state(chat_id)
    if state is not None:
        if state[0] == 'gift_code':
            clear_user_state(chat_id)
            now = time.time()
            # حذف تلاش‌های قدیمی (بیشتر از ۱ ساعت)
            while gift_attempt_rate[chat_id] and gift_attempt_rate[chat_id][0] < now - 3600:
                gift_attempt_rate[chat_id].popleft()

            if len(gift_attempt_rate[chat_id]) >= 5:
                bot.reply_to(message, "⏳ تعداد تلاش‌های شما برای کد هدیه به پایان رسید. یک ساعت صبر کنید.",
                             reply_markup=home_markup())
                return

            # ثبت این تلاش
            gift_attempt_rate[chat_id].append(now)

            result, gift_data = db.redeem_gift(text, chat_id)
            if result:
                bot.reply_to(message, f"🎉 کد با موفقیت فعال شد! {gift_data} روز VIP به حساب شما اضافه شد.",
                             reply_markup=home_markup())
            else:
                bot.reply_to(message, f"❌ {gift_data}", reply_markup=home_markup())
            return

        elif state[0] == 'anon_reply':
            target_id = state[1]; clear_user_state(chat_id)
            if not is_subscribed(chat_id):
                markup = build_channel_keyboard(f"anon_reply_{target_id}", chat_id)
                if markup:
                    bot.reply_to(message, texts.FORCE_JOIN_PROMPT, reply_markup=markup)
                return
            # فیلتر محتوای نامناسب
            is_bad, reason = is_inappropriate_content(text)
            if is_bad:
                bot.reply_to(message,
                    f"❌ پیام شما شامل {reason} است و ارسال نشد.\n"
                    "لطفاً متن مناسبی وارد کنید.",
                    reply_markup=home_markup())
                return
            # اصلاح: افزودن rate limit
            if not can_send_anon(chat_id, target_id):
                bot.reply_to(message, "⏳ محدودیت پیام ناشناس! کمی صبر کن.", reply_markup=home_markup()); return
            # رفع باگ: بررسی block قبل از reg_anon — وگرنه rate limit بیهوده مصرف می‌شود
            if db.is_anon_blocked(target_id, chat_id):
                bot.reply_to(message, "⛔ این کاربر شما را بلاک کرده است. پاسخ ارسال نشد.", reply_markup=home_markup()); return
            reg_anon(chat_id, target_id)
            # رفع باگ: اعمال نقاب VIP برای پاسخ ناشناس هم (مثل anon_msg)
            mask = None
            if db.is_vip(chat_id):
                mask_data = db.get_user_mask(chat_id)
                if mask_data:
                    emoji, mask_text = mask_data
                    mask = f"{emoji} {escape_md(mask_text)}" if mask_text else emoji
            msg_text = f"🎭 *{mask}* نجوا کرد:\n{escape_md(text)}" if mask else f"📩 *پاسخ ناشناس:*\n{escape_md(text)}"
            reply_markup = types.InlineKeyboardMarkup()
            reply_markup.add(types.InlineKeyboardButton("🔄 پاسخ ناشناس", callback_data=f"anon_reply_{chat_id}"))
            # رفع باگ: حذف dead code — چون در این نقطه target مطمئناً sender را بلاک نکرده
            reply_markup.add(types.InlineKeyboardButton("🚫 بلاک", callback_data=f"block_{chat_id}"),
                             types.InlineKeyboardButton("⚠️ گزارش تخلف", callback_data=f"report_{chat_id}"))
            try:
                bot.send_message(target_id, msg_text, reply_markup=reply_markup)
                db.add_anon_log(chat_id, target_id, text)
                bot.reply_to(message, "📨 پاسخ ناشناس ارسال شد...", reply_markup=home_markup())
                _send_anon_report_to_admin(chat_id, target_id, text, is_reply=True)
            except Exception as e:
                logger.error(f"Anon reply send error: {e}")
                bot.reply_to(message, "❌ ارسال ناموفق بود. لطفاً دوباره تلاش کن.", reply_markup=home_markup())
            return

        elif state[0] == 'anon_msg':
            target_id = state[1]; clear_user_state(chat_id)
            if not is_subscribed(chat_id):
                markup = build_channel_keyboard(f"anon_{target_id}", chat_id)
                if markup:
                    bot.reply_to(message, texts.FORCE_JOIN_PROMPT, reply_markup=markup)
                return
            # فیلتر محتوای نامناسب
            is_bad, reason = is_inappropriate_content(text)
            if is_bad:
                bot.reply_to(message,
                    f"❌ پیام شما شامل {reason} است و ارسال نشد.\n"
                    "لطفاً متن مناسبی وارد کنید.",
                    reply_markup=home_markup())
                return
            if not can_send_anon(chat_id, target_id):
                bot.reply_to(message, "⏳ محدودیت پیام ناشناس! کمی صبر کن.", reply_markup=home_markup()); return
            if db.is_anon_blocked(target_id, chat_id):
                bot.reply_to(message, "⛔ این کاربر شما را بلاک کرده است. پیام ارسال نشد.", reply_markup=home_markup()); return
            reg_anon(chat_id, target_id)
            mask = None
            if db.is_vip(chat_id):
                mask_data = db.get_user_mask(chat_id)
                if mask_data:
                    emoji, mask_text = mask_data
                    mask = f"{emoji} {escape_md(mask_text)}" if mask_text else emoji
            msg_text = f"🎭 *{mask}* نجوا کرد:\n{escape_md(text)}" if mask else f"📩 *پیام ناشناس:*\n{escape_md(text)}"
            reply_markup = types.InlineKeyboardMarkup()
            reply_markup.add(types.InlineKeyboardButton("🔄 پاسخ ناشناس", callback_data=f"anon_reply_{chat_id}"))
            # رفع باگ: حذف dead code — چون در این نقطه target مطمئناً sender را بلاک نکرده
            reply_markup.add(types.InlineKeyboardButton("🚫 بلاک", callback_data=f"block_{chat_id}"),
                             types.InlineKeyboardButton("⚠️ گزارش تخلف", callback_data=f"report_{chat_id}"))
            try:
                bot.send_message(target_id, msg_text, reply_markup=reply_markup)
                db.add_anon_log(chat_id, target_id, text)
                bot.reply_to(message, "📨 پیام ناشناس ارسال شد...", reply_markup=home_markup())
                _send_anon_report_to_admin(chat_id, target_id, text, is_reply=False)
            except Exception as e:
                logger.error(f"Anon send error: {e}")
                bot.reply_to(message, "❌ ارسال ناموفق بود. لطفاً دوباره تلاش کن.", reply_markup=home_markup())
            return

        elif state[0] == 'nickname':
            cid = state[1]; clear_user_state(chat_id)
            # فیلتر محتوای نامناسب
            is_bad, reason = is_inappropriate_content(text)
            if is_bad:
                bot.reply_to(message,
                    f"❌ لقب شما شامل {reason} است.\n"
                    "لطفاً لقب دیگری وارد کنید.",
                    reply_markup=home_markup())
                return
            db.set_nickname(chat_id, cid, text)
            bot.reply_to(message, f"📜 لقب «{escape_md(text)}» در کتاب سایه‌ها ثبت شد.", reply_markup=home_markup())
            return

        elif state[0] == 'link_text':
            clear_user_state(chat_id)
            full_link = f"[{escape_md(text)}]({user_link(chat_id)})"
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("📋 کپی لینک", callback_data="copy_dummy",
                                                  copy_text=types.CopyTextButton(full_link)))
            markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
            final_text = (
                f"🎭 *هایپرلینک تو ساخته شد:*\n{full_link}\n\n"
                f"💡 اونو کپی کن و توی بیوگرافیت بذار تا فضول‌ها رو شکار کنی..."
            )
            bot.reply_to(message, final_text, reply_markup=markup)
            return

        elif state[0] == 'welcome_text':
            clear_user_state(chat_id)
            if not db.is_vip(chat_id):
                bot.reply_to(message, VIP_EXPIRED_MSG, reply_markup=vip_menu_button()); return
            # فیلتر محتوای نامناسب
            is_bad, reason = is_inappropriate_content(text)
            if is_bad:
                bot.reply_to(message,
                    f"❌ متن شما شامل {reason} است.\n"
                    "لطفاً متن دیگری وارد کنید.",
                    reply_markup=vip_menu_button())
                return
            db.set_welcome_text(chat_id, text)
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🖼️ تنظیم عکس خوش‌آمدگویی", callback_data="set_welcome_photo"))
            markup.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="vip_info"))
            markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
            bot.reply_to(message,
                "📜 متن خوش‌آمدگویی ثبت شد.\n"
                "🖼️ می‌تونی یه عکس هم بهش اضافه کنی تا کامل‌تر بشه.\n"
                "دکمهٔ زیر رو بزن یا بعداً از منوی VIP اقدام کن.",
                reply_markup=markup)
            return

        elif state[0] == 'mask_emoji':
            clear_user_state(chat_id); emoji = text.strip()
            if not db.is_vip(chat_id):
                bot.reply_to(message, VIP_EXPIRED_MSG, reply_markup=vip_menu_button()); return
            set_user_state(chat_id, ('mask_text', emoji))
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(types.InlineKeyboardButton("بدون لقب", callback_data="mask_skip_text"),
                       types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_state"))
            bot.reply_to(message, "🎭 حالا لقب (متن) نقاب را بفرست، یا یکی از دکمه‌های زیر را بزن.", reply_markup=markup)
            return

        elif state[0] == 'mask_text':
            emoji = state[1]; clear_user_state(chat_id); mask_text = text.strip()
            if not db.is_vip(chat_id):
                bot.reply_to(message, VIP_EXPIRED_MSG, reply_markup=vip_menu_button()); return
            # فیلتر محتوای نامناسب
            is_bad, reason = is_inappropriate_content(mask_text)
            if is_bad:
                bot.reply_to(message,
                    f"❌ لقب نقاب شما شامل {reason} است.\n"
                    "لطفاً لقب دیگری وارد کنید.",
                    reply_markup=vip_menu_button())
                return
            db.set_user_mask(chat_id, emoji, mask_text)
            bot.reply_to(message, f"🎭 نقاب کارآگاهی تو: {emoji} {mask_text}", reply_markup=vip_menu_button())
            return

        elif state[0] == 'new_gift_days':
            days = int(text) if text.isdigit() else 0
            if days <= 0:
                clear_user_state(chat_id)
                bot.reply_to(message, "❌ تعداد روز نامعتبر.", reply_markup=admin_panel_back_markup()); return
            set_user_state(chat_id, ('new_gift_uses', days))
            bot.reply_to(message, "حالا تعداد استفاده (ظرفیت) کد را وارد کنید:", reply_markup=cancel_markup())
            return

        elif state[0] == 'new_gift_uses':
            days = state[1]; clear_user_state(chat_id)
            uses = int(text) if text.isdigit() else 0
            if uses <= 0:
                bot.reply_to(message, "❌ ظرفیت نامعتبر.", reply_markup=admin_panel_back_markup()); return
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            db.create_gift_code(code, days, uses)
            bot.reply_to(message, f"🎁 کد هدیه ساخته شد:\n{code}\nروز: {days} | ظرفیت: {uses}", reply_markup=admin_panel_back_markup())
            return

        elif state[0] == 'admin_search_user':
            clear_user_state(chat_id)
            process_admin_search(message)
            return

        elif state[0] == 'admin_addvip':
            clear_user_state(chat_id)
            process_admin_addvip(message)
            return

        elif state[0] == 'admin_edit_price':
            days = state[1]; clear_user_state(chat_id)
            # حذف کاراکترهای اضافی مثل کاما یا تومان
            cleaned = text.replace(',', '').replace('ریال', '').replace('تومان', '').strip()
            # تبدیل اعداد فارسی به انگلیسی برای پردازش
            for i, d in enumerate(PERSIAN_DIGITS):
                cleaned = cleaned.replace(d, str(i))
            try:
                new_price = int(cleaned)
                if new_price <= 0:
                    raise ValueError()
                # اگر به تومان وارد شده (عدد کوچک)، به ریال تبدیل کن
                # اگر عدد کمتر از ۱۰۰۰۰ هست احتمالا تومان وارد شده
                if new_price < 1000:
                    new_price = new_price * 10  # تبدیل تومان به ریال
                VIP_PRICES[days] = new_price
                db.set_vip_price(days, new_price)
                bot.reply_to(message,
                    f"✅ قیمت {to_persian_digits(days)} روزه با موفقیت به‌روزرسانی شد.\n"
                    f"💵 قیمت جدید: {fmt_amount_rial(new_price)} ({fmt_amount_toman(new_price)})",
                    reply_markup=admin_panel_back_markup())
            except (ValueError, TypeError):
                bot.reply_to(message,
                    "❌ عدد نامعتبر. لطفاً فقط عدد (به ریال یا تومان) وارد کنید.",
                    reply_markup=admin_panel_back_markup())
            return

        elif state[0] == 'admin_change_prices_iter':
            # state = ('admin_change_prices_iter', sorted_plans, current_index, collected_dict)
            sorted_plans = state[1]
            current_idx = state[2]
            collected = state[3] if len(state) > 3 else {}
            # پاک‌سازی و تبدیل عدد
            cleaned = text.replace(',', '').replace('ریال', '').replace('تومان', '').strip()
            for i, d in enumerate(PERSIAN_DIGITS):
                cleaned = cleaned.replace(d, str(i))
            try:
                new_price = int(cleaned)
                if new_price <= 0:
                    raise ValueError()
                if new_price < 1000:
                    new_price = new_price * 10  # تومان → ریال
                current_days = sorted_plans[current_idx]
                collected[current_days] = new_price
            except (ValueError, TypeError):
                bot.reply_to(message, "❌ عدد نامعتبر. لطفاً فقط عدد وارد کنید.")
                return

            # مرحلهٔ بعد
            next_idx = current_idx + 1
            if next_idx >= len(sorted_plans):
                # تمام شد — اعمال همه قیمت‌ها
                clear_user_state(chat_id)
                for d, p in collected.items():
                    VIP_PRICES[d] = p
                    db.set_vip_price(d, p)
                # نمایش خلاصه
                summary_lines = ["✅ *قیمت‌های جدید VIP با موفقیت ذخیره شدند:*\n"]
                for d in sorted_plans:
                    p = collected.get(d, VIP_PRICES.get(d, 0))
                    summary_lines.append(f"• {to_persian_digits(d)} روز: {fmt_amount_rial(p)} ({fmt_amount_toman(p)})")
                # بازگشت به زیرمنوی VIP
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="admin_vip_submenu"))
                m.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.reply_to(message, "\n".join(summary_lines), reply_markup=m)
            else:
                # ادامه با پلن بعدی
                set_user_state(chat_id, ('admin_change_prices_iter', sorted_plans, next_idx, collected))
                next_days = sorted_plans[next_idx]
                bot.reply_to(message,
                    f"✅ ذخیره شد. حالا پلن بعدی:\n\n"
                    f"{to_persian_digits(next_idx + 1)} از {to_persian_digits(len(sorted_plans))}:\n"
                    f"قیمت جدید برای *{to_persian_digits(next_days)} روزه* رو به ریال وارد کنید.\n"
                    f"📌 قیمت فعلی: {to_persian_int(VIP_PRICES.get(next_days, 0))} ریال",
                    reply_markup=cancel_markup())
            return

        elif state[0] == 'admin_quick_vip':
            target_id = state[1]; clear_user_state(chat_id)
            process_admin_quick_vip(message, target_id)
            return

        elif state[0] == 'admin_new_channel':
            clear_user_state(chat_id)
            ch_input = text.strip()
            info = fetch_channel_info(ch_input)
            if not info or info.get("name") == str(ch_input):
                bot.send_message(chat_id, "❌ نتوانستم اطلاعات کانال را دریافت کنم. مطمئن شوید ربات عضو است.", reply_markup=admin_panel_back_markup())
                return

            name = info["name"]
            link = info["link"]
            # اگر کانال عمومی است (با @ شروع می‌شود)، تست با همان @username
            test_id = info["api_id"]   # همیشه شناسهٔ عددی استاندارد (با -100)

            bot_id = bot.user.id
            try:
                member = bot.get_chat_member(test_id, bot_id)
                if member.status not in ['administrator', 'creator']:
                    bot.send_message(
                        chat_id,
                        "❌ ربات باید **ادمین کانال** باشد تا بتواند عضویت کاربران را بررسی کند.\n"
                        "لطفاً ربات را در کانال ادمین کنید و دوباره امتحان کنید.",
                        reply_markup=admin_panel_back_markup()
                    )
                    return
            except ApiTelegramException as e:
                err_msg = str(e).lower()
                if 'no such group' in err_msg or 'chat not found' in err_msg:
                    bot.send_message(chat_id, "❌ کانال مورد نظر یافت نشد. مطمئن شوید شناسه درست است و ربات عضو کانال باشد.", reply_markup=admin_panel_back_markup())
                elif 'user not found' in err_msg:
                    bot.send_message(chat_id, "❌ ربات نمی‌تواند وضعیت خود را بررسی کند. احتمالاً در کانال عضو نیست.", reply_markup=admin_panel_back_markup())
                else:
                    bot.send_message(chat_id, f"❌ خطای API: {e}", reply_markup=admin_panel_back_markup())
                return
            except Exception as e:
                logger.error(f"Test get_chat_member failed: {e}")
                bot.send_message(chat_id, f"❌ خطای ناشناخته: {e}", reply_markup=admin_panel_back_markup())
                return

            # ذخیره با همان شناسه‌ای که تست شده (برای عمومی یعنی @username)
            db.add_forced_channel(test_id, name, link)
            # رفع باگ: بررسی تکراری نبودن قبل از append
            if test_id not in CHANNELS:
                CHANNELS.append(test_id)
            channel_info[test_id] = {"name": name, "link": link}
            broken_channels.discard(test_id)
            bot.send_message(chat_id, f"✅ کانال «{name}» با شناسهٔ {test_id} اضافه شد.", reply_markup=admin_panel_back_markup())
            return

    target_id = pop_admin_reply(chat_id)
    if target_id is not None:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📞 پاسخ", callback_data=f"support_reply_{ADMIN_ID}"),
                   types.InlineKeyboardButton("🚪 خروج از پشتیبانی", callback_data="support_exit"))
        # رفع باگ: اگر کاربر ربات را بلاک کرده، ارسال خطا می‌دهد
        try:
            bot.send_message(target_id, f"📩 *پاسخ مدیر:*\n{text}", reply_markup=markup)
            bot.reply_to(message, "📨 پاسخ ارسال شد.", reply_markup=admin_panel_back_markup())
        except ApiTelegramException as e:
            if e.error_code == 403:
                try:
                    db.mark_user_blocked_bot(target_id)
                except Exception:
                    pass
                bot.reply_to(message, "⚠️ این کاربر ربات را بلاک کرده است. پیام ارسال نشد.", reply_markup=admin_panel_back_markup())
            else:
                logger.error(f"Admin reply to {target_id} error: {e}")
                bot.reply_to(message, "❌ خطا در ارسال پیام.", reply_markup=admin_panel_back_markup())
        except Exception as e:
            logger.error(f"Admin reply to {target_id} error: {e}")
            bot.reply_to(message, "❌ خطا در ارسال پیام.", reply_markup=admin_panel_back_markup())
        return

    if is_support_session(chat_id):
        u = db.get_user_basic(chat_id)
        name = u['first_name'] if u and u['first_name'] else "بی‌نام"
        username = u['username'] if u and u['username'] else None
        total_clicks = db.get_clicks_count(chat_id); distinct_snoops = db.get_distinct_snoop_count(chat_id)
        is_active_vip = db.is_vip(chat_id)
        vip_status = "فعال" if is_active_vip else "غیرفعال"
        # رفع باگ: +1 حذف شد — get_vip_days_left روزهای باقی‌مانده واقعی را برمی‌گرداند
        days_left = db.get_vip_days_left(chat_id)
        vip_str = f"👑 {to_persian_digits(days_left)} روز" if vip_status == "فعال" else vip_status
        admin_msg = (f"📩 *پیام پشتیبانی*\n"
                     f"👤 {escape_md(name)}\n🆔 {chat_id}\n📎 @{username if username else 'ندارد'}\n"
                     f"👥 فضول‌های دریافتی: {total_clicks}\n🔍 شکارهای یکتا: {distinct_snoops}\n🏅 VIP: {vip_str}\n\n"
                     f"💬 متن: {text}")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📞 پاسخ", callback_data=f"support_reply_{chat_id}"))
        bot.send_message(ADMIN_ID, admin_msg, reply_markup=markup)
        markup_user = types.InlineKeyboardMarkup(row_width=2)
        markup_user.add(types.InlineKeyboardButton("🚪 خروج از پشتیبانی", callback_data="support_exit"),
                        types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        set_support_partner(chat_id, ADMIN_ID)    
        set_support_partner(ADMIN_ID, chat_id)    
        # رفع باگ: wrap در try/except
        try:
            bot.reply_to(message, "📞 پیامت به مدیر رسید.", reply_markup=markup_user)
        except ApiTelegramException as e:
            if e.error_code == 403:
                try: db.mark_user_blocked_bot(chat_id)
                except Exception: pass
            else:
                logger.error(f"Support reply notify error: {e}")
        except Exception as e:
            logger.error(f"Support reply notify error: {e}")
        return

    # ====== fallback: اگه کاربر در هیچ حالتی نبود و پیامش هم به هیچ هندلری نخورد، منوی خانه رو بفرست ======
    # این بخش فقط برای پیام‌های متنی که هیچ state ای ندارن اجرا می‌شه
    home_text = build_dynamic_home_text(chat_id)
    # رفع باگ: wrap در try/except — اگه کاربر ربات رو بلاک کرده، کل polling thread کرش نکنه
    try:
        bot.reply_to(message, home_text, reply_markup=main_menu(chat_id))
    except ApiTelegramException as e:
        if e.error_code == 403:
            try: db.mark_user_blocked_bot(chat_id)
            except Exception: pass
        else:
            logger.error(f"text_handler fallback send error: {e}")
    except Exception as e:
        logger.error(f"text_handler fallback send error: {e}")

# ====== دریافت عکس خوش‌آمد ======
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    chat_id = message.chat.id
    # رفع باگ: ثبت پیام برای آمار 24 ساعته
    record_message(message.from_user.id)
    if db.is_blocked(chat_id):
        return
    db.sync_user_profile(chat_id, message.from_user.first_name, message.from_user.username)
    state = get_user_state(chat_id)
    if state and state[0] == 'welcome_photo':
        clear_user_state(chat_id)
        if not db.is_vip(chat_id):
            # رفع باگ: wrap در try/except
            try:
                bot.reply_to(message, VIP_EXPIRED_MSG, reply_markup=vip_menu_button())
            except Exception:
                pass
            return
        file_id = message.photo[-1].file_id
        db.set_welcome_photo(chat_id, file_id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📝 تنظیم متن خوش‌آمدگویی", callback_data="set_welcome"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="vip_info"))
        markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        # رفع باگ: wrap در try/except
        try:
            bot.reply_to(message,
                "🖼️ عکس خوش‌آمدگویی ثبت شد.\n"
                "📝 حالا می‌تونی یه متن هم بهش اضافه کنی تا پیامت کامل‌تر بشه!\n"
                "دکمهٔ زیر رو بزن یا بعداً از منوی VIP اقدام کن.",
                reply_markup=markup)
        except Exception as e:
            logger.error(f"photo_handler welcome_photo reply error: {e}")
        return

    # اگر در حالت پشتیبانی هسته، عکس رو هم به ادمین فوروارد کن
    if is_support_session(chat_id):
        _forward_support_message_to_admin(message)
        return

    # fallback: اگه کاربر در هیچ حالتی نبود و عکس فرستاد، منوی خانه رو بفرست
    home_text = build_dynamic_home_text(chat_id)
    # رفع باگ: wrap در try/except — جلوگیری از کرش polling
    try:
        bot.reply_to(message, home_text, reply_markup=main_menu(chat_id))
    except ApiTelegramException as e:
        if e.error_code == 403:
            try: db.mark_user_blocked_bot(chat_id)
            except Exception: pass
        else:
            logger.error(f"photo_handler fallback send error: {e}")
    except Exception as e:
        logger.error(f"photo_handler fallback send error: {e}")

# ====== هندلر همه انواع فایل برای پشتیبانی ======
# این هندلر فقط زمانی فعال می‌شود که کاربر در حالت پشتیبانی باشد
@bot.message_handler(content_types=['video', 'document', 'audio', 'voice', 'video_note', 'animation', 'sticker', 'contact', 'location'])
def file_handler_support(message):
    """هندلر همه انواع فایل — فقط در حالت پشتیبانی فعال است."""
    chat_id = message.chat.id
    # رفع باگ: ثبت پیام برای آمار 24 ساعته
    record_message(message.from_user.id)
    if db.is_blocked(chat_id):
        return
    # فقط در حالت پشتیبانی فعال باشد
    if not is_support_session(chat_id):
        # اگه کاربر در حالت پشتیبانی نیست و فایل فرستاد، منوی خانه رو بفرست
        home_text = build_dynamic_home_text(chat_id)
        # رفع باگ: wrap در try/except
        try:
            bot.reply_to(message, home_text, reply_markup=main_menu(chat_id))
        except ApiTelegramException as e:
            if e.error_code == 403:
                try: db.mark_user_blocked_bot(chat_id)
                except Exception: pass
            else:
                logger.error(f"file_handler fallback send error: {e}")
        except Exception as e:
            logger.error(f"file_handler fallback send error: {e}")
        return
    _forward_support_message_to_admin(message)

def _forward_support_message_to_admin(message):
    """فوروارد یک پیام (هر نوعی) از کاربر به ادمین در حالت پشتیبانی.
    پیام به‌صورت یک‌تکه (forward) ارسال می‌شود تا چندتکه نشود."""
    chat_id = message.chat.id
    try:
        # فوروارد مستقیم پیام به ادمین — همیشه یک‌تکه
        bot.forward_message(ADMIN_ID, from_chat_id=chat_id, message_id=message.message_id)

        # ارسال متادیتای کاربر به‌عنوان پیام جداگانه (کوتاه)
        u = db.get_user_basic(chat_id)
        name = u['first_name'] if u and u['first_name'] else "بی‌نام"
        username = u['username'] if u and u['username'] else None
        total_clicks = db.get_clicks_count(chat_id)
        distinct_snoops = db.get_distinct_snoop_count(chat_id)
        is_active_vip = db.is_vip(chat_id)
        vip_status = "فعال" if is_active_vip else "غیرفعال"
        # رفع باگ: +1 حذف شد — get_vip_days_left روزهای باقی‌مانده واقعی را برمی‌گرداند
        days_left = db.get_vip_days_left(chat_id)
        vip_str = f"👑 {to_persian_digits(days_left)} روز" if vip_status == "فعال" else vip_status

        admin_meta = (f"📩 *پیام پشتیبانی*\n"
                      f"👤 {escape_md(name)}\n🆔 {to_persian_digits(chat_id)}\n📎 @{username if username else 'ندارد'}\n"
                      f"👥 فضول‌های دریافتی: {to_persian_int(total_clicks)}\n🔍 شکارهای یکتا: {to_persian_int(distinct_snoops)}\n🏅 VIP: {vip_str}")
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📞 پاسخ", callback_data=f"support_reply_{chat_id}"))
        bot.send_message(ADMIN_ID, admin_meta, reply_markup=markup)

        # تأیید به کاربر
        markup_user = types.InlineKeyboardMarkup(row_width=2)
        markup_user.add(types.InlineKeyboardButton("🚪 خروج از پشتیبانی", callback_data="support_exit"),
                        types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        set_support_partner(chat_id, ADMIN_ID)
        set_support_partner(ADMIN_ID, chat_id)
        bot.reply_to(message, "📞 پیامت به مدیر رسید.", reply_markup=markup_user)
    except Exception as e:
        logger.error(f"Support forward error: {e}")
        # رفع باگ: wrap در try/except
        try:
            bot.reply_to(message, "❌ خطا در ارسال پیام. لطفاً دوباره تلاش کنید.")
        except Exception:
            pass

# ====== لیست فضول‌ها ======
def show_snoop_list(chat_id, page=1, message_id=None):
    snoops = db.get_snoops(chat_id)
    if not snoops:
        text = "📁 هنوز هیچ فضولی در دامت نیفتاده..."
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🏠 بازگشت به منو", callback_data="main_menu"))
        if message_id:
            try:
                bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
                return
            except Exception:
                pass
        bot.send_message(chat_id, text, reply_markup=markup)
        return

    per_page = 20; total_pages = max(1, (len(snoops)+per_page-1)//per_page)
    page = max(1, min(page, total_pages))
    start = (page-1)*per_page; end = start+per_page
    page_items = snoops[start:end]
    buttons = []
    for s in page_items:
        disp = s.get('nickname') or s['name']
        emoji = get_user_rank_emoji(s['clicker_id'])
        btn_text = f"{emoji} {disp}" if emoji else disp
        buttons.append(types.InlineKeyboardButton(btn_text, callback_data=f"snoopdetail_{s['clicker_id']}"))
    markup = types.InlineKeyboardMarkup(row_width=2)
    for i in range(0, len(buttons), 2):
        if i+1 < len(buttons): markup.add(buttons[i], buttons[i+1])
        else: markup.add(buttons[i])
    nav = []
    if page > 1: nav.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"snooplist_page_{page-1}"))
    if page < total_pages: nav.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"snooplist_page_{page+1}"))
    if nav: markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))

    text = f"📋 *لیست فضول‌ها (صفحه {page} از {total_pages})*"
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, reply_markup=markup)


# ====== ماموریت‌ها — نمایش صفحه‌بندی‌شده ======
def show_tasks_page(chat_id, user_id, page, call):
    """نمایش لیست ماموریت‌ها — مینیمال، با progress bar.
    - تسک‌های تکمیل‌شده به‌عنوان دکمه نمایش داده نمی‌شوند.
    - از هر گروه milestone فقط کمترین مرحله‌ای که هنوز انجام نشده نمایش داده می‌شود.
    - progress bar با درصد نمایش داده می‌شود."""
    all_tasks = tasks_module.TASKS
    total = len(all_tasks)

    # ابتدا _check_and_award_tasks_xp رو صدا بزن تا تسک‌های تازه تکمیل‌شده رو پردازش کنه
    # و نوتیفیکیشن‌های در انتظار رو هم در نظر بگیر
    try:
        _check_and_award_tasks_xp(user_id)
    except Exception as e:
        logger.error(f"Tasks check on page view: {e}")

    # محاسبه وضعیت هر تسک (done یا نه)
    task_status = {}  # task_id -> bool (done?)
    done_count = 0
    for t in all_tasks:
        is_done = db.has_bonus(user_id, f"task_{t['id']}")
        if not is_done:
            try:
                with db._lock:
                    is_done = bool(t["check"](db, user_id))
                # اگر تازه انجام شده، XP رو نمی‌دیم چون _check_and_award_tasks_xp قبلاً داده
            except Exception as e:
                logger.error(f"Task check error {t['id']}: {e}")
                is_done = False
        task_status[t["id"]] = is_done
        if is_done:
            done_count += 1

    # فیلتر کردن تسک‌های نمایش‌داده‌شده:
    # 1. تسک‌های انجام‌شده حذف می‌شوند
    # 2. از هر گروه milestone فقط کمترین threshold که هنوز انجام نشده می‌ماند
    remaining_tasks = []
    groups_done_threshold = {}  # group -> max threshold done
    groups_added = set()  # گروه‌هایی که قبلاً تسک فعالشون اضافه شده

    # اول pass اول: محاسبه max threshold done برای هر گروه
    for t in all_tasks:
        if "group" in t and t["group"]:
            grp = t["group"]
            if task_status.get(t["id"], False):
                thr = t.get("threshold", 0)
                if grp not in groups_done_threshold or thr > groups_done_threshold[grp]:
                    groups_done_threshold[grp] = thr

    # pass دوم: انتخاب تسک‌های نمایش
    for t in all_tasks:
        if task_status.get(t["id"], False):
            # تسک انجام شده — رد کن
            continue
        if "group" in t and t["group"]:
            grp = t["group"]
            thr = t.get("threshold", 0)
            # اگر threshold این تسک کمتر یا مساوی max done باشه، یعنی قبلاً انجام شده
            # (البته اگه done_count برای این تسک true نباشه، ولی threshold کمتر باشه، یعنی باید done می‌بود)
            # این حالت نباید رخ بده چون check() باید true برمی‌گرداند
            # اما برای اطمینان، فقط اولین تسک با threshold > max_done رو می‌گیریم
            max_done = groups_done_threshold.get(grp, 0)
            if thr <= max_done:
                # این تسک باید done می‌بود ولی نشده — مشکلی هست، ردش کن
                continue
            if grp in groups_added:
                # قبلاً تسک فعال این گروه اضافه شده
                continue
            groups_added.add(grp)
            remaining_tasks.append(t)
        else:
            # تسک بدون group — همیشه نمایش (اگه done نباشه)
            remaining_tasks.append(t)

    # حالا remaining_tasks لیست تسک‌های قابل نمایشه
    total_remaining = len(remaining_tasks)
    per_page = 10
    total_pages = max(1, (total_remaining + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_tasks = remaining_tasks[start:end]

    # progress bar
    pct = int(done_count * 100 / total) if total else 0
    bar_len = 20
    filled = int(pct * bar_len / 100)
    bar = '█' * filled + '░' * (bar_len - filled)

    # متن مینیمال
    lines = [
        f"🎯 *ماموریت‌های کارآگاه*",
        f"━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📈 {to_persian_digits(done_count)} از {to_persian_digits(total)} ({to_persian_digits(pct)}٪)",
        f"{bar}",
        f"",
    ]

    # تسک‌های صفحهٔ فعلی — فقط نام + XP
    current_cat = None
    for t in page_tasks:
        if t["category"] != current_cat:
            current_cat = t["category"]
            info = tasks_module.CATEGORY_INFO[current_cat]
            lines.append(f"\n{info['emoji']} *{info['name']}*")
        lines.append(f"⬜ {t['name']} (+{to_persian_digits(t['xp'])})")

    if not page_tasks:
        lines.append("\n🎉 همهٔ ماموریت‌های این صفحه تکمیل شده‌اند!")

    lines.append(f"\n📄 صفحهٔ {to_persian_digits(page)} از {to_persian_digits(total_pages)}")

    # کیبورد — فقط تسک‌های انجام‌نشده به‌عنوان دکمه
    markup = types.InlineKeyboardMarkup(row_width=1)
    for t in page_tasks:
        btn = types.InlineKeyboardButton(
            f"⬜ {t['name']} (+{to_persian_digits(t['xp'])})",
            callback_data=f"task_detail_{t['id']}"
        )
        markup.add(btn)

    # دکمه‌های ناوبری
    nav = []
    if page > 1:
        nav.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"tasks_page_{page-1}"))
    if page < total_pages:
        nav.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"tasks_page_{page+1}"))
    if nav:
        markup.add(*nav)
    markup.add(types.InlineKeyboardButton("🔙 اطلاعات من", callback_data="my_info"))
    markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))

    # ارسال/ویرایش پیام
    if call.message.content_type == 'photo':
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except: pass
        bot.send_message(chat_id, "\n".join(lines), reply_markup=markup)
    else:
        try:
            bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
        except:
            bot.send_message(chat_id, "\n".join(lines), reply_markup=markup)

    # بررسی آیا نوتیفیکیشن تسک تازه تکمیل‌شده‌ای داریم
    # همه تسک‌ها حداقل ۵۰ XP دارند، پس همیشه مجموع به‌صورت یک پیام ارسال می‌شود
    pending = _get_and_clear_pending_task_notifications(user_id)
    if pending:
        total_xp = sum(t["xp"] for t in pending)
        if len(pending) == 1:
            t = pending[0]
            notif = (
                f"🎉 *ماموریت تکمیل شد!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 {t['name']}\n"
                f"🎁 پاداش: +{to_persian_int(t['xp'])} XP"
            )
        else:
            notif = (
                f"🎉 *{to_persian_digits(len(pending))} ماموریت تکمیل شد!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            for t in pending[:10]:
                notif += f"✅ {t['name']} (+{to_persian_int(t['xp'])} XP)\n"
            if len(pending) > 10:
                notif += f"• و {to_persian_digits(len(pending) - 10)} ماموریت دیگر...\n"
            notif += f"\n💎 مجموع پاداش: +{to_persian_int(total_xp)} XP"
        try:
            bot.send_message(chat_id, notif)
        except Exception as e:
            logger.error(f"Task notification send error: {e}")

    # نکته: answer_callback_query قبلاً در callback_handler زده شده (loading toast)
    # پس اینجا دیگه نمی‌زنیم


def show_task_detail_popup(call, user_id, task_id):
    """نمایش جزئیات یک تسک به‌صورت popup (answer_callback_query) — برای جلوگیری از شلوغ شدن چت."""
    task = tasks_module.get_task_by_id(task_id)
    if not task:
        bot.answer_callback_query(call.id, "❌ تسک یافت نشد.", show_alert=True)
        return

    is_done = db.has_bonus(user_id, f"task_{task['id']}")
    if not is_done:
        # بررسی مجدد آیا الان انجام شده
        try:
            with db._lock:
                is_done = bool(task["check"](db, user_id))
            if is_done:
                # تسک الان تکمیل شد — XP رو بده
                level_before = db.get_user_level_cached(user_id)
                awarded, xp_new, level_new, _ = db.award_bonus_xp(user_id, f"task_{task['id']}", task["xp"])
                if awarded:
                    # اگر سطح بالا رفت، پیام ارتقا بفرست
                    if level_new > level_before:
                        try:
                            title, emoji = get_rank_tier(level_new)
                            xp_next = db.xp_for_next_level(level_new)
                            msg = texts.LEVEL_UP_MESSAGE.format(
                                level=to_persian_digits(level_new),
                                title=title,
                                emoji=emoji,
                                xp_current=to_persian_int(xp_new),
                                xp_next=to_persian_int(xp_next) if xp_next else "نهایتی"
                            )
                            try:
                                if LEVEL_UP_PHOTO_ID:
                                    try:
                                        bot.send_photo(user_id, LEVEL_UP_PHOTO_ID, caption=msg)
                                    except:
                                        bot.send_message(user_id, msg)
                                else:
                                    bot.send_message(user_id, msg)
                            except Exception as e:
                                logger.error(f"Level-up notify error: {e}")
                        except Exception as e:
                            logger.error(f"Level-up msg build error: {e}")

                    # toast به کاربر
                    bot.answer_callback_query(call.id,
                        f"🎉 ماموریت تکمیل شد!\n{task['name']}\n+{to_persian_digits(task['xp'])} XP",
                        show_alert=True)
                    return
        except Exception as e:
            logger.error(f"Task detail check error: {e}")

    status = "✅ انجام شده" if is_done else "⬜ در انتظار انجام"
    popup_text = texts.TASKS_DETAIL_POPUP.format(
        name=task["name"],
        xp=to_persian_digits(task["xp"]),
        desc=task["desc"],
        status=status
    )

    # اضافه‌کردن پیشنهاد ماموریت بعدی (در همون group)
    if is_done and task.get("group"):
        group = task["group"]
        # پیدا کردن ماموریت بعدی در همون group (با threshold بالاتر)
        group_tasks = sorted(
            [t for t in tasks_module.TASKS if t.get("group") == group],
            key=lambda x: x.get("threshold", 0)
        )
        # پیدا کردن اولین ماموریت انجام‌نشده بعد از این
        current_threshold = task.get("threshold", 0)
        next_task = None
        for t in group_tasks:
            if t.get("threshold", 0) > current_threshold:
                is_next_done = db.has_bonus(user_id, f"task_{t['id']}")
                if not is_next_done:
                    next_task = t
                    break
        if next_task:
            popup_text += texts.NEXT_TASK_HINT.format(
                name=next_task["name"],
                xp=to_persian_digits(next_task["xp"])
            )

    bot.answer_callback_query(call.id, popup_text, show_alert=True)


def show_leaderboard(chat_id, user_id):
    top = db.get_leaderboard_top(5)
    user_distinct = db.get_distinct_snoop_count(user_id)
    user_rank = db.get_user_rank_by_distinct(user_id)
    total_sharers = db.count_all_users()

    lines = [texts.LEADERBOARD_HEADER]

    # ۵ نفر برتر — فرمت جدید:
    # 🥇 🌿 با ۸۲ فضول یکتا:
    #          𓆩♡𓆪 strawberry 𓆩♡𓆪
    for i, row in enumerate(top):
        rank = i + 1
        # ایموجی سطح کاربر
        level_emoji = get_user_rank_emoji(row['owner_id'])
        # مدال رتبه
        medal = rank_emoji_display(rank)
        name = sanitize_name(row['first_name'] or "بی‌نام")
        if row['owner_id'] == user_id:
            name = f"⭐ {name}"
        name_escaped = name
        cnt = row['cnt']

        lines.append(
            f"{medal} {level_emoji} با {to_persian_digits(cnt)} فضول یکتا:"
        )
        lines.append(f"    𓆩♡𓆪 {name_escaped} 𓆩♡𓆪")

    user_hidden = db.is_hide_leaderboard(user_id)
    rank_text = texts.LEADERBOARD_MY_RANK.format(rank=to_persian_digits(user_rank), total=to_persian_digits(total_sharers))
    if user_hidden:
        rank_text += " (مخفی)"
    # فاصله قبل از بخش رتبه
    lines.append("")
    lines.append(rank_text)

    if not user_hidden and any(row['owner_id'] == user_id for row in top):
        for idx, row in enumerate(top):
            if row['owner_id'] == user_id:
                user_idx = idx
                break
        if user_idx == 0:
            lines.append("")
            lines.append(texts.LEADERBOARD_TOP1)
        else:
            gap = top[user_idx-1]['cnt'] - user_distinct
            lines.append("")
            lines.append(texts.LEADERBOARD_GAP_NEXT.format(gap=to_persian_digits(gap)))
    else:
        if top:
            last_cnt = top[-1]['cnt']
            gap = last_cnt - user_distinct
            if gap > 0:
                lines.append("")
                lines.append(texts.LEADERBOARD_GAP_TOP10.format(gap=to_persian_digits(gap)))
            else:
                lines.append("")
                lines.append("📊 تو به تالار راه یافته‌ای اما نامت مخفی است.")
        else:
            lines.append("")
            lines.append("📁 هنوز هیچ کارآگاهی در تالار نیست...")

    # فاصله قبل از motto
    lines.append("")
    lines.append(texts.LEADERBOARD_MOTTO)
    caption = "\n".join(lines)

    markup = types.InlineKeyboardMarkup(row_width=2)
    toggle_text = "👁️ مخفی کردن نام" if not user_hidden else "👁️ نمایش نام"
    markup.add(types.InlineKeyboardButton(toggle_text, callback_data="toggle_leaderboard_hide"))
    markup.add(
        types.InlineKeyboardButton("🔍 دریافت تله", callback_data="my_link_show"),
        types.InlineKeyboardButton("🏅 VIP", callback_data="vip_info"),
        types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu")
    )

    # ارسال با عکس ثابت لیدربورد
    if LEADERBOARD_PHOTO_ID:
        try:
            bot.send_photo(chat_id, LEADERBOARD_PHOTO_ID, caption=caption, reply_markup=markup)
        except:
            bot.send_message(chat_id, caption, reply_markup=markup)
    else:
        bot.send_message(chat_id, caption, reply_markup=markup)
def handle_original_callback(callback_data, chat_id, user_id, message_id=None):
    """اجرای کالبک اصلی بعد از تأیید عضویت، بدون answer_callback_query اضافه."""
    if callback_data == "main_menu":
        show_main_menu(chat_id, user_id, message_id)
    elif callback_data.startswith("snooplist_page_"):
        page = int(callback_data.split("_")[-1])
        show_snoop_list(chat_id, page, message_id)
    elif callback_data == "my_link_show":
        link = user_link(user_id)
        samples = [
            f"[جرات داری روم کلیک کن 👁️]({link})",
            f"[میخوای آشنا شیم؟ 🤭]({link})",
        ]
        text = (
            f"🔍 *تلهٔ اختصاصی تو:*\n{link}\n\n"
            f"🎭 این لینک خام رو که نمی‌تونی توی بیو بذاری...\n"
            f"باید پشت یه متن قایمش کنی — این میشه *هایپرلینک*.\n"
            f"یه جملهٔ جذاب که هرکی روش بزنه، مستقیم می‌افته توی دامت.\n\n"
            f"📋 چند نمونهٔ آماده با کد خودت:\n"
            f"1. {samples[0]}\n"
            f"2. {samples[1]}\n\n"
            f"💡 هرکدوم رو دوست داشتی *کپی* کن و بچسبون توی بیوگرافیت.\n"
            f"یا خودت یه متن دلخواه بساز..."
        )
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("📋 کپی 1", callback_data="copy_sample_1",
                                          copy_text=types.CopyTextButton(samples[0]))
        btn2 = types.InlineKeyboardButton("📋 کپی 2", callback_data="copy_sample_2",
                                          copy_text=types.CopyTextButton(samples[1]))
        markup.add(btn1, btn2)
        markup.add(types.InlineKeyboardButton("✍️ ساخت هایپرلینک با متن دلخواه", callback_data="get_hyperlink"))
        markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        send_or_edit_message(chat_id, text, markup, message_id)
    elif callback_data == "help":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📝 متن خوش‌آمد", callback_data="help_welcome"),
                   types.InlineKeyboardButton("🖼️ عکس خوش‌آمد", callback_data="help_welcome_photo"),
                   types.InlineKeyboardButton("🎭 نقاب کارآگاهی", callback_data="help_mask"),
                   types.InlineKeyboardButton("🎁 کد هدیه", callback_data="help_gift"),
                   types.InlineKeyboardButton("ℹ️ اطلاعات من", callback_data="help_myinfo"),
                   types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        send_or_edit_message(chat_id, texts.HELP_MENU_PROMPT, markup, message_id)
    elif callback_data == "vip_info":
        is_active, status_str = vip_status_display(user_id)
        text = vip_info_text() + f"\n\n📌 *وضعیت اشتراک شما:* {status_str}"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("🛒 خرید VIP", callback_data="buy_vip_menu"),
                   types.InlineKeyboardButton("✨ قابلیت‌های VIP", callback_data="vip_features"))
        markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        send_or_edit_message(chat_id, text, markup, message_id)
    elif callback_data == "my_info":
        u = bot.get_chat(user_id)
        total_clicks = db.get_clicks_count(user_id)
        snoop_count = db.get_distinct_snoop_count(user_id)
        today_clicks = db.get_today_clicks_count(user_id)
        invite_count = db.get_user_invite_count(user_id)
        is_active_vip, vip_status_str = vip_status_display(user_id)
        emoji = get_user_rank_emoji(user_id)
        level = db.get_user_level_cached(user_id)
        xp = db.get_user_xp(user_id)
        title, _ = get_rank_tier(level)
        xp_next = db.xp_for_next_level(level)
        display_name = f"{emoji} {escape_md(u.first_name or 'بی‌نام')}" if emoji else escape_md(u.first_name or 'بی‌نام')

        # محاسبه progress bar برای سطح
        # نکته مهم: سطح ۱ از XP=0 شروع می‌شود (نه از xp_for_level(1)=100)
        # سطح L (L≥2) از xp_for_level(L) شروع می‌شود
        if level < 50 and xp_next:
            if level == 1:
                xp_this_level_start = 0
            else:
                xp_this_level_start = db.xp_for_level(level)
            xp_in_level = xp - xp_this_level_start
            xp_needed_this_level = xp_next - xp_this_level_start
            progress_pct = int(xp_in_level * 100 / xp_needed_this_level) if xp_needed_this_level > 0 else 0
            progress_pct = max(0, min(100, progress_pct))
            bar_len = 10
            filled = int(progress_pct * bar_len / 100)
            level_bar = '█' * filled + '░' * (bar_len - filled)
            xp_to_next = xp_next - xp
            level_section = (
                f"📊 سطح: {to_persian_digits(level)} — {emoji} {title}\n"
                f"✨ {to_persian_int(xp)} از {to_persian_int(xp_next)} دریافت شده\n"
                f"{level_bar} {to_persian_digits(progress_pct)}٪\n"
                f"🎯 تا سطح بعد: {to_persian_int(xp_to_next)} XP"
            )
        else:
            level_section = (
                f"📊 سطح: {to_persian_digits(level)} — {emoji} {title}\n"
                f"✨ XP: {to_persian_int(xp)}\n"
                f"🏆 به حداکثر سطح رسیده‌اید!"
            )

        text = (
            f"📋 *اطلاعات من*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 {display_name}\n"
            f"🆔 {to_persian_digits(user_id)}\n"
            f"📎 @{u.username or 'ندارد'}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 *آمار*\n"
            f"🔍 شکارهای یکتا: {to_persian_int(snoop_count)}\n"
            f"👥 کل کلیک‌ها: {to_persian_int(total_clicks)}\n"
            f"📅 کلیک‌های امروز: {to_persian_int(today_clicks)}\n"
            f"👤 دعوت‌های موفق: {to_persian_int(invite_count)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *پیشرفت*\n"
            f"{level_section}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏅 *اشتراک*\n"
            f"وضعیت VIP: {vip_status_str}\n\n"
            f"🔗 *تلهٔ شما*\n"
            f"{user_link(user_id)}\n"
        )

        # بخش آخرین فعالیت‌ها
        activities = db.get_recent_activities(user_id, limit=4)
        if activities:
            text += f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
            text += f"🕐 *آخرین فعالیت‌ها*\n"
            for act in activities:
                # فرمت کردن زمان (شمسی)
                try:
                    ts = act.get('timestamp', '')
                    if ts:
                        # تبدیل به تاریخ شمسی
                        try:
                            g_date = datetime.datetime.strptime(ts[:10], "%Y-%m-%d").date()
                            j_date = jdatetime.date.fromgregorian(date=g_date)
                            time_str = to_persian_digits(j_date.strftime("%Y/%m/%d"))
                        except:
                            time_str = to_persian_digits(ts[:10])
                    else:
                        time_str = 'نامشخص'
                except:
                    time_str = 'نامشخص'

                if act['type'] == 'click':
                    name = escape_md(act.get('name', 'ناشناس'))
                    text += f"• {time_str}: {name} تله‌ات رو کلیک کرد\n"
                elif act['type'] == 'vip':
                    days = to_persian_digits(act.get('days', 0))
                    text += f"• {time_str}: VIP خریدی ({days} روز)\n"
                elif act['type'] == 'gift':
                    days = to_persian_digits(act.get('days', 0))
                    text += f"• {time_str}: VIP هدیه دادی ({days} روز)\n"
                elif act['type'] == 'task':
                    task_name = escape_md(act.get('task_name', 'ماموریت'))
                    text += f"• {time_str}: ماموریت «{task_name}» رو تکمیل کردی\n"

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🎯 ماموریت‌ها", callback_data="tasks_page_1"),
                   types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
        send_or_edit_message(chat_id, text, markup, message_id)
    elif callback_data == "leaderboard":
        show_leaderboard(chat_id, user_id)   # تابع show_leaderboard خودش پیام جدید می‌سازد
    # می‌توانید کالبک‌های دیگر را هم در اینجا اضافه کنید...
    else:
        # اگر کالبک ناشناخته بود، منوی اصلی را نشان بده
        show_main_menu(chat_id, user_id, message_id)

def show_main_menu(chat_id, user_id, message_id=None):
    """نمایش منوی اصلی بدون answer_callback_query اضافی."""
    text = build_dynamic_home_text(user_id)
    markup = main_menu(user_id)
    send_or_edit_message(chat_id, text, markup, message_id)

def send_or_edit_message(chat_id, text, markup, message_id):
    """در صورت وجود message_id ویرایش می‌کند، در غیر این صورت پیام جدید می‌فرستد."""
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        except Exception:
            bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)
# ====== کیبورد شیشه‌ای (یکپارچه) ======
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global broadcast_mode, broadcast_admin_chat, broadcast_preview_msg, broadcast_started_at
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data
    record_message(call.from_user.id)
    # ثبت آمار کلیک روی دکمه‌ها
    try:
        db.log_callback_click(data)
    except: pass
    while True:
        try:
            if db.is_blocked(user_id):
                bot.answer_callback_query(call.id, "⛔ حساب شما مسدود شده است.", show_alert=True)
                return

            db.sync_user_profile(user_id, call.from_user.first_name, call.from_user.username)

            force_check_exceptions = ["main_menu", "cancel_state"]
            is_admin = data.startswith("admin_") or data in [
                "admin_panel", "admin_search_user", "admin_vip_stats",
                "admin_most_active", "admin_gift_list", "admin_new_gift",
                "admin_vip", "admin_addvip", "admin_daily", "admin_broadcast",
                "admin_support_list", "admin_forced_ads"
            ]
            is_checkjoin = data.startswith("checkjoin_")

            # ----- بررسی اولیهٔ عضویت برای تمام callbackهای غیرمجاز -----
            if not (is_admin or is_checkjoin or any(data.startswith(ex) for ex in force_check_exceptions)):
                if not is_subscribed(user_id):
                    markup = build_channel_keyboard(data, user_id)
                    if markup:
                        bot.answer_callback_query(call.id, "⚡️ برای استفاده از قدرت‌های تاریک، ابتدا در کانال‌های زیر عضو شوید.")
                        if call.message.content_type == 'photo':
                            try:
                                bot.delete_message(chat_id, call.message.message_id)
                            except:
                                pass
                            bot.send_message(chat_id, texts.FORCE_JOIN_PROMPT, reply_markup=markup)
                        else:
                            try:
                                bot.edit_message_text(texts.FORCE_JOIN_PROMPT, chat_id, call.message.message_id, reply_markup=markup)
                            except:
                                bot.send_message(chat_id, texts.FORCE_JOIN_PROMPT, reply_markup=markup)
                    else:
                        bot.answer_callback_query(call.id, "⏳ در حال حاضر امکان بررسی عضویت وجود ندارد. لطفاً لحظاتی دیگر تلاش کنید.", show_alert=True)
                    return

            # ----- مدیریت checkjoin (جلوگیری از Recursion) -----
            if is_checkjoin:
                original_callback = data[len("checkjoin_"):]
                # پاک کردن کش عضویت قبل از چک مجدد
                clear_subscription_cache(user_id)
                if is_subscribed(user_id):
                    bot.answer_callback_query(call.id, "✅ عضویت تأیید شد.", show_alert=True)
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass

                    # --- مستقیماً کالبک اصلی را اجرا کن ---
                    if original_callback == "show_pending_snoop":
                        info = db.get_pending_snoop(user_id)
                        if info:
                            msg = (f"🔔 *یه فضول روی لینک شما کلیک کرد!*\n"
                                f"🕒 {info['t']}\n👤 {escape_md(info['display_name'])}\n"
                                f"🆔 {fmt_id(info['clicker_id'], info['vip_owner'])}\n"
                                f"📎 {fmt_uname(info['clicker_username'], info['vip_owner'])}")
                            if info['repeat'] > 3:
                                msg += "\n🔥 *فضول حرفه‌ای شناسایی شد!*"
                            if info['gift_vip_given']:
                                msg += "\n\n🎁 *هدیه:* ۱ روز VIP به خاطر شکار یک کاربر جدید!"
                            markup = types.InlineKeyboardMarkup(row_width=2)
                            markup.add(
                                types.InlineKeyboardButton("🏷️ لقب دادن", callback_data=f"nick_{info['clicker_id']}"),
                                types.InlineKeyboardButton("✉️ پیام ناشناس", callback_data=f"anon_{info['clicker_id']}"),
                                types.InlineKeyboardButton("📊 اطلاعات فضول", callback_data=f"snoopdetail_{info['clicker_id']}"),
                                types.InlineKeyboardButton("🎁 هدیه به فضول", callback_data=f"giftvip_{info['clicker_id']}"),
                                types.InlineKeyboardButton("📋 لیست فضول‌ها", callback_data="snooplist_page_1"),
                                types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu")
                            )
                            if info['repeat'] > 3:
                                markup.add(types.InlineKeyboardButton("🔕 بی‌صدا", callback_data=f"mute_{info['clicker_id']}"))
                            if info['photo_file_id']:
                                try:
                                    bot.send_photo(user_id, info['photo_file_id'], caption=msg, reply_markup=markup)
                                except:
                                    bot.send_message(user_id, msg, reply_markup=markup)
                            else:
                                bot.send_message(user_id, msg, reply_markup=markup)
                        else:
                            bot.send_message(user_id, "⏳ اطلاعات فضول منقضی شده یا در دسترس نیست.")
                        return

                    # برای بقیهٔ کالبک‌ها: data رو به original_callback تغییر بده و continue بزن
                    # تا callback_handler خودش همه چیز رو هندل کنه
                    data = original_callback
                    continue

                else:
                    # هنوز عضو نیست
                    markup = build_channel_keyboard(original_callback, user_id)
                    if markup:
                        bot.answer_callback_query(call.id, "⏳ هنوز در کانال‌های زیر عضو نیستی.", show_alert=True)
                        try:
                            bot.edit_message_text(texts.FORCE_JOIN_PROMPT, chat_id, call.message.message_id, reply_markup=markup)
                        except:
                            pass
                    return

            # ============================================================
            # از اینجا به بعد، تمام بخش‌های اصلی callback_handler قرار دارند
            # هر جا قبلاً return callback_handler(call) داشتیم،
            # به data = new_callback; continue تغییر یافته است.
            # ============================================================

            # ----- show_pending_snoop (مستقیم، بدون عضویت) -----
            if data == "show_pending_snoop":
                if is_subscribed(user_id):
                    info = db.get_pending_snoop(user_id)
                    if info:
                        msg = (f"🔔 *یه فضول روی لینک شما کلیک کرد!*\n"
                               f"🕒 {info['t']}\n👤 {escape_md(info['display_name'])}\n"
                               f"🆔 {fmt_id(info['clicker_id'], info['vip_owner'])}\n📎 {fmt_uname(info['clicker_username'], info['vip_owner'])}")
                        if info['repeat'] > 3:
                            msg += "\n🔥 *فضول حرفه‌ای شناسایی شد!*"
                        if info['gift_vip_given']:
                            msg += "\n\n🎁 *هدیه:* ۱ روز VIP به خاطر شکار یک کاربر جدید!"
                        markup = types.InlineKeyboardMarkup(row_width=2)
                        markup.add(
                            types.InlineKeyboardButton("🏷️ لقب دادن", callback_data=f"nick_{info['clicker_id']}"),
                            types.InlineKeyboardButton("✉️ پیام ناشناس", callback_data=f"anon_{info['clicker_id']}"),
                            types.InlineKeyboardButton("📊 اطلاعات فضول", callback_data=f"snoopdetail_{info['clicker_id']}"),
                            types.InlineKeyboardButton("🎁 هدیه به فضول", callback_data=f"giftvip_{info['clicker_id']}"),
                            types.InlineKeyboardButton("📋 لیست فضول‌ها", callback_data="snooplist_page_1"),
                            types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu")
                        )
                        if info['repeat'] > 3:
                            markup.add(types.InlineKeyboardButton("🔕 بی‌صدا", callback_data=f"mute_{info['clicker_id']}"))
                        if info['photo_file_id']:
                            try:
                                bot.send_photo(user_id, info['photo_file_id'], caption=msg, reply_markup=markup)
                            except:
                                bot.send_message(user_id, msg, reply_markup=markup)
                        else:
                            bot.send_message(user_id, msg, reply_markup=markup)
                        bot.answer_callback_query(call.id, "✅ اطلاعات فضول نمایش داده شد.")
                    else:
                        bot.answer_callback_query(call.id, "اطلاعات قبلاً نمایش داده شده یا وجود ندارد.")
                else:
                    markup = build_channel_keyboard("show_pending_snoop", user_id)
                    if markup:
                        bot.answer_callback_query(call.id, texts.FORCE_JOIN_STILL_NOT)
                        try:
                            bot.edit_message_text(texts.SNOOP_CAUGHT_UNSUBSCRIBED, chat_id, call.message.message_id, reply_markup=markup)
                        except:
                            bot.send_message(chat_id, texts.SNOOP_CAUGHT_UNSUBSCRIBED, reply_markup=markup)
                return

            # ----- مشاهیر تاریکی -----
            if data == "leaderboard":
                clear_user_state(chat_id)
                bot.answer_callback_query(call.id)
                show_leaderboard(chat_id, user_id)
                return

            if data == "toggle_leaderboard_hide":
                current_hide = db.is_hide_leaderboard(user_id)
                db.set_hide_leaderboard(user_id, not current_hide)
                bot.answer_callback_query(call.id, "وضعیت نمایش تغییر کرد.")
                show_leaderboard(chat_id, user_id)
                return

            # ----- mute / unmute (toggle پویا) -----
            if data.startswith("mute_"):
                target_id = int(data.split("_")[1])
                db.mute_snoop(user_id, target_id)
                # آپدیت دکمه: تبدیل به «با صدا»
                try:
                    # ساخت کیبورد جدید با دکمه «با صدا»
                    new_markup = types.InlineKeyboardMarkup(row_width=2)
                    new_markup.add(
                        types.InlineKeyboardButton("✉️ پیام ناشناس", callback_data=f"anon_{target_id}"),
                        types.InlineKeyboardButton("🏷️ لقب", callback_data=f"nick_{target_id}"),
                        types.InlineKeyboardButton("🎁 هدیه VIP", callback_data=f"giftvip_{target_id}"),
                        types.InlineKeyboardButton("🔙 لیست", callback_data="snooplist_page_1"))
                    new_markup.add(types.InlineKeyboardButton("🔔 با صدا", callback_data=f"unmute_{target_id}"))
                    new_markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=new_markup)
                except: pass
                bot.answer_callback_query(call.id, "🔕 این فضول بی‌صدا شد.")
                return
            if data.startswith("unmute_"):
                target_id = int(data.split("_")[1])
                db.unmute_snoop(user_id, target_id)
                # آپدیت دکمه: تبدیل به «بی‌صدا»
                try:
                    new_markup = types.InlineKeyboardMarkup(row_width=2)
                    new_markup.add(
                        types.InlineKeyboardButton("✉️ پیام ناشناس", callback_data=f"anon_{target_id}"),
                        types.InlineKeyboardButton("🏷️ لقب", callback_data=f"nick_{target_id}"),
                        types.InlineKeyboardButton("🎁 هدیه VIP", callback_data=f"giftvip_{target_id}"),
                        types.InlineKeyboardButton("🔙 لیست", callback_data="snooplist_page_1"))
                    new_markup.add(types.InlineKeyboardButton("🔕 بی‌صدا", callback_data=f"mute_{target_id}"))
                    new_markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=new_markup)
                except: pass
                bot.answer_callback_query(call.id, "🔔 این فضول با صدا شد.")
                return

            # ----- پشتیبانی -----
            if data == "support_exit":
                remove_support_session(chat_id)
                pop_support_partner(chat_id)
                clear_user_state(chat_id)
                bot.answer_callback_query(call.id, "از پشتیبانی خارج شدید.")
                show_main_menu_for_callback(call, chat_id, user_id)
                return

            # ----- کد هدیه -----
            if data == "gift_code":
                clear_user_state(chat_id)
                # دریافت کدهای هدیه فعال برای این کاربر
                # کد valid = ظرفیت پر نشده + حذف نشده + کاربر قبلاً استفاده نکرده
                all_codes = db.get_all_gift_codes()
                valid_codes = []
                for c in all_codes:
                    # اگر ظرفیت پر شده، رد کن
                    if c['used_count'] >= c['max_uses']:
                        continue
                    # اگر کاربر قبلاً استفاده کرده، رد کن
                    already_used = db.conn.execute(
                        "SELECT 1 FROM gift_usage WHERE code=? AND user_id=?",
                        (c['code'], user_id)
                    ).fetchone()
                    if already_used:
                        continue
                    valid_codes.append(c)

                if not valid_codes:
                    bot.answer_callback_query(call.id)
                    bot.send_message(chat_id,
                        "🎁 *کد هدیه*\n\n"
                        "در حال حاضر کد هدیهٔ فعالی برای شما موجود نیست.\n"
                        "اگر کد هدیه‌ای دارید، می‌توانید آن را مستقیماً ارسال کنید.",
                        reply_markup=home_markup())
                    return

                # نمایش کدهای فعال به‌صورت دکمه شیشه‌ای
                lines = ["🎁 *کدهای هدیهٔ فعال*\n"]
                for c in valid_codes:
                    days = c['days']
                    remaining = c['max_uses'] - c['used_count']
                    lines.append(f"• {to_persian_digits(days)} روز VIP — ظرفیت باقی‌مانده: {to_persian_digits(remaining)}")
                lines.append("\n💡 برای فعال‌سازی، روی یکی از دکمه‌های زیر بزنید:")

                markup = types.InlineKeyboardMarkup(row_width=1)
                for c in valid_codes:
                    days = c['days']
                    remaining = c['max_uses'] - c['used_count']
                    btn = types.InlineKeyboardButton(
                        f"🎁 {to_persian_digits(days)} روز VIP (ظرفیت: {to_persian_digits(remaining)})",
                        callback_data=f"redeem_gift_{c['code']}"
                    )
                    markup.add(btn)
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))

                bot.answer_callback_query(call.id)
                # ارسال به‌صورت پیام جدید (حذف پیام قبلی)
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                bot.send_message(chat_id, "\n".join(lines), reply_markup=markup)
                return

            # فعال‌سازی کد هدیه با دکمه شیشه‌ای
            if data.startswith("redeem_gift_"):
                code = data[len("redeem_gift_"):]
                # بررسی مجدد اعتبار کد
                row = db.conn.execute("SELECT * FROM gift_codes WHERE code=?", (code,)).fetchone()
                if not row:
                    bot.answer_callback_query(call.id, "❌ این کد دیگر موجود نیست.", show_alert=True)
                    return
                if row['used_count'] >= row['max_uses']:
                    bot.answer_callback_query(call.id, "❌ ظرفیت این کد به پایان رسیده.", show_alert=True)
                    return
                already = db.conn.execute(
                    "SELECT 1 FROM gift_usage WHERE code=? AND user_id=?",
                    (code, user_id)
                ).fetchone()
                if already:
                    bot.answer_callback_query(call.id, "❌ شما قبلاً این کد را استفاده کرده‌اید.", show_alert=True)
                    return
                # فعال‌سازی کد
                result, gift_data = db.redeem_gift(code, user_id)
                if result:
                    bot.answer_callback_query(call.id,
                        f"🎉 کد با موفقیت فعال شد!\n{to_persian_digits(gift_data)} روز VIP به حساب شما اضافه شد.",
                        show_alert=True)
                    # به‌روزرسانی پیام
                    try:
                        bot.edit_message_text(
                            f"✅ کد {code} با موفقیت فعال شد!\n{to_persian_digits(gift_data)} روز VIP به حساب شما اضافه شد.",
                            chat_id, call.message.message_id,
                            reply_markup=home_markup()
                        )
                    except: pass
                else:
                    bot.answer_callback_query(call.id, f"❌ {gift_data}", show_alert=True)
                return

            # ----- پاسخ ناشناس -----
            if data.startswith("anon_reply_"):
                target_id = int(data.split("_")[-1])
                if db.is_anon_blocked(target_id, user_id):
                    bot.answer_callback_query(call.id, "⛔ بلاک شده‌اید.", show_alert=True)
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('anon_reply', target_id))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, texts.ANON_REPLY_PROMPT, reply_markup=cancel_markup())
                return

            # ----- پشتیبانی پاسخ -----
            if data.startswith("support_reply_"):
                target_id = int(data.split("_")[-1])
                if user_id == ADMIN_ID:
                    remove_support_session(ADMIN_ID)
                    set_admin_reply(user_id, target_id)
                    bot.answer_callback_query(call.id)
                    bot.send_message(chat_id, "✍️ پاسخ:", reply_markup=cancel_markup())
                else:
                    add_support_session(user_id)
                    set_support_partner(user_id, ADMIN_ID)
                    bot.answer_callback_query(call.id)
                    bot.send_message(chat_id, "✉️ پیام:", reply_markup=cancel_markup())
                return

            # ----- بلاک / آنبلاک ناشناس -----
            if data.startswith("block_"):
                target_id = int(data.split("_")[1])
                db.block_anon(user_id, target_id)
                new_markup = types.InlineKeyboardMarkup()
                new_markup.add(types.InlineKeyboardButton("🔄 پاسخ ناشناس", callback_data=f"anon_reply_{user_id}"),
                               types.InlineKeyboardButton("✅ آنبلاک", callback_data=f"unblock_{target_id}"))
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=new_markup)
                except:
                    pass
                bot.answer_callback_query(call.id, "🚫 کاربر بلاک شد.")
                bot.send_message(ADMIN_ID, f"🚫 کاربر {user_id} کاربر {target_id} را بلاک کرد.")
                return
            if data.startswith("unblock_"):
                target_id = int(data.split("_")[1])
                db.unblock_anon(user_id, target_id)
                new_markup = types.InlineKeyboardMarkup()
                new_markup.add(types.InlineKeyboardButton("🔄 پاسخ ناشناس", callback_data=f"anon_reply_{user_id}"),
                               types.InlineKeyboardButton("🚫 بلاک", callback_data=f"block_{target_id}"))
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=new_markup)
                except:
                    pass
                bot.answer_callback_query(call.id, "✅ کاربر آزاد شد.")
                bot.send_message(ADMIN_ID, f"✅ کاربر {user_id} کاربر {target_id} را آنبلاک کرد.")
                return

            # ----- گزارش تخلف -----
            if data.startswith("report_") and not data.startswith("reportreason_"):
                target_id = int(data.split("_")[1])
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    types.InlineKeyboardButton("😖 مزاحمت", callback_data=f"reportreason_{target_id}_1"),
                    types.InlineKeyboardButton("🤬 توهین", callback_data=f"reportreason_{target_id}_2"),
                    types.InlineKeyboardButton("🚯 اسپم", callback_data=f"reportreason_{target_id}_3"),
                    types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_state"),
                )
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "⚠️ دلیل گزارش را انتخاب کنید:", reply_markup=markup)
                return

            if data.startswith("reportreason_"):
                parts = data.split("_")
                target_id = int(parts[1])
                reason_code = parts[2]
                reasons = {"1": "مزاحمت", "2": "توهین", "3": "اسپم"}
                reason = reasons.get(reason_code, "نامشخص")

                reporter = db.get_user_basic(user_id)
                reporter_name = reporter['first_name'] if reporter and reporter['first_name'] else "بی‌نام"
                reporter_username = reporter['username'] if reporter and reporter['username'] else "ندارد"

                culprit = db.get_user_basic(target_id)
                culprit_name = culprit['first_name'] if culprit and culprit['first_name'] else "بی‌نام"
                culprit_username = culprit['username'] if culprit and culprit['username'] else "ندارد"

                message_text = db.get_last_anon_log(target_id, user_id)
                if not message_text:
                    message_text = "متن پیام در دسترس نیست"

                admin_text = texts.ADMIN_REPORT_MESSAGE.format(
                    complainant_name=escape_md(reporter_name),
                    complainant_id=user_id,
                    complainant_username=reporter_username,
                    culprit_name=escape_md(culprit_name),
                    culprit_id=target_id,
                    culprit_username=culprit_username,
                    message_text=escape_md(message_text[:500]),
                    reason=reason
                )

                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("🚫 بلاک خاطی", callback_data=f"admin_block_{target_id}"),
                    types.InlineKeyboardButton("✉️ پیام به خاطی", callback_data=f"admin_msg_{target_id}"),
                    types.InlineKeyboardButton("✅ بررسی شد", callback_data=f"admin_review_{target_id}_{user_id}_{reason_code}"),
                    types.InlineKeyboardButton("❌ رد گزارش", callback_data=f"admin_rejectreport_{user_id}")
                )

                bot.send_message(ADMIN_ID, admin_text, reply_markup=markup)
                bot.answer_callback_query(call.id, "گزارش شما به تاریکی ارسال شد.")
                try:
                    bot.edit_message_text("📨 گزارش شما به مدیر ارسال شد. با متخلف برخورد خواهد شد.", chat_id, call.message.message_id, reply_markup=home_markup())
                except:
                    pass
                return

            # ----- پنل ادمین -----
            if data == "admin_panel":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                clear_user_state(chat_id)
                bot.edit_message_text(texts.ADMIN_PANEL, chat_id, call.message.message_id, reply_markup=admin_panel_markup())
                bot.answer_callback_query(call.id)
                return

            # ----- جستجوی کاربر -----
            if data == "admin_search_user":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('admin_search_user',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, texts.ADMIN_USER_SEARCH_PROMPT, reply_markup=cancel_markup())
                return

            # ----- لیست کاربران -----
            if data.startswith("admin_userlist_page_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                page = int(data.split("_")[-1])
                show_admin_userlist(chat_id, page, call.message.message_id)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("admin_resetwarns_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                target_id = int(data.split("_")[-1])
                db.reset_warnings(target_id)
                bot.answer_callback_query(call.id, f"اخطارهای کاربر {target_id} بازنشانی و در صورت نیاز مسدودیتش لغو شد.")
                info = db.get_user_detail(target_id)
                if info:
                    show_user_detail(chat_id, target_id, call.message.message_id, info)
                return

            if data.startswith("user_detail_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                target_id = int(data.split("_")[-1])
                info = db.get_user_detail(target_id)
                if not info:
                    bot.answer_callback_query(call.id, "کاربر یافت نشد.", show_alert=True)
                    return
                show_user_detail(chat_id, target_id, call.message.message_id, info)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("admin_action_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                parts = data.split("_")
                action = parts[2]
                target_id = int(parts[3])
                if action == "block":
                    db.block_user(target_id, by_admin=True)
                    bot.answer_callback_query(call.id, f"کاربر {target_id} مسدود شد.")
                elif action == "unblock":
                    db.unblock_user(target_id)
                    bot.answer_callback_query(call.id, f"کاربر {target_id} رفع مسدودیت شد.")
                elif action == "vip":
                    clear_user_state(chat_id)
                    set_user_state(chat_id, ('admin_quick_vip', target_id))
                    bot.answer_callback_query(call.id)
                    bot.send_message(chat_id, f"تعداد روز VIP برای کاربر {target_id}:", reply_markup=cancel_markup())
                    return
                elif action == "message":
                    set_admin_reply(user_id, target_id)
                    bot.answer_callback_query(call.id)
                    bot.send_message(chat_id, "✍️ پیام خود را بنویسید:", reply_markup=cancel_markup())
                    return
                return

            if data.startswith("admin_transactions_page_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                page = int(data.split("_")[-1])
                show_admin_transactions(chat_id, page, call.message.message_id)
                bot.answer_callback_query(call.id)
                return

            # ----- فعال‌ترین‌ها -----
            if data == "admin_most_active":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                top = db.get_most_active_owners_by_unique(10)
                lines = ["🔥 *فعال‌ترین شکارچیان (کاربران یکتای جذب‌شده)*"]
                for i, row in enumerate(top):
                    name = get_user_display(row['owner_id'], row['first_name'])
                    lines.append(f"{i+1}. {name} – {row['cnt']} فضول یکتا")
                markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "admin_vip_stats":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                active, expired = db.get_vip_stats()
                text = texts.ADMIN_VIP_STATS.format(active=active, expired=expired)
                markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙", callback_data="admin_panel"))
                bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("admin_anonlog_page_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                page = int(data.split("_")[-1])
                show_admin_anon_logs(chat_id, page, call.message.message_id)
                bot.answer_callback_query(call.id)
                return
            if data.startswith("anonlog_action_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                parts = data.split("_")
                action = parts[2]
                target_id = int(parts[3])
                if action == "msg":
                    set_admin_reply(user_id, target_id)
                    bot.answer_callback_query(call.id)
                    bot.send_message(chat_id, "✍️ پیام (از طرف پشتیبانی):", reply_markup=cancel_markup())
                elif action == "block":
                    db.block_user(target_id)
                    bot.answer_callback_query(call.id, f"کاربر {target_id} مسدود شد.")
                return

            if data.startswith("admin_review_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                parts = data.split("_")
                culprit_id = int(parts[2])
                reporter_id = int(parts[3])
                reason_code = parts[4]
                reasons = {"1": "مزاحمت", "2": "توهین", "3": "اسپم"}
                reason = reasons.get(reason_code, "نامشخص")

                current_warnings = db.increment_warning(culprit_id)

                if current_warnings >= 3:
                    db.block_user(culprit_id, by_admin=True)
                    try:
                        bot.send_message(culprit_id, texts.BAN_MESSAGE)
                    except ApiTelegramException as e:
                        if e.error_code == 403:
                            try: db.mark_user_blocked_bot(culprit_id)
                            except Exception: pass
                    except: pass
                else:
                    try:
                        bot.send_message(culprit_id, texts.WARNING_MESSAGE.format(current=current_warnings, reason=reason))
                    except ApiTelegramException as e:
                        if e.error_code == 403:
                            try: db.mark_user_blocked_bot(culprit_id)
                            except Exception: pass
                    except: pass

                try:
                    if REVIEW_PHOTO_ID:
                        bot.send_photo(reporter_id, REVIEW_PHOTO_ID, caption=texts.REVIEWED_FEEDBACK)
                    else:
                        bot.send_message(reporter_id, texts.REVIEWED_FEEDBACK)
                except ApiTelegramException as e:
                    if e.error_code == 403:
                        try: db.mark_user_blocked_bot(reporter_id)
                        except Exception: pass
                except: pass

                bot.answer_callback_query(call.id, "اخطار ثبت و اطلاع‌رسانی انجام شد.")
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
                except:
                    pass
                return

            if data.startswith("admin_rejectreport_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                reporter_id = int(data.split("_")[-1])
                # رفع باگ: mark blocked users
                try:
                    bot.send_message(reporter_id, texts.REJECTED_FEEDBACK)
                except ApiTelegramException as e:
                    if e.error_code == 403:
                        try: db.mark_user_blocked_bot(reporter_id)
                        except Exception: pass
                except: pass
                bot.answer_callback_query(call.id, "گزارش رد شد.")
                try:
                    bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
                except:
                    pass
                return

            # ----- کدهای هدیه -----
            if data == "admin_gift_list":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                codes = db.get_all_gift_codes()
                lines = ["🎁 *لیست کدهای هدیه*\n"]
                if not codes:
                    lines.append("هیچ کد هدیه‌ای ساخته نشده.")
                for c in codes:
                    lines.append(f"• {c['code']} | {to_persian_digits(c['days'])} روز | استفاده: {to_persian_digits(c['used_count'])}/{to_persian_digits(c['max_uses'])}")
                markup = types.InlineKeyboardMarkup(row_width=1)
                # دکمه حذف برای هر کد (در صورت وجود)
                for c in codes:
                    markup.add(types.InlineKeyboardButton(f"🗑️ حذف {c['code']}", callback_data=f"admin_delete_gift_{c['code']}"))
                markup.add(types.InlineKeyboardButton("➕ کد هدیه جدید", callback_data="admin_new_gift"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت به پنل ادمین", callback_data="admin_panel"))
                bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("admin_delete_gift_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                code = data[len("admin_delete_gift_"):]
                # تأیید حذف
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"admin_confirm_delete_gift_{code}"),
                    types.InlineKeyboardButton("❌ انصراف", callback_data="admin_gift_list")
                )
                bot.edit_message_text(
                    f"⚠️ *تأیید حذف کد هدیه*\n\n"
                    f"آیا از حذف کد {code} مطمئن هستی؟\n"
                    f"⚠️ این عمل قابل بازگشت نیست.",
                    chat_id, call.message.message_id, reply_markup=markup,
                    parse_mode="Markdown"
                )
                bot.answer_callback_query(call.id)
                return

            if data.startswith("admin_confirm_delete_gift_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                code = data[len("admin_confirm_delete_gift_"):]
                db.delete_gift_code(code)
                bot.answer_callback_query(call.id, f"✅ کد {code} حذف شد.")
                # برگشت به لیست کدها
                data = "admin_gift_list"
                continue

            if data == "admin_new_gift":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('new_gift_days',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "تعداد روز VIP کد هدیه را وارد کنید:", reply_markup=cancel_markup())
                return

            # ----- مدیریت VIP (صفحه‌بندی‌شده، فقط فعال‌ها) -----
            if data == "admin_vip" or data.startswith("admin_vip_page_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                # تشخیص صفحه
                if data == "admin_vip":
                    page = 1
                else:
                    try:
                        page = int(data.split("_")[-1])
                    except:
                        page = 1

                limit = 20
                offset = (page - 1) * limit
                vips = db.get_active_vips_paginated(offset, limit)
                total = db.count_active_vips()
                total_pages = max(1, (total + limit - 1) // limit)

                lines = [f"👑 *مدیریت VIP* (صفحهٔ {to_persian_digits(page)} از {to_persian_digits(total_pages)})"]
                lines.append(f"فعال: {to_persian_digits(total)} نفر\n")
                if not vips:
                    lines.append("هیچ VIP فعالی وجود ندارد.")
                else:
                    for v in vips:
                        name = v.get('first_name') or "بی‌نام"
                        # تبدیل تاریخ میلادی به شمسی
                        try:
                            g_date = datetime.datetime.strptime(v['expire_date'], "%Y-%m-%d").date()
                            j_date = jdatetime.date.fromgregorian(date=g_date)
                            date_display = to_persian_digits(j_date.strftime("%Y/%m/%d"))
                        except:
                            date_display = to_persian_digits(v['expire_date'])
                        lines.append(f"• {escape_md(name)} (id:{to_persian_digits(v['user_id'])}) — تا {date_display}")

                markup = types.InlineKeyboardMarkup(row_width=2)
                # دکمه‌های ناوبری
                nav = []
                if page > 1:
                    nav.append(types.InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_vip_page_{page-1}"))
                if page < total_pages:
                    nav.append(types.InlineKeyboardButton("بعدی ➡️", callback_data=f"admin_vip_page_{page+1}"))
                if nav:
                    markup.add(*nav)
                markup.add(types.InlineKeyboardButton("➕ افزودن VIP", callback_data="admin_addvip"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="admin_vip_submenu"))
                bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return
            if data == "admin_addvip":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('admin_addvip',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "فرمت: id days", reply_markup=cancel_markup())
                return

            # ----- مدیریت قیمت‌های VIP -----
            if data == "admin_vip_prices":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                lines = ["💵 *قیمت‌های فعلی VIP*\n"]
                m = types.InlineKeyboardMarkup(row_width=1)
                for days, amount in VIP_PRICES.items():
                    lines.append(f"• {to_persian_digits(days)} روز: {fmt_amount_rial(amount)} ({fmt_amount_toman(amount)})")
                m.add(types.InlineKeyboardButton("✏️ تغییر قیمت همه پلن‌ها", callback_data="admin_change_all_prices"))
                m.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="admin_vip_submenu"))
                bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=m)
                bot.answer_callback_query(call.id)
                return

            # شروع روند تغییر قیمت همه پلن‌ها — یکی‌یکی پرسیده می‌شود
            if data == "admin_change_all_prices":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                # مرتب‌سازی پلن‌ها از کم به زیاد
                sorted_plans = sorted(VIP_PRICES.keys())
                # شروع با اولین پلن
                clear_user_state(chat_id)
                set_user_state(chat_id, ('admin_change_prices_iter', sorted_plans, 0, {}))
                first_days = sorted_plans[0]
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id,
                    f"💵 *تغییر قیمت همه پلن‌ها*\n\n"
                    f"۱ از {to_persian_digits(len(sorted_plans))}:\n"
                    f"قیمت جدید برای *{to_persian_digits(first_days)} روزه* رو به ریال وارد کنید.\n"
                    f"📌 قیمت فعلی: {to_persian_int(VIP_PRICES.get(first_days, 0))} ریال\n\n"
                    f"💡 می‌تونی عدد رو به تومان هم وارد کنی (ربات خودش به ریال تبدیل می‌کنه).",
                    reply_markup=cancel_markup())
                return

            # ویرایش تکی قیمت (قدیمی — هنوز کار می‌کنه اگر کسی مستقیم بزنه)
            if data.startswith("admin_edit_price_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                days = int(data.split("_")[-1])
                clear_user_state(chat_id)
                set_user_state(chat_id, ('admin_edit_price', days))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id,
                    f"💵 قیمت جدید برای {to_persian_digits(days)} روزه رو به ریال وارد کنید.\n"
                    f"📌 قیمت فعلی: {to_persian_int(VIP_PRICES.get(days, 0))} ریال",
                    reply_markup=cancel_markup())
                return
            if data == "admin_daily":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                s = db.get_daily_stats()

                all_codes = db.get_all_gift_codes()
                active_codes_count = len([c for c in all_codes if c['used_count'] < c['max_uses']])
                broken_list = ', '.join(broken_channels) if broken_channels else 'ندارد'

                # محاسبهٔ کاربران جدید فعال‌شده امروز (کاربرانی که امروز کلیک داده‌اند و ایجادشده امروز هستند)
                # این برای نمایش "کاربران جدیدِ فعال‌شده امروز"
                # ساده‌سازی: تعداد کاربرانی که امروز created_at دارند و در clicks امروز حضور دارند
                # اما چون پیاده‌سازی کامل‌اش سنگین است، همان new_today استفاده می‌کنیم (تقریبی)

                # محاسبه ۳ تلهٔ برتر امروز
                today = datetime.date.today().isoformat()
                try:
                    top_today_rows = db.conn.execute(
                        "SELECT c.owner_id, u.first_name, COUNT(*) as c FROM clicks c "
                        "JOIN users u ON c.owner_id=u.user_id WHERE date(c.clicked_at)=? "
                        "GROUP BY c.owner_id ORDER BY c DESC LIMIT 3", (today,)).fetchall()
                except Exception:
                    top_today_rows = []
                medals = ['🥇', '🥈', '🥉']

                # ۳ تلهٔ برتر (بر اساس یکتایی)
                try:
                    top_distinct_rows = db.conn.execute(
                        "SELECT c.owner_id, u.first_name, COUNT(DISTINCT c.clicker_id) as c FROM clicks c "
                        "JOIN users u ON c.owner_id=u.user_id WHERE date(c.clicked_at)=? "
                        "GROUP BY c.owner_id ORDER BY c DESC LIMIT 3", (today,)).fetchall()
                except Exception:
                    top_distinct_rows = []

                # VIPهای در شرف انقضا
                expiring_vip_count = len(db.get_expiring_vips(days_left=1))

                # محاسبه آخرین پخش همگانی
                last_bc = db.conn.execute(
                    "SELECT value FROM settings WHERE key='last_broadcast_stats'").fetchone()
                last_bc_str = last_bc['value'] if last_bc else "ندارد"

                text = (
                    f"📊 داشبورد ربات فضول‌گیر\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👥 کاربران و رشد\n"
                    f"🔹 کل: {to_persian_int(s['total_users'])}\n"
                    f"🔸 جدید امروز: +{to_persian_digits(s['new_today'])} | دیروز: +{to_persian_digits(s['new_yesterday'])}\n"
                    f"🔹 فعال ۲۴ساعت: {to_persian_digits(s['active_today'])} | نرخ بازگشت: {to_persian_digits(s['return_rate'])}\n"
                    f"🆕 کاربران جدیدِ فعال‌شده امروز: {to_persian_digits(s['new_today'])} نفر\n\n"
                    f"📥 منابع ورود\n"
                    f"🟢 مستقیم: {to_persian_int(s['organic'])} | 🔵 خوش‌آمد: {to_persian_int(s['welcome'])} | 🟣 دعوت: {to_persian_int(s['referral'])}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🎯 شکار و تله‌ها\n"
                    f"🔹 کل کلیک: {to_persian_int(s['total_clicks'])}\n"
                    f"🔸 فضول یکتا: {to_persian_int(s['distinct_clickers'])} | صاحبان تله: {to_persian_int(s['trap_owners'])}\n"
                    f"📊 میانگین ۷ روز: {to_persian_digits(s['avg_7'])} کلیک/روز\n\n"
                    f"🏆 ۳ تلهٔ برتر امروز:\n"
                    + (
                        "\n".join(
                            f"{medals[i]} {sanitize_name(r['first_name'] or 'بی‌نام')} (id{to_persian_digits(r['owner_id'])}) — {to_persian_digits(r['c'])} کلیک"
                            for i, r in enumerate(top_today_rows)
                        ) if top_today_rows else "هنوز کلیکی امروز ثبت نشده"
                    )
                    + f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🏅 VIP و درآمد\n"
                    f"🔹 فعال: {to_persian_digits(s['active_vip'])}\n"
                    f"⏳ در شرف انقضا (امروز/فردا): {to_persian_digits(expiring_vip_count)}\n"
                    f"💰 امروز: {fmt_amount_rial(s['revenue_today'])} ({to_persian_digits(s['tx_today'])} تراکنش)\n"
                    f"💰 کل: {fmt_amount_rial(s['total_revenue'])} ({to_persian_digits(s['tx_total'])} تراکنش)\n\n"
                    f"🎁 کد هدیه\n"
                    f"🔹 ساخته: {to_persian_digits(s['gift_created'])} | استفاده: {to_persian_digits(s['gift_used'])} | فعال: {to_persian_digits(active_codes_count)}\n\n"
                    f"💬 پیام ناشناس\n"
                    f"🔸 کل: {to_persian_int(s['anon_total'])}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"⚙️ سیستم\n"
                    f"📢 کانال اجباری: {to_persian_digits(s['channels_count'])} عدد | عضویت: {to_persian_int(s['total_joins'])}\n"
                    f"⚠️ مشکل‌دار: {broken_list}\n"
                    f"🛡️ مسدود: {to_persian_digits(s['total_banned'])}\n\n"
                    f"⏱️ عملکرد\n"
                    f"🔹 آپ‌تایم: {uptime_str()}\n"
                    f"🔸 پیام‌های ۲۴h: {to_persian_digits(get_messages_24h())}\n"
                    f"📨 آخرین پخش همگانی: {last_bc_str}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔄 بروزرسانی: {shamsi_date(with_time=True)}"
                )

                markup = types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_daily"),
                    types.InlineKeyboardButton("📊 آرشیو روزانه", callback_data="admin_daily_archive"),
                    types.InlineKeyboardButton("🌙 گزارش روزانه", callback_data="admin_test_daily_report"),
                    types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")
                )
                bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            # دکمه تست گزارش روزانه (برای ادمین)
            if data == "admin_test_daily_report":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                try:
                    text = build_daily_report_text()
                    bot.send_message(chat_id, text)
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطا در ساخت گزارش: {e}")
                bot.answer_callback_query(call.id)
                return

            # ----- آرشیو روزانه — کاربران جدید در هر روز -----
            if data == "admin_daily_archive":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                # گرفتن آمار ۶۰ روز گذشته
                growth_data = db.get_daily_user_growth(days=60)
                if not growth_data:
                    bot.answer_callback_query(call.id, "هنوز داده‌ای موجود نیست.", show_alert=True)
                    return

                # ساخت متن
                lines = ["📊 *آرشیو روزانه — کاربران جدید*", "━━━━━━━━━━━━━━━━━━━━━━━━", ""]
                prev_count = None
                # از جدیدترین به قدیمی‌ترین (معکوس)
                for date_iso, count in reversed(growth_data):
                    # تبدیل تاریخ میلادی به شمسی
                    try:
                        g_date = datetime.date.fromisoformat(date_iso)
                        j_date = jdatetime.date.fromgregorian(date=g_date)
                        date_display = to_persian_digits(j_date.strftime("%Y/%m/%d"))
                    except Exception:
                        date_display = to_persian_digits(date_iso)

                    # محاسبه درصد رشد نسبت به روز قبل
                    if prev_count is not None and prev_count > 0:
                        change_pct = int(round((count - prev_count) * 100 / prev_count))
                        if change_pct > 0:
                            change_str = f" (🟢 +{to_persian_digits(change_pct)}٪)"
                        elif change_pct < 0:
                            change_str = f" (🔴 {to_persian_digits(change_pct)}٪)"
                        else:
                            change_str = " (⚪️ ۰٪)"
                    else:
                        change_str = ""

                    lines.append(f"📅 {date_display} → {to_persian_digits(count)}{change_str}")
                    prev_count = count

                # محاسبه مجموع و میانگین
                total_new = sum(c for _, c in growth_data)
                avg = total_new / len(growth_data) if growth_data else 0
                lines.append("")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━━━")
                lines.append(f"📈 مجموع (۶۰ روز اخیر): {to_persian_int(total_new)}")
                lines.append(f"📊 میانگین روزانه: {to_persian_digits(int(avg))}")

                markup = types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("🔙 بازگشت به آمار", callback_data="admin_daily")
                )
                # ارسال به‌صورت پیام جدید (چون ممکن است طولانی باشد)
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                bot.send_message(chat_id, "\n".join(lines), reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "admin_broadcast":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                set_broadcast_mode(True, chat_id, None, time.time())
                bot.answer_callback_query(call.id)
                markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ لغو حالت پخش همگانی", callback_data="broadcast_mode_cancel"))
                bot.send_message(chat_id,
                    "📢 *حالت پخش همگانی فعال شد!*\n\n"
                    f"⏳ اگر تا {BROADCAST_TIMEOUT//60} دقیقه دیگر پیامی نفرستید، این حالت خودکار لغو خواهد شد.\n\n"
                    "برای لغو فوری همین حالا، دکمهٔ زیر را بزنید.",
                    reply_markup=markup)
                return

            if data == "admin_support_list":
                # حذف شد — طبق درخواست، دکمه پشتیبانی‌ها از منوی ادمین حذف شده.
                # اما برای backward-compatibility کالبک رو نگه می‌داریم.
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                bot.answer_callback_query(call.id, "این بخش حذف شده است.", show_alert=True)
                return

            # ----- زیرمنوی VIP -----
            if data == "admin_vip_submenu":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                text = (
                    "👑 *مدیریت VIP*\n\n"
                    "یکی از گزینه‌های زیر را انتخاب کنید:\n\n"
                    "💰 تراکنش‌ها — لیست پرداخت‌ها\n"
                    "💵 تغییر قیمت VIP — ویرایش قیمت همه پلن‌ها\n"
                    "📊 آمار VIP — تعداد فعال و منقضی\n"
                    "⚙️ مدیریت VIP — افزودن VIP دستی و لیست VIPها"
                )
                bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=admin_vip_submenu_markup())
                bot.answer_callback_query(call.id)
                return

            # ----- اد اجباری -----
            if data == "admin_forced_ads":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                channels = db.get_all_forced_channels()
                lines = ["📢 *مدیریت کانال‌های اجباری*"]
                markup = types.InlineKeyboardMarkup(row_width=1)
                if channels:
                    for ch in channels:
                        ch_id = ch['channel_id']
                        ch_name = channel_info.get(ch_id, {}).get("name", ch_id)
                        count = db.get_channel_join_count(ch_id)
                        lines.append(f"• {ch_name} ({count} عضو جذب‌شده)")
                        markup.add(types.InlineKeyboardButton(f"❌ حذف {ch_name}", callback_data=f"admin_remove_channel_{ch_id}"))
                else:
                    lines.append("هیچ کانالی تعریف نشده است.")
                markup.add(types.InlineKeyboardButton("➕ افزودن کانال", callback_data="admin_add_channel"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "admin_add_channel":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('admin_new_channel',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "شناسه کانال (مثلاً @username یا شناسه عددی) را بفرستید:", reply_markup=cancel_markup())
                return

            # ----- حذف کانال (اصلاح‌شده با ادامهٔ حلقه) -----
            if data.startswith("admin_remove_channel_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                ch_id = data[len("admin_remove_channel_"):]
                db.remove_forced_channel(ch_id)
                if ch_id in CHANNELS:
                    CHANNELS.remove(ch_id)
                channel_info.pop(ch_id, None)
                broken_channels.discard(ch_id)            # <-- این خط اضافه شود
                bot.answer_callback_query(call.id, "✅ کانال حذف شد.")
                data = "admin_forced_ads"
                continue

            # ----- پخش همگانی -----
            # broadcast_confirm و broadcast_cancel حذف شدند — با کیبورد معمولی هندل می‌شن
            if data == "broadcast_mode_cancel":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                set_broadcast_mode(False)
                bot.answer_callback_query(call.id, "لغو شد.")
                bot.edit_message_text("❌ حالت پخش همگانی لغو شد.", chat_id, call.message.message_id, reply_markup=admin_panel_back_markup())
                return

            if data == "broadcast_stop":
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                broadcast_stop_flag.set()
                bot.answer_callback_query(call.id, "⏹️ درخواست توقف ارسال شد. چند ثانیه طول می‌کشد...")
                return

            # ----- دکمه‌های عمومی -----
            if data == "my_link_show":
                clear_user_state(chat_id)
                link = user_link(user_id)
                samples = [
                    f"[جرات داری روم کلیک کن 👁️]({link})",
                    f"[میخوای آشنا شیم؟ 🤭]({link})",
                ]
                text = (
                    f"🔍 *تلهٔ اختصاصی تو:*\n{link}\n\n"
                    f"🎭 این لینک خام رو که نمی‌تونی توی بیو بذاری...\n"
                    f"باید پشت یه متن قایمش کنی — این میشه *هایپرلینک*.\n"
                    f"یه جملهٔ جذاب که هرکی روش بزنه، مستقیم می‌افته توی دامت.\n\n"
                    f"📋 چند نمونهٔ آماده با کد خودت:\n"
                    f"1. {samples[0]}\n"
                    f"2. {samples[1]}\n\n"
                    f"💡 هرکدوم رو دوست داشتی *کپی* کن و بچسبون توی بیوگرافیت.\n"
                    f"یا خودت یه متن دلخواه بساز..."
                )
                markup = types.InlineKeyboardMarkup(row_width=2)
                btn1 = types.InlineKeyboardButton("📋 کپی 1", callback_data=f"copy_sample_1", copy_text=types.CopyTextButton(samples[0]))
                btn2 = types.InlineKeyboardButton("📋 کپی 2", callback_data=f"copy_sample_2", copy_text=types.CopyTextButton(samples[1]))
                markup.add(btn1, btn2)
                markup.add(types.InlineKeyboardButton("✍️ ساخت هایپرلینک با متن دلخواه", callback_data="get_hyperlink"))
                markup.add(types.InlineKeyboardButton("🎬 نحوه قرار دادن لینک", callback_data="help_link_tutorial"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))

                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, text, reply_markup=markup)
                else:
                    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "get_hyperlink":
                clear_user_state(chat_id)
                set_user_state(chat_id, ('link_text',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "✍️ متنی که میخوای هایپرلینک شه رو وارد کن:", reply_markup=cancel_markup())
                return

            # ----- اطلاعات من + آمار من -----
            if data == "my_info":
                clear_user_state(chat_id)
                # ابتدا چک کن تسک‌های تازه تکمیل‌شده رو (برای به‌روزرسانی سطح و XP)
                # نکته: _check_and_award_tasks_xp فقط در tasks page صدا زده می‌شه (نه در my_info)

                u = call.from_user
                total_clicks = db.get_clicks_count(user_id)
                snoop_count = db.get_distinct_snoop_count(user_id)
                today_clicks = db.get_today_clicks_count(user_id)
                invite_count = db.get_user_invite_count(user_id)
                is_active_vip, vip_status_str = vip_status_display(user_id)
                emoji = get_user_rank_emoji(user_id)
                level = db.get_user_level_cached(user_id)
                xp = db.get_user_xp(user_id)
                title, _ = get_rank_tier(level)
                xp_next = db.xp_for_next_level(level)

                # محاسبه progress bar برای سطح
                # نکته: سطح ۱ از XP=0 شروع می‌شود، سطح L≥2 از xp_for_level(L)
                if level < 50 and xp_next:
                    if level == 1:
                        xp_this_level_start = 0
                    else:
                        xp_this_level_start = db.xp_for_level(level)
                    xp_in_level = xp - xp_this_level_start
                    xp_needed_this_level = xp_next - xp_this_level_start
                    progress_pct = int(xp_in_level * 100 / xp_needed_this_level) if xp_needed_this_level > 0 else 0
                    progress_pct = max(0, min(100, progress_pct))
                    bar_len = 10
                    filled = int(progress_pct * bar_len / 100)
                    level_bar = '█' * filled + '░' * (bar_len - filled)
                    xp_to_next = xp_next - xp
                    level_section = (
                        f"📊 سطح: {to_persian_digits(level)} — {emoji} {title}\n"
                        f"✨ {to_persian_int(xp)} از {to_persian_int(xp_next)} دریافت شده\n"
                        f"{level_bar} {to_persian_digits(progress_pct)}٪\n"
                        f"🎯 تا سطح بعد: {to_persian_int(xp_to_next)} XP"
                    )
                else:
                    level_section = (
                        f"📊 سطح: {to_persian_digits(level)} — {emoji} {title}\n"
                        f"✨ XP: {to_persian_int(xp)}\n"
                        f"🏆 به حداکثر سطح رسیده‌اید!"
                    )

                display_name = f"{emoji} {escape_md(u.first_name or 'بی‌نام')}" if emoji else escape_md(u.first_name or 'بی‌نام')

                # قالب جدید بدون باکس/جعبه — سبک و خوانا
                text = (
                    f"📋 *اطلاعات من*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 {display_name}\n"
                    f"🆔 {to_persian_digits(user_id)}\n"
                    f"📎 @{u.username or 'ندارد'}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📈 *آمار*\n"
                    f"🔍 شکارهای یکتا: {to_persian_int(snoop_count)}\n"
                    f"👥 کل کلیک‌ها: {to_persian_int(total_clicks)}\n"
                    f"📅 کلیک‌های امروز: {to_persian_int(today_clicks)}\n"
                    f"👤 دعوت‌های موفق: {to_persian_int(invite_count)}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *پیشرفت*\n"
                    f"{level_section}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏅 *اشتراک*\n"
                    f"وضعیت VIP: {vip_status_str}\n\n"
                    f"🔗 *تلهٔ شما*\n"
                    f"{user_link(user_id)}\n"
                )

                # بخش آخرین فعالیت‌ها
                activities = db.get_recent_activities(user_id, limit=4)
                if activities:
                    text += f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    text += f"🕐 *آخرین فعالیت‌ها*\n"
                    for act in activities:
                        try:
                            ts = act.get('timestamp', '')
                            if ts:
                                # تبدیل به تاریخ شمسی
                                try:
                                    g_date = datetime.datetime.strptime(ts[:10], "%Y-%m-%d").date()
                                    j_date = jdatetime.date.fromgregorian(date=g_date)
                                    time_str = to_persian_digits(j_date.strftime("%Y/%m/%d"))
                                except:
                                    time_str = to_persian_digits(ts[:10])
                            else:
                                time_str = 'نامشخص'
                        except:
                            time_str = 'نامشخص'

                        if act['type'] == 'click':
                            name = escape_md(act.get('name', 'ناشناس'))
                            text += f"• {time_str}: {name} تله‌ات رو کلیک کرد\n"
                        elif act['type'] == 'vip':
                            days = to_persian_digits(act.get('days', 0))
                            text += f"• {time_str}: VIP خریدی ({days} روز)\n"
                        elif act['type'] == 'gift':
                            days = to_persian_digits(act.get('days', 0))
                            text += f"• {time_str}: VIP هدیه دادی ({days} روز)\n"
                        elif act['type'] == 'task':
                            task_name = escape_md(act.get('task_name', 'ماموریت'))
                            text += f"• {time_str}: ماموریت «{task_name}» رو تکمیل کردی\n"

                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("🎯 ماموریت‌ها", callback_data="tasks_page_1"),
                           types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, text, reply_markup=markup)
                else:
                    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
                return

            if data == "my_stats":
                today_clicks = db.get_today_clicks_count(user_id)
                new_souls = db.get_user_invite_count(user_id)
                top_snoops = db.get_snoops(user_id)[:3]
                lines = ["📊 *آمار شکارچی*\n"]
                lines.append(f"👣 کلیک‌های امروز: {today_clicks}")
                lines.append(f"👶 کاربران تازه: {new_souls}")
                if top_snoops:
                    lines.append("\n🕵️ *۳ فضول برتر:*")
                    for i, s in enumerate(top_snoops):
                        name = s.get('nickname') or s['name']
                        lines.append(f"{i+1}. {escape_md(name)} – {s['count']} بار")
                else:
                    lines.append("\n🕵️ هنوز هیچ فضولی ثبت نشده.")
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("🔙 اطلاعات من", callback_data="my_info"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, "\n".join(lines), reply_markup=markup)
                else:
                    bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
                return

            # ====== ماموریت‌ها ======
            if data.startswith("tasks_page_"):
                page = int(data.split("_")[-1])
                # loading toast برای پردازش ۲۰۰ تسک
                try:
                    bot.answer_callback_query(call.id, "⏳ در حال بارگذاری...")
                except: pass
                show_tasks_page(chat_id, user_id, page, call)
                return

            if data.startswith("task_detail_"):
                task_id = data[len("task_detail_"):]
                show_task_detail_popup(call, user_id, task_id)
                return

            if data == "achievements" or data == "my_progress":
                # نمایش پیشرفت سطح کاربر (جایگزین تالار افتخارات حذف‌شده)
                level = db.get_user_level_cached(user_id)
                xp = db.get_user_xp(user_id)
                xp_next = db.xp_for_next_level(level)
                title, emoji = get_rank_tier(level)
                # محاسبهٔ XP لازم برای این سطح و سطح بعدی
                xp_this_level_start = db.xp_for_level(level - 1) if level > 1 else 0
                xp_in_level = xp - xp_this_level_start
                xp_needed_this_level = (100 * level) if level <= 50 else 0
                # رتبه بعدی
                next_tier = None
                for i, tier in enumerate(texts.RANK_TIERS):
                    if tier["min_level"] <= level <= tier["max_level"]:
                        if i + 1 < len(texts.RANK_TIERS):
                            next_tier = texts.RANK_TIERS[i + 1]
                        break
                lines = [f"📈 *پیشرفت کارآگاهی شما*\n"]
                lines.append(f"{emoji} *رتبه:* {title}")
                lines.append(f"📊 *سطح:* {to_persian_digits(level)} از ۵۰")
                lines.append(f"✨ *XP کل:* {to_persian_int(xp)}")
                if xp_next:
                    lines.append(f"🎯 XP تا سطح بعد: {to_persian_int(xp_next - xp)}")
                else:
                    lines.append("🏆 به حداکثر سطح رسیده‌اید!")
                if xp_needed_this_level and level <= 50:
                    progress_pct = int(xp_in_level * 100 / xp_needed_this_level) if xp_needed_this_level else 0
                    progress_pct = max(0, min(100, progress_pct))
                    bar_len = 10
                    filled = int(progress_pct / 10)
                    bar = '█' * filled + '░' * (bar_len - filled)
                    lines.append(f"\n{bar} {to_persian_digits(progress_pct)}٪")
                if next_tier:
                    next_level_needed = next_tier["min_level"]
                    levels_to_next = next_level_needed - level
                    lines.append(f"\n🔮 رتبهٔ بعد: {next_tier['emoji']} {next_tier['title']}")  # 🔮 ایموجی رتبه — معتبر
                    lines.append(f"📋 {to_persian_digits(levels_to_next)} سطح تا رتبهٔ بعدی")
                lines.append("\n💡 *راه‌های کسب XP:*")
                lines.append(f"🔍 هر فضول یکتای جدید: +{to_persian_digits(XP_RECURRING['new_distinct_snoop'])}")
                lines.append(f"👤 هر دعوت موفق: +{to_persian_digits(XP_RECURRING['successful_invite'])}")
                lines.append(f"📅 ورود روزانه: +{to_persian_digits(XP_RECURRING['daily_login'])}")
                lines.append(f"👑 خرید اشتراک ویژه: +{to_persian_digits(XP_RECURRING['buy_vip'])}")
                lines.append(f"🎁 هدیه اشتراک ویژه: +{to_persian_digits(XP_RECURRING['gift_vip'])}")
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("🔙 اطلاعات من", callback_data="my_info"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, "\n".join(lines), reply_markup=markup)
                else:
                    bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id, reply_markup=markup)
                return

            # ----- لیست فضول‌ها -----
            if data.startswith("snooplist_page_"):
                page = int(data.split("_")[-1])
                clear_user_state(chat_id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    show_snoop_list(chat_id, page)
                else:
                    show_snoop_list(chat_id, page, message_id=call.message.message_id)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("snoopdetail_"):
                cid = int(data.split("_")[1])
                snoops = db.get_snoops(user_id)
                info = next((s for s in snoops if s['clicker_id'] == cid), None)
                if not info:
                    bot.answer_callback_query(call.id, "خطا!")
                    return
                vip = db.is_vip(user_id)
                name_disp = info.get('nickname') or info['name']
                detail = f"👤 {escape_md(name_disp)}\n🔢 {info['count']} بار\n🆔 {fmt_id(cid, vip)}\n📎 {fmt_uname(info.get('username'), vip)}"
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton("✉️ پیام ناشناس", callback_data=f"anon_{cid}"),
                    types.InlineKeyboardButton("🏷️ لقب", callback_data=f"nick_{cid}"),
                    types.InlineKeyboardButton("🎁 هدیه VIP", callback_data=f"giftvip_{cid}"),
                    types.InlineKeyboardButton("🔙 لیست", callback_data="snooplist_page_1"))
                if db.is_snoop_muted(user_id, cid):
                    markup.add(types.InlineKeyboardButton("🔔 با صدا", callback_data=f"unmute_{cid}"))
                else:
                    markup.add(types.InlineKeyboardButton("🔕 بی‌صدا", callback_data=f"mute_{cid}"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, detail, reply_markup=markup)
                else:
                    bot.edit_message_text(detail, chat_id, call.message.message_id, reply_markup=markup)
                return

            if data.startswith("nick_"):
                cid = int(data.split("_")[1])
                clear_user_state(chat_id)
                set_user_state(chat_id, ('nickname', cid))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, "🏷️ لقب:", reply_markup=cancel_markup())
                else:
                    bot.edit_message_text("🏷️ لقب:", chat_id, call.message.message_id, reply_markup=cancel_markup())
                return

            if data.startswith("anon_") and not data.startswith("anon_reply_"):
                cid = int(data.split("_")[1])
                clear_user_state(chat_id)
                set_user_state(chat_id, ('anon_msg', cid))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, "✉️ پیام ناشناس:", reply_markup=cancel_markup())
                else:
                    bot.edit_message_text("✉️ پیام ناشناس:", chat_id, call.message.message_id, reply_markup=cancel_markup())
                return

            if data.startswith("giftvip_"):
                target_id = int(data.split("_")[1])
                markup = types.InlineKeyboardMarkup(row_width=1)
                for days, amount in VIP_PRICES.items():
                    markup.add(types.InlineKeyboardButton(f"🎁 {days} روزه – {amount//10:,} تومان", callback_data=f"confirmgift_{target_id}_{days}"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data=f"snoopdetail_{target_id}"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.answer_callback_query(call.id)
                if call.message.content_type == 'photo':
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except:
                        pass
                    bot.send_message(chat_id, f"🎁 *هدیه VIP*", reply_markup=markup)
                else:
                    bot.edit_message_text(f"🎁 *هدیه VIP*", chat_id, call.message.message_id, reply_markup=markup)
                return

            if data.startswith("confirmgift_"):
                parts = data.split("_")
                target_id = int(parts[1])
                days = int(parts[2])
                # رفع باگ: بررسی اعتبار پلن قبل از ارسال فاکتور
                amount = VIP_PRICES.get(days)
                if amount is None:
                    bot.answer_callback_query(call.id, "❌ طرح انتخابی نامعتبر است.", show_alert=True)
                    return
                payload = f"giftvip_{user_id}_{target_id}_{days}_{int(time.time())}"
                try:
                    bot.send_invoice(chat_id, title="🎁 هدیه VIP", description=f"فعال‌سازی VIP برای کاربر دیگر به مدت {days} روز",
                                     invoice_payload=payload, provider_token=PROVIDER_TOKEN, currency="IRT",
                                     prices=[types.LabeledPrice(label=f"VIP {days} روزه", amount=amount)],
                                     need_name=False, need_phone_number=False, need_email=False, is_flexible=False)
                    bot.answer_callback_query(call.id, "فاکتور هدیه ارسال شد.")
                except Exception as e:
                    logger.error(f"Gift invoice error: {e}")
                    bot.answer_callback_query(call.id, "❌ خطا در ایجاد فاکتور.", show_alert=True)
                return

            if data == "support":
                clear_user_state(chat_id)
                add_support_session(chat_id)
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(types.InlineKeyboardButton("خروج از پشتیبانی", callback_data="support_exit"),
                           types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "📞 پیامت رو بنویس...", reply_markup=markup)
                return

            # ----- بخش VIP (بازطراحی‌شده با ۲ دکمه اصلی + عکس) -----
            if data == "vip_info":
                clear_user_state(chat_id)
                is_active, status_str = vip_status_display(user_id)
                text = vip_info_text() + f"\n\n📌 *وضعیت اشتراک شما:* {status_str}"
                m = types.InlineKeyboardMarkup(row_width=2)
                # دو دکمه اصلی که خواسته بودید
                m.add(types.InlineKeyboardButton("🛒 خرید VIP", callback_data="buy_vip_menu"),
                      types.InlineKeyboardButton("✨ قابلیت‌های VIP", callback_data="vip_features"))
                m.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                # همیشه پیام قبلی رو پاک کن و پیام جدید بفرست (مثل لیدربورد)
                # چون اگه پیام قبلی عکس داشته باشه، edit_text خراب می‌شه
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                if VIP_MAIN_PHOTO_ID:
                    try:
                        bot.send_photo(chat_id, VIP_MAIN_PHOTO_ID, caption=text, reply_markup=m)
                    except:
                        bot.send_message(chat_id, text, reply_markup=m)
                else:
                    bot.send_message(chat_id, text, reply_markup=m)
                bot.answer_callback_query(call.id)
                return

            # منوی قابلیت‌های VIP (دکمه‌های تنظیمات زیر این منو)
            if data == "vip_features":
                clear_user_state(chat_id)
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(types.InlineKeyboardButton("📝 تنظیم متن خوش‌آمدگویی", callback_data="set_welcome"))
                m.add(types.InlineKeyboardButton("🖼️ تنظیم عکس خوش‌آمدگویی", callback_data="set_welcome_photo"))
                m.add(types.InlineKeyboardButton("🎭 تنظیم نقاب کارآگاهی", callback_data="set_mask"))
                m.add(types.InlineKeyboardButton("📜 پیش‌نمایش پیام خوش‌آمد", callback_data="preview_welcome"))
                m.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="vip_info"))
                m.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                # delete+resend چون پیام قبلی ممکن است عکس‌دار باشد
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                bot.send_message(chat_id, "✨ *قابلیت‌های VIP*\n یکی از قابلیت‌ها را برای تنظیم انتخاب کنید:", reply_markup=m)
                bot.answer_callback_query(call.id)
                return

            if data == "buy_vip_menu":
                m = types.InlineKeyboardMarkup(row_width=1)
                for days, amount in VIP_PRICES.items():
                    m.add(types.InlineKeyboardButton(f"📅 {to_persian_digits(days)} روزه – {fmt_amount_toman(amount)}", callback_data=f"buy_vip_{days}"))
                m.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="vip_info"))
                # delete+resend چون پیام قبلی ممکن است عکس‌دار باشد
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                buy_text = "🛒 *خرید VIP*\n\nیکی از پلن‌های زیر را انتخاب کنید:"
                if BUY_VIP_PHOTO_ID:
                    try:
                        bot.send_photo(chat_id, BUY_VIP_PHOTO_ID, caption=buy_text, reply_markup=m)
                    except:
                        bot.send_message(chat_id, buy_text, reply_markup=m)
                else:
                    bot.send_message(chat_id, buy_text, reply_markup=m)
                bot.answer_callback_query(call.id)
                return

            if data.startswith("buy_vip_"):
                days = int(data.split("_")[2])
                # رفع باگ: بررسی اعتبار پلن قبل از ارسال فاکتور
                amount = VIP_PRICES.get(days)
                if amount is None:
                    bot.answer_callback_query(call.id, "❌ طرح انتخابی نامعتبر است.", show_alert=True)
                    return
                payload = f"vip_{user_id}_{days}_{int(time.time())}"
                try:
                    bot.send_invoice(chat_id, title="اشتراک VIP فضول‌یاب", description=f"فعال‌سازی اشتراک ویژه به مدت {days} روز",
                                     invoice_payload=payload, provider_token=PROVIDER_TOKEN, currency="IRT",
                                     prices=[types.LabeledPrice(label=f"VIP {days} روزه", amount=amount)],
                                     need_name=False, need_phone_number=False, need_email=False, is_flexible=False)
                    bot.answer_callback_query(call.id, "✅ فاکتور ارسال شد.")
                except Exception as e:
                    logger.error(f"VIP invoice error: {e}")
                    bot.answer_callback_query(call.id, "❌ خطا در ایجاد فاکتور.", show_alert=True)
                return

            if data == "set_welcome":
                if not db.is_vip(user_id):
                    bot.answer_callback_query(call.id, "⛔ این قابلیت فقط برای کاربران VIP فعال است.", show_alert=True)
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('welcome_text',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "✍️ متن:", reply_markup=cancel_markup())
                return

            if data == "set_welcome_photo":
                if not db.is_vip(user_id):
                    bot.answer_callback_query(call.id, "⛔ این قابلیت فقط برای کاربران VIP فعال است.", show_alert=True)
                    return
                clear_user_state(chat_id)
                set_user_state(chat_id, ('welcome_photo',))
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "🖼️ عکس خوش‌آمدگویی را ارسال کنید:", reply_markup=cancel_markup())
                return

            if data == "set_mask":
                if not db.is_vip(user_id):
                    bot.answer_callback_query(call.id, "⛔ این قابلیت فقط برای کاربران VIP فعال است.", show_alert=True)
                    return
                clear_user_state(chat_id)
                markup = types.InlineKeyboardMarkup(row_width=4)
                btns = [types.InlineKeyboardButton(em, callback_data=f"mask_emoji_{em}") for em in MASK_EMOJIS]
                for i in range(0, len(btns), 4):
                    markup.add(*btns[i:i+4])
                markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_state"))
                bot.edit_message_text("🎭 یک ایموجی برای نقاب انتخاب کن یا خودت تایپ کن:", chat_id, call.message.message_id, reply_markup=markup)
                set_user_state(chat_id, ('mask_emoji',))
                bot.answer_callback_query(call.id)
                return

            if data.startswith("mask_emoji_"):
                if not db.is_vip(user_id):
                    bot.answer_callback_query(call.id, "⛔ اشتراک VIP شما فعال نیست.", show_alert=True)
                    return
                emoji = data.split("_", 2)[2]
                clear_user_state(chat_id)
                set_user_state(chat_id, ('mask_text', emoji))
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(types.InlineKeyboardButton("بدون لقب", callback_data="mask_skip_text"),
                           types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_state"))
                bot.edit_message_text(f"🎭 ایموجی: {emoji}\nحالا لقب (متن) نقاب را بفرست، یا دکمه «بدون لقب» را بزن.", chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "mask_skip_text":
                state = get_user_state(chat_id)
                if state and state[0] == 'mask_text':
                    emoji = state[1]
                    clear_user_state(chat_id)
                    if not db.is_vip(chat_id):
                        bot.edit_message_text(VIP_EXPIRED_MSG, chat_id, call.message.message_id, reply_markup=vip_menu_button())
                        bot.answer_callback_query(call.id)
                        return
                    db.set_user_mask(chat_id, emoji, "")
                    bot.edit_message_text(f"🎭 نقاب کارآگاهی تو: {emoji}", chat_id, call.message.message_id, reply_markup=vip_menu_button())
                else:
                    bot.answer_callback_query(call.id, "خطا.")
                bot.answer_callback_query(call.id)
                return

            # ----- راهنما -----
            if data == "help":
                clear_user_state(chat_id)
                markup = types.InlineKeyboardMarkup(row_width=2)
                # دکمه‌های راهنمای جدید — طبق texts.HELP_MAIN_BUTTONS
                for label, callback in texts.HELP_MAIN_BUTTONS:
                    markup.add(types.InlineKeyboardButton(label, callback_data=callback))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.edit_message_text(texts.HELP_MAIN_PROMPT, chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            # ----- زیردکمه‌های راهنما -----
            if data in ("help_link", "help_vip", "help_anon", "help_gift",
                        "help_tasks", "help_xp", "help_myinfo", "help_link_tutorial"):
                mapping = {
                    "help_link": texts.HELP_LINK,
                    "help_vip": texts.HELP_VIP,
                    "help_anon": texts.HELP_ANON,
                    "help_gift": texts.HELP_GIFT,
                    "help_tasks": texts.HELP_TASKS,
                    "help_xp": texts.HELP_XP,
                    "help_myinfo": texts.HELP_MYINFO_NEW,
                }
                # برای help_link_tutorial فقط دکمه خانه (بدون بازگشت به راهنما)
                if data == "help_link_tutorial":
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                else:
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(types.InlineKeyboardButton("🔙 راهنما", callback_data="help"))
                    markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))

                # برای help_link_tutorial یک ویدیو ارسال می‌کنیم
                if data == "help_link_tutorial":
                    # پاک کردن پیام قبلی و ارسال ویدیو + متن
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except: pass
                    if LINK_TUTORIAL_VIDEO_ID:
                        try:
                            bot.send_video(chat_id, LINK_TUTORIAL_VIDEO_ID, caption=texts.LINK_TUTORIAL_TEXT, reply_markup=markup)
                        except:
                            bot.send_message(chat_id, texts.LINK_TUTORIAL_TEXT, reply_markup=markup)
                    else:
                        bot.send_message(chat_id, texts.LINK_TUTORIAL_TEXT + "\n\n⚠️ ویدیوی آموزشی به‌زودی اضافه می‌شود.", reply_markup=markup)
                    bot.answer_callback_query(call.id)
                    return

                bot.edit_message_text(mapping[data], chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            # ----- backward compatibility برای دکمه‌های قدیمی -----
            if data in ("help_welcome", "help_welcome_photo", "help_mask", "help_myinfo"):
                mapping = {
                    "help_welcome": texts.HELP_WELCOME,
                    "help_welcome_photo": texts.HELP_WELCOME_PHOTO,
                    "help_mask": texts.HELP_MASK,
                    "help_myinfo": texts.HELP_MYINFO_NEW
                }
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("🔙 راهنما", callback_data="help"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                bot.edit_message_text(mapping[data], chat_id, call.message.message_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "preview_welcome":
                clear_user_state(chat_id)
                welcome_text = db.get_welcome_text(user_id)
                welcome_photo = db.get_welcome_photo(user_id)
                if not welcome_text and not welcome_photo:
                    bot.answer_callback_query(call.id, "⛔ هیچ پیام خوش‌آمدی تنظیم نکردی.", show_alert=True)
                    return
                note = "" if db.is_vip(user_id) else "\n\n⚠️ توجه: چون اشتراک VIP شما در حال حاضر غیرفعال است، این پیام به فضول‌ها نمایش داده نمی‌شود."
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("🔙 بازگشت به VIP", callback_data="vip_info"))
                markup.add(types.InlineKeyboardButton("🏠 خانه", callback_data="main_menu"))
                if welcome_photo:
                    try:
                        bot.send_photo(chat_id, welcome_photo, caption=(welcome_text or "👋") + note, reply_markup=markup)
                    except:
                        bot.send_message(chat_id, (welcome_text or "👋") + note, reply_markup=markup)
                else:
                    bot.send_message(chat_id, (welcome_text or "👋") + note, reply_markup=markup)
                bot.answer_callback_query(call.id)
                return

            if data == "main_menu":
                clear_user_state(chat_id)
                bot.answer_callback_query(call.id)
                show_main_menu_for_callback(call, chat_id, user_id)
                return

            # ====== کالبک‌های ویزارد کاربر جدید ======
            if data == "wizard_make_trap":
                # کاربر تله ساخت — اول پیام تله رو نشون بده، بعد منوی اصلی
                bot.answer_callback_query(call.id)
                # حذف پیام ویزارد
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                # نمایش تله (مثل my_link_show)
                link = user_link(user_id)
                samples = [
                    f"[جرات داری روم کلیک کن 👁️]({link})",
                    f"[میخوای آشنا شیم؟ 🤭]({link})",
                ]
                trap_text = (
                    f"🔍 *تلهٔ اختصاصی تو:*\n{link}\n\n"
                    f"📋 این لینک خام رو که نمی‌تونی توی بیو بذاری...\n"
                    f"باید پشت یه متن قایمش کنی — این میشه *هایپرلینک*.\n"
                    f"یه جملهٔ جذاب که هرکی روش بزنه، مستقیم می‌افته توی دامت.\n\n"
                    f"📋 چند نمونهٔ آماده با کد خودت:\n"
                    f"۱. {samples[0]}\n"
                    f"۲. {samples[1]}\n\n"
                    f"💡 هرکدوم رو دوست داشتی *کپی* کن و بچسبون توی بیوگرافیت.\n"
                    f"یا خودت یه متن دلخواه بساز..."
                )
                trap_markup = types.InlineKeyboardMarkup(row_width=2)
                btn1 = types.InlineKeyboardButton("📋 کپی ۱", callback_data="copy_sample_1", copy_text=types.CopyTextButton(samples[0]))
                btn2 = types.InlineKeyboardButton("📋 کپی ۲", callback_data="copy_sample_2", copy_text=types.CopyTextButton(samples[1]))
                trap_markup.add(btn1, btn2)
                trap_markup.add(types.InlineKeyboardButton("✍️ ساخت هایپرلینک با متن دلخواه", callback_data="get_hyperlink"))
                trap_markup.add(types.InlineKeyboardButton("🎬 نحوه قرار دادن لینک", callback_data="help_link_tutorial"))
                # دکمه ادامه به منوی اصلی
                trap_markup.add(types.InlineKeyboardButton("➡️ ادامه به منوی اصلی", callback_data="wizard_go_home"))
                bot.send_message(chat_id, trap_text, reply_markup=trap_markup)
                return

            if data == "wizard_skip":
                # کاربر رد کرد — پیام کوتاه + منوی اصلی
                bot.answer_callback_query(call.id)
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except: pass
                bot.send_message(chat_id, texts.WIZARD_AFTER_TUTORIAL_SKIP)
                # ارسال منوی اصلی
                show_main_menu_for_callback(call, chat_id, user_id)
                return

            if data == "wizard_go_home":
                # بعد از ساخت تله، به منوی اصلی بره
                bot.answer_callback_query(call.id)
                show_main_menu_for_callback(call, chat_id, user_id)
                return

            if data.startswith("copy_sample_"):
                bot.answer_callback_query(call.id)
                return
            if data == "copy_dummy":
                bot.answer_callback_query(call.id)
                return

            if data.startswith("admin_block_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                target = int(data.split("_")[2])
                db.block_user(target, by_admin=True)
                bot.answer_callback_query(call.id, f"کاربر {target} مسدود شد.")
                return
            if data.startswith("admin_msg_"):
                if user_id != ADMIN_ID:
                    bot.answer_callback_query(call.id, "⛔")
                    return
                target = int(data.split("_")[2])
                set_admin_reply(user_id, target)
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "✍️ پیام خود را برای کاربر بنویسید:", reply_markup=cancel_markup())
                return

            if data == "cancel_state":
                clear_user_state(chat_id)
                remove_support_session(chat_id)
                pop_support_partner(chat_id)
                pop_admin_reply(chat_id)
                bot.answer_callback_query(call.id, "❌ لغو شد.")
                show_main_menu_for_callback(call, chat_id, user_id)
                return

            # اگر به اینجا رسیدیم، یعنی callback نهایی پردازش شده و باید خارج شویم
            bot.answer_callback_query(call.id)
            return

        except Exception as e:
            logger.error(f"Callback error: {e}")
            try:
                bot.answer_callback_query(call.id)
            except:
                pass
            return
        
# ====== هندلرهای پرداخت ======
@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(query):
    """رفع باگ: اعتبارسنجی payload قبل از تأیید پرداخت.
    بدون این اعتبارسنجی، کاربر می‌تواند با payload دستی پرداخت کند و VIP بگیرد."""
    try:
        parts = query.invoice_payload.split("_")
        if not parts or parts[0] not in ("vip", "giftvip"):
            bot.answer_pre_checkout_query(query.id, ok=False,
                error_message="فاکتور نامعتبر است.")
            return

        if parts[0] == "vip":
            # payload: vip_{user_id}_{days}_{time}
            if len(parts) < 4:
                bot.answer_pre_checkout_query(query.id, ok=False,
                    error_message="اطلاعات فاکتور ناقص است.")
                return
            buyer_id = int(parts[1])
            days = int(parts[2])
            # فقط خریدار می‌تواند پرداخت کند
            if buyer_id != query.from_user.id:
                bot.answer_pre_checkout_query(query.id, ok=False,
                    error_message="این فاکتور برای کاربر دیگری است.")
                return
            expected_amount = VIP_PRICES.get(days)
        else:  # giftvip
            # payload: giftvip_{buyer_id}_{target_id}_{days}_{time}
            if len(parts) < 5:
                bot.answer_pre_checkout_query(query.id, ok=False,
                    error_message="اطلاعات فاکتور هدیه ناقص است.")
                return
            buyer_id = int(parts[1])
            days = int(parts[3])
            if buyer_id != query.from_user.id:
                bot.answer_pre_checkout_query(query.id, ok=False,
                    error_message="این فاکتور برای کاربر دیگری است.")
                return
            expected_amount = VIP_PRICES.get(days)

        if expected_amount is None:
            bot.answer_pre_checkout_query(query.id, ok=False,
                error_message="طرح انتخابی نامعتبر است.")
            return

        bot.answer_pre_checkout_query(query.id, ok=True)
    except (ValueError, IndexError):
        bot.answer_pre_checkout_query(query.id, ok=False,
            error_message="خطا در پردازش فاکتور.")
    except Exception as e:
        logger.error(f"Pre-checkout error: {e}")
        bot.answer_pre_checkout_query(query.id, ok=False,
            error_message="خطا در پردازش فاکتور.")

@bot.message_handler(content_types=['successful_payment'])
def successful_payment(message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    try:
        parts = payload.split("_")
        if parts[0] == "vip":
            buyer_id = int(parts[1])
            # اصلاح بحرانی ۳: تطابق خریدار با کاربر واقعی
            if buyer_id != message.from_user.id:
                bot.send_message(message.chat.id, "❌ خرید نامعتبر است.", reply_markup=home_markup())
                return
            days = int(parts[2])
            expected_amount = VIP_PRICES.get(days)
            if expected_amount is None:
                bot.send_message(message.chat.id, "❌ طرح خرید نامعتبر است. لطفاً با پشتیبانی تماس بگیرید.",
                                 reply_markup=home_markup())
                return
            if payment.total_amount != expected_amount:
                bot.send_message(message.chat.id,
                                 f"❌ مبلغ پرداختی ({to_persian_int(payment.total_amount)} ریال) با مبلغ مورد انتظار ({to_persian_int(expected_amount)} ریال) مغایرت دارد. "
                                 "لطفاً با پشتیبانی تماس بگیرید.",
                                 reply_markup=home_markup())
                return
            db.add_transaction(buyer_id, "vip", expected_amount, days)
            db.add_vip(buyer_id, days)
            # ----- اعطای XP خرید VIP -----
            purchase_count = db.get_user_purchase_count(buyer_id)
            bonus = 'first_buy_vip' if purchase_count == 1 else None
            award_xp_with_level_up_notify(
                buyer_id, 0,
                recurring_type='buy_vip',
                bonus_type=bonus,
                chat_id=buyer_id
            )
            bot.send_message(buyer_id,
                             f"🏅 اشتراک VIP شما به مدت {to_persian_digits(days)} روز فعال شد! خوش آمدی به تیم کارآگاهان ویژه.",
                             reply_markup=home_markup())

        elif parts[0] == "giftvip":
            buyer_id = int(parts[1])
            if buyer_id != message.from_user.id:
                bot.send_message(message.chat.id, "❌ خرید نامعتبر است.", reply_markup=home_markup())
                return
            target_id = int(parts[2])
            days = int(parts[3])
            expected_amount = VIP_PRICES.get(days)
            if expected_amount is None:
                bot.send_message(message.chat.id, "❌ طرح هدیه نامعتبر است. لطفاً با پشتیبانی تماس بگیرید.",
                                 reply_markup=home_markup())
                return
            if payment.total_amount != expected_amount:
                bot.send_message(message.chat.id,
                                 f"❌ مبلغ پرداختی ({to_persian_int(payment.total_amount)} ریال) با مبلغ مورد انتظار ({to_persian_int(expected_amount)} ریال) مغایرت دارد. "
                                 "لطفاً با پشتیبانی تماس بگیرید.",
                                 reply_markup=home_markup())
                return
            db.add_transaction(buyer_id, "gift_vip", expected_amount, days)
            db.add_vip(target_id, days)
            buyer_name = get_user_display(buyer_id)
            # ----- اعطای XP هدیه VIP به خریدار -----
            gift_count = db.get_user_gift_count(buyer_id)
            bonus = 'first_gift_vip' if gift_count == 1 else None
            award_xp_with_level_up_notify(
                buyer_id, 0,
                recurring_type='gift_vip',
                bonus_type=bonus,
                chat_id=buyer_id
            )
            bot.send_message(buyer_id,
                             f"🎁 هدیهٔ تو ({to_persian_digits(days)} روز VIP) به کاربر مورد نظر رسید.",
                             reply_markup=home_markup())
            # رفع باگ: اگر target ربات را بلاک کرده، ارسال پیام خطا می‌دهد
            try:
                bot.send_message(target_id,
                                 f"🎁 *{escape_md(buyer_name)}* به تو {to_persian_digits(days)} روز VIP هدیه داد!\n🏅 حالا از قابلیت‌های ویژه برخوردار شدی.",
                                 reply_markup=home_markup())
            except ApiTelegramException as e:
                if e.error_code == 403:
                    logger.info(f"Target {target_id} has blocked the bot; gift VIP still applied.")
                    try:
                        db.mark_user_blocked_bot(target_id)
                    except Exception:
                        pass
                else:
                    logger.error(f"Gift notify target {target_id} error: {e}")
            except Exception as e:
                logger.error(f"Gift notify target {target_id} error: {e}")

        else:
            bot.send_message(message.chat.id, "✅ پرداخت شما دریافت شد.", reply_markup=home_markup())

    except Exception as e:
        logger.error(f"Payment error: {e}")
        bot.send_message(message.chat.id, "❌ خطا در پردازش پرداخت. لطفاً با پشتیبانی تماس بگیرید.",
                         reply_markup=home_markup())

# ====== وظایف دوره‌ای ======
def clean_logs_periodically():
    while True:
        time.sleep(86400)
        try: db.clean_old_anon_logs(30)
        except Exception as e: logger.error(f"Log clean error: {e}")

def remind_vip_expiry():
    while True:
        time.sleep(86400)
        try:
            expiring = db.get_expiring_vips(days_left=1)
            for uid in expiring:
                try:
                    bot.send_message(uid, texts.VIP_EXPIRY_REMINDER)
                except ApiTelegramException as e:
                    # رفع باگ: اگر کاربر ربات را بلاک کرده (403)، علامت‌گذاری کن تا دوباره ارسال نشود
                    if e.error_code == 403:
                        try:
                            db.mark_user_blocked_bot(uid)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"VIP reminder error: {e}")

def remind_inactive_users():
    """یادآوری روزانه به کاربرانی که ۳+ روز نیستی سر زدن و کلیک جدید دارن."""
    while True:
        # هر ۲۴ ساعت یک‌بار
        time.sleep(86400)
        try:
            # پیدا کردن کاربران فعال (بلاک نشده) که ۳+ روز از آخرین فعالیتشون گذشته
            with db._lock:
                rows = db.conn.execute(
                    "SELECT user_id, last_active_date FROM users "
                    "WHERE (blocked=0 OR blocked IS NULL) AND last_active_date IS NOT NULL "
                    "AND julianday('now') - julianday(last_active_date) >= 3 "
                    "AND julianday('now') - julianday(last_active_date) <= 30"
                ).fetchall()

            for row in rows:
                uid = row['user_id']
                last_active = row['last_active_date']
                try:
                    # محاسبه کلیک‌های جدید از آخرین فعالیت
                    from datetime import date as dt_date
                    last_date = dt_date.fromisoformat(last_active)
                    today = dt_date.today()
                    days_ago = (today - last_date).days

                    click_row = db.conn.execute(
                        "SELECT COUNT(*) as c FROM clicks WHERE owner_id=? AND date(clicked_at) >= date('now', ?)",
                        (uid, f'-{days_ago} days')
                    ).fetchone()
                    new_clicks = click_row['c'] if click_row else 0

                    distinct_row = db.conn.execute(
                        "SELECT COUNT(DISTINCT clicker_id) as c FROM clicks WHERE owner_id=? AND date(clicked_at) >= date('now', ?)",
                        (uid, f'-{days_ago} days')
                    ).fetchone()
                    new_snoops = distinct_row['c'] if distinct_row else 0

                    # فقط اگه کلیک جدید داره پیام بفرست
                    if new_clicks > 0:
                        u = db.get_user_basic(uid)
                        name = u['first_name'] if u and u['first_name'] else "دوست"
                        msg = texts.INACTIVE_REMINDER.format(
                            name=escape_md(name),
                            new_clicks=to_persian_int(new_clicks),
                            new_snoops=to_persian_int(new_snoops)
                        )
                        try:
                            bot.send_message(uid, msg)
                        except ApiTelegramException as e:
                            # رفع باگ: اگر کاربر ربات را بلاک کرده (403)، علامت‌گذاری کن
                            if e.error_code == 403:
                                try:
                                    db.mark_user_blocked_bot(uid)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Inactive reminder error for {uid}: {e}")
        except Exception as e:
            logger.error(f"Inactive reminder loop error: {e}")

def broadcast_timeout_watcher():
    while True:
        time.sleep(15)
        try:
            with broadcast_lock:
                if broadcast_mode and broadcast_started_at and (time.time() - broadcast_started_at > BROADCAST_TIMEOUT):
                    chat_to_notify = broadcast_admin_chat
                    set_broadcast_mode(False)
                    if chat_to_notify:
                        try:
                            bot.send_message(chat_to_notify, "⏱️ حالت پخش همگانی به دلیل عدم استفاده، به‌صورت خودکار لغو شد.")
                        except:
                            pass
        except Exception as e:
            logger.error(f"Broadcast watcher error: {e}")

def periodic_cleanup():
    while True:
        time.sleep(300)
        now = time.time()
        # پاک‌سازی anon_rate_vip (VIP)
        for key in list(anon_rate_vip.keys()):
            while anon_rate_vip[key] and anon_rate_vip[key][0] < now - 120:
                anon_rate_vip[key].popleft()
            if not anon_rate_vip[key]:
                del anon_rate_vip[key]
        # پاک‌سازی anon_daily_normal (کاربران عادی — نگه‌داری ۲۵ ساعت)
        for uid in list(anon_daily_normal.keys()):
            while anon_daily_normal[uid] and anon_daily_normal[uid][0] < now - 90000:
                anon_daily_normal[uid].popleft()
            if not anon_daily_normal[uid]:
                del anon_daily_normal[uid]
        for uid in list(click_rate.keys()):
            while click_rate[uid] and click_rate[uid][0] < now - 120:
                click_rate[uid].popleft()
            if not click_rate[uid]:
                del click_rate[uid]
        # پاک‌سازی gift_attempt_rate – حذف تلاش‌های قدیمی‌تر از ۲ ساعت
        for uid in list(gift_attempt_rate.keys()):
            while gift_attempt_rate[uid] and gift_attempt_rate[uid][0] < now - 7200:
                gift_attempt_rate[uid].popleft()
            if not gift_attempt_rate[uid]:
                del gift_attempt_rate[uid]

threading.Thread(target=periodic_cleanup, daemon=True).start()
threading.Thread(target=clean_logs_periodically, daemon=True).start()
threading.Thread(target=remind_vip_expiry, daemon=True).start()
threading.Thread(target=broadcast_timeout_watcher, daemon=True).start()
threading.Thread(target=daily_report_loop, daemon=True).start()
threading.Thread(target=remind_inactive_users, daemon=True).start()

# BOT_START_TIME در ابتدای اجرای main تعریف می‌شود؛ اینجا fallback می‌گذاریم تا uptime_str خراب نشود
BOT_START_TIME = time.time()
def uptime_str():
    seconds = int(time.time() - BOT_START_TIME)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    return f"{to_persian_digits(days)} روز و {to_persian_digits(hours)} ساعت و {to_persian_digits(minutes)} دقیقه"
# ====== وب‌سرور Health برای Railway ======
# Railway به healthcheck HTTP نیاز دارد؛ polling نیازی به پورت ندارد، پس یک سرور
# بسیار سبک (فقط کتابخانه استاندارد) در thread جدا بالا می‌آید.
from http.server import BaseHTTPRequestHandler, HTTPServer

HEALTH_PORT = int(os.environ.get("PORT", "8080"))

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # هر مسیری (از جمله /healthz که در railway.toml ست شده) 200 برمی‌گرداند
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args):
        pass  # لاگ هر ping را خاموش نگه می‌داریم

def start_health_server():
    try:
        server = HTTPServer(("0.0.0.0", HEALTH_PORT), _HealthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"✅ Health server روی پورت {HEALTH_PORT} فعال شد.")
    except OSError as e:
        print(f"⚠️ Health server راه نیفتاد: {e}")

# ====== اجرا ======
if __name__ == "__main__":
    print(f"🚀 ربات @{BOT_USERNAME} راه‌اندازی شد.")
    BOT_START_TIME = time.time()
    start_health_server()
    # رفع باگ: حلقه retry برای infinity_polling
    # اگر polling به دلیل خطا (مثل 403 permission_denied) کرش کرد، خودکار restart شود
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"Polling crashed, restarting in 5s: {e}")
            time.sleep(5)