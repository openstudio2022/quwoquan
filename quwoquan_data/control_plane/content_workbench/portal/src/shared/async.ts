export type ScheduledTask<T> = (signal: AbortSignal) => Promise<T>;

export function createLatestDebouncer<T>(delayMs: number, commit: (value: T) => void, fail?: (reason: unknown) => void) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  let sequence = 0;
  return {
    schedule(task: ScheduledTask<T>) {
      sequence += 1;
      const current = sequence;
      if (timer) clearTimeout(timer);
      controller?.abort();
      controller = new AbortController();
      const signal = controller.signal;
      timer = setTimeout(async () => {
        try {
          const value = await task(signal);
          if (!signal.aborted && current === sequence) commit(value);
        } catch (reason) {
          if (!signal.aborted && current === sequence) fail?.(reason);
        }
      }, delayMs);
    },
    cancel() {
      sequence += 1;
      if (timer) clearTimeout(timer);
      controller?.abort();
    },
  };
}
