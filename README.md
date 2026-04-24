# 🌸 Period Bot - แชทบอทติดตามรอบเดือนใน Line

แชทบอทผู้ช่วยติดตามรอบเดือนบน Line ที่คุยแบบเพื่อนสนิท ใช้ Claude AI

---

## ✨ ฟีเจอร์

- 🩸 บันทึกวันแรกที่เมนส์มา แค่พิมพ์บอกตามธรรมชาติ
- 📊 ติดตามปริมาณเลือดแต่ละวัน (มาก / น้อย / ปานกลาง)
- 📅 คำนวณและทำนายรอบถัดไปอัตโนมัติ
- 🔔 แจ้งเตือนทุกวันในช่วงมีเมนส์
- ⚠️ แจ้งเตือนล่วงหน้า 3 วันและ 1 วันก่อนรอบถัดไป
- 💙 คุยแบบเพื่อนสนิท ไม่ทางการ

---

## 🛠️ วิธีติดตั้ง

### 1. สมัคร LINE Developers

1. ไปที่ https://developers.line.biz/
2. สร้าง Provider และ Channel ใหม่ (Messaging API)
3. จด **Channel Secret** และ **Channel Access Token**

### 2. สมัคร Anthropic API

1. ไปที่ https://console.anthropic.com/
2. สร้าง API Key ใหม่
3. จด **API Key**

### 3. Deploy บน Railway

1. ไปที่ https://railway.app/ และ Login ด้วย GitHub
2. กด "New Project" → "Deploy from GitHub repo"
3. อัพโหลดไฟล์ทั้งหมดขึ้น GitHub ก่อน แล้วเลือก repo นั้น
4. ตั้ง Environment Variables:
   ```
   LINE_CHANNEL_ACCESS_TOKEN = (จาก LINE Developers)
   LINE_CHANNEL_SECRET = (จาก LINE Developers)
   ANTHROPIC_API_KEY = (จาก Anthropic Console)
   ```
5. Railway จะ deploy อัตโนมัติ และให้ URL มา เช่น `https://your-app.railway.app`

### 4. ตั้ง Webhook URL ใน LINE

1. กลับไปที่ LINE Developers → Channel ของเรา
2. ไปที่ "Messaging API" tab
3. ตั้ง **Webhook URL** เป็น: `https://your-app.railway.app/webhook`
4. กด Verify และ Enable Webhook

### 5. ทดสอบ

เพิ่ม LINE Official Account ของเราเป็นเพื่อน แล้วลองพิมพ์ว่า "เมนส์มาแล้ว!"

---

## 💬 ตัวอย่างการใช้งาน

| User พิมพ์ | Bot ตอบ |
|---|---|
| "เมนส์มาแล้ว!" | บันทึกและถามอาการ |
| "วันนี้มาเยอะมากเลย" | บันทึกและให้คำแนะนำ |
| "หมดแล้ว" | คำนวณระยะเวลาและทำนายรอบหน้า |
| "รอบหน้ามาเมื่อไหร่" | แจ้งวันที่คาดการณ์ |

---

## 📁 โครงสร้างไฟล์

```
period-bot/
├── app.py           # Main application
├── requirements.txt # Python dependencies
├── Procfile         # Railway deployment config
└── README.md        # คู่มือนี้
```

---

## 💰 ค่าใช้จ่าย

- **Railway**: ฟรีสำหรับ hobby project (มี limit)
- **LINE Messaging API**: ฟรี 500 push messages/เดือน (เกินต้องจ่าย)
- **Claude API**: จ่ายตาม usage (ถูกมาก ประมาณ $0.003/message)

---

## ⚠️ หมายเหตุ

- ข้อมูลเก็บใน SQLite บน Railway server
- ถ้าอยากให้ข้อมูลปลอดภัยมากขึ้น ควรใช้ PostgreSQL แทน
- LINE Push Message ฟรีแค่ 500/เดือน ถ้า user เยอะต้องอัพแพลน
