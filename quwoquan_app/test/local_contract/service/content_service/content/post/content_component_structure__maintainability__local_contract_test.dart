import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const postPresentation =
      'lib/service/content_service/content/post/presentation';
  const commentPresentation =
      'lib/service/content_service/content/comment/presentation';
  const componentFiles = <String, List<String>>{
    'article_editor': <String>[
      '$postPresentation/article_editor.dart',
      '$postPresentation/article_editor_content_builders.dart',
    ],
    'article_editor_accessories': <String>[
      '$postPresentation/article_editor_accessory_panels.dart',
      '$postPresentation/article_editor_accessory_style_panels.dart',
      '$postPresentation/article_editor_accessory_selection_panels.dart',
      '$postPresentation/article_editor_accessory_controls.dart',
    ],
    'comment_input_overlay': <String>[
      '$commentPresentation/comment_input_overlay.dart',
      '$commentPresentation/comment_input_overlay_components.dart',
    ],
    'content_share_sheet': <String>[
      '$postPresentation/content_share_sheet.dart',
      '$postPresentation/content_share_sheet_components.dart',
    ],
  };

  test('内容专项手写组件均低于 R03 千行红线', () {
    for (final group in componentFiles.entries) {
      for (final path in group.value) {
        final source = _readAppFile(path);
        final lineCount = const LineSplitter().convert(source).length;
        expect(
          lineCount,
          lessThan(1000),
          reason: '${group.key}: $path 有 $lineCount 行，必须继续按职责拆分',
        );
      }
    }
  });

  test('companion 只扩展父 library，不复制核心 State 真相源', () {
    for (final files in componentFiles.values) {
      final parent = files.first;
      final parentName = parent.split('/').last;
      final parentSource = _readAppFile(parent);
      for (final companion in files.skip(1)) {
        expect(parentSource, contains("part '${companion.split('/').last}';"));
        expect(_readAppFile(companion), contains("part of '$parentName';"));
      }
    }

    final articleSources = _joinSources(componentFiles['article_editor']!);
    expect(
      RegExp(
        r'class\s+_ArticleEditorState\s+extends\s+State<ArticleEditor>',
      ).allMatches(articleSources),
      hasLength(1),
    );

    final commentSources = _joinSources(
      componentFiles['comment_input_overlay']!,
    );
    expect(
      RegExp(
        r'class\s+_CommentInputSheetState\s+extends\s+ConsumerState<_CommentInputSheet>',
      ).allMatches(commentSources),
      hasLength(1),
    );

    final shareSources = _joinSources(componentFiles['content_share_sheet']!);
    expect(
      RegExp(
        r'class\s+_ConnectedContentShareSheetState\s+extends\s+ConsumerState<_ConnectedContentShareSheet>',
      ).allMatches(shareSources),
      hasLength(1),
    );
    expect(
      RegExp(
        r'class\s+_ContentShareSheetState\s+extends\s+State<ContentShareSheet>',
      ).allMatches(shareSources),
      hasLength(1),
    );
  });

  test('拆分后继续消费 CreatePageText 与 ChatText 语义文案', () {
    final articleSources = _joinSources(componentFiles['article_editor']!);
    final accessorySources = _joinSources(
      componentFiles['article_editor_accessories']!,
    );
    final commentSources = _joinSources(
      componentFiles['comment_input_overlay']!,
    );
    final shareSources = _joinSources(componentFiles['content_share_sheet']!);

    expect(articleSources, contains('CreatePageText.articleTitlePlaceholder'));
    expect(articleSources, contains('CreatePageText.articleBodyPlaceholder'));
    expect(articleSources, contains('CreatePageText.imageCaptionPlaceholder'));
    expect(articleSources, contains('CreatePageText.imageLayoutFullWidth'));
    expect(accessorySources, contains('CreatePageText.headingLarge'));
    expect(accessorySources, contains('CreatePageText.typographyQualityTitle'));
    expect(accessorySources, contains('CreatePageText.fontPreviewSample'));
    expect(commentSources, contains('ChatText.emojiRecent'));
    expect(shareSources, contains('ChatText.forwardCardUnavailable'));
    expect(shareSources, contains('ChatText.sharePrivateBlocked'));
  });
}

String _joinSources(List<String> paths) {
  return paths.map(_readAppFile).join('\n');
}

String _readAppFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct.readAsStringSync();
  }
  return File('quwoquan_app/$relativePath').readAsStringSync();
}
