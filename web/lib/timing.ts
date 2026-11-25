/** Keep these constants aligned with src/shorts_pipeline/timing.py. */

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

export function estimateSeconds(text: string): number {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return 0;
  let cursor = LEAD_IN;
  words.forEach((word, index) => {
    cursor += wordDuration(word);
    if (index !== words.length - 1) cursor += GAP;
  });
  return Math.round((cursor + TAIL) * 1000) / 1000;
}
