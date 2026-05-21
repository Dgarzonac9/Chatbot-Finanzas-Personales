 <div align="center">

<img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" />
<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
<img src="https://img.shields.io/badge/LangGraph-Agent-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" />
<img src="https://img.shields.io/badge/Groq-LLM-F55036?style=for-the-badge" />
<img src="https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white" />

<br/><br/>

# Chatbot de Finanzas Personales

### Tu asistente financiero en Telegram. Sin apps. Sin formularios. Solo escríbele.

Dile **"gasté 10k en comida"** y lo registra. Pregúntale **"cómo voy este mes"** y te responde con tu balance completo. Créa una **vaca** con tus amigos para el asado del fin de semana, gestiona **préstamos**, controla **deudas** y descarga todo en **Excel** cuando quieras.

<br/>

[![Probar el bot](https://img.shields.io/badge/🤖_Probar_en_Telegram-@TakeYourFinancesBot-26A5E4?style=for-the-badge&logo=telegram)](https://t.me/TakeYourFinancesBot)

</div>

---

## ¿Por qué existe este proyecto?

Las apps de finanzas personales tienen todas el mismo problema de adopción: hay que recordar abrirlas, navegar menús y llenar formularios. Nadie lo hace consistentemente.

Este bot vive donde ya estás — **Telegram** — y entiende lenguaje natural. No hay comandos que memorizar. Le escribís como le escribirías a un amigo y él se encarga del resto: registrar, calcular, reportar. Por debajo corre un **agente LangGraph** que interpreta la intención del mensaje, decide qué operación ejecutar y responde en lenguaje natural también.

---

## Demo

<div align="center">

| Gastos · Ingresos · Presupuesto | Vacas · Préstamos | Reporte de Vacas · Excel | Reporte del día |
|:---:|:---:|:---:|:---:|
| <img src="assets/screenshots/demo1.jpeg" width="200"/> | <img src="assets/screenshots/demo2.jpeg" width="200"/> | <img src="assets/screenshots/demo3.jpeg" width="200"/> | <img src="assets/screenshots/demo4.jpeg" width="200"/> |

</div>

---

## Comandos y ejemplos reales

El bot no tiene comandos fijos — interpreta lo que escribís. Estos son ejemplos de lo que entiende:

### Gastos
```
"gasté 10k en comida"
"me gasté 10k en comida y 20k en netflix"
"pagué 80 de transporte"
```

### Ingresos
```
"recibí salario 2000000"
"mis ingresos del mes"
```

### Presupuesto
```
"mi presupuesto es 500000"
"puedes presupuestarme 2 millones para el año"
"cómo voy con el presupuesto"
```
> El bot te dice en tiempo real cuánto llevás gastado, qué porcentaje del presupuesto usaste y cuánto te queda disponible.

### Reportes y Balance
```
"reporte de hoy"
"reporte del mes"
"gastos por categoría"
"cómo voy este mes"
"balance"
```

### Vacas (Fondos Grupales)
Las vacas son cajas colectivas para gastos compartidos. Perfectas para salidas, viajes o eventos con amigos.
```
"crear vaca Salida"
"hoy voy a salir con mis amigos, crea una vaca con nombre asado"
"en la vaquita asado registra comida 50000"
"agregar a vaca asado: bebidas 100000, no previstos 200000"
"divide la vaca asado entre 4 y dame el reporte"
```
> Resultado: muestra el desglose completo de gastos y calcula automáticamente cuánto pone cada persona.

### Deudas
```
"le debo 50000 a Juan"
"Juan me pagó"
"mis deudas"
```

### Préstamos
```
"le presté 200000 a Carlos"
"recuerda que le presté 17k a mi amigo Santiago"
"Carlos me abonó 50000"
```
> Soporta préstamos con o sin interés mensual y con fecha límite opcional.

### Excel
```
"generar excel"
"puedes darme un excel con el reporte del mes"
"reporte de abril"
```
> Genera y envía directamente al chat un archivo `.xlsx` con todos los registros del período.

---

## Stack Tecnológico

| Capa | Tecnología | Rol |
|------|-----------|-----|
| Interfaz de usuario | [python-telegram-bot 22.7](https://python-telegram-bot.org/) | Canal principal, recibe y envía mensajes |
| API REST | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | Lógica de negocio, endpoints, validación |
| Agente IA | [LangGraph 1.1.6](https://langchain-ai.github.io/langgraph/) + LangChain Core | Orquesta decisiones: qué herramienta ejecutar y cuándo |
| Modelo LLM | [Groq](https://groq.com/) | Comprensión del lenguaje natural del usuario |
| Base de datos | PostgreSQL + psycopg2 | Persistencia de todos los datos financieros |
| Exportación | openpyxl | Generación de reportes `.xlsx` |
| Deploy | Heroku (Procfile) | Hosting del servidor web |

---

## Arquitectura

```
┌───────────────────────────────────────────────────────┐
│                 Usuario — Telegram                    │
│     "gasté 10k en comida" / "divide la vaca entre 4" │
└────────────────────────┬──────────────────────────────┘
                         │ webhook
                         ▼
┌───────────────────────────────────────────────────────┐
│              python-telegram-bot                      │
│         Recibe el mensaje, extrae user_id             │
└────────────────────────┬──────────────────────────────┘
                         │
                         ▼
┌───────────────────────────────────────────────────────┐
│                  FastAPI Backend                      │
│              backend/main.py                          │
│   Enruta la solicitud, aplica validaciones Pydantic   │
└──────────────┬────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐     ┌──────────────────────────────┐
│       LangGraph Agent        │     │         PostgreSQL            │
│         agent/               │◄───►│                              │
│                              │     │  gastos · ingresos           │
│  1. Interpreta la intención  │     │  presupuestos · vacas        │
│  2. Elige la herramienta     │     │  vaca_gastos · deudas        │
│  3. Ejecuta la operación     │     │  prestamos                   │
│  4. Construye la respuesta   │     │                              │
└──────────────┬───────────────┘     └──────────────────────────────┘
               │
               ▼
┌──────────────────────────────┐
│           Groq API           │
│  Inferencia ultrarrápida     │
│  sobre modelos open-source   │
└──────────────────────────────┘
```

---

## Esquema de Base de Datos

```sql
-- Movimientos del día a día
gastos        (id, user_id, categoria, monto DECIMAL(12,2), fecha)
ingresos      (id, user_id, descripcion, monto DECIMAL(12,2), fecha)

-- Control mensual
presupuestos  (id, user_id, mes VARCHAR(7), monto)  -- UNIQUE(user_id, mes)

-- Fondos grupales
vacas         (id, user_id, nombre, num_personas, cerrada BOOLEAN, fecha_creacion)
vaca_gastos   (id, vaca_id → vacas(id), descripcion, monto, fecha)

-- Compromisos financieros
deudas        (id, user_id, tipo, persona, monto, descripcion, fecha, pagado BOOLEAN)
prestamos     (id, user_id, persona, monto, monto_pagado, tasa_interes % mensual,
               fecha, fecha_limite, pagado BOOLEAN)
```

---

## Instalación Local

**Requisitos previos**
- Python 3.10+
- PostgreSQL corriendo (local o en la nube)
- Token de bot de Telegram → [@BotFather](https://t.me/BotFather)
- API Key de Groq → [console.groq.com](https://console.groq.com)

```bash
# 1. Clonar
git clone https://github.com/Dgarzonac9/Chatbot-Finanzas-Personales.git
cd Chatbot-Finanzas-Personales

# 2. Entorno virtual
python -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate         # Windows

# 3. Dependencias
pip install -r requirements.txt

# 4. Variables de entorno — crear archivo .env en la raíz
DATABASE_URL=postgresql://usuario:contraseña@host:5432/nombre_db
TELEGRAM_TOKEN=tu_token_aqui
GROQ_API_KEY=tu_api_key_aqui

# 5. Crear tablas (solo la primera vez)
python init_db.py
# → Tablas creadas correctamente

# 6. Levantar servidor
uvicorn backend.main:app --reload
```

---

## Despliegue en Heroku

El `Procfile` ya está configurado con:
```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

```bash
heroku create nombre-de-tu-app
heroku config:set DATABASE_URL=postgresql://...
heroku config:set TELEGRAM_TOKEN=tu_token
heroku config:set GROQ_API_KEY=tu_api_key

# Si usás Heroku Postgres
heroku addons:create heroku-postgresql:essential-0

# Inicializar tablas en producción
heroku run python init_db.py

git push heroku master
```

---

## Estructura del Proyecto

```
Chatbot-Finanzas-Personales/
│
├── agent/              # Agente LangGraph: nodos, herramientas y grafo de decisión
├── backend/            # FastAPI: rutas, handlers del bot y lógica de negocio
│   └── main.py
│
├── init_db.py          # Crea todas las tablas en PostgreSQL
├── requirements.txt    # 47 dependencias fijadas con versión exacta
├── Procfile            # Configuración de deploy para Heroku
└── .gitignore
```

---

## Pruébalo ahora

El bot está corriendo en producción. Podés usarlo directamente desde Telegram:

**[@TakeYourFinancesBot](https://t.me/TakeYourFinancesBot)**

Mandále "hola" para empezar.

---

<div align="center">

Desarrollado por **[@Dgarzonac9](https://github.com/Dgarzonac9)**

</div>