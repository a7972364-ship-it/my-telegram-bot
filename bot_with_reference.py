import os, json, base64, re, time, requests
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GROQ_KEY       = "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"
VERCEL_TOKEN   = os.environ.get("VERCEL_TOKEN", "")
MY_ID          = 311728841

client = Groq(api_key=GROQ_KEY)
STYLE_FILE = "/tmp/saved_style.txt"

BASE_PROMPT = """Ты — топовый веб-дизайнер. Создавай визуально потрясающие сайты.

Формат ответа — ТОЛЬКО валидный JSON, никакого текста вне JSON:
{
  "files": {
    "index.html": "полный html код"
  },
  "summary": "1-2 предложения"
}

КРИТИЧЕСКИ ВАЖНО:
- ВЕСЬ CSS внутри тега <style> в <head> — никаких внешних файлов
- ВЕСЬ JS внутри тега <script> перед </body>
- Только внешние CDN через <script src="..."> и <link href="...">

ОБЯЗАТЕЛЬНЫЕ подключения в <head>:
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>

БАЗОВЫЕ СТИЛИ (всегда включай):
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { background: #0a0a0a; color: #ffffff; font-family: 'Inter', sans-serif; scroll-behavior: smooth; }

ДИЗАЙН:
- Акцент: градиент подобранный по теме сайта
- Карточки: background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
- Gradient text: background: linear-gradient(135deg, #X, #Y); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;

ОБЯЗАТЕЛЬНАЯ СТРУКТУРА:

1. НАВБАР (fixed):
nav { position: fixed; top: 0; width: 100%; padding: 20px 60px; display: flex; justify-content: space-between; align-items: center; backdrop-filter: blur(20px); background: rgba(10,10,10,0.8); border-bottom: 1px solid rgba(255,255,255,0.06); z-index: 1000; }

2. HERO (100vh):
- min-height: 100vh; display:flex; align-items:center; justify-content:center; text-align:center; position:relative; overflow:hidden;
- Заголовок: font-size: clamp(48px,8vw,96px); font-weight:900; letter-spacing:-3px; line-height:1.05;
- Ключевое слово в заголовке через gradient text
- Анимированный blob: position:absolute; width:600px; height:600px; border-radius:50%; filter:blur(120px); opacity:0.15; animation: blobAnim 8s ease-in-out infinite;
@keyframes blobAnim { 0%,100%{transform:translate(-50%,-50%) scale(1)} 50%{transform:translate(-40%,-60%) scale(1.2)} }

3. БЕГУЩАЯ СТРОКА тегов:
.marquee-wrap { overflow:hidden; padding:20px 0; border-top:1px solid rgba(255,255,255,0.06); border-bottom:1px solid rgba(255,255,255,0.06); }
.marquee-track { display:flex; gap:60px; animation:marquee 25s linear infinite; width:max-content; }
@keyframes marquee { from{transform:translateX(0)} to{transform:translateX(-50%)} }

4. СЕКЦИЯ ПРЕИМУЩЕСТВ: display:grid; grid-template-columns:repeat(3,1fr); gap:24px;

5. СЕКЦИЯ УСЛУГ: карточки с hover { transform:translateY(-4px); border-color:rgba(255,255,255,0.2); }

6. CTA СЕКЦИЯ: gradient background, большой заголовок, кнопка

7. ФУТЕР

КНОПКИ:
Primary: gradient background, border-radius:50px, padding:16px 40px, font-weight:600
Secondary: transparent, border:1px solid rgba(255,255,255,0.3), border-radius:50px

FADE-IN анимации через IntersectionObserver на все секции."""

STYLE_ADDON = """

СОХРАНЁННЫЙ СТИЛЬ ПОЛЬЗОВАТЕЛЯ (применяй строго):
{style_description}

Адаптируй этот стиль к новому контенту, сохраняя цвета, типографику и общее настроение."""


def load_saved_style() -> str | None:
    if os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, "r") as f:
            return f.read().strip()
    return None


def save_style(description: str):
    with open(STYLE_FILE, "w") as f:
        f.write(description)


def analyze_style(image_b64: str) -> str:
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=1000,
        messages=[
            {
                "role": "system",
                "content": "Ты дизайнер. Опиши визуальный стиль сайта на скриншоте: точные цвета фона и акцентов (hex), шрифты, размеры, отступы, стиль кнопок и карточек, анимации, общее настроение. Отвечай только описанием."
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": "Опиши визуальный стиль этого сайта максимально детально."}
                ]
            }
        ]
    )
    return response.choices[0].message.content.strip()


def build_system_prompt() -> str:
    style = load_saved_style()
    if style:
        return BASE_PROMPT + STYLE_ADDON.format(style_description=style)
    return BASE_PROMPT


def generate_site_files(user_text: str, image_b64: str | None = None) -> tuple[dict[str, str], str]:
    system = build_system_prompt()

    if image_b64:
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            {"type": "text", "text": user_text or "Создай сайт в стиле этого скриншота."}
        ]
        model = "meta-llama/llama-4-scout-17b-16e-instruct"
    else:
        content = user_text
        model   = "llama-3.3-70b-versatile"

    response = client.chat.completions.create(
        model=model,
        max_tokens=8000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": content}
        ]
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    return data.get("files", {}), data.get("summary", "Сайт готов!")


def deploy_to_vercel(files: dict[str, str]) -> str:
    vercel_files = [
        {
            "file": name,
            "data": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "encoding": "base64"
        }
        for name, content in files.items()
    ]
    resp = requests.post(
        "https://api.vercel.com/v13/deployments",
        headers={"Authorization": f"Bearer {VERCEL_TOKEN}", "Content-Type": "application/json"},
        data=json.dumps({
            "name": "my-telegram-sites",
            "files": vercel_files,
            "projectSettings": {"framework": None}
        }),
        timeout=60
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Vercel error {resp.status_code}: {resp.text[:300]}")
    url = resp.json().get("url", "")
    return ("https://" + url) if url and not url.startswith("http") else url


async def process_request(update: Update, user_text: str, image_b64: str | None = None):
    style    = load_saved_style()
    style_note = "🎨 Использую сохранённый стиль\n" if style else ""
    status   = await update.message.reply_text(f"{style_note}🤖 Создаю сайт...")
    try:
        files, summary = generate_site_files(user_text, image_b64)
        if not files:
            await status.edit_text("❌ Не удалось сгенерировать. Попробуй ещё раз.")
            return
        await status.edit_text(f"{style_note}🚀 Деплою на Vercel...")
        url = deploy_to_vercel(files)
        await status.edit_text(f"✅ Готово!\n\n🌐 {url}\n\n📝 {summary}")
    except json.JSONDecodeError:
        await status.edit_text("❌ Ошибка формата. Попробуй ещё раз.")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    style = load_saved_style()
    style_status = "✅ Стиль сохранён" if style else "⚪ Стиль не задан"
    await update.message.reply_text(
        f"👋 Создаю премиальные сайты.\n\n"
        f"{style_status}\n\n"
        f"Команды:\n"
        f"/setstyle — сохранить стиль по скриншоту\n"
        f"/clearstyle — сбросить стиль\n\n"
        f"Просто напиши что нужно сделать:"
    )


async def setstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text("📸 Отправь скриншот сайта — запомню его стиль навсегда.")
    context.user_data["waiting_for_style"] = True


async def clearstyle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    if os.path.exists(STYLE_FILE):
        os.remove(STYLE_FILE)
    await update.message.reply_text("🗑 Стиль сброшен.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await process_request(update, update.message.text.strip())


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    photo     = update.message.photo[-1]
    file      = await context.bot.get_file(photo.file_id)
    content   = await file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(content)).decode("utf-8")

    if context.user_data.get("waiting_for_style"):
        context.user_data["waiting_for_style"] = False
        status = await update.message.reply_text("🔍 Анализирую стиль...")
        try:
            description = analyze_style(image_b64)
            save_style(description)
            await status.edit_text("✅ Стиль сохранён! Все сайты теперь будут в этом стиле.\n/clearstyle — чтобы сбросить.")
        except Exception as e:
            await status.edit_text(f"❌ Ошибка: {e}")
        return

    await process_request(update, update.message.caption or "", image_b64)


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setstyle", setstyle))
    app.add_handler(CommandHandler("clearstyle", clearstyle))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен!")
    app.run_polling()
