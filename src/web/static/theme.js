// Loaded in <head>, before the page paints, so a saved theme never flashes the wrong one.

(function () {
  const STORAGE_KEY = "student-agent-theme";
  const root = document.documentElement;

  function savedTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null; // storage can be blocked, e.g. in a private window
    }
  }

  function preferredTheme() {
    const saved = savedTheme();
    if (saved === "light" || saved === "dark") return saved;
    return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function labelToggles() {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.textContent = next === "light" ? "Light mode" : "Dark mode";
    });
  }

  root.dataset.theme = preferredTheme();

  document.addEventListener("DOMContentLoaded", () => {
    labelToggles();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
        try {
          localStorage.setItem(STORAGE_KEY, root.dataset.theme);
        } catch {
          // The theme still applies to this page; it just won't be remembered.
        }
        labelToggles();
      });
    });
  });
})();
