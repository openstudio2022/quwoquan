import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_font_families.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';

/// 富块（quote / callout / codeBlock）容器几何与文本样式派生的唯一真相源
/// （GWT-003）：分页测量引擎与阅读渲染必须消费同一份定义，否则会出现
/// 「测量按纯文本、渲染带容器」的分页溢出。
abstract final class ArticleRichBlockChrome {
  /// 引用条宽度与其与正文的间距。
  static const double quoteBarWidth = AppSpacing.three;
  static const double quoteGap = AppSpacing.containerSm;

  /// callout / codeBlock 卡面内边距。
  static const EdgeInsets calloutPadding = EdgeInsets.symmetric(
    horizontal: AppSpacing.containerSm,
    vertical: AppSpacing.intraGroupSm,
  );
  static const EdgeInsets codePadding = EdgeInsets.symmetric(
    horizontal: AppSpacing.containerSm,
    vertical: AppSpacing.intraGroupSm,
  );

  static bool isRichBlockType(ArticleDocumentBlockType type) {
    return type == ArticleDocumentBlockType.quote ||
        type == ArticleDocumentBlockType.callout ||
        type == ArticleDocumentBlockType.codeBlock;
  }

  /// 测量/渲染共用：容器占用的水平内缩总量。
  static double horizontalInsetFor(ArticleDocumentBlockType type) {
    return switch (type) {
      ArticleDocumentBlockType.quote => quoteBarWidth + quoteGap,
      ArticleDocumentBlockType.callout => calloutPadding.horizontal,
      ArticleDocumentBlockType.codeBlock => codePadding.horizontal,
      _ => 0,
    };
  }

  /// 测量/渲染共用：容器占用的垂直额外高度。
  static double verticalPaddingFor(ArticleDocumentBlockType type) {
    return switch (type) {
      ArticleDocumentBlockType.callout => calloutPadding.vertical,
      ArticleDocumentBlockType.codeBlock => codePadding.vertical,
      _ => 0,
    };
  }

  /// 测量/渲染共用：富块文本样式派生（quote 弱化、code 等宽小号）。
  static TextStyle textStyleFor(
    ArticleDocumentBlockType type,
    TextStyle bodyStyle,
  ) {
    final bodyFont = bodyStyle.fontSize ?? AppTypography.base;
    return switch (type) {
      ArticleDocumentBlockType.quote => bodyStyle.copyWith(
        color: bodyStyle.color?.withValues(alpha: 0.78),
        fontStyle: FontStyle.italic,
      ),
      ArticleDocumentBlockType.callout => bodyStyle,
      ArticleDocumentBlockType.codeBlock => bodyStyle.copyWith(
        fontSize: bodyFont * 0.88,
        fontFamily: BundledFontFamilies.notoSansMono,
        fontFamilyFallback: const <String>[BundledFontFamilies.notoSansMono],
        height: AppTypography.bodyLineHeight,
      ),
      _ => bodyStyle,
    };
  }
}
