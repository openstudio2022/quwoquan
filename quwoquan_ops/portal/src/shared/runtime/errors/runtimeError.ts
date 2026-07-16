import type { RuntimeErrorResponse } from "./runtimeErrorResponse.js";
import type { RuntimeFailure } from "./runtimeFailure.js";

export class RuntimeError extends Error {
  readonly failure: RuntimeFailure;
  readonly requestId?: string;
  readonly traceId?: string;

  constructor(response: RuntimeErrorResponse) {
    super(response.code);
    this.name = "RuntimeError";
    this.failure = {
      code: response.code,
      origin: response.origin,
      kind: response.kind,
      nature: response.nature,
      location: response.location,
      context: response.context,
    };
    this.requestId = response.requestId;
    this.traceId = response.traceId;
  }
}

export function isRuntimeErrorResponse(value: unknown): value is RuntimeErrorResponse {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<RuntimeErrorResponse>;
  return (
    typeof candidate.code === "string" &&
    typeof candidate.origin === "string" &&
    typeof candidate.kind === "string" &&
    typeof candidate.nature === "string" &&
    !!candidate.location &&
    typeof candidate.location === "object" &&
    !!candidate.context &&
    typeof candidate.context === "object"
  );
}

export function fallbackRuntimeErrorResponse(args: {
  code: string;
  statusCode?: number;
  requestPath?: string;
  requestId?: string;
  traceId?: string;
  cause?: unknown;
}): RuntimeErrorResponse {
  const causeMessage =
    args.cause instanceof Error
      ? args.cause.message
      : typeof args.cause === "string"
        ? args.cause
        : "";
  return {
    code: args.code,
    origin: "remoteDependency",
    kind: args.statusCode && args.statusCode >= 500 ? "unavailable" : "network",
    nature: args.statusCode && args.statusCode >= 500 ? "transient" : "permanent",
    requestId: args.requestId,
    traceId: args.traceId,
    location: {
      businessObject: "ops_control_plane",
      functionModule: "fetchJSON",
    },
    context: {
      attributes: [
        ...(args.statusCode === undefined
          ? []
          : [{ key: "statusCode", value: String(args.statusCode) }]),
        ...(args.requestPath ? [{ key: "requestPath", value: args.requestPath }] : []),
        ...(causeMessage ? [{ key: "cause", value: causeMessage }] : []),
      ],
    },
  };
}

export function coerceRuntimeError(error: unknown): RuntimeError {
  if (error instanceof RuntimeError) return error;
  return new RuntimeError(
    fallbackRuntimeErrorResponse({
      code: "OPS.SYSTEM.unknown_error",
      cause: error,
    }),
  );
}
