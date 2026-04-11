import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/article_document_wire_dto.dart';

void main() {
  group('ArticleDocumentWireDto', () {
    test('fromMap / toMap round-trip preserves nodes', () {
      const wire = <String, dynamic>{
        'template': 'journal',
        'fontPreset': 'rounded',
        'titleStyle': 'major',
        'nodes': <Map<String, dynamic>>[
          {'id': 'n1', 'type': 'paragraph', 'text': 'hello'},
        ],
      };
      final dto = ArticleDocumentWireDto.fromMap(wire);
      expect(dto.nodes.length, 1);
      expect(dto.template, 'journal');
      final back = dto.toMap();
      expect(back['template'], 'journal');
      expect((back['nodes'] as List).length, 1);
    });

    test('toArticleDocumentData maps first node', () {
      final dto = ArticleDocumentWireDto.fromMap(const <String, dynamic>{
        'nodes': <Map<String, dynamic>>[
          {'id': 't1', 'type': 'documentTitle', 'text': 'T'},
          {'id': 'p1', 'type': 'paragraph', 'text': 'Body'},
        ],
      });
      final doc = dto.toArticleDocumentData();
      expect(doc.nodes.any((n) => n.text == 'Body'), isTrue);
    });
  });
}
