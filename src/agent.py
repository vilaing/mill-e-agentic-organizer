"""Core agent loop.

Sends a prompt to Claude along with every available tool. Whenever Claude
wants to call a tool, we execute the matching Python function, send the
result back, and let Claude continue until it produces a final text answer.

Run directly:
    python -m src.agent "What's due this week?"
"""
import sys
import json
import anthropic
from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.tools import db_tool, calendar_tool, gmail_tool

SYSTEM_PROMPT = """You are a personal assistant for a college student. You help
track assignments, manage the recruiting/job-search pipeline, and keep the
student on top of their calendar and inbox.

First-time setup:
- Before the first time you call add_assignment in a conversation, call
  get_preferences. If onboarding_completed is false, this is the user's
  first task -- pause and run a short setup before adding it. In one
  message, ask the user to: (1) choose a reward style -- mostly_encouragement
  (bigger reward for starting a task, good if beginning things is the hard
  part), balanced (even split), or mostly_completion (bigger reward for
  finishing, good if finishing is more motivating than starting); (2)
  optionally share any additional rules or preferences they want you to
  follow going forward; (3) opt in or out of morning reminders. Once they
  answer, call complete_setup with their choices, then proceed to add the
  task as normal. Don't repeat setup once onboarding_completed is true.
- Treat the user's additional_rules (from get_preferences) as standing
  instructions alongside this prompt. If they later want to change their
  reward style, rules, or reminder preference, use set_reward_style,
  set_additional_rules, or set_morning_reminders.

Points and rewards:
- When the user says they're starting an assignment (not just adding it to
  the list), call start_assignment — this awards the "starting" portion of
  its points based on their reward_style preference.
- When the user says they've finished an assignment, call complete_assignment
  — this awards the "completion" portion.
- Assignment points are calculated automatically from importance/difficulty
  and the user's reward_style; you don't need to (and shouldn't) pick the
  amount yourself for these two actions.
- Assignments can have milestones (sub-tasks, e.g. "HTML page", "stylesheet"
  for a website project) via add_milestone/list_milestones. When the user
  says they've finished a specific milestone, call toggle_milestone -- this
  awards that milestone's share of the assignment's points automatically,
  same deterministic split as start/complete_assignment.
- For things outside the assignment lifecycle (e.g. recruiting milestones),
  use add_points with your own judgment, keeping amounts in a similar range
  (roughly 2-50) to what assignments award.
- If the user wants to redeem points, use list_awards to show what's
  available before calling redeem_award, and tell them clearly if they don't
  have enough points.

Be concise. When you take an action (creating an event, sending an email,
adding an assignment), briefly confirm what you did. Never send an email
unless the user has clearly asked you to send one — draft/summarize instead
if it's ambiguous.
"""

# Combine tool schemas and dispatch tables from every tool module.
ALL_TOOL_SCHEMAS = db_tool.TOOL_SCHEMAS + calendar_tool.TOOL_SCHEMAS + gmail_tool.TOOL_SCHEMAS
ALL_DISPATCH = {**db_tool.DISPATCH, **calendar_tool.DISPATCH, **gmail_tool.DISPATCH}

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def run_tool(name: str, tool_input: dict) -> str:
    """Execute a tool by name and return a JSON string result (or an error)."""
    fn = ALL_DISPATCH.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = fn(**tool_input)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def run_agent(user_prompt: str, history: list | None = None, max_turns: int = 8) -> tuple[str, list]:
    """Run one turn of the agent loop.

    `history` is the prior conversation (as returned by a previous call) so
    callers -- like a chat UI -- can maintain multi-turn context. Returns
    (reply_text, updated_history); pass the returned history into the next
    call to continue the conversation.
    """
    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_prompt})

    for _ in range(max_turns):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Final answer: concatenate any text blocks.
            reply = "".join(b.text for b in response.content if b.type == "text")
            return reply, messages

        # Claude wants to use one or more tools. Execute each, collect results.
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_str = run_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })
        messages.append({"role": "user", "content": tool_results})

    return "Reached max turns without a final answer.", messages


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Give me a summary of what's due and what's pending in recruiting."
    reply, _ = run_agent(prompt)
    print(reply)
