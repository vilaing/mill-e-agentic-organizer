"""FastAPI web app: a REST API over the existing tool functions, plus a small
static frontend (chat, assignments, points/rewards, recruiting, settings).

Run with:
    python -m src.web.main
or:
    uvicorn src.web.main:app --reload
"""
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from src import demo, point_rules
from src.agent import run_agent
from src.config import DEMO_MODE, GOOGLE_SIGNIN_ENABLED
from src.db.db import init_db
from src.google_oauth import SignInError
from src.tools import db_tool

logger = logging.getLogger(__name__)

# The public demo has no reason to advertise its API.
app = FastAPI(title="Mill-E Agentic Organizer", docs_url=None if DEMO_MODE else "/docs",
              redoc_url=None if DEMO_MODE else "/redoc",
              openapi_url=None if DEMO_MODE else "/openapi.json")

if DEMO_MODE:
    app.add_middleware(demo.SandboxMiddleware)
else:
    init_db()  # upgrades an existing local database in place; safe to rerun

STATIC_DIR = Path(__file__).parent / "static"

# Local single-user history, kept in memory for the life of the process. In
# demo mode each visitor gets their own history from src/demo.py instead.
_LOCAL_CHAT_HISTORY: list = []


def _chat_history() -> list:
    return demo.current_history() if DEMO_MODE else _LOCAL_CHAT_HISTORY


# --- Schemas ---

class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class MilestoneIn(BaseModel):
    title: str
    point_percent: int | None = Field(default=None, ge=1, le=100)


class AssignmentIn(BaseModel):
    title: str
    course: str = ""
    due_date: str = ""
    importance: int = 3
    difficulty: int = 3
    milestones: list[MilestoneIn] = []


class RecruitingIn(BaseModel):
    company: str
    role: str = ""
    stage: str = "applied"
    next_action: str = ""
    next_action_date: str = ""
    notes: str = ""


class AwardIn(BaseModel):
    name: str
    cost: int
    description: str = ""
    break_minutes: int = 0
    dollar_value: float = 0


class RedeemIn(BaseModel):
    quantity: int = Field(default=1, ge=1, le=db_tool.MAX_REDEEM_QUANTITY)


class SpendBreakIn(BaseModel):
    minutes: int


class SpendDollarsIn(BaseModel):
    amount: float
    reason: str = ""


class SetupIn(BaseModel):
    reward_style: str
    additional_rules: str = Field(default="", max_length=2000)
    morning_reminders: bool = True


class RewardStyleIn(BaseModel):
    reward_style: str


class AdditionalRulesIn(BaseModel):
    additional_rules: str = Field(max_length=2000)


class MorningRemindersIn(BaseModel):
    enabled: bool


def _or_404(result: dict) -> dict:
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# --- Chat ---

@app.post("/api/chat")
def chat(body: ChatMessage):
    if DEMO_MODE:
        limit_reason = demo.consume_message_quota()
        if limit_reason:
            raise HTTPException(status_code=429, detail=limit_reason)
    history = _chat_history()
    try:
        reply, updated_history = run_agent(body.message, history=history)
    except Exception:
        logger.exception("Agent run failed")
        raise HTTPException(status_code=503, detail="The assistant is unavailable right now. Please try again.")
    history[:] = updated_history
    return {"reply": reply}


@app.post("/api/chat/reset")
def chat_reset():
    _chat_history().clear()
    return {"status": "cleared"}


# --- Demo ---

@app.get("/api/demo")
def demo_status():
    if not DEMO_MODE:
        return {"demo": False}
    return {
        "demo": True,
        "messages_left": demo.messages_left(),
        "google": {"available": GOOGLE_SIGNIN_ENABLED, "email": demo.google_email()},
    }


@app.post("/api/demo/reset")
def demo_reset():
    if not DEMO_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    if demo.google_email():
        raise HTTPException(status_code=400, detail="Reset is only available for the sample data.")
    demo.reset_current_sandbox()
    return {"status": "reset"}


# --- Google sign-in (hosted app) ---

def _require_google_signin() -> None:
    if not GOOGLE_SIGNIN_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")


@app.get("/api/auth/google/start")
def google_sign_in_start():
    _require_google_signin()
    return RedirectResponse(demo.begin_google_sign_in(), status_code=302)


@app.get("/api/auth/google/callback")
def google_sign_in_callback(state: str = "", code: str = "", error: str = ""):
    _require_google_signin()
    if error or not code:
        return RedirectResponse("/app?google=cancelled", status_code=302)
    try:
        demo.finish_google_sign_in(state, code)
    except SignInError as exc:
        return RedirectResponse(f"/app?google={exc.reason}", status_code=302)
    return RedirectResponse("/app", status_code=302)


@app.post("/api/auth/google/sign-out")
def google_sign_out():
    _require_google_signin()
    demo.sign_out_of_google()
    return {"status": "signed_out"}


# --- Preferences / setup ---

_RULES_UNAVAILABLE = "Your rules weren't saved because the assistant is unavailable. Please try again."


def _charge_rule_interpretation(rules: str) -> None:
    """Interpreting rules calls Claude, so in the demo it counts as a chat message."""
    if DEMO_MODE and point_rules.needs_interpretation(rules):
        limit_reason = demo.consume_message_quota()
        if limit_reason:
            raise HTTPException(status_code=429, detail=limit_reason)


@app.get("/api/preferences")
def get_preferences():
    return db_tool.get_preferences()


@app.post("/api/setup")
def complete_setup(body: SetupIn):
    _charge_rule_interpretation(body.additional_rules)
    try:
        return _or_404(point_rules.complete_setup(body.reward_style, body.additional_rules, body.morning_reminders))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Could not interpret rules during setup")
        raise HTTPException(status_code=503, detail=_RULES_UNAVAILABLE)


@app.post("/api/preferences/reward-style")
def set_reward_style(body: RewardStyleIn):
    return _or_404(db_tool.set_reward_style(body.reward_style))


@app.post("/api/preferences/additional-rules")
def set_additional_rules(body: AdditionalRulesIn):
    _charge_rule_interpretation(body.additional_rules)
    try:
        return point_rules.save_additional_rules(body.additional_rules)
    except Exception:
        logger.exception("Could not interpret rules")
        raise HTTPException(status_code=503, detail=_RULES_UNAVAILABLE)


@app.post("/api/preferences/morning-reminders")
def set_morning_reminders(body: MorningRemindersIn):
    return db_tool.set_morning_reminders(body.enabled)


# --- Assignments ---

@app.get("/api/assignments")
def list_assignments(status: str = "open"):
    return db_tool.list_assignments(status)


@app.post("/api/assignments")
def add_assignment(body: AssignmentIn):
    return _or_404(db_tool.add_assignment_with_milestones(
        body.title, body.course, body.due_date, body.importance, body.difficulty,
        [milestone.model_dump() for milestone in body.milestones],
    ))


@app.get("/api/assignments/{assignment_id}")
def get_assignment(assignment_id: int):
    return _or_404(db_tool.get_assignment(assignment_id))


@app.delete("/api/assignments/{assignment_id}")
def delete_assignment(assignment_id: int):
    return _or_404(db_tool.delete_assignment(assignment_id))


@app.post("/api/assignments/{assignment_id}/start")
def start_assignment(assignment_id: int):
    return _or_404(db_tool.start_assignment(assignment_id))


@app.post("/api/assignments/{assignment_id}/complete")
def complete_assignment(assignment_id: int):
    return _or_404(db_tool.complete_assignment(assignment_id))


# --- Milestones ---

@app.get("/api/assignments/{assignment_id}/milestones")
def list_milestones(assignment_id: int):
    return db_tool.list_milestones(assignment_id)


@app.post("/api/assignments/{assignment_id}/milestones")
def add_milestone(assignment_id: int, body: MilestoneIn):
    return _or_404(db_tool.add_milestone(assignment_id, body.title, body.point_percent))


@app.post("/api/milestones/{milestone_id}/toggle")
def toggle_milestone(milestone_id: int):
    return _or_404(db_tool.toggle_milestone(milestone_id))


@app.delete("/api/milestones/{milestone_id}")
def delete_milestone(milestone_id: int):
    return db_tool.delete_milestone(milestone_id)


# --- Recruiting ---

@app.get("/api/recruiting")
def list_recruiting():
    return db_tool.list_recruiting()


@app.post("/api/recruiting")
def upsert_recruiting(body: RecruitingIn):
    return db_tool.upsert_recruiting(
        body.company, body.role, body.stage, body.next_action, body.next_action_date, body.notes
    )


# --- Points & awards ---

@app.get("/api/points")
def get_points_total():
    return db_tool.get_points_total()


@app.get("/api/awards")
def list_awards(active_only: bool = True):
    return db_tool.list_awards(active_only)


@app.post("/api/awards")
def add_award(body: AwardIn):
    return _or_404(db_tool.add_award(body.name, body.cost, body.description, body.break_minutes, body.dollar_value))


@app.post("/api/awards/{award_id}/redeem")
def redeem_award(award_id: int, body: RedeemIn | None = None):
    return _or_404(db_tool.redeem_award(award_id, body.quantity if body else 1))


@app.post("/api/awards/{award_id}/deactivate")
def deactivate_award(award_id: int):
    return db_tool.deactivate_award(award_id)


# --- Reward banks ---

@app.get("/api/reward-banks")
def get_reward_banks():
    return db_tool.get_reward_banks()


@app.post("/api/reward-banks/spend-break")
def spend_break_minutes(body: SpendBreakIn):
    return _or_404(db_tool.spend_break_minutes(body.minutes))


@app.post("/api/reward-banks/spend-dollars")
def spend_dollars(body: SpendDollarsIn):
    return _or_404(db_tool.spend_dollars(body.amount, body.reason))


@app.get("/api/dollar-transactions")
def list_dollar_transactions(limit: int = 10):
    return db_tool.list_dollar_transactions(limit)


# --- Static frontend (must be mounted after the API routes above) ---

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "home.html")


@app.get("/app")
def web_app():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.main:app", host="127.0.0.1", port=8000, reload=True)
