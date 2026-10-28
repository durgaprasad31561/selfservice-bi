import type { ReactNode } from "react";

/** Midnight background with slowly drifting colour light, a fading grid and fine grain. */
export function Aurora({
  children,
  className = "",
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div";
}) {
  return (
    <Tag className={`aurora ${className}`}>
      <span className="aurora-blob b1" aria-hidden="true" />
      <span className="aurora-blob b2" aria-hidden="true" />
      <span className="aurora-blob b3" aria-hidden="true" />
      <span className="aurora-grid" aria-hidden="true" />
      <span className="aurora-noise" aria-hidden="true" />
      {children}
    </Tag>
  );
}
