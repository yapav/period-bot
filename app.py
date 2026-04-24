import os
import json
import random
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import anthropic
import schedule
from flask import Flask, abort, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (ApiClient, Configuration, MessagingApi,
                                   PushMessageRequest, ReplyMessageRequest,
                                   TextMessage)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ADMIN_LINE_USER_ID = os.environ.get("ADMIN_LINE_USER_ID", "")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EARLY_ACCESS_UNTIL = "2025-05-31"
EARLY_BIRD_UNTIL = "2025-05-31"
EARLY_BIRD_PRICE = 149
NORMAL_PRICE = 189

def get_current_price():
    today = datetime.now().strftime("%Y-%m-%d")
    if today <= EARLY_BIRD_UNTIL:
        return EARLY_BIRD_PRICE, True
    return NORMAL_PRICE, False


PERIOD_DAY1_QUOTES = [
    "อุ๊ย มาแล้วนะ 🩸 ปวดท้องมั้ยคะ? ถ้ามีช็อกโกแลตอุ่นๆให้ดื่มคงดีเนอะ 🍫",
    "มาแล้วววว สู้ๆนะ! 💪 วันนี้ใจดีกับตัวเองด้วยนะ พักเยอะๆได้เลย",
    "เมนส์มาเยือนแล้ว ไหวรึเปล่าคะ? 🌸 ถ้าปวดท้องให้กินยาได้เลยนะ ไม่ต้องฝืน",
    "โอ้โห มาแล้ว! อยู่ดีๆมั้ยคะ? 💙 จำไว้นะว่าความรู้สึกวันนี้มันเป็นแค่ชั่วคราว",
    "มาแล้วนะ 🫶 วันนี้อนุญาตตัวเองให้เอาใจใส่ตัวเองเป็นพิเศษเลยนะ",
    "เมนส์มาแล้ว! ร่างกายเราทำงานหนักมากเลยนะ 🌺 ขอบคุณร่างกายด้วยนะ",
    "มาแล้วววว 🩸 วันนี้ถ้าอยากนอนพักเยอะๆก็ได้เลยนะ ไม่ต้องรู้สึกผิด!",
    "อ้าวมาแล้ว! อบอุ่นท้องด้วยกระเป๋าน้ำร้อนได้เลยนะ 🔥 ช่วยได้มากเลย",
]

# ==============================
# CYCLE PHASE
# ==============================

def get_cycle_phase(day_of_cycle, cycle_length=28):
    if day_of_cycle <= 5:
        return "menstrual", {
            "name": "🩸 เฟสเมนส์ (Menstrual Phase)",
            "body": "ฮอร์โมนต่ำทุกตัว ร่างกายปล่อยเยื่อบุมดลูก",
            "skin": "ผิวอาจแห้งและแพ้ง่ายขึ้น ลองใช้ skincare อ่อนโยนหน่อยนะ",
            "mood": "อาจรู้สึกเหนื่อย อยากพัก หรือเก็บตัว นั่นเป็นเรื่องปกติมากๆ",
            "tips": "พักเยอะๆ กินอาหารที่มีธาตุเหล็ก เช่น ผักใบเขียว เนื้อแดง",
            "emoji": "🌙"
        }
    ovulation_day = cycle_length // 2
    if day_of_cycle <= ovulation_day - 1:
        return "follicular", {
            "name": "🌱 เฟสฟอลลิคูลาร์ (Follicular Phase)",
            "body": "ฮอร์โมน estrogen เริ่มสูงขึ้น ร่างกายเตรียมไข่",
            "skin": "ผิวจะดูดีขึ้นเรื่อยๆ เปล่งปลั่งขึ้น คอลลาเจนผลิตได้ดี ✨",
            "mood": "พลังงานสูงขึ้น อารมณ์ดี มีแรงบันดาลใจ เหมาะมากกับการเริ่มโปรเจกต์ใหม่!",
            "tips": "ช่วงนี้เหมาะกับการออกกำลังกายหนัก เรียนรู้สิ่งใหม่ หรือ social เยอะๆ",
            "emoji": "🌱"
        }
    if ovulation_day - 1 <= day_of_cycle <= ovulation_day + 1:
        return "ovulation", {
            "name": "✨ เฟสไข่ตก (Ovulation Phase)",
            "body": "ฮอร์โมน LH พุ่งสูง ไข่ถูกปล่อยออกมา",
            "skin": "นี่คือช่วงที่หน้าสวยที่สุดในรอบ! 💫 ผิวเปล่งปลั่ง หน้าดูมีชีวิตชีวา",
            "mood": "พลังงานสูงสุด มั่นใจ เข้าสังคมได้ดีมาก เหมาะกับการออกไปเจอคน",
            "tips": "ช่วงนี้เหมาะกับนัดสำคัญ การนำเสนองาน หรือออกเดต!",
            "emoji": "💫"
        }
    days_before_period = cycle_length - day_of_cycle
    if days_before_period > 7:
        return "luteal_early", {
            "name": "🍂 เฟสลูทีล ช่วงแรก (Early Luteal)",
            "body": "Progesterone เริ่มสูงขึ้น ร่างกายเตรียมรองรับการตั้งครรภ์",
            "skin": "ผิวอาจมันขึ้นนิดหน่อย อาจเริ่มมีสิวเล็กน้อย",
            "mood": "ยังรู้สึกดีอยู่ แต่อาจเริ่มอยากอาหารมากขึ้น",
            "tips": "ดูแลผิวให้ดีขึ้น ลดน้ำตาลและอาหารมันๆ จะช่วยเรื่องสิวได้",
            "emoji": "🍂"
        }
    return "pms", {
        "name": "⚡ เฟส PMS (Pre-Menstrual Phase)",
        "body": "ฮอร์โมนลดฮวบ ร่างกายกำลังเตรียมเริ่มรอบใหม่",
        "skin": "ผิวแพ้ง่าย อาจบวมเล็กน้อย และสิวอาจขึ้นได้ง่าย",
        "mood": "อาจรู้สึกหงุดหงิด เครียด หดหู่ หรืออ่อนไหวได้ง่าย — นั่นไม่ใช่ความผิดของเรานะ มันคือฮอร์โมน! 💙",
        "tips": "ลดคาเฟอีนและเกลือ เพิ่มแมกนีเซียม (ช็อกโกแลตดำ กล้วย) และพักผ่อนให้พอ",
        "emoji": "⚡"
    }

# ==============================
# DATABASE
# ==============================

def get_db():
    conn = sqlite3.connect("period_bot.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        display_name TEXT,
        mode TEXT DEFAULT 'self',
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT,
        created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS periods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, start_date TEXT, end_date TEXT, notes TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, log_date TEXT, flow_level TEXT, symptoms TEXT,
        UNIQUE(user_id, log_date))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, role TEXT, content TEXT, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS feature_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, feature TEXT, used_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT, package TEXT, amount INTEGER,
        status TEXT DEFAULT 'pending', created_at TEXT)""")
    conn.commit()
    conn.close()

init_db()

# ==============================
# FREEMIUM
# ==============================

def is_early_access():
    return datetime.now().strftime("%Y-%m-%d") <= EARLY_ACCESS_UNTIL

def check_premium(user_id):
    if is_early_access():
        return True
    conn = get_db()
    user = conn.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if not user or not user["is_premium"]:
        return False
    return True  # one-time payment ไม่มีวันหมดอายุ

def get_monthly_usage(user_id, feature):
    conn = get_db()
    month_start = datetime.now().strftime("%Y-%m-01")
    count = conn.execute("""
        SELECT COUNT(*) as cnt FROM feature_logs
        WHERE user_id = ? AND feature = ? AND used_at >= ?
    """, (user_id, feature, month_start)).fetchone()["cnt"]
    conn.close()
    return count

def log_feature(user_id, feature):
    conn = get_db()
    conn.execute("INSERT INTO feature_logs (user_id, feature, used_at) VALUES (?, ?, ?)",
                 (user_id, feature, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def check_and_use_feature(user_id, feature):
    if check_premium(user_id):
        log_feature(user_id, feature)
        return True
    usage = get_monthly_usage(user_id, feature)
    if usage < 1:
        log_feature(user_id, feature)
        return True
    return False

def get_upsell_message():
    return """เดือนนี้ใช้ฟรีไปแล้วนะคะ 🌸

อัพเกรด premium จะได้เพิ่มเลย
🧬 เช็คเฟสฮอร์โมนได้ไม่อั้น
📅 ดูปฏิทินย้อนหลัง 6 รอบ
🥚 แจ้งเตือนวันไข่ตกอัตโนมัติ
⚡ แจ้งเตือน PMS ล่วงหน้า
🌸 แจ้งเตือนพกผ้าอนามัย

ไม่ผูกมัดนะคะ จะหยุดเดือนไหนก็ได้เลย 💙
สนใจมั้ยคะ? พิมพ์ "อยากอัพเกรด" ได้เลยนะ"""

# ==============================
# DB HELPERS
# ==============================

def upsert_user(user_id, display_name=""):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (user_id, display_name, created_at) VALUES (?, ?, ?)",
                 (user_id, display_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_mode(user_id):
    conn = get_db()
    user = conn.execute("SELECT mode FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return user["mode"] if user else "self"

def get_latest_period(user_id):
    conn = get_db()
    p = conn.execute("SELECT * FROM periods WHERE user_id = ? ORDER BY start_date DESC LIMIT 1", (user_id,)).fetchone()
    conn.close()
    return p

def get_all_periods(user_id, limit=12):
    conn = get_db()
    rows = conn.execute("SELECT * FROM periods WHERE user_id = ? ORDER BY start_date DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return rows

def start_new_period(user_id, start_date=None):
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")
    # validate date format
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        start_date = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute("UPDATE periods SET end_date = ? WHERE user_id = ? AND end_date IS NULL", (start_date, user_id))
    conn.execute("INSERT INTO periods (user_id, start_date) VALUES (?, ?)", (user_id, start_date))
    conn.commit()
    conn.close()
    return start_date

def end_period(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    p = conn.execute("SELECT * FROM periods WHERE user_id = ? AND end_date IS NULL ORDER BY start_date DESC LIMIT 1", (user_id,)).fetchone()
    if p:
        conn.execute("UPDATE periods SET end_date = ? WHERE id = ?", (today, p["id"]))
        conn.commit()
    conn.close()
    return p

def log_daily(user_id, flow_level, symptoms=""):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO daily_logs (user_id, log_date, flow_level, symptoms) VALUES (?, ?, ?, ?)",
                 (user_id, today, flow_level, symptoms))
    conn.commit()
    conn.close()

def get_chat_history(user_id, limit=8):
    conn = get_db()
    rows = conn.execute("SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                        (user_id, limit)).fetchall()
    conn.close()
    return list(reversed(rows))

def save_chat(user_id, role, content):
    conn = get_db()
    conn.execute("INSERT INTO chat_history (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                 (user_id, role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def calculate_avg_cycle(user_id):
    periods = get_all_periods(user_id)
    if len(periods) < 2:
        return 28
    cycles = []
    for i in range(len(periods) - 1):
        d1 = datetime.strptime(periods[i]["start_date"], "%Y-%m-%d")
        d2 = datetime.strptime(periods[i+1]["start_date"], "%Y-%m-%d")
        diff = (d1 - d2).days
        if 20 <= diff <= 45:
            cycles.append(diff)
    return round(sum(cycles) / len(cycles)) if cycles else 28

def predict_next_period(user_id):
    latest = get_latest_period(user_id)
    if not latest:
        return None
    avg = calculate_avg_cycle(user_id)
    start = datetime.strptime(latest["start_date"], "%Y-%m-%d")
    return start + timedelta(days=avg)

def get_cycle_timing_message(user_id):
    periods = get_all_periods(user_id)
    if len(periods) < 2:
        return None
    avg = calculate_avg_cycle(user_id)
    d_latest = datetime.strptime(periods[0]["start_date"], "%Y-%m-%d")
    d_prev = datetime.strptime(periods[1]["start_date"], "%Y-%m-%d")
    actual_gap = (d_latest - d_prev).days
    diff = actual_gap - avg
    if abs(diff) <= 2:
        return f"⏱ รอบนี้มาตรงเวลามากเลยนะ! (มาห่าง {actual_gap} วัน รอบเฉลี่ย {avg} วัน) 🎯"
    elif diff < 0:
        return f"⚡ รอบนี้มาเร็วกว่าปกติ {abs(diff)} วันนะ\nอาจเกิดจากความเครียด การนอนน้อย หรือออกกำลังกายหนัก 💙"
    else:
        return f"🐢 รอบนี้มาช้ากว่าปกติ {diff} วันนะ\nมีหลายสาเหตุที่ทำให้มาช้าได้ ไม่ต้องกังวลมากนะ 🌸"

def get_ovulation_date(user_id):
    latest = get_latest_period(user_id)
    if not latest:
        return None
    avg = calculate_avg_cycle(user_id)
    start = datetime.strptime(latest["start_date"], "%Y-%m-%d")
    return start + timedelta(days=avg - 14)

def get_current_phase_info(user_id):
    latest = get_latest_period(user_id)
    if not latest:
        return None
    avg = calculate_avg_cycle(user_id)
    start = datetime.strptime(latest["start_date"], "%Y-%m-%d")
    day_of_cycle = (datetime.now() - start).days + 1
    if day_of_cycle < 1 or day_of_cycle > avg + 7:
        return None
    phase, info = get_cycle_phase(day_of_cycle, avg)
    return phase, info, day_of_cycle

def build_calendar_text(user_id):
    limit = 6 if check_premium(user_id) else 1
    periods = get_all_periods(user_id, limit=limit)
    if not periods:
        return "ยังไม่มีข้อมูลรอบเดือนเลยนะ บันทึกรอบแรกได้เลย แค่บอกว่า 'เมนส์มาแล้ว' 🌸"
    avg = calculate_avg_cycle(user_id)
    lines = [f"📅 ปฏิทินรอบเดือนของเรา\nรอบเฉลี่ย: {avg} วัน\n─────────────────"]
    for i, p in enumerate(periods):
        start = datetime.strptime(p["start_date"], "%Y-%m-%d")
        if p["end_date"]:
            end = datetime.strptime(p["end_date"], "%Y-%m-%d")
            duration = (end - start).days + 1
            end_str = end.strftime("%d %b")
            dur_str = f"({duration} วัน)"
        else:
            end_str = "ปัจจุบัน"
            dur_str = "(ยังอยู่ในรอบนี้)"
        if i < len(periods) - 1:
            prev_start = datetime.strptime(periods[i+1]["start_date"], "%Y-%m-%d")
            gap = (start - prev_start).days
            gap_str = f"\n   ← ห่างจากรอบก่อน {gap} วัน"
        else:
            gap_str = ""
        label = "🔴 ล่าสุด" if i == 0 else f"รอบที่ -{i}"
        lines.append(f"\n{label}\n🗓 {start.strftime('%d %b %Y')} – {end_str} {dur_str}{gap_str}")
    next_date = predict_next_period(user_id)
    if next_date:
        days_left = (next_date - datetime.now()).days
        lines.append("\n─────────────────")
        if days_left > 0:
            lines.append(f"🔮 รอบถัดไปประมาณ: {next_date.strftime('%d %b %Y')}\n   (อีก {days_left} วัน)")
        elif days_left == 0:
            lines.append("🔮 รอบถัดไป: วันนี้เลย!")
        else:
            lines.append(f"🔮 ผ่านกำหนดมาแล้ว {abs(days_left)} วัน\n   ถ้ามาแล้วบอกพี่สาวด้วยนะ!")
    return "\n".join(lines)

# ==============================
# ADMIN
# ==============================

def get_stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    premium = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_premium = 1").fetchone()["cnt"]
    month_start = datetime.now().strftime("%Y-%m-01")
    features = conn.execute("""
        SELECT feature, COUNT(*) as cnt FROM feature_logs
        WHERE used_at >= ? GROUP BY feature ORDER BY cnt DESC
    """, (month_start,)).fetchall()
    pending = conn.execute("SELECT COUNT(*) as cnt FROM payment_requests WHERE status = 'pending'").fetchone()["cnt"]
    conn.close()
    lines = [f"📊 Stats เดือนนี้\n─────────────────",
             f"👥 Users: {total}", f"⭐ Premium: {premium}",
             f"💰 รอ approve: {pending} คน\n", "🔥 ฟีเจอร์ที่ใช้เยอะสุด:"]
    for row in features:
        lines.append(f"   {row['feature']}: {row['cnt']} ครั้ง")
    return "\n".join(lines)

def approve_premium(user_id):
    conn = get_db()
    conn.execute("UPDATE users SET is_premium = 1, premium_until = NULL WHERE user_id = ?", (user_id,))
    conn.execute("UPDATE payment_requests SET status = 'approved' WHERE user_id = ? AND status = 'pending'", (user_id,))
    conn.commit()
    conn.close()

def notify_admin(message):
    if ADMIN_LINE_USER_ID:
        send_push_message(ADMIN_LINE_USER_ID, message)

# ==============================
# CLAUDE AI
# ==============================

SYSTEM_PROMPT_SELF = f"""คุณคือ "พี่สาว" แชทบอทผู้ช่วยติดตามรอบเดือนที่ดูแลและห่วงใยผู้ใช้เหมือนพี่สาวคนจริงๆ
พูดคุยเป็นกันเองแบบพี่สาวที่ห่วงใย ใช้ภาษาไทยน่ารักๆ ไม่เป็นทางการ อบอุ่น และเอาใจใส่

คำสั่งพิเศษ (return เฉพาะ JSON เท่านั้น ห้ามมี ```json หรือข้อความอื่น):
- บอกว่าเมนส์มาแล้ว / มาแล้ว / มาวันนี้ → {{{{"action": "start_period", "date": "YYYY-MM-DD"}}}}
  date คือวันแรกที่เมนส์มา ให้คำนวณในหัวแล้วใส่เป็นตัวเลขจริงๆ เช่น "2025-04-23" ห้าม return code หรือ expression เด็ดขาด
  ตัวอย่างการคำนวณ (สมมติวันนี้คือ 2025-04-25):
  - "มาวันนี้" → "2025-04-25"
  - "มาเมื่อวาน" → "2025-04-24"
  - "มาสองวันแล้ว" → "2025-04-23"
  - "วันนี้เป็นวันที่ 2" → วันแรกคือเมื่อวาน → "2025-04-24"
  - "วันนี้เป็นวันที่ 3" → วันแรกคือ 2 วันก่อน → "2025-04-23"
  - "เมื่อวานเป็นวันที่ 2" → วันแรกคือ 2 วันก่อน → "2025-04-23"
  - "มาตั้งแต่วันที่ 20" → "2025-04-20"
  คำนวณเองในหัว แล้ว return วันที่จริงเป็น string YYYY-MM-DD เท่านั้น ห้าม return code
- บอกว่าหยุดแล้ว / หมดแล้ว / เมนส์หมด → {{"action": "end_period"}}
- บอกปริมาณเลือดชัดเจน เช่น มาเยอะ / มาน้อย / มาปานกลาง → {{"action": "log_flow", "level": "มาก/น้อย/ปานกลาง"}}
- ถ้าคำตอบเรื่องปริมาณไม่ชัดเจน เช่น "ไม่เยอะมาก" "นิดหน่อย" "พอใช้" "ไม่แน่ใจ" → {{"action": "ask_flow"}}
- ถามรอบถัดไป / ครั้งหน้าเมื่อไหร่ → {{"action": "predict"}}
- ขอดูปฏิทิน / ดูประวัติ / รอบที่ผ่านมา → {{"action": "calendar"}}
- ถามเฟส / ฮอร์โมน / ตอนนี้อยู่เฟสไหน / ผิวช่วงนี้ → {{"action": "phase"}}
- อยากอัพเกรด / สมัคร premium / ราคา → {{"action": "upgrade"}}
- สนทนาทั่วไป → ตอบปกติ ไม่ต้องมี JSON

ตอบสั้นกระชับไม่เกิน 3-4 ประโยค อบอุ่น น่ารัก
วันนี้คือ {datetime.now().strftime("%Y-%m-%d")}"""

SYSTEM_PROMPT_BF = f"""คุณคือ "พี่สาว" แชทบอทช่วยผู้ชายดูแลแฟนสาวในช่วงรอบเดือน
พูดคุยเป็นกันเองแบบเพื่อนที่ให้คำแนะนำ ใช้ภาษาไทยเป็นกันเอง อบอุ่น ไม่ทางการ

คำสั่งพิเศษ (return เฉพาะ JSON เท่านั้น ห้ามมี ```json หรือข้อความอื่น):
- บอกว่าแฟนเมนส์มาแล้ว → {{{{"action": "start_period", "date": "YYYY-MM-DD"}}}}
  date คือวันแรกที่เมนส์มา ให้คำนวณในหัวแล้วใส่เป็นตัวเลขจริงๆ เช่น "2025-04-23" ห้าม return code หรือ expression เด็ดขาด
  ตัวอย่างการคำนวณ (สมมติวันนี้คือ 2025-04-25):
  - "มาวันนี้" → "2025-04-25"
  - "มาเมื่อวาน" → "2025-04-24"
  - "มาสองวันแล้ว" → "2025-04-23"
  - "วันนี้เป็นวันที่ 2" → วันแรกคือเมื่อวาน → "2025-04-24"
  - "วันนี้เป็นวันที่ 3" → วันแรกคือ 2 วันก่อน → "2025-04-23"
  - "เมื่อวานเป็นวันที่ 2" → วันแรกคือ 2 วันก่อน → "2025-04-23"
  - "มาตั้งแต่วันที่ 20" → "2025-04-20"
  คำนวณเองในหัว แล้ว return วันที่จริงเป็น string YYYY-MM-DD เท่านั้น ห้าม return code
- บอกว่าแฟนเมนส์หมดแล้ว → {{"action": "end_period"}}
- บอกปริมาณเลือดแฟนชัดเจน → {{"action": "log_flow", "level": "มาก/น้อย/ปานกลาง"}}
- ถ้าคำตอบไม่ชัด → {{"action": "ask_flow"}}
- ถามรอบถัดไปของแฟน → {{"action": "predict"}}
- ขอดูปฏิทินแฟน → {{"action": "calendar"}}
- ถามเฟสของแฟน → {{"action": "phase"}}
- อยากอัพเกรด → {{"action": "upgrade"}}
- สนทนาทั่วไป → ตอบปกติ ไม่ต้องมี JSON

ตอบสั้นกระชับ ให้คำแนะนำเรื่องการดูแลแฟนในแต่ละช่วง
วันนี้คือ {datetime.now().strftime("%Y-%m-%d")}"""

def chat_with_claude(user_id, user_message):
    history = get_chat_history(user_id)
    messages = [{"role": r["role"], "content": r["content"]} for r in history]
    messages.append({"role": "user", "content": user_message})
    mode = get_user_mode(user_id)
    system = SYSTEM_PROMPT_BF if mode == "boyfriend" else SYSTEM_PROMPT_SELF
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=system,
        messages=messages
    )
    reply = response.content[0].text
    save_chat(user_id, "user", user_message)
    save_chat(user_id, "assistant", reply)
    return reply

def process_claude_response(user_id, response_text):
    mode = get_user_mode(user_id)
    is_bf = mode == "boyfriend"

    try:
        clean = response_text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        action = data.get("action")

        if action == "start_period":
            # ดึงวันที่จาก Claude ถ้ามี
            period_date = data.get("date", None)
            actual_date = start_new_period(user_id, period_date)
            avg = calculate_avg_cycle(user_id)
            timing_msg = get_cycle_timing_message(user_id)

            # แสดงวันที่ถ้าเป็นการบันทึกย้อนหลัง
            today = datetime.now().strftime("%Y-%m-%d")
            date_note = ""
            if actual_date != today:
                d = datetime.strptime(actual_date, "%Y-%m-%d")
                date_note = f" (บันทึกย้อนหลังวันที่ {d.strftime('%d/%m/%Y')})"

            if is_bf:
                reply = f"บันทึกแล้วนะ! 🩸 แฟนเริ่มรอบเดือนแล้ว{date_note}\n"
                if timing_msg:
                    reply += f"\n{timing_msg}\n"
                reply += "\nวันนี้แฟนเป็นยังไงบ้าง? ปวดท้องมั้ย? ลองถามเขาดูนะ 💙"
            else:
                quote = random.choice(PERIOD_DAY1_QUOTES)
                reply = f"{quote}\n\nบันทึกแล้วนะ! 🩸{date_note}\n"
                if timing_msg:
                    reply += f"\n{timing_msg}\n"
                reply += f"\nรอบเฉลี่ยของเรา: {avg} วัน\nวันนี้มาเยอะหรือน้อยคะ? 💙"
            return reply

        elif action == "end_period":
            period = end_period(user_id)
            if period:
                start = datetime.strptime(period["start_date"], "%Y-%m-%d")
                days = (datetime.now() - start).days + 1
                next_date = predict_next_period(user_id)
                next_str = next_date.strftime("%d/%m/%Y") if next_date else "ยังคำนวณไม่ได้"
                days_left = (next_date - datetime.now()).days if next_date else None
                if is_bf:
                    reply = f"บันทึกแล้วนะ! รอบนี้แฟนมา {days} วัน\nรอบหน้าน่าจะประมาณ {next_str}"
                    if days_left and days_left > 0:
                        reply += f" (อีก {days_left} วัน)"
                    reply += "\n\nช่วงนี้แฟนน่าจะรู้สึกดีขึ้นแล้วนะ ดูแลเขาต่อด้วยนะ 💙"
                else:
                    reply = f"บันทึกแล้วนะ ✨ รอบนี้มา {days} วัน\nรอบหน้าน่าจะประมาณ {next_str}"
                    if days_left and days_left > 0:
                        reply += f" (อีก {days_left} วัน)"
                    reply += "\n\nพักผ่อนให้เต็มที่นะ ร่างกายทำงานหนักมากเลย 🌸"
                return reply
            return "ยังไม่ได้บันทึกว่าเมนส์มาเลยนะ บอกด้วยนะถ้าเมนส์มา! 🌸"

        elif action == "log_flow":
            level = data.get("level", "ปานกลาง")
            log_daily(user_id, level)
            if is_bf:
                tips = {
                    "มาก": "💧 แฟนมาเยอะนะ ลองเอาช็อกโกแลตอุ่นๆหรือน้ำร้อนให้เขาดูนะ เขาจะรู้สึกดีขึ้นเลย 🍫",
                    "น้อย": "✨ มาน้อยดีเลย แฟนน่าจะโอเคนะ ถามว่าต้องการอะไรมั้ยด้วยนะ",
                    "ปานกลาง": "🌸 ปกติดี อย่าลืมถามแฟนว่าต้องการอะไรมั้ยนะ"
                }
            else:
                tips = {
                    "มาก": "💧 มาเยอะนะ ดื่มน้ำเยอะๆด้วย และเปลี่ยนผ้าอนามัยทุก 3-4 ชั่วโมงนะ",
                    "น้อย": "✨ มาน้อยดีเลย! ใส่แผ่นเล็กก็พอนะ",
                    "ปานกลาง": "🌸 โอเคนะ! เปลี่ยนผ้าอนามัยทุก 4-6 ชั่วโมงด้วยนะ"
                }
            return f"บันทึกแล้วว่าวันนี้ {level} นะ!\n{tips.get(level, '')}"

        elif action == "ask_flow":
            if is_bf:
                return "แฟนมาเยอะแค่ไหนคะ? 😊\n🔴 มาเยอะ — ต้องเปลี่ยนผ้าอนามัยบ่อย\n🟡 มาปานกลาง — ปกติดี\n🟢 มาน้อย — แผ่นเล็กก็พอ"
            else:
                return "มาเยอะแค่ไหนคะ? 😊\n🔴 มาเยอะ — ต้องเปลี่ยนบ่อย\n🟡 มาปานกลาง — ปกติดี\n🟢 มาน้อย — แผ่นเล็กก็พอ"

        elif action == "predict":
            next_date = predict_next_period(user_id)
            ovulation = get_ovulation_date(user_id)
            if next_date:
                days_left = (next_date - datetime.now()).days
                prefix = "รอบถัดไปของแฟนคาดว่าจะมาประมาณ" if is_bf else "รอบถัดไปคาดว่าจะมาประมาณ"
                reply = f"🔮 {prefix} {next_date.strftime('%d/%m/%Y')}"
                if days_left > 0:
                    reply += f"\n(อีกประมาณ {days_left} วัน)"
                elif days_left == 0:
                    reply += "\n(วันนี้เลย! เตรียมตัวได้เลยนะ)"
                else:
                    reply += f"\n(เลยกำหนดมา {abs(days_left)} วันแล้ว)"
                if ovulation and check_premium(user_id):
                    reply += f"\n\n🥚 ไข่น่าจะตกประมาณ {ovulation.strftime('%d/%m/%Y')} นะ"
                return reply
            return "ยังไม่มีข้อมูลพอนะ บันทึกสัก 2 รอบก่อน จะได้คำนวณแม่นขึ้น! 💪"

        elif action == "calendar":
            if check_and_use_feature(user_id, "calendar"):
                return build_calendar_text(user_id)
            return get_upsell_message()

        elif action == "phase":
            if check_and_use_feature(user_id, "phase"):
                result = get_current_phase_info(user_id)
                if not result:
                    return "ยังไม่มีข้อมูลรอบเดือนเลยนะ บอกว่า 'เมนส์มาแล้ว' เพื่อเริ่มบันทึกได้เลย 🌸"
                phase, info, day = result
                if is_bf:
                    return (
                        f"{info['emoji']} แฟนตอนนี้อยู่วันที่ {day} ของรอบ\n"
                        f"{info['name']}\n\n"
                        f"💭 อารมณ์แฟน: {info['mood']}\n\n"
                        f"💡 วิธีดูแลแฟนช่วงนี้: {info['tips']}"
                    )
                return (
                    f"{info['emoji']} ตอนนี้อยู่วันที่ {day} ของรอบ\n"
                    f"{info['name']}\n\n"
                    f"🧬 ฮอร์โมน: {info['body']}\n\n"
                    f"✨ ผิว: {info['skin']}\n\n"
                    f"💭 อารมณ์: {info['mood']}\n\n"
                    f"💡 Tips: {info['tips']}"
                )
            return get_upsell_message()

        elif action == "upgrade":
            price, is_early = get_current_price()
            if is_early:
                return (
                    "ยินดีเลยนะคะ! 🎉\n\n"
                    f"Early Bird — unlock ตลอดชีพแค่ {price} บาท 🎊\n"
                    f"(ราคาปกติ {NORMAL_PRICE} บาท หมดเขต 31 พ.ค. นี้เท่านั้น)\n\n"
                    "จ่ายครั้งเดียว ใช้ได้ตลอด ไม่มีรายเดือนนะคะ 🌸\n"
                    "สนใจพิมพ์ 'จ่ายเลย' ได้เลยนะคะ 💙"
                )
            else:
                return (
                    "ยินดีเลยนะคะ! 🎉\n\n"
                    f"Unlock พี่สาว ตลอดชีพแค่ {price} บาท ✨\n"
                    "จ่ายครั้งเดียว ใช้ได้ตลอด ไม่มีรายเดือนนะคะ 🌸\n"
                    "สนใจพิมพ์ 'จ่ายเลย' ได้เลยนะคะ 💙"
                )

    except (json.JSONDecodeError, ValueError):
        pass

    # เช็คว่าพิมพ์จ่ายเลยมั้ย
    if response_text.strip() in ["จ่ายเลย", "สนใจ", "อยากจ่าย", "จ่าย"]:
        price, is_early = get_current_price()
        conn = get_db()
        conn.execute("INSERT INTO payment_requests (user_id, package, amount, created_at) VALUES (?, ?, ?, ?)",
                     (user_id, "one-time", price, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        early_label = " (Early Bird)" if is_early else ""
        notify_admin(
            f"💰 มีคนอยากอัพเกรด!\n"
            f"User: {user_id}\n"
            f"แพคเกจ: One-time{early_label}\n"
            f"ยอด: {price} บาท\n"
            f"approve: /approve {user_id}"
        )
        return (
            f"โอนมาที่ PromptPay: กรุงไทย 6629282752 ชื่อบัญชี ญาภา\n"
            f"ยอด: {price} บาท{early_label}\n\n"
            f"แล้วส่งสลิปมาในแชทนี้ได้เลยนะคะ 💙\n"
            f"พี่สาวจะ unlock ให้ภายใน 24 ชั่วโมงนะคะ"
        )

    # ถ้า response มี JSON หลุดออกมา ให้ลอง parse ก่อน
    import re
    json_match = re.search(r'\{[^{}]+\}', response_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if data.get("action"):
                # มี action JSON หลุดมา ลอง process อีกรอบ
                cleaned = json_match.group()
                return process_claude_response(user_id, cleaned)
        except:
            pass
    return response_text

# ==============================
# LINE WEBHOOK
# ==============================

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

WELCOME_MESSAGE = """สวัสดีนะคะ! พี่สาวยินดีต้อนรับเลย 🌸

จะดีกว่ามั้ยถ้ามีพี่สาวใจดีคอยดูแล
เรื่องประจำเดือนให้ทุกเดือนเลย? 💙

🩸 บันทึกรอบเดือน + วิเคราะห์ว่ามาเร็ว/ช้ากว่าปกติ
📅 แจ้งเตือนล่วงหน้าก่อนรอบถัดไป
🗓 ดูประวัติรอบเดือนย้อนหลังสูงสุด 6 เดือน
🧬 เช็คเฟสฮอร์โมนรายวัน
🌸 แจ้งเตือนให้พกผ้าอนามัย
🥚 แจ้งเตือนวันไข่ตก
💑 โหมดแฟน — ให้แฟนดูแลเราได้ด้วย

เดือนพฤษภาคมนี้ใช้ได้ฟรีทุกฟีเจอร์เลยนะคะ 🎉
หลังจากนั้น unlock ตลอดชีพแค่ 149 บาท
(ราคา early bird หมดเขต 31 พ.ค. นี้เท่านั้น)

ก่อนเริ่มขอถามหน่อยนะคะ
ใช้สำหรับใครคะ?
1️⃣ ตัวเอง
2️⃣ แฟนสาว (โหมดแฟน)

พิมพ์ 1 หรือ 2 ได้เลยนะคะ 💙"""

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    upsert_user(user_id)
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=WELCOME_MESSAGE)]
            )
        )

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text.strip()
    upsert_user(user_id)

    # Admin commands
    if user_id == ADMIN_LINE_USER_ID:
        if user_message.startswith("/approve "):
            parts = user_message.split()
            if len(parts) >= 2:
                target_user = parts[1]
                approve_premium(target_user)
                send_push_message(target_user,
                    "🎉 Unlock สำเร็จแล้วนะคะ!\n"
                    "ใช้ได้ตลอดชีพเลยนะคะ ไม่มีหมดอายุ\n"
                    "ขอบคุณที่สนับสนุนพี่สาวนะคะ 💙🌸")
                reply_text = f"✅ Approved {target_user} — lifetime unlock"
            else:
                reply_text = "format: /approve [user_id]"
        elif user_message == "/stats":
            reply_text = get_stats()
        else:
            reply_text = "Admin:\n/approve [user_id]\n/stats"

        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)])
            )
        return

    # Onboarding — ตอบ 1 หรือ 2 หลังเพิ่มเพื่อนใหม่
    if user_message == "1":
        conn = get_db()
        user = conn.execute("SELECT mode FROM users WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if user and user["mode"] not in ["self", "boyfriend"]:
            conn = get_db()
            conn.execute("UPDATE users SET mode = 'self' WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            reply_text = "เยี่ยมเลยนะคะ! 🌸 พี่สาวพร้อมดูแลแล้ว\nเริ่มได้เลยนะคะ แค่บอกว่า 'เมนส์มาแล้ว' เมื่อถึงเวลา 💙"
        else:
            conn = get_db()
            conn.execute("UPDATE users SET mode = 'self' WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            reply_text = "เปลี่ยนกลับโหมดตัวเองแล้วนะคะ 🌸"
    elif user_message == "2":
        conn = get_db()
        conn.execute("UPDATE users SET mode = 'boyfriend' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        reply_text = "โหมดแฟนเปิดแล้วนะคะ! 💑\nพี่สาวจะคอยแจ้งเตือนและให้คำแนะนำในการดูแลแฟนสาวให้นะคะ\nเริ่มได้เลยนะคะ แค่บอกว่า 'แฟนเมนส์มาแล้ว' 🌸"
    # โหมดแฟน
    elif user_message in ["โหมดแฟน", "boyfriend mode", "ติดตามแฟน"]:
        conn = get_db()
        conn.execute("UPDATE users SET mode = 'boyfriend' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        reply_text = "เปิดโหมดแฟนแล้วนะคะ! 💑\nตอนนี้พี่สาวจะช่วยดูแลแฟนของคุณด้วยนะ\nบอกได้เลยว่าแฟนเมนส์มาแล้วหรือยัง 🌸"
    elif user_message in ["โหมดปกติ", "normal mode", "โหมดตัวเอง"]:
        conn = get_db()
        conn.execute("UPDATE users SET mode = 'self' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        reply_text = "เปลี่ยนกลับโหมดปกติแล้วนะคะ 🌸"
    else:
        # Rule-based shortcuts ลด Claude API cost
        msg_lower = user_message.lower().strip()

        # จ่ายเงิน
        if msg_lower in ["จ่ายเลย", "สนใจ", "อยากจ่าย", "จ่าย"]:
            reply_text = process_claude_response(user_id, msg_lower)

        # คำสั่งตรงๆ ที่ไม่ต้องผ่าน Claude
        elif any(w in user_message for w in ["เมนส์มาแล้ว", "มาแล้ว", "period มา", "มาวันนี้", "มาเมื่อวาน", "มาวันแรก", "เริ่มมาแล้ว", "เริ่มมาวัน", "มาตั้งแต่"]):
            # ถ้ามีการระบุวันที่ ส่งไปหา Claude เพื่อ extract วันที่
            date_keywords = ["วันที่", "เมื่อวาน", "วันก่อน", "สองวัน", "สามวัน", "อาทิตย์ที่"]
            has_date = any(w in user_message for w in date_keywords)
            if has_date:
                try:
                    claude_response = chat_with_claude(user_id, user_message)
                    reply_text = process_claude_response(user_id, claude_response)
                except Exception as e:
                    reply_text = "โทษทีนะ ระบบมีปัญหาชั่วคราว ลองใหม่อีกทีนะคะ 🙏"
                    print(f"Error: {e}")
            else:
                reply_text = process_claude_response(user_id, '{"action": "start_period", "date": "' + datetime.now().strftime("%Y-%m-%d") + '"}')
        elif any(w in user_message for w in ["หมดแล้ว", "หยุดแล้ว", "เมนส์หมด", "ไม่มาแล้ว"]):
            reply_text = process_claude_response(user_id, '{"action": "end_period"}')
        elif any(w in user_message for w in ["ดูปฏิทิน", "ดูประวัติ", "รอบที่ผ่านมา", "ย้อนหลัง"]):
            reply_text = process_claude_response(user_id, '{"action": "calendar"}')
        elif any(w in user_message for w in ["รอบหน้า", "ครั้งหน้า", "จะมาเมื่อไหร่", "มาเมื่อไหร่"]):
            reply_text = process_claude_response(user_id, '{"action": "predict"}')
        elif any(w in user_message for w in ["เฟสไหน", "ฮอร์โมน", "ผิวช่วงนี้", "อยู่เฟส"]):
            reply_text = process_claude_response(user_id, '{"action": "phase"}')
        elif any(w in user_message for w in ["อัพเกรด", "premium", "สมัคร", "ราคา", "จ่ายเท่าไหร่"]):
            reply_text = process_claude_response(user_id, '{"action": "upgrade"}')
        elif any(w in user_message for w in ["มาเยอะ", "มามาก"]):
            reply_text = process_claude_response(user_id, '{"action": "log_flow", "level": "มาก"}')
        elif any(w in user_message for w in ["มาน้อย", "น้อยมาก", "นิดหน่อย"]):
            reply_text = process_claude_response(user_id, '{"action": "log_flow", "level": "น้อย"}')
        elif any(w in user_message for w in ["มาปานกลาง", "ปกติ", "ปานกลาง"]):
            reply_text = process_claude_response(user_id, '{"action": "log_flow", "level": "ปานกลาง"}')

        # ถ้าไม่ตรงกับ rule ไหนเลย ค่อยส่งไปหา Claude
        else:
            try:
                claude_response = chat_with_claude(user_id, user_message)
                reply_text = process_claude_response(user_id, claude_response)
            except Exception as e:
                reply_text = "โทษทีนะ ระบบมีปัญหาชั่วคราว ลองใหม่อีกทีนะคะ 🙏"
                print(f"Error: {e}")

    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message_with_http_info(
            ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply_text)])
        )

# ==============================
# PUSH NOTIFICATIONS
# ==============================

def send_push_message(user_id, message):
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message_with_http_info(
                PushMessageRequest(to=user_id, messages=[TextMessage(text=message)])
            )
    except Exception as e:
        print(f"Push error: {e}")

def daily_check_and_notify():
    conn = get_db()
    users = conn.execute("SELECT user_id, mode FROM users").fetchall()
    conn.close()
    today = datetime.now()

    for user_row in users:
        user_id = user_row["user_id"]
        is_bf = (user_row["mode"] or "self") == "boyfriend"

        try:
            latest = get_latest_period(user_id)
            if not latest:
                continue
            avg = calculate_avg_cycle(user_id)
            start_date = datetime.strptime(latest["start_date"], "%Y-%m-%d")
            day_of_cycle = (today - start_date).days + 1

            if latest["end_date"] is None:
                # กำลังมีเมนส์อยู่
                if is_bf:
                    msgs = ["",
                        f"แฟนเมนส์วันที่ {day_of_cycle} แล้วนะ 🩸 ลองถามว่าปวดท้องมั้ย หรือต้องการอะไรมั้ย 💙",
                        f"วันที่ {day_of_cycle} แล้ว ลองเอาช็อกโกแลตหรือน้ำอุ่นให้แฟนดูนะ 🍫",
                        f"วันที่ {day_of_cycle} แล้ว ใกล้หมดแล้วนะ ดูแลแฟนต่อไปนะ 💙",
                        f"วันที่ {day_of_cycle} แล้ว แฟนน่าจะดีขึ้นเรื่อยๆนะ 🌸",
                    ]
                else:
                    msgs = ["",
                        f"วันที่ {day_of_cycle} แล้วนะ! 🩸 วันนี้เป็นยังไงบ้าง มาเยอะหรือน้อยคะ?",
                        f"วันที่ {day_of_cycle} นะ 💙 ยังปวดท้องอยู่มั้ย? ดูแลตัวเองด้วยนะ",
                        f"วันที่ {day_of_cycle} แล้ว! 🌸 วันนี้มาน้อยลงมั้ยคะ?",
                        f"วันที่ {day_of_cycle} นะ ใกล้หมดแล้วแหละ สู้ๆ! 💪",
                        f"วันที่ {day_of_cycle} แล้ว ใกล้หายแล้วนะ 🌟",
                        f"วันที่ {day_of_cycle} แล้ว ✨ ถ้าหมดแล้วบอกพี่สาวด้วยนะ!",
                        f"วันที่ {day_of_cycle} แล้วนะ 📅 ถ้าหมดแล้วบอกด้วยนะ จะได้คำนวณรอบหน้าให้!",
                    ]
                if 1 <= day_of_cycle < len(msgs):
                    send_push_message(user_id, msgs[day_of_cycle])

            else:
                # premium เท่านั้นที่ได้รับแจ้งเตือน
                if not check_premium(user_id):
                    continue

                ovulation_day = avg - 14
                if day_of_cycle == ovulation_day - 1:
                    msg = ("🥚 พรุ่งนี้น่าจะเป็นช่วงที่แฟนไข่ตกนะ!\nช่วงนี้แฟนจะดูดีและมีพลังงานสูง ✨\nเหมาะกับการพาออกไปเดทนะ!" if is_bf
                           else "🥚 พรุ่งนี้น่าจะเป็นช่วงที่ไข่ตกนะ!\nช่วงนี้ผิวจะดูเปล่งปลั่งที่สุด พลังงานสูงมาก ✨")
                    send_push_message(user_id, msg)

                elif day_of_cycle == ovulation_day:
                    msg = ("💫 วันนี้น่าจะเป็นวันที่แฟนไข่ตกนะ!\nแฟนจะดูสวยและมีพลังงานสูงสุดวันนี้เลย 🌟" if is_bf
                           else "💫 วันนี้น่าจะเป็นวันที่ไข่ตกนะ!\nนี่คือช่วงที่หน้าสวยที่สุดในรอบเลย 🌟")
                    send_push_message(user_id, msg)

                next_date = predict_next_period(user_id)
                if next_date:
                    days_left = (next_date - today).days
                    if days_left == 7:
                        msg = ("⚡ อีก 7 วันแฟนน่าจะถึงรอบเดือนแล้วนะ\nช่วงนี้แฟนอาจจะอ่อนไหวได้ง่าย\nเข้าใจและอดทนหน่อยนะ มันคือฮอร์โมน! 💙" if is_bf
                               else "⚡ เริ่มเข้าสู่ช่วง PMS แล้วนะ อีก 7 วันรอบเดือนน่าจะมา\nอาจรู้สึกเครียดหรืออ่อนไหวได้ง่าย ไม่ใช่ความผิดของเรานะ 💙")
                        send_push_message(user_id, msg)
                    elif days_left == 3:
                        msg = ("📅 อีก 3 วันแฟนน่าจะถึงรอบเดือนแล้วนะ!\nลองพกผ้าอนามัยสำรองไว้ให้แฟนด้วยนะ 🌸\nแฟนจะประทับใจมากเลย 💙" if is_bf
                               else "📅 อีก 3 วันรอบเดือนน่าจะมาแล้วนะ!\nอย่าลืมพกผ้าอนามัยติดกระเป๋าด้วยนะ 🌸")
                        send_push_message(user_id, msg)
                    elif days_left == 1:
                        msg = ("🩸 พรุ่งนี้แฟนน่าจะถึงรอบเดือนแล้วนะ!\nอย่าลืมพกผ้าอนามัยสำรองไว้ให้เขาด้วยนะ 💙" if is_bf
                               else "🩸 พรุ่งนี้น่าจะมาแล้วนะ! เตรียมผ้าอนามัยไว้ได้เลย\nถ้ามาก็บอกพี่สาวด้วยนะ 💙")
                        send_push_message(user_id, msg)
                    elif days_left == 0:
                        msg = ("🌸 วันนี้น่าจะถึงรอบเดือนของแฟนแล้วนะ!\nถามแฟนดูนะว่ามาแล้วหรือยัง แล้วบอกพี่สาวด้วย!" if is_bf
                               else "🌸 วันนี้น่าจะถึงรอบเดือนแล้วนะ!\nมาแล้วหรือยังคะ? ถ้ามาก็บอกพี่สาวด้วยนะ!")
                        send_push_message(user_id, msg)

        except Exception as e:
            print(f"Notification error for {user_id}: {e}")

def run_scheduler():
    schedule.every().day.at("09:00").do(daily_check_and_notify)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=run_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
