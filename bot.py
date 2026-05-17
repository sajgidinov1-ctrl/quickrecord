“””
QuickRecord — Бот для записи клиентов
Оплата через СБП (Т-Банк) | SQLite база | Резерв слота 30 минут
“””

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
InlineKeyboardMarkup, InlineKeyboardButton,
ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ============================================================

# НАСТРОЙКИ

# ============================================================

BOT_TOKEN = “8674542784:AAE7VJ6DqkIMKf9Flsx9TL-qJ4vmZMIf6no”
ADMIN_CHAT_ID = 8235415794

# ⚠️ Замени YOUR_USERNAME на свой username в PythonAnywhere

WEBHOOK_HOST = “https://YOUR_USERNAME.pythonanywhere.com”
WEBHOOK_PATH = f”/webhook/{BOT_TOKEN}”
WEBHOOK_URL = f”{WEBHOOK_HOST}{WEBHOOK_PATH}”

WEB_SERVER_HOST = “0.0.0.0”
WEB_SERVER_PORT = 8443

BUSINESS_NAME = “QuickRecord”
BUSINESS_EMOJI = “📅”

SBP_PHONE = “89931422707”
SBP_BANK = “Т-Банк”
SBP_RECIPIENT = “Динислам С. А.”

RESERVE_MINUTES = 30

SERVICES = {
“Стрижка”: 1000,
“Стрижка + борода”: 1500,
“Борода”: 800,
“Окрашивание”: 2500,
“Маникюр”: 1200,
“Массаж (60 мин)”: 2000,
}

WORK_HOURS = [
“09:00”, “10:00”, “11:00”, “12:00”,
“13:00”, “14:00”, “15:00”, “16:00”,
“17:00”, “18:00”, “19:00”, “20:00”
]

DB_PATH = “bookings.db”

# ============================================================

# БАЗА ДАННЫХ

# ============================================================

def init_db():
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(”””
CREATE TABLE IF NOT EXISTS bookings (
id INTEGER PRIMARY KEY AUTOINCREMENT,
date TEXT NOT NULL,
time TEXT NOT NULL,
user_id INTEGER NOT NULL,
name TEXT,
phone TEXT,
service TEXT,
price INTEGER,
status TEXT DEFAULT ‘reserved’,
reserved_at TEXT NOT NULL,
confirmed_at TEXT
)
“””)
conn.commit()
conn.close()

def is_slot_taken(date: str, time: str) -> bool:
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
expire_time = (datetime.now() - timedelta(minutes=RESERVE_MINUTES)).strftime(”%Y-%m-%d %H:%M:%S”)
c.execute(”””
SELECT id FROM bookings
WHERE date = ? AND time = ?
AND status IN (‘confirmed’, ‘reserved’)
AND (status = ‘confirmed’ OR reserved_at > ?)
“””, (date, time, expire_time))
result = c.fetchone()
conn.close()
return result is not None

def get_free_slots(date: str) -> list:
return [t for t in WORK_HOURS if not is_slot_taken(date, t)]

def reserve_slot(date, time, user_id, name, phone, service, price) -> int:
cancel_expired_reserves(user_id)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
now = datetime.now().strftime(”%Y-%m-%d %H:%M:%S”)
c.execute(”””
INSERT INTO bookings (date, time, user_id, name, phone, service, price, status, reserved_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ‘reserved’, ?)
“””, (date, time, user_id, name, phone, service, price, now))
booking_id = c.lastrowid
conn.commit()
conn.close()
return booking_id

def confirm_booking(booking_id: int):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
now = datetime.now().strftime(”%Y-%m-%d %H:%M:%S”)
c.execute(“UPDATE bookings SET status = ‘confirmed’, confirmed_at = ? WHERE id = ?”, (now, booking_id))
conn.commit()
conn.close()

def cancel_booking_by_id(booking_id: int):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(“UPDATE bookings SET status = ‘cancelled’ WHERE id = ?”, (booking_id,))
conn.commit()
conn.close()

def cancel_expired_reserves(user_id=None):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
expire_time = (datetime.now() - timedelta(minutes=RESERVE_MINUTES)).strftime(”%Y-%m-%d %H:%M:%S”)
if user_id:
c.execute(”””
UPDATE bookings SET status = ‘cancelled’
WHERE user_id = ? AND status = ‘reserved’ AND reserved_at <= ?
“””, (user_id, expire_time))
else:
c.execute(”””
UPDATE bookings SET status = ‘cancelled’
WHERE status = ‘reserved’ AND reserved_at <= ?
“””, (expire_time,))
conn.commit()
conn.close()

def get_booking_by_id(booking_id: int):
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(“SELECT * FROM bookings WHERE id = ?”, (booking_id,))
row = c.fetchone()
conn.close()
if row:
cols = [“id”, “date”, “time”, “user_id”, “name”, “phone”, “service”, “price”, “status”, “reserved_at”, “confirmed_at”]
return dict(zip(cols, row))
return None

# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(**name**)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class BookingStates(StatesGroup):
choosing_service = State()
choosing_date = State()
choosing_time = State()
entering_name = State()
entering_phone = State()
confirming = State()
waiting_screenshot = State()

def services_keyboard():
buttons = []
for service, price in SERVICES.items():
buttons.append([InlineKeyboardButton(
text=f”{service} — {price} ₽”,
callback_data=f”service:{service}:{price}”
)])
return InlineKeyboardMarkup(inline_keyboard=buttons)

def dates_keyboard():
buttons = []
today = datetime.now()
row = []
for i in range(7):
day = today + timedelta(days=i)
label = “Сегодня” if i == 0 else (“Завтра” if i == 1 else day.strftime(”%d.%m”))
row.append(InlineKeyboardButton(
text=label,
callback_data=f”date:{day.strftime(’%Y-%m-%d’)}”
))
if len(row) == 3:
buttons.append(row)
row = []
if row:
buttons.append(row)
return InlineKeyboardMarkup(inline_keyboard=buttons)

def times_keyboard(free_slots: list):
buttons = []
row = []
for time in WORK_HOURS:
if time in free_slots:
row.append(InlineKeyboardButton(text=time, callback_data=f”time:{time}”))
else:
row.append(InlineKeyboardButton(text=f”🚫 {time}”, callback_data=“slot_taken”))
if len(row) == 3:
buttons.append(row)
row = []
if row:
buttons.append(row)
return InlineKeyboardMarkup(inline_keyboard=buttons)

def confirm_keyboard():
return InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text=“✅ Перейти к оплате”, callback_data=“confirm_pay”)],
[InlineKeyboardButton(text=“❌ Отменить”, callback_data=“cancel”)],
])

def phone_keyboard():
return ReplyKeyboardMarkup(
keyboard=[[KeyboardButton(text=“📱 Отправить мой номер”, request_contact=True)]],
resize_keyboard=True,
one_time_keyboard=True
)

def admin_approve_keyboard(booking_id: int):
return InlineKeyboardMarkup(inline_keyboard=[
[InlineKeyboardButton(text=“✅ Подтвердить оплату”, callback_data=f”approve:{booking_id}”)],
[InlineKeyboardButton(text=“❌ Отклонить”, callback_data=f”reject:{booking_id}”)],
])

# ============================================================

# HANDLERS

# ============================================================

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
await state.clear()
cancel_expired_reserves()
await message.answer(
f”{BUSINESS_EMOJI} *QuickRecord* — быстрая запись к мастеру\n\nПривет! Выбери услугу 👇”,
parse_mode=“Markdown”,
reply_markup=services_keyboard()
)
await state.set_state(BookingStates.choosing_service)

@dp.callback_query(F.data.startswith(“service:”))
async def choose_service(callback: types.CallbackQuery, state: FSMContext):
parts = callback.data.split(”:”)
service, price = parts[1], int(parts[2])
await state.update_data(service=service, price=price)
await callback.message.edit_text(
f”✅ Услуга: *{service}* — {price} ₽\n\nВыбери удобную дату 📅”,
parse_mode=“Markdown”,
reply_markup=dates_keyboard()
)
await state.set_state(BookingStates.choosing_date)
await callback.answer()

@dp.callback_query(F.data.startswith(“date:”))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
date_str = callback.data.split(”:”)[1]
date_obj = datetime.strptime(date_str, “%Y-%m-%d”)
date_display = date_obj.strftime(”%d.%m.%Y (%A)”).replace(
“Monday”, “Пн”).replace(“Tuesday”, “Вт”).replace(“Wednesday”, “Ср”).replace(
“Thursday”, “Чт”).replace(“Friday”, “Пт”).replace(“Saturday”, “Сб”).replace(“Sunday”, “Вс”)

```
cancel_expired_reserves()
free_slots = get_free_slots(date_str)

if not free_slots:
    await callback.message.edit_text(
        f"😔 На *{date_display}* все слоты заняты.\n\nВыбери другую дату 📅",
        parse_mode="Markdown",
        reply_markup=dates_keyboard()
    )
    await callback.answer()
    return

await state.update_data(date=date_str, date_display=date_display)
await callback.message.edit_text(
    f"✅ Дата: *{date_display}*\n\nВыбери время ⏰  |  🚫 — занято",
    parse_mode="Markdown",
    reply_markup=times_keyboard(free_slots)
)
await state.set_state(BookingStates.choosing_time)
await callback.answer()
```

@dp.callback_query(F.data == “slot_taken”)
async def slot_taken(callback: types.CallbackQuery):
await callback.answer(“❌ Это время занято, выбери другое”, show_alert=True)

@dp.callback_query(F.data.startswith(“time:”))
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
time_str = callback.data.split(”:”)[1]
data = await state.get_data()

```
if is_slot_taken(data['date'], time_str):
    cancel_expired_reserves()
    free_slots = get_free_slots(data['date'])
    await callback.message.edit_text(
        f"😔 Время *{time_str}* только что заняли!\n\nВыбери другое время ⏰",
        parse_mode="Markdown",
        reply_markup=times_keyboard(free_slots)
    )
    await callback.answer("Это время уже занято!", show_alert=True)
    return

await state.update_data(time=time_str)
await callback.message.edit_text(
    f"✅ Время: *{time_str}*\n\nКак тебя зовут? 👇",
    parse_mode="Markdown"
)
await state.set_state(BookingStates.entering_name)
await callback.answer()
```

@dp.message(BookingStates.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
name = message.text.strip()
if len(name) < 2:
await message.answer(“Пожалуйста, введи настоящее имя 😊”)
return
await state.update_data(name=name)
await message.answer(
f”Отлично, *{name}*! 👋\n\nПоделись номером телефона:”,
parse_mode=“Markdown”,
reply_markup=phone_keyboard()
)
await state.set_state(BookingStates.entering_phone)

@dp.message(BookingStates.entering_phone, F.contact)
async def enter_phone_contact(message: types.Message, state: FSMContext):
await state.update_data(phone=message.contact.phone_number)
await show_confirmation(message, state)

@dp.message(BookingStates.entering_phone, F.text)
async def enter_phone_text(message: types.Message, state: FSMContext):
await state.update_data(phone=message.text.strip())
await show_confirmation(message, state)

async def show_confirmation(message: types.Message, state: FSMContext):
data = await state.get_data()
await message.answer(
f”📋 *Детали записи:*\n\n”
f”💆 {data[‘service’]}\n”
f”📅 {data[‘date_display’]}\n”
f”⏰ {data[‘time’]}\n”
f”👤 {data[‘name’]}\n”
f”📱 {data[‘phone’]}\n”
f”💰 {data[‘price’]} ₽\n\n”
f”⚠️ После нажатия *Перейти к оплате* время резервируется на *{RESERVE_MINUTES} минут*.”,
parse_mode=“Markdown”,
reply_markup=confirm_keyboard()
)
await state.set_state(BookingStates.confirming)

@dp.callback_query(F.data == “confirm_pay”)
async def show_payment_details(callback: types.CallbackQuery, state: FSMContext):
data = await state.get_data()

```
if is_slot_taken(data['date'], data['time']):
    await callback.message.edit_text(
        "😔 К сожалению, это время только что заняли.\n\nНапиши /start и выбери другое время."
    )
    await callback.answer()
    return

booking_id = reserve_slot(
    date=data['date'], time=data['time'],
    user_id=callback.from_user.id,
    name=data['name'], phone=data['phone'],
    service=data['service'], price=data['price']
)
await state.update_data(booking_id=booking_id)
await callback.message.delete()
await callback.message.answer(
    f"🔒 *Время зарезервировано на {RESERVE_MINUTES} минут!*\n\n"
    f"💳 Переведи *{data['price']} ₽* через СБП:\n\n"
    f"📱 Номер: `{SBP_PHONE}`\n"
    f"🏦 Банк: *{SBP_BANK}*\n"
    f"👤 Получатель: *{SBP_RECIPIENT}*\n\n"
    f"Комментарий к переводу:\n`Запись {data['service']} {data['time']}`\n\n"
    f"После перевода пришли *скриншот чека* 📸",
    parse_mode="Markdown",
    reply_markup=ReplyKeyboardRemove()
)
await state.set_state(BookingStates.waiting_screenshot)
await callback.answer()
```

@dp.callback_query(F.data == “cancel”)
async def cancel_booking(callback: types.CallbackQuery, state: FSMContext):
data = await state.get_data()
if data.get(‘booking_id’):
cancel_booking_by_id(data[‘booking_id’])
await state.clear()
await callback.message.edit_text(“❌ Запись отменена.\n\nНапиши /start чтобы начать заново.”)
await callback.answer()

@dp.message(BookingStates.waiting_screenshot, F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
data = await state.get_data()
user = message.from_user
booking_id = data.get(‘booking_id’)

```
await message.answer(
    "⏳ *Скриншот получен!*\n\nПроверяю оплату, обычно до 5 минут.\nПришлю уведомление ✅",
    parse_mode="Markdown"
)

try:
    await bot.send_message(
        ADMIN_CHAT_ID,
        f"🔔 *НОВАЯ ЗАПИСЬ #{booking_id}*\n\n"
        f"💆 {data['service']}\n"
        f"📅 {data['date_display']} в {data['time']}\n"
        f"👤 {data['name']}\n"
        f"📱 {data['phone']}\n"
        f"💰 {data['price']} ₽\n"
        f"🆔 @{user.username or 'нет'} (ID: {user.id})\n\n"
        f"⬇️ Скриншот оплаты:",
        parse_mode="Markdown"
    )
    await bot.forward_message(ADMIN_CHAT_ID, message.chat.id, message.message_id)
    await bot.send_message(
        ADMIN_CHAT_ID,
        f"Подтвердить запись #{booking_id} для {data['name']}?",
        reply_markup=admin_approve_keyboard(booking_id)
    )
except Exception as e:
    logger.error(f"Ошибка уведомления: {e}")

await state.clear()
```

@dp.message(BookingStates.waiting_screenshot)
async def wrong_screenshot(message: types.Message):
await message.answer(“📸 Пришли *скриншот* перевода (фото чека из банка).”, parse_mode=“Markdown”)

@dp.callback_query(F.data.startswith(“approve:”))
async def approve_booking(callback: types.CallbackQuery):
booking_id = int(callback.data.split(”:”)[1])
booking = get_booking_by_id(booking_id)
if not booking:
await callback.answer(“Запись не найдена!”, show_alert=True)
return
confirm_booking(booking_id)
try:
await bot.send_message(
booking[‘user_id’],
f”🎉 *Оплата подтверждена! Запись активна.*\n\n”
f”✅ {booking[‘service’]}\n”
f”📅 {booking[‘date’]} в {booking[‘time’]}\n\n”
f”Ждём тебя!”,
parse_mode=“Markdown”
)
await callback.message.edit_text(f”✅ Запись #{booking_id} подтверждена.”)
except Exception as e:
logger.error(f”Ошибка: {e}”)
await callback.answer(“Подтверждено!”)

@dp.callback_query(F.data.startswith(“reject:”))
async def reject_booking(callback: types.CallbackQuery):
booking_id = int(callback.data.split(”:”)[1])
booking = get_booking_by_id(booking_id)
if not booking:
await callback.answer(“Запись не найдена!”, show_alert=True)
return
cancel_booking_by_id(booking_id)
try:
await bot.send_message(
booking[‘user_id’],
“❌ *Оплата не прошла проверку.*\n\nНапиши /start и попробуй снова.”,
parse_mode=“Markdown”
)
await callback.message.edit_text(f”❌ Запись #{booking_id} отклонена. Слот освобождён.”)
except Exception as e:
logger.error(f”Ошибка: {e}”)
await callback.answer(“Отклонено!”)

# ============================================================

# WEBHOOK SETUP

# ============================================================

async def on_startup(app):
init_db()
await bot.set_webhook(WEBHOOK_URL)
logger.info(f”Webhook: {WEBHOOK_URL}”)

async def on_shutdown(app):
await bot.delete_webhook()

def main():
app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)
web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)

if **name** == “**main**”:
main()
