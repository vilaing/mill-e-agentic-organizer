# Student Agent

A personal agent that reads your Gmail and Google Calendar, tracks assignments
and recruiting progress in a local database, and runs on a schedule to send
you reminders and update a points-based reward system.

Built directly on the Anthropic API with tool use (function calling) — no
claude.ai connectors. You own the agent loop, the OAuth, and the data.

## Architecture

```
scheduler.py  --(daily cron)-->  agent.py  --(tool use loop)-->  Claude API
                                      |
                        +-------------+-------------+
                        |             |             |
                 calendar_tool   gmail_tool      db_tool
                        |             |             |
                Google Calendar   Gmail API      SQLite
                      API
```

`agent.py` is the core: it sends Claude a prompt plus a list of tool
definitions, executes whichever tools Claude asks for, feeds the results
back, and loops until Claude returns a final text answer. That loop is the
whole "agent" — everything else is just tools plumbed into it.

## Setup

### 1. Anthropic API key
Get a key from https://console.anthropic.com/ and put it in `.env`
(copy `.env.example` first).

### 2. Google Cloud project (for Gmail + Calendar)
1. Go to https://console.cloud.google.com/ and create a project.
2. Enable the **Gmail API** and **Google Calendar API** under "APIs & Services".
3. Configure the OAuth consent screen (External, add yourself as a test user).
4. Create an OAuth Client ID (type: Desktop app) under Credentials.
5. Download the JSON and save it as `credentials.json` in the project root.
6. The first time you run `agent.py`, it will open a browser to authenticate
   and save a `token.json` for future runs.

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Initialize the database
```bash
python -m src.db.db init
```

### 5. Run the agent once, manually
```bash
python -m src.agent "What's due this week and what should I follow up on for recruiting?"
```

### 6. Run the web app
```bash
python -m src.web.main
```
Then open http://127.0.0.1:8000. FastAPI serves both the JSON API (under
`/api`) and a small static frontend (chat, assignments, points/rewards,
recruiting, settings) -- no separate frontend build/toolchain needed.

### 7. Run it on a schedule
```bash
python -m src.scheduler
```
This runs the agent daily with a fixed prompt (morning briefing). Swap in
`cron` or a system service for real deployment instead of leaving a Python
process running in the foreground.

## Project structure

```
student-agent/
  src/
    agent.py            # core agent loop (Claude API + tool use)
    config.py            # env var loading
    scheduler.py          # daily automated run
    tools/
      calendar_tool.py    # Google Calendar read/write
      gmail_tool.py        # Gmail read/send
      db_tool.py            # assignments, recruiting pipeline, points
    db/
      schema.sql
      db.py
    web/
      main.py              # FastAPI app: REST API + serves the frontend
      static/                # chat / assignments / rewards / recruiting / settings UI
  data/
    student_agent.db      # created on init
  requirements.txt
  .env.example
```

## Extending this into an MCP server

Once the three tools work standalone, the natural next step is wrapping them
in a custom MCP server (`mcp` Python SDK) so any MCP-compatible client — not
just this script — can use them. That's a good "phase 2" for the resume
writeup: same tool functions, exposed over the MCP protocol instead of
called directly from `agent.py`.
