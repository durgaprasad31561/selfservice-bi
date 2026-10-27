## Run history and changes

**Run 1 (27 Oct 2026, Groq `openai/gpt-oss-120b`)**: 82/85 passed. Execution accuracy
96.2%, correct refusals 100%, 0 wrong answers, 0 unsafe SQL. Failures:

| ID | Question | What happened | Fix |
|---|---|---|---|
| F08 | Product sales of electronics in 2018 | Asked which category was meant | The compact prompt listed only 25 of 74 category names; all 74 are listed again |
| F09 | How many items were sold in the toys category? | Same as F08 | Same as F08, plus a rule: never ask which filter value was meant - copy it and let the value matcher resolve it |
| W09 | Show me performance by state | Answered with Total Sales by state (assumption stated) instead of asking which measure | Rule: vague success words ("performance", "best", "doing well") need clarification with measure options |

No question text was added to the few-shot examples for these fixes (to avoid tuning to the
test set); the changes are general prompt rules and catalog completeness.

## Method notes

- Reference values are computed with hand-written SQL on `analytics.*`, not with the
  semantic compiler, so a wrong business definition in `model.yaml` would show up as a
  wrong answer.
- "Unsafe SQL executed" re-validates every SQL statement that produced an answer with the
  same validator used at run time; the database role (`bi_reader`, read-only, SELECT on
  `analytics` only) is a second, independent barrier.
- Latency includes waiting for the LLM provider's free-tier rate limit (8k tokens/minute
  per model), which dominates the p95; a single uncontended question takes ~2-4 s.
- Many must-refuse questions are refused before any LLM call (question guard and
  unsupported-concept check), so they cost nothing and take < 5 ms.
