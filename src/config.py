import os
from dotenv import load_dotenv

load_dotenv()

# load Claude model (Sonnet 5) with Anthropic key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

# load all Google jsons
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
GOOGLE_TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

# load the working database
DB_PATH = os.getenv("DB_PATH", "data/student_agent.db")

# Scopes the agent needs. Keep these as narrow as possible.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]
