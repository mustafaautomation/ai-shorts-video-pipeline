"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  STAGE_LABELS,
  claimId,
  mockReceipts,
  rankFixtures,
  resetUsed,
  scenesFromScript,
  usedIds,
  type FixtureReel,
  type PublishReceipt,
  type SceneCard,
  type StageName,
  type StageState,
} from "@/lib/pipeline";
import { renderReel, type CaptionWord } from "@/lib/render-reel";

type ScriptDraft = {
  hook: string;
  body: string[];
  cta: string;
  full_text: string;
  provider: string;
  word_count: number;
  estimated_seconds: number;
};

const initialStages = (): StageState[] =>
  STAGE_LABELS.map((stage) => ({ ...stage, status: "waiting", detail: "" }));

export function Studio() {
  const [topic, setTopic] = useState("How to explain a hard idea in 30 seconds");
  const [stages, setStages] = useState<StageState[]>(initialStages);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [winner, setWinner] = useState<FixtureReel | null>(null);
  const [script, setScript] = useState<ScriptDraft | null>(null);
  const [scenes, setScenes] = useState<SceneCard[]>([]);
  const [voiceProvider, setVoiceProvider] = useState<string | null>(null);
  const [words, setWords] = useState<CaptionWord[]>([]);
  const [audio, setAudio] = useState<ArrayBuffer | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [receipts, setReceipts] = useState<PublishReceipt[] | null>(null);
  const [variant, setVariant] = useState(0);

  useEffect(() => () => {
    if (videoUrl) URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  function mark(name: StageName, status: StageState["status"], detail: string) {
    setStages((current) => current.map((stage) => (stage.name === name ? { ...stage, status, detail } : stage)));
  }

  async function writeScript(nextVariant: number) {
    const response = await fetch("/api/script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, variant: nextVariant }),
    });
    const payload = (await response.json()) as ScriptDraft & { error?: string };
    if (!response.ok) throw new Error(payload.error || "The writer did not return a script.");
    return payload;
  }

  async function speak(text: string) {
    const response = await fetch("/api/voice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const payload = (await response.json()) as {
      error?: string;
      provider: string;
      mime: string;
      audioBase64: string;
      words: CaptionWord[];
    };
    if (!response.ok) throw new Error(payload.error || "Voice failed.");
    const binary = Uint8Array.from(atob(payload.audioBase64), (char) => char.charCodeAt(0));
    return { provider: payload.provider, words: payload.words, audio: binary.buffer };
  }

  async function paint(nextScenes: SceneCard[], spoken: { words: CaptionWord[]; audio: ArrayBuffer }) {
    mark("render", "running", "Encoding 1080×1920");
    const blob = await renderReel({
      audio: spoken.audio,
      words: spoken.words,
      scenes: nextScenes.map((scene) => ({ narration: scene.narration, seed: scene.seed })),
      onFrame: (index, total) => {
        if (index === total || index % 12 === 0) mark("render", "running", `Frame ${index} / ${total}`);
      },
    });
    const url = URL.createObjectURL(blob);
    setVideoUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return url;
    });
    mark("render", "done", "MP4 ready in the browser");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setReceipts(null);
    setVideoUrl(null);
    setStages(initialStages());
    try {
      mark("scrape", "running", "Ranking the sample set");
      const ranked = rankFixtures();
      const taken = new Set(usedIds());
      const next = ranked.find((reel) => !taken.has(reel.id));
      if (!next) {
        mark("scrape", "done", "Every sample id is already used");
        mark("dedupe", "done", "Run is idempotent — clear used ids to go again");
        setError("Those sample reels were already used. Clear them and run again.");
        return;
      }
      mark("scrape", "done", `${next.username} · ${next.views.toLocaleString()} views`);
      setWinner(next);

      mark("dedupe", "running", next.id);
      if (!claimId(next.id)) {
        mark("dedupe", "done", "Already claimed");
        return;
      }
      mark("dedupe", "done", "Claimed. A second run will skip this id.");

      mark("transcribe", "running", "Fixture transcript (Whisper when a key is set)");
      mark("transcribe", "done", next.transcript);

      mark("script", "running", "Writing an original script");
      const drafted = await writeScript(0);
      setVariant(0);
      setScript(drafted);
      const built = scenesFromScript(drafted.hook, drafted.body, drafted.cta, 3);
      setScenes(built);
      mark("script", "done", `${drafted.provider} · ${drafted.word_count} words`);
      mark("scenes", "done", `${built.length} plates · Ken Burns, not a paid clip`);

      mark("voice", "running", "Edge TTS, with an offline tone if Microsoft is down");
      const spoken = await speak(drafted.full_text);
      setVoiceProvider(spoken.provider);
      setWords(spoken.words);
      setAudio(spoken.audio);
      mark("voice", "done", `${spoken.provider} · ${spoken.words.length} words timed`);

      await paint(built, spoken);
      mark("approval", "done", "Waiting for Approve or Regenerate");
      mark("publish", "waiting", "Mock receipts appear after Approve");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The run stopped.");
    } finally {
      setPending(false);
    }
  }

  async function regenerateScript() {
    if (!script) return;
    setPending(true);
    setError(null);
    setReceipts(null);
    try {
      const nextVariant = variant + 1;
      mark("script", "running", "Rewriting only the script");
      const drafted = await writeScript(nextVariant);
      setVariant(nextVariant);
      setScript(drafted);
      const built = scenesFromScript(drafted.hook, drafted.body, drafted.cta, 3 + nextVariant * 5);
      setScenes(built);
      mark("script", "done", "Regenerated script");
      mark("voice", "running", "New voiceover");
      const spoken = await speak(drafted.full_text);
      setVoiceProvider(spoken.provider);
      setWords(spoken.words);
      setAudio(spoken.audio);
      mark("voice", "done", spoken.provider);
      await paint(built, spoken);
      mark("approval", "done", "Script replaced. Scenes follow the new words.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Regenerate failed.");
    } finally {
      setPending(false);
    }
  }

  async function regenerateScene(index: number) {
    if (!audio || !script) return;
    setPending(true);
    setError(null);
    try {
      const built = scenes.map((scene) =>
        scene.index === index ? { ...scene, seed: scene.seed + 9, prompt: `${scene.prompt} Alternate framing.` } : scene,
      );
      setScenes(built);
      mark("scenes", "done", `Redid scene ${index + 1} only`);
      await paint(built, { audio, words });
      mark("approval", "done", `Scene ${index + 1} replaced`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Scene regenerate failed.");
    } finally {
      setPending(false);
    }
  }

  function approve() {
    if (!script) return;
    setReceipts(mockReceipts(script.hook, topic));
    mark("publish", "done", "Mock payloads only. Nothing was posted.");
    mark("approval", "done", "Approved");
  }

  return (
    <section>
      <form onSubmit={onSubmit}>
        <label htmlFor="topic">Topic</label>
        <input id="topic" name="topic" type="text" value={topic} maxLength={240} required onChange={(event) => setTopic(event.target.value)} />
        <div className="actions">
          <button type="submit" disabled={pending}>{pending ? "Running…" : "Run the pipeline"}</button>
          <button type="button" className="secondary" onClick={() => { resetUsed(); setError(null); }} disabled={pending}>
            Clear used ids
          </button>
        </div>
        <p className="hint">
          Free path: sample scrape, original script, Ken Burns plates, Edge or offline voice, and a 1080×1920 MP4 encoded in this browser. Publishing stays mocked.
        </p>
        {error ? <p className="error" role="alert">{error}</p> : null}
      </form>

      <div className="studio">
      <ol className="stages" aria-live="polite">
        {stages.map((stage, index) => (
          <li key={stage.name} data-status={stage.status}>
            <span>{index + 1}</span>
            <div>
              <strong>{stage.label}</strong>
              <p>{stage.detail || "Waiting"}</p>
            </div>
          </li>
        ))}
      </ol>

      <div className="board">
        {winner ? (
          <>
            <p className="meta">Inspired by {winner.id}, not copied</p>
            <h2>Transcript</h2>
            <p className="beat">{winner.transcript}</p>
          </>
        ) : null}
        {script ? (
          <>
            <p className="meta">{script.provider} · {script.word_count} words · voice {voiceProvider ?? "—"}</p>
            <h2>Hook</h2>
            <p className="beat">{script.hook}</p>
            <h2>Scenes</h2>
            {scenes.map((scene) => (
              <p className="beat" key={`${scene.index}-${scene.seed}`}>{scene.index + 1}. {scene.narration}</p>
            ))}
          </>
        ) : (
          <>
            <p className="meta">Waiting</p>
            <h2>The run lands here</h2>
            <p className="beat">Scrape, skip used ids, write something original, then render it in the phone.</p>
          </>
        )}
        {script && videoUrl ? (
          <div className="approval">
            <h2>Approval</h2>
            <div className="actions">
              <button type="button" onClick={approve} disabled={pending}>Approve</button>
              <button type="button" className="secondary" onClick={regenerateScript} disabled={pending}>Regenerate script</button>
              <button type="button" className="secondary" onClick={() => regenerateScene(1)} disabled={pending || scenes.length < 2}>
                Regenerate scene 2
              </button>
            </div>
          </div>
        ) : null}
        {receipts ? (
          <div>
            <h2>Mock publish</h2>
            {receipts.map((receipt) => (
              <pre key={receipt.platform} className="receipt">{JSON.stringify(receipt.request, null, 2)}</pre>
            ))}
          </div>
        ) : null}
      </div>
      <ResultPhone url={videoUrl} />
      </div>
    </section>
  );
}

function ResultPhone({ url }: { url: string | null }) {
  return (
    <div className="phone result-phone">
      {url ? (
        <>
          <video key={url} src={url} controls playsInline aria-label="Rendered vertical reel" />
          <a className="download" href={url} download="reel.mp4">Download MP4</a>
        </>
      ) : (
        <video src="/demo-reel.mp4" controls playsInline preload="metadata" aria-label="Sample reel from the CLI pipeline" />
      )}
    </div>
  );
}
