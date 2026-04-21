# Agent-Studio

A full-stack agentic app that connects Snowflake data to Gmail actions via LLM reasoning.

`Snowflake → LangGraph reasoning/tool step → Gmail`

### Why this stack

- `FastAPI` provides a thin API layer that the React frontend calls.
- `LangGraph` handles the ordered, tool-driven workflow with LLM reasoning in the middle.
- `Snowflake Connector` handles SQL execution directly.
- `Gmail API` handles send, draft, and reply actions.

---

### Project structure

```text
Agentic Garden/
├── app/
│   ├── agent.py              # LangGraph workflow and LLM reasoning
│   ├── config.py             # Environment-driven settings
│   ├── models.py             # Pydantic models
│   ├── n8n_importer.py       # Workflow template loader
│   ├── connectors/
│   │   ├── snowflake.py      # Snowflake query execution
│   │   └── gmail.py          # Gmail send/draft/reply
│   └── main.py               # FastAPI app (also serves frontend/dist)
├── frontend/                 # React + Vite UI
├── main.py                   # Local entrypoint
├── vercel.json               # Vercel deployment config
└── pyproject.toml
```

---

### Local Setup

1. Clone the repo:
```bash
git clone https://github.com/harshvshalihotri/Agent-Studio.git
cd Agent-Studio
```

2. Create a `.env` file inside the `app/` folder:
```bash
cp app/.env.example app/.env
```

3. Fill in your credentials in `app/.env`:
```env
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

GOOGLE_API_KEY=your_key
GOOGLE_MODEL=gemini-pro

SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema
SNOWFLAKE_ROLE=your_role
SNOWFLAKE_AUTHENTICATOR=snowflake

GMAIL_CLIENT_ID=your_client_id
GMAIL_CLIENT_SECRET=your_client_secret
GMAIL_SENDER_EMAIL=your_email
```

4. Install Python dependencies:
```bash
pip install -e .
```

5. Install frontend dependencies:
```bash
cd frontend
npm install
cd ..
```

---

### Run Locally

**Backend:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend (in a separate terminal):**
```bash
cd frontend
npm run dev
```

- Backend runs on `http://localhost:8000`
- Frontend runs on `http://localhost:5173`

**To build frontend and serve it via FastAPI:**
```bash
cd frontend
npm run build
cd ..
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

After building, FastAPI serves the frontend from `frontend/dist` at `http://localhost:8000`.

---

### Vercel Deployment

The app deploys as a single project on Vercel with the backend serving the built frontend.

1. Push to GitHub
2. Import repo on [vercel.com](https://vercel.com)
3. Set **Root Directory** to blank (default)
4. Add all environment variables from `app/.env` in Vercel → Settings → Environment Variables
5. Deploy

> ⚠️ `SNOWFLAKE_AUTHENTICATOR=externalbrowser` will **not** work on Vercel or any server — it requires an interactive browser. Use `snowflake` (password-based) or `snowflake_jwt` (key pair) for server deployments.

> ⚠️ `GMAIL_CREDENTIALS_FILE` and `GMAIL_TOKEN_FILE` are local file paths and won't work on Vercel. Use `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` instead.

---

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/workflows/imported` | List imported workflow templates |
| `POST` | `/agent/run` | Run the agent |
| `GET` | `/debug` | Debug frontend path (remove in production) |

---

### Example Request

```json
{
  "sql_query": "select customer_name, revenue from sales order by revenue desc limit 25",
  "max_rows": 25,
  "reasoning_goal": "Identify the key revenue patterns and write an exec-ready summary.",
  "email": {
    "action": "draft",
    "to": ["leader@example.com"],
    "subject": "Weekly revenue snapshot",
    "instructions": "Keep it concise and call out the top 3 observations."
  }
}
```

---

### Gmail OAuth

Two setup paths are supported:

- `GMAIL_CREDENTIALS_FILE` pointing to a Google OAuth client JSON file
- `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` directly in `.env`

Use a Google OAuth client of type **Desktop app**.

On first local run, the app will open a browser OAuth consent flow and save the token to `credentials/gmail-token.json`.

---

### Snowflake Auth

| Authenticator | Use case |
|---|---|
| `snowflake` | Username + password — works everywhere including servers |
| `externalbrowser` | Browser-based SSO — local development only |
| `snowflake_jwt` | Key pair auth — works on servers without password |

---

### Notes

- `reply` action requires correct `thread_id` and `reply_to_message_id` in the request.
- Remove the `/debug` endpoint before going to production.
- The frontend proxies API requests to FastAPI during local development via Vite's dev server.
