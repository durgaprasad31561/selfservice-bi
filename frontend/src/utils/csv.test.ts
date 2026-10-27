import { slugify, toCsv } from "./csv";
import type { ColumnInfo } from "../types/api";

const cols: ColumnInfo[] = [
  { name: "state", label: "Customer State", role: "dimension", format: null, dimension_type: "categorical", grain: null },
  { name: "sales", label: "Total Sales", role: "measure", format: "currency", dimension_type: null, grain: null },
];

it("writes labels as header and raw values, escaping commas and quotes", () => {
  const csv = toCsv(cols, [
    { state: "São Paulo", sales: 5878935.99 },
    { state: 'Bed, "Bath"', sales: null },
  ]);
  expect(csv.split("\r\n")).toEqual([
    "Customer State,Total Sales",
    "São Paulo,5878935.99",
    '"Bed, ""Bath""",',
  ]);
});

it("makes safe file names", () => {
  expect(slugify("Total sales in São Paulo, 2018!")).toBe("total-sales-in-sao-paulo-2018");
  expect(slugify("???")).toBe("result");
});
