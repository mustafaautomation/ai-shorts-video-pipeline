import { createHash } from "node:crypto";

import { estimateSeconds } from "./timing";

export type ScriptDraft = {
  topic: string;
  hook: string;
  body: string[];
  cta: string;
  provider: string;
  full_text: string;
  word_count: number;
  estimated_seconds: number;
};

const HOOKS = [
  "Stop scrolling. {Topic} is simpler than the long version.",
  "Here is the short version of {topic}.",
  "{Topic} gets easier when you keep one shape.",
  "{Topic}, with the extra parts already cut.",
  "Before you swipe, take the useful version of {topic}.",
];

const BEATS = [
  "Open on the problem in plain words, then let {topic} be the fix.",
  "Give one picture a stranger could repeat after hearing it a single time.",
  "Drop every detail that does not change what the viewer should do next.",
  "Use one example so the idea can land on the very first pass.",
  "Say what changes today when someone actually applies {topic}.",
  "Contrast the slow way with the one-step way, then stop talking.",
  "Keep every line spoken. If you would not say it out loud, cut it.",
  "Name the person this helps, and the exact moment they need it.",
];

const CTAS = [
  "Save this and try {topic} on the next thing you explain.",
  "Follow for the short version, and comment the topic you want next.",
  "Share this with someone who needs {topic} explained cleanly.",
  "Tap save, then teach {topic} once while it is still fresh.",
];

const EXTENSIONS = [
  "Say it like you are talking to one person across the table.",
  "Keep a single example in the frame the whole time.",
  "Do not add a second idea after that picture lands.",
  "Let the last line be the thing they should do next.",
  "Stop before you explain the background or the history.",
  "Trust that one clear picture is enough for this short.",
  "Leave a little room for the viewer to try it today.",
  "Cut any word that does not change the next step.",
];

const CTA_VERBS = new Set([
  "comment",
  "follow",
  "save",
  "send",
  "share",
  "start",
  "subscribe",
  "tap",
  "tell",
  "try",
  "watch",
]);

const DANGLING = new Set([
  "a",
  "an",
  "and",
  "for",
  "in",
  "of",
  "on",
  "or",
  "the",
  "to",
  "who",
  "with",
  "without",
]);

const SYSTEM_PROMPT =
  "You write spoken scripts for a 30 to 45 second vertical short. " +
  "Return JSON with keys hook (string), body (array of 2 to 4 short sentences), " +
  "and cta (string). No markdown, no hashtags, no stage directions, no brackets. " +
  "The hook is one or two spoken sentences. The CTA tells the viewer to save, " +
  "share, follow, comment, or try something. Mention the topic in the words " +
  "the viewer hears. Target 75 to 100 spoken words.";

function normalizeTopic(topic: string): string {
  const cleaned = topic.replaceAll("\n", " ").split(/\s+/).filter(Boolean).join(" ");
  const stripped = cleaned.replace(/^[ .,:;!-]+|[ .,:;!-]+$/g, "");
  if (![...stripped].some((char) => /[0-9a-z]/i.test(char))) return "this idea";
  return stripped || "this idea";
}

function stripDangling(words: string[]): string[] {
  const cleaned = [...words];
  while (cleaned.length > 0 && DANGLING.has(cleaned[cleaned.length - 1].toLowerCase().replace(/[.,!?;:]+$/g, ""))) {
    cleaned.pop();
  }
  return cleaned;
}

function spokenTopic(topic: string): string {
  let words = stripDangling(normalizeTopic(topic).split(/\s+/).slice(0, 12));
  let text = words.join(" ");
  while (words.length > 0 && text.length > 78) {
    words = stripDangling(words.slice(0, -1));
    text = words.join(" ");
  }
  return text || "this idea";
}

function topicSeed(topic: string): number {
  const digest = createHash("sha256").update(normalizeTopic(topic).toLowerCase()).digest("hex");
  return Number.parseInt(digest.slice(0, 12), 16);
}

function formsFor(phrase: string): { topic: string; Topic: string } {
  const lower = phrase === phrase.toUpperCase() && /[A-Z]/.test(phrase) && phrase.length <= 4
    ? phrase
    : phrase.slice(0, 1).toLowerCase() + phrase.slice(1);
  const upper = phrase.slice(0, 1).toUpperCase() + phrase.slice(1);
  return { topic: lower, Topic: upper };
}

function fill(template: string, forms: { topic: string; Topic: string }): string {
  return template.replaceAll("{Topic}", forms.Topic).replaceAll("{topic}", forms.topic);
}

function spokenText(hook: string, body: string[], cta: string): string {
  return [hook, ...body, cta].map((part) => part.trim()).filter(Boolean).join(" ");
}

function acceptable(topic: string, hook: string, body: string[], cta: string): boolean {
  const text = spokenText(hook, body, cta);
  const hookWords = hook.split(/\s+/).filter(Boolean);
  const ctaTokens = new Set(cta.split(/\s+/).map((word) => word.replace(/^[.,!?:;"']+|[.,!?:;"']+$/g, "").toLowerCase()));
  const phrase = spokenTopic(topic).toLowerCase();
  const collapsed = text.toLowerCase().split(/\s+/).join(" ");
  const duration = estimateSeconds(text);
  return (
    hook.trim().length > 0 &&
    hookWords.length > 0 &&
    hookWords.length <= 24 &&
    body.length >= 2 &&
    body.length <= 4 &&
    body.every((beat) => beat.trim().length > 0) &&
    cta.trim().length > 0 &&
    [...CTA_VERBS].some((verb) => ctaTokens.has(verb)) &&
    duration >= 30 &&
    duration <= 45 &&
    collapsed.includes(phrase) &&
    !text.includes("[") &&
    !text.includes("]") &&
    !text.includes("#")
  );
}

function hookFor(seed: number, forms: { topic: string; Topic: string }): string {
  for (let offset = 0; offset < HOOKS.length; offset += 1) {
    const hook = fill(HOOKS[(seed + offset) % HOOKS.length], forms);
    const words = hook.split(/\s+/).map((word) => word.replace(/^[.,!?;:]+|[.,!?;:]+$/g, "").toLowerCase());
    const doubled = words.some((word, index) => index > 0 && word === words[index - 1]);
    if (!doubled && words.length <= 24) return hook;
  }
  return `${forms.Topic} in one clean pass.`;
}

function publish(topic: string, hook: string, body: string[], cta: string, provider: string): ScriptDraft {
  const full = spokenText(hook, body, cta);
  return {
    topic,
    hook,
    body,
    cta,
    provider,
    full_text: full,
    word_count: full.split(/\s+/).filter(Boolean).length,
    estimated_seconds: estimateSeconds(full),
  };
}

export function offlineScript(topic: string): ScriptDraft {
  const phrase = spokenTopic(topic);
  const forms = formsFor(phrase);
  const seed = topicSeed(topic);
  const hook = hookFor(seed, forms);
  const cta = fill(CTAS[seed % CTAS.length], forms);
  const rotated = BEATS.map((_, offset) => fill(BEATS[(seed + offset) % BEATS.length], forms));
  const extras = EXTENSIONS.map((_, offset) => EXTENSIONS[(seed + offset) % EXTENSIONS.length]);
  for (const count of [2, 3, 4]) {
    const body = rotated.slice(0, count);
    if (acceptable(topic, hook, body, cta)) return publish(topic, hook, body, cta, "offline");
    for (let used = 1; used <= extras.length; used += 1) {
      const extended = [...body.slice(0, -1), `${body[body.length - 1]} ${extras.slice(0, used).join(" ")}`];
      if (acceptable(topic, hook, extended, cta)) return publish(topic, hook, extended, cta, "offline");
    }
  }
  const shortHook = `${forms.Topic} in one clean pass.`;
  const shortCta = "Save this and try it once today.";
  const fallback = [
    "Start with the problem the viewer already feels.",
    "Show one example they can picture immediately.",
    `Then come back to ${forms.topic} and cut anything extra.`,
  ];
  if (acceptable(topic, shortHook, fallback, shortCta)) {
    return publish(topic, shortHook, fallback, shortCta, "offline");
  }
  for (let used = 1; used <= extras.length; used += 1) {
    const extended = [...fallback.slice(0, -1), `${fallback[fallback.length - 1]} ${extras.slice(0, used).join(" ")}`];
    if (acceptable(topic, shortHook, extended, shortCta)) {
      return publish(topic, shortHook, extended, shortCta, "offline");
    }
  }
  throw new Error("offline script writer could not fit the 30-45s window");
}

function stripFence(text: string): string {
  let stripped = text.trim();
  if (stripped.startsWith("```")) {
    stripped = stripped.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  }
  return stripped.trim();
}

function fromPayload(topic: string, data: unknown, provider: string): ScriptDraft | null {
  if (!data || typeof data !== "object") return null;
  const record = data as { hook?: unknown; body?: unknown; cta?: unknown };
  const hook = typeof record.hook === "string" ? record.hook.trim() : "";
  const cta = typeof record.cta === "string" ? record.cta.trim() : "";
  let body: string[] = [];
  if (typeof record.body === "string") {
    body = record.body.split(/\n+|(?<=[.!?])\s+/).map((part) => part.trim()).filter(Boolean);
  } else if (Array.isArray(record.body)) {
    body = record.body.map((part) => String(part).trim()).filter(Boolean);
  }
  if (!acceptable(topic, hook, body, cta)) return null;
  return publish(topic, hook, body, cta, provider);
}

async function postJson(url: string, headers: Record<string, string>, payload: unknown): Promise<unknown> {
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) throw new Error(`provider status ${response.status}`);
  return response.json();
}

async function fromGroq(topic: string): Promise<ScriptDraft | null> {
  const key = process.env.GROQ_API_KEY;
  if (!key) return null;
  const model = process.env.GROQ_MODEL || "llama-3.3-70b-versatile";
  const phrase = spokenTopic(topic);
  try {
    const data = await postJson(
      "https://api.groq.com/openai/v1/chat/completions",
      { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      {
        model,
        temperature: 0.6,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          {
            role: "user",
            content: `Topic: ${topic}\nSay this phrase out loud somewhere in the script: ${phrase}\nSpoken length must land between 30 and 45 seconds.`,
          },
        ],
      },
    );
    const content = (data as { choices?: { message?: { content?: string } }[] }).choices?.[0]?.message?.content;
    if (!content) return null;
    return fromPayload(topic, JSON.parse(stripFence(content)), "groq");
  } catch {
    return null;
  }
}

async function fromGemini(topic: string): Promise<ScriptDraft | null> {
  const key = process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY;
  if (!key) return null;
  const model = process.env.GEMINI_MODEL || "gemini-2.0-flash";
  const phrase = spokenTopic(topic);
  try {
    const data = await postJson(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
      { "x-goog-api-key": key, "Content-Type": "application/json" },
      {
        contents: [
          {
            parts: [
              {
                text: `${SYSTEM_PROMPT}\n\nTopic: ${topic}\nSay this phrase out loud somewhere in the script: ${phrase}`,
              },
            ],
          },
        ],
        generationConfig: { temperature: 0.6, responseMimeType: "application/json" },
      },
    );
    const text = (data as { candidates?: { content?: { parts?: { text?: string }[] } }[] }).candidates?.[0]?.content
      ?.parts?.[0]?.text;
    if (!text) return null;
    return fromPayload(topic, JSON.parse(stripFence(text)), "gemini");
  } catch {
    return null;
  }
}

export async function generateScript(topic: string): Promise<ScriptDraft> {
  const cleaned = topic.replace(/\s+/g, " ").trim();
  if (!cleaned) throw new Error("topic is required");
  if (cleaned.length > 240) throw new Error("topic must be 240 characters or fewer");
  const groq = await fromGroq(cleaned);
  if (groq) return groq;
  const gemini = await fromGemini(cleaned);
  if (gemini) return gemini;
  return offlineScript(cleaned);
}
