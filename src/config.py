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

# Public demo mode: per-visitor sandboxes, simulated Gmail/Calendar, usage caps.
# See src/demo.py. The Docker image turns this on.
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
DEMO_SANDBOX_DIR = os.getenv("DEMO_SANDBOX_DIR", "data/sandboxes")
DEMO_SANDBOX_TTL_HOURS = int(os.getenv("DEMO_SANDBOX_TTL_HOURS", "24"))
DEMO_MAX_SANDBOXES = int(os.getenv("DEMO_MAX_SANDBOXES", "500"))
DEMO_MESSAGES_PER_VISITOR = int(os.getenv("DEMO_MESSAGES_PER_VISITOR", "20"))
DEMO_MESSAGES_PER_DAY = int(os.getenv("DEMO_MESSAGES_PER_DAY", "200"))

# Optional "Sign in with Google" for the hosted app. Needs a Web application
# OAuth client; the button stays hidden until all three values are set.
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
GOOGLE_SIGNIN_ENABLED = DEMO_MODE and all(
    (GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI)
)

# Scopes the agent needs. Keep these as narrow as possible.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]
