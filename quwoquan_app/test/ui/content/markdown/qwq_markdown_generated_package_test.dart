import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/markdown/qwq_markdown.dart';

void main() {
  test('生成的 quwoquan_data article.md 可被 QwqMarkdownParser 解析', () {
    final articlePath = File(
      'test/ui/content/markdown/fixtures/real_source_article.md',
    );

    expect(articlePath.existsSync(), isTrue);
    final result = const QwqMarkdownParser().parse(
      articlePath.readAsStringSync(),
    );

    expect(result.isValid, isTrue);
    expect(result.document.frontMatter.title, isNotEmpty);
    expect(result.document.frontMatter.coverAssetId, isNotEmpty);
    expect(result.document.frontMatter.coverImage, startsWith('asset://'));
    expect(result.document.blocks, isNotEmpty);
    expect(result.document.referencedAssetIds, isNotEmpty);
    expect(result.document.bodyEntityAnchorRefs, isNotEmpty);
    expect(
      result.document.bodyEntityAnchorRefs,
      contains('trees/entities/地点/西湖.yaml'),
    );
    expect(articlePath.readAsStringSync(), contains('## 实体锚点'));
  });
}
