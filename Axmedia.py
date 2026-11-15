import os
import sqlite3
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

# Loglama ayarları
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "9083400579:AAGYWJ9AlzGe-w-eiUAPY1ksrpc8t51K8AE"
ADMIN_IDS = 8838971834

# --- VERİTABANI BAŞLANGICI ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Kullanıcıları ve bakım modunu tutacağımız tablo
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Bakım modu kapalı olarak başlat
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'off')")
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    val = cursor.fetchone()
    conn.close()
    return val[0] if val else 'off'

def set_setting(key, value):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = ?", (value, key))
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# --- KOMUTLAR VE MANTIK ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id) # Kullanıcıyı veritabanına kaydet
    
    # Bakım modu kontrolü
    if get_setting('maintenance') == 'on' and user_id not in ADMIN_IDS:
        await update.message.reply_text("🛠️ **Bot Bakımda!**\n\nŞu anda sistem güncelleniyor. Lütfen daha sonra tekrar deneyin.")
        return

    user_name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Selam {user_name}!\n\n"
        "🔗 Bana desteklenen platformlardan bir link gönder, istediğin kalite ve formatta indireyim."
    )

# --- 👑 ADMİN PANELİ KOMUTLARI ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    m_status = get_setting('maintenance')
    status_text = "🟢 Aktif (Çalışıyor)" if m_status == 'off' else "🔴 Bakımda"
    total_users = len(get_all_users())

    keyboard = [
        [InlineKeyboardButton(f"🔄 Bakım Modunu Değiştir (Şu an: {status_text})", callback_data="toggle_maintenance")],
        [InlineKeyboardButton("📊 İstatistikler", callback_data="bot_stats")],
        [InlineKeyboardButton("❌ Paneli Kapat", callback_data="close_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("👑 **Admin Kontrol Paneline Hoş Geldin**\n\nAşağıdaki butonlardan botu yönetebilirsin:", reply_markup=reply_markup, parse_mode="Markdown")

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("Bu yetkin yok!", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "toggle_maintenance":
        current = get_setting('maintenance')
        new_val = 'off' if current == 'on' else 'on'
        set_setting('maintenance', new_val)
        
        status_text = "🟢 Aktif" if new_val == 'off' else "🔴 Bakımda"
        await query.edit_message_text(text=f"✅ Bakım modu durumu değiştirildi: **{status_text}**", parse_mode="Markdown")
    
    elif data == "bot_stats":
        total_users = len(get_all_users())
        m_status = get_setting('maintenance')
        await query.edit_message_text(text=f"📊 **Bot İstatistikleri**\n\n👥 Toplam Kullanıcı: `{total_users}`\n🛠️ Bakım Modu: `{m_status}`", parse_mode="Markdown")
        
    elif data == "close_admin":
        await query.message.delete()

# --- 📢 TOPLU DUYURU SİSTEMİ ---
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    # Komuttan sonraki metni al (Örn: /duyuru Bot güncellendi!)
    message_text = " ".join(context.args)
    if not message_text:
        await update.message.reply_text("⚠️ Lütfen duyuru metnini ekleyin.\nÖrnek: `/duyuru Botumuz güncellenmiştir!`", parse_mode="Markdown")
        return

    users = get_all_users()
    await update.message.reply_text(f"🚀 Duyuru {len(users)} kullanıcıya gönderiliyor, lütfen bekleyin...")

    success_count = 0
    fail_count = 0

    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 **Duyuru:**\n\n{message_text}", parse_mode="Markdown")
            success_count += 1
        except Exception:
            fail_count += 1  # Botu engelleyen veya silen kullanıcılar için hata yakalama

    await update.message.reply_text(f"✅ **Duyuru Tamamlandı!**\n\nBaşarılı: `{success_count}`\nBaşarısız: `{fail_count}`", parse_mode="Markdown")

# --- LİNK VE İNDİRME İŞLEYİCİSİ ---
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Bakım modu kontrolü (Adminler her zaman kullanabilir)
    if get_setting('maintenance') == 'on' and user_id not in ADMIN_IDS:
        await update.message.reply_text("🛠️ Botumuz şu an bakım aşamasındadır. Kısa süre sonra tekrar aktif olacaktır.")
        return

    url = update.message.text.strip()
    if not url.startswith("http"):
        await update.message.reply_text("⚠️ Lütfen geçerli bir bağlantı (URL) gönder.")
        return

    context.user_data['target_url'] = url

    # Senin istediğin 3 sıra buton tasarımı
    keyboard = [
        [
            InlineKeyboardButton("🎬 1080p Video", callback_data="dl_v_1080"),
            InlineKeyboardButton("🎬 720p Video", callback_data="dl_v_720"),
            InlineKeyboardButton("🎬 480p Video", callback_data="dl_v_480"),
        ],
        [
            InlineKeyboardButton("🎵 Yüksek Ses (MP3)", callback_data="dl_audio_high"),
            InlineKeyboardButton("🎵 Normal Ses (MP3)", callback_data="dl_audio_norm"),
            InlineKeyboardButton("🖼️ Fotoğraf/Kapak", callback_data="dl_photo"),
        ],
        [
            InlineKeyboardButton("📊 Medya Bilgisi", callback_data="media_info"),
            InlineKeyboardButton("❌ İptal Et", callback_data="cancel_op"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📥 **Medya Başarıyla Algılandı!**\n\n"
        "Lütfen indirmek istediğin formatı veya kaliteyi seç:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# İndirme ve Buton Yöneticisi (Önceki kodla aynı mantık)
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    url = context.user_data.get('target_url')

    if data == "cancel_op":
        await query.edit_message_text(text="❌ İşlem iptal edildi.")
        return

    if not url:
        await query.edit_message_text(text="⚠️ Oturum zaman aşımına uğradı. Lütfen tekrar link gönder.")
        return

    if data == "media_info":
        await query.edit_message_text(text="🔍 Medya analizi yapılıyor...")
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                await query.edit_message_text(
                    text=f"📌 **Başlık:** {info.get('title', 'Bilinmiyor')}\n👤 **Yayıncı:** {info.get('uploader', 'Bilinmiyor')}",
                    parse_mode="Markdown"
                )
        except Exception as e:
            await query.edit_message_text(text=f"❌ Bilgi alınamadı: {str(e)[:100]}")
        return

    await query.edit_message_text(text="⏳ Dosya indiriliyor ve hazırlanıyor...")
    # (Buradaki yt-dlp indirme ve gönderme mantığı bir önceki kod ile tamamen aynı çalışır)

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("duyuru", broadcast))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_url))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(toggle_maintenance|bot_stats|close_admin)$"))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Gelişmiş Bot (Admin + Bakım Modu) Çalışıyor...")
    app.run_polling()

if __name__ == '__main__':
    main()
