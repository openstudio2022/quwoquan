import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';

/// 首页频道展示策略。
///
/// 真相源来自 `content/content/post/ui_config.yaml` 生成的 [HomeChannelConfig]。
/// `template` 只作为远程覆盖缺字段时的兼容入口，真实布局由 layout policy 决定。
class HomeFeedLayoutPolicy {
  const HomeFeedLayoutPolicy({
    required this.layoutTemplate,
    required this.phoneColumns,
    required this.supportsFullSpanModules,
    required this.intersectionModulePolicy,
    required this.contentCardPolicy,
  });

  final String layoutTemplate;
  final int phoneColumns;
  final bool supportsFullSpanModules;
  final String intersectionModulePolicy;
  final String contentCardPolicy;

  factory HomeFeedLayoutPolicy.fromChannel(
    HomeChannelConfig? channel, {
    required String fallbackTemplate,
  }) {
    if (channel != null && channel.layoutTemplate.trim().isNotEmpty) {
      return HomeFeedLayoutPolicy(
        layoutTemplate: channel.layoutTemplate,
        phoneColumns: channel.phoneColumns.clamp(1, 2).toInt(),
        supportsFullSpanModules: channel.supportsFullSpanModules,
        intersectionModulePolicy: channel.intersectionModulePolicy,
        contentCardPolicy: channel.contentCardPolicy,
      );
    }
    return HomeFeedLayoutPolicy.fromTemplateFallback(fallbackTemplate);
  }

  factory HomeFeedLayoutPolicy.fromTemplateFallback(String template) {
    switch (template) {
      case 'single_column_relations':
        return const HomeFeedLayoutPolicy(
          layoutTemplate: 'singleColumnRelations',
          phoneColumns: 1,
          supportsFullSpanModules: false,
          intersectionModulePolicy: 'none',
          contentCardPolicy: 'richRelation',
        );
      case 'intersection_rail_masonry':
      case 'masonry_recommend':
      default:
        return const HomeFeedLayoutPolicy(
          layoutTemplate: 'singleColumnMultiForm',
          phoneColumns: 1,
          supportsFullSpanModules: false,
          intersectionModulePolicy: 'inlineOnly',
          contentCardPolicy: 'richMultiForm',
        );
    }
  }

  bool get isSingleColumnRelations => layoutTemplate == 'singleColumnRelations';

  bool get usesCompactDiscoveryCards =>
      contentCardPolicy == 'compactVisual' ||
      layoutTemplate == 'dualColumnDiscovery';

  /// 交集 spotlight 是否开启。真相源是频道配置的 `intersectionModulePolicy`
  /// （`none` / `inlineOnly` / `spotlightSegment`，见 content post `ui_config.yaml`
  /// 与远程覆盖），不在端上硬编码：`spotlightSegment` 才出横滑模块，
  /// `inlineOnly` 只在卡片内联句，`none` 完全不出。
  bool get hasIntersectionSpotlight =>
      intersectionModulePolicy == 'spotlightSegment';

  bool get insertsSegmentCards => false;

  int columnsFor(BuildContext context) {
    if (isSingleColumnRelations) return 1;
    final width = MediaQuery.sizeOf(context).width;
    if (width < AppSpacing.expandedBreakpoint) {
      return phoneColumns.clamp(1, 2).toInt();
    }
    return AppSpacing.responsiveGridColumns(context, availableWidth: width);
  }

  bool shouldRenderFullSpan(ContentPostViewData post) {
    if (!supportsFullSpanModules) return false;
    if (contentCardPolicy == 'articleFullSpan' && post.isArticleLike) {
      return true;
    }
    return false;
  }
}
