import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class CanonicalSemanticMarkdownException implements Exception {
  const CanonicalSemanticMarkdownException(this.code);
  final String code;
  @override
  String toString() => code;
}

const _headerKeys = <String>{
  'assets',
  'canonicalDigest',
  'canonicalizationVersion',
  'dialectVersion',
  'losses',
  'offsetEncoding',
  'policyVersion',
  'requiredCapabilities',
  'schemaVersion',
  'semanticFingerprint',
  'sourceMap',
};
const _nodeKeys = <String>{
  'attributes',
  'children',
  'diagnostics',
  'disposition',
  'inlines',
  'losses',
  'nodeId',
  'policyVersion',
  'rawSlice',
  'rawSliceFingerprint',
  'requiredCapabilities',
  'semanticFingerprint',
  'sourceAnchor',
};
Object? _normalized(Object? v) {
  if (v is String) return v;
  if (v == null || v is bool || v is int) return v;
  if (v is double) {
    if (!v.isFinite)
      throw const CanonicalSemanticMarkdownException(
        'SEMANTIC_DOCUMENT.INVALID.CANONICAL_NUMBER',
      );
    return v;
  }
  if (v is List) return v.map(_normalized).toList();
  if (v is Map) {
    final keys = v.keys.map((e) => e.toString()).toList()..sort();
    return {for (final k in keys) k: _normalized(v[k])};
  }
  throw const CanonicalSemanticMarkdownException(
    'SEMANTIC_DOCUMENT.INVALID.FIELD_TYPE',
  );
}

String _canonicalJson(Object? v) => jsonEncode(_normalized(v));
String _digest(Map<String, Object?> v, Set<String> excluded) {
  final m = {
    for (final e in v.entries)
      if (!excluded.contains(e.key)) e.key: e.value,
  };
  return sha256.convert(utf8.encode(_canonicalJson(m))).toString();
}

bool _matches(Object? v, String a) => v == a || v == 'sha256:$a';
String _nodeText(Map<String, Object?> n) {
  final a = n['attributes'];
  if (a is Map)
    for (final k in const ['plainText', 'text', 'caption']) {
      final v = a[k];
      if (v is String && v.isNotEmpty)
        return v.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    }
  return '';
}

String _body(Map<String, Object?> n) {
  final text = _nodeText(n), a = (n['attributes'] as Map?) ?? const {};
  switch (n['kind']) {
    case 'documentTitle':
      return '# $text';
    case 'heading':
      final level = ((a['level'] as int?) ?? 2).clamp(2, 6);
      return '${'#' * level} $text';
    case 'paragraph':
      return text;
    case 'blockquote':
      return '> ${text.replaceAll('\n', '\n> ')}';
    case 'codeBlock':
      return '```${a['language'] ?? ''}\n$text\n```';
    case 'preformatted':
      return '    ${text.replaceAll('\n', '\n    ')}';
    case 'divider':
      return '---';
    case 'listItem':
      return '${a['listKind'] == 'ordered' ? '1. ' : '- '}$text';
    default:
      return text;
  }
}

bool _renderableUnsafe(String text) {
  final l = text.toLowerCase();
  return RegExp(
        r'<\s*(script|style|iframe|object|embed|form|input|button|meta|link)(?:\s|>|/)',
      ).hasMatch(l) ||
      RegExp(r'\bon[a-z]+\s*=|\bsrcdoc\s*=|(?:javascript|data)\s*:')
          .hasMatch(l);
}

void _validate(Map<String, Object?> v) {
  final result = validateSemanticDocumentEnvelope(
    v,
    semanticDocumentCapabilityIds,
  );
  if (result.code != SemanticDocumentValidationCode.ok)
    throw CanonicalSemanticMarkdownException(
      '${result.code.name}:${result.detail}',
    );
  final nodes = v['nodes'] as List;
  if (nodes.any((n) => n is Map && n['kind'] == 'unsupportedOpaque'))
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.UNSUPPORTED_OPAQUE.PUBLISH_FORBIDDEN',
    );
  if (!_matches(
    v['semanticFingerprint'],
    _digest(v, {'semanticFingerprint', 'canonicalDigest'}),
  ))
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.SEMANTIC_FINGERPRINT',
    );
  if (!_matches(v['canonicalDigest'], _digest(v, {'canonicalDigest'})))
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.CANONICAL_DIGEST',
    );
}

String serializeEnvelope(DocumentEnvelope envelope) {
  final v =
      _normalized(documentEnvelopeToWire(envelope)) as Map<String, Object?>;
  _validate(v);
  final header = {for (final k in (_headerKeys.toList()..sort())) k: v[k]};
  final blocks = <String>[];
  for (final raw in v['nodes'] as List) {
    final n = raw as Map<String, Object?>;
    final m = {for (final k in (_nodeKeys.toList()..sort())) k: n[k]};
    final body = _body(n);
    if (_renderableUnsafe(body))
      throw const CanonicalSemanticMarkdownException(
        'SEMANTIC_DOCUMENT.UNSAFE.RAW_HTML',
      );
    blocks.add(':::qwq-meta ${n['kind']} ${_canonicalJson(m)}\n\n$body');
  }
  return '---\n${_canonicalJson(header)}\n---\n\n${blocks.join('\n\n')}\n';
}

bool _exact(Map<String, Object?> v, Set<String> keys) =>
    v.length == keys.length && v.keys.every(keys.contains);
DocumentEnvelope parseCanonicalMarkdown(String markdown) {
  if (markdown.contains('\r') || !markdown.endsWith('\n'))
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.CANONICAL_LINE_ENDING',
    );
  final lines = markdown.substring(0, markdown.length - 1).split('\n');
  if (lines.length < 5 ||
      lines[0] != '---' ||
      lines[2] != '---' ||
      lines[3] != '')
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.FRONTMATTER',
    );
  Map<String, Object?> h;
  try {
    h = (jsonDecode(lines[1]) as Map).map((k, v) => MapEntry(k.toString(), v));
  } catch (_) {
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.FRONTMATTER',
    );
  }
  if (!_exact(h, _headerKeys) || _canonicalJson(h) != lines[1])
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.CANONICAL_FRONTMATTER',
    );
  final nodes = <Object?>[];
  for (var i = 4; i < lines.length;) {
    if (!lines[i].startsWith(':::qwq-meta '))
      throw const CanonicalSemanticMarkdownException(
        'SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING',
      );
    final at = lines[i].indexOf(' ', 12),
        kind = lines[i].substring(12, at),
        payload = lines[i].substring(at + 1);
    Map<String, Object?> m;
    try {
      m = (jsonDecode(payload) as Map).map((k, v) => MapEntry(k.toString(), v));
    } catch (_) {
      throw const CanonicalSemanticMarkdownException(
        'SEMANTIC_DOCUMENT.INVALID.DIRECTIVE_ATTRIBUTE',
      );
    }
    if (!_exact(m, _nodeKeys) ||
        _canonicalJson(m) != payload ||
        lines[i + 1] != '')
      throw const CanonicalSemanticMarkdownException(
        'SEMANTIC_DOCUMENT.INVALID.DIRECTIVE_ATTRIBUTE',
      );
    final n = <String, Object?>{'kind': kind, ...m};
    i += 2;
    final body = <String>[];
    while (i < lines.length && !lines[i].startsWith(':::qwq-meta ')) {
      body.add(lines[i++]);
    }
    if (i < lines.length && body.isNotEmpty && body.last.isEmpty)
      body.removeLast();
    final text = body.join('\n');
    if (text != _body(n) || _renderableUnsafe(text))
      throw const CanonicalSemanticMarkdownException(
        'SEMANTIC_DOCUMENT.INVALID.METADATA_BINDING',
      );
    nodes.add(n);
  }
  final wire = <String, Object?>{...h, 'nodes': nodes};
  _validate(wire);
  final envelope = documentEnvelopeFromWire(wire);
  if (serializeEnvelope(envelope) != markdown)
    throw const CanonicalSemanticMarkdownException(
      'SEMANTIC_DOCUMENT.INVALID.NON_CANONICAL_MARKDOWN',
    );
  return envelope;
}
