import { canonicalApiSearch } from '../filters.js';
import { recordPerformance } from '../performance.js';
import { validateForWorkbench } from '../semanticRenderer.js';
import type { ApiFailure, CountFacet, Facets, Overview, RefreshResult, ReviewInput, ReviewResult, SourceDescriptor, SourceEvidence, TagNode, WorkDetail, WorksPage, WorkSummary } from './types.js';

export const CANONICAL_PATHS = {
  overview: '/api/overview', facets: '/api/facets', items: '/api/items', detail: '/api/items/{objectId}/{versionId}',
  sourceEvidence: '/api/items/{objectId}/{versionId}/sources/{sourceUnitId}/evidence/{evidenceId}',
  media: '/api/media/{objectId}/{versionId}/{relativePath}', reviews: '/api/reviews', candidates: '/api/candidates', refresh: '/api/refresh',
} as const;
const arr = (value: unknown): unknown[] => Array.isArray(value) ? value : [];
const str = (value: unknown, fallback = ''): string => typeof value === 'string' ? value : fallback;
const num = (value: unknown): number => typeof value === 'number' && Number.isFinite(value) ? value : 0;
const obj = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
export const encodeObjectKey = (objectId: string, versionId: string): string => `${objectId}@${versionId}`;
export function decodeObjectKey(objectKey: string): { objectId: string; versionId: string } { const separator = objectKey.lastIndexOf('@'); if (separator <= 0 || separator === objectKey.length - 1) throw new Error('无效作品标识，应为 objectId@versionId'); return { objectId: objectKey.slice(0, separator), versionId: objectKey.slice(separator + 1) }; }
export const normalizeCount = (value: unknown): CountFacet => { const item = obj(value); const id = str(item.value, str(item.contentFormId, 'unknown')); return { id, label: str(item.label, id === 'unknown' ? '未知' : id), count: num(item.count) }; };
const counts = (value: unknown): CountFacet[] => arr(value).map(normalizeCount);
export const normalizeTag = (value: unknown): TagNode => { const item = obj(value); const ref = str(item.tagRef, 'unknown'); return { ref, label: str(item.label, ref === 'unknown' ? '未知标签' : ref), count: num(item.count), children: arr(item.children).map(normalizeTag) }; };
export const normalizeWork = (value: unknown): WorkSummary => { const item = obj(value); const objectId = str(item.objectId, 'unknown'); const versionId = str(item.versionId, 'R0'); return { objectId, objectRef: str(item.objectRef), objectKey: encodeObjectKey(objectId, versionId), title: str(item.title, '未命名内容'), contentFormId: str(item.contentFormId, 'unknown'), versionId, sourcePlatforms: arr(item.sources).map(String), tagRefs: arr(item.tagRefs).map(String), humanState: str(item.reviewState, 'pending_review'), poolState: str(item.poolState, 'offline_candidate'), businessDigest: str(item.businessDigest), textBytes: num(item.textBytes), mediaBytes: num(item.mediaBytes), captureCoverage: typeof item.captureCoverage === 'number' ? item.captureCoverage : Object.keys(obj(item.captureCoverage)).length ? obj(item.captureCoverage) : null, semanticParseCoverage: typeof item.semanticParseCoverage === 'number' ? item.semanticParseCoverage : Object.keys(obj(item.semanticParseCoverage)).length ? obj(item.semanticParseCoverage) : null, revision: str(item.revision, 'unknown'), captureMethod: str(item.captureMethod, 'unknown'), dialectVersions: arr(item.dialectVersions).map(String), semanticFingerprint: typeof item.semanticFingerprint === 'string' ? item.semanticFingerprint : null, dispositionCounts: Object.fromEntries(Object.entries(obj(item.dispositionCounts)).map(([key, value]) => [key, num(value)])), lossSeverity: str(item.lossSeverity, 'unknown'), carrierMismatch: Boolean(item.carrierMismatch), modelBatch: str(item.modelBatch, 'unknown'), reviewGate: obj(item.reviewGate) }; };
export function normalizeSource(value: unknown, index = 0): SourceDescriptor {
  const item = obj(value);
  return {
    sourceUnitId: str(item.sourceUnitId, `source-${index + 1}`),
    title: str(item.title, '未命名来源'),
    platform: str(item.platform, '未声明平台'),
    canonicalUrl: typeof item.canonicalUrl === 'string' ? item.canonicalUrl : null,
    sourceUseMode: str(item.sourceUseMode, '未声明用途'),
    rightsClue: str(item.rightsClue, '未声明权利线索'),
    fetchedAt: str(item.fetchedAt),
    evidenceState: (['available', 'missing', 'unreadable'].includes(str(item.evidenceState)) ? str(item.evidenceState) : 'missing') as SourceDescriptor['evidenceState'],
    adopted: Boolean(item.adopted),
    evidence: arr(item.evidence).map((entry, evidenceIndex) => {
      const evidence = obj(entry);
      const displayMode = str(evidence.displayMode);
      return {
        evidenceId: str(evidence.evidenceId, `evidence-${evidenceIndex + 1}`),
        kind: str(evidence.kind), mediaType: str(evidence.mediaType), sha256: str(evidence.sha256), bytes: num(evidence.bytes),
        displayMode: (['source-gfm', 'raw', 'unavailable'].includes(displayMode) ? displayMode : 'unavailable') as 'source-gfm' | 'raw' | 'unavailable',
        defaultReason: typeof evidence.defaultReason === 'string' ? evidence.defaultReason : null, readStatus: str(evidence.readStatus, 'unreadable') as import('./types.js').EvidenceDescriptor['readStatus'], revision: typeof evidence.revision === 'number' || typeof evidence.revision === 'string' ? evidence.revision : null,
      };
    }),
    defaultEvidenceId: typeof item.defaultEvidenceId === 'string' ? item.defaultEvidenceId : null,
  };
}

export function defaultEvidenceId(source?: SourceDescriptor): string {
  if (!source) return '';
  const preferred = source.evidence.find((item) => item.evidenceId === source.defaultEvidenceId && item.displayMode !== 'unavailable');
  return preferred?.evidenceId ?? source.evidence.find((item) => item.displayMode !== 'unavailable')?.evidenceId ?? '';
}
async function request<T>(path: string, operation: string, init: RequestInit = {}): Promise<T> { const started = performance.now(); let serverTiming: string | null = null; try { const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init.headers } }); serverTiming = response.headers.get('Server-Timing'); const body = await response.json().catch(() => ({})); if (!response.ok) { const errorBody = obj(obj(body).error); const error = new Error(str(errorBody.message, `请求失败 (${response.status})`)) as ApiFailure; error.code = str(errorBody.code) || undefined; error.status = response.status; error.stale = response.status === 409 && error.code === 'CONTENT_WORKBENCH.STALE_READ'; throw error; } return body as T; } finally { recordPerformance({ operation, durationMs: performance.now() - started, serverTiming, recordedAt: Date.now() }); } }
const query = (search: string): string => canonicalApiSearch(search);
export const api = {
  async overview(search = '', signal?: AbortSignal): Promise<Overview> { const response = obj(await request<unknown>(CANONICAL_PATHS.overview + query(search), 'overview', { signal })); return { readToken: str(response.readToken), staleRead: Boolean(response.stale_read), total: num(response.total), contentForms: counts(response.contentForms), reviewStates: counts(response.reviewStates), sourcePlatforms: counts(response.sources), tags: arr(response.taxonomy).map(normalizeTag), volume: { textBytes: num(obj(response.volume).textBytes), mediaBytes: num(obj(response.volume).mediaBytes) }, qualityScores: arr(response.qualityScores).map((entry) => { const score = obj(entry); return { contentFormId: str(score.contentFormId), dimension: str(score.dimension), n: num(score.n), mean: num(score.mean), distribution: Object.fromEntries(Object.entries(obj(score.distribution)).map(([key, value]) => [key, num(value)])) }; }) }; },
  async facets(search = '', signal?: AbortSignal): Promise<Facets> { const response = obj(await request<unknown>(CANONICAL_PATHS.facets + query(search), 'facets', { signal })); const facets = obj(response.facets); return { readToken: str(response.readToken) || undefined, contentForms: counts(facets.contentForms), sourcePlatforms: counts(facets.sources), humanStates: counts(facets.reviewStates), poolStates: counts(facets.poolStates), versions: counts(facets.versions), tags: arr(response.taxonomy).map(normalizeTag), captureCoverages: counts(facets.captureCoverages), semanticParseCoverages: counts(facets.semanticParseCoverages), revisions: counts(facets.revisions), captureMethods: counts(facets.captureMethods), dialectVersions: counts(facets.dialectVersions), semanticFingerprints: counts(facets.semanticFingerprints), lossSeverities: counts(facets.lossSeverities), carrierMismatches: counts(facets.carrierMismatches), modelBatches: counts(facets.modelBatches), reviewGates: counts(facets.reviewGates) }; },
  async works(search = '', signal?: AbortSignal): Promise<WorksPage> { const response = obj(await request<unknown>(CANONICAL_PATHS.items + query(search), 'items', { signal })); return { readToken: str(response.readToken) || undefined, staleRead: Boolean(response.stale_read), total: num(response.total), page: num(response.page) || 1, pageSize: num(response.pageSize) || 20, items: arr(response.items).map(normalizeWork) }; },
  async work(objectKey: string, search = '', signal?: AbortSignal): Promise<WorkDetail> { const { objectId, versionId } = decodeObjectKey(objectKey); const response = obj(await request<unknown>(`/api/items/${encodeURIComponent(objectId)}/${encodeURIComponent(versionId)}${query(search)}`, 'detail', { signal })); const summary = normalizeWork(response.item); const sourceDescriptors = arr(response.sourceDescriptors).map(normalizeSource); const semantic = validateForWorkbench(response.semanticTree); const serverValidation = obj(response.semanticValidation); const semanticValidation = semantic.validation.code === 'ok' ? semantic.validation : { code: str(serverValidation.code, semantic.validation.code), detail: str(serverValidation.detail, 'generated TypeScript validator rejected canonical semantic AST'), publishEligible: false }; return { ...summary, readToken: str(response.readToken), staleRead: Boolean(response.stale_read), body: str(response.body) || undefined, fields: obj(response.fields), media: arr(response.media).map((entry) => { const media = obj(entry); return { url: str(media.url) || undefined, mime: str(media.mime) || undefined, alt: str(media.alt) || undefined, relativePath: str(media.relativePath) || undefined }; }), sourceDescriptors, productionReview: Object.keys(obj(response.productionReview)).length ? obj(response.productionReview) : undefined, humanReview: Object.keys(obj(response.humanReview)).length ? obj(response.humanReview) : undefined, lineage: arr(response.lineage).map((entry) => obj(entry)), qualityScores: Object.fromEntries(Object.entries(obj(response.qualityScores)).map(([key, value]) => [key, num(value)])), sourceSemanticTree: validateForWorkbench(response.sourceSemanticTree).envelope, semanticTree: semantic.envelope, sourceSemanticValidation: obj(response.sourceSemanticValidation) as import('./types.js').SemanticValidation, semanticValidation, nodeDiagnostics: arr(response.nodeDiagnostics), nodeDiff: arr(response.nodeDiff) as import('./types.js').NodeDiff[], canonicalDispositions: arr(response.canonicalDispositions) as import('./types.js').AuthorityRecord[], canonicalHumanDecisions: arr(response.canonicalHumanDecisions) as import('./types.js').AuthorityRecord[], offlineSuggestion: Object.keys(obj(response.offlineSuggestion)).length ? obj(response.offlineSuggestion) as import('./types.js').AuthorityRecord : undefined, raw: response.raw }; },
  async sourceEvidence(objectKey: string, sourceUnitId: string, evidenceId: string, readToken: string, signal?: AbortSignal): Promise<SourceEvidence> { const { objectId, versionId } = decodeObjectKey(objectKey); const path = `/api/items/${encodeURIComponent(objectId)}/${encodeURIComponent(versionId)}/sources/${encodeURIComponent(sourceUnitId)}/evidence/${encodeURIComponent(evidenceId)}?${new URLSearchParams({ readToken })}`; const response = obj(await request<unknown>(path, 'sourceEvidence', { signal })); return { readToken: str(response.readToken), staleRead: Boolean(response.stale_read), sourceUnitId: str(response.sourceUnitId), evidenceId: str(response.evidenceId), kind: str(response.kind) || undefined, mediaType: str(response.mediaType) || undefined, sha256: str(response.sha256) || undefined, bytes: num(response.bytes), truncated: Boolean(response.truncated), content: str(response.content) }; },
  review(input: ReviewInput, signal?: AbortSignal): Promise<ReviewResult> { return request(CANONICAL_PATHS.reviews, 'review', { method: 'POST', body: JSON.stringify(input), signal }); },
  async refresh(signal?: AbortSignal): Promise<RefreshResult> { const response = obj(await request<unknown>(CANONICAL_PATHS.refresh, 'refresh', { method: 'POST', body: '{}', signal })); return { readToken: str(response.readToken), staleRead: Boolean(response.stale_read), refreshed: Boolean(response.refreshed) }; },
};

export { createLatestDebouncer } from '../async.js';
export { canonicalExternalUrl, isRenderableMarkdown } from '../markdown.js';
export { clearPerformanceSamples, nearestRankP95, performanceP95, performanceSamples, recordPerformance } from '../performance.js';
export { ancestorRefs, visibleTaxonomy } from '../taxonomy.js';
