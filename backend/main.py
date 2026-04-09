import asyncio
import io
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from agent import state
from agent.graph import app as agente
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# ── Handler del bot ──────────────────────────────────────────────────────────

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    mensaje = update.message.text
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id

    await context.bot.send_chat_action(chat_id, "typing")

    try:
        resultado = await asyncio.to_thread(
            agente.invoke,
            {
                "input": mensaje,
                "user_id": user_id,
                "intencion": None,
                "output": None,
                "excel_buffer": None,
                "excel_nombre": None,
            }
        )

        # ── Si hay Excel lo envía como documento ──────────────────────────
        if resultado.get("excel_buffer"):
            await context.bot.send_document(
                chat_id=chat_id,
                document=io.BytesIO(resultado["excel_buffer"]),
                filename=resultado.get("excel_nombre", "reporte.xlsx"),
                caption=resultado.get("output", "📊 Tu reporte Excel"),
            )
        else:
            respuesta = resultado.get("output") or "No pude entender tu mensaje 😅"
            await update.message.reply_text(respuesta, parse_mode="Markdown")

    except Exception as e:
        print("Error:", e)
        await update.message.reply_text("Ocurrió un error. Intenta de nuevo.")


# ── Inicializar bot ───────────────────────────────────────────────────────────

bot_app = ApplicationBuilder().token(TOKEN).updater(None).build()
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
    await bot_app.start()
    yield
    await bot_app.stop()
    await bot_app.shutdown()


# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)

@app.get("/")
def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        print("Error en webhook:", e)
        return {"ok": False, "error": str(e)}