import { runtimeLogCatalog } from '../../generated/observability/runtimeLogCatalog.generated.js';

type RuntimeLogKind = (typeof runtimeLogCatalog.logKinds)[number];
type RuntimeLogSeverity = (typeof runtimeLogCatalog.severityLevels)[number];
type RuntimeLogSignal = (typeof runtimeLogCatalog.signals)[number];

export interface PortalRuntimeLogResource {
  sourceType: 'portal';
  service: string;
  environment: string;
  component?: string;
  appVersion?: string;
  'service.version'?: string;
}

export interface PortalRuntimeLogCorrelation {
  requestId?: string;
  traceId?: string;
  spanId?: string;
  operationId?: string;
  pageName?: string;
  surfaceId?: string;
  executionId?: string;
  workPackageId?: string;
  environmentRunId?: string;
}

export interface PortalRuntimeLogRecord {
  schema: typeof runtimeLogCatalog.schema;
  recordId: string;
  occurredAt: string;
  observedAt: string;
  logKind: RuntimeLogKind;
  severity: RuntimeLogSeverity;
  signal: RuntimeLogSignal;
  message: string;
  resource: PortalRuntimeLogResource;
  correlation?: PortalRuntimeLogCorrelation;
  errorCode?: string;
  fingerprint?: string;
  attributes?: Record<string, string>;
}

export interface PortalRuntimeLoggerOptions {
  gatewayBaseUrl: string;
  resource: PortalRuntimeLogResource;
  fetchImpl?: typeof fetch;
  now?: () => Date;
  remoteEnabled?: boolean;
}

/// Portal 唯一浏览器运行日志入口。它只表达登记 signal 的结构化事实，alpha 留存在
/// 内存环形缓冲，beta/gamma/prod 通过统一 Product Ops ingestion 上报。
export class PortalRuntimeLogger {
  readonly #gatewayBaseUrl: string;
  readonly #resource: PortalRuntimeLogResource;
  readonly #fetch: typeof fetch;
  readonly #now: () => Date;
  readonly #remoteEnabled: boolean;
  readonly #records: PortalRuntimeLogRecord[] = [];

  constructor(options: PortalRuntimeLoggerOptions) {
    this.#gatewayBaseUrl = options.gatewayBaseUrl.replace(/\/+$/, '');
    this.#resource = options.resource;
    this.#fetch = options.fetchImpl ?? fetch;
    this.#now = options.now ?? (() => new Date());
    this.#remoteEnabled = options.remoteEnabled ?? options.resource.environment !== 'alpha';
  }

  pending(): readonly PortalRuntimeLogRecord[] {
    return this.#records;
  }

  async exception(options: {
    error: unknown;
    correlation?: PortalRuntimeLogCorrelation;
  }): Promise<void> {
    const type = options.error instanceof Error ? options.error.name || 'Error' : typeof options.error;
    const fingerprint = await sha256Text(
      `${type}:${options.error instanceof Error ? options.error.message : String(options.error)}`,
    );
    const record = this.#record({
      logKind: 'exception',
      severity: 'ERROR',
      signal: 'portal.exception.browser',
      message: 'unhandled browser exception',
      correlation: options.correlation,
      errorCode: runtimeLogCatalog.failureCodes.portal_uncaught_browser,
      fingerprint,
      attributes: {
        source: 'browser',
        exceptionType: type,
      },
    });
    this.#append(record);
    if (this.#remoteEnabled) {
      await this.#send(record);
    }
  }

  #record(input: Omit<PortalRuntimeLogRecord, 'schema' | 'recordId' | 'occurredAt' | 'observedAt' | 'resource'>): PortalRuntimeLogRecord {
    const contract = runtimeLogCatalog.signalRegistry[input.signal];
    if (!contract || contract.logKind !== input.logKind) {
      throw new Error(`unregistered portal runtime signal: ${input.signal}`);
    }
    const {
      attributes: inputAttributes,
      correlation: inputCorrelation,
      ...base
    } = input;
    const attributes = Object.fromEntries(
      Object.entries(inputAttributes ?? {}).filter(
        ([key]) => (contract.attributeAllowlist as readonly string[]).includes(key),
      ),
    );
    const correlation = Object.fromEntries(
      Object.entries(inputCorrelation ?? {}).filter(
        ([key, value]) => value && (contract.correlationKeys as readonly string[]).includes(key),
      ),
    ) as PortalRuntimeLogCorrelation;
    const timestamp = this.#now().toISOString();
    return {
      schema: runtimeLogCatalog.schema,
      recordId: `r.${Date.now().toString(36)}.${randomToken()}`,
      occurredAt: timestamp,
      observedAt: timestamp,
      ...base,
      message: bound(redact(base.message), runtimeLogCatalog.maxMessageBytes),
      resource: this.#resource,
      ...(Object.keys(correlation).length > 0 ? { correlation } : {}),
      ...(Object.keys(attributes).length > 0 ? { attributes } : {}),
    };
  }

  #append(record: PortalRuntimeLogRecord): void {
    this.#records.push(record);
    if (this.#records.length > 100) {
      this.#records.splice(0, this.#records.length - 100);
    }
  }

  async #send(record: PortalRuntimeLogRecord): Promise<void> {
    if (!this.#gatewayBaseUrl) {
      return;
    }
    const body = canonicalJson({ records: [record] });
    const response = await this.#fetch(`${this.#gatewayBaseUrl}/ops/runtime-logs`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': await sha256Text(body),
      },
      body,
    });
    if (!response.ok) {
      throw new Error(`runtime diagnostic ingestion failed: ${response.status}`);
    }
  }
}

export function installPortalRuntimeDiagnostics(logger: PortalRuntimeLogger): () => void {
  const onError = (event: ErrorEvent): void => {
    void logger.exception({ error: event.error ?? new Error(event.message) }).catch(() => undefined);
  };
  const onUnhandledRejection = (event: PromiseRejectionEvent): void => {
    void logger.exception({ error: event.reason }).catch(() => undefined);
  };
  globalThis.addEventListener('error', onError);
  globalThis.addEventListener('unhandledrejection', onUnhandledRejection);
  return () => {
    globalThis.removeEventListener('error', onError);
    globalThis.removeEventListener('unhandledrejection', onUnhandledRejection);
  };
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalize);
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, child]) => [key, canonicalize(child)]),
    );
  }
  return value;
}

function redact(value: string): string {
  return value
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, 'Bearer ***')
    .replace(/(access_token|token|authcode|authorization|signature|secret)=([^&#\s]+)/gi, '$1=***')
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '***');
}

function bound(value: string, maxBytes: number): string {
  const encoder = new TextEncoder();
  if (encoder.encode(value).length <= maxBytes) {
    return value;
  }
  let result = value;
  while (result && encoder.encode(`${result}…`).length > maxBytes) {
    result = result.slice(0, -1);
  }
  return `${result}…`;
}

function randomToken(): string {
  const bytes = new Uint8Array(8);
  globalThis.crypto.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, '0')).join('');
}

async function sha256Text(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}
