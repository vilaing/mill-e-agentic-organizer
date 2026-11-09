// Themed dropdowns. Each one wraps a hidden native <select>, which stays the
// source of truth, so existing code can keep reading .value and listening for
// "change". The markup follows the ARIA select-only combobox pattern.

const dropdownRenderers = new WeakMap();
let dropdownCount = 0;

// position: fixed lets popups escape modals that scroll or clip their content.
function positionPopup(anchor, popup) {
  const rect = anchor.getBoundingClientRect();
  popup.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - popup.offsetWidth - 8))}px`;
  const spaceBelow = innerHeight - rect.bottom - 8;
  const openUpward = popup.offsetHeight > spaceBelow && rect.top > spaceBelow;
  popup.style.top = `${openUpward ? Math.max(8, rect.top - popup.offsetHeight - 4) : rect.bottom + 4}px`;
}

// Closes a popup on outside clicks, page scrolling, or resizing. Returns a
// function that removes the listeners.
function dismissPopupOnOutsideActivity(root, popup, close) {
  const onPointerDown = (e) => {
    if (!root.contains(e.target)) close();
  };
  const onScrollOrResize = (e) => {
    if (e.type === "scroll" && popup.contains(e.target)) return;
    close();
  };
  document.addEventListener("pointerdown", onPointerDown);
  window.addEventListener("scroll", onScrollOrResize, true);
  window.addEventListener("resize", onScrollOrResize);
  return () => {
    document.removeEventListener("pointerdown", onPointerDown);
    window.removeEventListener("scroll", onScrollOrResize, true);
    window.removeEventListener("resize", onScrollOrResize);
  };
}

// Call after setting a <select>'s value from code.
function syncDropdown(select) {
  dropdownRenderers.get(select)?.();
}

function enhanceSelect(select) {
  const labelEl = select.previousElementSibling;
  const name = select.getAttribute("aria-label")
    || (labelEl && labelEl.matches("label") ? labelEl.textContent : "");
  const id = `dropdown-${++dropdownCount}`;

  const wrapper = document.createElement("div");
  wrapper.className = "dropdown";
  select.before(wrapper);
  select.classList.add("native-select");
  wrapper.append(select);

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "dropdown-trigger";
  trigger.setAttribute("role", "combobox");
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-controls", `${id}-menu`);
  if (name) trigger.setAttribute("aria-label", name);

  // Every label sits in the same grid cell, invisibly, so the trigger is always
  // as wide as its longest option and doesn't resize when the choice changes.
  const value = document.createElement("span");
  value.className = "dropdown-value";
  const current = document.createElement("span");
  const sizers = [...select.options].map((option) => {
    const sizer = document.createElement("span");
    sizer.className = "dropdown-sizer";
    sizer.setAttribute("aria-hidden", "true");
    sizer.textContent = option.textContent;
    return sizer;
  });
  value.append(...sizers, current);
  trigger.append(value);
  trigger.insertAdjacentHTML(
    "beforeend",
    '<svg class="dropdown-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
  );

  const menu = document.createElement("div");
  menu.className = "dropdown-menu hidden";
  menu.id = `${id}-menu`;
  menu.setAttribute("role", "listbox");
  if (name) menu.setAttribute("aria-label", name);
  const items = [...select.options].map((option, index) => {
    const item = document.createElement("div");
    item.className = "dropdown-option";
    item.id = `${id}-option-${index}`;
    item.setAttribute("role", "option");
    item.textContent = option.textContent;
    item.addEventListener("mousemove", () => setActive(index));
    item.addEventListener("mousedown", (e) => e.preventDefault()); // keep focus on the trigger
    item.addEventListener("click", () => choose(index));
    menu.append(item);
    return item;
  });
  wrapper.append(trigger, menu);

  let activeIndex = 0;
  const isOpen = () => trigger.getAttribute("aria-expanded") === "true";

  function render() {
    const selected = select.selectedIndex;
    current.textContent = select.options[selected]?.textContent ?? "";
    items.forEach((item, index) => item.setAttribute("aria-selected", String(index === selected)));
  }

  function setActive(index) {
    activeIndex = index;
    items.forEach((item, i) => item.classList.toggle("is-active", i === index));
    trigger.setAttribute("aria-activedescendant", items[index].id);
    items[index].scrollIntoView({ block: "nearest" });
  }

  let stopDismissing = null;

  function open() {
    menu.classList.remove("hidden");
    trigger.setAttribute("aria-expanded", "true");
    menu.style.minWidth = `${trigger.offsetWidth}px`;
    positionPopup(trigger, menu);
    setActive(Math.max(0, select.selectedIndex));
    stopDismissing = dismissPopupOnOutsideActivity(wrapper, menu, close);
  }

  function close() {
    menu.classList.add("hidden");
    trigger.setAttribute("aria-expanded", "false");
    trigger.removeAttribute("aria-activedescendant");
    stopDismissing?.();
    stopDismissing = null;
  }

  function choose(index) {
    if (select.selectedIndex !== index) {
      select.selectedIndex = index;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      render();
    }
    close();
    trigger.focus();
  }

  trigger.addEventListener("click", () => (isOpen() ? close() : open()));

  trigger.addEventListener("keydown", (e) => {
    const last = items.length - 1;
    if (!isOpen()) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        open();
      }
      return;
    }
    const moves = {
      ArrowDown: Math.min(activeIndex + 1, last),
      ArrowUp: Math.max(activeIndex - 1, 0),
      Home: 0,
      End: last,
    };
    if (e.key in moves) {
      e.preventDefault();
      setActive(moves[e.key]);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      choose(activeIndex);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
    } else if (e.key === "Tab") {
      close();
    }
  });

  dropdownRenderers.set(select, render);
  render();
}

document.querySelectorAll("select").forEach(enhanceSelect);
