import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/avatar/conversation_avatar.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/ui/search/models/recent_search_read_presentation.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/models/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/ui/search/providers/search_coordinator.dart';

part 'global_search_page_history_widgets.dart';
part 'global_search_page_inspiration_widgets.dart';
part 'global_search_page_state.dart';
part 'global_search_page_state_history.dart';
part 'global_search_page_state_navigation.dart';
part 'global_search_page_state_suggestions.dart';
part 'global_search_page_suggestion_widgets.dart';

/// 搜索域统一语义 token。
///
/// 字体四级：
/// - L1 区块标题 [sectionTitleSize] + [sectionTitleWeight] + foregroundPrimary
/// - L2 正文/列表主文本 [bodySize] + [bodyWeight] + foregroundPrimary
/// - L4 辅助说明 [captionSize] + [bodyWeight] + foregroundSecondary
///
/// 低频工具栏：[toolbarSize] + [toolbarWeight] + foregroundTertiary，
/// 删除态操作 [toolbarSize] + [toolbarActionWeight] + foregroundSecondary。
///
/// 颜色三级：主文本 foregroundPrimary / 辅助 foregroundSecondary /
/// 低频工具栏与占位 foregroundTertiary；仅提交与可点链接使用 primaryColor。
class _SearchTokens {
  _SearchTokens._();

  // ===== 字体层级 =====
  static const double sectionTitleSize = AppTypography.iosBody; // L1 17
  static const FontWeight sectionTitleWeight = AppTypography.semiBold;
  static const double bodySize = AppTypography.iosCallout; // L2 16
  static const double captionSize = AppTypography.iosCaption1; // L4 12
  static const double toolbarSize = AppTypography.iosSubheadline; // 工具栏 15
  static const FontWeight bodyWeight = AppTypography.regular;
  static const FontWeight toolbarWeight = AppTypography.regular;
  static const FontWeight toolbarActionWeight = AppTypography.medium;

  // ===== 间距层级 =====
  static const double headerContentGap = AppSpacing.intraGroupSm;
  static const double sectionGap = AppSpacing.interGroupLg;
  static const double historyColumnGap = AppSpacing.interGroupMd;
  static const double historyRowGap = AppSpacing.intraGroupLg;

  /// 搜索页正文左右边距：窄屏 containerMd，宽屏 containerLg。
  static double contentHorizontal(BuildContext context) =>
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.containerMd,
        regular: AppSpacing.containerMd,
        expanded: AppSpacing.containerLg,
      );
}

enum _SearchHomeTab { guess, circles, locations }

class GlobalSearchPage extends ConsumerStatefulWidget {
  const GlobalSearchPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<GlobalSearchPage> createState() => _GlobalSearchPageState();
}
