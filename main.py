import os
import logging
import urllib.request  # لتحميل الخط العربي تلقائياً
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, AudioFileClip
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait
from dotenv import load_dotenv
import json
import asyncio
import time
from collections import defaultdict

load_dotenv()

# ==========================================
# 1. الإعدادات الأساسية
# ==========================================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", 0))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

app = Client("MemoryDesignerBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

TEMP_DIR = "temp_images"
os.makedirs(TEMP_DIR, exist_ok=True)

# ==========================================
# 2. تحميل الخط العربي تلقائياً (الحل السحري)
# ==========================================
FONT_PATH = "Cairo-Regular.ttf"
if not os.path.exists(FONT_PATH):
    print("⏳ جاري تحميل الخط العربي...")
    try:
        # رابط مباشر لملف الخط من مستودع جوجل الرسمي
        font_url = "https://github.com/google/fonts/raw/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf"
        urllib.request.urlretrieve(font_url, FONT_PATH)
        print("✅ تم تحميل الخط بنجاح!")
    except Exception as e:
        print(f"❌ فشل تحميل الخط: {e}")

# ==========================================
# 3. إدارة البيانات والحالات
# ==========================================
user_states = {}
USERS_FILE = "users_data.json"
CONFIG_FILE = "admin_config.json"

DEV_NAME = "المبرمج"
DEV_USERNAME = ""

if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users_db = json.load(f)
else:
    users_db = {}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config_data = json.load(f)
else:
    config_data = {"channels": [], "media": {"create": None}}

def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_db, f, ensure_ascii=False)

def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False)

class RateLimiter:
    def __init__(self):
        self.cooldown = 60
        self._last = {}
        self._violations = defaultdict(list)
        self.banned = {}

    def is_rate_limited(self, uid):
        now = time.time()
        if now - self._last.get(uid, 0) < self.cooldown: return True
        self._last[uid] = now
        return False

    def record_violation(self, uid):
        now = time.time()
        window = [t for t in self._violations[uid] if now - t < 3600]
        window.append(now)
        self._violations[uid] = window
        if len(window) >= 3:
            self.banned[uid] = now + 3600

    def is_banned(self, uid):
        if uid in self.banned:
            if time.time() > self.banned[uid]:
                del self.banned[uid]
                return False
            return True
        return False

rate_limiter = RateLimiter()

# ==========================================
# 4. دوال التصميم
# ==========================================
def wrap_text(text, font, max_width):
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)
    lines = []
    words = bidi_text.split(' ')
    current_line = ""
    for word in words:
        test_line = current_line + " " + word if current_line else word
        bbox = font.getbbox(test_line)
        line_width = bbox[2] - bbox[0]
        if line_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def create_cinematic_image(image_path, text, color_hex, output_path):
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    width, height = img.size
    try:
        font = ImageFont.truetype(FONT_PATH, size=int(width * 0.05))
    except IOError:
        font = ImageFont.load_default()

    color_rgb = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
    margin_right = int(width * 0.05)
    margin_top = int(height * 0.2)
    max_text_width = int(width * 0.45)
    
    lines = wrap_text(text, font, max_text_width)
    y_offset = margin_top
    for line in lines:
        bbox = font.getbbox(line)
        line_width = bbox[2] - bbox[0]
        x_position = width - margin_right - line_width
        draw.text((x_position, y_offset), line, font=font, fill=color_rgb)
        y_offset += int(font.size * 1.5)
    img.save(output_path, quality=95)

def create_video_with_audio(image_path, audio_path, output_path):
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    image_clip = ImageClip(image_path).set_duration(duration)
    video = image_clip.set_audio(audio_clip)
    video.write_videofile(output_path, fps=1, codec="libx264", audio_codec="aac", logger=None)

# ==========================================
# 5. الأزرار والقوائم
# ==========================================
def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء والرجوع للقائمة الرئيسية", callback_data="back_to_start")]])

def get_main_keyboard(user_id):
    kb = [
        [InlineKeyboardButton("🎨 ابدأ التصميم الآن", callback_data="start_design")],
        [InlineKeyboardButton("📞 نداء للمطور", callback_data="call_dev")]
    ]
    if DEV_USERNAME:
        kb.append([InlineKeyboardButton(f"👨‍💻 {DEV_NAME}", url=f"https://t.me/{DEV_USERNAME}")])
    
    if user_id == OWNER_ID:
        kb.append([InlineKeyboardButton("🛡️ لوحة التحكم (للمطور)", callback_data="open_admin")])
    return InlineKeyboardMarkup(kb)

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 الإذاعة", callback_data="admin_broadcast"), InlineKeyboardButton("🚫 المحظورين", callback_data="admin_bans")],
        [InlineKeyboardButton("📡 الاشتراك الإجباري", callback_data="admin_channels"), InlineKeyboardButton("🖼️ وسائط الترحيب", callback_data="admin_media")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="back_to_start")]
    ])

def get_channels_keyboard():
    channels = config_data.get("channels", [])
    kb = []
    for i in range(5):
        if i < len(channels): kb.append([InlineKeyboardButton(f"📢 قناة {i+1} (إدارة)", callback_data=f"admin_ch_{i}")])
        else: kb.append([InlineKeyboardButton(f"➕ تعيين قناة {i+1}", callback_data=f"admin_add_ch_{i}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="open_admin")])
    return InlineKeyboardMarkup(kb)

# ==========================================
# 6. التحقق من الاشتراك
# ==========================================
async def check_subscription(client, user_id):
    channels = config_data.get("channels", [])
    if not channels: return True 
    for ch in channels:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]: return False
        except UserNotParticipant: return False
        except: pass 
    return True

# ==========================================
# 7. أوامر البوت والترحيب
# ==========================================
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    global DEV_NAME, DEV_USERNAME
    
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    
    if rate_limiter.is_banned(user_id):
        return await message.reply_text("**🚫 أنت محظور مؤقتاً بسبب محاولات خاطئة.**")

    if DEV_USERNAME == "":
        try:
            dev_user = await client.get_users(OWNER_ID)
            DEV_NAME = dev_user.first_name
            DEV_USERNAME = dev_user.username if dev_user.username else str(OWNER_ID)
        except:
            DEV_NAME = "المبرمج"
            DEV_USERNAME = str(OWNER_ID)

    if str(user_id) not in users_db:
        users_db[str(user_id)] = {"name": message.from_user.first_name, "username": message.from_user.username}
        save_users()
        name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
        username = f"@{message.from_user.username}" if message.from_user.username else "لا يوجد"
        dev_text = f"**👤 دخول مستخدم جديد:**\n\n**الاسم:** {name}\n**الآيدي:** `{user_id}`\n**المعرف:** {username}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 مراسلة المستخدم", url=f"tg://user?id={user_id}")]])
        try: await client.send_message(OWNER_ID, dev_text, reply_markup=kb)
        except: pass

    if not await check_subscription(client, user_id):
        channels = config_data.get("channels", [])
        kb = []
        for ch in channels: kb.append([InlineKeyboardButton(f"📢 انضم إلى {ch}", url=f"https://t.me/{ch.replace('@', '')}")])
        kb.append([InlineKeyboardButton("✅ تم الاشتراك، تحقق", callback_data="check_join")])
        return await message.reply_text("**عذراً، يجب عليك الاشتراك في القنوات التالية أولاً:**", reply_markup=InlineKeyboardMarkup(kb))

    text = (
        "**🎬 مرحباً بك في بوت تصميم الذكريات السينمائية**\n\n"
        "**هذا البوت يحول صورك إلى فيديوهات فنية تحتوي على رسائلك وأغانيك المفضلة.**\n\n"
        "**كيف تستخدمه؟**\n"
        "**1️⃣** اضغط على زر (ابدأ التصميم).\n"
        "**2️⃣** أرسل الصورة التي تريد الكتابة عليها.\n"
        "**3️⃣** أرسل النص الذي تريده.\n"
        "**4️⃣** اختر لون النص من الأزرار.\n"
        "**5️⃣** أرسل مقطعاً صوتياً (من 30 إلى 60 ثانية).\n"
        "**6️⃣** سأقوم بدمجهم لك في فيديو واحد!"
    )
    
    try: await message.delete()
    except: pass
    await message.reply_text(text, reply_markup=get_main_keyboard(user_id))

@app.on_callback_query(filters.regex("^check_join$"))
async def check_join(client, callback_query):
    if await check_subscription(client, callback_query.from_user.id):
        await callback_query.answer("تم التحقق بنجاح!")
        await callback_query.message.delete()
        await start_cmd(client, callback_query.message)
    else:
        await callback_query.answer("لم تشترك في جميع القنوات بعد.", show_alert=True)

@app.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id in user_states: del user_states[user_id]
    await callback_query.answer("تم الإلغاء.")
    try: await callback_query.message.delete()
    except: pass
    await start_cmd(client, callback_query.message)

# ==========================================
# 8. لوحة التحكم (للمطور فقط)
# ==========================================
@app.on_callback_query(filters.regex("^open_admin$"))
async def open_admin(client, callback_query):
    if callback_query.from_user.id != OWNER_ID:
        return await callback_query.answer("هذا القسم للمطور فقط!", show_alert=True)
    
    text = "**🛡️ لوحة التحكم الأمنية**\n\n**مرحباً بك أيها المالك. اختر الإجراء المطلوب:**"
    await callback_query.message.edit_text(text, reply_markup=get_admin_keyboard())

@app.on_callback_query(filters.regex("^admin_stats$"))
async def admin_stats(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    total_users = len(users_db)
    banned = len(rate_limiter.banned)
    text = f"**📊 الإحصائيات:**\n\n**- المستخدمين:** `{total_users}`\n**- المحظورين مؤقتاً:** `{banned}`\n**- الحالة:** ✅ يعمل"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="open_admin")]])
    await callback_query.message.edit_text(text, reply_markup=kb)

@app.on_callback_query(filters.regex("^admin_broadcast$"))
async def admin_broadcast(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    user_states[callback_query.from_user.id] = {"step": "admin_waiting_broadcast"}
    text = "**📢 أرسل الآن الرسالة التي تريد إذاعتها لجميع المستخدمين:**"
    await callback_query.message.edit_text(text, reply_markup=get_back_keyboard())

@app.on_callback_query(filters.regex("^admin_bans$"))
async def admin_bans(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    if not rate_limiter.banned:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="open_admin")]])
        return await callback_query.message.edit_text("**✅ لا يوجد محظورون حالياً.**", reply_markup=kb)
    
    kb = []
    for banned_id in rate_limiter.banned.keys():
        kb.append([InlineKeyboardButton(f"🔓 فك الحظر عن {banned_id}", callback_data=f"unban_{banned_id}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="open_admin")])
    await callback_query.message.edit_text("**🚫 قائمة المحظورين:**", reply_markup=InlineKeyboardMarkup(kb))

@app.on_callback_query(filters.regex(r"^unban_"))
async def unban_user(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    banned_id = int(callback_query.data.split("_")[1])
    if banned_id in rate_limiter.banned: del rate_limiter.banned[banned_id]
    await callback_query.answer("تم فك الحظر.")
    await admin_bans(client, callback_query)

@app.on_callback_query(filters.regex("^admin_channels$"))
async def admin_channels(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    await callback_query.message.edit_text("**📡 إدارة قنوات الاشتراك الإجباري:**", reply_markup=get_channels_keyboard())

@app.on_callback_query(filters.regex(r"^admin_add_ch_"))
async def admin_add_ch(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    user_states[callback_query.from_user.id] = {"step": "admin_waiting_channel"}
    await callback_query.message.edit_text("**أرسل يوزر القناة (مثال: @MyChannel):**", reply_markup=get_back_keyboard())

@app.on_callback_query(filters.regex(r"^admin_del_ch_"))
async def admin_del_ch(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    idx = int(callback_query.data.split("_")[3])
    config_data["channels"].pop(idx)
    save_config()
    await callback_query.answer("تم حذف القناة.")
    await admin_channels(client, callback_query)

@app.on_callback_query(filters.regex("^admin_media$"))
async def admin_media(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    has_media = "✅" if config_data["media"].get("create") else "❌"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{has_media} صورة/فيديو الترحيب", callback_data="set_media")],
        [InlineKeyboardButton("🗑 حذف الوسائط", callback_data="del_media")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="open_admin")]
    ])
    await callback_query.message.edit_text("**🖼️ إدارة وسائط الترحيب:**", reply_markup=kb)

@app.on_callback_query(filters.regex("^set_media$"))
async def set_media(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    user_states[callback_query.from_user.id] = {"step": "admin_waiting_media"}
    await callback_query.message.edit_text("**أرسل الصورة أو الفيديو الآن:**", reply_markup=get_back_keyboard())

@app.on_callback_query(filters.regex("^del_media$"))
async def del_media(client, callback_query):
    if callback_query.from_user.id != OWNER_ID: return
    config_data["media"]["create"] = None
    save_config()
    await callback_query.answer("تم حذف الوسائط.")
    await admin_media(client, callback_query)

# ==========================================
# 9. نداء المطور
# ==========================================
@app.on_callback_query(filters.regex("^call_dev$"))
async def call_developer(client, callback_query):
    user_id = callback_query.from_user.id
    await callback_query.answer("جاري إرسال بياناتك للمطور...", show_alert=True)
    user = callback_query.from_user
    
    try:
        full_user = await client.get_users(user_id)
        bio = full_user.bio if full_user.bio else "لا يوجد وصف"
        photo = full_user.photo
    except:
        bio, photo = "غير متوفر", None

    name = f"{user.first_name} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else "لا يوجد"
    age = f"{user.age}" if getattr(user, 'age', None) else "غير محدد"
    dob = f"{user.birthday}" if getattr(user, 'birthday', None) else "غير محدد"
    
    dev_text = f"**📞 نداء جديد:**\n\n**👤 الاسم:** {name}\n**🆔 الآيدي:** `{user_id}`\n**🔗 المعرف:** {username}\n**🎂 العمر:** {age}\n**📅 الميلاد:** {dob}\n**📝 الوصف:** {bio}"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 مراسلة المستخدم", url=f"tg://user?id={user_id}")]])

    try:
        if photo:
            photo_path = await client.download_media(photo.big_file_id, file_name=f"{TEMP_DIR}/profile_{user_id}.jpg")
            await client.send_photo(OWNER_ID, photo=photo_path, caption=dev_text, reply_markup=kb)
            os.remove(photo_path)
        else:
            await client.send_message(OWNER_ID, dev_text, reply_markup=kb)
    except: pass

# ==========================================
# 10. مراحل التصميم
# ==========================================
@app.on_callback_query(filters.regex("^start_design$"))
async def ask_for_photo(client, callback_query):
    await callback_query.answer()
    user_states[callback_query.from_user.id] = {"step": "waiting_photo"}
    await callback_query.message.edit_text("**🖼️ الخطوة الأولى: أرسل الصورة المطلوبة:**", reply_markup=get_back_keyboard())

@app.on_message(filters.private & filters.photo)
async def receive_photo(client, message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id]["step"] == "waiting_photo":
        try: await message.delete()
        except: pass
        file_path = await message.download(file_name=f"{TEMP_DIR}/{user_id}.jpg")
        user_states[user_id]["image_path"] = file_path
        user_states[user_id]["step"] = "waiting_text"
        await message.reply_text("**✅ تم استلام الصورة.**\n\n**✍️ الخطوة الثانية: أرسل النص المطلوب:**", reply_markup=get_back_keyboard())

@app.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def receive_text(client, message):
    user_id = message.from_user.id
    if user_id not in user_states: return
    
    state = user_states[user_id]["step"]
    
    if state == "admin_waiting_broadcast":
        del user_states[user_id]
        msg_status = await message.reply_text("**⏳ جاري الإذاعة...**")
        success, failed = 0, 0
        for uid in users_db.keys():
            try:
                await client.send_message(int(uid), f"**📢 إعلان من المطور:**\n\n{message.text}")
                success += 1
                await asyncio.sleep(0.1)
            except: failed += 1
        return await msg_status.edit_text(f"**✅ تم الإرسال لـ {success}.\n❌ فشل لـ {failed}.**")
        
    elif state == "admin_waiting_channel":
        del user_states[user_id]
        try:
            chat = await client.get_chat(message.text)
            await client.get_chat_member(message.text, "me")
            config_data["channels"].append(f"@{chat.username}")
            save_config()
            await message.reply_text("**✅ تم إضافة القناة.**", reply_markup=get_channels_keyboard())
        except Exception as e:
            await message.reply_text(f"**❌ فشل الإضافة:** `{e}`", reply_markup=get_channels_keyboard())
        return

    if state == "waiting_text":
        try: await message.delete()
        except: pass
        user_states[user_id]["text"] = message.text
        user_states[user_id]["step"] = "waiting_color"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔵 أزرق", callback_data="color_4DA8DA"), InlineKeyboardButton("⚪ أبيض", callback_data="color_FFFFFF")],
            [InlineKeyboardButton("🔴 أحمر", callback_data="color_FF4C4C"), InlineKeyboardButton("🟡 ذهبي", callback_data="color_FFD700")],
            [InlineKeyboardButton("🔙 إلغاء", callback_data="back_to_start")]
        ])
        await message.reply_text("**🎨 الخطوة الثالثة: اختر لون النص:**", reply_markup=kb)

@app.on_message(filters.private & (filters.photo | filters.video) & filters.user(OWNER_ID))
async def receive_admin_media(client, message):
    user_id = message.from_user.id
    if user_id in user_states and user_states[user_id]["step"] == "admin_waiting_media":
        del user_states[user_id]
        file_id = message.photo.file_id if message.photo else message.video.file_id
        config_data["media"]["create"] = file_id
        save_config()
        await message.reply_text("**✅ تم حفظ الوسائط بنجاح.**", reply_markup=get_admin_keyboard())

@app.on_callback_query(filters.regex(r"^color_"))
async def process_color(client, callback_query):
    user_id = callback_query.from_user.id
    if user_id not in user_states or user_states[user_id]["step"] != "waiting_color": return
    
    color_hex = callback_query.data.split("_")[1]
    user_states[user_id]["color"] = color_hex
    user_states[user_id]["step"] = "waiting_audio"
    await callback_query.answer()
    await callback_query.message.edit_text("**🎵 الخطوة الرابعة: أرسل المقطع الصوتي (30-60 ثانية):**", reply_markup=get_back_keyboard())

@app.on_message(filters.private & (filters.audio | filters.voice | filters.video_note))
async def receive_audio(client, message):
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id]["step"] != "waiting_audio": return

    audio = message.audio or message.voice
    duration = audio.duration
    if duration < 30 or duration > 60:
        return await message.reply_text(f"**❌ المدة غير مناسبة ({duration} ثانية). يجب أن تكون بين 30 و 60.**", reply_markup=get_back_keyboard())

    try: await message.delete()
    except: pass
    status_msg = await message.reply_text("**⏳ جاري تصميم الفيديو...**")
    
    audio_path = await message.download(file_name=f"{TEMP_DIR}/{user_id}.mp3")
    image_path = user_states[user_id]["image_path"]
    text = user_states[user_id]["text"]
    color_hex = user_states[user_id]["color"]
    processed_image_path = f"{TEMP_DIR}/processed_{user_id}.jpg"
    output_video_path = f"{TEMP_DIR}/final_{user_id}.mp4"
    
    try:
        create_cinematic_image(image_path, text, color_hex, processed_image_path)
        create_video_with_audio(processed_image_path, audio_path, output_video_path)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تصميم آخر", callback_data="start_design")], [InlineKeyboardButton("🔙 القائمة", callback_data="back_to_start")]])
        await message.reply_video(video=output_video_path, caption="**✅ تم إنشاء الفيديو بنجاح!**", reply_markup=kb)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"**❌ خطأ أثناء التصميم:**\n`{e}`", reply_markup=get_back_keyboard())
    finally:
        for path in [image_path, audio_path, processed_image_path, output_video_path]:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass
        del user_states[user_id]

# ==========================================
# 11. التشغيل
# ==========================================
if __name__ == "__main__":
    print("🎬 Memory Designer Bot is running...")
    app.run()
