// Custom field types for the shared pop-up form in app.js. Each builder returns
// { root, getValue }; getValue may throw an Error whose message the form shows.

const CUSTOM_FIELDS = {
  date: createDateField,
  scale: createScaleField,
  milestones: createMilestonesField,
};

function formatIsoDate(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

// new Date("YYYY-MM-DD") means midnight UTC, which can land on the previous
// day locally, so dates are always built from their parts.
function parseIsoDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function createDateField(field) {
  const root = document.createElement("div");
  root.className = "date-field";
  let selected = field.value || "";
  let focusDate = selected ? parseIsoDate(selected) : new Date();
  let view = new Date(focusDate.getFullYear(), focusDate.getMonth(), 1);
  let stopDismissing = null;

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "dropdown-trigger";
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute("aria-expanded", "false");
  const valueEl = document.createElement("span");
  trigger.append(valueEl);
  trigger.insertAdjacentHTML(
    "beforeend",
    '<svg class="dropdown-chevron" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
  );

  const popup = document.createElement("div");
  popup.className = "date-popup hidden";
  popup.setAttribute("role", "dialog");
  popup.setAttribute("aria-label", field.label);

  const header = document.createElement("div");
  header.className = "date-header";
  const navButton = (label, symbol, months) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "date-nav";
    button.setAttribute("aria-label", label);
    button.textContent = symbol;
    button.addEventListener("click", () => {
      view = new Date(view.getFullYear(), view.getMonth() + months, 1);
      focusDate = new Date(view);
      renderGrid();
    });
    return button;
  };
  const monthEl = document.createElement("div");
  monthEl.className = "date-month";
  monthEl.setAttribute("aria-live", "polite");
  header.append(navButton("Previous month", "←", -1), monthEl, navButton("Next month", "→", 1));

  const weekdays = document.createElement("div");
  weekdays.className = "date-grid";
  weekdays.setAttribute("aria-hidden", "true");
  ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].forEach((name) => {
    const cell = document.createElement("span");
    cell.className = "date-weekday";
    cell.textContent = name;
    weekdays.append(cell);
  });

  const grid = document.createElement("div");
  grid.className = "date-grid";

  const footer = document.createElement("div");
  footer.className = "date-footer";
  const footerButton = (label, onClick) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "date-link";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  };
  footer.append(
    footerButton("Today", () => choose(formatIsoDate(new Date()))),
    footerButton("Clear", () => choose("")),
  );

  popup.append(header, weekdays, grid, footer);
  root.append(trigger, popup);

  function renderTrigger() {
    const text = selected
      ? parseIsoDate(selected).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" })
      : "Pick a date";
    valueEl.textContent = text;
    valueEl.classList.toggle("date-placeholder", !selected);
    trigger.setAttribute("aria-label", `${field.label}: ${text}`);
  }

  function renderGrid() {
    monthEl.textContent = view.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    grid.replaceChildren();
    for (let i = 0; i < view.getDay(); i++) grid.append(document.createElement("span"));

    const today = formatIsoDate(new Date());
    const focusIso = formatIsoDate(focusDate);
    const daysInMonth = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(view.getFullYear(), view.getMonth(), day);
      const iso = formatIsoDate(date);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "date-day";
      button.dataset.date = iso;
      button.textContent = String(day);
      button.tabIndex = iso === focusIso ? 0 : -1;
      button.setAttribute("aria-label", date.toLocaleDateString(undefined, { dateStyle: "full" }));
      button.setAttribute("aria-pressed", String(iso === selected));
      if (iso === today) button.classList.add("is-today");
      button.addEventListener("click", () => choose(iso));
      grid.append(button);
    }
  }

  function moveFocus(date) {
    focusDate = date;
    view = new Date(date.getFullYear(), date.getMonth(), 1);
    renderGrid();
    grid.querySelector(`[data-date="${formatIsoDate(date)}"]`).focus();
  }

  function shiftDays(days) {
    return new Date(focusDate.getFullYear(), focusDate.getMonth(), focusDate.getDate() + days);
  }

  // Lands on the same day next month, or that month's last day if it's shorter.
  function shiftMonths(months) {
    const lastDay = new Date(focusDate.getFullYear(), focusDate.getMonth() + months + 1, 0).getDate();
    return new Date(focusDate.getFullYear(), focusDate.getMonth() + months, Math.min(focusDate.getDate(), lastDay));
  }

  grid.addEventListener("keydown", (e) => {
    const moves = {
      ArrowLeft: () => shiftDays(-1),
      ArrowRight: () => shiftDays(1),
      ArrowUp: () => shiftDays(-7),
      ArrowDown: () => shiftDays(7),
      PageUp: () => shiftMonths(-1),
      PageDown: () => shiftMonths(1),
    };
    if (e.key in moves) {
      e.preventDefault();
      moveFocus(moves[e.key]());
    }
  });

  function open() {
    focusDate = selected ? parseIsoDate(selected) : new Date();
    view = new Date(focusDate.getFullYear(), focusDate.getMonth(), 1);
    renderGrid();
    popup.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
    positionPopup(trigger, popup);
    stopDismissing = dismissPopupOnOutsideActivity(root, popup, close);
    grid.querySelector('[tabindex="0"]').focus();
  }

  function close() {
    popup.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
    stopDismissing?.();
    stopDismissing = null;
  }

  function choose(iso) {
    selected = iso;
    renderTrigger();
    close();
    trigger.focus();
  }

  trigger.addEventListener("click", () => (popup.classList.contains("hidden") ? open() : close()));
  popup.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    close();
    trigger.focus();
  });
  // relatedTarget is null when a re-rendered day loses focus, so only a real
  // move to another control (like tabbing away) closes the calendar.
  root.addEventListener("focusout", (e) => {
    if (e.relatedTarget && !root.contains(e.relatedTarget)) close();
  });

  renderTrigger();
  return { root, getValue: () => selected };
}

// A themed - / number / + control. Used on reward cards, not in the pop-up form.
function createQuantityStepper({ label, max, onChange }) {
  const root = document.createElement("div");
  root.className = "qty-stepper";
  root.setAttribute("role", "group");
  root.setAttribute("aria-label", label);

  const stepButton = (symbol, name, delta) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = symbol;
    button.setAttribute("aria-label", name);
    button.addEventListener("click", () => setValue(getValue() + delta));
    return button;
  };
  const minus = stepButton("−", "Decrease quantity", -1);
  const plus = stepButton("+", "Increase quantity", 1);
  const input = document.createElement("input");
  input.type = "text";
  input.inputMode = "numeric";
  input.autocomplete = "off";
  input.value = "1";
  input.setAttribute("aria-label", "Quantity");
  root.append(minus, input, plus);

  function clamp(value) {
    return Math.min(max, Math.max(1, Number.isNaN(value) ? 1 : value));
  }

  function getValue() {
    return clamp(parseInt(input.value, 10));
  }

  function refresh() {
    minus.disabled = getValue() <= 1;
    plus.disabled = getValue() >= max;
    onChange(getValue());
  }

  function setValue(value) {
    input.value = String(clamp(value));
    refresh();
  }

  input.addEventListener("input", () => {
    input.value = input.value.replace(/\D/g, "").slice(0, String(max).length);
    refresh();
  });
  input.addEventListener("blur", () => setValue(getValue()));

  refresh();
  return { root, getValue, reset: () => setValue(1) };
}

function createScaleField(field) {
  const root = document.createElement("div");
  root.className = "scale-field";
  root.setAttribute("role", "radiogroup");
  root.setAttribute("aria-label", field.label);

  const options = document.createElement("div");
  options.className = "scale-options";
  for (let value = 1; value <= 5; value++) {
    const option = document.createElement("label");
    option.className = "scale-option";
    const input = document.createElement("input");
    input.type = "radio";
    input.className = "visually-hidden";
    input.name = `scale-${field.name}`;
    input.value = String(value);
    input.checked = value === (field.value ?? 3);
    const face = document.createElement("span");
    face.textContent = String(value);
    option.append(input, face);
    options.append(option);
  }

  const hints = document.createElement("div");
  hints.className = "scale-hints";
  hints.setAttribute("aria-hidden", "true");
  const low = document.createElement("span");
  low.textContent = field.lowLabel;
  const high = document.createElement("span");
  high.textContent = field.highLabel;
  hints.append(low, high);

  root.append(options, hints);
  return { root, getValue: () => Number(root.querySelector("input:checked").value) };
}

// Returns a whole number from 1 to 100, null if blank, or undefined if invalid.
function parseMilestonePercent(text) {
  const trimmed = text.trim().replace(/%$/, "").trim();
  if (trimmed === "") return null;
  if (!/^\d+$/.test(trimmed)) return undefined;
  const percent = Number(trimmed);
  return percent >= 1 && percent <= 100 ? percent : undefined;
}

// Mirrors _milestone_total_percent in db_tool.py, for instant feedback. The
// server re-checks this before saving.
function milestonesTotalPercent(milestones) {
  const defaultPercent = 50 / Math.max(milestones.length, 1);
  return milestones.reduce((sum, m) => sum + (m.point_percent ?? defaultPercent), 0);
}

function createMilestonesField() {
  const root = document.createElement("div");
  root.className = "milestones-field";
  const milestones = [];

  const addRow = document.createElement("div");
  addRow.className = "milestone-add-row";
  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.placeholder = "Milestone name";
  titleInput.autocomplete = "off";
  titleInput.setAttribute("aria-label", "Milestone name");
  const percentInput = document.createElement("input");
  percentInput.type = "text";
  percentInput.inputMode = "numeric";
  percentInput.className = "milestone-percent-input";
  percentInput.placeholder = "Auto %";
  percentInput.autocomplete = "off";
  percentInput.setAttribute("aria-label", "Percent of the assignment's points (optional)");
  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "secondary";
  addButton.textContent = "Add";
  addRow.append(titleInput, percentInput, addButton);

  const errorEl = document.createElement("p");
  errorEl.className = "modal-error hidden";
  errorEl.setAttribute("role", "alert");
  const list = document.createElement("div");
  list.className = "milestone-draft-list";
  const summary = document.createElement("p");
  summary.className = "milestone-summary hidden";
  root.append(addRow, errorEl, list, summary);

  function showError(message) {
    errorEl.textContent = message;
    errorEl.classList.toggle("hidden", !message);
  }

  function renderList() {
    const defaultPercent = 50 / Math.max(milestones.length, 1);
    list.replaceChildren(...milestones.map((milestone, index) => {
      const row = document.createElement("div");
      row.className = "milestone-draft";
      const title = document.createElement("span");
      title.className = "milestone-title";
      title.textContent = milestone.title;
      const share = document.createElement("span");
      share.className = "milestone-points";
      share.textContent = milestone.point_percent === null
        ? `Auto, ${Math.round(defaultPercent)}%`
        : `${milestone.point_percent}%`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "milestone-delete";
      remove.setAttribute("aria-label", `Remove ${milestone.title}`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        milestones.splice(index, 1);
        renderList();
      });
      row.append(title, share, remove);
      return row;
    }));

    const used = Math.round(milestonesTotalPercent(milestones));
    summary.textContent = `Milestones ${used}% of points, starting and finishing ${100 - used}%`;
    summary.classList.toggle("hidden", milestones.length === 0);
  }

  // Returns an error message, or "" if the typed milestone was added or blank.
  function addTypedMilestone() {
    const title = titleInput.value.trim();
    if (!title) return percentInput.value.trim() ? "Give the milestone a name first." : "";
    const percent = parseMilestonePercent(percentInput.value);
    if (percent === undefined) return "Enter a whole percent from 1 to 100, or leave it blank for Auto.";
    const candidate = [...milestones, { title, point_percent: percent }];
    const total = milestonesTotalPercent(candidate);
    if (total > 100.000001) {
      return `That would put milestones at ${Math.round(total)}% of the points. Keep the total at 100% or less.`;
    }
    milestones.push(candidate.at(-1));
    titleInput.value = "";
    percentInput.value = "";
    renderList();
    return "";
  }

  function addFromControls() {
    const error = addTypedMilestone();
    showError(error);
    if (!error) titleInput.focus();
  }

  addButton.addEventListener("click", addFromControls);
  [titleInput, percentInput].forEach((input) => {
    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault(); // Enter adds the milestone instead of saving the form
      addFromControls();
    });
  });

  return {
    root,
    getValue() {
      // Include a milestone that was typed but not added before pressing Save.
      const error = addTypedMilestone();
      if (error) throw new Error(error);
      return milestones.map((milestone) => ({ ...milestone }));
    },
  };
}
