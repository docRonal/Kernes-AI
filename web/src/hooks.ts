import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

export function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    setWidth(Math.round(node.getBoundingClientRect().width));
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}

/** Rolls a money figure towards `target`. Whole złoty while moving, exact grosz at rest. */
export function useCountUp(target: number, { enabled = true, from = 0, duration = 900 } = {}): number {
  const reduce = useReducedMotion();
  const animate = enabled && !reduce;
  const [value, setValue] = useState(animate ? from : target);
  const current = useRef(animate ? from : target);

  useEffect(() => {
    if (!animate) {
      current.current = target;
      setValue(target);
      return;
    }
    const origin = current.current;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - progress) ** 3;
      const next = progress < 1 ? Math.round((origin + (target - origin) * eased) / 100) * 100 : target;
      current.current = next;
      setValue(next);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, animate, duration]);

  return value;
}
