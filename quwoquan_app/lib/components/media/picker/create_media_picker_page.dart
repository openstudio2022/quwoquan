import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:photo_manager/photo_manager.dart';
import 'package:quwoquan_app/components/media/camera/camera_capture_page.dart';
import 'package:quwoquan_app/components/media/picker/one_tap_movie_preview_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/media_picker_service.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

class CreateMediaPickerPage extends StatefulWidget {
  const CreateMediaPickerPage({
    super.key,
    required this.entryMode,
    required this.maxSelection,
    this.initialSelection = const <CreateMediaItem>[],
  });

  final MediaPickerEntryMode entryMode;
  final int maxSelection;
  final List<CreateMediaItem> initialSelection;

  @override
  State<CreateMediaPickerPage> createState() => _CreateMediaPickerPageState();
}

class _CreateMediaPickerPageState extends State<CreateMediaPickerPage> {
  static const int _pageSize = 80;
  final MediaPickerService _service = MediaPickerService();
  final ScrollController _scrollController = ScrollController();

  bool _loading = true;
  bool _hasPermission = false;
  bool _isLoadingMore = false;
  bool _hasMore = true;
  int _page = 0;

  MediaPickerCategory _category = MediaPickerCategory.all;
  List<AssetPathEntity> _albums = const [];
  AssetPathEntity? _selectedAlbum;
  final List<AssetEntity> _assets = <AssetEntity>[];

  final List<CreateMediaItem> _selectedItems = <CreateMediaItem>[];
  final Map<String, CreateMediaItem> _selectedById = <String, CreateMediaItem>{};

  @override
  void initState() {
    super.initState();
    _selectedItems.addAll(widget.initialSelection);
    for (final item in widget.initialSelection) {
      _selectedById[item.id] = item;
    }
    _scrollController.addListener(_onScroll);
    _loadInitial();
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    super.dispose();
  }

  Future<void> _loadInitial() async {
    final granted = await _service.ensurePhotoPermission();
    if (!mounted) return;
    if (!granted) {
      setState(() {
        _hasPermission = false;
        _loading = false;
      });
      return;
    }
    final albums = await _service.loadAlbums(type: _requestTypeByEntryMode());
    if (!mounted) return;
    setState(() {
      _hasPermission = true;
      _albums = albums;
      _selectedAlbum = albums.isNotEmpty ? albums.first : null;
      _loading = false;
    });
    await _reloadAssets();
  }

  RequestType _requestTypeByEntryMode() {
    return widget.entryMode == MediaPickerEntryMode.video
        ? RequestType.video
        : RequestType.common;
  }

  void _onScroll() {
    if (_scrollController.position.pixels >
        (_scrollController.position.maxScrollExtent - AppSpacing.buttonHeight)) {
      _loadMore();
    }
  }

  Future<void> _reloadAssets() async {
    final album = _selectedAlbum;
    if (album == null) return;
    setState(() {
      _assets.clear();
      _page = 0;
      _hasMore = true;
      _isLoadingMore = false;
    });
    await _loadMore();
  }

  Future<void> _loadMore() async {
    if (_isLoadingMore || !_hasMore) return;
    final album = _selectedAlbum;
    if (album == null) return;
    setState(() => _isLoadingMore = true);
    final next = await _service.loadAssets(
      album: album,
      page: _page,
      pageSize: _pageSize,
    );
    if (!mounted) return;
    setState(() {
      _assets.addAll(next);
      _page += 1;
      _isLoadingMore = false;
      _hasMore = next.length >= _pageSize;
    });
  }

  bool _matchesCategory(AssetEntity entity) {
    if (widget.entryMode == MediaPickerEntryMode.video) {
      return entity.type == AssetType.video;
    }
    switch (_category) {
      case MediaPickerCategory.all:
        return true;
      case MediaPickerCategory.video:
        return entity.type == AssetType.video;
      case MediaPickerCategory.photo:
        return entity.type == AssetType.image && !_isGif(entity);
      case MediaPickerCategory.live:
        return _isGif(entity);
      case MediaPickerCategory.fullscreen:
        if (entity.type != AssetType.image) return false;
        if (entity.width <= 0 || entity.height <= 0) return false;
        final ratio = entity.height / entity.width;
        return ratio >= 1.9;
    }
  }

  bool _isGif(AssetEntity entity) {
    final mime = (entity.mimeType ?? '').toLowerCase();
    return mime.contains('gif');
  }

  Future<void> _toggleAsset(AssetEntity entity) async {
    final key = entity.id;
    if (_selectedById.containsKey(key)) {
      setState(() {
        final removed = _selectedById.remove(key);
        _selectedItems.removeWhere((e) => e.id == removed?.id);
      });
      return;
    }
    if (_selectedItems.length >= widget.maxSelection) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.mediaPickerOverLimit)),
      );
      return;
    }
    final item = await _service.assetToMediaItem(entity);
    if (item == null || !mounted) return;
    if (widget.entryMode == MediaPickerEntryMode.video && !item.isVideo) return;
    if (widget.entryMode == MediaPickerEntryMode.image && item.isVideo) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.mediaPickerImageOnly)),
      );
      return;
    }
    setState(() {
      _selectedItems.add(item);
      _selectedById[key] = item;
    });
  }

  Future<void> _openCamera() async {
    final result = await Navigator.of(context).push<CameraCaptureResult>(
      MaterialPageRoute<CameraCaptureResult>(
        builder: (_) => CameraCapturePage(initialMode: widget.entryMode),
      ),
    );
    if (!mounted || result == null) return;
    if (_selectedItems.length >= widget.maxSelection) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.mediaPickerOverLimit)),
      );
      return;
    }
    final item = _service.fileToMediaItem(
      filePath: result.path,
      source: CreateMediaSource.camera,
      type: result.type,
    );
    setState(() {
      _selectedItems.add(item);
      _selectedById[item.id] = item;
    });
  }

  Future<void> _selectAlbum() async {
    if (_albums.isEmpty) return;
    final picked = await showModalBottomSheet<AssetPathEntity>(
      context: context,
      builder: (context) {
        return SafeArea(
          child: ListView.separated(
            itemCount: _albums.length,
            separatorBuilder: (_, _) => Divider(
              height: AppSpacing.intraGroupXs / 2,
              color: AppColorsFunctional.getColor(
                Theme.of(context).brightness == Brightness.dark,
                ColorType.borderSecondary,
              ),
            ),
            itemBuilder: (context, index) {
              final album = _albums[index];
              final selected = album.id == _selectedAlbum?.id;
              return ListTile(
                onTap: () => Navigator.of(context).pop(album),
                title: Text(
                  album.name,
                  style: TextStyle(
                    color: selected ? AppColors.primaryColor : null,
                    fontSize: AppTypography.lg,
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  ),
                ),
                trailing: selected
                    ? Icon(Icons.check, color: AppColors.primaryColor)
                    : null,
              );
            },
          ),
        );
      },
    );
    if (picked == null || !mounted) return;
    if (picked.id == _selectedAlbum?.id) return;
    setState(() => _selectedAlbum = picked);
    await _reloadAssets();
  }

  void _removeSelectedAt(int index) {
    if (index < 0 || index >= _selectedItems.length) return;
    final item = _selectedItems[index];
    setState(() {
      _selectedItems.removeAt(index);
      _selectedById.remove(item.id);
    });
  }

  void _reorderSelected(int from, int to) {
    if (from == to) return;
    if (from < 0 || to < 0 || from >= _selectedItems.length || to >= _selectedItems.length) {
      return;
    }
    setState(() {
      final moving = _selectedItems.removeAt(from);
      _selectedItems.insert(to, moving);
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final bg = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final sub = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    if (_loading) {
      return Scaffold(
        backgroundColor: bg,
        body: Center(
          child: CircularProgressIndicator(color: AppColors.primaryColor),
        ),
      );
    }
    if (!_hasPermission) {
      return Scaffold(
        backgroundColor: bg,
        appBar: AppBar(
          backgroundColor: bg,
          leading: IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: Icon(Icons.close, color: fg),
          ),
        ),
        body: Center(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerLg),
            child: Text(
              UITextConstants.mediaPickerPermissionDenied,
              style: TextStyle(color: sub, fontSize: AppTypography.base),
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    }
    final list = _assets.where(_matchesCategory).toList();
    return Scaffold(
      backgroundColor: bg,
      body: SafeArea(
        child: Column(
          children: [
            _buildTopBar(fg, sub),
            _buildCategoryTabs(isDark),
            Expanded(
              child: _buildGrid(list, isDark),
            ),
            if (_selectedItems.isNotEmpty) _buildSelectedStrip(sub, isDark),
            _buildBottomActions(),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(Color fg, Color sub) {
    final albumName = _selectedAlbum?.name ?? UITextConstants.mediaPickerAlbumAll;
    return SizedBox(
      height: AppSpacing.toolbarHeight,
      child: Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: Icon(Icons.close, color: fg),
          ),
          Expanded(
            child: Center(
              child: GestureDetector(
                onTap: _selectAlbum,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      albumName,
                      style: TextStyle(
                        color: fg,
                        fontSize: AppTypography.lg,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Icon(Icons.keyboard_arrow_down, color: sub, size: AppSpacing.iconMedium),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.iconButtonMinSizeSm),
        ],
      ),
    );
  }

  Widget _buildCategoryTabs(bool isDark) {
    final categories = <MediaPickerCategory>[
      MediaPickerCategory.all,
      MediaPickerCategory.video,
      MediaPickerCategory.photo,
      MediaPickerCategory.live,
      MediaPickerCategory.fullscreen,
    ];
    return SizedBox(
      height: AppSpacing.tabNavigationHeight,
      child: ListView.separated(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        scrollDirection: Axis.horizontal,
        itemBuilder: (context, index) {
          final cat = categories[index];
          final selected = cat == _category;
          return GestureDetector(
            onTap: () => setState(() => _category = cat),
            child: Container(
              constraints: BoxConstraints(minHeight: AppSpacing.minInteractiveSize),
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              alignment: Alignment.center,
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    _categoryLabel(cat),
                    style: TextStyle(
                      color: selected
                          ? AppColors.primaryColor
                          : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                      fontSize: AppTypography.base,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 120),
                    width: selected ? AppSpacing.buttonHeightSm : 0,
                    height: AppSpacing.intraGroupXs / 2,
                    decoration: BoxDecoration(
                      color: AppColors.primaryColor,
                      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
        separatorBuilder: (_, _) => SizedBox(width: AppSpacing.intraGroupSm),
        itemCount: categories.length,
      ),
    );
  }

  String _categoryLabel(MediaPickerCategory category) {
    switch (category) {
      case MediaPickerCategory.all:
        return UITextConstants.mediaPickerCategoryAll;
      case MediaPickerCategory.video:
        return UITextConstants.mediaPickerCategoryVideo;
      case MediaPickerCategory.photo:
        return UITextConstants.mediaPickerCategoryPhoto;
      case MediaPickerCategory.live:
        return UITextConstants.mediaPickerCategoryLive;
      case MediaPickerCategory.fullscreen:
        return UITextConstants.mediaPickerCategoryFullscreen;
    }
  }

  Widget _buildGrid(List<AssetEntity> list, bool isDark) {
    const crossCount = 3;
    final total = list.length + 1;
    return GridView.builder(
      controller: _scrollController,
      padding: EdgeInsets.all(AppSpacing.intraGroupXs / 2),
      itemCount: total,
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossCount,
        mainAxisSpacing: AppSpacing.intraGroupXs / 2,
        crossAxisSpacing: AppSpacing.intraGroupXs / 2,
      ),
      itemBuilder: (context, index) {
        if (index == 0) return _buildCameraTile(isDark);
        final entity = list[index - 1];
        return GestureDetector(
          onTap: () => _toggleAsset(entity),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Positioned.fill(
                child: _buildAssetThumb(entity, isDark),
              ),
              if (entity.type == AssetType.video)
                Positioned(
                  left: AppSpacing.intraGroupSm,
                  bottom: AppSpacing.intraGroupSm,
                  child: Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.intraGroupSm,
                      vertical: AppSpacing.intraGroupXs / 2,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black54,
                      borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
                    ),
                    child: Text(
                      _formatVideoDuration(entity.duration),
                      style: TextStyle(color: Colors.white, fontSize: AppTypography.sm),
                    ),
                  ),
                ),
              Positioned(
                top: AppSpacing.intraGroupSm,
                right: AppSpacing.intraGroupSm,
                child: _buildSelectBadge(entity.id),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildCameraTile(bool isDark) {
    return GestureDetector(
      onTap: _openCamera,
      child: Container(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.photo_camera_outlined,
              size: AppSpacing.iconLarge + AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              UITextConstants.mediaPickerCameraEntry,
              style: TextStyle(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                fontSize: AppTypography.base,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSelectBadge(String id) {
    final index = _selectedItems.indexWhere((item) => item.id == id);
    final selected = index >= 0;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      width: AppSpacing.buttonHeightSm,
      height: AppSpacing.buttonHeightSm,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: selected ? AppColors.primaryColor : Colors.black26,
        border: Border.all(
          color: Colors.white,
          width: AppSpacing.intraGroupXs / 2,
        ),
      ),
      child: selected
          ? Text(
              '${index + 1}',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: AppTypography.sm,
              ),
            )
          : const SizedBox.shrink(),
    );
  }

  Widget _buildSelectedStrip(Color sub, bool isDark) {
    return Container(
      height: AppSpacing.bottomNavHeight + AppSpacing.buttonHeightSm,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: _selectedItems.length,
        itemBuilder: (context, index) {
          final item = _selectedItems[index];
          return LongPressDraggable<int>(
            data: index,
            feedback: _selectedItemThumb(
              item: item,
              isDark: isDark,
              showDelete: false,
            ),
            childWhenDragging: Opacity(
              opacity: 0.4,
              child: _selectedItemThumb(item: item, isDark: isDark),
            ),
            child: DragTarget<int>(
              onAcceptWithDetails: (details) => _reorderSelected(details.data, index),
              builder: (context, candidate, rejected) {
                return AnimatedScale(
                  scale: candidate.isNotEmpty ? 1.08 : 1,
                  duration: const Duration(milliseconds: 120),
                  child: _selectedItemThumb(item: item, isDark: isDark, onDelete: () => _removeSelectedAt(index)),
                );
              },
            ),
          );
        },
        separatorBuilder: (context, index) => SizedBox(width: AppSpacing.intraGroupSm),
      ),
    );
  }

  Widget _selectedItemThumb({
    required CreateMediaItem item,
    required bool isDark,
    VoidCallback? onDelete,
    bool showDelete = true,
  }) {
    final size = AppSpacing.bottomNavHeight;
    final file = File(item.path);
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            border: Border.all(
              color: AppColorsFunctional.getColor(isDark, ColorType.borderSecondary),
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: item.isVideo
              ? Container(
                  color: Colors.black87,
                  child: Icon(Icons.videocam_outlined, color: Colors.white, size: AppSpacing.iconMedium),
                )
              : Image.file(
                  file,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) => Container(
                    color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                  ),
                ),
        ),
        if (showDelete && onDelete != null)
          Positioned(
            right: -AppSpacing.intraGroupXs,
            top: -AppSpacing.intraGroupXs,
            child: GestureDetector(
              onTap: onDelete,
              child: Container(
                width: AppSpacing.iconSmall + AppSpacing.intraGroupSm,
                height: AppSpacing.iconSmall + AppSpacing.intraGroupSm,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.black87,
                ),
                child: Icon(Icons.close, color: Colors.white, size: AppSpacing.iconSmall),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildBottomActions() {
    final selectionCount = _selectedItems.length;
    final canNext = selectionCount > 0;
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.intraGroupSm,
        AppSpacing.containerMd,
        AppSpacing.interGroupSm,
      ),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton.icon(
              onPressed: canNext
                  ? _openOneTapMoviePreview
                  : null,
              icon: Icon(Icons.movie_creation_outlined, size: AppSpacing.iconMedium),
              label: Text(
                UITextConstants.mediaPickerOneTapMovie,
                style: TextStyle(fontSize: AppTypography.base),
              ),
              style: OutlinedButton.styleFrom(
                minimumSize: Size.fromHeight(AppSpacing.buttonHeight),
                side: BorderSide(color: AppColors.primaryColor),
                foregroundColor: AppColors.primaryColor,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: FilledButton(
              onPressed: canNext
                  ? () {
                      Navigator.of(context).pop(
                        CreateMediaPickerResult(
                          items: List<CreateMediaItem>.from(_selectedItems),
                        ),
                      );
                    }
                  : null,
              style: FilledButton.styleFrom(
                minimumSize: Size.fromHeight(AppSpacing.buttonHeight),
                backgroundColor: AppColors.primaryColor,
                foregroundColor: Colors.white,
              ),
              child: Text(
                '${UITextConstants.mediaPickerNextStep}($selectionCount)',
                style: TextStyle(fontSize: AppTypography.base, fontWeight: FontWeight.w700),
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatVideoDuration(int seconds) {
    final s = seconds % 60;
    final m = (seconds ~/ 60) % 60;
    final h = seconds ~/ 3600;
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  Future<void> _openOneTapMoviePreview() async {
    final selected = List<CreateMediaItem>.from(_selectedItems);
    final images = selected.where((item) => item.isImage).toList();
    if (images.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.mediaPickerImageOnly)),
      );
      return;
    }
    final goNext = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        fullscreenDialog: true,
        builder: (_) => OneTapMoviePreviewPage(items: selected),
      ),
    );
    if (!mounted || goNext != true) return;
    Navigator.of(context).pop(
      CreateMediaPickerResult(
        items: selected,
        openOneTapMovie: true,
      ),
    );
  }

  Widget _buildAssetThumb(AssetEntity entity, bool isDark) {
    return FutureBuilder<Uint8List?>(
      future: entity.thumbnailDataWithSize(const ThumbnailSize.square(240)),
      builder: (context, snapshot) {
        final bytes = snapshot.data;
        if (bytes != null && bytes.isNotEmpty) {
          return Image.memory(bytes, fit: BoxFit.cover);
        }
        return Container(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        );
      },
    );
  }
}
