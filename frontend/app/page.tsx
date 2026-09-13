"use client";

import { useState } from "react";
import type { ResearchResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function Home() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResponse | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/research`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail?.message || `Request failed (${res.status})`);
      }

      const data: ResearchResponse = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-10">
      <h1 className="text-2xl font-semibold mb-1">Zephra Research Agent</h1>
      <p className="text-slate-500 mb-6">Multi-source, evidence-grounded research answers.</p>

      <form onSubmit={handleSubmit} className="flex gap-2 mb-8">
        <input
          className="flex-1 border border-slate-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-slate-400"
          placeholder="Ask a research question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-slate-900 text-white px-4 py-2 rounded-md disabled:opacity-50"
        >
          {loading ? "Researching..." : "Research"}
        </button>
      </form>

      {error && (
        <div className="border border-red-300 bg-red-50 text-red-800 rounded-md px-4 py-3 mb-6">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-8">
          <section>
            <h2 className="text-sm font-medium text-slate-500 uppercase mb-2">Answer</h2>
            <p className="text-lg leading-relaxed">{result.answer.summary}</p>
          </section>

          {result.answer.claims.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-slate-500 uppercase mb-2">Supporting claims</h2>
              <ul className="space-y-2">
                {result.answer.claims.map((c, i) => (
                  <li key={i} className="border border-slate-200 rounded-md px-3 py-2">
                    <span>{c.text}</span>{" "}
                    <span className="text-slate-400 text-sm">
                      [{c.source_ids.join(", ")}]
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.answer.conflicts.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-amber-600 uppercase mb-2">Conflicts</h2>
              <ul className="list-disc list-inside space-y-1 text-amber-800">
                {result.answer.conflicts.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </section>
          )}

          {result.answer.uncertainties.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-slate-500 uppercase mb-2">Uncertainties</h2>
              <ul className="list-disc list-inside space-y-1 text-slate-600">
                {result.answer.uncertainties.map((u, i) => (
                  <li key={i}>{u}</li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="text-sm font-medium text-slate-500 uppercase mb-2">Sources</h2>
            <ul className="space-y-2">
              {result.sources.map((s) => (
                <li key={s.id} className="text-sm">
                  <span className="font-mono text-slate-400 mr-2">[{s.id}]</span>
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-blue-700 underline">
                    {s.title}
                  </a>
                  <span className="text-slate-400">
                    {" "}
                    · {s.providers.join(", ")}
                    {s.relevance_score != null ? ` · score ${s.relevance_score.toFixed(2)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {result.provider_errors.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-slate-400 uppercase mb-2">Provider notes</h2>
              <ul className="list-disc list-inside space-y-1 text-slate-400 text-sm">
                {result.provider_errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </main>
  );
}
