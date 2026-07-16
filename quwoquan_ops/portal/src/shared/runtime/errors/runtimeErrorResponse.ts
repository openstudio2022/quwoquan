import type { RuntimeFailure } from "./runtimeFailure.js";

export interface RuntimeErrorResponse extends RuntimeFailure {
  requestId?: string;
  traceId?: string;
  userMessage?: string;
  debugMessage?: string;
}
