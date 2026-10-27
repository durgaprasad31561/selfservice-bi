import { buildVocabulary, completions, normalizeText } from "./QuestionBox";
import type { Metadata } from "../types/api";

const meta = {
  measures: [
    {
      name: "total_sales",
      label: "Total Sales",
      synonyms: ["revenue"],
      description: "",
      type: "sum",
      format: "currency",
      valid_dimensions: [],
      default_filters: [],
    },
  ],
  dimensions: [
    {
      name: "product_category",
      label: "Product Category",
      type: "categorical",
      synonyms: [],
      grains: [],
      value_count: 2,
      description: "",
      values: ["Health & Beauty", "Housewares"],
    },
  ],
} as unknown as Metadata;

it("normalizes accents and ampersands", () => {
  expect(normalizeText("São Paulo & Co")).toBe("sao paulo and co");
});

it("completes the words being typed from the semantic layer", () => {
  const vocab = buildVocabulary(meta);
  expect(completions("top categories in heal", vocab).map((c) => c.term.text)).toEqual([
    "Health & Beauty",
  ]);
  expect(completions("show reve", vocab)[0].term.text).toBe("revenue");
  expect(completions("show ", vocab)).toEqual([]);
  const multi = completions("sales for health and", vocab);
  expect(multi[0].term.text).toBe("Health & Beauty");
  expect(multi[0].replaceFrom).toBe("sales for ".length);
});
