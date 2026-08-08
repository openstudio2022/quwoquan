import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/di/chat_presentation_slots.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_suggestion_view.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/recent_search_read_presentation.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/application/public/recent_search_entry_view.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_coordinator.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_inspiration_models.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_session_state.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_suggestion_models.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';

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
