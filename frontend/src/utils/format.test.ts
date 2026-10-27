import { abbreviate, formatCell, formatPeriod, formatTick, formatValue } from "./format";

describe("formatValue", () => {
  it("formats Brazilian Real consistently", () => {
    expect(formatValue(1234.5, "currency")).toBe("R$ 1,234.50");
    expect(formatValue(16008872.12, "currency", { compact: true })).toBe("R$ 16.0M");
    expect(formatValue(950, "currency", { compact: true })).toBe("R$ 950.00");
  });

  it("formats the other measure types", () => {
    expect(formatValue(99441, "integer")).toBe("99,441");
    expect(formatValue(6.7712, "percent")).toBe("6.77%");
    expect(formatValue(12.56, "days")).toBe("12.6 days");
    expect(formatValue(4.0866, "rating")).toBe("4.09 / 5");
    expect(formatValue(null, "currency")).toBe("—");
    expect(formatValue("Toys", null)).toBe("Toys");
  });

  it("abbreviates large numbers", () => {
    expect(abbreviate(96096)).toBe("96.1K");
    expect(abbreviate(2_500_000_000)).toBe("2.5B");
    expect(formatTick(1_500_000, "currency")).toBe("R$ 1.5M");
    expect(formatTick(25, "percent")).toBe("25%");
  });
});

describe("formatPeriod", () => {
  it("labels time grains", () => {
    expect(formatPeriod("2018-03-01", "month")).toBe("Mar 2018");
    expect(formatPeriod("2017-04-01", "quarter")).toBe("Q2 2017");
    expect(formatPeriod(2017, "year")).toBe("2017");
    expect(formatPeriod("2018-01-08", "week")).toBe("08 Jan 2018");
  });

  it("formats cells by column role", () => {
    expect(
      formatCell("2018-03-01", {
        name: "order_date", label: "Order Month", role: "dimension", format: null, dimension_type: "time", grain: "month",
      }),
    ).toBe("Mar 2018");
    expect(
      formatCell(10.5, { name: "s", label: "S", role: "measure", format: "currency", dimension_type: null, grain: null }),
    ).toBe("R$ 10.50");
  });
});
