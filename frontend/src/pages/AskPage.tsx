import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PipelineProgress } from "../components/PipelineProgress";
import { QuestionBox } from "../components/QuestionBox";
import { ResultCard } from "../components/ResultCard";
import { ErrorNote, PageHeader } from "../components/ui";
import { useMetadata, useSuggestions } from "../hooks/queries";
import { useAskSession } from "../hooks/useAskSession";
import type { Suggestion } from "../types/api";
import { IconSparkles } from "../components/Icons";

function groupSuggestions(list: Suggestion[]): [string, Suggestion[]][] {
  const groups = new Map<string, Suggestion[]>();
  for (const s of list) groups.set(s.category, [...(groups.get(s.category) ?? []), s]);
  return [...groups.entries()];
}

export function AskPage() {
  const metadata = useMetadata();
  const suggestions = useSuggestions();
  const { entries, busy, ask, clear } = useAskSession();
  const [question, setQuestion] = useState("");
  const [params, setParams] = useSearchParams();
  const handledQuery = useRef(false);

  const run = (q: string) => {
    setQuestion("");
    void ask(q);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // /ask?q=... (from History or the Data Catalog) asks immediately
  useEffect(() => {
    const q = params.get("q");
    if (q && !handledQuery.current) {
      handledQuery.current = true;
      setParams({}, { replace: true });
      run(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const coverage = metadata.data?.coverage;
  return (
    <div>
      <PageHeader
        eyebrow="Natural-language analytics"
        icon={<IconSparkles size={22} />}
        title="Ask a question"
        subtitle={
          coverage
            ? `Brazilian orders from ${coverage.min_date} to ${coverage.max_date}. Money in Brazilian Real (R$).`
            : "Questions are answered from the Olist semantic layer."
        }
        actions={
          entries.length > 0 && (
            <button type="button" className="btn-ghost" onClick={clear}>
              Clear answers
            </button>
          )
        }
      />

      <QuestionBox
        metadata={metadata.data}
        disabled={busy}
        value={question}
        onChange={setQuestion}
        onSubmit={run}
      />

      {suggestions.data && entries.length === 0 && (
        <section className="mt-8 animate-fade-up" aria-label="Suggested questions">
          <div className="mb-4 flex items-center gap-2">
            <span className="icon-tile h-7 w-7">
              <IconSparkles size={15} />
            </span>
            <h2 className="text-sm font-semibold">Try one of these</h2>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {groupSuggestions(suggestions.data).map(([category, items]) => (
              <div key={category} className="card p-4">
                <p className="label">{category}</p>
                <div className="flex flex-wrap gap-2">
                  {items.map((s) => (
                    <button
                      key={s.question}
                      type="button"
                      disabled={busy}
                      onClick={() => run(s.question)}
                      className="chip text-left"
                    >
                      {s.question}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="mt-6 space-y-5">
        {entries.map((e) =>
          e.pending ? (
            <div key={e.id} className="card space-y-4 p-5 animate-fade-up">
              <div className="flex items-center gap-3">
                <span className="icon-tile h-9 w-9">
                  <IconSparkles size={18} />
                </span>
                <div>
                  <p className="text-xs text-muted">Working on</p>
                  <p className="font-medium">{e.question}</p>
                </div>
              </div>
              <PipelineProgress />
            </div>
          ) : e.response ? (
            <ResultCard key={e.id} response={e.response} onAsk={run} />
          ) : (
            <ErrorNote key={e.id} message={`“${e.question}”: ${e.error}`} />
          ),
        )}
      </div>
    </div>
  );
}
