"""Runs the agent automatically on a schedule.

This is the piece that makes it an *agent* rather than a chatbot you have to
remember to open: it decides, unprompted, what needs your attention.

For real deployment, prefer a system cron job or a service (systemd, a
scheduled cloud function) over leaving this process running. This script is
mainly useful for local development/demoing.
"""
import time
import schedule
from src.agent import run_agent

MORNING_PROMPT = """Give me my morning briefing:
1. What assignments are due in the next 3 days?
2. Any unread emails from recruiters or professors that need a response?
3. Any recruiting next-actions due soon?
Keep it short and actionable. Don't send any emails unless something is truly urgent."""


def morning_briefing():
    print("Running morning briefing...")
    reply, _ = run_agent(MORNING_PROMPT)
    print(reply)
    # TODO: replace print with a real notification (email digest, Slack, push, etc.)


def main():
    schedule.every().day.at("08:00").do(morning_briefing)
    print("Scheduler running. Waiting for 08:00 daily trigger... (Ctrl+C to stop)")
    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
