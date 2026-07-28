"""FastAPI web app: a REST API over the existing tool functions, plus a small
static frontend (chat, assignments, points/rewards, recruiting, settings).

Run with:
    python -m src.web.main
or:
    uvicorn src.web.main:app --reload
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.agent import run_agent
from src.tools import db_tool

app = FastAPI(title="Student Agent")

STATIC_DIR = Path(__file__).parent / "static"

# Single-user app: conversation history and chat state live in memory for the
# life of the process. Fine for local/personal use; would need a real session
# store for multiple concurrent users.
CHAT_HISTORY: list = []


# --- Schemas ---

class ChatMessage(BaseModel):
    message: str


class AssignmentIn(BaseModel):
    title: str
    course: str = ""
    due_date: str = ""
    importance: int = 3
    difficulty: int = 3


class MilestoneIn(BaseModel):
    title: str


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


class SpendBreakIn(BaseModel):
    minutes: int


class SpendDollarsIn(BaseModel):
    amount: float
    reason: str = ""


class SetupIn(BaseModel):
    reward_style: str
    additional_rules: str = ""
    morning_reminders: bool = True


class RewardStyleIn(BaseModel):
    reward_style: str


class AdditionalRulesIn(BaseModel):
    additional_rules: str


class MorningRemindersIn(BaseModel):
    enabled: bool


def _or_404(result: dict) -> dict:
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# --- Chat ---

@app.post("/api/chat")
def chat(body: ChatMessage):
    reply, updated_history = run_agent(body.message, history=CHAT_HISTORY)
    CHAT_HISTORY[:] = updated_history
    return {"reply": reply}


@app.post("/api/chat/reset")
def chat_reset():
    CHAT_HISTORY.clear()
    return {"status": "cleared"}


# --- Preferences / setup ---

@app.get("/api/preferences")
def get_preferences():
    return db_tool.get_preferences()


@app.post("/api/setup")
def complete_setup(body: SetupIn):
    return _or_404(db_tool.complete_setup(body.reward_style, body.additional_rules, body.morning_reminders))


@app.post("/api/preferences/reward-style")
def set_reward_style(body: RewardStyleIn):
    return _or_404(db_tool.set_reward_style(body.reward_style))


@app.post("/api/preferences/additional-rules")
def set_additional_rules(body: AdditionalRulesIn):
    return db_tool.set_additional_rules(body.additional_rules)


@app.post("/api/preferences/morning-reminders")
def set_morning_reminders(body: MorningRemindersIn):
    return db_tool.set_morning_reminders(body.enabled)


# --- Assignments ---

@app.get("/api/assignments")
def list_assignments(status: str = "open"):
    return db_tool.list_assignments(status)


@app.post("/api/assignments")
def add_assignment(body: AssignmentIn):
    return db_tool.add_assignment(body.title, body.course, body.due_date, body.importance, body.difficulty)


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
    return _or_404(db_tool.add_milestone(assignment_id, body.title))


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
def redeem_award(award_id: int):
    return _or_404(db_tool.redeem_award(award_id))


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
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.web.main:app", host="127.0.0.1", port=8000, reload=True)
