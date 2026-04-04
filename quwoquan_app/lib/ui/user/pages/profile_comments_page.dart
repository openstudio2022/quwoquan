import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/user/providers/profile_comments_provider.dart';

/// 评论收发列表；数据为 ContentRepository 返回的 CommentDto（非页内 Map）。
class ProfileCommentsPage extends ConsumerStatefulWidget {
  const ProfileCommentsPage({super.key});

  @override
  ConsumerState<ProfileCommentsPage> createState() =>
      _ProfileCommentsPageState();
}

class _ProfileCommentsPageState extends ConsumerState<ProfileCommentsPage>
    with SingleTickerProviderStateMixin {
  late final TabController _tabController;
  int _selectedTabIndex = 0;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(() {
      if (!mounted || _tabController.indexIsChanging) return;
      setState(() {
        _selectedTabIndex = _tabController.index;
      });
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(sentCommentsProvider.notifier).load();
      ref.read(receivedCommentsProvider.notifier).load();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

    return AppScaffold(
      navigationBar: AppNavigationBar(
        automaticallyImplyLeading: false,
        middle: Text(
          UITextConstants.comment,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      child: SafeArea(
          child: Column(
            children: [
              _buildTabBar(isDark),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _CommentsListView(
                      tab: _ProfileCommentsTabKind.sent,
                      isDark: isDark,
                    ),
                    _CommentsListView(
                      tab: _ProfileCommentsTabKind.received,
                      isDark: isDark,
                    ),
                  ],
                ),
              ),
            ],
          ),
      ),
    );
  }

  Widget _buildTabBar(bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Center(
        child: CupertinoSlidingSegmentedControl<int>(
          groupValue: _selectedTabIndex,
          children: const {
            0: Padding(
              padding: EdgeInsets.symmetric(horizontal: 20),
              child: Text(UITextConstants.profileCommentsTabSent),
            ),
            1: Padding(
              padding: EdgeInsets.symmetric(horizontal: 20),
              child: Text(UITextConstants.profileCommentsTabReceived),
            ),
          },
          onValueChanged: (index) {
            if (index == null) return;
            setState(() {
              _selectedTabIndex = index;
            });
            _tabController.animateTo(index);
          },
        ),
      ),
    );
  }
}

enum _ProfileCommentsTabKind { sent, received }

class _CommentsListView extends ConsumerWidget {
  const _CommentsListView({required this.tab, required this.isDark});

  final _ProfileCommentsTabKind tab;
  final bool isDark;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = tab == _ProfileCommentsTabKind.sent
        ? ref.watch(sentCommentsProvider)
        : ref.watch(receivedCommentsProvider);

    if (state.isLoading && state.comments.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.error != null && state.comments.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(UITextConstants.loadFailed,
                style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundSecondary))),
            SizedBox(height: AppSpacing.md),
            CupertinoButton(
              onPressed: () => _load(ref),
              child: Text(UITextConstants.retry),
            ),
          ],
        ),
      );
    }
    if (state.comments.isEmpty) {
      return Center(
        child: Text(UITextConstants.noComment,
            style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(
                    isDark, ColorType.foregroundSecondary))),
      );
    }

    return NotificationListener<ScrollNotification>(
      onNotification: (notification) {
        if (notification is ScrollEndNotification &&
            notification.metrics.pixels >=
                notification.metrics.maxScrollExtent - 200) {
          _loadMore(ref);
        }
        return false;
      },
      child: ListView.builder(
        padding: EdgeInsets.all(AppSpacing.md),
        itemCount: state.comments.length +
            (state.isLoadingMore ? 1 : 0),
        itemBuilder: (ctx, index) {
          if (index >= state.comments.length) {
            return Padding(
              padding: EdgeInsets.all(AppSpacing.md),
              child: const Center(child: CupertinoActivityIndicator()),
            );
          }
          return _ProfileCommentItem(
            comment: state.comments[index],
            isDark: isDark,
          );
        },
      ),
    );
  }

  void _load(WidgetRef ref) {
    if (tab == _ProfileCommentsTabKind.sent) {
      ref.read(sentCommentsProvider.notifier).load();
    } else {
      ref.read(receivedCommentsProvider.notifier).load();
    }
  }

  void _loadMore(WidgetRef ref) {
    if (tab == _ProfileCommentsTabKind.sent) {
      ref.read(sentCommentsProvider.notifier).loadMore();
    } else {
      ref.read(receivedCommentsProvider.notifier).loadMore();
    }
  }
}

class _ProfileCommentItem extends StatelessWidget {
  final CommentDto comment;
  final bool isDark;

  const _ProfileCommentItem({required this.comment, required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(
                isDark, ColorType.borderPrimary),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: AppSpacing.iconSmall,
                backgroundColor: AppColorsFunctional.getColor(
                    isDark, ColorType.backgroundSecondary),
                child: Icon(CupertinoIcons.person_fill,
                    size: AppSpacing.iconSmall,
                    color: AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundTertiary)),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  comment.displayName ?? comment.authorId,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    fontWeight: FontWeight.w500,
                    color: AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundSecondary),
                  ),
                ),
              ),
              Text(
                _formatTime(context, comment.createdAt),
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  color: AppColorsFunctional.getColor(
                      isDark, ColorType.foregroundTertiary),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.xs),
          Padding(
            padding: EdgeInsets.only(
                left: AppSpacing.iconSmall * 2 + AppSpacing.sm),
            child: Text(comment.content,
                style: TextStyle(fontSize: AppTypography.sm)),
          ),
        ],
      ),
    );
  }

  String _formatTime(BuildContext context, DateTime time) {
    final l10n = context.l10n;
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return l10n.justNow;
    if (diff.inHours < 1) return l10n.minutesAgoTemplate(diff.inMinutes);
    if (diff.inDays < 1) return l10n.hoursAgoTemplate(diff.inHours);
    if (diff.inDays < 30) return l10n.daysAgoTemplate(diff.inDays);
    return l10n.monthDayTemplate(time.month, time.day);
  }
}
