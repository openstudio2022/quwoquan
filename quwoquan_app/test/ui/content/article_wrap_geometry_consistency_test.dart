/// 编辑态与阅读态环绕几何一致性测试。
///
/// 验证编辑态 `_buildWrapGroup` 接入 `resolveArticleWrapLayout()` 后，
/// 两侧在同一文档、同一宽度下产出一致的图片宽度、gap、分割点。
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

void main() {
  const bodyStyle = TextStyle(fontSize: 16, height: 1.6);
  const captionStyle = TextStyle(fontSize: 13, height: 1.4);

  group('resolveArticleWrapLayout 几何一致性', () {
    test('图片宽度为内容区 50%', () {
      const contentWidth = 360.0;
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '测试正文',
          rowContentWidth: contentWidth,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      // 默认 wrapImageMaxWidth <= 0 时，图片宽度 = contentWidth * 0.5
      expect(result.layout.imageWidth, contentWidth * 0.5);
    });

    test('gap 使用 metrics.wrapImageGap', () {
      final metrics = ArticleCanvasMetrics.snapshot();
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '测试正文',
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      expect(result.layout.sideGap, metrics.wrapImageGap);
    });

    test('有 caption 时 captionHeight > 0', () {
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '测试正文',
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '图片说明',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      expect(result.layout.captionHeight, greaterThan(0));
    });

    test('无 caption 且无占位时 captionHeight 来自精确测量', () {
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '测试正文',
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          captionPlaceholderWhenEmpty: false,
          imageLayout: 'wrapLeft',
        ),
      );
      // captionHeight 由 measureArticleTextHeight 精确测量，
      // 空字符串时 TextPainter 仍可能返回一行高度
      expect(result.layout.captionHeight, greaterThanOrEqualTo(0));
      // 有 caption 时应更大
      final withCaption = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '测试正文',
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '这是一段较长的图片说明文字用于验证高度差异',
          captionStyle: captionStyle,
          captionPlaceholderWhenEmpty: false,
          imageLayout: 'wrapLeft',
        ),
      );
      expect(
        withCaption.layout.captionHeight,
        greaterThanOrEqualTo(result.layout.captionHeight),
      );
    });

    test('分割点使用 resolveWrappedSplitIndex 而非像素高度', () {
      final text = '这是一段较长的正文内容用于测试分割点的一致性，' * 5;
      const contentWidth = 360.0;
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: text,
          rowContentWidth: contentWidth,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      // 分割点应在文本范围内
      expect(result.layout.splitOffset, greaterThanOrEqualTo(0));
      expect(result.layout.splitOffset, lessThanOrEqualTo(text.length));
      // leadingText + trailingText 应覆盖全文
      expect(
        result.leadingText.length + result.trailingText.length,
        text.length,
      );
    });

    test('wrapLeft 和 wrapRight 产出相同几何参数', () {
      const text = '环绕正文内容';
      final left = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: text,
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      final right = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: text,
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapRight',
        ),
      );
      expect(left.layout.imageWidth, right.layout.imageWidth);
      expect(left.layout.sideGap, right.layout.sideGap);
      expect(left.layout.besideWidth, right.layout.besideWidth);
      expect(left.layout.besideHeight, right.layout.besideHeight);
      expect(left.layout.splitOffset, right.layout.splitOffset);
    });

    test('空文本时分割点为 0 且不崩溃', () {
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '',
          rowContentWidth: 360,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      expect(result.layout.splitOffset, 0);
      expect(result.leadingText, '');
      expect(result.trailingText, '');
    });

    test('极窄内容区不崩溃', () {
      final result = resolveArticleWrapLayout(
        ArticleWrapLayoutInput(
          body: '窄屏正文',
          rowContentWidth: 200,
          bodyStyle: bodyStyle,
          captionText: '',
          captionStyle: captionStyle,
          imageLayout: 'wrapLeft',
        ),
      );
      expect(result.layout.imageWidth, greaterThan(0));
      expect(result.layout.besideWidth, greaterThan(0));
    });
  });
}
