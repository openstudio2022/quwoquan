import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const forbiddenCompatibilityMethods = <String>[
    'updateBody',
    'insertArticleParagraph',
    'insertArticleOrderedItem',
    'insertArticleTextBlock',
    'updateArticleTextBlock',
    'updateArticleTextBlockType',
    'insertArticlePageAfter',
    'updateArticlePageText',
    'updateArticlePageTextFromBinding',
    'removeArticlePage',
    'insertArticleImageAtBodyOffset',
    'replaceArticlePageImage',
    'insertArticleImages',
    'replaceArticlePageImageFromBinding',
    'updateArticlePageImageLayout',
    'updateArticlePageCaptionFromBinding',
    'updateArticlePageImageLayoutFromBinding',
    'removeArticleImageAsset',
    'removeArticlePageFromBinding',
    'removeArticleImageAssetById',
    'updateArticlePageCaptionForAsset',
    'updateArticlePageImageLayoutForAsset',
    'insertArticleImageAfterPage',
    'insertArticleParagraphAfterAsset',
    'materializeArticleParagraphBeforeAsset',
    'materializeArticleParagraphAfterAsset',
    'replaceArticleImageBlock',
    'updateArticleImageLayout',
    'removeArticleBlock',
    'removeArticleBlocks',
    'replaceArticleImageForAsset',
    'syncParagraphDraftBeforeAsset',
    'syncParagraphDraftBetweenAssets',
    'syncParagraphDraftAfterLastAsset',
    'insertArticleParagraphBeforeAsset',
  ];

  test('create editor production 只保留 nodes 级编辑 API', () {
    final sources = _providerSources();
    final combined = sources.values.join('\n');

    expect(combined, isNot(contains('@Deprecated')));
    for (final method in forbiddenCompatibilityMethods) {
      expect(
        RegExp('\\b$method\\s*\\(').hasMatch(combined),
        isFalse,
        reason: '$method 属于旧 body/assets/block 兼容轨',
      );
    }
  });

  test('ArticleDocumentData 不再从旧投影反向构造 nodes', () {
    final source = _readAppFile(
      'lib/ui/content/models/article_document_models.dart',
    );

    for (final symbol in <String>[
      'article_document_models_projection.dart',
      '_buildDocumentNodesFromCurrent',
      'useFullBlockSequence',
      'String body =',
      'List<ArticleDocumentAsset> assets =',
      'List<ArticleDocumentBlock> blocks =',
      'String? body',
      'List<ArticleDocumentAsset>? assets',
      'List<ArticleDocumentBlock>? blocks',
    ]) {
      expect(source, isNot(contains(symbol)), reason: '旧反向构造符号仍存在: $symbol');
    }
  });

  test('create editor provider 与文档模型手写文件低于 R03 千行红线', () {
    final sources = <String, String>{
      ..._providerSources(),
      'lib/ui/content/models/article_document_models.dart': _readAppFile(
        'lib/ui/content/models/article_document_models.dart',
      ),
    };

    for (final entry in sources.entries) {
      final lineCount = const LineSplitter().convert(entry.value).length;
      expect(
        lineCount,
        lessThan(1000),
        reason: '${entry.key} 有 $lineCount 行，必须继续按职责拆分',
      );
    }
  });
}

Map<String, String> _providerSources() {
  final directory = _appDirectory('lib/ui/content/entry/providers');
  final files =
      directory
          .listSync()
          .whereType<File>()
          .where((file) {
            final name = file.uri.pathSegments.last;
            return name.startsWith('create_editor_provider') &&
                name.endsWith('.dart');
          })
          .toList(growable: false)
        ..sort((left, right) => left.path.compareTo(right.path));
  return <String, String>{
    for (final file in files) file.path: file.readAsStringSync(),
  };
}

Directory _appDirectory(String relativePath) {
  final direct = Directory(relativePath);
  if (direct.existsSync()) {
    return direct;
  }
  return Directory('quwoquan_app/$relativePath');
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
