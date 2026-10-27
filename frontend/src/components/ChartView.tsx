/**
 * Renders a result as KPI tiles, line, bar, donut or table.
 *
 * Rules (dataviz method): one y-axis per chart (several measures -> small multiples),
 * categorical colours in fixed slot order and tied to the entity (not its rank),
 * 2px lines, rounded bar ends, recessive grid, hover tooltips, legend for >= 2 series.
 */
import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartType, ColumnInfo, Row } from "../types/api";
import { formatPeriod, formatTick, formatValue } from "../utils/format";
import { DataTable } from "./DataTable";

export const SERIES = Array.from({ length: 8 }, (_, i) => `var(--series-${i + 1})`);
const AXIS = { stroke: "var(--axis)", tick: { fill: "var(--text-muted)", fontSize: 12 } };

interface Props {
  type: ChartType;
  columns: ColumnInfo[];
  rows: Row[];
  x?: string | null;
  y?: string[];
  series?: string | null;
  height?: number;
  compact?: boolean;
  /** "YYYY-MM" months with incomplete data (from data coverage). */
  incompleteMonths?: Set<string>;
}

function labelOf(value: unknown, col: ColumnInfo | undefined): string {
  if (!col) return String(value ?? "");
  if (col.dimension_type === "time") return formatPeriod(value, col.grain);
  if (col.name === "rating" && value !== null) return `${value}★`;
  return value === null || value === undefined ? "(none)" : String(value);
}

/** Tooltip: the value leads (strong), the label follows; text stays in ink colours. */
interface TooltipEntry {
  dataKey?: unknown;
  name?: unknown;
  value?: unknown;
  color?: string;
  payload?: { fill?: string };
}

function ChartTooltip({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean;
  payload?: readonly TooltipEntry[];
  label?: unknown;
  format: (n: unknown, key: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      {label !== undefined && <div className="mb-1 text-ink-2">{String(label)}</div>}
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: p.color ?? p.payload?.fill }} />
          <span className="font-semibold tabular-nums text-ink">{format(p.value, String(p.dataKey))}</span>
          <span className="text-ink-2">{String(p.name ?? "")}</span>
        </div>
      ))}
    </div>
  );
}

function Kpis({ columns, rows, y }: { columns: ColumnInfo[]; rows: Row[]; y: string[] }) {
  const row = rows[0] ?? {};
  const measures = columns.filter((c) => y.includes(c.name));
  const dim = columns.find((c) => c.role === "dimension");
  return (
    <div className={`grid gap-3 ${measures.length > 1 ? "sm:grid-cols-2 lg:grid-cols-3" : ""}`}>
      {measures.map((m) => (
        <div key={m.name} className="rounded-lg border border-line bg-surface-2 p-4">
          <div className="text-sm text-ink-2">
            {m.label}
            {dim ? ` · ${labelOf(row[dim.name], dim)}` : ""}
          </div>
          <div className="mt-1 text-3xl font-semibold tabular-nums tracking-tight" title={formatValue(row[m.name], m.format)}>
            {formatValue(row[m.name], m.format, { compact: true })}
          </div>
          {m.format === "currency" && typeof row[m.name] === "number" && Math.abs(row[m.name] as number) >= 1e4 && (
            <div className="mt-0.5 text-xs text-muted tabular-nums">{formatValue(row[m.name], m.format)}</div>
          )}
        </div>
      ))}
    </div>
  );
}

function Legend({ items }: { items: { label: string; color: string; extra?: string }[] }) {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: i.color }} aria-hidden="true" />
          <span>{i.label}</span>
          {i.extra && <span className="tabular-nums text-muted">{i.extra}</span>}
        </li>
      ))}
    </ul>
  );
}

function SingleLine({ data, xKey, measure, height, incomplete }: {
  data: Row[]; xKey: string; measure: ColumnInfo; height: number; incomplete: boolean[];
}) {
  // Incomplete periods (little or no data) are drawn dashed with hollow markers so a
  // collection gap never reads as a real drop.
  const anyIncomplete = incomplete.some(Boolean);
  const plotted = data.map((d, i) => {
    const v = d[measure.name];
    const near = incomplete[i] || incomplete[i - 1] || incomplete[i + 1];
    return { ...d, __solid: incomplete[i] ? null : v, __dash: near ? v : null, __inc: incomplete[i] };
  });
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={plotted} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={xKey} {...AXIS} tickLine={false} minTickGap={24} />
          <YAxis {...AXIS} tickLine={false} axisLine={false} width={72}
                 tickFormatter={(v) => formatTick(v, measure.format)} />
          <Tooltip
            cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
            content={({ active, payload, label }) => {
              const row = payload?.[0]?.payload as (Row & { __inc?: boolean }) | undefined;
              if (!active || !row) return null;
              return (
                <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
                  <div className="mb-1 text-ink-2">{String(label)}</div>
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[0] }} />
                    <span className="font-semibold tabular-nums text-ink">
                      {formatValue(row[measure.name], measure.format)}
                    </span>
                    <span className="text-ink-2">{measure.label}</span>
                  </div>
                  {row.__inc && <div className="mt-1 text-warn-ink">Incomplete month: little or no data</div>}
                </div>
              );
            }}
          />
          <Line type="monotone" dataKey="__solid" name={measure.label} stroke={SERIES[0]} strokeWidth={2}
                connectNulls={false}
                dot={data.length <= 24 ? { r: 3, strokeWidth: 0, fill: SERIES[0] } : false}
                activeDot={{ r: 5, stroke: "var(--surface-1)", strokeWidth: 2 }} isAnimationActive={false} />
          {anyIncomplete && (
            <Line type="monotone" dataKey="__dash" name={`${measure.label} (incomplete)`} stroke={SERIES[0]}
                  strokeWidth={2} strokeDasharray="4 4" strokeOpacity={0.6} connectNulls={false}
                  isAnimationActive={false} activeDot={false} legendType="none"
                  dot={(props: { cx?: number; cy?: number; index?: number }) =>
                    props.index !== undefined && incomplete[props.index] && props.cx && props.cy ? (
                      <circle key={props.index} cx={props.cx} cy={props.cy} r={4} fill="var(--surface-1)"
                              stroke={SERIES[0]} strokeWidth={1.5} />
                    ) : (
                      <g key={props.index} />
                    )} />
          )}
        </LineChart>
      </ResponsiveContainer>
      {anyIncomplete && (
        <p className="mt-1 flex items-center gap-2 text-xs text-ink-2">
          <svg width="24" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="24" y2="4" stroke="var(--series-1)" strokeWidth="2" strokeDasharray="4 4" />
          </svg>
          Dashed: incomplete months (data collection starting or stopping), not real drops
        </p>
      )}
    </div>
  );
}

function SingleBar({ data, xKey, measure, height, compact }: {
  data: Row[]; xKey: string; measure: ColumnInfo; height: number; compact?: boolean;
}) {
  const barHeight = Math.max(height, data.length * 30 + 24);
  return (
    <ResponsiveContainer width="100%" height={compact ? height : barHeight}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 64, bottom: 4, left: 4 }} barCategoryGap={4}>
        <CartesianGrid horizontal={false} stroke="var(--grid)" />
        <XAxis type="number" {...AXIS} tickLine={false} axisLine={false}
               tickFormatter={(v) => formatTick(v, measure.format)} />
        <YAxis type="category" dataKey={xKey} {...AXIS} tickLine={false} width={150} interval={0}
               tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 21)}…` : v)} />
        <Tooltip cursor={{ fill: "var(--surface-2)" }}
                 content={(p) => <ChartTooltip {...p} format={(v) => formatValue(v, measure.format)} />} />
        <Bar dataKey={measure.name} name={measure.label} fill={SERIES[0]} radius={[0, 4, 4, 0]}
             isAnimationActive={false} maxBarSize={26}>
          {data.length <= 12 && !compact && (
            <LabelList dataKey={measure.name} position="right" className="tabular-nums"
                       style={{ fill: "var(--text-secondary)", fontSize: 12 }}
                       formatter={(v: unknown) => formatValue(v, measure.format, { compact: true })} />
          )}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function ChartView({
  type, columns, rows, x, y = [], series, height = 300, compact = false, incompleteMonths,
}: Props) {
  const xCol = columns.find((c) => c.name === x) ?? columns.find((c) => c.role === "dimension");
  const measures = columns.filter((c) => (y.length ? y.includes(c.name) : c.role === "measure"));
  const xKey = "__x";

  const data = useMemo<Row[]>(
    () => rows.map((r) => ({ ...r, [xKey]: labelOf(xCol ? r[xCol.name] : "", xCol) })),
    [rows, xCol],
  );

  const incomplete = useMemo(
    () =>
      rows.map((r) =>
        Boolean(
          incompleteMonths &&
            xCol?.dimension_type === "time" &&
            ["month", "week", "day"].includes(xCol.grain ?? "") &&
            incompleteMonths.has(String(r[xCol.name]).slice(0, 7)),
        ),
      ),
    [rows, xCol, incompleteMonths],
  );

  if (type === "table" || !rows.length || !measures.length) {
    return <DataTable columns={columns} rows={rows} maxHeight={compact ? height : 420} />;
  }
  if (type === "kpi") return <Kpis columns={columns} rows={rows} y={measures.map((m) => m.name)} />;

  if (type === "line" && series) {
    // one line per series value; colour follows the series value (sorted), not its rank
    const m = measures[0];
    const sCol = columns.find((c) => c.name === series);
    const names = [...new Set(rows.map((r) => labelOf(r[series], sCol)))].sort().slice(0, 8);
    const pivot = new Map<string, Record<string, unknown>>();
    for (const r of rows) {
      const key = labelOf(xCol ? r[xCol.name] : "", xCol);
      const entry = pivot.get(key) ?? { [xKey]: key };
      entry[labelOf(r[series], sCol)] = r[m.name];
      pivot.set(key, entry);
    }
    const wide = [...pivot.values()];
    return (
      <div>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={wide} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey={xKey} {...AXIS} tickLine={false} minTickGap={24} />
            <YAxis {...AXIS} tickLine={false} axisLine={false} width={72}
                   tickFormatter={(v) => formatTick(v, m.format)} />
            <Tooltip cursor={{ stroke: "var(--axis)" }}
                     content={(p) => <ChartTooltip {...p} format={(v) => formatValue(v, m.format)} />} />
            {names.map((n, i) => (
              <Line key={n} dataKey={n} name={n} stroke={SERIES[i]} strokeWidth={2} dot={false}
                    activeDot={{ r: 4, stroke: "var(--surface-1)", strokeWidth: 2 }} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
        <Legend items={names.map((n, i) => ({ label: n, color: SERIES[i] }))} />
      </div>
    );
  }

  if (type === "pie") {
    const m = measures[0];
    const total = rows.reduce((s, r) => s + (Number(r[m.name]) || 0), 0);
    const slices = data.map((d, i) => ({
      name: String(d[xKey]),
      value: Number(d[m.name]) || 0,
      color: SERIES[i % 8],
    }));
    return (
      <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            <Pie data={slices} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="88%"
                 stroke="var(--surface-1)" strokeWidth={2} isAnimationActive={false}>
              {slices.map((s) => <Cell key={s.name} fill={s.color} />)}
            </Pie>
            <Tooltip content={(p) => (
              <ChartTooltip {...p} format={(v) => `${formatValue(v, m.format)} (${total ? ((Number(v) / total) * 100).toFixed(1) : 0}%)`} />
            )} />
          </PieChart>
        </ResponsiveContainer>
        <ul className="space-y-1.5 text-sm">
          {slices.map((s) => (
            <li key={s.name} className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
              <span className="min-w-24 text-ink-2">{s.name}</span>
              <span className="font-semibold tabular-nums">
                {total ? ((s.value / total) * 100).toFixed(1) : "0"}%
              </span>
              <span className="text-xs tabular-nums text-muted">{formatValue(s.value, m.format, { compact: true })}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // line or bar: one chart per measure (small multiples) so no chart has two scales
  const multiple = measures.length > 1;
  return (
    <div className={multiple ? "grid gap-6 lg:grid-cols-2" : ""}>
      {measures.map((m) => (
        <figure key={m.name}>
          {multiple && <figcaption className="mb-1 text-sm font-medium text-ink-2">{m.label}</figcaption>}
          {type === "line" ? (
            <SingleLine data={data} xKey={xKey} measure={m} incomplete={incomplete}
                        height={multiple ? Math.min(height, 240) : height} />
          ) : (
            <SingleBar data={data} xKey={xKey} measure={m} height={height} compact={compact} />
          )}
        </figure>
      ))}
    </div>
  );
}
