import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子互动板块：点赞/评论流（含独立 loading/error 状态）
class SectionInteraction extends ConsumerStatefulWidget {
  const SectionInteraction({
    super.key,
    required this.circleId,
    required this.isDark,
  });

  final String circleId;
  final bool isDark;

  @override
  ConsumerState<SectionInteraction> createState() => _SectionInteractionState();
}

/// 互动行展示模型（由 [PostBaseDto] 或本地占位数据构造，避免 UI 层 Map 按键漂移）。
class _InteractionRow {
  const _InteractionRow({
    required this.userName,
    required this.avatar,
    required this.time,
    required this.action,
    required this.target,
  });

  final String userName;
  final String avatar;
  final String time;
  final String action;
  final String target;

  factory _InteractionRow.fromPost(PostBaseDto p) {
    return _InteractionRow(
      userName: p.displayName,
      avatar: p.avatarUrl,
      time: '',
      action: '发布了',
      target: p.normalizedTitle.isNotEmpty ? p.normalizedTitle : p.type,
    );
  }
}

class _SectionInteractionState extends ConsumerState<SectionInteraction> {
  String _activeSubTab = 'likes';
  bool _isLoading = true;
  UiErrorSemantic? _errorSemantic;
  List<_InteractionRow> _interactions = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadInteractions());
  }

  Future<void> _loadInteractions() async {
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
    });
    try {
      final repo = ref.read(circleRepositoryProvider);
      final feed = await repo.getCircleFeed(widget.circleId);
      if (mounted) {
        setState(() {
          _interactions = feed
              .map(_InteractionRow.fromPost)
              .toList(growable: false);
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorSemantic = runtimeErrorSemantic(
            context,
            error: e,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );
        });
      }
    }
  }

  // Fallback mock data when feed is empty
  List<_InteractionRow> get _displayInteractions {
    if (_interactions.isNotEmpty) {
      return _interactions;
    }
    return const [
      _InteractionRow(
        userName: '陈一发',
        avatar:
            'media/avatar/s/mock/seed/u_1630939687530-241d630735df/v1/avatar.jpg',
        action: '赞了',
        target: '《川西秘境摄影集》',
        time: '14:20',
      ),
      _InteractionRow(
        userName: '王小明',
        avatar:
            'media/avatar/s/mock/seed/u_1643816831234-e7cb32194e92/v1/avatar.jpg',
        action: '评论了',
        target: '器材交流帖',
        time: '10:05',
      ),
      _InteractionRow(
        userName: '李青云',
        avatar:
            'media/avatar/s/mock/seed/u_1603110502322-93cd2173d19a/v1/avatar.jpg',
        action: '赞了',
        target: '周末外拍活动照片',
        time: '昨天',
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_errorSemantic != null) {
      return _buildErrorCard();
    }

    final fgPrimary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );

    return Column(
      children: [
        _buildSubTabs(),
        SizedBox(height: AppSpacing.md),
        ..._displayInteractions.map(
          (item) => _buildInteractionItem(item, fgPrimary, fgSecondary),
        ),
      ],
    );
  }

  Widget _buildSubTabs() {
    final tabs = [
      ('likes', UITextConstants.circleLikes),
      ('comments', UITextConstants.circleComments),
    ];
    final activeIndex = tabs.indexWhere((tab) => tab.$1 == _activeSubTab);
    return SecondaryCapsuleTabBar(
      isDark: widget.isDark,
      tabs: tabs.map((tab) => tab.$2).toList(growable: false),
      activeIndex: activeIndex < 0 ? 0 : activeIndex,
      onTap: (index) => setState(() => _activeSubTab = tabs[index].$1),
      horizontalPadding: 0,
      variant: SecondaryCapsuleTabBarVariant.inlineMuted,
    );
  }

  Widget _buildInteractionItem(
    _InteractionRow item,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    final avatarUrl = resolveAvatarImageUrl(item.avatar);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: AppSpacing.md,
            backgroundImage: avatarUrl.isEmpty ? null : NetworkImage(avatarUrl),
            onBackgroundImageError: (_, _) {},
          ),
          SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        item.userName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Text(
                      item.time,
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  '${item.action} ${item.target}',
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorCard() {
    return AppSectionErrorCard(
      semantic: _errorSemantic!,
      margin: EdgeInsets.zero,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _loadInteractions();
        }
      },
    );
  }
}
