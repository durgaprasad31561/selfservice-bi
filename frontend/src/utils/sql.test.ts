import { tokenizeSql } from "./sql";

it("tokenizes keywords, functions, strings and numbers without losing text", () => {
  const sql = "SELECT SUM(price) FROM t WHERE s = 'it''s' LIMIT 10";
  const tokens = tokenizeSql(sql);
  const kinds = Object.fromEntries(tokens.filter((t) => t.text.trim()).map((t) => [t.text, t.kind]));
  expect(kinds.SELECT).toBe("keyword");
  expect(kinds.SUM).toBe("function");
  expect(kinds["'it''s'"]).toBe("string");
  expect(kinds["10"]).toBe("number");
  expect(tokens.map((t) => t.text).join("")).toBe(sql);
});
