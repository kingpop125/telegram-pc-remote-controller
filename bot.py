import os
import sys
import io
import hashlib
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

# تجنب مشاكل ترميز اللغة العربية والرموز التعبيرية في سطر الأوامر على ويندوز
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass
import json
import time
import subprocess
import webbrowser
import contextlib
import logging
import telebot
from PIL import Image
import pyautogui

# تهيئة التسجيل (Logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TelegramPCController")

# استيراد الإعدادات
try:
    import config
except ImportError:
    logger.error("لم يتم العثور على ملف config.py. يرجى إنشاؤه أولاً.")
    sys.exit(1)

# التحقق من رمز البوت
if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("\n" + "="*60)
    print("تنبيه: يرجى وضع رمز الوصول الخاص بالبوت TELEGRAM_BOT_TOKEN في ملف config.py")
    print("="*60 + "\n")
    # سنقوم بتهيئة البوت برمز فارغ ولكن لن يعمل حتى يتم تعديله
    BOT_TOKEN = "INVALID"
else:
    BOT_TOKEN = config.TELEGRAM_BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)

# ------------------------------------------------------------------------
# إعدادات وظائف التشفير وفك التشفير End-to-End (E2EE)
# ------------------------------------------------------------------------

def is_encryption_enabled():
    """التحقق مما إذا كان تشفير E2EE مفعلاً في الإعدادات"""
    return hasattr(config, 'ENCRYPTION_PASSWORD') and config.ENCRYPTION_PASSWORD != ""

def encrypt_data(data_bytes: bytes, password: str) -> str:
    """تشفير البيانات باستخدام AES-256-CBC متوافق مع CryptoJS"""
    key = hashlib.sha256(password.encode()).digest()
    iv = hashlib.md5(password.encode()).digest()
    
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data_bytes) + padder.finalize()
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded_data) + encryptor.finalize()
    
    return base64.b64encode(encrypted).decode()

def decrypt_data(encrypted_b64: str, password: str) -> bytes:
    """فك تشفير البيانات باستخدام AES-256-CBC متوافق مع CryptoJS"""
    key = hashlib.sha256(password.encode()).digest()
    iv = hashlib.md5(password.encode()).digest()
    
    encrypted = base64.b64decode(encrypted_b64)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(encrypted) + decryptor.finalize()
    
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded_data) + unpadder.finalize()

def send_secure_reply(message, text):
    """إرسال رد مشفر إذا كان التشفير مفعلاً، أو رد عادي إذا كان معطلاً"""
    if is_encryption_enabled():
        try:
            encrypted_text = encrypt_data(text.encode('utf-8'), config.ENCRYPTION_PASSWORD)
            return bot.reply_to(message, encrypted_text)
        except Exception as e:
            logger.error(f"خطأ أثناء تشفير الرد: {e}")
            return bot.reply_to(message, f"❌ خطأ داخلي أثناء تشفير الرد: {e}")
    else:
        return bot.reply_to(message, text, parse_mode="Markdown")

def edit_secure_reply(chat_id, message_id, text):
    """تعديل رسالة برد مشفر إذا كان التشفير مفعلاً، أو رد عادي إذا كان معطلاً"""
    if is_encryption_enabled():
        try:
            encrypted_text = encrypt_data(text.encode('utf-8'), config.ENCRYPTION_PASSWORD)
            return bot.edit_message_text(encrypted_text, chat_id, message_id)
        except Exception as e:
            logger.error(f"خطأ أثناء تشفير التعديل: {e}")
            return bot.edit_message_text(f"❌ خطأ داخلي أثناء تشفير الرد: {e}", chat_id, message_id)
    else:
        return bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown")

# إعداد مكتبة Gemini
HAS_GEMINI = False
if config.GEMINI_API_KEY and config.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    try:
        import google.generativeai as genai
        genai.configure(api_key=config.GEMINI_API_KEY)
        HAS_GEMINI = True
        logger.info("تم تفعيل ذكاء Gemini الاصطناعي بنجاح.")
    except Exception as e:
        logger.error(f"خطأ أثناء تهيئة Gemini: {e}")

# ------------------------------------------------------------------------
# دوال المساعدة والأمان
# ------------------------------------------------------------------------

def is_authorized(message):
    """التحقق مما إذا كان المستخدم مصرحاً له بالتحكم بالجهاز"""
    user_id = message.from_user.id
    if user_id in config.ALLOWED_USER_IDS:
        return True
    return False

def unauthorized_reply(message):
    """الرد على المستخدم غير المصرح له وعرض معرّف حسابه"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or "لا يوجد"
    
    reply_text = (
        f"⚠️ **وصول غير مصرح به!**\n\n"
        f"جهاز الكمبيوتر محمي ولا يستقبل أوامر إلا من الحسابات المصرح لها فقط.\n\n"
        f"👤 اسم المستخدم: @{username}\n"
        f"🆔 معرف حسابك (Chat ID): `{user_id}`\n\n"
        f"🔑 لتفعيل التحكم، قم بنسخ هذا المعرف `{user_id}` وضعه داخل قائمة `ALLOWED_USER_IDS` في ملف `config.py` على جهازك، ثم أعد تشغيل البوت."
    )
    bot.reply_to(message, reply_text, parse_mode="Markdown")
    logger.warning(f"محاولة وصول غير مصرح بها من: UserID={user_id}, Username={username}")

def execute_python_code(code_string, bot_instance=None, message_obj=None):
    """تنفيذ كود بايثون محلياً والتقاط النتائج ومخرجات الطباعة"""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    # تجهيز المكتبات الشائعة لتكون متاحة للكود المولد مباشرة
    local_globals = {
        'os': os,
        'sys': sys,
        'subprocess': subprocess,
        'webbrowser': webbrowser,
        'time': time,
        'pyautogui': pyautogui,
        'telebot': telebot,
        'Image': Image,
        'json': json,
        'bot': bot_instance,
        'message': message_obj,
    }
    
    start_time = time.time()
    try:
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            exec(code_string, local_globals)
        
        stdout_val = stdout_capture.getvalue()
        stderr_val = stderr_capture.getvalue()
        duration = time.time() - start_time
        
        return True, stdout_val, stderr_val, duration
    except Exception as e:
        duration = time.time() - start_time
        return False, stdout_capture.getvalue(), f"{str(e)}\n{stderr_capture.getvalue()}", duration

# ------------------------------------------------------------------------
# معالجة أوامر التليجرام
# ------------------------------------------------------------------------

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    
    # إذا لم يكن مسجلاً، نعرض له الـ ID حقه ليسهل عليه إعداده
    if not is_authorized(message):
        unauthorized_reply(message)
        return
        
    welcome_text = (
        f"👋 أهلاً بك! الكمبيوتر الخاص بك جاهز لتلقي الأوامر.\n\n"
        f"🤖 **الأوامر المتاحة:**\n"
        f"📸 `/screenshot` - لالتقاط صورة لشاشة الكمبيوتر الحالية وإرسالها لك.\n"
        f"💻 `/cmd <الأمر>` - لتشغيل أمر مباشرة في Command Prompt (مثال: `/cmd dir`).\n"
        f"📜 `/history` - لاستعراض سجل المحادثة الكاملة التي دارت بيننا في ورشة العمل (IDE).\n"
        f"🧠 `/ai <طلبك باللغة الطبيعية>` - لتنفيذ أي طلب ذكي عبر Gemini (مثال: `/ai افتح يوتيوب وابحث عن برمجة`).\n\n"
        f"💬 **ملاحظة:** يمكنك أيضاً إرسال أي رسالة نصية عادية مباشرة وسأقوم بتفسيرها وتنفيذها باستخدام الذكاء الاصطناعي!"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['screenshot'])
def take_screenshot(message, decrypted_text=None):
    if not is_authorized(message):
        unauthorized_reply(message)
        return
        
    if is_encryption_enabled() and decrypted_text is None:
        send_secure_reply(message, "⚠️ التشفير E2EE مفعّل! يجب تشفير هذا الأمر وإرساله كنص مشفر.")
        return
        
    status_msg = send_secure_reply(message, "📸 جاري التقاط شاشة الكمبيوتر...")
    
    temp_path = "temp_screenshot.png"
    try:
        # التقاط الشاشة
        screenshot = pyautogui.screenshot()
        screenshot.save(temp_path)
        
        if is_encryption_enabled():
            # تشفير ملف الصورة
            with open(temp_path, 'rb') as f:
                img_bytes = f.read()
            enc_base64 = encrypt_data(img_bytes, config.ENCRYPTION_PASSWORD)
            
            enc_file_path = "screenshot.enc"
            with open(enc_file_path, 'w', encoding='utf-8') as f:
                f.write(enc_base64)
                
            with open(enc_file_path, 'rb') as enc_file:
                bot.send_document(message.chat.id, enc_file, caption="🔒 لقطة شاشة مشفرة (E2EE). استخدم أداة فك التشفير لعرضها.")
            os.remove(enc_file_path)
        else:
            # إرسال الصورة مباشرة
            with open(temp_path, 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption="💻 شاشة الكمبيوتر الحالية")
            
        bot.delete_message(message.chat.id, status_msg.message_id)
    except Exception as e:
        edit_secure_reply(message.chat.id, status_msg.message_id, f"❌ فشل التقاط الشاشة: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

@bot.message_handler(commands=['cmd'])
def run_command(message, decrypted_text=None):
    if not is_authorized(message):
        unauthorized_reply(message)
        return
        
    if is_encryption_enabled() and decrypted_text is None:
        send_secure_reply(message, "⚠️ التشفير E2EE مفعّل! يجب تشفير هذا الأمر وإرساله كنص مشفر.")
        return
        
    text_to_parse = decrypted_text if decrypted_text else message.text
    cmd_parts = text_to_parse.split(" ", 1)
    if len(cmd_parts) < 2:
        send_secure_reply(message, "⚠️ يرجى كتابة الأمر بعد الاختصار، مثال:\n`/cmd dir`")
        return
        
    cmd_to_run = cmd_parts[1]
    status_msg = send_secure_reply(message, f"⚙️ جاري تشغيل الأمر:\n`{cmd_to_run}`...")
    
    try:
        # تنفيذ الأمر
        result = subprocess.run(
            cmd_to_run,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='ignore'
        )
        
        output = result.stdout
        error = result.stderr
        
        response_text = ""
        if output:
            response_text += f"**المخرجات (Output):**\n```\n{output}\n```\n"
        if error:
            response_text += f"**الأخطاء (Errors):**\n```\n{error}\n```\n"
        if not output and not error:
            response_text = "✅ تم تنفيذ الأمر بنجاح ولكن لم ينتج عنه أي مخرجات نصية."
            
        # إذا كانت المخرجات طويلة جداً، نرسلها كملف نصي لتجنب تجاوز حد رسائل التليجرام
        if len(response_text) > 3500:
            if is_encryption_enabled():
                raw_file_content = f"Command: {cmd_to_run}\n\nSTDOUT:\n{output}\n\nSTDERR:\n{error}"
                enc_content = encrypt_data(raw_file_content.encode('utf-8'), config.ENCRYPTION_PASSWORD)
                file_output = io.BytesIO(enc_content.encode('utf-8'))
                file_output.name = "output.enc"
                bot.send_document(message.chat.id, file_output, caption="🔒 مخرجات الأمر طويلة ومشفّرة (E2EE).")
            else:
                file_output = io.BytesIO(f"Command: {cmd_to_run}\n\nSTDOUT:\n{output}\n\nSTDERR:\n{error}".encode('utf-8'))
                file_output.name = "output.txt"
                bot.send_document(message.chat.id, file_output, caption="📄 مخرجات الأمر طويلة وتم إرسالها كملف.")
            bot.delete_message(message.chat.id, status_msg.message_id)
        else:
            edit_secure_reply(message.chat.id, status_msg.message_id, response_text)
            
    except subprocess.TimeoutExpired:
        edit_secure_reply(message.chat.id, status_msg.message_id, "❌ انتهت مهلة التنفيذ (تجاوزت 30 ثانية).")
    except Exception as e:
        edit_secure_reply(message.chat.id, status_msg.message_id, f"❌ حدث خطأ أثناء التنفيذ: {str(e)}")

@bot.message_handler(commands=['history'])
def send_history(message, decrypted_text=None):
    if not is_authorized(message):
        unauthorized_reply(message)
        return
        
    if is_encryption_enabled() and decrypted_text is None:
        send_secure_reply(message, "⚠️ التشفير E2EE مفعّل! يجب تشفير هذا الأمر وإرساله كنص مشفر.")
        return
        
    status_msg = send_secure_reply(message, "📜 جاري استخراج تاريخ المحادثة التي دارت بيننا في ورشة العمل...")
    
    log_path = os.path.join(config.BRAIN_DIR, config.CURRENT_CONVERSATION_ID, ".system_generated", "logs", "transcript.jsonl")
    
    if not os.path.exists(log_path):
        edit_secure_reply(message.chat.id, status_msg.message_id, f"❌ لم يتم العثور على ملف سجلات المحادثة على الكمبيوتر.\nالمسار: `{log_path}`")
        return
        
    try:
        history = []
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    step = json.loads(line)
                    step_type = step.get("type")
                    source = step.get("source")
                    content = step.get("content")
                    
                    # We look for user messages and model outputs
                    if step_type == "USER_INPUT":
                        history.append(f"👤 المستخدم:\n{content}")
                    elif step_type == "PLANNER_RESPONSE" or source == "MODEL" or step_type == "PLANNER_RESPONSE_RAW":
                        if content and not content.startswith("{"):
                            history.append(f"🤖 Antigravity:\n{content}")
                except Exception:
                    continue
                    
        if not history:
            edit_secure_reply(message.chat.id, status_msg.message_id, "ℹ️ سجل المحادثة فارغ حالياً.")
            return
            
        # Send full history as text file
        full_text = "\n\n" + "="*50 + "\n\n"
        full_text += "\n\n" + "="*50 + "\n\n".join(history)
        
        if is_encryption_enabled():
            enc_content = encrypt_data(full_text.encode('utf-8'), config.ENCRYPTION_PASSWORD)
            file_output = io.BytesIO(enc_content.encode('utf-8'))
            file_output.name = "IDE_Chat_History.enc"
            bot.send_document(message.chat.id, file_output, caption="🔒 السجل الكامل للمحادثة مشفر (E2EE).")
        else:
            file_output = io.BytesIO(full_text.encode('utf-8'))
            file_output.name = "IDE_Chat_History.txt"
            bot.send_document(message.chat.id, file_output, caption="📄 السجل الكامل للمحادثة البرمجية بيننا في الـ IDE.")
            
        # Send latest 5 messages directly
        latest_msgs = history[-6:]
        summary_text = "📜 **آخر الرسائل في محادثة ورشة العمل:**\n\n" + "\n\n".join(latest_msgs)
        if len(summary_text) > 3000:
            summary_text = summary_text[:3000] + "\n\n...(الباقي في الملف المرفق)"
            
        edit_secure_reply(message.chat.id, status_msg.message_id, summary_text)
        
    except Exception as e:
        edit_secure_reply(message.chat.id, status_msg.message_id, f"❌ حدث خطأ أثناء قراءة سجل المحادثات: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_text_or_ai(message):
    if not is_authorized(message):
        unauthorized_reply(message)
        return
        
    # فك تشفير الرسالة القادمة إذا كان تشفير E2EE مفعلاً
    if is_encryption_enabled():
        try:
            decrypted_bytes = decrypt_data(message.text.strip(), config.ENCRYPTION_PASSWORD)
            user_prompt = decrypted_bytes.decode('utf-8')
        except Exception:
            # إذا فشل فك التشفير، نرسل تنبيهاً ونرفض التنفيذ
            bot.reply_to(
                message,
                "⚠️ **تنبيه أمني: رسالة غير صالحة أو مشفرة بكلمة مرور خاطئة!**\n\n"
                "التشفير ثنائي الأطراف (E2EE) مفعّل على جهازك. يرجى استخدام أداة [encryptor.html](file:///c:/NEW/encryptor.html) لتشفيير أوامرك قبل إرسالها."
            )
            return
    else:
        user_prompt = message.text

    # توجيه الرسالة إذا كانت عبارة عن أمر تم تشفيره وإرساله كنص
    if user_prompt.startswith('/screenshot'):
        take_screenshot(message, decrypted_text=user_prompt)
        return
    elif user_prompt.startswith('/cmd'):
        run_command(message, decrypted_text=user_prompt)
        return
    elif user_prompt.startswith('/history'):
        send_history(message, decrypted_text=user_prompt)
        return
    elif user_prompt.startswith('/ai '):
        user_prompt = user_prompt[4:]
    elif user_prompt.startswith('/'):
        send_secure_reply(message, "⚠️ أمر غير معروف أو صيغة خاطئة.")
        return

    if not HAS_GEMINI:
        send_secure_reply(
            message,
            "⚠️ **الذكاء الاصطناعي غير مفعل حالياً.**\n\n"
            "لتفعيل ميزة الأوامر الذكية، يرجى الحصول على مفتاح Gemini API مجاني ووضعه في ملف `config.py` كـ `GEMINI_API_KEY`.\n\n"
            "💡 يمكنك استخدام الأوامر المباشرة الآن مثل:\n"
            "📸 `/screenshot` أو 💻 `/cmd dir`"
        )
        return
        
    status_msg = send_secure_reply(message, "🧠 جاري التفكير وتحليل طلبك باستخدام الذكاء الاصطناعي...")
    
    # صياغة نص التوجيه للـ AI لضمان الحصول على كود بايثون نظيف وموثوق
    prompt_instruction = (
        "You are Antigravity, a powerful agentic AI coding assistant designed by Google DeepMind, running locally on the user's Windows PC.\n"
        "You have two modes of response based on the user's input:\n"
        "1. Chat Mode: If the user is just conversing, asking questions, chatting, or asking for code explanations (without requesting to execute anything on the PC), reply friendly in Arabic. Set the \"code\" field to an empty string \"\" and put your chat response in \"explanation\". Do not include instructions about command execution in this case.\n"
        "2. Command/Action Mode: If the user asks to perform an action on the PC (e.g. open apps, take screenshots, run scripts, check status), write a Python script to do it in the \"code\" field and explain what you will do in \"explanation\" in Arabic.\n\n"
        "Output format MUST be a single raw JSON object containing:\n"
        "{\n"
        "  \"explanation\": \"Your response or explanation in Arabic\",\n"
        "  \"code\": \"Python code here or empty string if just chatting\"\n"
        "}\n\n"
        "Guidelines for the Python \"code\" (when executing actions):\n"
        "- Use standard libraries like os, subprocess, webbrowser, time, socket, etc.\n"
        "- You can use pyautogui for GUI interactions.\n"
        "- Predefined globals available: 'bot' (the telebot instance) and 'message' (the current Telegram message object). You can send photos/documents directly back to the user, for example: `with open('screenshot.png', 'rb') as f: bot.send_photo(message.chat.id, f)`\n"
        "- Write print statements in the code to log progress and results. Any output printed to stdout will be returned to the user.\n"
        "- Handle exceptions within the code.\n"
        "- DO NOT perform destructive actions like deleting system files, formatting drives, or shutting down unless explicitly asked.\n"
        "- Keep the script concise.\n"
        "Return ONLY a valid JSON object. Do not include markdown code block formatting (like ```json) in your raw response.\n\n"
        f"User request: {user_prompt}"
    )
    
    try:
        # استدعاء نموذج Gemini
        model = genai.GenerativeModel('gemini-3.5-flash')
        response = model.generate_content(prompt_instruction)
        
        # تنظيف الاستجابة للحصول على JSON صالح
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            ai_data = json.loads(response_text)
            explanation = ai_data.get("explanation", "جاري التنفيذ...")
            code_to_run = ai_data.get("code", "")
        except Exception as json_err:
            logger.error(f"فشل تحليل الـ JSON من استجابة الذكاء الاصطناعي: {json_err}. الاستجابة الأصلية: {response_text}")
            edit_secure_reply(message.chat.id, status_msg.message_id, "❌ حدث خطأ أثناء تحليل إجابة الذكاء الاصطناعي. يرجى المحاولة مرة أخرى بصياغة مختلفة.")
            return

        if not code_to_run:
            edit_secure_reply(message.chat.id, status_msg.message_id, explanation)
            return
            
        # تحديث الرسالة بشرح ما سيفعله البوت
        edit_secure_reply(message.chat.id, status_msg.message_id, f"⚙️ **{explanation}**\n\nجاري تشغيل الكود البرمجي...")
        
        # تنفيذ الكود البرمجي
        success, stdout_val, stderr_val, duration = execute_python_code(code_to_run, bot, message)
        
        # صياغة التقرير النهائي
        report = f"📋 **تقرير تنفيذ الطلب:**\n"
        report += f"👤 الطلب: \"{user_prompt}\"\n"
        report += f"⏱️ مدة التنفيذ: {duration:.2f} ثانية\n\n"
        
        if success:
            report += "✅ **تم التنفيذ بنجاح!**\n"
            if stdout_val:
                report += f"\n**النتائج:**\n```\n{stdout_val.strip()}\n```"
        else:
            report += "❌ **فشل التنفيذ أو حدث خطأ:**\n"
            if stdout_val:
                report += f"\n**مخرجات التشغيل:**\n```\n{stdout_val.strip()}\n```"
            report += f"\n**تفاصيل الخطأ:**\n```\n{stderr_val.strip()}\n```"
            
        # إرسال التقرير النهائي
        if len(report) > 3500:
            if is_encryption_enabled():
                raw_report = f"Prompt: {user_prompt}\n\nCode Executed:\n{code_to_run}\n\nSTDOUT:\n{stdout_val}\n\nSTDERR:\n{stderr_val}"
                enc_report = encrypt_data(raw_report.encode('utf-8'), config.ENCRYPTION_PASSWORD)
                file_output = io.BytesIO(enc_report.encode('utf-8'))
                file_output.name = "ai_report.enc"
                bot.send_document(message.chat.id, file_output, caption="🔒 تقرير التنفيذ طويل ومشفّر (E2EE).")
            else:
                file_output = io.BytesIO(f"Prompt: {user_prompt}\n\nCode Executed:\n{code_to_run}\n\nSTDOUT:\n{stdout_val}\n\nSTDERR:\n{stderr_val}".encode('utf-8'))
                file_output.name = "ai_report.txt"
                bot.send_document(message.chat.id, file_output, caption="📄 تقرير التنفيذ طويل وتم إرساله كملف.")
            bot.delete_message(message.chat.id, status_msg.message_id)
        else:
            edit_secure_reply(message.chat.id, status_msg.message_id, report)
            
    except Exception as e:
        edit_secure_reply(message.chat.id, status_msg.message_id, f"❌ حدث خطأ أثناء معالجة الطلب عبر الذكاء الاصطناعي: {str(e)}")

# ------------------------------------------------------------------------
# تشغيل البوت
# ------------------------------------------------------------------------
if __name__ == "__main__":
    if BOT_TOKEN == "INVALID":
        print("\n" + "!"*60)
        print("يرجى ملء الإعدادات أولاً في config.py ثم إعادة التشغيل.")
        print("!"*60 + "\n")
        sys.exit(1)
        
    print("\n" + "="*60)
    print("🚀 البوت يعمل الآن ويستمع للأوامر من التليجرام...")
    print("إذا كان هذا التشغيل الأول، أرسل رسالة للبوت ليعطيك الـ Chat ID الخاص بك.")
    print("="*60 + "\n")
    
    try:
        while True:
            try:
                bot.polling(none_stop=True, interval=0, timeout=20)
            except Exception as poll_err:
                logger.error(f"خطأ في الاتصال مع تليجرام، إعادة المحاولة بعد 5 ثوانٍ: {poll_err}")
                time.sleep(5)
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت بنجاح.")
