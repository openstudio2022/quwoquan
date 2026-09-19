// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/generated/semantic_document.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/canonical_semantic_markdown_codec.dart';

void main() {
  test('读取保留 exact 实例、版本、双摘要与完整子树，不解析 Markdown', () {
    final wire = _sealedWire();
    final envelope = documentEnvelopeFromWire(wire);
    final result = requireCanonicalEnvelope(envelope);

    expect(identical(result, envelope), isTrue);
    expect(documentEnvelopeToWire(result), wire);
    expect(result.schemaVersion, '1.2.3');
    expect(result.dialectVersion, '1.4.5');
    expect(result.canonicalizationVersion, '1.0.0');
    expect(result.policyVersion, 'policy-exact-7');
    expect(result.canonicalDigest, wire['canonicalDigest']);
    expect(result.semanticFingerprint, wire['semanticFingerprint']);
    expect(result.nodes.single.children.single.nodeId, 'paragraph-1');
    expect(result.nodes.single.children.single.attributes['plainText'], '正文😀');
    expect(result.nodes.single.children.single.inlines.single.start, 2);
  });

  test('缺 canonical 文档必须 typed 拒绝，不补标题或空正文', () {
    expect(
      () => requireCanonicalEnvelope(null),
      throwsA(
        isA<CanonicalSemanticMarkdownException>().having(
          (error) => error.code,
          '既有字段类型诊断',
          'SEMANTIC_DOCUMENT.INVALID.FIELD_TYPE',
        ),
      ),
    );
  });

  for (final entry in <String, String>{
    'schemaVersion': '2.0.0',
    'dialectVersion': '2.0.0',
    'canonicalizationVersion': '1.0.1',
    'offsetEncoding': 'utf16',
  }.entries) {
    test('${entry.key} 不兼容必须拒绝，不归一化版本', () {
      final wire = _sealedWire()..[entry.key] = entry.value;
      expect(
        () => requireCanonicalEnvelope(documentEnvelopeFromWire(wire)),
        throwsA(isA<CanonicalSemanticMarkdownException>()),
      );
    });
  }

  test('子节点正文漂移即使保留旧摘要也必须拒绝', () {
    final wire = _sealedWire();
    final nodes = wire['nodes']! as List;
    final children = (nodes.single as Map)['children'] as List;
    (children.single as Map)['attributes'] = {'plainText': '被改写'};
    expect(
      () => requireCanonicalEnvelope(documentEnvelopeFromWire(wire)),
      throwsA(
        isA<CanonicalSemanticMarkdownException>().having(
          (error) => error.code,
          '语义摘要漂移',
          'SEMANTIC_DOCUMENT.INVALID.SEMANTIC_FINGERPRINT',
        ),
      ),
    );
  });

  test('canonical digest 漂移必须拒绝', () {
    final wire = _sealedWire()..['canonicalDigest'] = '0' * 64;
    expect(
      () => requireCanonicalEnvelope(documentEnvelopeFromWire(wire)),
      throwsA(
        isA<CanonicalSemanticMarkdownException>().having(
          (error) => error.code,
          'canonical 摘要漂移',
          'SEMANTIC_DOCUMENT.INVALID.CANONICAL_DIGEST',
        ),
      ),
    );
  });

  test('reader 不猜测未声明的 capability', () {
    final wire = _sealedWire()..['requiredCapabilities'] = <String>[];
    expect(
      () => requireCanonicalEnvelope(documentEnvelopeFromWire(wire)),
      throwsA(isA<CanonicalSemanticMarkdownException>()),
    );
  });
}

Map<String, Object?> _sealedWire() {
  const anchor = SourceAnchor(
    origin: 'imported_html',
    start: 0,
    end: 3,
    selector: 'p',
  );
  final capabilities = semanticDocumentCapabilityIds.toList()..sort();
  final envelope = DocumentEnvelope(
    schemaVersion: '1.2.3',
    dialectVersion: '1.4.5',
    canonicalizationVersion: '1.0.0',
    offsetEncoding: 'unicode_scalar_value',
    nodes: [
      SemanticNode(
        nodeId: 'section-1',
        kind: SemanticNodeKind.section,
        disposition: ProcessingDisposition.preserved,
        policyVersion: 'policy-exact-7',
        requiredCapabilities: capabilities,
        losses: const [],
        semanticFingerprint: 'section-fingerprint',
        sourceAnchor: anchor,
        children: [
          SemanticNode(
            nodeId: 'paragraph-1',
            kind: SemanticNodeKind.paragraph,
            disposition: ProcessingDisposition.preserved,
            policyVersion: 'policy-exact-7',
            requiredCapabilities: capabilities,
            losses: const [],
            semanticFingerprint: 'paragraph-fingerprint',
            sourceAnchor: anchor,
            attributes: const {'plainText': '正文😀'},
            inlines: const [
              SemanticInline(kind: SemanticInlineKind.bold, start: 2, end: 3),
            ],
          ),
        ],
      ),
    ],
    requiredCapabilities: capabilities,
    assets: const {},
    sourceMap: const {'section-1': anchor, 'paragraph-1': anchor},
    policyVersion: 'policy-exact-7',
    losses: const [],
    semanticFingerprint: '',
    canonicalDigest: '',
  );
  final wire = documentEnvelopeToWire(envelope);
  wire['semanticFingerprint'] = _digest(wire, {
    'semanticFingerprint',
    'canonicalDigest',
  });
  wire['canonicalDigest'] = _digest(wire, {'canonicalDigest'});
  return wire;
}

String _digest(Map<String, Object?> wire, Set<String> excluded) {
  Object? sorted(Object? value) {
    if (value is Map) {
      final keys = value.keys.cast<String>().toList()..sort();
      return {for (final key in keys) key: sorted(value[key])};
    }
    if (value is List) return value.map(sorted).toList();
    return value;
  }

  return sha256
      .convert(
        utf8.encode(
          jsonEncode(
            sorted({
              for (final entry in wire.entries)
                if (!excluded.contains(entry.key)) entry.key: entry.value,
            }),
          ),
        ),
      )
      .toString();
}
