import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/footprint_repository.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show contentBehaviorTrackerProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/my_footprint_provider.dart';

/// 「我的足迹」只读列表页（WP1·T5）。
///
/// 足迹是自动形成的私有消费轨迹（看过/赞过/评论过/转发过），仅本人可见、
/// 只读、不产生交集与影响事实。type 枚举与行为映射由云侧唯一定义，
/// 端侧只透传 type 并展示云端下发数据。
/// 路由：/profile/footprint?type=viewed|liked|commented|shared
class MyFootprintPage extends ConsumerStatefulWidget {
  const MyFootprintPage({super.key, this.type = ''});

  final String type;

  @override
  ConsumerState<MyFootprintPage> createState() => _MyFootprintPageState();
}

class _MyFootprintPageState extends ConsumerState<MyFootprintPage> {
  /// 足迹 type 闭集（契约 GET /content/footprint 的 type 枚举），'' 表示全部。
  static const List<String> _typeTabs = <String>[
    '',
    'viewed',
    'liked',
    'commented',
    'shared',
  ];

  late String _selectedType;

  @override
  void initState() {
    super.initState();
    _selectedType = _typeTabs.contains(widget.type) ? widget.type : '';
    Future<void>.microtask(
      () =>
          ref.read(myFootprintListProvider.notifier).load(type: _selectedType),
    );
  }

  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  void _selectType(String type) {
    if (type == _selectedType) return;
    setState(() => _selectedType = type);
    ref.read(myFootprintListProvider.notifier).load(type: type);
  }

  void _openEntry(FootprintEntry entry) {
    final id = entry.postId.trim();
    if (id.isEmpty) return;
    // R21：足迹回访归因 authorProfile（个人档案域入口），交集链路不参与。
    ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(id, referralSource: ReferralSource.authorProfile);
    context.push(AppRoutePaths.workBrowser(workId: id, source: 'myFootprint'));
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColors.iosSystemBackground(context);
    final state = ref.watch(myFootprintListProvider);
    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: bg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          FoundationText.myFootprintTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm,
            ),
            child: _buildTypeSelector(context),
          ),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: Text(
              FoundationText.myFootprintPrivacyHint,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ),
          Expanded(child: _buildBody(context, state)),
        ],
      ),
    );
  }

  Widget _buildTypeSelector(BuildContext context) {
    return CupertinoSlidingSegmentedControl<String>(
      groupValue: _selectedType,
      children: <String, Widget>{
        for (final type in _typeTabs)
          type: Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            child: Text(
              type.isEmpty
                  ? AppConceptConstants.all
                  : UITextConstants.footprintTypeLabel(type),
              style: TextStyle(fontSize: AppTypography.iosFootnote),
            ),
          ),
      },
      onValueChanged: (value) => _selectType(value ?? ''),
    );
  }

  Widget _buildBody(BuildContext context, MyFootprintListState state) {
    if (state.isLoading && state.items.isEmpty) {
      return AppRequestFeedback.section();
    }
    if (state.rawError != null) {
      return AppPageErrorState(
        semantic: _resolvePageErrorSemantic(state.rawError!),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await ref
                .read(myFootprintListProvider.notifier)
                .load(type: _selectedType);
            return ref.read(myFootprintListProvider).rawError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    if (state.items.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: Text(
            FoundationText.myFootprintEmpty,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ),
      );
    }
    return ListView.separated(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      itemCount: state.items.length + (state.hasMore ? 1 : 0),
      separatorBuilder: (_, _) => Container(
        height: AppSpacing.hairline,
        color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
      ),
      itemBuilder: (_, index) {
        if (index >= state.items.length) {
          return _buildLoadMore(context, state);
        }
        return _FootprintEntryTile(
          entry: state.items[index],
          onTap: () => _openEntry(state.items[index]),
        );
      },
    );
  }

  Widget _buildLoadMore(BuildContext context, MyFootprintListState state) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      child: state.isLoading
          ? AppRequestFeedback.section()
          : CupertinoButton(
              onPressed: () =>
                  ref.read(myFootprintListProvider.notifier).loadMore(),
              child: Text(
                FoundationText.myFootprintLoadMore,
                style: TextStyle(fontSize: AppTypography.iosFootnote),
              ),
            ),
    );
  }
}

class _FootprintEntryTile extends StatelessWidget {
  const _FootprintEntryTile({required this.entry, required this.onTap});

  final FootprintEntry entry;
  final VoidCallback onTap;

  String _relativeTime(BuildContext context) {
    final time = DateTime.tryParse(entry.occurredAt);
    if (time == null) return '';
    final l10n = context.l10n;
    final diff = DateTime.now().toUtc().difference(time.toUtc());
    if (diff.inMinutes < 1) return l10n.justNow;
    if (diff.inHours < 1) return l10n.minutesAgoTemplate(diff.inMinutes);
    if (diff.inDays < 1) return l10n.hoursAgoTemplate(diff.inHours);
    if (diff.inDays < 30) return l10n.daysAgoTemplate(diff.inDays);
    final local = time.toLocal();
    return l10n.monthDayTemplate(local.month, local.day);
  }

  @override
  Widget build(BuildContext context) {
    final post = entry.post;
    final title = post == null
        ? entry.postId
        : (post.normalizedTitle.isNotEmpty
              ? post.normalizedTitle
              : post.displayName);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      onPressed: onTap,
      child: Row(
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: AppColors.iosLabel(context),
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  <String>[
                    if (post != null && post.displayName.trim().isNotEmpty)
                      post.displayName.trim(),
                    _relativeTime(context),
                  ].join(' · '),
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.iosSecondaryLabel(context),
                  ),
                ),
              ],
            ),
          ),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.iconXSmall,
            color: AppColors.iosTertiaryLabel(context),
          ),
        ],
      ),
    );
  }
}
