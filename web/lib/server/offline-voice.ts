/** Tone bed used when Edge TTS is unreachable. Word times match web/lib/timing.ts. */

import { estimateSeconds } from "../timing";

export type WordMark = { text: string; start: number; end: number };

const LEAD_IN = 0.18;
const TAIL = 0.45;
const GAP = 0.065;
const MIN_WORD = 0.22;
const MAX_WORD = 0.56;
const PER_ALNUM = 0.046;
const BASE_WORD = 0.14;

function wordDuration(word: string): number {
  const letters = [...word].filter((char) => /[0-9a-z]/i.test(char)).length;
  const raw = BASE_WORD + PER_ALNUM * Math.max(1, letters);
  return Math.max(MIN_WORD, Math.min(MAX_WORD, raw));
}

export function planWords(text: string): WordMark[] {
  const words = text.split(/\s+/).filter(Boolean);
  let cursor = LEAD_IN;
  return words.map((word, index) => {
    const duration = wordDuration(word);
    const start = Math.round(cursor * 1000) / 1000;
    const end = Math.round((cursor + duration) * 1000) / 1000;
    cursor += duration;
    if (index !== words.length - 1) cursor += GAP;
    return { text: word, start, end };
  });
}

export function offlineVoice(text: string): { wav: Buffer; words: WordMark[]; duration: number } {
  const words = planWords(text);
  const duration = words.length ? words[words.length - 1].end + TAIL : 0.4;
  const rate = 22050;
  const total = Math.floor(duration * rate);
  const samples = new Int16Array(total);
  words.forEach((word, index) => {
    const start = Math.floor(word.start * rate);
    const end = Math.min(total, Math.floor(word.end * rate));
    const span = Math.max(1, end - start);
    const fundamental = 132 + (index % 6) * 17;
    for (let sample = Math.max(0, start); sample < end; sample += 1) {
      const local = (sample - start) / span;
      const envelope = Math.sin(Math.PI * local) ** 1.15;
      const time = sample / rate;
      const value =
        0.55 * Math.sin(2 * Math.PI * fundamental * time) +
        0.18 * Math.sin(2 * Math.PI * fundamental * 2.01 * time);
      samples[sample] = Math.max(-32767, Math.min(32767, Math.round(envelope * value * 32767)));
    }
  });
  const header = Buffer.alloc(44);
  const dataBytes = Buffer.from(samples.buffer);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + dataBytes.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(rate, 24);
  header.writeUInt32LE(rate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(dataBytes.length, 40);
  return {
    wav: Buffer.concat([header, dataBytes]),
    words,
    duration: estimateSeconds(text) || duration,
  };
}
