// Vanilla JS SPA -- no build step, talks to the FastAPI backend under /api.

async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  // A server crash returns plain text, not JSON.
  const data = await res.json().catch(() => null);
  if (!res.ok || data === null) {
    const detail = typeof data?.detail === "string" ? data.detail : "";
    throw new Error(detail || "Something went wrong on the server. Please try again.");
  }
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

// --- Side menu: collapses to icons on desktop, slides in as a drawer on phones ---

const SIDEBAR_COLLAPSED_KEY = "mill-e-sidebar-collapsed";
const sidebarToggle = document.getElementById("sidebar-toggle");
const phoneLayout = matchMedia("(max-width: 760px)");
const bodyClasses = document.body.classList;

function renderSidebar() {
  const phone = phoneLayout.matches;
  const collapsed = bodyClasses.contains("sidebar-collapsed");
  const open = phone ? bodyClasses.contains("sidebar-open") : !collapsed;
  sidebarToggle.setAttribute("aria-expanded", String(open));
  sidebarToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.title = !phone && collapsed ? btn.getAttribute("aria-label") : "";
  });
}

function closeDrawer() {
  bodyClasses.remove("sidebar-open");
  renderSidebar();
}

sidebarToggle.addEventListener("click", () => {
  if (phoneLayout.matches) {
    bodyClasses.toggle("sidebar-open");
    if (bodyClasses.contains("sidebar-open")) document.querySelector(".tab-btn.active").focus();
  } else {
    const collapsed = bodyClasses.toggle("sidebar-collapsed");
    try {
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
    } catch {
      // The menu still collapses; it just won't be remembered next visit.
    }
  }
  renderSidebar();
});

document.getElementById("sidebar-scrim").addEventListener("click", closeDrawer);

document.getElementById("tabs").addEventListener("click", (e) => {
  if (phoneLayout.matches && e.target.closest(".tab-btn")) closeDrawer();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !bodyClasses.contains("sidebar-open")) return;
  closeDrawer();
  sidebarToggle.focus();
});

phoneLayout.addEventListener("change", closeDrawer);

try {
  bodyClasses.toggle("sidebar-collapsed", localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true");
} catch {
  // Storage can be blocked, e.g. in a private window; start expanded.
}
renderSidebar();

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

const CHAT_MS_PER_CHAR = 6;
const CHAT_MAX_TYPE_MS = 1500;

// Types out already-formatted HTML by revealing its text nodes, so tags never
// show mid-word. Untyped text stays in place, invisible, so the bubble keeps
// its final size. The clean HTML is restored at the end.
function typeChatHtml(el, html) {
  el.innerHTML = html;
  chatLog.scrollTop = chatLog.scrollHeight;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);
  const segments = textNodes.map((node) => {
    const typed = document.createTextNode("");
    const rest = document.createElement("span");
    rest.className = "type-rest";
    rest.textContent = node.nodeValue;
    const text = node.nodeValue;
    node.replaceWith(typed, rest);
    return { text, typed, rest };
  });

  const total = segments.reduce((sum, segment) => sum + segment.text.length, 0);
  if (total === 0) return;
  const duration = Math.min(total * CHAT_MS_PER_CHAR, CHAT_MAX_TYPE_MS);
  const caret = document.createElement("span");
  caret.className = "type-caret is-active";
  const start = performance.now();
  let segmentIndex = 0;
  let charsInFinishedSegments = 0;

  function drawFrame(now) {
    const shown = Math.min(total, Math.ceil((Math.max(0, now - start) / duration) * total));
    while (segmentIndex < segments.length) {
      const { text, typed, rest } = segments[segmentIndex];
      const shownHere = Math.min(shown - charsInFinishedSegments, text.length);
      typed.nodeValue = text.slice(0, shownHere);
      rest.textContent = text.slice(shownHere);
      rest.before(caret);
      if (shownHere < text.length) break;
      charsInFinishedSegments += text.length;
      segmentIndex++;
    }
    if (shown < total) requestAnimationFrame(drawFrame);
    else el.innerHTML = html;
  }
  requestAnimationFrame(drawFrame);
}

function appendChatMsg(text, role) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  chatLog.appendChild(div);
  if (role === "agent") {
    typeChatHtml(div, formatChatText(text));
  } else {
    div.innerHTML = formatChatText(text);
    chatLog.scrollTop = chatLog.scrollHeight;
  }
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
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const { reply } = await api("/chat", { method: "POST", body: JSON.stringify({ message, timezone }) });
    pendingEl.classList.remove("typing");
    typeChatHtml(pendingEl, formatChatText(reply));
  } catch (err) {
    pendingEl.classList.remove("typing");
    pendingEl.textContent = `Error: ${err.message}`;
  }
  refreshPoints();
  refreshDemoBanner();
});

// --- Public demo banner and starter prompts (hidden outside demo mode) ---

async function refreshDemoBanner() {
  const status = await api("/demo");
  if (!status.demo) return status;
  document.getElementById("demo-banner").classList.remove("hidden");
  const { available, email } = status.google;
  const left = status.messages_left;
  document.getElementById("demo-messages-left").textContent = email
    ? ""
    : `${left} chat ${left === 1 ? "message" : "messages"} left today.`;

  document.getElementById("google-connect").classList.toggle("hidden", !available || Boolean(email));
  document.getElementById("google-sign-out").classList.toggle("hidden", !email);
  const emailEl = document.getElementById("google-email");
  emailEl.classList.toggle("hidden", !email);
  emailEl.textContent = email || "";
  document.getElementById("demo-reset").classList.toggle("hidden", Boolean(email));
  if (email) {
    document.getElementById("demo-banner-text").textContent =
      "Your real inbox and calendar are connected. Emails are saved as Gmail drafts, never sent. This workspace is temporary and ends when you sign out.";
  }
  return status;
}

document.getElementById("google-sign-out").addEventListener("click", async () => {
  await api("/auth/google/sign-out", { method: "POST" });
  location.reload();
});

const GOOGLE_SIGN_IN_MESSAGES = {
  cancelled: "Google sign-in was cancelled, so you're still using the sample data.",
  permissions: "Google sign-in needs all of the requested permissions. You're still using the sample data.",
  failed: "Google sign-in didn't complete. Please try again.",
};

function showGoogleSignInResult() {
  const params = new URLSearchParams(location.search);
  const message = GOOGLE_SIGN_IN_MESSAGES[params.get("google")];
  if (message) appendChatMsg(message, "agent");
  if (params.has("google")) history.replaceState(null, "", "/app");
}

document.getElementById("demo-reset").addEventListener("click", async () => {
  await api("/demo/reset", { method: "POST" });
  location.reload();
});

const demoPrompts = document.getElementById("demo-prompts");

demoPrompts.addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  demoPrompts.classList.add("hidden");
  chatInput.value = btn.textContent;
  chatForm.requestSubmit();
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
  const customReaders = {};
  fields.forEach((f) => {
    const label = document.createElement("label");
    label.textContent = f.label;
    genericModalForm.appendChild(label);

    const buildCustomField = CUSTOM_FIELDS[f.type];
    if (buildCustomField) {
      const { root, getValue } = buildCustomField(f);
      genericModalForm.appendChild(root);
      customReaders[f.name] = getValue;
      return;
    }

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
    if (f.required) input.required = true;
    if (f.value !== undefined) input.value = f.value;
    genericModalForm.appendChild(input);
    if (f.type === "select") enhanceSelect(input);
  });

  const errorEl = document.createElement("p");
  errorEl.className = "modal-error hidden";
  errorEl.setAttribute("role", "alert");
  genericModalForm.appendChild(errorEl);

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
    errorEl.classList.add("hidden");
    submitBtn.disabled = true;
    try {
      const values = {};
      fields.forEach((f) => {
        if (customReaders[f.name]) {
          values[f.name] = customReaders[f.name]();
          return;
        }
        const el = document.getElementById(`gm-${f.name}`);
        values[f.name] = f.type === "number" ? Number(el.value) : el.value;
      });
      await onSubmit(values);
      closeGenericModal();
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove("hidden");
    } finally {
      submitBtn.disabled = false;
    }
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

let currentDetailStatus = null;

// Undo stays available so a milestone that's already done can always be reversed.
function updateMilestoneLocks() {
  const locked = currentDetailStatus === "open";
  document.querySelectorAll("#detail-milestones-list .milestone-done-btn").forEach((button) => {
    const blocked = locked && !button.classList.contains("is-undo");
    button.disabled = blocked;
    button.title = blocked ? "Start this assignment first" : "";
  });
  const hasMilestones = document.querySelector("#detail-milestones-list .milestone-row") !== null;
  document.getElementById("detail-milestone-lock").classList.toggle("hidden", !locked || !hasMilestones);
}

function updateMilestoneCount(milestones) {
  const done = milestones.filter((m) => m.done).length;
  document.getElementById("detail-milestone-count").textContent =
    milestones.length ? `${done} of ${milestones.length} done` : "";
}

function applyMilestoneState(row, milestone, justToggled) {
  row.classList.toggle("is-done", Boolean(milestone.done));
  const button = row.querySelector(".milestone-done-btn");
  button.textContent = milestone.done ? "Undo" : "Done";
  button.classList.toggle("is-undo", Boolean(milestone.done));
  button.setAttribute("aria-label", `${milestone.done ? "Undo" : "Mark done:"} ${milestone.title}`);

  const points = row.querySelector(".milestone-points");
  if (milestone.points_awarded > 0) {
    points.textContent = `+${milestone.points_awarded} pts`;
  } else {
    points.textContent = milestone.point_percent ? `${milestone.point_percent}%` : "";
  }
  points.classList.toggle("is-earned", justToggled && Boolean(milestone.done));
  updateMilestoneLocks();
}

function createDetailMeter(label, value) {
  const stat = document.createElement("div");
  stat.className = "detail-stat";
  stat.setAttribute("role", "img");
  stat.setAttribute("aria-label", `${label}: ${value} of 5`);
  const name = document.createElement("span");
  name.textContent = label;
  const pips = document.createElement("span");
  pips.className = "detail-pips";
  for (let i = 1; i <= 5; i++) {
    const pip = document.createElement("span");
    if (i <= value) pip.className = "is-filled";
    pips.append(pip);
  }
  stat.append(name, pips);
  return stat;
}

const ASSIGNMENT_STATUS_LABELS = { open: "Not started", in_progress: "In progress", done: "Done" };

async function renderDetailMilestones() {
  const list = await api(`/assignments/${currentDetailAssignmentId}/milestones`);
  const container = document.getElementById("detail-milestones-list");
  const errorEl = document.getElementById("detail-milestone-error");
  container.innerHTML = "";
  updateMilestoneCount(list);
  if (list.length === 0) {
    container.innerHTML = `<div class="empty-state">No milestones yet.</div>`;
    updateMilestoneLocks();
    return;
  }
  list.forEach((m) => {
    const row = document.createElement("div");
    row.className = "milestone-row";
    row.innerHTML = `
      <span class="milestone-title"><span class="milestone-text">${escapeHtml(m.title)}</span></span>
      <span class="milestone-points"></span>
      <button type="button" class="milestone-done-btn"></button>
      <button type="button" class="milestone-delete" title="Delete">&times;</button>
    `;
    row.querySelector(".milestone-delete").setAttribute("aria-label", `Delete ${m.title}`);
    applyMilestoneState(row, m, false);

    // The row is updated in place, not re-rendered, so its strikethrough can animate.
    let toggling = false;
    row.querySelector(".milestone-done-btn").addEventListener("click", async () => {
      if (toggling) return;
      toggling = true;
      errorEl.classList.add("hidden");
      try {
        const result = await api(`/milestones/${m.id}/toggle`, { method: "POST" });
        m.done = result.done;
        m.points_awarded = result.points_awarded;
        applyMilestoneState(row, m, true);
        updateMilestoneCount(list);
        renderAssignmentDetailHeader();
        refreshPoints();
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
      } finally {
        toggling = false;
      }
    });
    row.querySelector(".milestone-delete").addEventListener("click", async (e) => {
      e.stopPropagation();
      await api(`/milestones/${m.id}`, { method: "DELETE" });
      renderDetailMilestones();
    });
    container.appendChild(row);
  });
  updateMilestoneLocks();
}

async function renderAssignmentDetailHeader() {
  const a = await api(`/assignments/${currentDetailAssignmentId}`);
  currentDetailStatus = a.status;
  updateMilestoneLocks();
  const points = a.importance * a.difficulty * 2;
  const earned = a.points_earned || 0;

  document.getElementById("detail-title").textContent = a.title;
  document.getElementById("detail-sub").textContent = [a.course, a.due_date ? `due ${a.due_date}` : ""]
    .filter(Boolean).join(" · ");
  const status = document.createElement("span");
  status.className = `badge detail-status is-${a.status}`;
  status.textContent = ASSIGNMENT_STATUS_LABELS[a.status] || a.status;
  document.getElementById("detail-meta").replaceChildren(
    status,
    createDetailMeter("Importance", a.importance),
    createDetailMeter("Difficulty", a.difficulty),
  );

  const badge = document.getElementById("detail-points-badge");
  badge.textContent = `${earned}/${points} pts`;
  stylePointsBadge(badge, points);

  const progress = document.getElementById("detail-progress");
  progress.setAttribute("aria-valuemax", String(points));
  progress.setAttribute("aria-valuenow", String(Math.min(earned, points)));
  document.getElementById("detail-progress-fill").style.width = `${Math.min(100, (earned / points) * 100)}%`;

  const { point_rules_summary: ruleSummary } = await api("/preferences");
  const ruleNote = document.getElementById("detail-point-rule");
  ruleNote.textContent = ruleSummary;
  ruleNote.classList.toggle("hidden", !ruleSummary);

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
  const percentInput = document.getElementById("detail-new-milestone-percent");
  const errorEl = document.getElementById("detail-milestone-error");
  const title = input.value.trim();
  if (!title) return;
  const point_percent = parseMilestonePercent(percentInput.value);
  try {
    if (point_percent === undefined) throw new Error("Enter a whole percent from 1 to 100, or leave it blank for Auto.");
    await api(`/assignments/${currentDetailAssignmentId}/milestones`, {
      method: "POST",
      body: JSON.stringify({ title, point_percent }),
    });
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
    return;
  }
  errorEl.classList.add("hidden");
  input.value = "";
  percentInput.value = "";
  renderDetailMilestones();
});

document.getElementById("detail-delete-assignment").addEventListener("click", async () => {
  if (!confirm("Delete this assignment and its milestones? No points are awarded or removed.")) return;
  await api(`/assignments/${currentDetailAssignmentId}`, { method: "DELETE" });
  showAssignmentListView();
});

document.getElementById("add-assignment-btn").addEventListener("click", () => {
  openGenericModal("Add assignment", [
    { name: "title", label: "Title", placeholder: "Problem set 4", required: true },
    { name: "course", label: "Course", placeholder: "CS 101" },
    { name: "due_date", label: "Due date", type: "date" },
    { name: "importance", label: "Importance", type: "scale", lowLabel: "Low", highLabel: "High" },
    { name: "difficulty", label: "Difficulty", type: "scale", lowLabel: "Easy", highLabel: "Hard" },
    { name: "milestones", label: "Milestones (optional)", type: "milestones" },
  ], async (values) => {
    await api("/assignments", { method: "POST", body: JSON.stringify(values) });
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
      <div class="card-actions award-actions"></div>
      <p class="modal-error award-error hidden" role="alert"></p>
    `;
    stylePointsBadge(card.querySelector(".pts-badge"), award.cost);
    const actions = card.querySelector(".card-actions");
    const errorEl = card.querySelector(".award-error");
    const redeemBtn = document.createElement("button");
    const stepper = createQuantityStepper({
      label: `Quantity of ${award.name}`,
      max: 99,
      onChange: (quantity) => {
        redeemBtn.textContent = `Redeem for ${award.cost * quantity} pts`;
        errorEl.classList.add("hidden");
      },
    });
    let redeeming = false;
    redeemBtn.onclick = async () => {
      if (redeeming) return;
      redeeming = true;
      try {
        const result = await api(`/awards/${award.id}/redeem`, {
          method: "POST",
          body: JSON.stringify({ quantity: stepper.getValue() }),
        });
        stepper.reset();
        showRedeemModal(result);
        refreshPoints();
        loadRewardBanks();
        loadDollarTransactions();
      } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove("hidden");
      } finally {
        redeeming = false;
      }
    };
    actions.append(stepper.root, redeemBtn);
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

const redeemModalTitle = document.getElementById("redeem-modal-title");
const redeemModalClose = document.getElementById("redeem-modal-close");
const REDEEM_LEAVE_MS = 180; // matches the .is-leaving animation in style.css
let redeemReturnFocus = null;

function showRedeemModal(result) {
  const name = result.quantity > 1 ? `${result.quantity} x ${result.redeemed}` : result.redeemed;
  const parts = [`Redeemed **${name}** for ${result.points_spent} pts.`, `New total: ${result.remaining_points} pts.`];
  if (result.break_minutes_added > 0) {
    parts.push(`+${result.break_minutes_added} min added to your break bank (now ${result.break_bank_total} min).`);
  }
  if (result.dollar_value_added > 0) {
    parts.push(`+$${result.dollar_value_added.toFixed(2)} added to your $$ bank (now $${result.dollar_bank_total.toFixed(2)}).`);
  }
  showSuccessPopup("Reward redeemed!", parts.join(" "));
}

// The animated confirmation pop-up, shared by rewards and settings.
function showSuccessPopup(title, message) {
  redeemModalTitle.textContent = title;
  redeemModalBody.innerHTML = formatChatText(message);
  redeemReturnFocus = document.activeElement;
  redeemModal.classList.remove("hidden", "is-leaving");
  redeemModal.classList.add("is-entering");
  redeemModalClose.focus({ preventScroll: true });
}

redeemModalClose.addEventListener("click", () => {
  if (redeemModal.classList.contains("is-leaving")) return;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  redeemModal.classList.remove("is-entering");
  redeemModal.classList.add("is-leaving");
  setTimeout(() => {
    redeemModal.classList.add("hidden");
    redeemModal.classList.remove("is-leaving");
    redeemReturnFocus?.focus({ preventScroll: true });
  }, reduceMotion ? 0 : REDEEM_LEAVE_MS);
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
  const errorEl = document.getElementById("dollar-spend-error");
  errorEl.classList.add("hidden");
  const typed = amountInput.value.trim().replace(/^\$/, "").replaceAll(",", "");
  const amount = Number(typed);
  try {
    if (!/^(\d+(\.\d{0,2})?|\.\d{1,2})$/.test(typed) || amount <= 0) {
      throw new Error("Enter an amount like 4.50.");
    }
    await api("/reward-banks/spend-dollars", { method: "POST", body: JSON.stringify({ amount, reason: reasonInput.value }) });
    amountInput.value = "";
    reasonInput.value = "";
    loadRewardBanks();
    loadDollarTransactions();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
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
    { name: "next_action_date", label: "Next action date", type: "date" },
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
  syncDropdown(document.getElementById("settings-reward-style"));
  document.getElementById("settings-additional-rules").value = prefs.additional_rules;
  document.getElementById("settings-morning-reminders").checked = prefs.morning_reminders;
  showRuleEffect(prefs.point_rules_summary);
}

function showRuleEffect(summary) {
  const el = document.getElementById("settings-rule-effect");
  el.textContent = summary ? `Applied to points: ${summary}` : "";
  el.classList.toggle("hidden", !summary);
}

function savedPreferencesMessage({ additional_rules, point_rules_summary }) {
  if (point_rules_summary) return `Your rules now apply to points. ${point_rules_summary}`;
  if (additional_rules.trim()) {
    return "The assistant will follow your rules in chat. They don't change how points are earned.";
  }
  return "Your reward style, additional rules, and reminder setting are up to date.";
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const reward_style = document.getElementById("settings-reward-style").value;
  const additional_rules = document.getElementById("settings-additional-rules").value;
  const morning_reminders = document.getElementById("settings-morning-reminders").checked;
  const errorEl = document.getElementById("settings-error");
  const saveBtn = e.target.querySelector('button[type="submit"]');
  errorEl.classList.add("hidden");
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";
  try {
    // Rules go first: they're the only step that can fail for outside reasons.
    const saved = await api("/preferences/additional-rules", { method: "POST", body: JSON.stringify({ additional_rules }) });
    await api("/preferences/reward-style", { method: "POST", body: JSON.stringify({ reward_style }) });
    await api("/preferences/morning-reminders", { method: "POST", body: JSON.stringify({ enabled: morning_reminders }) });
    showRuleEffect(saved.point_rules_summary);
    saveBtn.disabled = false;
    saveBtn.focus({ preventScroll: true }); // disabling it dropped keyboard focus
    showSuccessPopup("Preferences saved!", savedPreferencesMessage(saved));
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = "Save preferences";
  }
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
  const demoStatus = await refreshDemoBanner();
  if (demoStatus.demo && !demoStatus.google.email) demoPrompts.classList.remove("hidden");
  showGoogleSignInResult();
}

init();
