// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-005.t1
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { CANONICAL_PATHS, api, ancestorRefs, canonicalExternalUrl, clearPerformanceSamples, createLatestDebouncer, decodeObjectKey, defaultEvidenceId, encodeObjectKey, isRenderableMarkdown, nearestRankP95, normalizeSource, normalizeTag, normalizeWork, performanceP95, performanceSamples, recordPerformance, visibleTaxonomy } from '../.test-dist/shared/api/client.js';
import { canonicalApiSearch, parseFilters, serializeFilters } from '../.test-dist/shared/filters.js';
import { rendererFor, validateReview } from '../.test-dist/shared/renderers.js';
import { parseCanonicalMarkdown, serializeEnvelope } from '../.test-dist/shared/canonicalSemanticMarkdown.js';

test('canonical operations 与 client path 完全一致', async () => {
  const operations = JSON.parse(await readFile(new URL('../../schema/governance/content_workbench/operations.json', import.meta.url)));
  const declared = Object.fromEntries(operations.operations.map((operation) => [operation.operationId, operation.path]));
  assert.equal(CANONICAL_PATHS.overview, declared.overview);
  assert.equal(CANONICAL_PATHS.facets, declared.facets);
  assert.equal(CANONICAL_PATHS.items, declared.list);
  assert.equal(CANONICAL_PATHS.detail, declared.detail);
  assert.equal(CANONICAL_PATHS.media, declared.media);
  assert.equal(CANONICAL_PATHS.reviews, declared.saveReview);
  assert.equal(CANONICAL_PATHS.candidates, declared.registerCandidate);
});

test('canonical item 字段显式映射且 objectKey 可逆', () => {
  const work = normalizeWork({ objectId: 'a@b', objectRef: 'posts/x', versionId: 'R1', businessDigest: 'sha256:x', sources: ['platform'], reviewState: 'qualified', poolState: 'offline_candidate' });
  assert.equal(work.objectKey, 'a@b@R1');
  assert.deepEqual(decodeObjectKey(work.objectKey), { objectId: 'a@b', versionId: 'R1' });
  assert.equal(encodeObjectKey('id', 'R0'), 'id@R0');
  assert.equal(normalizeTag({ tagRef: 'root', children: [{ tagRef: 'leaf' }] }).children.length, 1);
});

test('前端 URL 名称转换为 canonical query 名称', () => {
  const filters = parseFilters('?contentFormIds=image&sourcePlatforms=weibo&tagRefs=x&tagMatch=direct&versions=R1&humanStates=qualified&poolStates=offline_candidate&query=q&sort=title_asc&page=3&pageSize=50&readToken=sha256:abc');
  assert.equal(parseFilters(serializeFilters(filters)).page, 3);
  const canonical = new URLSearchParams(canonicalApiSearch(serializeFilters(filters)));
  assert.deepEqual(canonical.getAll('sources'), ['weibo']);
  assert.deepEqual(canonical.getAll('reviewStates'), ['qualified']);
  assert.deepEqual(canonical.getAll('tagRefs'), ['x']);
  assert.deepEqual(canonical.getAll('versions'), ['R1']);
  assert.equal(canonical.has('sourcePlatforms'), false);
  assert.equal(canonical.has('humanStates'), false);
});

test('未知 renderer fallback 与 review validation', () => {
  assert.equal(rendererFor('homepage'), 'homepage');
  assert.equal(rendererFor('brand-new-form'), 'unknown');
  assert.equal(validateReview({ state: 'qualified' }).length, 0);
  assert.equal(validateReview({ state: 'unqualified' }).length, 2);
  assert.equal(validateReview({ state: 'unqualified', changes: '补证据', targetState: 'R1' }).length, 0);
});


test('300ms debounce 会 abort 旧任务且 latest wins', async () => {
  const committed = []; let firstSignal;
  const runner = createLatestDebouncer(10, (value) => committed.push(value));
  runner.schedule(async (signal) => { firstSignal = signal; await new Promise((resolve) => setTimeout(resolve, 40)); return '旧'; });
  await new Promise((resolve) => setTimeout(resolve, 15)); runner.schedule(async () => '新');
  await new Promise((resolve) => setTimeout(resolve, 30)); assert.equal(firstSignal.aborted, true); assert.deepEqual(committed, ['新']); runner.cancel();
});

test('标签树默认只挂根，选中叶子展开祖先分支', () => {
  const tree = [{ ref: 'root', label: '根', count: 1, children: [{ ref: 'branch', label: '枝', count: 1, children: [{ ref: 'leaf', label: '叶', count: 1, children: [] }] }] }];
  assert.equal(visibleTaxonomy(tree, [], []).at(0).children.length, 0);
  assert.deepEqual([...ancestorRefs(tree, ['leaf'])].sort(), ['branch', 'root']);
  assert.equal(visibleTaxonomy(tree, [], ['leaf']).at(0).children.at(0).children.at(0).ref, 'leaf');
});

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
test('来源 canonical URL 仅允许 http/https，Markdown 能力识别 GFM 文本', () => {
  assert.match(canonicalExternalUrl('https://example.com/a'), /^https:/);
  assert.equal(canonicalExternalUrl('javascript:alert(1)'), undefined);
  assert.equal(canonicalExternalUrl('data:text/html,x'), undefined);
  assert.equal(isRenderableMarkdown('text/markdown'), true);
  assert.equal(isRenderableMarkdown('text/plain', 'raw'), false);
});

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-006.t2
test('performance 样本有界且 nearest-rank p95 正确', () => {
  clearPerformanceSamples(); assert.equal(nearestRankP95([1, 2, 3, 4, 100]), 100);
  for (let index = 0; index < 205; index += 1) recordPerformance({ operation: 'list', durationMs: index, serverTiming: 'db;dur=1', recordedAt: index });
  assert.equal(performanceSamples().length, 200); assert.equal(performanceP95('list'), 194);
});

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
test('来源正文保持 lazy：只有 sourceEvidence canonical operation 承载正文 route', () => {
  assert.match(CANONICAL_PATHS.sourceEvidence, /sources\/\{sourceUnitId\}\/evidence\/\{evidenceId\}/);
  assert.equal(CANONICAL_PATHS.refresh, '/api/refresh');
});

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
test('Markdown SSR 支持 GFM 且危险协议不生成可点击链接', () => {
  const markdown = '# 标题\n\n- 列表\n\n> 引用\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n`code` [安全](https://example.com) [危险](javascript:alert(1))';
  const html = renderToStaticMarkup(React.createElement(ReactMarkdown, {
    remarkPlugins: [remarkGfm],
    skipHtml: true,
    components: { a: ({ href, children }) => { const safe = canonicalExternalUrl(href); return safe ? React.createElement('a', { href: safe, target: '_blank', rel: 'noopener noreferrer' }, children) : React.createElement('span', null, children); } },
    children: markdown,
  }));
  assert.match(html, /<h1>标题<\/h1>/);
  assert.match(html, /<table>/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /target="_blank" rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /href="javascript:/);
});


// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
test('canonical sourceDescriptor 严格映射并选择默认可显示证据', () => {
  const source = normalizeSource({
    sourceUnitId: 's1', title: '来源标题', platform: 'wikipedia', canonicalUrl: 'https://example.com/source',
    sourceUseMode: 'homepage_primary', rightsClue: 'CC BY-SA', fetchedAt: '2026-09-14T00:00:00Z',
    evidenceState: 'available', adopted: true, defaultEvidenceId: 'raw-disabled', evidence: [
      { evidenceId: 'raw-disabled', kind: 'raw', mediaType: 'text/plain', sha256: 'sha256:a', bytes: 1, displayMode: 'unavailable', defaultReason: '不可读' },
      { evidenceId: 'markdown', kind: 'markdown', mediaType: 'text/markdown', sha256: 'sha256:b', bytes: 2, displayMode: 'source-gfm', defaultReason: null },
    ],
    url: 'https://legacy.example', license: 'legacy', facts: { legacy: true },
  });
  assert.deepEqual({ title: source.title, canonicalUrl: source.canonicalUrl, sourceUseMode: source.sourceUseMode, rightsClue: source.rightsClue, fetchedAt: source.fetchedAt }, {
    title: '来源标题', canonicalUrl: 'https://example.com/source', sourceUseMode: 'homepage_primary', rightsClue: 'CC BY-SA', fetchedAt: '2026-09-14T00:00:00Z',
  });
  assert.equal('url' in source, false);
  assert.equal('facts' in source, false);
  assert.equal(source.evidence[0].displayMode, 'unavailable');
  assert.equal(source.evidence[0].defaultReason, '不可读');
  assert.equal(defaultEvidenceId(source), 'markdown');
});

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
test('默认证据命中时优先使用，全部 unavailable 时无选择', () => {
  const source = normalizeSource({ sourceUnitId: 's1', title: 't', platform: 'p', canonicalUrl: null, sourceUseMode: 'u', rightsClue: 'r', fetchedAt: 'f', evidenceState: 'missing', adopted: true, defaultEvidenceId: 'second', evidence: [
    { evidenceId: 'first', kind: 'raw', mediaType: 'text/plain', sha256: 'a', bytes: 1, displayMode: 'raw', defaultReason: null },
    { evidenceId: 'second', kind: 'markdown', mediaType: 'text/markdown', sha256: 'b', bytes: 2, displayMode: 'source-gfm', defaultReason: null },
  ] });
  assert.equal(defaultEvidenceId(source), 'second');
  assert.equal(defaultEvidenceId({ ...source, evidence: source.evidence.map((item) => ({ ...item, displayMode: 'unavailable' })) }), '');
});

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-006.t3
test('detail 只读 sourceDescriptors，refresh 仅返回 canonical 字段', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url) => {
      if (String(url) === '/api/refresh') return new Response(JSON.stringify({ readToken: 'token-new', stale_read: false, refreshed: true, status: 'legacy' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      return new Response(JSON.stringify({ readToken: 'token', stale_read: false, item: { objectId: 'id', versionId: 'R0' }, fields: {}, media: [], sourceFacts: [{ sourceUnitId: 'legacy' }], sourceDescriptors: [], lineage: [], qualityScores: {} }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    };
    const detail = await api.work('id@R0');
    assert.deepEqual(detail.sourceDescriptors, []);
    const refreshed = await api.refresh();
    assert.deepEqual(refreshed, { readToken: 'token-new', staleRead: false, refreshed: true });
    assert.equal('status' in refreshed, false);
    assert.equal('durationMs' in refreshed, false);
  } finally { globalThis.fetch = originalFetch; }
});

// 保真治理分面必须一比一转为 canonical query；不建立第二套筛选语义。
test('capture semantic diagnostics 分面沿同一 URL 查询轨', () => {
  const filters = parseFilters('?captureMethods=wikipedia_parsoid&lossSeverities=medium&carrierMismatches=false&modelBatches=batch-7&reviewGates=%7B%22decision%22%3A%22acceptWithDiagnostics%22%7D');
  const canonical = new URLSearchParams(canonicalApiSearch(serializeFilters(filters)));
  assert.equal(canonical.get('captureMethods'), 'wikipedia_parsoid');
  assert.equal(canonical.get('lossSeverities'), 'medium');
  assert.equal(canonical.get('carrierMismatches'), 'false');
  assert.equal(canonical.get('modelBatches'), 'batch-7');
  assert.equal(canonical.get('reviewGates'), '{"decision":"acceptWithDiagnostics"}');
});

import { CAPABILITY_IDS, NODE_REGISTRY } from '../.test-dist/generated/semanticDocument.js';
import { validateForWorkbench } from '../.test-dist/shared/semanticRenderer.js';

function semanticFixture({ schemaVersion = '1.0.0', extraCapability, nodeKind = 'paragraph' } = {}) {
  const capabilities = ['parse.markdown', 'parse.html', 'serialize.markdown', 'render.app', 'render.web', 'render.workbench', 'author.editContent'];
  if (extraCapability) capabilities.push(extraCapability);
  const sourceAnchor = { origin: 'source-gfm', start: 0, end: 4, selector: 'p:1' };
  return { schemaVersion, dialectVersion: '1.0.0', canonicalizationVersion: '1.0.0', offsetEncoding: 'unicode_scalar_value', nodes: [{ nodeId: 'n1', kind: nodeKind, disposition: 'normalized', policyVersion: 'p1', requiredCapabilities: capabilities, losses: [], semanticFingerprint: 'node-fp', sourceAnchor, attributes: { plainText: '正文' }, inlines: [] }], requiredCapabilities: capabilities, assets: {}, sourceMap: { n1: sourceAnchor }, policyVersion: 'p1', losses: [], semanticFingerprint: 'document-fp', canonicalDigest: 'digest' };
}
test('Portal 使用 generated registry 与 validator 并保留节点顺序文本指纹', () => {
  assert.equal(NODE_REGISTRY.paragraph.status, 'formal');
  assert.equal(CAPABILITY_IDS.has('render.workbench'), true);
  const result = validateForWorkbench(semanticFixture());
  assert.equal(result.validation.code, 'ok');
  assert.equal(result.envelope.nodes[0].kind, 'paragraph');
  assert.equal(result.envelope.nodes[0].attributes.plainText, '正文');
  assert.equal(result.envelope.nodes[0].semanticFingerprint, 'node-fp');
});
test('Portal 对未知版本、capability、experimental 节点 fail closed', () => {
  assert.equal(validateForWorkbench(semanticFixture({ schemaVersion: '2.0.0' })).validation.code, 'SEMANTIC_DOCUMENT.INCOMPATIBLE.SCHEMA_MAJOR');
  assert.equal(validateForWorkbench(semanticFixture({ extraCapability: 'unknown.capability' })).validation.code, 'SEMANTIC_DOCUMENT.CAPABILITY.MISSING');
  assert.equal(validateForWorkbench(semanticFixture({ nodeKind: 'interactiveWidget' })).validation.code, 'SEMANTIC_DOCUMENT.EXPERIMENTAL.PUBLISH_FORBIDDEN');
});

test('API detail 到 TypeScript validator 保持 canonical AST 顺序与指纹', async () => {
  const originalFetch = globalThis.fetch;
  const semantic = semanticFixture();
  semantic.nodes.unshift({ ...semantic.nodes[0], nodeId: 'h1', kind: 'heading', semanticFingerprint: 'heading-fp', requiredCapabilities: [...semantic.nodes[0].requiredCapabilities, 'author.editStructure'], attributes: { plainText: '标题', level: 2 } });
  semantic.requiredCapabilities.push('author.editStructure');
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ readToken: 'token', stale_read: false, item: { objectId: 'id', versionId: 'R0' }, fields: {}, media: [], sourceDescriptors: [], lineage: [], qualityScores: {}, semanticTree: semantic, semanticValidation: { code: 'ok', detail: '', publishEligible: true }, nodeDiagnostics: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    const detail = await api.work('id@R0');
    assert.equal(detail.semanticValidation.code, 'ok');
    assert.deepEqual(detail.semanticTree.nodes.map((node) => [node.kind, node.attributes.plainText, node.semanticFingerprint]), [['heading', '标题', 'heading-fp'], ['paragraph', '正文', 'node-fp']]);
    assert.equal(detail.semanticTree.semanticFingerprint, 'document-fp');
  } finally { globalThis.fetch = originalFetch; }
});


// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/content-pool-workbench/spec.md#gwt-003.t1
test('detail 保留 typed node diff 与 canonical/offline authority', async () => {
  const originalFetch = globalThis.fetch; const semantic = semanticFixture();
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ readToken:'token', stale_read:false, item:{objectId:'id',versionId:'R0'}, fields:{}, media:[], sourceDescriptors:[], lineage:[], qualityScores:{}, sourceSemanticTree:semantic, semanticTree:semantic, sourceSemanticValidation:{code:'ok',detail:'',publishEligible:true}, semanticValidation:{code:'ok',detail:'',publishEligible:true}, nodeDiagnostics:[], nodeDiff:[{alignmentStatus:'preserved',alignedBy:'nodeId',nodeId:'n1',kind:'paragraph',sourceOrder:0,targetOrder:0,orderingDelta:0,sourceFingerprint:'node-fp',targetFingerprint:'node-fp',sourceAnchor:semantic.nodes[0].sourceAnchor,losses:[],diagnostics:[],sourceNode:semantic.nodes[0],targetNode:semantic.nodes[0]}], canonicalDispositions:[{authority:'canonical_content_review',issueId:'i1'}], canonicalHumanDecisions:[{authority:'canonical_human_decision',decisionId:'d1'}], offlineSuggestion:{authority:'workbench_offline_suggestion',decision:'unqualified'} }), {status:200,headers:{'Content-Type':'application/json'}});
    const detail=await api.work('id@R0'); assert.equal(detail.nodeDiff[0].alignmentStatus,'preserved'); assert.equal(detail.canonicalDispositions[0].authority,'canonical_content_review'); assert.equal(detail.offlineSuggestion.authority,'workbench_offline_suggestion');
  } finally { globalThis.fetch=originalFetch; }
});

test('三视口容器契约保持同一 AST fingerprint/count/order', async () => {
  const source=await readFile(new URL('../src/pages/WorkDetailPage.tsx', import.meta.url),'utf8');
  assert.match(source,/preview--\$\{viewport\}/); assert.match(source,/data-semantic-fingerprint=\{work\.semanticFingerprint/); assert.match(source,/data-node-count=\{work\.semanticTree\?\.nodes\.length/); assert.match(source,/data-node-order=\{work\.semanticTree\?\.nodes\.map/); assert.doesNotMatch(source,/parseMarkdown|marked\(|remarkParse/);
});

test('raw evidence 与 renderer 局部失败保持文本/局部隔离', async () => {
  const page=await readFile(new URL('../src/pages/WorkDetailPage.tsx',import.meta.url),'utf8'); const renderer=await readFile(new URL('../src/shared/semanticRenderer.tsx',import.meta.url),'utf8');
  assert.match(page,/<pre className="raw-content">\{evidence\.content\}<\/pre>/); assert.doesNotMatch(page,/dangerouslySetInnerHTML/); assert.match(renderer,/节点 renderer 失败/); assert.match(renderer,/data-node-id=\{node\.nodeId\}/);
});

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
test('canonical semantic Markdown real candidate is exact and byte stable', async (t) => { const file=new URL('../../../.qwq_output/data/content-remediation/executions/temple-of-emperors-v2-rerun-a2b10ce21722/source.semantic.json',import.meta.url); let source; try{source=JSON.parse(await readFile(file,'utf8'));}catch{t.skip('candidate unavailable');return;} const markdown=serializeEnvelope(source); const parsed=parseCanonicalMarkdown(markdown); assert.deepEqual(parsed,source); assert.equal(serializeEnvelope(parsed),markdown); });

test('canonical semantic Markdown parser fail closed', () => { assert.throws(() => parseCanonicalMarkdown('# legacy\n'), /SEMANTIC_DOCUMENT/); assert.throws(() => parseCanonicalMarkdown('---\n{}\n---\n'), /SEMANTIC_DOCUMENT/); });
