import { render, screen } from "@testing-library/react";
import { ChartView } from "./ChartView";
import type { ColumnInfo } from "../types/api";

const cols: ColumnInfo[] = [
  { name: "payment_type", label: "Payment Type", role: "dimension", format: null, dimension_type: "categorical", grain: null },
  { name: "payment_amount", label: "Payment Amount", role: "measure", format: "currency", dimension_type: null, grain: null },
];
const rows = [
  { payment_type: "Credit Card", payment_amount: 750 },
  { payment_type: "Boleto", payment_amount: 250 },
];

it("donut legend shows each slice share", () => {
  render(<ChartView type="pie" columns={cols} rows={rows} x="payment_type" y={["payment_amount"]} />);
  expect(screen.getByText("75.0%")).toBeInTheDocument();
  expect(screen.getByText("25.0%")).toBeInTheDocument();
});

it("table view is formatted", () => {
  render(<ChartView type="table" columns={cols} rows={rows} />);
  expect(screen.getByRole("table")).toHaveTextContent("R$ 750.00");
});

it("KPI tiles abbreviate large money and show the exact value", () => {
  render(
    <ChartView type="kpi" columns={[cols[1]]} rows={[{ payment_amount: 16008872.12 }]} y={["payment_amount"]} />,
  );
  expect(screen.getByText("R$ 16.0M")).toBeInTheDocument();
  expect(screen.getByText("R$ 16,008,872.12")).toBeInTheDocument();
});
