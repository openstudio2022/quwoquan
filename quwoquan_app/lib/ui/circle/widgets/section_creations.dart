import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/content/content/post/presentation/post_preview_card.dart';
import 'package:quwoquan_app/content/content/post/presentation/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/circle/circle_management/circle/domain/circle_tab.dart';
import 'package:quwoquan_app/content/content/post/domain/content_surface_view_mapper.dart';
import 'package:quwoquan_app/content/media/media_asset/application/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_reason_chip.dart';
import 'package:quwoquan_app/content/content/post/presentation/record_post_card.dart';
import 'package:quwoquan_app/components/object_page/object_secondary_filter_bar.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/content/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/circle/circle_management/circle/domain/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/circle/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
part 'section_creations_state.dart';
part 'section_creations_state_helpers.dart';

enum _CirclePostManagementAction { pin, feature, remove }

/// 圈子"创作"板块：SubTab 过滤 + 排序 + 二列网格。
///
/// 主数据为 [CircleHubFeedPostEntry]：内容事实读取 [ContentPostViewData]，展示字段读取
/// metadata 生成的 typed presentation，互动结果写回页面模型快照。
class SectionCreations extends ConsumerStatefulWidget {
  const SectionCreations({
    super.key,
    required this.circleId,
    required this.isDark,
    required this.role,
    this.inlineScroll = false,
  });

  final String circleId;
  final bool isDark;
  final CircleRole role;
  final bool inlineScroll;

  @override
  ConsumerState<SectionCreations> createState() => _SectionCreationsState();
}

class _ViewModeButton extends StatelessWidget {
  const _ViewModeButton({
    required this.icon,
    required this.tooltip,
    required this.selected,
    required this.fgSecondary,
    required this.borderColor,
    required this.backgroundColor,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final bool selected;
  final Color fgSecondary;
  final Color borderColor;
  final Color backgroundColor;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onPressed,
        child: Container(
          padding: EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: selected
                ? AppColors.primaryColor.withValues(alpha: 0.12)
                : backgroundColor,
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
            border: Border.all(
              color: selected
                  ? AppColors.primaryColor.withValues(alpha: 0.24)
                  : borderColor.withValues(alpha: 0.12),
            ),
          ),
          child: Icon(
            icon,
            size: AppSpacing.iconSmall,
            color: selected ? AppColors.primaryColor : fgSecondary,
          ),
        ),
      ),
    );
  }
}
