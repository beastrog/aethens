// Tiny motion helper (no dependencies). Sets html.motion-ok when motion is allowed, reveals
// [data-reveal] once on scroll, tracks visibility of [data-play] elements (off-screen or hidden
// tab = not visible) and exposes pointer position as --px/--py on [data-pointer] elements.

const reduce = matchMedia("(prefers-reduced-motion: reduce)");
const root = document.documentElement;

export const motionOk = (): boolean => !reduce.matches;

type Listener = (visible: boolean) => void;
const listeners = new Map<Element, Set<Listener>>();
const onScreen = new Map<Element, boolean>();

function emit(el: Element) {
  const v = !!onScreen.get(el) && !document.hidden;
  el.toggleAttribute("data-visible", v);
  listeners.get(el)?.forEach((fn) => fn(v));
}

const playIO = new IntersectionObserver((entries) => {
  for (const e of entries) {
    onScreen.set(e.target, e.isIntersecting);
    emit(e.target);
  }
});

/** Call fn(true/false) whenever el becomes visible / hidden (off-screen or background tab). */
export function onVisible(el: Element, fn: Listener) {
  if (!listeners.has(el)) {
    listeners.set(el, new Set());
    el.setAttribute("data-play", "");
    playIO.observe(el);
  }
  listeners.get(el)!.add(fn);
}

/** Call fn when reduced-motion preference flips on, so components can jump to final state. */
export function onReduce(fn: () => void) {
  reduce.addEventListener("change", () => reduce.matches && fn());
}

function init() {
  const sync = () => root.classList.toggle("motion-ok", !reduce.matches);
  sync();
  reduce.addEventListener("change", sync);
  document.addEventListener("visibilitychange", () => listeners.forEach((_, el) => emit(el)));

  const revealIO = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.setAttribute("data-in", "");
        revealIO.unobserve(e.target);
      }
    },
    { rootMargin: "0px 0px -12% 0px" },
  );
  document.querySelectorAll("[data-reveal]").forEach((el) => revealIO.observe(el));
  document.querySelectorAll("[data-play]").forEach((el) => onVisible(el, () => {}));

  if (matchMedia("(hover: hover) and (pointer: fine)").matches) {
    let raf = 0;
    let last: PointerEvent | null = null;
    document.addEventListener(
      "pointermove",
      (ev) => {
        last = ev;
        if (raf) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          const target = (last!.target as Element | null)?.closest?.("[data-pointer]") as HTMLElement | null;
          if (!target) return;
          const r = target.getBoundingClientRect();
          target.style.setProperty("--px", `${last!.clientX - r.left}px`);
          target.style.setProperty("--py", `${last!.clientY - r.top}px`);
        });
      },
      { passive: true },
    );
  }
}

let started = false;
export function startMotion() {
  if (started) return;
  started = true;
  init();
}
