import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 首页频道展示策略。
///
/// 真相源来自 `content/post/ui_config.yaml` 生成的 [HomeChannelConfig]。
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
        return const HomeFeedLayoutPolicy(
          layoutTemplate: 'dualColumnDiscovery',
          phoneColumns: 2,
          supportsFullSpanModules: true,
          intersectionModulePolicy: 'spotlightSegment',
          contentCardPolicy: 'compactVisual',
        );
      case 'masonry_recommend':
      default:
        return const HomeFeedLayoutPolicy(
          layoutTemplate: 'dualColumnDiscovery',
          phoneColumns: 2,
          supportsFullSpanModules: true,
          intersectionModulePolicy: 'segmentInsert',
          contentCardPolicy: 'compactVisual',
        );
    }
  }

  bool get isSingleColumnRelations => layoutTemplate == 'singleColumnRelations';

  bool get usesCompactDiscoveryCards =>
      contentCardPolicy == 'compactVisual' ||
      layoutTemplate == 'dualColumnDiscovery';

  bool get hasIntersectionSpotlight =>
      supportsFullSpanModules &&
      intersectionModulePolicy != 'none' &&
      intersectionModulePolicy != 'inlineOnly';

  bool get insertsSegmentCards =>
      supportsFullSpanModules &&
      (intersectionModulePolicy == 'spotlightSegment' ||
          intersectionModulePolicy == 'campusSpotlight' ||
          intersectionModulePolicy == 'segmentInsert');

  int columnsFor(BuildContext context) {
    if (isSingleColumnRelations) return 1;
    final width = MediaQuery.sizeOf(context).width;
    if (width < AppSpacing.expandedBreakpoint) {
      return phoneColumns.clamp(1, 2).toInt();
    }
    return AppSpacing.responsiveGridColumns(context, availableWidth: width);
  }

  bool shouldRenderFullSpan(PostBaseDto post) {
    if (!supportsFullSpanModules) return false;
    if (contentCardPolicy == 'articleFullSpan' && post.isArticleLike) {
      return true;
    }
    return false;
  }
}
