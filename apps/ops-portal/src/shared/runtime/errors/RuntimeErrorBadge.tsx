import type { RuntimeError } from "./runtimeError.js";

export function RuntimeErrorBadge({ error }: { error: RuntimeError | null }) {
  if (!error) return null;
  const location = error.failure.location;
  const locationText = [location.businessObject, location.functionModule]
    .filter(Boolean)
    .join("/");
  return (
    <span className="badge badge--danger">
      {error.failure.code}
      {locationText ? ` · ${locationText}` : ""}
      {error.traceId ? ` · trace=${error.traceId}` : ""}
      {error.requestId ? ` · request=${error.requestId}` : ""}
    </span>
  );
}
