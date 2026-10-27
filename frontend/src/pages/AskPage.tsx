import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PipelineProgress } from "../components/PipelineProgress";
import { QuestionBox } from "../components/QuestionBox";
import { ResultCard } from "../components/ResultCard";
import { ErrorNote, PageHeader } from "../components/ui";
import { useMetadata, useSuggestions } from "../hooks/queries";
import { useAskSession } from "../hooks/useAskSession";

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
        title="Ask a question"
        subtitle={
          coverage
            ? `Brazilian orders from ${coverage.min_date} to ${coverage.max_date}. Money in Brazilian Real (R$).`
            : "Questions are answered from the Olist semantic layer."
        }
        actions={entries.length > 0 && <button type="button" className="btn-ghost" onClick={clear}>Clear answers</button>}
      />

      <QuestionBox metadata={metadata.data} disabled={busy} value={question} onChange={setQuestion} onSubmit={run} />

      {suggestions.data && entries.length === 0 && (
        <section className="mt-6">
          <h2 className="label">Try one of these</h2>
          <div className="flex flex-wrap gap-2">
            {suggestions.data.map((s) => (
              <button key={s.question} type="button" disabled={busy} onClick={() => run(s.question)}
                      className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-ink-2 hover:border-accent hover:text-ink"
                      title={s.category}>
                {s.question}
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="mt-6 space-y-5">
        {entries.map((e) =>
          e.pending ? (
            <div key={e.id} className="card space-y-3 p-5">
              <p className="text-sm font-medium text-ink-2">{e.question}</p>
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
