// Vanilla JS SPA -- no build step, talks to the FastAPI backend under /api.

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

// --- Tabs ---

document.getElementById("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (!btn) return;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
  const tab = btn.dataset.tab;
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${tab}`));
  if (tab === "assignments") showAssignmentListView();
  if (tab === "rewards") { loadAwards(); loadRewardBanks(); loadDollarTransactions(); }
  if (tab === "recruiting") loadRecruiting();
  if (tab === "settings") loadSettings();
});

// --- Points badge ---

// Every 10-point bucket steps to a darker blue; caps out at 70+ so huge
// totals don't go fully black.
function pointsColor(points) {
  const bucket = Math.min(Math.floor(Math.max(points, 0) / 10), 7);
  const lightness = 88 - bucket * 9; // 88 -> 25
  const fg = lightness > 55 ? "#0b1220" : "#eaf1ff";
  return { bg: `hsl(218, 85%, ${lightness}%)`, fg };
}

function stylePointsBadge(el, points) {
  const { bg, fg } = pointsColor(points);
  el.style.background = bg;
  el.style.color = fg;
  el.style.borderColor = bg;
}

async function refreshPoints() {
  const { total_points } = await api("/points");
  const badge = document.getElementById("points-badge");
  badge.textContent = `${total_points} pts`;
  stylePointsBadge(badge, total_points);
}

// --- Chat ---

const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

// Claude's replies use light markdown (**bold**, *italic*, `code`, "- "
// bullets). Escape first so user/model text can't inject HTML, then render
// just those bits. Bold before italic so "**x**" doesn't leave stray single
// asterisks for the italic pass to pick up; bullets before italic so a
// leading "* " marker isn't mistaken for the start of an italic span.
function formatChatText(raw) {
  let html = escapeHtml(raw);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/^[*-] /gm, "&bull; ");
  html = html.replace(/\*([^*\n]+?)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");
  return html;
}

function appendChatMsg(text, role) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = formatChatText(text);
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  return div;
}

function appendTypingIndicator() {
  const div = document.createElement("div");
  div.className = "chat-msg agent typing";
  div.innerHTML = `<span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  return div;
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;
  chatInput.value = "";
  appendChatMsg(message, "user");
  const pendingEl = appendTypingIndicator();
  try {
    const { reply } = await api("/chat", { method: "POST", body: JSON.stringify({ message }) });
    pendingEl.classList.remove("typing");
    pendingEl.innerHTML = formatChatText(reply);
  } catch (err) {
    pendingEl.classList.remove("typing");
    pendingEl.textContent = `Error: ${err.message}`;
  }
  refreshPoints();
});

// --- Welcome message: quick overview of upcoming tasks, shown once on load ---

function buildWelcomeText(assignments) {
  if (assignments.length === 0) {
    return "Welcome back! You have no open or in-progress assignments right now -- add one to get started.";
  }
  const upcoming = sortAssignments(assignments, "due_date").slice(0, 5);
  const lines = upcoming.map((a) => {
    const course = a.course ? ` (${a.course})` : "";
    const due = a.due_date ? ` -- due ${a.due_date}` : "";
    const inProgress = a.status === "in_progress" ? " [in progress]" : "";
    return `- **${a.title}**${course}${due}${inProgress}`;
  });
  const rest = assignments.length - upcoming.length;
  const more = rest > 0 ? `\n...and ${rest} more.` : "";
  return `Welcome back! Here's what's open or in progress:\n${lines.join("\n")}${more}`;
}

async function showWelcomeMessage() {
  try {
    const assignments = await api("/assignments?status=active");
    appendChatMsg(buildWelcomeText(assignments), "agent");
  } catch (err) {
    // Non-critical -- skip the welcome message if this fails.
  }
}

// --- Generic modal (used for add-assignment / add-award / add-recruiting) ---

const genericModal = document.getElementById("generic-modal");
const genericModalTitle = document.getElementById("generic-modal-title");
const genericModalForm = document.getElementById("generic-modal-form");

function openGenericModal(title, fields, onSubmit) {
  genericModalTitle.textContent = title;
  genericModalForm.innerHTML = "";
  fields.forEach((f) => {
    const label = document.createElement("label");
    label.textContent = f.label;
    genericModalForm.appendChild(label);

    let input;
    if (f.type === "select") {
      input = document.createElement("select");
      f.options.forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt.value;
        o.textContent = opt.label;
        input.appendChild(o);
      });
    } else if (f.type === "textarea") {
      input = document.createElement("textarea");
      input.rows = 3;
    } else {
      input = document.createElement("input");
      input.type = f.type || "text";
    }
    input.id = `gm-${f.name}`;
    if (f.placeholder) input.placeholder = f.placeholder;
    if (f.value !== undefined) input.value = f.value;
    genericModalForm.appendChild(input);
  });

  const actions = document.createElement("div");
  actions.className = "modal-actions";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "secondary";
  cancelBtn.textContent = "Cancel";
  cancelBtn.onclick = closeGenericModal;
  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "Save";
  actions.appendChild(cancelBtn);
  actions.appendChild(submitBtn);
  genericModalForm.appendChild(actions);

  genericModalForm.onsubmit = async (e) => {
    e.preventDefault();
    const values = {};
    fields.forEach((f) => {
      const el = document.getElementById(`gm-${f.name}`);
      values[f.name] = f.type === "number" ? Number(el.value) : el.value;
    });
    await onSubmit(values);
    closeGenericModal();
  };

  genericModal.classList.remove("hidden");
}

function closeGenericModal() {
  genericModal.classList.add("hidden");
}

// --- Assignments ---

function sortAssignments(list, sortBy) {
  const sorted = [...list];
  if (sortBy === "importance") {
    sorted.sort((a, b) => b.importance - a.importance);
  } else if (sortBy === "difficulty") {
    sorted.sort((a, b) => b.difficulty - a.difficulty);
  } else {
    // due_date: ascending, with no-due-date items pushed to the end.
    sorted.sort((a, b) => (a.due_date || "9999-99-99").localeCompare(b.due_date || "9999-99-99"));
  }
  return sorted;
}

async function loadAssignments() {
  const status = document.getElementById("assignment-status-filter").value;
  const sortBy = document.getElementById("assignment-sort").value;
  const list = sortAssignments(await api(`/assignments?status=${status}`), sortBy);
  const container = document.getElementById("assignment-list");
  container.innerHTML = "";
  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">No assignments here.</div>`;
    return;
  }
  list.forEach((a) => {
    const card = document.createElement("div");
    card.className = "card clickable";
    const points = a.importance * a.difficulty * 2;
    const earned = a.points_earned || 0;
    const milestoneSummary = a.milestone_count > 0
      ? ` &middot; milestones: ${a.milestones_done}/${a.milestone_count}`
      : "";
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-title">${escapeHtml(a.title)}</div>
          <div class="card-sub">${escapeHtml(a.course || "")}${a.due_date ? ` &middot; due ${escapeHtml(a.due_date)}` : ""}</div>
        </div>
        <span class="badge pts-badge">${earned}/${points} pts</span>
      </div>
      <div class="card-meta">status: ${a.status} &middot; importance: ${a.importance} &middot; difficulty: ${a.difficulty}${milestoneSummary}</div>
      <div class="card-actions"></div>
    `;
    stylePointsBadge(card.querySelector(".pts-badge"), points);
    card.addEventListener("click", () => openAssignmentDetail(a.id));
    const actions = card.querySelector(".card-actions");
    if (a.status === "open") {
      const startBtn = document.createElement("button");
      startBtn.className = "secondary";
      startBtn.textContent = "Start";
      startBtn.onclick = async (e) => {
        e.stopPropagation();
        await api(`/assignments/${a.id}/start`, { method: "POST" });
        loadAssignments();
        refreshPoints();
      };
      actions.appendChild(startBtn);
    }
    if (a.status !== "done") {
      const doneBtn = document.createElement("button");
      doneBtn.textContent = "Complete";
      doneBtn.onclick = async (e) => {
        e.stopPropagation();
        await api(`/assignments/${a.id}/complete`, { method: "POST" });
        loadAssignments();
        refreshPoints();
      };
      actions.appendChild(doneBtn);
    }
    container.appendChild(card);
  });
}

document.getElementById("assignment-status-filter").addEventListener("change", loadAssignments);
document.getElementById("assignment-sort").addEventListener("change", loadAssignments);

// --- Assignment detail view ---

const assignmentListView = document.getElementById("assignment-list-view");
const assignmentDetailView = document.getElementById("assignment-detail-view");
let currentDetailAssignmentId = null;

function showAssignmentListView() {
  currentDetailAssignmentId = null;
  assignmentDetailView.classList.add("hidden");
  assignmentListView.classList.remove("hidden");
  loadAssignments();
}

async function renderDetailMilestones() {
  const list = await api(`/assignments/${currentDetailAssignmentId}/milestones`);
  const container = document.getElementById("detail-milestones-list");
  container.innerHTML = "";
  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">No milestones yet.</div>`;
    return;
  }
  list.forEach((m) => {
    const row = document.createElement("div");
    row.className = "milestone-row";
    row.innerHTML = `
      <input type="checkbox" ${m.done ? "checked" : ""} />
      <span class="milestone-title ${m.done ? "done" : ""}">${escapeHtml(m.title)}</span>
      <span class="milestone-points">${m.points_awarded > 0 ? `+${m.points_awarded} pts` : ""}</span>
      <button type="button" class="milestone-delete" title="Delete">&times;</button>
    `;
    row.querySelector("input").addEventListener("change", async () => {
      await api(`/milestones/${m.id}/toggle`, { method: "POST" });
      renderDetailMilestones();
      renderAssignmentDetailHeader();
      refreshPoints();
    });
    row.querySelector(".milestone-delete").addEventListener("click", async (e) => {
      e.stopPropagation();
      await api(`/milestones/${m.id}`, { method: "DELETE" });
      renderDetailMilestones();
    });
    container.appendChild(row);
  });
}

async function renderAssignmentDetailHeader() {
  const a = await api(`/assignments/${currentDetailAssignmentId}`);
  const points = a.importance * a.difficulty * 2;
  const earned = a.points_earned || 0;

  document.getElementById("detail-title").textContent = a.title;
  document.getElementById("detail-sub").textContent = [a.course, a.due_date ? `due ${a.due_date}` : ""]
    .filter(Boolean).join(" · ");
  document.getElementById("detail-meta").textContent =
    `status: ${a.status} · importance: ${a.importance} · difficulty: ${a.difficulty}`;

  const badge = document.getElementById("detail-points-badge");
  badge.textContent = `${earned}/${points} pts`;
  stylePointsBadge(badge, points);

  const actions = document.getElementById("detail-actions");
  actions.innerHTML = "";
  if (a.status === "open") {
    const startBtn = document.createElement("button");
    startBtn.className = "secondary";
    startBtn.textContent = "Start";
    startBtn.onclick = async () => { await api(`/assignments/${a.id}/start`, { method: "POST" }); renderAssignmentDetailHeader(); refreshPoints(); };
    actions.appendChild(startBtn);
  }
  if (a.status !== "done") {
    const doneBtn = document.createElement("button");
    doneBtn.textContent = "Complete";
    doneBtn.onclick = async () => { await api(`/assignments/${a.id}/complete`, { method: "POST" }); renderAssignmentDetailHeader(); refreshPoints(); };
    actions.appendChild(doneBtn);
  }
}

async function openAssignmentDetail(assignmentId) {
  currentDetailAssignmentId = assignmentId;
  assignmentListView.classList.add("hidden");
  assignmentDetailView.classList.remove("hidden");
  await renderAssignmentDetailHeader();
  await renderDetailMilestones();
}

document.getElementById("assignment-detail-back").addEventListener("click", showAssignmentListView);

document.getElementById("detail-add-milestone-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("detail-new-milestone-title");
  const title = input.value.trim();
  if (!title) return;
  await api(`/assignments/${currentDetailAssignmentId}/milestones`, {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  input.value = "";
  renderDetailMilestones();
});

document.getElementById("detail-delete-assignment").addEventListener("click", async () => {
  if (!confirm("Delete this assignment and its milestones? No points are awarded or removed.")) return;
  await api(`/assignments/${currentDetailAssignmentId}`, { method: "DELETE" });
  showAssignmentListView();
});

document.getElementById("add-assignment-btn").addEventListener("click", () => {
  openGenericModal("Add assignment", [
    { name: "title", label: "Title", placeholder: "Problem set 4" },
    { name: "course", label: "Course", placeholder: "CS 101" },
    { name: "due_date", label: "Due date", placeholder: "2026-08-01" },
    { name: "importance", label: "Importance (1-5)", type: "number", value: 3 },
    { name: "difficulty", label: "Difficulty (1-5)", type: "number", value: 3 },
    { name: "milestones", label: "Milestones (one per line, optional)", type: "textarea", placeholder: "HTML page\nStylesheet\nJS wiring" },
  ], async (values) => {
    const { milestones, ...assignmentValues } = values;
    const created = await api("/assignments", { method: "POST", body: JSON.stringify(assignmentValues) });
    const titles = milestones.split("\n").map((t) => t.trim()).filter(Boolean);
    for (const title of titles) {
      await api(`/assignments/${created.id}/milestones`, { method: "POST", body: JSON.stringify({ title }) });
    }
    loadAssignments();
  });
});

// --- Awards ---

async function loadAwards() {
  const list = await api("/awards?active_only=true");
  const container = document.getElementById("award-list");
  container.innerHTML = "";
  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">No awards yet.</div>`;
    return;
  }
  list.forEach((award) => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-title">${escapeHtml(award.name)}</div>
          <div class="card-sub">${escapeHtml(award.description || "")}</div>
        </div>
        <span class="badge pts-badge">${award.cost} pts</span>
      </div>
      <div class="card-actions"></div>
    `;
    stylePointsBadge(card.querySelector(".pts-badge"), award.cost);
    const actions = card.querySelector(".card-actions");
    const redeemBtn = document.createElement("button");
    redeemBtn.textContent = "Redeem";
    redeemBtn.onclick = async () => {
      try {
        const result = await api(`/awards/${award.id}/redeem`, { method: "POST" });
        showRedeemModal(result);
        refreshPoints();
        loadRewardBanks();
        loadDollarTransactions();
      } catch (err) {
        alert(err.message);
      }
    };
    actions.appendChild(redeemBtn);
    if (!award.is_preset) {
      const deactivateBtn = document.createElement("button");
      deactivateBtn.className = "secondary";
      deactivateBtn.textContent = "Remove";
      deactivateBtn.onclick = async () => { await api(`/awards/${award.id}/deactivate`, { method: "POST" }); loadAwards(); };
      actions.appendChild(deactivateBtn);
    }
    container.appendChild(card);
  });
}

document.getElementById("add-award-btn").addEventListener("click", () => {
  openGenericModal("Add custom award", [
    { name: "name", label: "Name", placeholder: "Movie night" },
    { name: "cost", label: "Cost (points)", type: "number", value: 20 },
    { name: "description", label: "Description", type: "textarea" },
    { name: "break_minutes", label: "Break minutes banked (0 if not a break award)", type: "number", value: 0 },
    { name: "dollar_value", label: "$$ banked (0 if not a $$ award)", type: "number", value: 0 },
  ], async (values) => {
    await api("/awards", { method: "POST", body: JSON.stringify(values) });
    loadAwards();
  });
});

// --- Redeem popup ---

const redeemModal = document.getElementById("redeem-modal");
const redeemModalBody = document.getElementById("redeem-modal-body");

function showRedeemModal(result) {
  const parts = [`Redeemed **${result.redeemed}** for ${result.points_spent} pts.`, `New total: ${result.remaining_points} pts.`];
  if (result.break_minutes_added > 0) {
    parts.push(`+${result.break_minutes_added} min added to your break bank (now ${result.break_bank_total} min).`);
  }
  if (result.dollar_value_added > 0) {
    parts.push(`+$${result.dollar_value_added.toFixed(2)} added to your $$ bank (now $${result.dollar_bank_total.toFixed(2)}).`);
  }
  redeemModalBody.innerHTML = formatChatText(parts.join(" "));
  redeemModal.classList.remove("hidden");
}

document.getElementById("redeem-modal-close").addEventListener("click", () => {
  redeemModal.classList.add("hidden");
});

// --- Reward banks (break time / $$ accumulated from redeeming awards) ---

function formatTimer(totalSeconds) {
  const s = Math.max(0, Math.round(totalSeconds));
  const mins = Math.floor(s / 60).toString().padStart(2, "0");
  const secs = (s % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

const breakTimerDisplay = document.getElementById("break-timer-display");
const breakStartBtn = document.getElementById("break-timer-start");
const breakStopBtn = document.getElementById("break-timer-stop");

// Swap which button looks "active" (accent blue) vs muted so the running
// state is obvious at a glance, not just inferred from which is disabled.
function updateBreakButtonStyles() {
  if (breakRunning) {
    breakStartBtn.classList.add("secondary");
    breakStopBtn.classList.remove("secondary");
    breakStopBtn.classList.add("danger");
  } else {
    breakStartBtn.classList.remove("secondary");
    breakStopBtn.classList.remove("danger");
    breakStopBtn.classList.add("secondary");
  }
}

// The countdown starts from however many minutes are currently banked (e.g.
// 10 min banked opens at 10:00). Stopping pauses it at the exact second --
// e.g. stop at 7:32 and it sits at 7:32 until Start is pressed again, which
// resumes from there rather than restarting. A "session" spans from the
// first Start after idle to either full depletion or the user abandoning it;
// whole minutes actually used are billed to the bank incrementally as they
// tick by (not on every pause), so pausing never loses or double-charges time.
let breakBankMinutes = 0;
let breakSessionActive = false;
let breakRunning = false;
let breakRemainingSeconds = 0;
let breakStartedFromMinutes = 0;
let breakMinutesSpentThisSession = 0;
let breakTimerInterval = null;

async function loadRewardBanks() {
  const { break_minutes, dollars } = await api("/reward-banks");
  breakBankMinutes = break_minutes;
  document.getElementById("break-bank-value").textContent = `${break_minutes} min banked`;
  document.getElementById("dollar-bank-value").textContent = `$${dollars.toFixed(2)} banked`;
  // Don't clobber a paused/running countdown's exact display with the bank
  // total -- only sync the idle display when there's no session in progress.
  if (!breakSessionActive) {
    breakTimerDisplay.textContent = formatTimer(break_minutes * 60);
    breakStartBtn.disabled = break_minutes <= 0;
  }
}

// Bills whatever whole minutes have been used since the last bill, without
// touching the live countdown display.
async function billElapsedMinutes() {
  const elapsedSeconds = breakStartedFromMinutes * 60 - breakRemainingSeconds;
  const wholeMinutesUsed = Math.floor(elapsedSeconds / 60);
  const delta = wholeMinutesUsed - breakMinutesSpentThisSession;
  if (delta > 0) {
    const toSpend = Math.min(delta, breakBankMinutes);
    if (toSpend > 0) {
      await api("/reward-banks/spend-break", { method: "POST", body: JSON.stringify({ minutes: toSpend }) });
      breakBankMinutes -= toSpend;
      document.getElementById("break-bank-value").textContent = `${breakBankMinutes} min banked`;
    }
    breakMinutesSpentThisSession = wholeMinutesUsed;
  }
}

breakStartBtn.addEventListener("click", () => {
  if (!breakSessionActive) {
    if (breakBankMinutes <= 0) return;
    breakSessionActive = true;
    breakStartedFromMinutes = breakBankMinutes;
    breakRemainingSeconds = breakBankMinutes * 60;
    breakMinutesSpentThisSession = 0;
  }
  breakRunning = true;
  breakStartBtn.disabled = true;
  breakStopBtn.disabled = false;
  updateBreakButtonStyles();
  breakTimerInterval = setInterval(() => {
    breakRemainingSeconds -= 1;
    if (breakRemainingSeconds <= 0) {
      breakRemainingSeconds = 0;
      breakTimerDisplay.textContent = "00:00";
      clearInterval(breakTimerInterval);
      breakRunning = false;
      breakSessionActive = false;
      breakStopBtn.disabled = true;
      updateBreakButtonStyles();
      billElapsedMinutes().then(loadRewardBanks);
      return;
    }
    breakTimerDisplay.textContent = formatTimer(breakRemainingSeconds);
  }, 1000);
});

breakStopBtn.addEventListener("click", () => {
  clearInterval(breakTimerInterval);
  breakRunning = false;
  breakStartBtn.disabled = false;
  breakStopBtn.disabled = true;
  updateBreakButtonStyles();
  // Display stays exactly where it was on the last tick -- no reset.
  billElapsedMinutes();
});

updateBreakButtonStyles();

// --- $$ transactions ---

async function loadDollarTransactions() {
  const list = await api("/dollar-transactions?limit=10");
  const container = document.getElementById("dollar-transactions");
  container.innerHTML = "";
  if (list.length === 0) return;
  list.forEach((tx) => {
    const row = document.createElement("div");
    row.className = "transaction-row";
    const sign = tx.amount >= 0 ? "positive" : "negative";
    const amountText = `${tx.amount >= 0 ? "+" : "-"}$${Math.abs(tx.amount).toFixed(2)}`;
    row.innerHTML = `
      <span class="transaction-reason">${escapeHtml(tx.reason)}</span>
      <span class="transaction-amount ${sign}">${amountText}</span>
    `;
    container.appendChild(row);
  });
}

document.getElementById("dollar-spend-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const amountInput = document.getElementById("dollar-spend-amount");
  const reasonInput = document.getElementById("dollar-spend-reason");
  const amount = Number(amountInput.value);
  if (!amount || amount <= 0) return;
  try {
    await api("/reward-banks/spend-dollars", { method: "POST", body: JSON.stringify({ amount, reason: reasonInput.value }) });
    amountInput.value = "";
    reasonInput.value = "";
    loadRewardBanks();
    loadDollarTransactions();
  } catch (err) {
    alert(err.message);
  }
});

// --- Recruiting ---

// Pipeline order used when sorting by stage. Any stage not listed here
// (e.g. a hypothetical "not_applied") sorts first.
const STAGE_ORDER = ["applied", "oa", "interview", "offer", "rejected"];

const STAGE_META = {
  not_applied: { label: "Not applied", bg: "#6b7280", fg: "#f3f4f6" },
  applied: { label: "Applied", bg: "#8b5cf6", fg: "#f5f3ff" },
  oa: { label: "OA", bg: "#eab308", fg: "#1a1400" },
  interview: { label: "Interview", bg: "#f97316", fg: "#1a0f00" },
  offer: { label: "Offer", bg: "#22c55e", fg: "#052e12" },
  rejected: { label: "Rejected", bg: "#ef4444", fg: "#2b0000" },
};

function stageMeta(stage) {
  return STAGE_META[stage] || { ...STAGE_META.not_applied, label: stage };
}

function sortRecruiting(list, sortBy) {
  const sorted = [...list];
  if (sortBy === "stage") {
    sorted.sort((a, b) => {
      const ia = STAGE_ORDER.indexOf(a.stage);
      const ib = STAGE_ORDER.indexOf(b.stage);
      return (ia === -1 ? -1 : ia) - (ib === -1 ? -1 : ib);
    });
  } else {
    sorted.sort((a, b) => (a.next_action_date || "9999-99-99").localeCompare(b.next_action_date || "9999-99-99"));
  }
  return sorted;
}

async function loadRecruiting() {
  const sortBy = document.getElementById("recruiting-sort").value;
  const list = sortRecruiting(await api("/recruiting"), sortBy);
  const container = document.getElementById("recruiting-list");
  container.innerHTML = "";
  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">No recruiting entries yet.</div>`;
    return;
  }
  list.forEach((r) => {
    const card = document.createElement("div");
    card.className = "card";
    const meta = stageMeta(r.stage);
    card.innerHTML = `
      <div class="card-top">
        <div>
          <div class="card-title">${escapeHtml(r.company)}${r.role ? ` -- ${escapeHtml(r.role)}` : ""}</div>
          <div class="card-sub">${r.next_action ? `${escapeHtml(r.next_action)}${r.next_action_date ? ` by ${escapeHtml(r.next_action_date)}` : ""}` : ""}</div>
        </div>
        <span class="badge stage-badge">${escapeHtml(meta.label)}</span>
      </div>
      ${r.notes ? `<div class="card-meta">${escapeHtml(r.notes)}</div>` : ""}
    `;
    const stageBadge = card.querySelector(".stage-badge");
    stageBadge.style.background = meta.bg;
    stageBadge.style.color = meta.fg;
    stageBadge.style.borderColor = meta.bg;
    container.appendChild(card);
  });
}

document.getElementById("recruiting-sort").addEventListener("change", loadRecruiting);

document.getElementById("add-recruiting-btn").addEventListener("click", () => {
  openGenericModal("Add / update recruiting entry", [
    { name: "company", label: "Company", placeholder: "Acme Corp" },
    { name: "role", label: "Role", placeholder: "SWE Intern" },
    { name: "stage", label: "Stage", type: "select", options: [
      { value: "applied", label: "Applied" },
      { value: "oa", label: "OA" },
      { value: "interview", label: "Interview" },
      { value: "offer", label: "Offer" },
      { value: "rejected", label: "Rejected" },
    ] },
    { name: "next_action", label: "Next action", placeholder: "Follow up" },
    { name: "next_action_date", label: "Next action date", placeholder: "2026-08-01" },
    { name: "notes", label: "Notes", type: "textarea" },
  ], async (values) => {
    await api("/recruiting", { method: "POST", body: JSON.stringify(values) });
    loadRecruiting();
  });
});

// --- Settings ---

async function loadSettings() {
  const prefs = await api("/preferences");
  document.getElementById("settings-reward-style").value = prefs.reward_style;
  document.getElementById("settings-additional-rules").value = prefs.additional_rules;
  document.getElementById("settings-morning-reminders").checked = prefs.morning_reminders;
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const reward_style = document.getElementById("settings-reward-style").value;
  const additional_rules = document.getElementById("settings-additional-rules").value;
  const morning_reminders = document.getElementById("settings-morning-reminders").checked;
  await api("/preferences/reward-style", { method: "POST", body: JSON.stringify({ reward_style }) });
  await api("/preferences/additional-rules", { method: "POST", body: JSON.stringify({ additional_rules }) });
  await api("/preferences/morning-reminders", { method: "POST", body: JSON.stringify({ enabled: morning_reminders }) });
  alert("Preferences saved.");
});

// --- First-time setup modal ---

const setupModal = document.getElementById("setup-modal");

document.getElementById("setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const reward_style = document.getElementById("setup-reward-style").value;
  const additional_rules = document.getElementById("setup-additional-rules").value;
  const morning_reminders = document.getElementById("setup-morning-reminders").checked;
  await api("/setup", { method: "POST", body: JSON.stringify({ reward_style, additional_rules, morning_reminders }) });
  setupModal.classList.add("hidden");
  showWelcomeMessage();
});

// --- Utils ---

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

// --- Init ---

async function init() {
  const prefs = await api("/preferences");
  if (!prefs.onboarding_completed) {
    setupModal.classList.remove("hidden");
  } else {
    showWelcomeMessage();
  }
  refreshPoints();
}

init();
