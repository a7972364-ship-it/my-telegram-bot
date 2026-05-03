"""
Telegram Bot — генерирует сайты через Groq и деплоит на Vercel.
Поддерживает референсы: скинь скриншот сайта + описание что хочешь.

Установка:
    pip install groq python-telegram-bot requests

Использование в Telegram:
    - Просто текст:  "Лендинг для барбершопа с тёмной темой"
    - Фото + текст:  [скриншот сайта] + "сделай похожее для ресторана"
    - Только фото:   [скриншот] — скопирует стиль
"""

import json, base64, re, time, requests
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# ─── Конфигурация ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8651518107:AAFtxuF2KZDM4IeuGdf1bVb1_ZV01rcI5lk"
GROQ_KEY       = "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"
VERCEL_TOKEN   = "vcp_0RK0qObXsHx0QLrscLH0fAbpzJdfnxwkzCQLudCFy3na0zw2Qj29KfDY"
MY_ID          = 311728841
# ─────────────────────────────────────────────────────────────────────────────

client = Groq(api_key=GROQ_KEY)

SYSTEM_PROMPT = """Ты — опытный веб-разработчик. Создай сайт и верни файлы в формате JSON.

Формат ответа — ТОЛЬКО валидный JSON, никакого лишнего текста:
{
  "files": {
    "index.html": "полный html код",
    "style.css": "полный css код",
    "script.js": "полный js код если нужен"
  },
  "summary": "1-2 предложения что сделал"
}

Правила:
- Пиши красивый, современный, адаптивный код
- В index.html подключай CSS и JS через относительные пути
- Не используй внешние CDN — весь код в файлах
- Если показан скриншот референса — повтори его визуальный стиль (цвета, шрифты, отступы), но не содержимое"""


def generate_site_files(user_text: str, image_b64: str | None = None) -> tuple[dict[str, str], str]:
    if image_b64:
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
            },
            {
                "type": "text",
                "text": user_text or "Проанализируй стиль на скриншоте и создай новый сайт в таком же стиле."
            }
        ]
        model = "meta-llama/llama-4-scout-17b-16e-instruct"
    else:
        content = user_text
        model   = "llama-3.3-70b-versatile"

    response = client.chat.completions.create(
        model=model,
        max_tokens=8000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": content}
        ]
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data    = json.loads(raw)
    files   = data.get("files", {})
    summary = data.get("summary", "Сайт готов!")
    return files, summary


def deploy_to_vercel(files: dict[str, str], project_name: str) -> str:
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
        data=json.dumps({"name": project_name, "files": vercel_files, "projectSettings": {"framework": None}}),
        timeout=60
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Vercel error {resp.status_code}: {resp.text[:300]}")
    url = resp.json().get("url", "")
    return ("https://" + url) if url and not url.startswith("http") else url


def make_project_name(text: str) -> str:
    slug   = re.sub(r"[^a-z0-9]+", "-", text.lower())[:28].strip("-")
    suffix = int(time.time()) % 10000
    return f"tg-{slug}-{suffix}" if slug else f"tg-site-{suffix}"


async def process_request(update: Update, user_text: str, image_b64: str | None = None):
    status = await update.message.reply_text("⏳ Начинаю...")
    try:
        if image_b64:
            await status.edit_text("🤖 Groq анализирует скриншот и пишет код...")
        else:
            await status.edit_text("🤖 Groq пишет код...")

        files, summary = generate_site_files(user_text, image_b64)

        if not files:
            await status.edit_text("❌ Не удалось сгенерировать файлы. Попробуй переформулировать.")
            return

        file_list = ", ".join(files.keys())
        await status.edit_text(f"🚀 Деплою на Vercel ({file_list})...")

        url = deploy_to_vercel(files, make_project_name(user_text or "site"))

        ref_note = "🎨 Использован твой скриншот как референс\n" if image_b64 else ""
        await status.edit_text(
            f"✅ Готово!\n\n"
            f"🌐 {url}\n\n"
            f"{ref_note}"
            f"📝 {summary}\n\n"
            f"📁 Файлы: {file_list}"
        )
    except json.JSONDecodeError:
        await status.edit_text("❌ Groq вернул неверный формат. Попробуй ещё раз.")
    except Exception as e:
        await status.edit_text(f"❌ Ошибка: {e}")
        raise


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    await update.message.reply_text(
        "👋 Привет! Я создаю сайты и деплою их на Vercel.\n\n"
        "Как использовать:\n"
        "• Текст: _Лендинг для кофейни с тёмной темой_\n"
        "• 📷 Скриншот: бот повторит стиль\n"
        "• 📷 Скриншот + подпись: стиль + твоё описание",
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    user_text = update.message.text.strip()
    if user_text:
        await process_request(update, user_text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    photo     = update.message.photo[-1]
    file      = await context.bot.get_file(photo.file_id)
    content   = await file.download_as_bytearray()
    image_b64 = base64.b64encode(bytes(content)).decode("utf-8")
    user_text = update.message.caption or ""

    await process_request(update, user_text, image_b64)


if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("✅ Бот запущен! Только для пользователя", MY_ID)
    app.run_polling()
