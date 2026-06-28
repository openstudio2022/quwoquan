part of 'create_media_picker_page.dart';

class _CreateMediaPickerPageState extends State<CreateMediaPickerPage> {
  static const int _pageSize = 80;
  static const double _tabletFourColumnGridMinWidth =
      AppSpacing.expandedBreakpoint;
  static const double _desktopFiveColumnGridMinWidth =
      AppSpacing.webPageContentMaxWidth;
  final ScrollController _scrollController = ScrollController();

  bool _loading = true;
  bool _hasPermission = false;
  bool _isLoadingMore = false;
  bool _hasMore = true;
  int _page = 0;

  List<AssetPathEntity> _albums = const [];
  AssetPathEntity? _selectedAlbum;
  final GlobalKey _topBarKey = GlobalKey();
  final List<AssetEntity> _assets = <AssetEntity>[];

  final List<CreateMediaItem> _selectedItems = <CreateMediaItem>[];
  final Map<String, CreateMediaItem> _selectedById =
      <String, CreateMediaItem>{};

  /// 选中/取消选中会触发整页 [setState]；若每次 build 都为格子新建
  /// [FutureBuilder] 的 future，会重置所有缩略图为加载态，表现为「整页刷新」。
  final Map<String, Future<Uint8List?>> _thumbnailFutures =
      <String, Future<Uint8List?>>{};
  final Map<String, Future<int>> _albumCountFutures = <String, Future<int>>{};
  final Map<String, Future<Uint8List?>> _albumCoverFutures =
      <String, Future<Uint8List?>>{};

  @override
  void initState() {
    super.initState();
    final initialSelection = widget.entryMode == MediaPickerEntryMode.image
        ? const <CreateMediaItem>[]
        : widget.initialSelection;
    _selectedItems.addAll(initialSelection);
    for (final item in initialSelection) {
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
    if (!mounted) {
      return;
    }
    final outcome = await AppPermissionCoordinator.instance.ensure(
      context,
      AppPermissionKind.photos,
    );
    if (!mounted) return;
    if (outcome != AppPermissionEnsureOutcome.granted) {
      setState(() {
        _hasPermission = false;
        _loading = false;
      });
      return;
    }
    final albums = await widget.mediaPickerService.loadAlbums(
      type: _requestTypeByEntryMode(),
    );
    if (!mounted) return;
    final preparedAlbums = await _prepareImageAlbums(albums);
    if (!mounted) return;
    setState(() {
      _hasPermission = true;
      _albums = preparedAlbums;
      _selectedAlbum = preparedAlbums.isNotEmpty ? preparedAlbums.first : null;
      _loading = false;
    });
    await _reloadAssets();
  }

  Future<List<AssetPathEntity>> _prepareImageAlbums(
    List<AssetPathEntity> source,
  ) async {
    if (widget.entryMode == MediaPickerEntryMode.video) {
      return source;
    }
    final entries = <_AlbumSortEntry>[];
    for (final album in source) {
      if (_isVideoOnlyAlbum(album)) {
        continue;
      }
      final count = await widget.mediaPickerService.loadAlbumAssetCount(album);
      _albumCountFutures[album.id] = Future<int>.value(count);
      if (count <= 0) {
        continue;
      }
      entries.add(_AlbumSortEntry(album: album, count: count));
    }
    entries.sort((a, b) {
      // 「全部照片」(isAll) 永远置顶，其次相机目录，再按图片数降序、名称升序。
      final priorityCompare = _albumPriority(
        b.album,
      ).compareTo(_albumPriority(a.album));
      if (priorityCompare != 0) return priorityCompare;
      final countCompare = b.count.compareTo(a.count);
      if (countCompare != 0) return countCompare;
      return _albumDisplayName(a.album).compareTo(_albumDisplayName(b.album));
    });
    return entries.map((entry) => entry.album).toList(growable: false);
  }

  bool _isVideoOnlyAlbum(AssetPathEntity album) {
    final normalized = album.name.trim().toLowerCase();
    return normalized == 'videos' ||
        normalized == 'video' ||
        normalized == 'all videos' ||
        normalized == UITextConstants.mediaPickerVideoTitle;
  }

  bool _isCameraAlbum(AssetPathEntity album) {
    final normalized = album.name.trim().toLowerCase();
    return normalized == 'camera' ||
        normalized == UITextConstants.mediaPickerAlbumCamera ||
        normalized == 'camera roll';
  }

  int _albumPriority(AssetPathEntity album) {
    if (album.isAll) {
      return 2;
    }
    return _isCameraAlbum(album) ? 1 : 0;
  }

  String _albumDisplayName(AssetPathEntity album) {
    // 系统聚合相册（isAll，iOS 的 Recents / Android 的 All）统一显示为「全部照片」，
    // 避免出现「最近项目 / Recents」等不一致命名。
    if (album.isAll) {
      return UITextConstants.mediaPickerAlbumAllPhotos;
    }
    final name = album.name.trim();
    final normalized = name.toLowerCase();
    if (normalized == 'camera' || normalized == 'camera roll') {
      return UITextConstants.mediaPickerAlbumCamera;
    }
    if (normalized == 'recents' ||
        normalized == 'recent' ||
        normalized == 'all photos') {
      return UITextConstants.mediaPickerAlbumRecents;
    }
    if (normalized == 'screenshots') {
      return UITextConstants.mediaPickerCategoryFullscreen;
    }
    return name.isEmpty ? UITextConstants.mediaPickerAlbumAll : name;
  }

  RequestType _requestTypeByEntryMode() {
    return widget.entryMode == MediaPickerEntryMode.video
        ? RequestType.video
        : RequestType.image;
  }

  void _onScroll() {
    if (_scrollController.position.pixels >
        (_scrollController.position.maxScrollExtent -
            AppSpacing.buttonHeight)) {
      _loadMore();
    }
  }

  Future<void> _reloadAssets() async {
    final album = _selectedAlbum;
    if (album == null) return;
    setState(() {
      _assets.clear();
      _thumbnailFutures.clear();
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
    final next = await widget.mediaPickerService.loadAssets(
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

  bool _matchesEntryMode(AssetEntity entity) {
    if (widget.entryMode == MediaPickerEntryMode.video) {
      return entity.type == AssetType.video;
    }
    return entity.type == AssetType.image;
  }

  Future<void> _toggleAsset(AssetEntity entity) async {
    final key = entity.id;
    if (_selectedById.containsKey(key)) {
      final selectedIndex = _selectedItems.indexWhere((item) => item.id == key);
      if (widget.entryMode == MediaPickerEntryMode.image &&
          selectedIndex >= 0) {
        await _editSelectedImageAt(selectedIndex);
      }
      return;
    }
    if (_selectedItems.length >= widget.maxSelection) {
      if (!mounted) return;
      AppToast.show(context, UITextConstants.mediaPickerOverLimit);
      return;
    }
    final item = await widget.mediaPickerService.assetToMediaItem(entity);
    if (item == null || !mounted) return;
    if (widget.entryMode == MediaPickerEntryMode.video && !item.isVideo) return;
    if (widget.entryMode == MediaPickerEntryMode.image && item.isVideo) {
      AppToast.show(context, UITextConstants.mediaPickerImageOnly);
      return;
    }
    setState(() {
      _selectedItems.add(item);
      _selectedById[key] = item;
    });
  }

  Future<void> _openCamera() async {
    if (_selectedItems.length >= widget.maxSelection) {
      AppToast.show(context, UITextConstants.mediaPickerOverLimit);
      return;
    }
    final result = await Navigator.of(context).push<CameraCaptureResult>(
      MaterialPageRoute<CameraCaptureResult>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageCamera,
        ),
        builder: (context) => _buildCameraPage(context),
      ),
    );
    if (!mounted || result == null) return;
    if (_selectedItems.length >= widget.maxSelection) {
      AppToast.show(context, UITextConstants.mediaPickerOverLimit);
      return;
    }
    final item = widget.mediaPickerService.fileToMediaItem(
      filePath: result.path,
      source: CreateMediaSource.camera,
      type: result.type,
    );
    setState(() {
      _selectedItems.add(item);
      _selectedById[item.id] = item;
    });
  }

  Widget _buildCameraPage(BuildContext context) {
    final caller = CameraPhotoCaller.picker;
    final entrySource = CameraPhotoEntrySource.photoPicker;
    final builder = widget.cameraBuilder;
    if (builder != null) {
      return builder(context, caller, entrySource, _selectedItems.length);
    }
    return CameraCapturePage(
      initialMode: widget.entryMode,
      allowVideoMode: widget.entryMode == MediaPickerEntryMode.video,
      caller: caller,
      entrySource: entrySource,
      selectedCountBeforeCapture: _selectedItems.length,
    );
  }

  Future<void> _selectAlbum() async {
    if (_albums.isEmpty) {
      return;
    }
    final background = AppColors.iosGroupedBackgroundDark;
    final picked = await showAppTopAnchoredDropdown<AssetPathEntity>(
      context: context,
      anchorTop: _albumDropdownAnchorTop(),
      scrimColor: AppColorsFunctional.getColor(true, ColorType.modalScrim),
      barrierLabel: UITextConstants.cancel,
      builder: (dropdownContext) => _buildForcedDarkChrome(
        baseContext: dropdownContext,
        background: background,
        child: _buildAlbumDropdownPanel(
          dropdownContext,
          background: background,
        ),
      ),
    );
    if (picked == null || !mounted) return;
    if (picked.id == _selectedAlbum?.id) return;
    setState(() => _selectedAlbum = picked);
    await _reloadAssets();
  }

  /// 相册下拉的锚点：顶栏底边的全局 Y；顶栏尚未布局时回退到安全区 + 工具栏高度。
  double _albumDropdownAnchorTop() {
    final box = _topBarKey.currentContext?.findRenderObject() as RenderBox?;
    if (box != null && box.hasSize) {
      return box.localToGlobal(Offset.zero).dy + box.size.height;
    }
    return MediaQuery.of(context).viewPadding.top + AppSpacing.toolbarHeight;
  }

  Widget _buildAlbumDropdownPanel(
    BuildContext dropdownContext, {
    required Color background,
  }) {
    const isDark = true;
    return DecoratedBox(
      key: TestKeys.mediaPickerAlbumDropdownPanel,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(AppSpacing.containerSm),
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.32),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(AppSpacing.containerSm),
        ),
        child: ListView.separated(
          shrinkWrap: true,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.intraGroupSm,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
          ),
          itemBuilder: (context, index) =>
              _buildAlbumPickerRow(_albums[index], isDark, dropdownContext),
          separatorBuilder: (context, index) => Divider(
            height: AppSpacing.hairline,
            thickness: AppSpacing.hairline,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.borderSecondary,
            ).withValues(alpha: 0.72),
          ),
          itemCount: _albums.length,
        ),
      ),
    );
  }

  Widget _buildAlbumPickerRow(
    AssetPathEntity album,
    bool isDark,
    BuildContext dropdownContext,
  ) {
    final selected = album.id == _selectedAlbum?.id;
    final primary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return CupertinoButton(
      key: ValueKey<String>('media-picker-album-${album.id}'),
      padding: EdgeInsets.zero,
      onPressed: () => Navigator.of(dropdownContext).pop(album),
      child: Container(
        color: CupertinoColors.transparent,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
        child: Row(
          children: [
            _buildAlbumCover(album, isDark),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: FutureBuilder<int>(
                future: _albumCountFuture(album),
                builder: (context, snapshot) {
                  final count = snapshot.data;
                  final countSuffix = count == null ? '' : ' ($count)';
                  return Text(
                    '${_albumDisplayName(album)}$countSuffix',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: primary,
                      fontSize: AppTypography.iosBody,
                      fontWeight: selected
                          ? AppTypography.semiBold
                          : AppTypography.regular,
                    ),
                  );
                },
              ),
            ),
            if (selected)
              Icon(
                CupertinoIcons.checkmark,
                color: AppColors.primaryColor,
                size: AppSpacing.iconMedium,
              )
            else
              SizedBox.square(dimension: AppSpacing.iconMedium),
          ],
        ),
      ),
    );
  }

  Widget _buildAlbumCover(AssetPathEntity album, bool isDark) {
    final size = AppSpacing.bottomNavHeight;
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: SizedBox(
        width: size,
        height: size,
        child: FutureBuilder<Uint8List?>(
          future: _albumCoverFuture(album),
          builder: (context, snapshot) {
            final bytes = snapshot.data;
            if (bytes != null && bytes.isNotEmpty) {
              return Image.memory(bytes, fit: BoxFit.cover);
            }
            return Container(
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.backgroundSecondary,
              ),
              child: Icon(
                CupertinoIcons.photo,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
                size: AppSpacing.iconMedium,
              ),
            );
          },
        ),
      ),
    );
  }

  Future<int> _albumCountFuture(AssetPathEntity album) {
    return _albumCountFutures.putIfAbsent(
      album.id,
      () => widget.mediaPickerService.loadAlbumAssetCount(album),
    );
  }

  Future<Uint8List?> _albumCoverFuture(AssetPathEntity album) {
    return _albumCoverFutures.putIfAbsent(
      album.id,
      () => widget.mediaPickerService.loadAlbumCover(album),
    );
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
    if (from < 0 ||
        to < 0 ||
        from >= _selectedItems.length ||
        to >= _selectedItems.length) {
      return;
    }
    setState(() {
      final moving = _selectedItems.removeAt(from);
      _selectedItems.insert(to, moving);
    });
  }

  void _finishSelection() {
    Navigator.of(context).pop(
      CreateMediaPickerResult(
        items: List<CreateMediaItem>.from(_selectedItems),
      ),
    );
  }

  Future<void> _editLatestSelectedImage() async {
    final index = _selectedItems.lastIndexWhere((item) => item.isImage);
    if (index < 0) return;
    await _editSelectedImageAt(index);
  }

  Future<void> _editSelectedImageAt(int selectedIndex) async {
    if (selectedIndex < 0 || selectedIndex >= _selectedItems.length) {
      return;
    }
    final current = _selectedItems[selectedIndex];
    if (!current.isImage) {
      AppToast.show(context, UITextConstants.mediaPickerImageOnly);
      return;
    }
    final imageSelectedIndexes = <int>[
      for (var i = 0; i < _selectedItems.length; i++)
        if (_selectedItems[i].isImage) i,
    ];
    final editorImageIndex = imageSelectedIndexes.indexOf(selectedIndex);
    if (editorImageIndex < 0) {
      return;
    }
    final imagePaths = <String>[
      for (final index in imageSelectedIndexes) _selectedItems[index].path,
    ];
    final editorRequest = CreateMediaPickerImageEditorRequest(
      initialPath: current.path,
      index: editorImageIndex,
      total: imagePaths.length,
      imagePaths: imagePaths,
    );
    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageImagePreview,
        ),
        fullscreenDialog: true,
        builder: (context) => _buildImageEditor(context, editorRequest),
      ),
    );
    final edited = _resolveEditedImageResult(
      result: result,
      fallbackSelectedIndex: selectedIndex,
      imageSelectedIndexes: imageSelectedIndexes,
    );
    if (!mounted || edited == null) {
      return;
    }
    final item = _selectedItems[edited.selectedIndex];
    final editedItem = item.copyWith(path: edited.path);
    setState(() {
      _selectedItems[edited.selectedIndex] = editedItem;
      _selectedById[editedItem.id] = editedItem;
    });
  }

  Widget _buildImageEditor(
    BuildContext context,
    CreateMediaPickerImageEditorRequest request,
  ) {
    final builder = widget.imageEditorBuilder;
    if (builder != null) {
      return builder(context, request);
    }
    return ImageEditorPage(
      initialPath: request.initialPath,
      source: 'create',
      index: request.index,
      total: request.total,
      imagePaths: request.imagePaths,
    );
  }

  _EditedPickerImage? _resolveEditedImageResult({
    required Object? result,
    required int fallbackSelectedIndex,
    required List<int> imageSelectedIndexes,
  }) {
    if (result is String) {
      final path = result.trim();
      if (path.isEmpty) return null;
      return _EditedPickerImage(
        selectedIndex: fallbackSelectedIndex,
        path: path,
      );
    }
    if (result is Map) {
      final rawPath = result['path']?.toString().trim();
      if (rawPath == null || rawPath.isEmpty) return null;
      final rawIndex = result['index'];
      final imageIndex = rawIndex is num
          ? rawIndex.toInt()
          : int.tryParse(rawIndex?.toString() ?? '');
      if (imageIndex == null ||
          imageIndex < 0 ||
          imageIndex >= imageSelectedIndexes.length) {
        return _EditedPickerImage(
          selectedIndex: fallbackSelectedIndex,
          path: rawPath,
        );
      }
      return _EditedPickerImage(
        selectedIndex: imageSelectedIndexes[imageIndex],
        path: rawPath,
      );
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    const isDark = true;
    final bg = AppColors.iosGroupedBackgroundDark;
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final sub = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    if (_loading) {
      return _buildForcedDarkChrome(
        baseContext: context,
        background: bg,
        child: AppScaffold(
          backgroundColor: bg,
          child: Center(child: CupertinoActivityIndicator()),
        ),
      );
    }
    if (!_hasPermission) {
      return _buildForcedDarkChrome(
        baseContext: context,
        background: bg,
        child: AppScaffold(
          backgroundColor: bg,
          navigationBar: AppNavigationBar(
            backgroundColor: bg,
            leading: AppNavigationBarIconButton(
              icon: CupertinoIcons.xmark,
              onPressed: () => Navigator.of(context).pop(),
            ),
          ),
          child: Center(
            child: Padding(
              padding: EdgeInsets.all(AppSpacing.containerLg),
              child: AppInlineGateState(
                semantic: AppPermissionCoordinator.instance.permissionSemantic(
                  AppPermissionKind.photos,
                  openSettings: true,
                  includeRetry: true,
                ),
                onAction: (action) async {
                  switch (action.type) {
                    case UiErrorActionType.retry:
                    case UiErrorActionType.resubmit:
                      setState(() => _loading = true);
                      await _loadInitial();
                      return;
                    case UiErrorActionType.openSettings:
                      await AppPermissionCoordinator.instance.openSettings(
                        AppPermissionKind.photos,
                        onReturn: (granted) {
                          if (mounted && granted) {
                            unawaited(_loadInitial());
                          }
                        },
                      );
                      return;
                    case UiErrorActionType.dismiss:
                    case UiErrorActionType.back:
                      if (mounted) {
                        Navigator.of(context).pop();
                      }
                      return;
                    case UiErrorActionType.login:
                      return;
                  }
                },
              ),
            ),
          ),
        ),
      );
    }
    final list = _assets.where(_matchesEntryMode).toList(growable: false);
    return _buildForcedDarkChrome(
      baseContext: context,
      background: bg,
      child: AppScaffold(
        backgroundColor: bg,
        child: SafeArea(
          bottom: false,
          child: Column(
            children: [
              _buildTopBar(fg, sub),
              if (widget.entryMode == MediaPickerEntryMode.video)
                _buildVideoShootHero(isDark),
              Expanded(child: _buildGrid(list, isDark)),
              if (_selectedItems.isNotEmpty) _buildSelectedStrip(sub, isDark),
              _buildBottomActions(isDark),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildForcedDarkChrome({
    required BuildContext baseContext,
    required Color background,
    required Widget child,
  }) {
    final theme = CupertinoTheme.of(baseContext);
    final mediaQuery = MediaQuery.maybeOf(baseContext);
    final darkChild = CupertinoTheme(
      data: theme.copyWith(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: background,
        barBackgroundColor: background,
      ),
      child: child,
    );
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light.copyWith(
        statusBarColor: background,
        systemNavigationBarColor: background,
        systemNavigationBarDividerColor: background,
      ),
      child: mediaQuery == null
          ? darkChild
          : MediaQuery(
              data: mediaQuery.copyWith(platformBrightness: Brightness.dark),
              child: darkChild,
            ),
    );
  }

  int _gridCrossAxisCount(double width) {
    if (width >= _desktopFiveColumnGridMinWidth) {
      return 5;
    }
    if (width >= _tabletFourColumnGridMinWidth) {
      return 4;
    }
    return 3;
  }

  Widget _buildCameraTile(bool isDark) {
    return GestureDetector(
      key: const ValueKey<String>('media-picker-camera-tile'),
      onTap: _openCamera,
      child: Container(
        color: AppColors.black,
        alignment: Alignment.center,
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                widget.entryMode == MediaPickerEntryMode.video
                    ? CupertinoIcons.videocam_fill
                    : CupertinoIcons.camera,
                size: AppSpacing.iconLarge + AppSpacing.intraGroupSm,
                color: AppColors.white,
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                widget.entryMode == MediaPickerEntryMode.video
                    ? UITextConstants.mediaPickerVideoCameraEntry
                    : UITextConstants.mediaPickerCameraEntry,
                style: TextStyle(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundPrimary,
                  ),
                  fontSize: AppTypography.base,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSelectBadge(String id) {
    final index = _selectedItems.indexWhere((item) => item.id == id);
    final selected = index >= 0;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      width: AppSpacing.buttonHeightXs,
      height: AppSpacing.buttonHeightXs,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: selected
            ? AppColors.primaryColor
            : AppColors.black.withValues(alpha: 0.26),
        border: Border.all(
          color: AppColors.white,
          width: AppSpacing.hairline * 2,
        ),
      ),
      child: selected
          ? Text(
              '${index + 1}',
              style: TextStyle(
                color: AppColors.white,
                fontWeight: FontWeight.w700,
                fontSize: AppTypography.iosCaption1,
                height: AppTypography.lineHeightTight,
              ),
            )
          : const SizedBox.shrink(),
    );
  }

  Widget _buildSelectedStrip(Color sub, bool isDark) {
    final background = AppColors.iosGroupedBackgroundDark;
    final thumbSize = AppSpacing.bottomNavHeight;
    return Container(
      height: AppSpacing.bottomNavHeight + AppSpacing.containerMd,
      color: background,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerXs,
      ),
      // 统一拖拽重排：长按起拖 + 兄弟实时让位 + 松手提交，复用 MediaReorderableView。
      // 替换旧的 LongPressDraggable + DragTarget「跳变」方案，与其余两处共用同一交互真相源。
      child: MediaReorderableView(
        layout: MediaReorderableLayout.strip,
        itemCount: _selectedItems.length,
        spacing: AppSpacing.intraGroupSm,
        itemSize: Size(thumbSize, thumbSize),
        onReorder: (oldIndex, newIndex) {
          // 组件用 Flutter 标准插入位，_reorderSelected 用最终下标，需转换。
          final to = oldIndex < newIndex ? newIndex - 1 : newIndex;
          _reorderSelected(oldIndex, to);
        },
        itemBuilder: (context, index, isDragging) {
          final item = _selectedItems[index];
          return GestureDetector(
            onTap: item.isImage
                ? () => unawaited(_editSelectedImageAt(index))
                : null,
            child: _selectedItemThumb(
              item: item,
              isDark: isDark,
              onDelete: () => _removeSelectedAt(index),
            ),
          );
        },
      ),
    );
  }

  Widget _buildBottomActions(bool isDark) {
    final selectionCount = _selectedItems.length;
    final actions = mediaPickerBottomActionsForEntryMode(
      mode: widget.entryMode,
      selectionCount: selectionCount,
    );
    final background = AppColors.iosGroupedBackgroundDark;
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderSecondary,
    );
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final bottomPadding = bottomInset + AppSpacing.intraGroupSm;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        border: Border(
          top: BorderSide(color: border, width: AppSpacing.hairline),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.intraGroupSm,
          AppSpacing.containerMd,
          bottomPadding,
        ),
        child: Row(
          children: [
            for (var i = 0; i < actions.length; i++) ...[
              if (i > 0) SizedBox(width: AppSpacing.interGroupSm),
              Expanded(child: _buildBottomActionButton(actions[i], isDark)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBottomActionButton(
    CreateMediaPickerBottomActionSpec spec,
    bool isDark,
  ) {
    final onPressed = spec.enabled
        ? () {
            switch (spec.action) {
              case CreateMediaPickerBottomAction.editImage:
                unawaited(_editLatestSelectedImage());
                return;
              case CreateMediaPickerBottomAction.completeImage:
              case CreateMediaPickerBottomAction.nextStep:
                _finishSelection();
                return;
            }
          }
        : null;
    final neutralBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final disabledBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final neutralForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final disabledForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundTertiary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderSecondary,
    );
    final child = Container(
      key: ValueKey<String>('media-picker-bottom-action-${spec.action.name}'),
      height: AppSpacing.buttonHeight,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: spec.enabled
            ? (spec.isPrimary ? AppColors.primaryColor : neutralBackground)
            : disabledBackground.withValues(alpha: 0.48),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: spec.isPrimary || !spec.enabled
            ? null
            : Border.all(color: borderColor),
      ),
      child: Text(
        spec.label,
        style: TextStyle(
          fontSize: AppTypography.base,
          fontWeight: spec.isPrimary ? FontWeight.w700 : FontWeight.w600,
          color: spec.enabled
              ? (spec.isPrimary ? AppColors.white : neutralForeground)
              : disabledForeground,
        ),
      ),
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onPressed,
      child: child,
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

  Future<Uint8List?> _cachedThumbnailFuture(AssetEntity entity) {
    return _thumbnailFutures.putIfAbsent(
      entity.id,
      () => widget.mediaPickerService.loadThumbnail(entity),
    );
  }

  Widget _buildAssetThumb(AssetEntity entity, bool isDark) {
    return FutureBuilder<Uint8List?>(
      future: _cachedThumbnailFuture(entity),
      builder: (context, snapshot) {
        final bytes = snapshot.data;
        if (bytes != null && bytes.isNotEmpty) {
          return Image.memory(bytes, fit: BoxFit.cover);
        }
        return Container(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundSecondary,
          ),
        );
      },
    );
  }
}
