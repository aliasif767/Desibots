# 🤖 Desibots Hub — Centralized AI Assistant Platform

A professional SaaS platform integrating 4 specialized AI bots under a single authenticated, subscription-gated web interface.

---

## 🏗️ Architecture

```
desibots/
├── main-backend/        # Node.js + Express (Auth, Subscriptions, Bot Proxy)
├── main-frontend/       # React + Vite + Vanilla CSS (Dashboard, Login, Bot Viewer)
├── firstaid-project/    # First Aid Streamlit Bot (FastAPI backend + Streamlit UI)
├── hisabbot/            # Finance/Audit Streamlit Bot
├── lawerbot/            # Legal RAG Streamlit Bot
├── pakorderbot/         # Order Management FastAPI Bot
├── docker-compose.yml   # Full orchestration
└── .env.example         # Environment variables template
```

---

## 🚀 Run Locally (Recommended — Full Docker)

### Step 1: Set up environment variables
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY and a strong JWT_SECRET
```

### Step 2: Start everything
```bash
docker-compose up --build
```

| Service           | URL                        |
|-------------------|----------------------------|
| Main Website      | http://localhost:3000       |
| Main Backend API  | http://localhost:8000       |

> Bot services are **internal only** — accessible exclusively through the proxy.

---

## 💻 Run Locally (Development Mode — No Docker)

### Backend
```bash
cd main-backend
npm install
npm run dev        # Starts on http://localhost:8000
```

### Frontend
```bash
cd main-frontend
npm install
npm run dev        # Starts on http://localhost:5173
```
> The Vite proxy automatically forwards `/api` and `/proxy` requests to `localhost:8000`.

---

## 🔐 Authentication Flow

1. **Sign Up** at `/auth` — creates a new user account
2. **Log In** — receive a JWT token stored in localStorage
3. **Dashboard** — view all 4 bot cards
4. Click a bot:
   - ✅ **Subscribed** → Opens bot in iframe via secure proxy
   - ❌ **Not subscribed** → Triggers payment modal
5. **Mock Payment** — fill any card details → subscription activated instantly

---

## 🤖 Bot Proxy Security

Bots run on the internal Docker network only. They are **never directly accessible** from the internet. All traffic is routed through:

```
Browser → main-frontend → /proxy/:botId → main-backend (auth check) → bot container
```

---

## 🗄️ Database (SQLite)

Auto-created at `main-backend/database.sqlite` on first run.

| Table           | Columns                                      |
|-----------------|----------------------------------------------|
| `users`         | id, username, password (bcrypt hashed)       |
| `subscriptions` | id, user_id, plan, active                    |

---

## 🔑 Default Test Account

A default admin account is auto-created on first backend startup:

| Field    | Value      |
|----------|------------|
| Username | `admin`    |
| Password | `admin123` |

This account has an active Pro subscription — use it to test bot access immediately.

---

## 📦 Environment Variables

| Variable      | Description                          |
|---------------|--------------------------------------|
| `JWT_SECRET`  | Secret key for signing JWT tokens    |
| `GROQ_API_KEY`| Your Groq API key for the AI models  |

---

## ➕ Adding a New Bot

1. Create a new folder `mybot/` with a `Dockerfile`
2. Add the service to `docker-compose.yml` under the `desibots-net` network
3. Add a proxy route in `main-backend/server.js`:
   ```js
   app.use('/proxy/mybot', authenticateToken, requireSubscription, proxyMiddleware('http://mybot:8501'));
   ```
4. Add a card to `main-frontend/src/pages/Dashboard.jsx` in the `BOTS` array
