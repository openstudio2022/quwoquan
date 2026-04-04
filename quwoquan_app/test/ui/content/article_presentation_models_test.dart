import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

void main() {
  test('环绕布局在有一行配文时会按整行提升右侧高度并保留段落级续写间距', () {
    final bodyStyle = const TextStyle(
      fontSize: AppTypography.base,
      height: AppSpacing.textLineHeightArticleBody,
    );
    final captionStyle = const TextStyle(
      fontSize: AppTypography.sm,
      height: AppSpacing.textLineHeightLabel,
    );

    final wrap = resolveArticleWrapLayout(
      ArticleWrapLayoutInput(
        body:
            'sdsadasdassdasdsdasfjfsal;jflsakjdlkfjlaskdjfkffklsadlkjfljsdklfjadklfjsdfad;dfjssalkdjflk;sslf;asaaskdjasaaskdasaaskasaasasa',
        rowContentWidth: 520,
        bodyStyle: bodyStyle,
        captionText: 'dsafds',
        captionStyle: captionStyle,
        imageLayout: 'wrapLeft',
      ),
    );

    final lineHeight =
        (bodyStyle.fontSize ?? AppTypography.base) *
        (bodyStyle.height ?? AppSpacing.textLineHeightBody);
    expect(
      wrap.layout.besideHeight,
      greaterThanOrEqualTo(wrap.layout.maxLinesBeside * lineHeight - 0.01),
    );
    expect(wrap.layout.trailingSpacing, greaterThan(0));
    expect(wrap.leadingText.trim(), isNotEmpty);
  });

  test('纸张规格按单页宽度冻结，不再因矮舞台压缩纸面', () {
    final metrics = ArticleCanvasMetrics.snapshot();
    final tallFrame = metrics.frameSpecForViewport(const Size(398, 900));
    final roomyFrame = metrics.frameSpecForViewport(const Size(398, 700));
    final shortFrame = metrics.frameSpecForViewport(const Size(398, 360));

    expect(roomyFrame.paperSize.height, tallFrame.paperSize.height);
    expect(roomyFrame.contentSize.height, tallFrame.contentSize.height);
    expect(shortFrame.paperSize.height, tallFrame.paperSize.height);
    expect(shortFrame.contentSize.height, tallFrame.contentSize.height);
    expect(shortFrame.viewportSize.height, tallFrame.viewportSize.height);
  });
}
