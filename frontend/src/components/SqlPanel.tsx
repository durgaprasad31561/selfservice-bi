import { useState } from "react";
import { tokenizeSql } from "../utils/sql";
import type { TokenKind } from "../utils/sql";

const CLASS: Record<TokenKind, string> = {
  keyword: "text-accent font-semibold",
  function: "text-[color:var(--series-7)]",
  string: "text-[color:var(--series-6)]",
  number: "text-[color:var(--series-2)]",
  comment: "text-muted italic",
  operator: "text-ink-2",
  text: "text-ink",
};

export function SqlPanel({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div className="relative">
      <button
        type="button"
        onClick={copy}
        className="btn-ghost absolute right-2 top-2 px-2 py-1 text-xs"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre className="max-h-80 overflow-auto rounded-lg border border-line bg-surface-2 p-4 pr-16 font-mono text-[12.5px] leading-relaxed">
        <code>
          {tokenizeSql(sql).map((t, i) => (
            <span key={i} className={CLASS[t.kind]}>
              {t.text}
            </span>
          ))}
        </code>
      </pre>
      <p className="mt-2 text-xs text-muted">
        Read-only query, checked by the SQL validator and run on the read-only database role.
      </p>
    </div>
  );
}
