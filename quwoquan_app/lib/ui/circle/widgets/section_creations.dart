import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_tab.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

/// 圈子"创作"板块：SubTab 过滤 + 排序 + 二列网格
class SectionCreations extends ConsumerStatefulWidget {
  const SectionCreations({
    super.key,
    required this.circleId,
    required this.isDark,
    required this.role,
  });

  final String circleId;
  final bool isDark;
  final CircleRole role;

  @override
  ConsumerState<SectionCreations> createState() => _SectionCreationsState();
}

class _SectionCreationsState extends ConsumerState<SectionCreations> {
  bool _isLoading = true;
  String? _error;
  List<Map<String, dynamic>> _feedItems = const [];

  static const _subTabLabels = {
    CreationSubTab.all: UITextConstants.circleSubAll,
    CreationSubTab.micro: UITextConstants.circleSubMicro,
    CreationSubTab.image: UITextConstants.circleSubPhoto,
    CreationSubTab.video: UITextConstants.circleSubVideo,
    CreationSubTab.article: UITextConstants.circleSubArticle,
  };

  static const _sortLabels = {
    CreationSortMode.latest: UITextConstants.circleSortLatest,
    CreationSortMode.hot: UITextConstants.circleSortHot,
    CreationSortMode.featured: UITextConstants.circleSortFeatured,
  };

  static const _subTabTypeMap = {
    CreationSubTab.micro: 'moment',
    CreationSubTab.image: 'photo',
    CreationSubTab.video: 'video',
    CreationSubTab.article: 'article',
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFeed());
  }

  Future<void> _loadFeed() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final notifier = ref.read(circleStateProvider(widget.circleId));
      final repo = ref.read(circleRepositoryProvider);
      final items = await repo.getCircleFeed(
        widget.circleId,
        sort: notifier.state.sortMode.name,
      );
      if (mounted) {
        setState(() {
          _feedItems = items;
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

  @override
  Widget build(BuildContext context) {
    final notifier = ref.watch(circleStateProvider(widget.circleId));
    final fg = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);

    return Column(
      children: [
        _buildSubTabRow(notifier, fg, fgSecondary),
        if (_isAdminOrOwner)
          _buildSortControls(notifier, fg, fgSecondary),
        SizedBox(height: AppSpacing.sm),
        Expanded(child: _buildContent(notifier, fg, fgSecondary)),
      ],
    );
  }

  bool get _isAdminOrOwner =>
      widget.role == CircleRole.owner || widget.role == CircleRole.admin;

  Widget _buildSubTabRow(CircleStateNotifier notifier, Color fg, Color fgSecondary) {
    final activeTab = notifier.state.activeSubTab;
    return SizedBox(
      height: AppSpacing.subTabNavigationHeight,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        children: CreationSubTab.values.map((tab) {
          final isActive = tab == activeTab;
          return GestureDetector(
            onTap: () => notifier.setSubTab(tab),
            child: Container(
              alignment: Alignment.center,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              child: Text(
                _subTabLabels[tab]!,
                style: TextStyle(
                  fontSize: AppTypography.md,
                  fontWeight: isActive ? AppTypography.semiBold : AppTypography.normal,
                  color: isActive ? AppColors.primaryColor : fgSecondary,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildSortControls(CircleStateNotifier notifier, Color fg, Color fgSecondary) {
    final activeSortMode = notifier.state.sortMode;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: CreationSortMode.values.map((mode) {
          final selected = mode == activeSortMode;
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.sm),
            child: GestureDetector(
              onTap: () {
                notifier.setSortMode(mode);
                _loadFeed();
              },
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.sm,
                ),
                decoration: BoxDecoration(
                  color: selected
                      ? (widget.isDark
                          ? Colors.white.withValues(alpha: 0.1)
                          : Colors.black.withValues(alpha: 0.06))
                      : null,
                  borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
                  border: Border.all(
                    color: widget.isDark ? Colors.white24 : Colors.black12,
                  ),
                ),
                child: Text(
                  _sortLabels[mode]!,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.extraBold,
                    color: selected ? fg : fgSecondary,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildContent(CircleStateNotifier notifier, Color fg, Color fgSecondary) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator.adaptive());
    }
    if (_error != null) {
      return _buildErrorCard(fgSecondary);
    }

    final activeSubTab = notifier.state.activeSubTab;
    final filtered = _feedItems.where((item) {
      if (activeSubTab == CreationSubTab.all) return true;
      final postType = (item['type'] ?? '').toString();
      return postType == _subTabTypeMap[activeSubTab];
    }).toList();

    if (filtered.isEmpty) {
      return _buildEmpty(fgSecondary);
    }

    return GridView.builder(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.sm,
        crossAxisSpacing: AppSpacing.sm,
        childAspectRatio: 0.8,
      ),
      itemCount: filtered.length,
      itemBuilder: (context, index) {
        final item = filtered[index];
        return _buildGridItem(item, fgSecondary);
      },
    );
  }

  Widget _buildGridItem(Map<String, dynamic> item, Color fgSecondary) {
    final cover = (item['coverUrl'] ?? item['thumbnailUrl'] ?? '').toString();
    final imageUrls = item['imageUrls'];
    final resolvedCover = cover.isNotEmpty
        ? cover
        : (imageUrls is List && imageUrls.isNotEmpty ? imageUrls[0].toString() : '');
    final likeCount = item['likeCount'] ?? item['likes'] ?? 0;

    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (resolvedCover.isNotEmpty)
            Image.network(
              resolvedCover,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => Container(
                color: fgSecondary.withValues(alpha: 0.1),
                child: Icon(Icons.image, color: fgSecondary),
              ),
            )
          else
            Container(
              color: fgSecondary.withValues(alpha: 0.1),
              child: Icon(Icons.image, color: fgSecondary),
            ),
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: Container(
              padding: EdgeInsets.all(AppSpacing.intraGroupMd),
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.6),
                    Colors.transparent,
                  ],
                ),
              ),
              child: Row(
                children: [
                  Icon(Icons.favorite, size: AppTypography.sm, color: Colors.white),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  Text(
                    '$likeCount',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      fontWeight: AppTypography.medium,
                      color: Colors.white,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmpty(Color fgSecondary) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.photo_library_outlined,
            size: AppSpacing.xl * 2,
            color: fgSecondary,
          ),
          SizedBox(height: AppSpacing.md),
          Text(
            UITextConstants.circleNoCreations,
            style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorCard(Color fgSecondary) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.error_outline, color: AppColors.error, size: AppSpacing.iconLarge),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.loadFailed,
            style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
          ),
          SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            onPressed: _loadFeed,
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
