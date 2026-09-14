export type WorkbenchFilters = {
  contentFormIds: string[];
  sourcePlatforms: string[];
  tagRefs: string[];
  tagMatch: 'direct' | 'subtree';
  versions: string[];
  humanStates: string[];
  poolStates: string[];
  captureCoverages: string[]; semanticParseCoverages: string[]; revisions: string[]; captureMethods: string[]; dialectVersions: string[];
  semanticFingerprints: string[]; lossSeverities: string[]; carrierMismatches: string[]; modelBatches: string[]; reviewGates: string[];
  query?: string;
  sort: string;
  page: number;
  pageSize: number;
  readToken?: string;
};

const list = (params: URLSearchParams, key: string): string[] =>
  params.getAll(key).flatMap((value) => value.split(',')).filter(Boolean);

export function parseFilters(search: string): WorkbenchFilters {
  const params = new URLSearchParams(search);
  const legacyTag = params.get('tagRef');
  return {
    contentFormIds: list(params, 'contentFormIds'),
    sourcePlatforms: list(params, 'sourcePlatforms'),
    tagRefs: list(params, 'tagRefs').concat(legacyTag ? [legacyTag] : []),
    tagMatch: params.get('tagMatch') === 'direct' ? 'direct' : 'subtree',
    versions: list(params, 'versions'),
    humanStates: list(params, 'humanStates'),
    poolStates: list(params, 'poolStates'),
    captureCoverages: list(params, 'captureCoverages'), semanticParseCoverages: list(params, 'semanticParseCoverages'), revisions: list(params, 'revisions'), captureMethods: list(params, 'captureMethods'), dialectVersions: list(params, 'dialectVersions'),
    semanticFingerprints: list(params, 'semanticFingerprints'), lossSeverities: list(params, 'lossSeverities'), carrierMismatches: list(params, 'carrierMismatches'), modelBatches: list(params, 'modelBatches'), reviewGates: list(params, 'reviewGates'),
    query: params.get('query') || undefined,
    sort: params.get('sort') || 'updated_desc',
    page: Math.max(1, Number(params.get('page')) || 1),
    pageSize: Math.min(100, Math.max(1, Number(params.get('pageSize')) || 20)),
    readToken: params.get('readToken') || undefined,
  };
}

export function serializeFilters(filters: WorkbenchFilters): string {
  const params = new URLSearchParams();
  for (const [key, values] of [
    ['contentFormIds', filters.contentFormIds],
    ['sourcePlatforms', filters.sourcePlatforms],
    ['tagRefs', filters.tagRefs],
    ['versions', filters.versions],
    ['humanStates', filters.humanStates],
    ['poolStates', filters.poolStates],
    ['captureCoverages', filters.captureCoverages], ['semanticParseCoverages', filters.semanticParseCoverages], ['revisions', filters.revisions], ['captureMethods', filters.captureMethods], ['dialectVersions', filters.dialectVersions], ['semanticFingerprints', filters.semanticFingerprints], ['lossSeverities', filters.lossSeverities], ['carrierMismatches', filters.carrierMismatches], ['modelBatches', filters.modelBatches], ['reviewGates', filters.reviewGates],
  ] as const) {
    values.forEach((value) => params.append(key, value));
  }
  for (const [key, value] of [
    ['tagMatch', filters.tagMatch],
    ['query', filters.query],
    ['sort', filters.sort],
    ['readToken', filters.readToken],
  ] as const) {
    if (value) params.set(key, value);
  }
  params.set('page', String(filters.page));
  params.set('pageSize', String(filters.pageSize));
  return `?${params.toString()}`;
}

export function canonicalApiSearch(search: string): string {
  const filters = parseFilters(search);
  const params = new URLSearchParams();
  for (const [key, values] of [
    ['contentFormIds', filters.contentFormIds],
    ['sources', filters.sourcePlatforms],
    ['tagRefs', filters.tagRefs],
    ['versions', filters.versions],
    ['reviewStates', filters.humanStates],
    ['poolStates', filters.poolStates],
    ['captureCoverages', filters.captureCoverages], ['semanticParseCoverages', filters.semanticParseCoverages], ['revisions', filters.revisions], ['captureMethods', filters.captureMethods], ['dialectVersions', filters.dialectVersions], ['semanticFingerprints', filters.semanticFingerprints], ['lossSeverities', filters.lossSeverities], ['carrierMismatches', filters.carrierMismatches], ['modelBatches', filters.modelBatches], ['reviewGates', filters.reviewGates],
  ] as const) {
    values.forEach((value) => params.append(key, value));
  }
  for (const [key, value] of [
    ['tagMatch', filters.tagMatch],
    ['query', filters.query],
    ['sort', filters.sort],
    ['readToken', filters.readToken],
  ] as const) {
    if (value) params.set(key, value);
  }
  params.set('page', String(filters.page));
  params.set('pageSize', String(filters.pageSize));
  const value = params.toString();
  return value ? `?${value}` : '';
}
