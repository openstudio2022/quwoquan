import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

if (!globalThis.crypto) {
  globalThis.crypto = webcrypto;
}

import {
  PortalRuntimeLogger,
} from "../../../.test-dist/shared/observability/runtimeLogger.js";

test("portal runtime logger emits canonical, redacted browser exception", async () => {
  let request;
  const logger = new PortalRuntimeLogger({
    gatewayBaseUrl: "https://product-ops.example",
    resource: {
      sourceType: "portal",
      service: "ops-portal",
      environment: "gamma",
      "service.version": "1.2.3",
    },
    fetchImpl: async (url, init) => {
      request = { url, init };
      return new Response(JSON.stringify({ acceptedCount: 1, duplicateBatch: false }), {
        status: 200,
      });
    },
  });

  await logger.exception({
    error: new Error("Bearer secret-token user@example.com"),
  });

  assert.equal(new URL(request.url).pathname, "/ops/runtime-logs");
  assert.match(request.init.headers["Idempotency-Key"], /^[a-f0-9]{64}$/);
  const record = JSON.parse(request.init.body).records[0];
  assert.equal(record.schema, "observability.slim");
  assert.equal(record.signal, "portal.exception.browser");
  assert.equal(record.resource["service.version"], "1.2.3");
  assert.equal(record.errorCode, "PORTAL.RUNTIME.uncaught_browser_exception");
  assert.equal(record.message, "unhandled browser exception");
  assert.deepEqual(record.attributes, {
    source: "browser",
    exceptionType: "Error",
  });
  assert.equal(record.releaseId, undefined);
  assert.equal(logger.pending().length, 1);
});
