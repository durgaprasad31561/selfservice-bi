import type { ColumnInfo, Row } from "../types/api";

function escape(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** CSV with a header of column labels and raw (unformatted) values. */
export function toCsv(columns: ColumnInfo[], rows: Row[]): string {
  const header = columns.map((c) => escape(c.label)).join(",");
  const body = rows.map((r) => columns.map((c) => escape(r[c.name])).join(","));
  return [header, ...body].join("\r\n");
}

export function downloadCsv(filename: string, columns: ColumnInfo[], rows: Row[]): void {
  // BOM so Excel opens UTF-8 (São Paulo) correctly
  const blob = new Blob(["﻿" + toCsv(columns, rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function slugify(text: string): string {
  return (
    text
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60) || "result"
  );
}
