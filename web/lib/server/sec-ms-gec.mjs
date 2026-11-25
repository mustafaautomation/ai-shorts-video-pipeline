/** v2 Sec-MS-GEC token. Same construction as edge-tts drm.generate_sec_ms_gec_v2. */

const MASK = 0xffffffffn;
const u = (value) => value & MASK;
const WIN_EPOCH = 11644473600;
const TRUSTED = "6A5AA1D4EAFF4E9FB37E23D68491D6F4";
const INITIAL = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19].map(BigInt);
const STATE = [0xfd9fbea2, 0x91243ce7, 0xbe499094, 0xcd2e1e0a, 0x6c006f49, 0x04bd35ab, 0xfeb0a7e4, 0x03effbd2].map(BigInt);
const SCHEDULE = [0xeb24bf9e, 0x1558691f, 0xa0c09ee2, 0x0cfa32ba, 0xa622ee8c, 0xd1dd9491, 0xc0dd25a0, 0xf9e70ab6, 0xf0c31573, 0x7058ce4e, 0x7188e606, 0x00e5ab33, 0xd258b060, 0x72766564].map(BigInt);
const ROUND = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2].map(BigInt);
const BLOCK = ROUND.slice(0, 14).concat([0xc9dc06a7n], ROUND.slice(15));
const SIG0_ADJ = 0x059c0b80n;
const SIG1_ADJ = 0x000b92c0n;
const ADJUST = 0xc9dc06a7n;
const CS_COEFF = [[0xe82e91b1, 0xb32700d0], [0x44de24c6, 0x88dff51d], [0x3beb65bc, 0x29514038], [0xc89c5933, 0xb328cbdf], [0x8d1ec211, 0xd405b4d5], [0x314ef5d5, 0x26e55f3c], [0xe92491b1, 0x607801c6], [0xf0a5b9d5, 0x82b2c1fb], [0x06064cf3, 0xfa51a3da], [0xda79fa60, 0x207cc464], [0xbed20560, 0x3c3c74f3], [0x89f9c9f8, 0xd2d14b61], [0x35fa38c6, 0xbb04a2c1], [0xcb49e3c6, 0xc5626167]].map((pair) => pair.map(BigInt));

const rol16 = (value) => { const v = u(value); return u((v << 16n) | (v >> 16n)); };
const sigma0 = (value) => u((value >> 7n) ^ (value << 25n) ^ (value >> 18n) ^ (value << 14n) ^ (value >> 3n));
const sigma1 = (value) => u((value >> 17n) ^ (value << 15n) ^ (value >> 19n) ^ (value << 13n) ^ (value >> 10n));

function rounds(state, words, first = 0) {
  let [a, b, c, d, e, f, g, h] = state;
  const constants = first === 14 ? BLOCK : ROUND;
  for (let index = first; index < 64; index += 1) {
    const rotE = e * 0x100000001n;
    const rotA = a * 0x100000001n;
    const t1 = h + (u(rotE >> 6n) ^ u(rotE >> 11n) ^ u(rotE >> 25n)) + (g ^ (e & (f ^ g))) + constants[index] + words[index];
    const t2 = (u(rotA >> 2n) ^ u(rotA >> 13n) ^ u(rotA >> 22n)) + ((a & b) | (c & (a | b)));
    [a, b, c, d, e, f, g, h] = [u(t1 + t2), a, b, c, u(d + t1), e, f, g];
  }
  return [a, b, c, d, e, f, g, h];
}

function expand(words, first = 16) {
  for (let index = first; index < 64; index += 1) {
    const x = words[index - 2];
    const y = words[index - 15];
    const s1 = (x >> 17n) ^ (x << 15n) ^ (x >> 19n) ^ (x << 13n) ^ (x >> 10n);
    const s0 = (y >> 7n) ^ (y << 25n) ^ (y >> 18n) ^ (y << 14n) ^ (y >> 3n);
    words.push(u(s1 + words[index - 7] + s0 + words[index - 16]));
  }
}

function readU32(bytes, offset, size) {
  let value = 0n;
  for (let index = 0; index < size; index += 1) value = (value << 8n) | BigInt(bytes[offset + index] || 0);
  return value;
}

function sha256Init(data) {
  const words = Array(14).fill(0n);
  words.push(readU32(data, 0, 3));
  words.push(readU32(data, 3, 4));
  for (let index = 16; index < 30; index += 1) {
    let value = SCHEDULE[index - 16];
    if (index - 2 >= 14) value += index === 16 ? sigma1(words[index - 2]) ^ SIG1_ADJ : sigma1(words[index - 2]);
    if (index - 7 >= 14) value += words[index - 7];
    if (index - 15 >= 14) value += index === 29 ? sigma0(words[index - 15]) ^ SIG0_ADJ : sigma0(words[index - 15]);
    words.push(u(value));
  }
  words.push(u(sigma1(words[28]) + words[23] + sigma0(words[15]) + words[14] + ADJUST - ROUND[14]));
  expand(words, 31);
  const working = rounds(STATE, words, 14);
  return working.map((value, index) => u(value + INITIAL[index]));
}

function sha256Digest(data) {
  const length = 57 + data.length;
  const padLen = ((55 - length) % 64 + 64) % 64;
  const padded = Buffer.concat([data.subarray(7), Buffer.from([0x80]), Buffer.alloc(padLen), Buffer.alloc(8)]);
  padded.writeBigUInt64BE(BigInt(length * 8), padded.length - 8);
  let state = sha256Init(data.subarray(0, 7));
  for (let offset = 0; offset < padded.length; offset += 64) {
    const words = [];
    for (let index = 0; index < 16; index += 1) words.push(padded.readUInt32BE(offset + index * 4) & 0xffffffff ? BigInt(padded.readUInt32BE(offset + index * 4)) : 0n);
    expand(words);
    const working = rounds(state, words, 0);
    state = working.map((value, index) => u(value + state[index]));
  }
  const out = Buffer.alloc(32);
  state.forEach((value, index) => out.writeUInt32BE(Number(value), index * 4));
  return out;
}

export function secMsGecV2(unixSeconds = Date.now() / 1000) {
  let ticks = unixSeconds + WIN_EPOCH;
  ticks -= ticks % 300;
  ticks *= 1e9 / 100;
  const data = Buffer.from(`${ticks.toFixed(0)}${TRUSTED}`, "ascii");
  const digest = sha256Digest(data);
  const keyA = (BigInt(digest.readUInt32LE(0)) | 1n);
  const keyB = (BigInt(digest.readUInt32LE(4)) | 1n);
  const factors = [u(keyA * 0x82893933n), u(keyB * 0x82893933n)];
  const terms = CS_COEFF.map(([coefficient], index) => u(coefficient * factors[index % 2]));
  const offsets = CS_COEFF.map(([, offset]) => offset);
  const words = wordsLe(Buffer.concat([Buffer.from([0]), data]));
  words.forEach((word, index) => {
    let term = word * (index % 2 === 0 ? keyA : keyB);
    let offset = rol16(word) * (index % 2 === 0 ? 0xef0569fbn : 0xc31713dbn);
    if (index === 0) {
      term += 0xf2f90b1an * factors[0];
      offset += 0x0b1a0000n;
    }
    terms.push(u(term));
    offsets.push(u(offset));
  });
  let swapAcc = 0n; let swapLast = 0n; let state = 0n; let acc = 0n;
  for (let index = 0; index < terms.length; index += 2) {
    const x = terms[index]; const y = terms[index + 1];
    let t = rol16(u(offsets[index] + x));
    let q = u(t * 0x76f50f34n);
    swapAcc = u(swapAcc + u(rol16(q) * 0xc3efea97n + q));
    t = rol16(u(offsets[index + 1] + y));
    q = u(t * 0x1881ce3cn);
    swapLast = u(rol16(q) * 0x35bd1ec9n + q);
    swapAcc = u(swapAcc + swapLast);
    state = u(state * keyA + x);
    state = u(rol16(state) * 0xcf98b111n);
    state = u(rol16(state) * 0x87085b9fn);
    state = u(rol16(state) * 0x12ceb96dn);
    state = u(rol16(state) * 0x257e1d83n);
    acc += state;
    t = u(state * keyB + y);
    t = u(rol16(t) * 0xa27416f5n);
    t = u(rol16(t) * 0xd38396ffn);
    state = u(rol16(u(rol16(t) * 0x7c932b89n)) * 0xbfa49f69n);
    acc = u(acc + state);
  }
  const left = u(swapLast ^ state);
  const right = u(swapAcc ^ acc);
  const cs64 = Buffer.alloc(8);
  cs64.writeUInt32LE(Number(left), 0);
  cs64.writeUInt32LE(Number(right), 4);
  return `${cs64.toString("hex").toUpperCase()}-${digest.toString("hex").toUpperCase()}`;
}

function wordsLe(data) {
  const padded = Buffer.concat([data, Buffer.alloc((4 - (data.length % 4)) % 4)]);
  const words = [];
  for (let offset = 0; offset < padded.length; offset += 4) words.push(BigInt(padded.readUInt32LE(offset)));
  if (words.length % 2) words.push(0n);
  return words;
}
