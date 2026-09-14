"""Canonical DocumentEnvelope <-> qwq-rich-md codec.

The node registry and protocol constants are generated from semantic_document.yaml;
this module owns only the deterministic textual projection.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from copy import deepcopy
from typing import Any, Mapping

from generated.semantic_document import CAPABILITY_IDS, CANONICALIZATION_VERSION, DIALECT_VERSION, NODE_REGISTRY, OFFSET_ENCODING, SCHEMA_VERSION, NodeKind, ValidationCode, validate_envelope

_HEADER_KEYS = frozenset({"schemaVersion","dialectVersion","canonicalizationVersion","offsetEncoding","requiredCapabilities","assets","sourceMap","policyVersion","losses","semanticFingerprint","canonicalDigest"})
_NODE_KEYS = frozenset({"nodeId","disposition","policyVersion","requiredCapabilities","losses","semanticFingerprint","sourceAnchor","diagnostics","rawSlice","rawSliceFingerprint","attributes","children","inlines"})
_OPEN = ":::qwq "
_RAW_HTML = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")

class CanonicalMarkdownError(ValueError):
    pass

def _normalized(value: Any) -> Any:
    if isinstance(value, str): return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)): return value
    if isinstance(value, float):
        if not math.isfinite(value): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.CANONICAL_NUMBER")
        return value
    if isinstance(value, list): return [_normalized(v) for v in value]
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.CANONICAL_KEY")
        return {unicodedata.normalize("NFC", k): _normalized(v) for k,v in value.items()}
    raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.FIELD_TYPE")

def canonical_json(value: Any) -> str:
    return json.dumps(_normalized(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def _digest(value: Mapping[str, Any], excluded: frozenset[str]) -> str:
    material={k:v for k,v in value.items() if k not in excluded}
    return hashlib.sha256(canonical_json(material).encode()).hexdigest()

def _matches_digest(claimed: Any, actual: str) -> bool:
    return claimed in (actual, "sha256:"+actual)

def verify_canonical_identity(envelope: Mapping[str, Any]) -> None:
    semantic=_digest(envelope,frozenset({"semanticFingerprint","canonicalDigest"}))
    canonical=_digest(envelope,frozenset({"canonicalDigest"}))
    if not _matches_digest(envelope.get("semanticFingerprint"),semantic): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.SEMANTIC_FINGERPRINT")
    if not _matches_digest(envelope.get("canonicalDigest"),canonical): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.CANONICAL_DIGEST")

def _validate(envelope: Mapping[str, Any]) -> None:
    result=validate_envelope(envelope, CAPABILITY_IDS)
    if result.code != ValidationCode.OK: raise CanonicalMarkdownError(f"{result.code.value}:{result.detail}")
    verify_canonical_identity(envelope)
    for node in envelope["nodes"]:
        if node.get("kind") == NodeKind.UNSUPPORTED_OPAQUE.value: raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.UNSUPPORTED_OPAQUE.PUBLISH_FORBIDDEN")

def _inline_markdown(node: Mapping[str, Any]) -> str:
    attrs=node.get("attributes") or {}
    return str(attrs.get("plainText") or attrs.get("text") or "")

def _native_body(node: Mapping[str, Any]) -> str:
    kind=node["kind"]; text=_inline_markdown(node); a=node.get("attributes") or {}
    if kind=="documentTitle": return "# "+text
    if kind=="heading": return "#"*max(2,min(6,int(a.get("level",2))))+" "+text
    if kind=="paragraph": return text
    if kind=="blockquote": return "\n".join("> "+line for line in text.split("\n"))
    if kind=="codeBlock": return "```"+str(a.get("language") or "")+"\n"+text+"\n```"
    if kind=="preformatted": return "\n".join("    "+line for line in text.split("\n"))
    if kind=="divider": return "---"
    if kind=="listItem": return ("1. " if a.get("listKind")=="ordered" else "- ")+text
    if kind=="definitionList": return text
    return ""

def _review_body(node: Mapping[str, Any]) -> str:
    return _native_body(node) if node["kind"] in {"documentTitle","heading","paragraph","blockquote","codeBlock","preformatted","divider","listItem","definitionList"} else _body(node)

def _body(node: Mapping[str, Any]) -> str:
    attrs=node.get("attributes")
    if isinstance(attrs,Mapping):
        for key in ("plainText","text","caption"):
            value=attrs.get(key)
            if isinstance(value,str) and value: return value.replace("\r\n","\n").replace("\r","\n")
    return ""

def serialize_envelope(envelope: Mapping[str, Any]) -> str:
    value=_normalized(deepcopy(dict(envelope))); _validate(value)
    header={k:value[k] for k in sorted(_HEADER_KEYS)}; blocks=[]
    for node in value["nodes"]:
        kind=node["kind"]; metadata={k:node.get(k) for k in sorted(_NODE_KEYS)}; body=_review_body(node)
        if _renderable_unsafe(body): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.UNSAFE.RAW_HTML")
        blocks.append(f":::qwq-meta {kind} {canonical_json(metadata)}\n\n{body}")
    return f"---\n{canonical_json(header)}\n---\n\n"+"\n\n".join(blocks)+"\n"

def _renderable_unsafe(text: str) -> bool:
    lower=text.lower()
    return bool(re.search(r"<\s*(script|style|iframe|object|embed|form|input|button|meta|link)(?:\s|>|/)",lower) or re.search(r"\bon[a-z]+\s*=|\bsrcdoc\s*=|(?:javascript|data)\s*:",lower))

def parse_canonical_markdown(markdown: str) -> dict[str, Any]:
    if "\r" in markdown or not markdown.endswith("\n"): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.CANONICAL_LINE_ENDING")
    lines=markdown[:-1].split("\n")
    if len(lines)<5 or lines[0]!="---" or lines[2]!="---" or lines[3]!="": raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.FRONTMATTER")
    try: header=json.loads(lines[1])
    except Exception as exc: raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.FRONTMATTER") from exc
    if not isinstance(header,dict) or set(header)!=_HEADER_KEYS or canonical_json(header)!=lines[1]: raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.CANONICAL_FRONTMATTER")
    nodes=[];i=4
    while i<len(lines):
        line=lines[i]
        if not line.startswith(":::qwq-meta "): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING")
        rest=line[len(":::qwq-meta "):];at=rest.find(" ");kind,payload=rest[:at],rest[at+1:]
        try: metadata=json.loads(payload)
        except Exception as exc: raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.DIRECTIVE_ATTRIBUTE") from exc
        if not isinstance(metadata,dict) or set(metadata)!=_NODE_KEYS or canonical_json(metadata)!=payload: raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.DIRECTIVE_ATTRIBUTE")
        if i+1>=len(lines) or lines[i+1] != "": raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING")
        node={"kind":kind,**metadata};i+=2;body=[]
        while i<len(lines) and not lines[i].startswith(":::qwq-meta "): body.append(lines[i]);i+=1
        if i<len(lines) and body and body[-1]=="": body.pop()
        text="\n".join(body)
        if text!=_review_body(node) or _renderable_unsafe(text): raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING")
        nodes.append(node)
    envelope={**header,"nodes":nodes};_validate(envelope)
    if serialize_envelope(envelope)!=markdown: raise CanonicalMarkdownError("SEMANTIC_DOCUMENT.INVALID.NON_CANONICAL_MARKDOWN")
    return envelope

serializeEnvelope=serialize_envelope
parseCanonicalMarkdown=parse_canonical_markdown

_SAFE_TAGS={"documentTitle":"h1","heading":"heading_level","paragraph":"p","blockquote":"blockquote","preformatted":"pre","codeBlock":"code","divider":"hr","list":"list","listItem":"li","definitionList":"dl","callout":"aside","factBox":"aside","factRow":"div","table":"table","tableCaption":"caption","tableRow":"tr","tableCell":"td_or_th","groupedDirectory":"nav","footnoteReference":"sup","footnoteDefinition":"li","footnoteList":"ol","hatnote":"aside","externalLinks":"section","seeAlso":"section","relatedResources":"section","figure":"figure","gallery":"gallery"}
def safe_projection(envelope: Mapping[str,Any])->str:
 events=[]
 def visit(n,depth):
  a=n.get('attributes') or {}; links=[]; assets=[]; cells=[]; edges=[]
  def scan(v):
   if isinstance(v,dict):
    if isinstance(v.get('href'),str) and v['href']:links.append(v['href'])
    for key in ('assetId','figureId'):
     if isinstance(v.get(key),str) and v[key]:assets.append(v[key])
    if 'row' in v and 'column' in v:cells.append({k:v.get(k) for k in ('row','column','rowSpan','rowspan','columnSpan','colspan','scope','sortKey')})
    for z in v.values():scan(z)
   elif isinstance(v,list):
    for z in v:scan(z)
  scan(a);rid=a.get('refId') or a.get('identifier');
  if n['kind']=='footnoteReference' and rid:edges.append(rid)
  events.append({'order':len(events),'depth':depth,'nodeId':n['nodeId'],'kind':n['kind'],'safeTag':_SAFE_TAGS.get(n['kind'],'section'),'text':_body(n),'links':sorted(links),'assetIds':sorted(assets),'tableCells':cells,'footnoteEdges':edges})
  for c in n.get('children') or []:visit(c,depth+1)
 for n in envelope['nodes']:visit(n,0)
 return canonical_json(events)+'\n'
