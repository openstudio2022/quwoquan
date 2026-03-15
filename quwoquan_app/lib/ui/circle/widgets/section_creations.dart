import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
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

  List<IdentityFilterConfig> get _identityFilters =>
      ContentUIConfig.creationIdentityFilters;

  List<WorkFormatFilterConfig> get _workFormatFilters =>
      ContentUIConfig.workFormatFilters;

  static const _sortLabels = {
    CreationSortMode.latest: UITextConstants.circleSortLatest,
    CreationSortMode.hot: UITextConstants.circleSortHot,
    CreationSortMode.featured: UITextConstants.circleSortFeatured,
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
      final query = _feedQueryForState(notifier.state);
      final items = await repo.getCircleFeed(
        widget.circleId,
        identity: query.identity,
        type: query.type,
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
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );

    return Column(
      children: [
        _buildIdentityFilterRow(notifier, fg, fgSecondary),
        if (notifier.state.activeSubTab == CreationSubTab.work) ...[
          SizedBox(height: AppSpacing.sm),
          _buildWorkFormatFilterRow(notifier, fg, fgSecondary),
        ],
        if (_isAdminOrOwner) ...[
          _buildSortControls(notifier, fg, fgSecondary),
          _buildViewModeToggle(notifier),
        ],
        SizedBox(height: AppSpacing.sm),
        Expanded(child: _buildContent(notifier, fg, fgSecondary)),
      ],
    );
  }

  bool get _isAdminOrOwner =>
      widget.role == CircleRole.owner || widget.role == CircleRole.admin;

  ({String? identity, String? type}) _feedQueryForState(CircleState state) {
    switch (state.activeSubTab) {
      case CreationSubTab.moment:
        return (identity: 'moment', type: null);
      case CreationSubTab.work:
        return (
          identity: 'work',
          type: _contentTypeForWorkFormat(state.activeWorkFormat),
        );
      case CreationSubTab.all:
        return (identity: null, type: null);
    }
  }

  Widget _buildIdentityFilterRow(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: _identityFilters
            .map((filter) {
              final tab = _creationSubTabForId(filter.id);
              final selected = notifier.state.activeSubTab == tab;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: ChoiceChip(
                  label: Text(
                    UITextConstants.contentLabelForKey(filter.labelKey),
                  ),
                  selected: selected,
                  onSelected: (_) {
                    notifier.setSubTab(tab);
                    _loadFeed();
                  },
                  labelStyle: TextStyle(
                    color: selected ? fg : fgSecondary,
                    fontWeight: AppTypography.semiBold,
                  ),
                  selectedColor: AppColors.primaryColor.withValues(alpha: 0.14),
                  backgroundColor: Colors.transparent,
                  side: BorderSide(
                    color: selected
                        ? AppColors.primaryColor.withValues(alpha: 0.45)
                        : fgSecondary.withValues(alpha: 0.2),
                  ),
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }

  Widget _buildWorkFormatFilterRow(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: _workFormatFilters
            .map((filter) {
              final format = _creationWorkFormatForId(filter.id);
              final selected = notifier.state.activeWorkFormat == format;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: ChoiceChip(
                  label: Text(
                    UITextConstants.contentLabelForKey(filter.labelKey),
                  ),
                  selected: selected,
                  onSelected: (_) {
                    notifier.setWorkFormat(format);
                    _loadFeed();
                  },
                  labelStyle: TextStyle(
                    color: selected ? fg : fgSecondary,
                    fontWeight: AppTypography.semiBold,
                  ),
                  selectedColor: AppColors.primaryColor.withValues(alpha: 0.14),
                  backgroundColor: Colors.transparent,
                  side: BorderSide(
                    color: selected
                        ? AppColors.primaryColor.withValues(alpha: 0.45)
                        : fgSecondary.withValues(alpha: 0.2),
                  ),
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }

  CreationSubTab _creationSubTabForId(String id) {
    switch (id) {
      case 'moment':
        return CreationSubTab.moment;
      case 'work':
        return CreationSubTab.work;
      default:
        return CreationSubTab.all;
    }
  }

  CreationWorkFormat _creationWorkFormatForId(String id) {
    switch (id) {
      case 'image':
        return CreationWorkFormat.image;
      case 'video':
        return CreationWorkFormat.video;
      case 'note':
        return CreationWorkFormat.note;
      default:
        return CreationWorkFormat.all;
    }
  }

  String? _contentTypeForWorkFormat(CreationWorkFormat format) {
    switch (format) {
      case CreationWorkFormat.image:
        return 'image';
      case CreationWorkFormat.video:
        return 'video';
      case CreationWorkFormat.note:
        return 'article';
      case CreationWorkFormat.all:
        return null;
    }
  }

  bool _matchesIdentityFilter(Map<String, dynamic> item, CreationSubTab tab) {
    switch (tab) {
      case CreationSubTab.moment:
        return _itemIdentity(item) == 'moment';
      case CreationSubTab.work:
        return _itemIdentity(item) == 'work';
      case CreationSubTab.all:
        return true;
    }
  }

  bool _matchesWorkFormat(
    Map<String, dynamic> item,
    CreationSubTab activeSubTab,
    CreationWorkFormat format,
  ) {
    if (activeSubTab != CreationSubTab.work ||
        format == CreationWorkFormat.all) {
      return true;
    }
    switch (format) {
      case CreationWorkFormat.image:
        return _itemDisplayFormat(item) == 'image';
      case CreationWorkFormat.video:
        return _itemDisplayFormat(item) == 'video';
      case CreationWorkFormat.note:
        return _itemDisplayFormat(item) == 'note';
      case CreationWorkFormat.all:
        return true;
    }
  }

  String _itemIdentity(Map<String, dynamic> item) {
    return (item['contentIdentity'] ??
            (item['type']?.toString() == 'moment' ? 'moment' : 'work'))
        .toString();
  }

  String _itemDisplayFormat(Map<String, dynamic> item) {
    final type = (item['type'] ?? '').toString();
    switch (type) {
      case 'image':
        return 'image';
      case 'video':
        return 'video';
      case 'article':
        return 'note';
      case 'moment':
        return 'moment';
      default:
        return type;
    }
  }

  String _itemTypeLabel(Map<String, dynamic> item) {
    final identity = _itemIdentity(item);
    if (identity == 'moment') {
      return UITextConstants.creationFilterMoment;
    }
    switch (_itemDisplayFormat(item)) {
      case 'image':
        return UITextConstants.workFormatFilterImage;
      case 'video':
        return UITextConstants.workFormatFilterVideo;
      case 'note':
        return UITextConstants.workFormatFilterNote;
      default:
        return UITextConstants.creationFilterWork;
    }
  }

  Widget _buildSortControls(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
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
                  borderRadius: BorderRadius.circular(
                    AppSpacing.circularBorderRadius,
                  ),
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

  Widget _buildViewModeToggle(CircleStateNotifier notifier) {
    final activeMode = notifier.state.viewMode;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          IconButton(
            tooltip: '网格视图',
            onPressed: () => notifier.setViewMode(CreationViewMode.grid),
            icon: Icon(
              Icons.grid_view_rounded,
              color: activeMode == CreationViewMode.grid
                  ? AppColors.primaryColor
                  : null,
            ),
          ),
          IconButton(
            tooltip: '列表视图',
            onPressed: () => notifier.setViewMode(CreationViewMode.list),
            icon: Icon(
              Icons.view_agenda_outlined,
              color: activeMode == CreationViewMode.list
                  ? AppColors.primaryColor
                  : null,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return _buildErrorCard(fgSecondary);
    }

    final activeSubTab = notifier.state.activeSubTab;
    final activeWorkFormat = notifier.state.activeWorkFormat;
    final filtered = _feedItems.where((item) {
      return _matchesIdentityFilter(item, activeSubTab) &&
          _matchesWorkFormat(item, activeSubTab, activeWorkFormat);
    }).toList();

    if (filtered.isEmpty) {
      return _buildEmpty(fgSecondary);
    }

    if (notifier.state.viewMode == CreationViewMode.list) {
      return ListView.separated(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        itemCount: filtered.length,
        separatorBuilder: (_, _) => SizedBox(height: AppSpacing.sm),
        itemBuilder: (context, index) {
          final item = filtered[index];
          return _buildListItem(item, fgSecondary);
        },
      );
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
        : (imageUrls is List && imageUrls.isNotEmpty
              ? imageUrls[0].toString()
              : '');
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
                  Icon(
                    Icons.favorite,
                    size: AppTypography.sm,
                    color: Colors.white,
                  ),
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

  Widget _buildListItem(Map<String, dynamic> item, Color fgSecondary) {
    final cover = (item['coverUrl'] ?? item['thumbnailUrl'] ?? '').toString();
    final likeCount = item['likeCount'] ?? item['likes'] ?? 0;
    final typeLabel = _itemTypeLabel(item);
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: widget.isDark
            ? Colors.white10
            : Colors.black.withValues(alpha: 0.03),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Row(
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            child: SizedBox(
              width: AppSpacing.followButtonWidth + AppSpacing.intraGroupMd,
              height: AppSpacing.followButtonWidth + AppSpacing.intraGroupMd,
              child: cover.isNotEmpty
                  ? Image.network(
                      cover,
                      fit: BoxFit.cover,
                      errorBuilder: (_, _, _) => Container(
                        color: fgSecondary.withValues(alpha: 0.1),
                        child: Icon(Icons.image, color: fgSecondary),
                      ),
                    )
                  : Container(
                      color: fgSecondary.withValues(alpha: 0.1),
                      child: Icon(Icons.image, color: fgSecondary),
                    ),
            ),
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  typeLabel,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColors.primaryColor,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  '赞 $likeCount',
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: AppColorsFunctional.getColor(
                      widget.isDark,
                      ColorType.foregroundPrimary,
                    ),
                  ),
                ),
              ],
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
