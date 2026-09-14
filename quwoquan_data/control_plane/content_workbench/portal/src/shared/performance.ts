export type PerformanceSample = {
  operation: string;
  durationMs: number;
  serverTiming: string | null;
  recordedAt: number;
};

const MAX_SAMPLES = 200;
const samples: PerformanceSample[] = [];

export function recordPerformance(sample: PerformanceSample): void {
  samples.push(sample);
  if (samples.length > MAX_SAMPLES) samples.splice(0, samples.length - MAX_SAMPLES);
}

export function performanceSamples(operation?: string): PerformanceSample[] {
  return samples.filter((sample) => !operation || sample.operation === operation).map((sample) => ({ ...sample }));
}

export function clearPerformanceSamples(): void { samples.length = 0; }

export function nearestRankP95(values: number[]): number | undefined {
  if (!values.length) return undefined;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(sorted.length * 0.95) - 1];
}

export function performanceP95(operation?: string): number | undefined {
  return nearestRankP95(performanceSamples(operation).map((sample) => sample.durationMs));
}
