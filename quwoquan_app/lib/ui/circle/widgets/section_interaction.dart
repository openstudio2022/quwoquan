import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
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

class _SectionInteractionState extends ConsumerState<SectionInteraction> {
  String _activeSubTab = 'likes';
  bool _isLoading = true;
  String? _error;
  List<Map<String, dynamic>> _interactions = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadInteractions());
  }

  Future<void> _loadInteractions() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final repo = ref.read(circleRepositoryProvider);
      final feed = await repo.getCircleFeed(widget.circleId);
      if (mounted) {
        setState(() {
          _interactions = feed;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = e.toString();
        });
      }
    }
  }

  // Fallback mock data when feed is empty
  List<Map<String, dynamic>> get _displayInteractions {
    if (_interactions.isNotEmpty &&
        _interactions.every(
          (item) =>
              item['userName'] is String &&
              item['avatar'] is String &&
              item['time'] is String,
        )) {
      return _interactions;
    }
    return [
      {
        'id': 'i1',
        'userName': '陈一发',
        'avatar':
            'https://images.unsplash.com/photo-1630939687530-241d630735df?q=80&w=100',
        'action': '赞了',
        'target': '《川西秘境摄影集》',
        'time': '14:20',
      },
      {
        'id': 'i2',
        'userName': '王小明',
        'avatar':
            'https://images.unsplash.com/photo-1643816831234-e7cb32194e92?q=80&w=100',
        'action': '评论了',
        'target': '器材交流帖',
        'time': '10:05',
      },
      {
        'id': 'i3',
        'userName': '李青云',
        'avatar':
            'https://images.unsplash.com/photo-1603110502322-93cd2173d19a?q=80&w=100',
        'action': '赞了',
        'target': '周末外拍活动照片',
        'time': '昨天',
      },
    ];
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
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
    Map<String, dynamic> item,
    Color fgPrimary,
    Color fgSecondary,
  ) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: AppSpacing.md,
            backgroundImage: NetworkImage(item['avatar'] as String),
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
                        item['userName'] as String,
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
                      item['time'] as String,
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  '${item['action']} ${item['target']}',
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
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    return Container(
      padding: EdgeInsets.all(AppSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.error_outline,
            color: AppColors.error,
            size: AppSpacing.iconLarge,
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.loadFailed,
            style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
          ),
          SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            onPressed: _loadInteractions,
            child: Text(
              UITextConstants.retry,
              style: TextStyle(
                color: AppColors.primaryColor,
                fontSize: AppTypography.base,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
