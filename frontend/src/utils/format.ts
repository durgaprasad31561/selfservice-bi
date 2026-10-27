/** Number and date formatting. Money is Brazilian Real, always shown as "R$ 1,234.56". */
import type { ColumnInfo, ValueFormat } from "../types/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const nf = (digits: number) =>
  new Intl.NumberFormat("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Compact form: 16008872 -> "16.0M", 12500 -> "12.5K". */
export function abbreviate(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${nf(1).format(value / 1e9)}B`;
  if (abs >= 1e6) return `${nf(1).format(value / 1e6)}M`;
  if (abs >= 1e4) return `${nf(1).format(value / 1e3)}K`;
  return nf(abs < 10 && !Number.isInteger(value) ? 2 : 0).format(value);
}

export function formatValue(
  value: unknown,
  format: ValueFormat | null | undefined,
  options: { compact?: boolean } = {},
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value !== "number") return String(value);
  const { compact = false } = options;
  switch (format) {
    case "currency":
      return compact && Math.abs(value) >= 1e4 ? `R$ ${abbreviate(value)}` : `R$ ${nf(2).format(value)}`;
    case "integer":
      return compact && Math.abs(value) >= 1e4 ? abbreviate(value) : nf(0).format(Math.round(value));
    case "percent":
      return `${nf(compact ? 1 : 2).format(value)}%`;
    case "days":
      return `${nf(1).format(value)} days`;
    case "rating":
      return `${nf(2).format(value)} / 5`;
    case "decimal":
      return nf(2).format(value);
    default:
      if (compact) return abbreviate(value);
      return Number.isInteger(value) ? nf(0).format(value) : nf(2).format(value);
  }
}

/** Axis tick label (always compact, no unit words). */
export function formatTick(value: unknown, format: ValueFormat | null | undefined): string {
  if (typeof value !== "number") return String(value ?? "");
  if (format === "currency") return `R$ ${abbreviate(value)}`;
  if (format === "percent") return `${nf(0).format(value)}%`;
  if (format === "rating" || format === "decimal" || format === "days") return nf(1).format(value);
  return abbreviate(value);
}

/** Label for a time value at a grain: month -> "Mar 2018", quarter -> "Q2 2017". */
export function formatPeriod(value: unknown, grain: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return String(value);
  const text = String(value);
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(text);
  if (!m) return text;
  const [, y, mo, d] = m;
  const month = MONTHS[Number(mo) - 1];
  switch (grain) {
    case "year":
      return y;
    case "quarter":
      return `Q${Math.floor((Number(mo) - 1) / 3) + 1} ${y}`;
    case "month":
      return `${month} ${y}`;
    case "week":
      return `${d} ${month} ${y}`;
    default:
      return d ? `${d} ${month} ${y}` : `${month} ${y}`;
  }
}

/** Display text for any cell given its column. */
export function formatCell(value: unknown, column: ColumnInfo): string {
  if (column.dimension_type === "time") return formatPeriod(value, column.grain);
  if (column.role === "measure") return formatValue(value, column.format);
  if (typeof value === "number") return formatValue(value, null);
  return value === null || value === undefined ? "—" : String(value);
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
