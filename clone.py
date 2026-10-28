import logging
import os
import time
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# તારી વિગતો
API_ID = 37454672
API_HASH = '795fbda39b1dd4a2437cadbeac320fe2'
BOT_TOKEN = '9045745675:AAHTzksONddK7uYMcVpKIEHWM1nTSF-_V2s'

logging.basicConfig(level=logging.INFO)

bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

user_clients = {}
user_states = {}

# પ્રોગ્રેસ બાર બતાવવા માટેનું ફંક્શન
async def progress_callback(current, total, msg, action, start_time, last_update_time):
    now = time.time()
    # ટેલિગ્રામમાં એરર ન આવે એટલે દર 3 સેકન્ડે મેસેજ અપડેટ થશે
    if now - last_update_time[0] > 3 or current == total:
        last_update_time[0] = now
        percent = current * 100 / total if total else 0
        elapsed_time = now - start_time
        speed = current / elapsed_time if elapsed_time > 0 else 0
        eta = (total - current) / speed if speed > 0 else 0
        
        current_mb = current / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        speed_mb = speed / (1024 * 1024)
        
        filled = int(20 * current // total) if total else 0
        bar = '█' * filled + '░' * (20 - filled)
        
        text = f"**{action}**\n\n[{bar}] {percent:.1f}%\n"
        text += f"📦 Size: {current_mb:.1f}MB / {total_mb:.1f}MB\n"
        text += f"🚀 Speed: {speed_mb:.1f} MB/s\n"
        text += f"⏳ ETA: {int(eta)} sec"
        
        try:
            await msg.edit(text)
        except Exception:
            pass

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    chat_id = event.chat_id
    if chat_id in user_clients:
        await event.respond("✅ You are already logged in! Send the link of a private channel message to clone the file.")
        return
    
    user_states[chat_id] = {'step': 'phone'}
    await event.respond("Hello! I am Neno Cloner Bot.\n\nTo clone files, you first need to connect your account. Please send your **mobile number** with the country code (e.g., +91...).")

@bot.on(events.NewMessage)
async def message_handler(event):
    chat_id = event.chat_id
    text = event.text.strip()
    
    if text == '/start':
        return
        
    state = user_states.get(chat_id, {})
    step = state.get('step')
    
    # સ્ટેપ 1: મોબાઈલ નંબર લેવો
    if step == 'phone':
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            send_code_result = await client.send_code_request(text)
            user_states[chat_id] = {
                'step': 'otp',
                'client': client,
                'phone': text,
                'phone_code_hash': send_code_result.phone_code_hash
            }
            # નવો Warning વાળો મેસેજ
            await event.respond("✅ An OTP has been sent to your Telegram account.\n\n⚠️ **IMPORTANT**: Please type the OTP with spaces between each number (e.g., type 1 2 3 4 5 instead of 12345). If you send it without spaces, Telegram will expire the code!")
        except Exception as e:
            await event.respond(f"❌ Invalid number or error occurred: {e}\nPlease send /start again.")
            await client.disconnect()
            user_states.pop(chat_id, None)
            
    # સ્ટેપ 2: OTP લેવો
    elif step == 'otp':
        client = state['client']
        phone = state['phone']
        phone_code_hash = state['phone_code_hash']
        
        # OTP માંથી સ્પેસ કાઢવાનો નવો કોડ
        clean_otp = text.replace(" ", "")
        
        try:
            await client.sign_in(phone=phone, code=clean_otp, phone_code_hash=phone_code_hash)
            user_clients[chat_id] = client
            user_states.pop(chat_id, None)
            await event.respond("🎉 Login successful! Now you can send the link of a message from your joined private channel.")
        except SessionPasswordNeededError:
            user_states[chat_id]['step'] = 'password'
            await event.respond("🔒 Two-Step Verification (2FA) is enabled on your account. Please send your password here.")
        except Exception as e:
            await event.respond(f"❌ Invalid OTP or error occurred: {e}\nPlease send /start again.")
            await client.disconnect()
            user_states.pop(chat_id, None)
            
    # સ્ટેપ 3: પાસવર્ડ (જો 2FA હોય તો)
    elif step == 'password':
        client = state['client']
        try:
            await client.sign_in(password=text)
            user_clients[chat_id] = client
            user_states.pop(chat_id, None)
            await event.respond("🎉 Login successful! Now you can send the link of a message from your joined private channel.")
        except Exception as e:
            await event.respond(f"❌ Invalid password or error occurred: {e}\nPlease send /start again.")
            await client.disconnect()
            user_states.pop(chat_id, None)
            
    # લિંક પરથી ફાઈલ ડાઉનલોડ કરવી
    elif text.startswith('https://t.me/c/'):
        if chat_id not in user_clients:
            await event.respond("⚠️ Please send /start to log in with your number and OTP first.")
            return
            
        msg = await event.respond("⏳ Initializing download...")
        user_client = user_clients[chat_id]
        
        try:
            parts = text.split('/')
            channel_id = int(parts[-2])
            msg_id = int(parts[-1])
            
            formatted_channel_id = int(f"-100{channel_id}")
            message = await user_client.get_messages(formatted_channel_id, ids=msg_id)
            
            if message and message.media:
                start_time = time.time()
                last_update_time = [0]
                
                # ફાઈલ ડાઉનલોડ
                file_path = await user_client.download_media(
                    message, 
                    progress_callback=lambda c, t: progress_callback(c, t, msg, "📥 Downloading to Bot Server...", start_time, last_update_time)
                )
                
                await msg.edit("✅ Download complete! Starting upload...")
                
                start_time = time.time()
                last_update_time = [0]
                
                # ફાઈલ અપલોડ
                await bot.send_file(
                    chat_id, 
                    file_path, 
                    caption=message.text or "Cloned by Neno Cloner Bot",
                    progress_callback=lambda c, t: progress_callback(c, t, msg, "📤 Uploading to Chat...", start_time, last_update_time)
                )
                
                os.remove(file_path)
                await msg.delete()
            else:
                await msg.edit("❌ No file/media found in this link or message not found.")
        except Exception as e:
            await msg.edit(f"⚠️ Invalid link or error fetching file: {e}")

print("✅ Multi-User Neno Cloner Bot (English + Progress Bar + OTP Space Fix) શરૂ થઈ ગયું છે...")
bot.run_until_disconnected()

