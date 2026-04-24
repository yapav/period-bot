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
from linebot.v3.webhooks import MessageEvent, TextMessageContent

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PERIOD_DAY1_QUOTES = [
    "อุ๊ย มาแล้วนะ 🩸 ปวดท้องมั้ยคะ? ถ้ามีช็อกโกแลตอุ่นๆให้ดื่มคงดีเนอะ 🍫",
    "มาแล้วววว สู้ๆนะ! 💪 วันนี้ใจดีกับตัวเองด้วยนะ พักเยอะๆได้เลย",
    "เมนส์มาเยือนแล้ว ไหวรึเปล่าคะ? 🌸 ถ้าปวดท้องให้กินยาได้เลยนะ ไม่ต้องฝืน",
    "โอ้โห มาแล้ว! อยู่ดีๆมั้ยคะ? 💙 จำไว้นะว่าความรู้สึกวันนี้มันเป็นแค่ชั่วคราว",
    "มาแล้วนะเพื่อน 🫶 วันนี้อนุญาตตัวเองให้เอาใจใส่ตัวเองเป็นพิเศษเลยนะ",
    "เมนส์มาแล้ว! ร่างกายเราทำงานหนักมากเลยนะ 🌺 ขอบคุณร่างกายด้วยนะที่ดูแลเราดีมาก",
    "มาแล้วววว 🩸 วันนี้ถ้าอยากนอนพักเยอะๆก็ได้เลยนะ ไม่ต้องรู้สึกผิด!",
    "อ้าวมาแล้ว! อบอุ่นท้องด้วยกระเป๋าน้ำร้อนได้เลยนะ 🔥 ช่วยได้มากเลย",
]

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

def get_db():
    conn = sqlite3.connect("period_bot.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, display_name TEXT, created_at TEXT)""")
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
    conn.commit()
    conn.close()

def upsert_user(user_id, display_name=""):
    conn = get_db()
    conn.execute("INSERT OR IGNORE INTO users (user_id, display_name, created_at) VALUES (?, ?, ?)",
                 (user_id, display_name, datetime.now().isoformat()))
    conn.commit()
    conn.close()

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

def start_new_period(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute("UPDATE periods SET end_date = ? WHERE user_id = ? AND end_date IS NULL", (today, user_id))
    conn.execute("INSERT INTO periods (user_id, start_date) VALUES (?, ?)", (user_id, today))
    conn.commit()
    conn.close()

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
        return f"⚡ รอบนี้มาเร็วกว่าปกติ {abs(diff)} วันนะ (มาห่าง {actual_gap} วัน ปกติ {avg} วัน)\nอาจเกิดจากความเครียด การนอนน้อย หรือออกกำลังกายหนัก 💙"
    else:
        return f"🐢 รอบนี้มาช้ากว่าปกติ {diff} วันนะ (มาห่าง {actual_gap} วัน ปกติ {avg} วัน)\nมีหลายสาเหตุที่ทำให้มาช้าได้ ไม่ต้องกังวลมากนะ 🌸"

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
    periods = get_all_periods(user_id, limit=6)
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
            gap_str = f"   ← ห่างจากรอบก่อน {gap} วัน"
        else:
            gap_str = ""
        label = "🔴 ล่าสุด" if i == 0 else f"รอบที่ -{i}"
        lines.append(f"\n{label}\n🗓 {start.strftime('%d %b %Y')} – {end_str} {dur_str}{chr(10) + gap_str if gap_str else ''}")
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

SYSTEM_PROMPT = """คุณคือ "พี่สาว" แชทบอทผู้ช่วยติดตามรอบเดือนที่ที่ดูแลและห่วงใยผู้ใช้เหมือนพี่สาวคนจริงๆ
พูดคุยเป็นกันเองแบบพี่สาวที่ห่วงใย ใช้ภาษาไทยน่ารักๆ ไม่เป็นทางการ อบอุ่น และเอาใจใส่

คำสั่งพิเศษ (return JSON เท่านั้น ห้ามมีข้อความอื่น):
- บอกว่าเมนส์มาแล้ว / มาแล้ว / มาวันนี้ → {"action": "start_period"}
- บอกว่าหยุดแล้ว / หมดแล้ว / เมนส์หมด → {"action": "end_period"}
- บอกปริมาณเลือด มาเยอะ/น้อย/ปานกลาง → {"action": "log_flow", "level": "มาก/น้อย/ปานกลาง"}
- ถามรอบถัดไป / ครั้งหน้าเมื่อไหร่ → {"action": "predict"}
- ขอดูปฏิทิน / ดูประวัติ / รอบที่ผ่านมา → {"action": "calendar"}
- ถามเฟส / ฮอร์โมน / ตอนนี้อยู่เฟสไหน / ผิวช่วงนี้ → {"action": "phase"}
- สนทนาทั่วไป → ตอบปกติ ไม่ต้องมี JSON

ตอบสั้นกระชับไม่เกิน 3-4 ประโยค อบอุ่น น่ารัก"""

def chat_with_claude(user_id, user_message):
    history = get_chat_history(user_id)
    messages = [{"role": r["role"], "content": r["content"]} for r in history]
    messages.append({"role": "user", "content": user_message})
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    reply = response.content[0].text
    save_chat(user_id, "user", user_message)
    save_chat(user_id, "assistant", reply)
    return reply

def process_claude_response(user_id, response_text):
    try:
        data = json.loads(response_text.strip())
        action = data.get("action")

        if action == "start_period":
            start_new_period(user_id)
            avg = calculate_avg_cycle(user_id)
            quote = random.choice(PERIOD_DAY1_QUOTES)
            timing_msg = get_cycle_timing_message(user_id)
            reply = f"{quote}\n\nบันทึกแล้วนะ! 🩸\n"
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
                reply = f"บันทึกแล้วนะ ✨ รอบนี้มา {days} วัน\nรอบหน้าน่าจะประมาณ {next_str}"
                if days_left and days_left > 0:
                    reply += f" (อีก {days_left} วัน)"
                reply += "\n\nพักผ่อนให้เต็มที่นะ ร่างกายทำงานหนักมากเลย 🌸"
                return reply
            return "ยังไม่ได้บันทึกว่าเมนส์มาเลยนะ บอกด้วยนะถ้าเมนส์มา! 🌸"

        elif action == "log_flow":
            level = data.get("level", "ปานกลาง")
            log_daily(user_id, level)
            tips = {
                "มาก": "💧 มาเยอะนะ ดื่มน้ำเยอะๆด้วย และเปลี่ยนผ้าอนามัยทุก 3-4 ชั่วโมงนะ",
                "น้อย": "✨ มาน้อยดีเลย! ใส่แผ่นเล็กก็พอนะ",
                "ปานกลาง": "🌸 โอเคนะ! เปลี่ยนผ้าอนามัยทุก 4-6 ชั่วโมงด้วยนะ"
            }
            return f"บันทึกแล้วว่าวันนี้ {level} นะ!\n{tips.get(level, '')}"

        elif action == "predict":
            next_date = predict_next_period(user_id)
            ovulation = get_ovulation_date(user_id)
            if next_date:
                days_left = (next_date - datetime.now()).days
                reply = f"🔮 รอบถัดไปคาดว่าจะมาประมาณ {next_date.strftime('%d/%m/%Y')}"
                if days_left > 0:
                    reply += f"\n(อีกประมาณ {days_left} วัน)"
                elif days_left == 0:
                    reply += "\n(วันนี้เลย! เตรียมตัวได้เลยนะ)"
                else:
                    reply += f"\n(เลยกำหนดมา {abs(days_left)} วันแล้ว ถ้ามาแล้วบอกพี่สาวด้วยนะ!)"
                if ovulation:
                    reply += f"\n\n🥚 ไข่น่าจะตกประมาณ {ovulation.strftime('%d/%m/%Y')} นะ"
                return reply
            return "ยังไม่มีข้อมูลพอนะ บันทึกสัก 2 รอบก่อน จะได้คำนวณแม่นขึ้น! 💪"

        elif action == "calendar":
            return build_calendar_text(user_id)

        elif action == "phase":
            result = get_current_phase_info(user_id)
            if not result:
                return "ยังไม่มีข้อมูลรอบเดือนเลยนะ บอกว่า 'เมนส์มาแล้ว' เพื่อเริ่มบันทึกได้เลย 🌸"
            phase, info, day = result
            return (
                f"{info['emoji']} ตอนนี้อยู่วันที่ {day} ของรอบ\n"
                f"{info['name']}\n\n"
                f"🧬 ฮอร์โมน: {info['body']}\n\n"
                f"✨ ผิว: {info['skin']}\n\n"
                f"💭 อารมณ์: {info['mood']}\n\n"
                f"💡 Tips: {info['tips']}"
            )

    except (json.JSONDecodeError, ValueError):
        pass
    return response_text

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_message = event.message.text
    upsert_user(user_id)
    try:
        claude_response = chat_with_claude(user_id, user_message)
        reply_text = process_claude_response(user_id, claude_response)
    except Exception as e:
        reply_text = "โทษทีนะ ระบบมีปัญหาชั่วคราว ลองใหม่อีกทีนะคะ 🙏"
        print(f"Error: {e}")
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )
        )

def send_push_message(user_id, message):
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.push_message_with_http_info(
                PushMessageRequest(to=user_id, messages=[TextMessage(text=message)])
            )
    except Exception as e:
        print(f"Push error: {e}")

def daily_check_and_notify():
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    today = datetime.now()

    for user_row in users:
        user_id = user_row["user_id"]
        try:
            latest = get_latest_period(user_id)
            if not latest:
                continue
            avg = calculate_avg_cycle(user_id)
            start_date = datetime.strptime(latest["start_date"], "%Y-%m-%d")
            day_of_cycle = (today - start_date).days + 1

            if latest["end_date"] is None:
                # กำลังมีเมนส์อยู่
                daily_msgs = [
                    "",
                    f"วันที่ {day_of_cycle} แล้วนะ! 🩸 วันนี้เป็นยังไงบ้าง มาเยอะหรือน้อยคะ?",
                    f"วันที่ {day_of_cycle} นะ 💙 ยังปวดท้องอยู่มั้ย? ดูแลตัวเองด้วยนะ",
                    f"วันที่ {day_of_cycle} แล้ว! 🌸 วันนี้มาน้อยลงมั้ยคะ?",
                    f"วันที่ {day_of_cycle} นะ ใกล้หมดแล้วแหละ สู้ๆ! 💪",
                    f"วันที่ {day_of_cycle} แล้ว ใกล้หายแล้วนะ 🌟 วันนี้ยังไงบ้าง?",
                    f"วันที่ {day_of_cycle} แล้ว ✨ ถ้าหมดแล้วบอกพี่สาวด้วยนะ!",
                    f"วันที่ {day_of_cycle} แล้วนะ 📅 ถ้าหมดแล้วบอกด้วยนะ จะได้คำนวณรอบหน้าให้!",
                ]
                if 1 <= day_of_cycle < len(daily_msgs):
                    send_push_message(user_id, daily_msgs[day_of_cycle])
            else:
                # ไม่ได้มีเมนส์ → เช็คไข่ตกและ PMS
                ovulation_day = avg - 14

                if day_of_cycle == ovulation_day - 1:
                    send_push_message(user_id,
                        "🥚 พรุ่งนี้น่าจะเป็นช่วงที่ไข่ตกนะ!\n"
                        "ช่วงนี้ผิวจะดูเปล่งปลั่งที่สุด พลังงานสูงมากเลย ✨\n"
                        "เหมาะกับการนัดสำคัญหรือออกไปพบปะคนนะ!")
                elif day_of_cycle == ovulation_day:
                    send_push_message(user_id,
                        "💫 วันนี้น่าจะเป็นวันที่ไข่ตกนะ!\n"
                        "นี่คือช่วงที่หน้าสวยที่สุดในรอบเลย ออกไปโลดแล่นได้เลย 🌟")

                next_date = predict_next_period(user_id)
                if next_date:
                    days_left = (next_date - today).days
                    if days_left == 7:
                        send_push_message(user_id,
                            "⚡ เริ่มเข้าสู่ช่วง PMS แล้วนะ อีก 7 วันรอบเดือนน่าจะมา\n"
                            "ช่วงนี้อาจรู้สึกเครียด หงุดหงิด หรืออ่อนไหวได้ง่ายขึ้น\n"
                            "ไม่ใช่ความผิดของเรานะ มันคือฮอร์โมน! 💙 ดูแลตัวเองด้วยนะ")
                    elif days_left == 3:
                        send_push_message(user_id,
                            "📅 อีก 3 วันรอบเดือนน่าจะมาแล้วนะ!\n"
                            "อย่าลืมพกผ้าอนามัยติดกระเป๋าด้วยนะ 🌸\n"
                            "ช่วงนี้อาจปวดเมื่อยหรือท้องอืดได้ ดื่มน้ำเยอะๆนะ")
                    elif days_left == 1:
                        send_push_message(user_id,
                            "🩸 พรุ่งนี้น่าจะมาแล้วนะ! เตรียมผ้าอนามัยไว้ได้เลย\n"
                            "ถ้ามาก็บอกพี่สาวด้วยนะ จะได้บันทึกให้! 💙")
                    elif days_left == 0:
                        send_push_message(user_id,
                            "🌸 วันนี้น่าจะถึงรอบเดือนแล้วนะ!\n"
                            "มาแล้วหรือยังคะ? ถ้ามาก็บอกพี่สาวด้วยนะ!")
        except Exception as e:
            print(f"Notification error for {user_id}: {e}")

def run_scheduler():
    schedule.every().day.at("09:00").do(daily_check_and_notify)
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
