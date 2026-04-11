import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/tool/impl/web/normalized_web_reference.dart';

void main() {
  test('fromSerpOrganicItem maps title url snippet', () {
    final n = NormalizedWebReference.fromSerpOrganicItem(<String, dynamic>{
      'title': ' T ',
      'url': ' https://x.test ',
      'snippet': ' s ',
    });
    expect(n.title, 'T');
    expect(n.url, 'https://x.test');
    expect(n.snippet, 's');
    expect(n.isUsable, isTrue);
  });

  test('fromBraveWebResult uses description as snippet', () {
    final n = NormalizedWebReference.fromBraveWebResult(<String, dynamic>{
      'title': 'a',
      'url': 'u',
      'description': 'd',
    });
    expect(n.snippet, 'd');
  });
}
