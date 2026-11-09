// Adapts the home page to how this server is configured, and plays its intro.

async function initHome() {
  const status = await fetch("/api/demo").then((res) => res.json());
  const openApp = document.getElementById("open-app");
  const note = document.getElementById("hero-note");

  if (!status.demo) {
    openApp.textContent = "Open the app";
    note.classList.add("hidden");
    return;
  }

  const { available, email } = status.google;
  if (email) {
    openApp.textContent = "Open your workspace";
    note.textContent = `Signed in as ${email}.`;
  } else if (available) {
    document.getElementById("home-google").classList.remove("hidden");
    note.textContent = "The demo needs no account and uses sample data. Google sign-in is open to approved test accounts.";
  }
  document.getElementById("google-privacy").classList.toggle("hidden", !available);
}

initHome().catch(() => {
  // The page still works as a static introduction if this request fails.
});

// --- "What it does" carousel ---

function initCarousel() {
  const carousel = document.getElementById("features");
  const track = carousel.querySelector(".carousel-track");
  const cards = [...track.querySelectorAll(".carousel-card")];
  const controls = carousel.querySelector(".carousel-controls");
  const dotsContainer = carousel.querySelector(".carousel-dots");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let active = 0;

  const dots = cards.map((_, index) => {
    const dot = document.createElement("button");
    dot.type = "button";
    dot.className = "carousel-dot";
    dot.setAttribute("aria-label", `Show card ${index + 1}`);
    dot.addEventListener("click", () => goTo(index));
    dotsContainer.append(dot);
    return dot;
  });

  function showActive(index) {
    active = index;
    cards.forEach((card, i) => card.classList.toggle("is-active", i === index));
    dots.forEach((dot, i) => dot.setAttribute("aria-current", String(i === index)));
  }

  function goTo(index) {
    const card = cards[(index + cards.length) % cards.length];
    track.scrollTo({
      left: card.offsetLeft - (track.clientWidth - card.offsetWidth) / 2,
      behavior: reduceMotion ? "auto" : "smooth",
    });
  }

  function closestToCenter() {
    const center = track.scrollLeft + track.clientWidth / 2;
    const distances = cards.map((card) => Math.abs(card.offsetLeft + card.offsetWidth / 2 - center));
    return distances.indexOf(Math.min(...distances));
  }

  let frame = null;
  track.addEventListener("scroll", () => {
    if (frame !== null) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      showActive(closestToCenter());
    });
  }, { passive: true });

  controls.querySelectorAll(".carousel-arrow").forEach((arrow) => {
    arrow.addEventListener("click", () => goTo(active + Number(arrow.dataset.direction)));
  });
  cards.forEach((card, index) => {
    card.addEventListener("click", () => {
      if (index !== active) goTo(index);
    });
  });

  showActive(0);
  carousel.classList.add("is-ready");
  controls.classList.remove("hidden");
}

initCarousel();

// --- Intro animation ---

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Screen readers get the whole sentence at once. The visible copy is split into
// typed and not-yet-typed halves, so the text wraps in its final position.
function prepareTypewriter(el) {
  const text = el.textContent;
  el.textContent = "";

  const accessible = document.createElement("span");
  accessible.className = "visually-hidden";
  accessible.textContent = text;

  const visual = document.createElement("span");
  visual.setAttribute("aria-hidden", "true");
  const typed = document.createElement("span");
  const caret = document.createElement("span");
  caret.className = "type-caret";
  const rest = document.createElement("span");
  rest.className = "type-rest";
  rest.textContent = text;
  visual.append(typed, caret, rest);
  el.append(accessible, visual);

  // Pass msPerChar for a set speed, or totalMs to finish in a set time.
  return async function type({ msPerChar, totalMs }) {
    const weights = Array.from(text, (char) => 0.6 + Math.random() * 0.8 + (",.?".includes(char) ? 5 : 0));
    // The last character needs no wait after it, so it lands exactly on totalMs.
    const scale = totalMs ? totalMs / weights.slice(0, -1).reduce((sum, weight) => sum + weight, 0) : msPerChar;

    caret.classList.add("is-active");
    // Waits are measured from the start so browser timer delays don't add up.
    const start = performance.now();
    let elapsedTarget = 0;
    for (let i = 1; i <= text.length; i++) {
      typed.textContent = text.slice(0, i);
      rest.textContent = text.slice(i);
      if (i === text.length) break;
      elapsedTarget += weights[i - 1] * scale;
      await sleep(start + elapsedTarget - performance.now());
    }
    caret.classList.remove("is-active");
  };
}

async function playSampleChat() {
  const items = [...document.querySelectorAll(".sample-chat > p")].map((el) => {
    el.classList.add("intro-item", "is-waiting");
    return { el, type: el.classList.contains("bubble") ? prepareTypewriter(el) : null };
  });
  return async () => {
    for (const { el, type } of items) {
      el.classList.remove("is-waiting");
      if (type) {
        await type({ msPerChar: el.classList.contains("user") ? 30 : 13 });
        await sleep(350);
      } else {
        await sleep(650);
      }
    }
  };
}

function revealSectionsOnScroll() {
  const headings = new Map();
  document.querySelectorAll(".home-section h2").forEach((heading) => {
    headings.set(heading, prepareTypewriter(heading));
  });
  const reveals = document.querySelectorAll(".carousel, .home-grid article, .privacy-list");
  reveals.forEach((el) => el.classList.add("reveal", "is-waiting"));
  document.querySelectorAll(".home-grid").forEach((grid) => {
    [...grid.children].forEach((card, index) => {
      card.style.transitionDelay = `${index * 90}ms`;
    });
  });

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(({ target, isIntersecting }) => {
      if (!isIntersecting) return;
      observer.unobserve(target);
      if (headings.has(target)) headings.get(target)({ msPerChar: 38 });
      else target.classList.remove("is-waiting");
    });
  }, { threshold: 0.2 });
  [...headings.keys(), ...reveals].forEach((el) => observer.observe(el));
}

async function playIntro() {
  const typeHeading = prepareTypewriter(document.querySelector(".hero h1"));
  const typeCopy = prepareTypewriter(document.querySelector(".hero-copy"));
  const actions = [document.querySelector(".hero-actions"), document.getElementById("hero-note")];
  actions.forEach((el) => el.classList.add("intro-item", "is-waiting"));
  const playChat = await playSampleChat();
  revealSectionsOnScroll();

  const chatFinished = sleep(250).then(playChat);
  await typeHeading({ totalMs: 2000 });
  await typeCopy({ totalMs: 1600 });
  actions.forEach((el) => el.classList.remove("is-waiting"));
  await chatFinished;
}

if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
  playIntro();
}
