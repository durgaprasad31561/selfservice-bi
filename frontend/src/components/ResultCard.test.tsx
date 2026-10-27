import { fireEvent, render, screen } from "@testing-library/react";
import { ResultCard } from "./ResultCard";
import { Providers, makeResponse } from "../test/fixtures";

const REFUSAL = "I don't have sufficient data to answer that question.";

describe("ResultCard", () => {
  it("shows the answer, KPI and calculation details", () => {
    render(<Providers><ResultCard response={makeResponse()} /></Providers>);
    expect(screen.getByText("Total Sales in 2017 was R$ 7,142,672.43.")).toBeInTheDocument();
    expect(screen.getByText("R$ 7.1M")).toBeInTheDocument();
    expect(screen.getByText("High confidence")).toBeInTheDocument();
    fireEvent.click(screen.getByText("How this was calculated"));
    expect(screen.getByText("Total Sales: Excludes canceled and unavailable orders.")).toBeInTheDocument();
    expect(screen.getByText("Show SQL")).toBeInTheDocument();
  });

  it("shows warnings in a banner", () => {
    const r = makeResponse({
      status: "answered_with_warning",
      warnings: ["Data is incomplete for Oct 2018 (4 orders)."],
    });
    render(<Providers><ResultCard response={r} /></Providers>);
    expect(screen.getByText("Answered with warning")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Data is incomplete for Oct 2018");
  });

  it("shows refusals with the standard sentence, reason and clickable suggestions", () => {
    const onAsk = vi.fn();
    const r = makeResponse({
      status: "refused",
      answer_text: REFUSAL,
      reason: "The dataset has no cost data.",
      suggestions: ["Total sales in 2017"],
      data: [],
      chart: null,
    });
    render(<Providers><ResultCard response={r} onAsk={onAsk} /></Providers>);
    expect(screen.getByText(REFUSAL)).toBeInTheDocument();
    expect(screen.getByText("The dataset has no cost data.")).toBeInTheDocument();
    expect(screen.queryByText("Export CSV")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Total sales in 2017" }));
    expect(onAsk).toHaveBeenCalledWith("Total sales in 2017");
  });

  it("offers clarification options", () => {
    const onAsk = vi.fn();
    const r = makeResponse({
      status: "clarify",
      answer_text: "Money or units?",
      data: [],
      chart: null,
      sql: null,
      clarification: {
        question: "Money or units?",
        options: ["Top categories by product sales", "Top categories by items sold"],
      },
    });
    render(<Providers><ResultCard response={r} onAsk={onAsk} /></Providers>);
    fireEvent.click(screen.getByRole("button", { name: "Top categories by items sold" }));
    expect(onAsk).toHaveBeenCalledWith("Top categories by items sold");
  });

  it("shows errors without data", () => {
    const r = makeResponse({
      status: "error",
      answer_text: "The AI model is temporarily unavailable.",
      data: [],
      chart: null,
      sql: null,
    });
    render(<Providers><ResultCard response={r} /></Providers>);
    expect(screen.getByRole("alert")).toHaveTextContent("temporarily unavailable");
  });

  it("toggles between chart and table", () => {
    const r = makeResponse({
      answer_text: "Health & Beauty had the highest Product Sales.",
      columns: [
        { name: "product_category", label: "Product Category", role: "dimension", format: null, dimension_type: "categorical", grain: null },
        { name: "product_sales", label: "Product Sales", role: "measure", format: "currency", dimension_type: null, grain: null },
      ],
      data: [
        { product_category: "Health & Beauty", product_sales: 1255695.13 },
        { product_category: "Toys", product_sales: 400000 },
      ],
      chart: { type: "bar", title: "Product Sales by Product Category", x: "product_category", y: ["product_sales"], series: null, reason: "" },
    });
    render(<Providers><ResultCard response={r} /></Providers>);
    fireEvent.click(screen.getByRole("button", { name: /Table/ }));
    expect(screen.getByRole("table")).toHaveTextContent("R$ 1,255,695.13");
  });
});
