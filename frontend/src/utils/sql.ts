/** Minimal SQL tokenizer for syntax highlighting (no external dependency). */

export type TokenKind = "keyword" | "function" | "string" | "number" | "comment" | "operator" | "text";

export interface Token {
  kind: TokenKind;
  text: string;
}

const KEYWORDS = new Set(
  (
    "select from where and or not in is null as group by order having limit offset with join left " +
    "right inner outer full cross on using union all distinct case when then else end between like " +
    "asc desc nulls last first filter over partition date interval true false exists"
  ).split(" "),
);

const PATTERN =
  /('(?:[^']|'')*')|(--[^\n]*)|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_][A-Za-z0-9_]*\b)(\s*\()?|(::|<=|>=|<>|!=|[=<>*+\-/%,().])|(\s+)|(.)/g;

export function tokenizeSql(sql: string): Token[] {
  const tokens: Token[] = [];
  for (const m of sql.matchAll(PATTERN)) {
    const [, str, comment, num, word, paren, op, space, other] = m;
    if (str) tokens.push({ kind: "string", text: str });
    else if (comment) tokens.push({ kind: "comment", text: comment });
    else if (num) tokens.push({ kind: "number", text: num });
    else if (word) {
      const lower = word.toLowerCase();
      if (KEYWORDS.has(lower)) tokens.push({ kind: "keyword", text: word });
      else if (paren) tokens.push({ kind: "function", text: word });
      else tokens.push({ kind: "text", text: word });
      if (paren) tokens.push({ kind: "operator", text: paren });
    } else if (op) tokens.push({ kind: "operator", text: op });
    else tokens.push({ kind: "text", text: space ?? other ?? "" });
  }
  return tokens;
}
