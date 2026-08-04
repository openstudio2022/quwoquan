import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/content/footprint_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/user/providers/my_footprint_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';

/// 我的主页一级「足迹」Tab。
///
/// 数据仍由 `FootprintRepository` 统一提供；这里只负责把独立足迹页的只读列表
/// 内嵌到主页一级 tab，避免把浏览历史塞进 profile 首屏 CTA。
class ProfileFootprintTab extends ConsumerStatefulWidget {
  const ProfileFootprintTab({
    super.key,
    required this.isDark,
    this.onSecondaryHorizontalDragEnd,
  });

  final bool isDark;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;

  @override
  ConsumerState<ProfileFootprintTab> createState() =>
      _ProfileFootprintTabState();
}

class _ProfileFootprintTabState extends ConsumerState<ProfileFootprintTab> {
  static const List<String> _tabIds = <String>[
    'all',
    'viewed',
    'liked',
    'commented',
    'shared',
  ];

  String _selectedTabId = 'all';

  String get _selectedType => _selectedTabId == 'all' ? '' : _selectedTabId;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(
      () => ref.read(myFootprintListProvider.notifier).load(),
    );
  }

  UiErrorSemantic _resolveErrorSemantic(Object error) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  void _selectTab(String tabId) {
    if (tabId == _selectedTabId) return;
    setState(() => _selectedTabId = tabId);
    ref.read(myFootprintListProvider.notifier).load(type: _selectedType);
  }

  void _openEntry(FootprintEntry entry) {
    final id = entry.postId.trim();
    if (id.isEmpty) return;
    ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(id, referralSource: ReferralSource.authorProfile);
    context.push(AppRoutePaths.workBrowser(workId: id, source: 'profileTab'));
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(myFootprintListProvider);
    return Column(
      key: const ValueKey<String>('profile-footprint-tab'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ProfileSecondaryTabBar(
          tabs: _tabIds
              .map(
                (id) => ProfileSecondaryTabItem(
                  id: id,
                  label: id == 'all'
                      ? AppConceptConstants.all
                      : UITextConstants.footprintTypeLabel(id),
                ),
              )
              .toList(growable: false),
          selectedId: _selectedTabId,
          onSelected: _selectTab,
          isDark: widget.isDark,
          onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            0,
            AppSpacing.containerMd,
            AppSpacing.intraGroupSm,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Text(
                  FoundationText.myFootprintPrivacyHint,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.iosSecondaryLabel(context),
                    height: AppSpacing.textLineHeightCaption,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              CupertinoButton(
                key: const ValueKey<String>('profile-footprint-view-all'),
                padding: EdgeInsets.zero,
                minimumSize: Size.square(AppSpacing.minInteractiveSize),
                onPressed: () => context.push(
                  AppRoutePaths.myFootprint(
                    type: _selectedType.isEmpty ? null : _selectedType,
                  ),
                ),
                child: Text(
                  SearchText.searchViewAll,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ],
          ),
        ),
        _buildBody(context, state),
      ],
    );
  }

  Widget _buildBody(BuildContext context, MyFootprintListState state) {
    if (state.isLoading && state.items.isEmpty) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
        child: AppRequestFeedback.section(),
      );
    }
    if (state.rawError != null) {
      return AppPageErrorState(
        semantic: _resolveErrorSemantic(state.rawError!),
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
      return Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.interGroupXl,
        ),
        child: _FootprintEmptyCard(),
      );
    }
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.feedContentHorizontal(context),
        0,
        AppSpacing.feedContentHorizontal(context),
        AppSpacing.interGroupLg,
      ),
      child: Column(
        children: <Widget>[
          for (final entry in state.items) ...<Widget>[
            _FootprintInlineTile(entry: entry, onTap: () => _openEntry(entry)),
            SizedBox(height: AppSpacing.intraGroupSm),
          ],
          if (state.hasMore)
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: () =>
                  ref.read(myFootprintListProvider.notifier).loadMore(),
              child: state.isLoading
                  ? AppRequestFeedback.inline()
                  : Text(FoundationText.myFootprintLoadMore),
            ),
        ],
      ),
    );
  }
}

class _FootprintEmptyCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.10),
          width: AppSpacing.hairline,
        ),
      ),
      child: Text(
        FoundationText.myFootprintEmpty,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: AppTypography.iosSubheadline,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class _FootprintInlineTile extends StatelessWidget {
  const _FootprintInlineTile({required this.entry, required this.onTap});

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
    return Container(
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.10),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.018),
            blurRadius: AppSpacing.sm,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.containerXs,
          ),
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
                        height: AppSpacing.textLineHeightFootnote,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      <String>[
                        if (post != null && post.displayName.trim().isNotEmpty)
                          post.displayName.trim(),
                        _relativeTime(context),
                      ].where((text) => text.trim().isNotEmpty).join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconXSmall,
                color: AppColors.iosQuaternaryLabel(context),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
