import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  RuntimeError,
  coerceRuntimeError,
  fallbackRuntimeErrorResponse,
} from "../../../../.test-dist/shared/runtime/errors/runtimeError.js";
import { RuntimeErrorBadge } from "../../../../.test-dist/shared/runtime/errors/RuntimeErrorBadge.js";

test("coerceRuntimeError preserves RuntimeError instances", () => {
  const runtimeError = new RuntimeError(
    fallbackRuntimeErrorResponse({
      code: "OPS.CONTRACT.invalid_response",
      statusCode: 502,
      requestPath: "/v1/control-plane/platform/audits",
      requestId: "req-1",
      traceId: "trace-1",
      cause: new Error("bad json"),
    }),
  );

  assert.equal(coerceRuntimeError(runtimeError), runtimeError);
  assert.equal(runtimeError.failure.code, "OPS.CONTRACT.invalid_response");
  assert.equal(runtimeError.requestId, "req-1");
  assert.equal(runtimeError.traceId, "trace-1");
  assert.deepEqual(runtimeError.failure.context.attributes.at(-1), {
    key: "cause",
    value: "bad json",
  });
});

test("RuntimeErrorBadge renders structured error identifiers", () => {
  const error = new RuntimeError(
    fallbackRuntimeErrorResponse({
      code: "OPS.SYSTEM.unknown_error",
      requestId: "req-2",
      traceId: "trace-2",
    }),
  );

  const html = renderToStaticMarkup(React.createElement(RuntimeErrorBadge, { error }));

  assert.match(html, /OPS\.SYSTEM\.unknown_error/);
  assert.match(html, /ops_control_plane\/fetchJSON/);
  assert.match(html, /trace=trace-2/);
  assert.match(html, /request=req-2/);
});

