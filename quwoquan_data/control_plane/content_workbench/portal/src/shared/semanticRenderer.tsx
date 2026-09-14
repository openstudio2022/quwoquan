import type { ElementType, ReactNode } from 'react';
import {
  CAPABILITY_IDS,
  NODE_REGISTRY,
  validateSemanticDocumentEnvelope,
  type DocumentEnvelope,
  type SemanticNode,
  type SemanticNodeKind,
  type ValidationResult,
} from '../generated/semanticDocument.js';
import { parseCanonicalMarkdown, CanonicalMarkdownError } from './canonicalSemanticMarkdown.js';

export type SemanticValidation = ValidationResult & { publishEligible: boolean };
const record = (value: unknown): Readonly<Record<string, unknown>> => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Readonly<Record<string, unknown>> : {};
const text = (node: SemanticNode): string => {
  const attributes = record(node.attributes);
  for (const key of ['text', 'plainText', 'title', 'caption', 'label', 'term', 'definition', 'code']) {
    if (typeof attributes[key] === 'string') return attributes[key];
  }
  return node.rawSlice || '';
};
const children = (node: SemanticNode): ReactNode => node.children?.map((child) => <SemanticNodeView key={child.nodeId} node={child} />);
const opaque = (node: SemanticNode) => <pre className="semantic-opaque" data-node-kind={node.kind}>{node.rawSlice || JSON.stringify(node.attributes || {}, null, 2)}</pre>;

export function parseCanonicalMarkdownForWorkbench(markdown: string): { envelope: DocumentEnvelope | null; validation: SemanticValidation } {
  try { const envelope=parseCanonicalMarkdown(markdown); return {envelope,validation:{code:'ok',publishEligible:true}}; }
  catch(reason){ return {envelope:null,validation:{code:'SEMANTIC_DOCUMENT.INVALID.FIELD_TYPE',detail:reason instanceof CanonicalMarkdownError?reason.message:String(reason),publishEligible:false}}; }
}

export function validateForWorkbench(value: unknown): { envelope: DocumentEnvelope | null; validation: SemanticValidation } {
  const candidate = record(value);
  if (!Object.keys(candidate).length) return { envelope: null, validation: { code: 'missing_required_field', detail: 'source.semantic.json', publishEligible: false } };
  const result = validateSemanticDocumentEnvelope(candidate, CAPABILITY_IDS);
  if (result.code !== 'ok') return { envelope: null, validation: { ...result, publishEligible: false } };
  const envelope = candidate as unknown as DocumentEnvelope;
  const publishEligible = !envelope.nodes.some((node) => NODE_REGISTRY[node.kind].status === 'experimental' || ['degraded', 'unsupported_opaque', 'blocked_unsafe'].includes(node.disposition));
  return { envelope, validation: { code: 'ok', publishEligible } };
}

function Table({ node }: { node: SemanticNode }) {
  const grid = record(node.attributes).logicalGrid;
  if (!Array.isArray(grid)) return <div className="semantic-table"><span>{text(node)}</span>{children(node)}</div>;
  return <div className="table-wrap"><table><tbody>{grid.map((rawRow, rowIndex) => <tr key={rowIndex}>{Array.isArray(rawRow) && rawRow.map((rawCell, cellIndex) => { const cell = record(rawCell); if (cell.covered) return null; const Tag = cell.header ? 'th' : 'td'; return <Tag key={cellIndex} rowSpan={Number(cell.rowspan || cell.rowSpan || 1)} colSpan={Number(cell.colspan || cell.columnSpan || 1)}>{String(cell.text || '')}</Tag>; })}</tr>)}</tbody></table></div>;
}
function GroupedDirectory({ node }: { node: SemanticNode }) { const groups = record(node.attributes).groups; return <nav className="grouped-directory">{Array.isArray(groups) ? groups.map((rawGroup, index) => { const group = record(rawGroup); return <section key={index}><strong>{String(group.label || '')}</strong><ul>{Array.isArray(group.members) && group.members.map((rawMember, memberIndex) => <li key={memberIndex}>{String(record(rawMember).text || record(rawMember).label || '')}</li>)}</ul></section>; }) : children(node)}</nav>; }
function Definition({ node }: { node: SemanticNode }) { const attributes = record(node.attributes); const entries = attributes.entries; return <dl>{Array.isArray(entries) ? entries.map((rawEntry, index) => { const entry = record(rawEntry); return <div key={index}><dt>{String(entry.term || entry.label || '')}</dt><dd>{String(entry.definition || entry.text || '')}</dd></div>; }) : <div><dt>{String(attributes.term || '')}</dt><dd>{String(attributes.definition || text(node))}</dd></div>}</dl>; }
function Figure({ node }: { node: SemanticNode }) { const attributes = record(node.attributes); return <figure><div className="rich-media-placeholder">资产：{String(attributes.assetId || attributes.figureId || node.nodeId)}</div><figcaption>{String(attributes.caption || text(node))}</figcaption></figure>; }
function Gallery({ node }: { node: SemanticNode }) { const attributes = record(node.attributes); const ids = attributes.assetIds; return <section className="semantic-gallery">{Array.isArray(ids) ? ids.map((id) => <div className="rich-media-placeholder" key={String(id)}>资产：{String(id)}</div>) : children(node)}{typeof attributes.caption === 'string' && <p>{attributes.caption}</p>}</section>; }

export function SemanticNodeView({ node }: { node: SemanticNode }) {
  try { return SemanticNodeViewUnsafe({ node }); } catch (reason) { return <div className="notice notice--error" data-node-id={node.nodeId}><strong>节点 renderer 失败</strong><span>{node.nodeId} · {reason instanceof Error ? reason.message : String(reason)}</span><pre>{node.rawSlice || JSON.stringify(node.attributes || {}, null, 2)}</pre></div>; }
}
function SemanticNodeViewUnsafe({ node }: { node: SemanticNode }) {
  const descriptor = NODE_REGISTRY[node.kind as SemanticNodeKind];
  if (!descriptor || descriptor.status === 'experimental' || node.kind === 'unsupportedOpaque' || node.disposition === 'unsupported_opaque') return opaque(node);
  switch (node.kind) {
    case 'documentTitle': return <h1>{text(node)}</h1>;
    case 'heading': { const level = Math.min(6, Math.max(2, Number(record(node.attributes).level || 2))); const Tag = `h${level}` as ElementType; return <Tag>{text(node)}{children(node)}</Tag>; }
    case 'paragraph': return <p>{text(node)}{children(node)}</p>;
    case 'blockquote': case 'epigraph': return <blockquote>{text(node)}{children(node)}</blockquote>;
    case 'callout': case 'hatnote': case 'factBox': case 'details': return <aside className={`semantic-${node.kind}`}>{text(node)}{children(node)}</aside>;
    case 'codeBlock': case 'preformatted': case 'verse': return <pre><code>{text(node)}</code></pre>;
    case 'divider': return <hr />;
    case 'list': return record(node.attributes).listKind === 'ordered' ? <ol>{children(node)}</ol> : <ul>{children(node)}</ul>;
    case 'listItem': return <li>{text(node)}{children(node)}</li>;
    case 'table': return <Table node={node} />;
    case 'tableRow': return <div role="row">{children(node)}</div>;
    case 'tableCell': return <span role="cell">{text(node)}{children(node)}</span>;
    case 'tableCaption': return <strong>{text(node)}</strong>;
    case 'groupedDirectory': return <GroupedDirectory node={node} />;
    case 'definitionList': case 'factRow': return <Definition node={node} />;
    case 'footnoteDefinition': case 'footnoteReference': case 'footnoteList': return <aside className="semantic-footnote">{text(node)}{children(node)}</aside>;
    case 'figure': return <Figure node={node} />;
    case 'gallery': return <Gallery node={node} />;
    case 'section': case 'bibliography': case 'externalLinks': case 'relatedResources': case 'seeAlso': return <section className={`semantic-${node.kind}`}>{text(node)}{children(node)}</section>;
    default: return <div data-node-kind={node.kind}>{text(node)}{children(node)}</div>;
  }
}
export function SemanticProductPreview({ envelope }: { envelope: DocumentEnvelope }) { return <article className="semantic-document" data-semantic-fingerprint={envelope.semanticFingerprint} data-node-count={envelope.nodes.length} data-node-order={envelope.nodes.map((node) => node.nodeId).join(',')}>{envelope.nodes.map((node) => <div id={`preview-node-${node.nodeId}`} data-node-id={node.nodeId} key={node.nodeId}><SemanticNodeView node={node} /></div>)}</article>; }
