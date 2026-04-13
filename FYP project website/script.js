const header = document.querySelector("[data-header]");
const menuToggle = document.querySelector("[data-menu-toggle]");
const nav = document.querySelector("[data-nav]");
const cursorGlow = document.querySelector(".cursor-glow");
const heroImage = document.querySelector(".hero-media img");
const revealItems = document.querySelectorAll(".reveal");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let pointerX = 0;
let pointerY = 0;
let glowX = 0;
let glowY = 0;

function updateHeader() {
  header.classList.toggle("is-scrolled", window.scrollY > 20);
}

function closeMenu() {
  document.body.classList.remove("menu-open");
  menuToggle.setAttribute("aria-expanded", "false");
  menuToggle.setAttribute("aria-label", "Open navigation");
}

menuToggle.addEventListener("click", () => {
  const isOpen = document.body.classList.toggle("menu-open");
  menuToggle.setAttribute("aria-expanded", String(isOpen));
  menuToggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
});

nav.addEventListener("click", (event) => {
  if (event.target.matches("a")) {
    closeMenu();
  }
});

window.addEventListener("scroll", updateHeader, { passive: true });
updateHeader();

function moveGlow() {
  glowX += (pointerX - glowX) * 0.12;
  glowY += (pointerY - glowY) * 0.12;

  if (cursorGlow) {
    cursorGlow.style.transform = `translate3d(${glowX - 170}px, ${glowY - 170}px, 0)`;
  }

  requestAnimationFrame(moveGlow);
}

window.addEventListener(
  "pointermove",
  (event) => {
    if (reduceMotion.matches) {
      return;
    }

    pointerX = event.clientX;
    pointerY = event.clientY;
    document.body.classList.add("has-pointer");

    if (heroImage && window.matchMedia("(min-width: 761px)").matches) {
      const moveX = (event.clientX / window.innerWidth - 0.5) * 12;
      const moveY = (event.clientY / window.innerHeight - 0.5) * 12;
      heroImage.style.transform = `scale(1.07) translate(${moveX}px, ${moveY}px)`;
    }
  },
  { passive: true }
);

window.addEventListener("pointerleave", () => {
  document.body.classList.remove("has-pointer");
});

if (!reduceMotion.matches) {
  moveGlow();
}

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.18 }
  );

  revealItems.forEach((item) => observer.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add("is-visible"));
}
