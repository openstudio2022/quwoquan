import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_wrap_paragraph_editor.dart';

/// 完全模拟真机 _buildWrapGroup 链路的测试 harness。
/// 支持有/无配文、有/无窄文、不同屏幕宽度。
class _RealChainHarness extends StatelessWidget {
  const _RealChainHarness({
    required this.text,
    required this.captionText,
    this.contentWidth = 340.0,
    this.placeholder,
    this.imageLayout = 'wrapLeft',
  });

  final String text;
  final String captionText;
  final double contentWidth;
  final String? placeholder;
  final String imageLayout;

  @override
  Widget build(BuildContext context) {
    const bodyStyle = TextStyle(fontSize: 16, height: 1.82);
    final captionStyle = TextStyle(
      color: CupertinoColors.secondaryLabel,
      fontSize: AppTypography.sm,
      height: articleCaptionLineHeight(),
    );

    return CupertinoApp(
      home: CupertinoPageScaffold(
        child: SingleChildScrollView(
          child: Center(
            child: SizedBox(
              width: contentWidth,
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final wrapResult = resolveArticleWrapLayout(
                    ArticleWrapLayoutInput(
                      body: text,
                      rowContentWidth: constraints.maxWidth,
                      bodyStyle: bodyStyle,
                      captionText: captionText,
                      captionStyle: captionStyle,
                      captionPlaceholderWhenEmpty: false,
                      imageLayout: imageLayout,
                    ),
                  );
                  final wd = wrapResult.layout;

                  final imageColumn = Padding(
                    padding: EdgeInsets.only(top: wd.textHalfLeading),
                    child: SizedBox(
                      width: wd.imageWidth,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: <Widget>[
                          Container(
                            key: const ValueKey<String>('test_image'),
                            width: wd.imageWidth,
                            height: wd.imageHeight,
                            color: CupertinoColors.systemGrey4,
                          ),
                          if (captionText.trim().isNotEmpty)
                            Padding(
                              key: const ValueKey<String>('test_caption_wrap'),
                              padding: EdgeInsets.only(top: wd.captionSpacing),
                              child: SizedBox(
                                key: const ValueKey<String>('test_caption_text'),
                                height: wd.captionHeight,
                              ),
                            ),
                        ],
                      ),
                    ),
                  );

                  return ArticleWrapParagraphEditor(
                    groupId: 'test',
                    narrowText: wrapResult.leadingText,
                    belowText: wrapResult.trailingText,
                    imageChild: imageColumn,
                    imageWidth: wd.imageWidth,
                    narrowWidth: wd.besideWidth,
                    gap: wd.sideGap,
                    isLeft: imageLayout == 'wrapLeft',
                    floatHeight: wd.besideHeight,
                    maxLinesBeside: wd.maxLinesBeside,
                    belowSpacing: wd.sameParagraphSpacing,
                    style: bodyStyle,
                    placeholderStyle: const TextStyle(
                      fontSize: 16,
                      color: CupertinoColors.placeholderText,
                    ),
                    placeholder: placeholder,
                    onChanged: (_, __) {},
                    onFocused: (_) {},
                    onSelectionChanged: (_, __) {},
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

void main() {
  const fontSize = 16.0;
  const styleHeight = 1.82;
  const lineHeight = fontSize * styleHeight; // 29.12
  const halfLeading = (lineHeight - fontSize) / 2; // 6.56

  final longText = 'abcdefghijklmnopqrstuvwxyz' * 20;

  // ── 像素级对齐：多屏幕宽度 × 有/无配文 ──

  for (final imageLayout in <String>['wrapLeft', 'wrapRight']) {
    for (final width in <double>[280, 340, 430]) {
      group('$imageLayout 宽度=$width 无配文', () {
      testWidgets('顶部对齐', (tester) async {
        await tester.pumpWidget(_RealChainHarness(
          text: longText,
          captionText: '',
          contentWidth: width,
          imageLayout: imageLayout,
        ));
        await tester.pumpAndSettle();

        final imageTop = tester
            .getTopLeft(find.byKey(const ValueKey<String>('test_image')))
            .dy;
        final narrowTop = tester
            .getTopLeft(
                find.byKey(const ValueKey<String>('wrap_narrow_test')))
            .dy;
        final textVisualTop = narrowTop + halfLeading;
        final diff = (imageTop - textVisualTop).abs();
        expect(diff, lessThanOrEqualTo(1.0),
            reason: 'w=$width 图片顶 $imageTop ≈ 文字视觉顶 $textVisualTop');
      });

      testWidgets('底部对齐', (tester) async {
        await tester.pumpWidget(_RealChainHarness(
          text: longText,
          captionText: '',
          contentWidth: width,
          imageLayout: imageLayout,
        ));
        await tester.pumpAndSettle();

        final imageBottom = tester
            .getRect(find.byKey(const ValueKey<String>('test_image')))
            .bottom;
        final narrowBottom = tester
            .getRect(
                find.byKey(const ValueKey<String>('wrap_narrow_test')))
            .bottom;
        final textVisualBottom = narrowBottom - halfLeading;
        final diff = (imageBottom - textVisualBottom).abs();
        expect(diff, lessThanOrEqualTo(1.0),
            reason: 'w=$width 图片底 $imageBottom ≈ 文字视觉底 $textVisualBottom');
      });

      testWidgets('下方间距', (tester) async {
        await tester.pumpWidget(_RealChainHarness(
          text: longText,
          captionText: '',
          contentWidth: width,
          imageLayout: imageLayout,
        ));
        await tester.pumpAndSettle();

        final belowFinder =
            find.byKey(const ValueKey<String>('wrap_below_test'));
        if (!tester.any(belowFinder)) return; // 短文可能没有 below
        final narrowBottom = tester
            .getRect(
                find.byKey(const ValueKey<String>('wrap_narrow_test')))
            .bottom;
        final imageBottom = tester
            .getRect(find.byKey(const ValueKey<String>('test_image')))
            .bottom;
        final belowTop = tester.getRect(belowFinder).top;
        final rowBottom = math.max(imageBottom, narrowBottom);
        final expected = articleParagraphSpacing();
        final actual = belowTop - rowBottom;
        expect(actual, greaterThanOrEqualTo(expected - 2.0),
            reason: 'w=$width 下方间距 $actual ≥ $expected');
        expect(actual, lessThanOrEqualTo(expected + 2.0),
            reason: 'w=$width 下方间距 $actual ≤ $expected');
      });
      });

      group('$imageLayout 宽度=$width 有配文', () {
      testWidgets('顶部对齐', (tester) async {
        await tester.pumpWidget(_RealChainHarness(
          text: longText,
          captionText: '图片说明',
          contentWidth: width,
          imageLayout: imageLayout,
        ));
        await tester.pumpAndSettle();

        final imageTop = tester
            .getTopLeft(find.byKey(const ValueKey<String>('test_image')))
            .dy;
        final narrowTop = tester
            .getTopLeft(
                find.byKey(const ValueKey<String>('wrap_narrow_test')))
            .dy;
        final textVisualTop = narrowTop + halfLeading;
        final diff = (imageTop - textVisualTop).abs();
        expect(diff, lessThanOrEqualTo(1.0),
            reason: 'w=$width 有配文 图片顶 $imageTop ≈ 文字视觉顶 $textVisualTop');
      });

      testWidgets('底部对齐', (tester) async {
        await tester.pumpWidget(_RealChainHarness(
          text: longText,
          captionText: '图片说明',
          contentWidth: width,
          imageLayout: imageLayout,
        ));
        await tester.pumpAndSettle();

        final captionBottom = tester
            .getRect(
                find.byKey(const ValueKey<String>('test_caption_wrap')))
            .bottom;
        final narrowBottom = tester
            .getRect(
                find.byKey(const ValueKey<String>('wrap_narrow_test')))
            .bottom;
        final textVisualBottom = narrowBottom - halfLeading;
        final diff = (captionBottom - textVisualBottom).abs();
        expect(diff, lessThanOrEqualTo(1.0),
            reason:
                'w=$width 有配文 配文底 $captionBottom ≈ 文字视觉底 $textVisualBottom');
      });

      testWidgets('下方间距', (tester) async {
        await tester.pumpWidget(_RealChainHarness(
          text: longText,
          captionText: '图片说明',
          contentWidth: width,
          imageLayout: imageLayout,
        ));
        await tester.pumpAndSettle();

        final belowFinder =
            find.byKey(const ValueKey<String>('wrap_below_test'));
        if (!tester.any(belowFinder)) return;
        final captionBottom = tester
            .getRect(
                find.byKey(const ValueKey<String>('test_caption_wrap')))
            .bottom;
        final narrowBottom = tester
            .getRect(
                find.byKey(const ValueKey<String>('wrap_narrow_test')))
            .bottom;
        final belowTop = tester.getRect(belowFinder).top;
        final rowBottom = math.max(captionBottom, narrowBottom);
        final expected = articleParagraphSpacing();
        final actual = belowTop - rowBottom;
        expect(actual, greaterThanOrEqualTo(expected - 2.0),
            reason: 'w=$width 有配文 下方间距 $actual ≥ $expected');
        expect(actual, lessThanOrEqualTo(expected + 2.0),
            reason: 'w=$width 有配文 下方间距 $actual ≤ $expected');
      });
      });
    }
  }

  // ── placeholder 测试 ──

  group('placeholder', () {
    testWidgets('窄文为空时显示 placeholder', (tester) async {
      await tester.pumpWidget(const _RealChainHarness(
        text: '',
        captionText: '',
        placeholder: '+ 想写点什么',
      ));
      await tester.pumpAndSettle();

      expect(find.text('+ 想写点什么'), findsOneWidget);
    });

    testWidgets('窄文非空时不显示 placeholder', (tester) async {
      await tester.pumpWidget(_RealChainHarness(
        text: longText,
        captionText: '',
        placeholder: '+ 想写点什么',
      ));
      await tester.pumpAndSettle();

      expect(find.text('+ 想写点什么'), findsNothing);
    });
  });
}
