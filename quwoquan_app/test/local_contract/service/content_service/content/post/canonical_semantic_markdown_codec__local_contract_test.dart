// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-005
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/generated/semantic_document.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/canonical_semantic_markdown_codec.dart';

void main() {
  test('real candidate AST Markdown AST is exact and byte stable', () {
    final file = File(
      '../.qwq_output/data/content-remediation/executions/temple-of-emperors-v2-rerun-a2b10ce21722/source.semantic.json',
    );
    if (!file.existsSync()) return;
    final source = (jsonDecode(file.readAsStringSync()) as Map).map(
      (k, v) => MapEntry(k.toString(), v),
    );
    final envelope = documentEnvelopeFromWire(source);
    final markdown = serializeEnvelope(envelope);
    final parsed = parseCanonicalMarkdown(markdown);
    expect(documentEnvelopeToWire(parsed), source);
    expect(serializeEnvelope(parsed), markdown);
  });
  test(
    'canonical parser does not upgrade legacy Markdown or fill identity',
    () {
      expect(
        () => parseCanonicalMarkdown('# legacy\n'),
        throwsA(isA<CanonicalSemanticMarkdownException>()),
      );
      expect(
        () => parseCanonicalMarkdown('---\n{}\n---\n'),
        throwsA(isA<CanonicalSemanticMarkdownException>()),
      );
    },
  );
}
