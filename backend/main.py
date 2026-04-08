import asyncio
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from agent.graph import app as agente
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os

# ── Cargar variables de entorno tenv() ──────
load_dotenv()
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Asegúrate de tener esta variable en tu .env

# ── Handler del bot ──────────────────────────────────────────────────────────

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    mensaje = update.message.text
    user_id = update.message.from_user.id

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        resultado = await asyncio.to_thread(
            agente.invoke,
            {"input": mensaje, "user_id": user_id, "intencion": None, "output": None}
        )
        respuesta = resultado.get("output") or "No pude entender tu mensaje 😅"
    except Exception as e:
        print("Error:", e)
        respuesta = "Ocurrió un error. Intenta de nuevo."

    await update.message.reply_text(respuesta)


# ── Inicializar bot ───────────────────────────────────────────────────────────

bot_app = ApplicationBuilder().token(TOKEN).updater(None).build()
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))


# ── Lifespan: arranca y para el bot junto con FastAPI ────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al iniciar el servidor
    await bot_app.initialize()
    await bot_app.bot.set_webhook(
        url=WEBHOOK_URL
    )
    await bot_app.start()
    yield
    # Al apagar el servidor
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