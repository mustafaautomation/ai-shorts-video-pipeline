"use client";

import { useEffect, useState, type FormEvent } from "react";

type ScriptDraft = {
  topic: string;
  hook: string;
  body: string[];
  cta: string;
  provider: string;
  full_text: string;
  word_count: number;
  estimated_seconds: number;
};

export function Studio() {
  const [topic, setTopic] = useState("How to explain a hard idea in 30 seconds");
  const [script, setScript] = useState<ScriptDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    return () => window.speechSynthesis?.cancel();
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await fetch("/api/script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic }),
      });
      const payload = (await response.json()) as ScriptDraft & { error?: string };
      if (!response.ok) {
        setScript(null);
        setError(payload.error ?? "The writer did not return a script.");
        return;
      }
      setScript(payload);
    } catch {
      setScript(null);
      setError("The writer could not be reached.");
    } finally {
      setPending(false);
    }
  }

  function speak() {
    if (!script) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(script.full_text);
    utterance.rate = 1.02;
    window.speechSynthesis.speak(utterance);
  }

  return (
    <section className="studio">
      <form onSubmit={onSubmit}>
        <label htmlFor="topic">Topic</label>
        <input
          id="topic"
          name="topic"
          type="text"
          value={topic}
          maxLength={240}
          required
          onChange={(event) => setTopic(event.target.value)}
        />
        <div className="actions">
          <button type="submit" disabled={pending}>
            {pending ? "Writing…" : "Write the script"}
          </button>
          <button type="button" className="secondary" onClick={speak} disabled={!script}>
            Read it aloud
          </button>
        </div>
        <p className="hint">
          This page writes the script live. The phone is a reel the pipeline already rendered.
          Voice here uses your browser. The pipeline itself uses Edge TTS.
        </p>
        {error ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}
      </form>
      <div className="board" aria-live="polite">
        {script ? (
          <>
            <p className="meta">
              {script.provider} · {script.word_count} words · about {script.estimated_seconds.toFixed(0)}s
            </p>
            <h2>Hook</h2>
            <p className="beat">{script.hook}</p>
            <h2>Body</h2>
            {script.body.map((beat) => (
              <p className="beat" key={beat}>
                {beat}
              </p>
            ))}
            <h2>Call to action</h2>
            <p className="beat">{script.cta}</p>
          </>
        ) : (
          <>
            <p className="meta">Waiting for a topic</p>
            <h2>The script lands here</h2>
            <p className="beat">Hook, two to four beats, then one ask. Thirty to forty-five seconds when read aloud.</p>
          </>
        )}
      </div>
    </section>
  );
}
