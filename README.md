## Agentic Garden

Simple backend agent for this flow:

`Snowflake -> LangGraph reasoning/tool step -> Gmail`

### Why this stack

- `FastAPI` gives you a thin API layer that a React frontend can call later.
- `LangGraph` is the best fit here because your workflow is ordered and tool-driven, but still needs LLM reasoning in the middle.
- `Snowflake Connector` handles SQL execution directly.
- `Gmail API` handles send, draft, and reply actions.

### Project structure

```text
app/
  agent.py              # LangGraph workflow and LLM reasoning
  config.py             # Environment-driven settings
  connectors/
    snowflake.py        # Snowflake query execution
    gmail.py            # Gmail send/draft/reply
  main.py               # FastAPI app
frontend/               # React UI
main.py                 # Local entrypoint
```

### Setup

1. Create a `.env` file from `.env.example`.
2. Add your OpenAI-compatible model credentials.
3. Add your Snowflake credentials.
4. Configure Gmail OAuth with either a downloaded client JSON file or plain `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET`.
5. Install dependencies.

```bash
pip install -e .
```

### Run

```bash
python main.py
```

The API will start on `http://localhost:8000`.

For the React frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend will start on `http://localhost:5173` and proxy API requests to FastAPI.

To produce a single deployable app:

```bash
cd frontend
npm run build
```

After that, FastAPI will serve the built frontend from `frontend/dist`.

### Endpoints

- `GET /health`
- `GET /workflows/imported`
- `POST /agent/run`

### Example request

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

### Gmail OAuth

This app supports two Gmail OAuth setup paths:

- `GMAIL_CREDENTIALS_FILE` pointing to a Google OAuth client JSON file
- `GMAIL_CLIENT_ID` and `GMAIL_CLIENT_SECRET` directly in `.env`

For this app, the practical choice is a Google OAuth client of type `Desktop app`.
An OAuth redirect URI that points to `n8n` is not used here.

### Snowflake Auth

This app supports:

- `SNOWFLAKE_AUTHENTICATOR=snowflake` for direct username/password
- `SNOWFLAKE_AUTHENTICATOR=externalbrowser` for browser-based SSO

If you use `externalbrowser`, keep `SNOWFLAKE_USER` set and the connector will open a browser login flow on connect.

### Notes

- On first Gmail use, the app will open a local OAuth consent flow and save the token to `credentials/gmail-token.json`.
- The current implementation is backend-only. A React frontend can call `/agent/run` directly.
- `reply` requires the correct Gmail `thread_id` and `reply_to_message_id`.
