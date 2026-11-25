/**
 * Microsoft Edge read-aloud from a Node server.
 * Browsers cannot set the required WebSocket headers, so this stays server-side.
 * The Sec-MS-GEC value is the v2 token the current service expects.
 */

import { randomBytes, randomUUID } from "node:crypto";
import WebSocket from "ws";

import { secMsGecV2 } from "./sec-ms-gec.mjs";
import type { WordMark } from "./offline-voice";

const TRUSTED = "6A5AA1D4EAFF4E9FB37E23D68491D6F4";
const VERSION = "2-143.0.3650.75";

export async function synthesizeEdge(text: string): Promise<{
  audio: Buffer;
  words: WordMark[];
  duration: number;
}> {
  const chunks: Buffer[] = [];
  const words: WordMark[] = [];
  await speak(text, chunks, words);
  if (!chunks.length) throw new Error("Edge TTS returned no audio");
  const audio = Buffer.concat(chunks);
  const duration = words.length ? words[words.length - 1].end + 0.2 : 1;
  return { audio, words, duration };
}

async function speak(text: string, chunks: Buffer[], words: WordMark[]): Promise<void> {
  const escaped = text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
  const voice = `Microsoft Server Speech Text to Speech Voice (en-US, AriaNeural)`;
  const ssml =
    `<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>` +
    `<voice name='${voice}'><prosody pitch='+0Hz' rate='+0%' volume='+0%'>${escaped}</prosody></voice></speak>`;
  const errors: string[] = [];
  try {
    await session(secMsGecV2(), ssml, chunks, words);
    return;
  } catch (error) {
    errors.push(error instanceof Error ? error.message : "edge failed");
  }
  // Clock skew: retry with the server date if the first handshake was rejected.
  const skewed = await serverSkewSeconds();
  if (skewed !== 0) {
    await session(secMsGecV2(Date.now() / 1000 + skewed), ssml, chunks, words);
    return;
  }
  throw new Error(errors.join("; ") || "edge failed");
}

async function serverSkewSeconds(): Promise<number> {
  try {
    const response = await fetch("https://www.bing.com", { method: "HEAD" });
    const date = response.headers.get("date");
    if (!date) return 0;
    return new Date(date).getTime() / 1000 - Date.now() / 1000;
  } catch {
    return 0;
  }
}

function session(token: string, ssml: string, chunks: Buffer[], words: WordMark[]): Promise<void> {
  const connection = randomUUID().replaceAll("-", "");
  const url =
    "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1" +
    `?TrustedClientToken=${TRUSTED}&ConnectionId=${connection}` +
    `&Sec-MS-GEC=${token}&Sec-MS-GEC-Version=${VERSION}`;
  const muid = randomBytes(16).toString("hex").toUpperCase();
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(url, {
      headers: {
        Pragma: "no-cache",
        "Cache-Control": "no-cache",
        Origin: "chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold",
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
        Cookie: `muid=${muid};`,
      },
      handshakeTimeout: 12000,
    });
    const timer = setTimeout(() => {
      socket.terminate();
      reject(new Error("Edge TTS timed out"));
    }, 20000);
    let audio = false;
    socket.on("open", () => {
      const stamp = new Date().toUTCString().replace("GMT", "GMT+0000 (Coordinated Universal Time)");
      socket.send(
        `X-Timestamp:${stamp}\r\nContent-Type:application/json; charset=utf-8\r\nPath:speech.config\r\n\r\n` +
          `{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"true"},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}\r\n`,
      );
      socket.send(
        `X-RequestId:${randomUUID().replaceAll("-", "")}\r\nContent-Type:application/ssml+xml\r\nX-Timestamp:${stamp}Z\r\nPath:ssml\r\n\r\n${ssml}`,
      );
    });
    socket.on("message", (data, isBinary) => {
      const buffer = Buffer.isBuffer(data) ? data : Buffer.from(data as ArrayBuffer);
      if (!isBinary) {
        const raw = buffer.toString("utf8");
        const split = raw.indexOf("\r\n\r\n");
        const body = split >= 0 ? raw.slice(split + 4) : "";
        if (raw.includes("Path:turn.end")) socket.close();
        if (!raw.includes("Path:audio.metadata") || !body) return;
        try {
          const meta = JSON.parse(body) as {
            Metadata?: { Type?: string; Data?: { Offset?: number; Duration?: number; text?: { Text?: string } } }[];
          };
          for (const item of meta.Metadata ?? []) {
            if (item.Type !== "WordBoundary") continue;
            const start = (item.Data?.Offset ?? 0) / 1e7;
            const length = (item.Data?.Duration ?? 0) / 1e7;
            const token = item.Data?.text?.Text?.trim();
            if (token) words.push({ text: token, start, end: start + length });
          }
        } catch {
          /* ignore a metadata frame we cannot parse */
        }
        return;
      }
      if (buffer.length < 2) return;
      const headerLength = buffer.readUInt16BE(0);
      const header = buffer.subarray(2, 2 + headerLength).toString("utf8");
      const body = buffer.subarray(2 + headerLength);
      if (header.includes("Path:audio") && header.includes("audio/mpeg") && body.length) {
        audio = true;
        chunks.push(body);
      }
    });
    socket.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    socket.on("unexpected-response", (_request, response) => {
      clearTimeout(timer);
      reject(new Error(`Edge TTS handshake ${response.statusCode}`));
    });
    socket.on("close", () => {
      clearTimeout(timer);
      if (audio) resolve();
      else reject(new Error("Edge TTS closed without audio"));
    });
  });
}
