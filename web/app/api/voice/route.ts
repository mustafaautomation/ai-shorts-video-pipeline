import { offlineVoice } from "@/lib/server/offline-voice";
import { synthesizeEdge } from "@/lib/server/edge-voice";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(request: Request) {
  let text = "";
  try {
    const body = (await request.json()) as { text?: unknown };
    text = typeof body.text === "string" ? body.text.trim() : "";
  } catch {
    return Response.json({ error: "Send JSON with text." }, { status: 400 });
  }
  if (!text || text.length > 4000) {
    return Response.json({ error: "Voice text must be 1–4000 characters." }, { status: 422 });
  }

  try {
    const spoken = await synthesizeEdge(text);
    return Response.json({
      provider: "edge",
      mime: "audio/mpeg",
      audioBase64: spoken.audio.toString("base64"),
      words: spoken.words,
      duration: spoken.duration,
    });
  } catch {
    const fallback = offlineVoice(text);
    return Response.json({
      provider: "offline",
      mime: "audio/wav",
      audioBase64: fallback.wav.toString("base64"),
      words: fallback.words,
      duration: fallback.duration,
    });
  }
}
