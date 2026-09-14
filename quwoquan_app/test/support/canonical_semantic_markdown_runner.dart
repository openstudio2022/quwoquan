import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/service/content_service/content/post/generated/semantic_document.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/canonical_semantic_markdown_codec.dart';

void main(List<String> a) {
  final v = (jsonDecode(File(a[0]).readAsStringSync()) as Map).map(
    (k, v) => MapEntry(k.toString(), v),
  );
  final e = documentEnvelopeFromWire(v);
  stdout.write(
    a.length > 1 && a[1] == 'safe' ? safeProjection(e) : serializeEnvelope(e),
  );
}
