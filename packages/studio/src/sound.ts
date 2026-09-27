/** Color is a voice's vibe, chosen from the seed. The shape comes from the decoded WAV. */

export const PALETTES = {
  sunset: { label: "Sunset", text: "#ac4b2d", soft: "#fff0e2", colors: ["#9b557d", "#e28b68", "#ffd091"] },
  prism: { label: "Prism", text: "#8e476d", soft: "#fbeafa", colors: ["#9a6cf0", "#548cf0", "#37c5df", "#77d4a4", "#f2cf6e", "#ed8b62", "#eb7185"] },
  silk: { label: "Silk", text: "#655e5b", soft: "#f0ece9", colors: ["#8c8d9b", "#d6d4d0", "#a8a6a9"] },
  aura: { label: "Aura", text: "#357c91", soft: "#e3f6f8", colors: ["#5c83c6", "#61d0d5", "#b0e8db"] },
} as const;

export type PaletteName = keyof typeof PALETTES;

const ORDER: PaletteName[] = ["sunset", "prism", "silk", "aura"];

export function paletteFor(seed: number | null | undefined): PaletteName {
  const n = seed == null || Number.isNaN(seed) ? 0 : Math.abs(Math.trunc(seed));
  return ORDER[n % ORDER.length] ?? "sunset";
}

export async function readEnvelope(blob: Blob, buckets = 160): Promise<number[]> {
  const copy = await blob.arrayBuffer();
  const context = new AudioContext();
  try {
    const audio = await context.decodeAudioData(copy);
    const channel = audio.getChannelData(0);
    const size = Math.max(1, Math.floor(channel.length / buckets));
    const levels: number[] = [];
    for (let i = 0; i < buckets; i++) {
      let sum = 0;
      const start = i * size;
      const end = Math.min(start + size, channel.length);
      for (let j = start; j < end; j++) {
        const sample = channel[j] ?? 0;
        sum += sample * sample;
      }
      levels.push(Math.sqrt(sum / Math.max(1, end - start)));
    }
    const loudest = Math.max(...levels, 0.0001);
    return levels.map((level) => level / loudest);
  } finally {
    await context.close();
  }
}

function resample(values: number[], points: number): number[] {
  if (values.length === 0) return Array.from({ length: points }, () => 0);
  const next: number[] = [];
  for (let index = 0; index < points; index++) {
    const start = Math.floor((index * values.length) / points);
    const end = Math.max(start + 1, Math.floor(((index + 1) * values.length) / points));
    let sum = 0;
    let count = 0;
    for (let cursor = start; cursor < end && cursor < values.length; cursor++) {
      sum += values[cursor] ?? 0;
      count++;
    }
    next.push(count ? sum / count : 0);
  }
  // Speech is fairly even, so rank the stretches from quietest to loudest.
  // Louder stretches always get the taller hump, and the whole band height is used.
  const order = next.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value);
  const ranked = new Array<number>(next.length).fill(0.5);
  order.forEach((entry, rank) => {
    ranked[entry.index] = order.length > 1 ? rank / (order.length - 1) : 0.5;
  });
  return ranked;
}

function soften(values: number[]): number[] {
  return values.map((value, index) => {
    const before = values[index - 1] ?? value;
    const after = values[index + 1] ?? value;
    return before * 0.15 + value * 0.7 + after * 0.15;
  });
}

function stretch(values: number[]): number[] {
  const low = Math.min(...values);
  const span = Math.max(...values) - low;
  return span < 0.0001 ? values : values.map((value) => (value - low) / span);
}

/** Catmull-Rom spline through the knots: continuous in position and slope. */
function spline(knots: number[], position: number): number {
  const last = knots.length - 1;
  const index = Math.min(last - 1, Math.max(0, Math.floor(position)));
  const t = Math.min(1, Math.max(0, position - index));
  const p0 = knots[Math.max(0, index - 1)] ?? 0;
  const p1 = knots[index] ?? 0;
  const p2 = knots[Math.min(last, index + 1)] ?? p1;
  const p3 = knots[Math.min(last, index + 2)] ?? p2;
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
}

export interface WaveGeometry {
  band: string;
  contours: { d: string; strong: boolean }[];
  grid: number[];
}

const DEPTHS = [1, 0.79, 0.58, 0.37];

/**
 * Drawn in real pixels. Knots are spaced by distance, so a narrow card and a wide
 * reference clip keep the same wave height and curve proportions.
 */
export function waveGeometry(peaks: number[] | null, width: number, height: number, motion = 0): WaveGeometry {
  const center = height / 2;
  const reach = Math.min(32, height * 0.35);
  const floor = peaks ? 6 : 3;
  // One knot per ~110px keeps the humps as wide as the prototype's sine at any card size.
  const knots = peaks ? stretch(soften(resample(peaks, Math.max(4, Math.round(width / 110) + 1)))) : [0.5, 0.5, 0.5, 0.5];
  const envelope = (x: number) => Math.max(0, Math.min(1, spline(knots, (x / width) * (knots.length - 1))));
  const sway = (x: number) => (motion ? 1 + 0.09 * Math.sin((x * Math.PI * 2) / 220 + motion) : 1);
  const amplitude = (x: number) => (floor + reach * envelope(x)) * sway(x);
  const pointCount = Math.max(33, Math.ceil(width / 4));
  const xs = Array.from({ length: pointCount }, (_, i) => (i * width) / (pointCount - 1));
  const line = (fn: (x: number) => number) => xs.map((x, i) => `${i ? "L" : "M"}${x.toFixed(1)} ${fn(x).toFixed(1)}`).join(" ");
  const top = line((x) => center - amplitude(x));
  const band = `${top} ${xs
    .slice()
    .reverse()
    .map((x) => `L${x.toFixed(1)} ${(center + amplitude(x)).toFixed(1)}`)
    .join(" ")} Z`;
  const contours = [-1, 1].flatMap((side) =>
    DEPTHS.map((depth, index) => ({ d: line((x) => center + side * amplitude(x) * depth), strong: index === 0 })),
  );
  const columns = Math.floor(width / 56);
  const grid = Array.from({ length: columns }, (_, i) => ((i + 1) * width) / (columns + 1));
  return { band, contours, grid };
}

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
