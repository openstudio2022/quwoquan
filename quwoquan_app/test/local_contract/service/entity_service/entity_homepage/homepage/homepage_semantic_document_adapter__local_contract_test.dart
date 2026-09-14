import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_introduction_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('canonical payload wins and invalid payload never falls back', () {
    final valid = _envelope();
    final canonical = HomepageMarkdownDocumentAdapter.canonical(valid);
    expect(canonical.isAvailable, isTrue);
    expect(canonical.semanticKinds, <String>['paragraph']);

    final invalid = HomepageMarkdownDocumentAdapter.canonical(
      _envelope(canonicalDigest: 'sha256:${'0' * 64}'),
    );
    expect(invalid.isAvailable, isFalse);
    expect(invalid.errorCode, 'semantic_identity_drift');
  });

  test('legacy requires explicit version and rejects raw HTML', () {
    expect(
      HomepageMarkdownDocumentAdapter.legacy('plain').isAvailable,
      isFalse,
    );
    expect(
      HomepageMarkdownDocumentAdapter.legacy(
        '---\nmarkdownDialect: qwq-rich-md\n---\n<p>unsafe</p>',
      ).isAvailable,
      isFalse,
    );
    expect(
      HomepageMarkdownDocumentAdapter.legacy(
        '---\nmarkdownDialect: qwq-rich-md\n---\nplain',
      ).semanticKinds,
      <String>['paragraph'],
    );
  });

  test('unknown and experimental canonical nodes fail closed', () {
    final experimental = _envelope(kind: SemanticNodeKind.timeline);
    expect(
      HomepageMarkdownDocumentAdapter.canonical(experimental).isAvailable,
      isFalse,
    );
  });
}

DocumentEnvelope _envelope({
  SemanticNodeKind kind = SemanticNodeKind.paragraph,
  String? canonicalDigest,
}) {
  const fingerprint =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  final anchor = const SourceAnchor(
    origin: 'fixture',
    start: 0,
    end: 4,
    selector: 'node-1',
  );
  final descriptor = semanticDocumentNodeRegistry[kind]!;
  final node = SemanticNode(
    nodeId: 'node-1',
    kind: kind,
    disposition: ProcessingDisposition.preserved,
    policyVersion: semanticDocumentCanonicalizationVersion,
    requiredCapabilities: descriptor.requiredCapabilities.toList(),
    losses: const [],
    semanticFingerprint: fingerprint,
    sourceAnchor: anchor,
    attributes: const {'text': '正文'},
  );
  final required = descriptor.requiredCapabilities.toList()..sort();
  final base = DocumentEnvelope(
    schemaVersion: semanticDocumentSchemaVersion,
    dialectVersion: semanticDocumentDialectVersion,
    canonicalizationVersion: semanticDocumentCanonicalizationVersion,
    offsetEncoding: semanticDocumentOffsetEncoding,
    nodes: <SemanticNode>[node],
    requiredCapabilities: required,
    assets: const {},
    sourceMap: <String, SourceAnchor>{'node-1': anchor},
    policyVersion: semanticDocumentCanonicalizationVersion,
    losses: const [],
    semanticFingerprint: fingerprint,
    canonicalDigest: '',
  );
  final wire = documentEnvelopeToWire(base)..remove('canonicalDigest');
  final digest = 'sha256:${sha256.convert(utf8.encode(jsonEncode(wire)))}';
  return DocumentEnvelope(
    schemaVersion: base.schemaVersion,
    dialectVersion: base.dialectVersion,
    canonicalizationVersion: base.canonicalizationVersion,
    offsetEncoding: base.offsetEncoding,
    nodes: base.nodes,
    requiredCapabilities: base.requiredCapabilities,
    assets: base.assets,
    sourceMap: base.sourceMap,
    policyVersion: base.policyVersion,
    losses: base.losses,
    semanticFingerprint: base.semanticFingerprint,
    canonicalDigest: canonicalDigest ?? digest,
  );
}
