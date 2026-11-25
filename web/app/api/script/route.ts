import { generateScript } from "@/lib/script";

export const runtime = "nodejs";

export async function POST(request: Request) {
  let topic = "";
  let variant = 0;
  try {
    const body = (await request.json()) as { topic?: unknown; variant?: unknown };
    topic = typeof body.topic === "string" ? body.topic : "";
    variant = typeof body.variant === "number" ? body.variant : 0;
  } catch {
    return Response.json({ error: "Send a JSON body with a topic." }, { status: 400 });
  }
  if (!topic.trim() || topic.trim().length > 240) {
    return Response.json({ error: "Give a topic of 240 characters or fewer." }, { status: 422 });
  }
  try {
    const script = await generateScript(topic, variant);
    return Response.json(script);
  } catch {
    return Response.json({ error: "The writer could not finish a script." }, { status: 500 });
  }
}
