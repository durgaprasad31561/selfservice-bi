import { useMemo, useState } from "react";
import type { ColumnInfo, Row } from "../types/api";
import { formatCell } from "../utils/format";

interface Props {
  columns: ColumnInfo[];
  rows: Row[];
  maxHeight?: number;
}

/** Sortable table; numbers right-aligned with tabular figures. */
export function DataTable({ columns, rows, maxHeight = 420 }: Props) {
  const [sort, setSort] = useState<{ col: string; dir: 1 | -1 } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((a, b) => {
      const x = a[sort.col];
      const y = b[sort.col];
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x > y ? 1 : -1) * sort.dir;
    });
  }, [rows, sort]);

  const toggle = (col: string) =>
    setSort((s) => (s?.col === col ? (s.dir === -1 ? { col, dir: 1 } : null) : { col, dir: -1 }));

  const isNumeric = (c: ColumnInfo) =>
    c.role === "measure" || rows.some((r) => typeof r[c.name] === "number");

  return (
    <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-surface-2">
          <tr>
            {columns.map((c) => {
              const active = sort?.col === c.name;
              return (
                <th
                  key={c.name}
                  scope="col"
                  aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                  className={`whitespace-nowrap px-3 py-2 font-medium text-ink-2 ${isNumeric(c) ? "text-right" : "text-left"}`}
                >
                  <button
                    type="button"
                    onClick={() => toggle(c.name)}
                    className="inline-flex items-center gap-1 hover:text-ink"
                  >
                    {c.label}
                    <span className="text-muted" aria-hidden="true">
                      {active ? (sort.dir === 1 ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={i} className="border-t border-line hover:bg-surface-2">
              {columns.map((c) => (
                <td
                  key={c.name}
                  className={`whitespace-nowrap px-3 py-1.5 ${isNumeric(c) ? "text-right tabular-nums" : ""}`}
                >
                  {formatCell(r[c.name], c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
