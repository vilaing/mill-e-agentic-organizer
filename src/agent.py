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
student on top of their calendar and inbox. You also run a lightweight
points-based reward system: award points when the student completes
assignments or makes recruiting progress, using the add_points tool.

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


def run_agent(user_prompt: str, max_turns: int = 8) -> str:
    messages = [{"role": "user", "content": user_prompt}]

    for _ in range(max_turns):
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            # Final answer: concatenate any text blocks.
            return "".join(b.text for b in response.content if b.type == "text")

        # Claude wants to use one or more tools. Execute each, collect results.
        messages.append({"role": "assistant", "content": response.content})
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

    return "Reached max turns without a final answer."


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Give me a summary of what's due and what's pending in recruiting."
    print(run_agent(prompt))
