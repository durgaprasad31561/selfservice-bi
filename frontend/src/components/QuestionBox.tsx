import { useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Metadata } from "../types/api";
import { IconSend } from "./Icons";

interface Term {
  text: string;
  kind: string; // Measure | Dimension | Value
  norm: string;
}

export function normalizeText(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Autocomplete vocabulary from the semantic layer: measures, dimensions and values. */
export function buildVocabulary(meta: Metadata | undefined): Term[] {
  if (!meta) return [];
  const seen = new Set<string>();
  const terms: Term[] = [];
  const add = (text: string, kind: string) => {
    const norm = normalizeText(text);
    if (!norm || seen.has(norm)) return;
    seen.add(norm);
    terms.push({ text, kind, norm });
  };
  meta.measures.forEach((m) => {
    add(m.label.toLowerCase(), "Measure");
    m.synonyms.forEach((s) => add(s, "Measure"));
  });
  meta.dimensions.forEach((d) => {
    add(d.label.toLowerCase(), "Dimension");
    if (d.name !== "seller") (d.values ?? []).forEach((v) => add(v, d.label));
  });
  return terms;
}

/** Terms that complete the last 1-3 words being typed. */
export function completions(text: string, vocab: Term[], limit = 8): { term: Term; replaceFrom: number }[] {
  if (!text.trim() || /\s$/.test(text)) return [];
  const words = [...text.matchAll(/\S+/g)];
  for (let n = Math.min(3, words.length); n >= 1; n--) {
    const start = words[words.length - n].index ?? 0;
    const fragment = normalizeText(text.slice(start));
    if (fragment.length < 2) continue;
    const hits = vocab.filter((t) => t.norm.startsWith(fragment) && t.norm !== fragment);
    if (hits.length) {
      hits.sort((a, b) => (a.kind === b.kind ? a.norm.length - b.norm.length : a.kind === "Measure" ? -1 : 1));
      return hits.slice(0, limit).map((term) => ({ term, replaceFrom: start }));
    }
  }
  return [];
}

interface Props {
  metadata?: Metadata;
  disabled?: boolean;
  onSubmit: (question: string) => void;
  value: string;
  onChange: (value: string) => void;
}

export function QuestionBox({ metadata, disabled, onSubmit, value, onChange }: Props) {
  const vocab = useMemo(() => buildVocabulary(metadata), [metadata]);
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const items = open ? completions(value, vocab) : [];

  const accept = (i: number) => {
    const item = items[i];
    if (!item) return;
    onChange(`${value.slice(0, item.replaceFrom)}${item.term.text} `);
    setOpen(false);
    input.current?.focus();
  };

  const submit = () => {
    const q = value.trim();
    if (q && !disabled) {
      setOpen(false);
      onSubmit(q);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (items.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setIndex((i) => (i + 1) % items.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setIndex((i) => (i - 1 + items.length) % items.length);
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        accept(index);
        return;
      }
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (items.length && open && index > 0) accept(index);
      else submit();
    }
  };

  return (
    <div className="relative">
      <label htmlFor="question" className="sr-only">Ask a question about the data</label>
      <div className="card flex items-end gap-2 p-2 shadow-sm focus-within:border-accent">
        <textarea
          id="question"
          ref={input}
          rows={2}
          value={value}
          disabled={disabled}
          maxLength={500}
          placeholder="Ask a question, e.g. “Show total sales in São Paulo in 2018”"
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
            setIndex(0);
          }}
          onKeyDown={onKeyDown}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          role="combobox"
          aria-expanded={items.length > 0}
          aria-controls="question-suggestions"
          aria-autocomplete="list"
          className="min-h-[3.25rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-base text-ink placeholder:text-muted focus:outline-none"
        />
        <button type="button" className="btn-primary h-10" onClick={submit} disabled={disabled || !value.trim()}>
          Ask <IconSend size={16} />
        </button>
      </div>
      <p className="mt-1.5 px-1 text-xs text-muted">Enter to ask · Shift+Enter for a new line · Tab to complete</p>
      {items.length > 0 && (
        <ul
          id="question-suggestions"
          role="listbox"
          className="absolute left-0 right-0 top-full z-20 -mt-5 overflow-hidden rounded-lg border border-line bg-surface shadow-lg"
        >
          {items.map((item, i) => (
            <li
              key={item.term.norm}
              role="option"
              aria-selected={i === index}
              onMouseDown={(e) => {
                e.preventDefault();
                accept(i);
              }}
              className={`flex cursor-pointer items-center justify-between px-3 py-1.5 text-sm ${i === index ? "bg-surface-2" : ""}`}
            >
              <span>{item.term.text}</span>
              <span className="text-xs text-muted">{item.term.kind}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
