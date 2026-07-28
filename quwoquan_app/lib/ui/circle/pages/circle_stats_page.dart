// ignore_for_file: unnecessary_underscores, deprecated_member_use

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_list_view_data.dart';
import 'package:quwoquan_app/ui/circle/services/circle_stats_row_wire.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子成员/群聊/粉丝/获赞列表页（1:1 对应 AuthorStatsList 的 members/groups/fans/likes 圈子维度）
/// 路由：/circle/:id/stats?type=members|groups|fans|likes
class CircleStatsPage extends ConsumerStatefulWidget {
  const CircleStatsPage({
    super.key,
    required this.circleId,
    this.type = 'members',
  });

  final String circleId;
  final String type;

  static String _title(String type) {
    switch (type) {
      case 'members':
        return CommunityText.circleMembers;
      case 'groups':
        return CommunityText.circleGroups;
      case 'fans':
        return CommunityText.circleFans;
      case 'likes':
        return CommunityText.circleLikes;
      default:
        return CommunityText.circleMembers;
    }
  }

  static String _searchHint(String type) {
    switch (type) {
      case 'members':
        return CommunityText.searchMembersHint;
      case 'groups':
        return CommunityText.searchGroupsHint;
      case 'fans':
        return CommunityText.searchFansHint;
      case 'likes':
        return CommunityText.searchLikesHint;
      default:
        return CommunityText.searchMembersHint;
    }
  }

  @override
  ConsumerState<CircleStatsPage> createState() => _CircleStatsPageState();
}

class _CircleStatsPageState extends ConsumerState<CircleStatsPage> {
  String get _type => widget.type;
  String _searchQuery = '';
  bool _isLoading = true;
  UiErrorSemantic? _pageErrorSemantic;

  List<CircleStatsMemberRowViewData> _users = [];
  List<CircleStatsGroupRowViewData> _groups = [];
  List<CircleStatsLikeRowViewData> _likes = [];

  UiErrorSemantic _resolvePageErrorSemantic(Object error) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  // R20 页面曝光/停留：对象子页以 circleId 为主体走行为通道。
  late final DateTime _pageEnteredAt;
  ContentBehaviorTracker? _behaviorTracker;

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    unawaited(_loadFromRepository());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _behaviorTracker = ref.read(contentBehaviorTrackerProvider);
      _behaviorTracker!.trackImpression(
        widget.circleId,
        contentType: 'circle_stats_page',
        tags: <String>[_type],
        referralSource: ReferralSource.circlePost,
      );
    });
  }

  @override
  void dispose() {
    _behaviorTracker?.trackDwell(
      widget.circleId,
      durationSeconds:
          DateTime.now().difference(_pageEnteredAt).inMilliseconds / 1000.0,
      contentType: 'circle_stats_page',
      tags: <String>[_type],
      referralSource: ReferralSource.circlePost,
    );
    super.dispose();
  }

  Future<void> _loadFromRepository() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _pageErrorSemantic = null;
      });
    }
    try {
      switch (_type) {
        case 'groups':
          final groups = await ref
              .read(circleStatsGroupQueryProvider)
              .list(
                CircleGroupListQuery(circleId: widget.circleId, limit: 100),
              );
          if (!mounted) {
            return;
          }
          setState(() {
            _groups = groups.items
                .map(circleStatsGroupRowFromGroupSlice)
                .toList(growable: false);
            _pageErrorSemantic = null;
            _isLoading = false;
          });
          break;
        case 'likes':
          if (!mounted) {
            return;
          }
          setState(() {
            _likes = const [];
            _pageErrorSemantic = null;
            _isLoading = false;
          });
          break;
        case 'members':
        case 'fans':
        default:
          final roster = await ref
              .read(circleStatsMembershipQueryProvider)
              .listMemberships(
                CircleMembershipListQuery(
                  circleId: widget.circleId,
                  limit: 100,
                ),
              );
          if (!mounted) {
            return;
          }
          setState(() {
            _users = roster.items
                .map(circleStatsMemberRowFromMembership)
                .toList(growable: false);
            _pageErrorSemantic = null;
            _isLoading = false;
          });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _users = [];
        _groups = [];
        _likes = [];
        _pageErrorSemantic = _resolvePageErrorSemantic(error);
        _isLoading = false;
      });
    }
  }

  List<CircleStatsMemberRowViewData> get _filteredUsers {
    if (_searchQuery.isEmpty) return _users;
    final q = _searchQuery.toLowerCase();
    return _users.where((u) => u.name.toLowerCase().contains(q)).toList();
  }

  List<CircleStatsGroupRowViewData> get _filteredGroups {
    if (_searchQuery.isEmpty) return _groups;
    final q = _searchQuery.toLowerCase();
    return _groups.where((u) => u.name.toLowerCase().contains(q)).toList();
  }

  List<CircleStatsLikeRowViewData> get _filteredLikes {
    if (_searchQuery.isEmpty) return _likes;
    final q = _searchQuery.toLowerCase();
    return _likes.where((i) => i.userName.toLowerCase().contains(q)).toList();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        backgroundColor: cardBg.withValues(alpha: 0.94),
        border: Border(
          bottom: BorderSide(
            color: borderColor.withValues(alpha: 0.25),
            width: AppSpacing.hairline,
          ),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () => context.pop(),
        ),
        middle: Text(
          CircleStatsPage._title(_type),
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              AppSpacing.containerSm,
            ),
            child: AppSearchField(
              onChanged: (v) => setState(() => _searchQuery = v),
              placeholder: CircleStatsPage._searchHint(_type),
            ),
          ),
          Expanded(
            child: _isLoading
                ? AppRequestFeedback.section()
                : _pageErrorSemantic != null
                ? AppPageErrorState(
                    semantic: _pageErrorSemantic!,
                    onAction: (action) async {
                      if (action.type == UiErrorActionType.retry ||
                          action.type == UiErrorActionType.resubmit) {
                        await _loadFromRepository();
                      }
                    },
                  )
                : _type == 'likes'
                ? _buildLikesList(fg, fgSecondary, borderColor, bg)
                : _type == 'groups'
                ? _buildGroupsList(fg, fgSecondary, borderColor)
                : _buildUsersList(fg, fgSecondary, borderColor, bg),
          ),
        ],
      ),
    );
  }

  Widget _buildUsersList(
    Color fg,
    Color fgSecondary,
    Color borderColor,
    Color bg,
  ) {
    final list = _filteredUsers;
    if (list.isEmpty) {
      return Center(
        child: Text(
          CommunityText.noData,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final u = list[i];
        final name = u.name;
        final avatar = u.avatarUrl;
        final worksCount = u.worksCountLabel;
        final fansCount = u.fansCountLabel;
        final likesCount = u.likesCountLabel;
        final isFollowed = u.isFollowed;
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: bg,
            child: CupertinoButton(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () {},
              child: Row(
                children: [
                  AppCircularAvatar(
                    imageUrl: avatar,
                    size: AppSpacing.lg * 2,
                    backgroundColor: AppColors.iosFill(context),
                    fallback: Icon(CupertinoIcons.person, color: fgSecondary),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.extraBold,
                            color: fg,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          '$worksCount 作品 · $fansCount 粉丝 · $likesCount 获赞',
                          style: TextStyle(
                            fontSize: AppTypography.xsPlus,
                            fontWeight: AppTypography.bold,
                            color: fgSecondary,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  CupertinoButton(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.md,
                      vertical: AppSpacing.sm,
                    ),
                    color: isFollowed
                        ? borderColor.withValues(alpha: 0.18)
                        : AppColors.primaryColor.withValues(alpha: 0.12),
                    minimumSize: Size(
                      AppSpacing.largeButtonSize + AppSpacing.lg,
                      AppSpacing.xl,
                    ),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.circularBorderRadius,
                    ),
                    onPressed: () {
                      setState(() {
                        final idx = _users.indexWhere((e) => e.id == u.id);
                        if (idx >= 0) {
                          final row = _users[idx];
                          row.isFollowed = !row.isFollowed;
                        }
                      });
                    },
                    child: Text(
                      isFollowed
                          ? FoundationText.following
                          : FoundationText.follow,
                      style: TextStyle(
                        fontSize: AppTypography.xsPlus,
                        fontWeight: AppTypography.extraBold,
                        color: isFollowed
                            ? fgSecondary
                            : AppColors.primaryColor,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildGroupsList(Color fg, Color fgSecondary, Color borderColor) {
    final list = _filteredGroups;
    if (list.isEmpty) {
      return Center(
        child: Text(
          CommunityText.noData,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final g = list[i];
        final name = g.name;
        final count = g.memberCountLabel;
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: AppColors.transparent,
            child: CupertinoButton(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () {},
              child: Row(
                children: [
                  Container(
                    width: AppSpacing.largeButtonSize,
                    height: AppSpacing.largeButtonSize,
                    decoration: BoxDecoration(
                      color: borderColor.withValues(alpha: 0.16),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.largeBorderRadius,
                      ),
                    ),
                    child: Icon(
                      CupertinoIcons.group,
                      color: fgSecondary,
                      size: AppSpacing.iconMedium + AppSpacing.xs,
                    ),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.extraBold,
                            color: fg,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          '$count 人',
                          style: TextStyle(
                            fontSize: AppTypography.xsPlus,
                            fontWeight: AppTypography.bold,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    CupertinoIcons.chevron_forward,
                    color: fgSecondary,
                    size: AppSpacing.iconMedium,
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildLikesList(
    Color fg,
    Color fgSecondary,
    Color borderColor,
    Color bg,
  ) {
    final list = _filteredLikes;
    if (list.isEmpty) {
      return Center(
        child: Text(
          CommunityText.noLikesRecord,
          style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      itemCount: list.length,
      itemBuilder: (context, i) {
        final item = list[i];
        final userName = item.userName;
        final userAvatar = item.userAvatarUrl;
        final content = item.content;
        final targetTitle = item.targetTitle;
        final time = item.time;
        return Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: _buildCard(
            borderColor: borderColor,
            backgroundColor: bg,
            child: CupertinoButton(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              onPressed: () {},
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  AppCircularAvatar(
                    imageUrl: userAvatar,
                    size: AppSpacing.lg * 2,
                    backgroundColor: AppColors.iosFill(context),
                    fallback: Icon(CupertinoIcons.person, color: fgSecondary),
                  ),
                  SizedBox(width: AppSpacing.largeBorderRadius),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                userName,
                                style: TextStyle(
                                  fontSize: AppTypography.lg,
                                  fontWeight: AppTypography.extraBold,
                                  color: fg,
                                ),
                              ),
                            ),
                            SizedBox(width: AppSpacing.sm),
                            Text(
                              time,
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                fontWeight: AppTypography.bold,
                                color: fgSecondary,
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          content,
                          style: TextStyle(
                            fontSize: AppTypography.smPlus,
                            fontWeight: AppTypography.semiBold,
                            color: fgSecondary,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        SizedBox(height: AppSpacing.sm),
                        Container(
                          padding: EdgeInsets.all(AppSpacing.largeBorderRadius),
                          decoration: BoxDecoration(
                            color: bg.withValues(alpha: 0.72),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.largeBorderRadius,
                            ),
                            border: Border.all(
                              color: borderColor.withValues(alpha: 0.22),
                            ),
                          ),
                          child: Text(
                            targetTitle,
                            style: TextStyle(
                              fontSize: AppTypography.xsPlus,
                              fontWeight: AppTypography.bold,
                              color: fgSecondary,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildCard({
    required Color borderColor,
    required Color backgroundColor,
    required Widget child,
  }) {
    return Container(
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: borderColor.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.05),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
