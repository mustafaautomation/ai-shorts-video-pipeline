import { generateScript } from "@/lib/script";

export const runtime = "nodejs";

export async function POST(request: Request) {
  let topic = "";
  try {
    const body = (await request.json()) as { topic?: unknown };
    topic = typeof body.topic === "string" ? body.topic : "";
  } catch {
    return Response.json({ error: "Send a JSON body with a topic." }, { status: 400 });
  }
  if (!topic.trim() || topic.trim().length > 240) {
    return Response.json({ error: "Give a topic of 240 characters or fewer." }, { status: 422 });
  }
  try {
    const script = await generateScript(topic);
    return Response.json(script);
  } catch {
    return Response.json({ error: "The writer could not finish a script." }, { status: 500 });
  }
}
