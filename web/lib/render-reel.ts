import {
  AudioBufferSource,
  BufferTarget,
  CanvasSource,
  Mp4OutputFormat,
  Output,
  canEncodeAudio,
} from "mediabunny";

export type CaptionWord = { text: string; start: number; end: number };
export type ScenePlate = { narration: string; seed: number };

const WIDTH = 1080;
const HEIGHT = 1920;
const FPS = 12;

export async function renderReel(options: {
  audio: ArrayBuffer;
  words: CaptionWord[];
  scenes: ScenePlate[];
  onFrame?: (index: number, total: number) => void;
}): Promise<Blob> {
  const context = new AudioContext();
  const decoded = await toStereo48k(await context.decodeAudioData(options.audio.slice(0)));
  await context.close();
  const duration = Math.min(decoded.duration, 48);
  const frames = Math.max(1, Math.round(duration * FPS));
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas is not available in this browser.");

  const output = new Output({
    format: new Mp4OutputFormat({ fastStart: "in-memory" }),
    target: new BufferTarget(),
  });
  const video = new CanvasSource(canvas, {
    codec: "avc",
    bitrate: 1_500_000,
    keyFrameInterval: 2,
    latencyMode: "realtime",
  });
  const aacOk = await canEncodeAudio("aac", { numberOfChannels: 2, sampleRate: 48000, bitrate: 128_000 });
  const audioCodec = aacOk ? "aac" : "opus";
  const audio = new AudioBufferSource({ codec: audioCodec, bitrate: audioCodec === "aac" ? 128_000 : 64_000 });
  output.addVideoTrack(video);
  output.addAudioTrack(audio);
  output.setMetadataTags({ title: "Portfolio demo reel", artist: "Mustafa" });
  await output.start();

  for (let frame = 0; frame < frames; frame += 1) {
    const time = frame / FPS;
    paintFrame(ctx, time, duration, options.words, options.scenes);
    await video.add(time, 1 / FPS);
    options.onFrame?.(frame + 1, frames);
  }
  await audio.add(decoded);
  await output.finalize();
  const buffer = output.target.buffer;
  if (!buffer) throw new Error("The encoder did not return an MP4.");
  return new Blob([buffer], { type: "video/mp4" });
}

async function toStereo48k(input: AudioBuffer): Promise<AudioBuffer> {
  const rate = 48000;
  const length = Math.max(1, Math.ceil(input.duration * rate));
  const offline = new OfflineAudioContext(2, length, rate);
  const source = offline.createBufferSource();
  source.buffer = input;
  source.connect(offline.destination);
  source.start();
  return offline.startRendering();
}

function paintFrame(
  ctx: CanvasRenderingContext2D,
  time: number,
  duration: number,
  words: CaptionWord[],
  scenes: ScenePlate[],
) {
  const sceneCount = Math.max(1, scenes.length);
  const sceneIndex = Math.min(sceneCount - 1, Math.floor((time / Math.max(duration, 0.1)) * sceneCount));
  const scene = scenes[sceneIndex] ?? { narration: "", seed: 1 };
  const drift = (time * 18 + scene.seed * 12) % 220;
  const gradient = ctx.createLinearGradient(0, drift, WIDTH, HEIGHT - drift);
  const hue = (scene.seed * 28 + sceneIndex * 16) % 40;
  gradient.addColorStop(0, `hsl(${28 + hue} 42% 14%)`);
  gradient.addColorStop(0.45, `hsl(${70 + hue} 38% 22%)`);
  gradient.addColorStop(1, "#12110e");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  ctx.fillStyle = "#d6e35a";
  ctx.fillRect(WIDTH / 2 - 70, 210, 140, 8);
  ctx.font = "700 32px Outfit, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(sceneIndex === 0 ? "HOOK" : sceneIndex === sceneCount - 1 ? "TRY THIS" : `SCENE ${sceneIndex}`, WIDTH / 2, 190);

  ctx.fillStyle = "#f4efe6";
  ctx.font = "700 54px Outfit, Arial, sans-serif";
  wrapText(ctx, scene.narration, WIDTH / 2, 280, 900, 64);

  const active = words.find((word) => time >= word.start && time < word.end + 0.04) ?? words[words.length - 1];
  const line = captionLine(words, active);
  ctx.font = "800 72px Outfit, Arial, sans-serif";
  const y = HEIGHT - 420;
  let cursor = WIDTH / 2 - line.reduce((sum, word) => sum + ctx.measureText(`${word.text} `).width, 0) / 2;
  for (const word of line) {
    ctx.fillStyle = word === active ? "#d6e35a" : "#ffffff";
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 10;
    ctx.strokeText(word.text, cursor + ctx.measureText(word.text).width / 2, y);
    ctx.fillText(word.text, cursor + ctx.measureText(word.text).width / 2, y);
    cursor += ctx.measureText(`${word.text} `).width;
  }

  ctx.font = "600 26px Outfit, Arial, sans-serif";
  ctx.fillStyle = "rgba(244,239,230,0.7)";
  ctx.fillText("PORTFOLIO DEMO  ·  PUBLISH IS MOCKED", WIDTH / 2, HEIGHT - 90);
}

function captionLine(words: CaptionWord[], active: CaptionWord | undefined): CaptionWord[] {
  if (!active) return [];
  const index = words.indexOf(active);
  const start = Math.max(0, index - (index % 3));
  return words.slice(start, start + 3);
}

function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
) {
  const words = text.split(/\s+/).slice(0, 18);
  let line = "";
  let cursor = y;
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      ctx.fillText(line, x, cursor);
      line = word;
      cursor += lineHeight;
    } else {
      line = next;
    }
  }
  if (line) ctx.fillText(line, x, cursor);
}
