import { useEffect, useRef, useState } from "react";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Animate a number from 0 to `target` (ease-out). Returns the current value.
 * Non-numbers are returned unchanged; reduced-motion users see the final value at once.
 */
export function useCountUp<T>(target: T, duration = 1100, delay = 0): T {
  const [value, setValue] = useState<T>(() =>
    typeof target === "number" && !prefersReducedMotion() ? (0 as T) : target,
  );
  const frame = useRef<number>();

  useEffect(() => {
    if (typeof target !== "number" || prefersReducedMotion()) {
      setValue(target);
      return;
    }
    let start: number | null = null;
    const step = (now: number) => {
      if (start === null) start = now + delay;
      const t = Math.min(1, Math.max(0, (now - start) / duration));
      const eased = 1 - Math.pow(1 - t, 3);
      setValue((target * eased) as T);
      if (t < 1) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [target, duration, delay]);

  return value;
}
