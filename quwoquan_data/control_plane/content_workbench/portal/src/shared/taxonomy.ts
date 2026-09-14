import type { TagNode } from './api/types.js';

export function ancestorRefs(nodes: TagNode[], selectedRefs: string[]): Set<string> {
  const selected = new Set(selectedRefs);
  const ancestors = new Set<string>();
  function visit(node: TagNode, path: string[]): boolean {
    const contains = selected.has(node.ref) || node.children.some((child) => visit(child, [...path, node.ref]));
    if (contains) path.forEach((ref) => ancestors.add(ref));
    return contains;
  }
  nodes.forEach((node) => visit(node, []));
  return ancestors;
}

export function visibleTaxonomy(nodes: TagNode[], expandedRefs: Iterable<string>, selectedRefs: string[]): TagNode[] {
  const expanded = new Set(expandedRefs);
  ancestorRefs(nodes, selectedRefs).forEach((ref) => expanded.add(ref));
  return nodes.map((node) => ({
    ...node,
    children: expanded.has(node.ref) ? visibleTaxonomy(node.children, expanded, selectedRefs) : [],
  }));
}
