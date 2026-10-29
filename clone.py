import logging
import os
import time
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
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

# ડમી વેબ સર્વર (Render ને ચાલુ રાખવા માટે)
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Neno Cloner Bot is Running Successfully!")

def keep_alive():
    port = int(os.environ.get('PORT', 10000))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

# પ્રોગ્રેસ બાર બતાવવા માટેનું ફંક્શન
async def progress_callback(current, total, msg, action, start_time, last_update_time):
    now = time.time()
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
            
    # લિંક પરથી ફાઈલ ડાઉનલોડ કરવી (સિંગલ અને બલ્ક બંને માટે)
    elif text.startswith('https://t.me/c/'):
        if chat_id not in user_clients:
            await event.respond("⚠️ Please send /start to log in with your number and OTP first.")
            return
            
        msg = await event.respond("⏳ Analyzing link...")
        user_client = user_clients[chat_id]
        
        try:
            parts = text.split('/')
            channel_id = int(parts[-2])
            msg_part = parts[-1]
            formatted_channel_id = int(f"-100{channel_id}")
            
            # જો લિંકમાં '198-228' જેવી રેન્જ હોય
            if '-' in msg_part:
                start_msg, end_msg = map(int, msg_part.split('-'))
                await msg.edit(f"⏳ Found bulk link! Fetching messages from {start_msg} to {end_msg}...")
                
                # લાઈનમાં બધી ફાઈલો ખેંચવા લૂપ ચલાવો
                for m_id in range(start_msg, end_msg + 1):
                    try:
                        message = await user_client.get_messages(formatted_channel_id, ids=m_id)
                        if message and message.media:
                            start_time = time.time()
                            last_update_time = [0]
                            status_msg = await event.respond(f"⏳ Downloading message {m_id}...")
                            
                            file_path = await user_client.download_media(
                                message, 
                                progress_callback=lambda c, t: progress_callback(c, t, status_msg, f"📥 Downloading {m_id}...", start_time, last_update_time)
                            )
                            
                            await status_msg.edit(f"✅ Download {m_id} complete! Uploading...")
                            start_time = time.time()
                            last_update_time = [0]
                            
                            await bot.send_file(
                                chat_id, 
                                file_path, 
                                caption=message.text or "Cloned by Neno Cloner Bot",
                                progress_callback=lambda c, t: progress_callback(c, t, status_msg, f"📤 Uploading {m_id}...", start_time, last_update_time)
                            )
                            os.remove(file_path)
                            await status_msg.delete()
                    except Exception as e:
                        await event.respond(f"⚠️ Error with message {m_id}: {e}")
                
                await msg.edit("✅ Bulk Cloning Complete!")
            
            # જો સિંગલ મેસેજની લિંક હોય
            else:
                msg_id = int(msg_part)
                message = await user_client.get_messages(formatted_channel_id, ids=msg_id)
                
                if message and message.media:
                    start_time = time.time()
                    last_update_time = [0]
                    
                    file_path = await user_client.download_media(
                        message, 
                        progress_callback=lambda c, t: progress_callback(c, t, msg, "📥 Downloading to Bot Server...", start_time, last_update_time)
                    )
                    
                    await msg.edit("✅ Download complete! Starting upload...")
                    start_time = time.time()
                    last_update_time = [0]
                    
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

# ડમી સર્વર ચાલુ કરો
keep_alive()

print("✅ Multi-User Neno Cloner Bot (With Web Server & Bulk Clone) શરૂ થઈ ગયું છે...")
bot.run_until_disconnected()
