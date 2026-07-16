part of 'create_page.dart';
class _CreatePageState extends ConsumerState<CreatePage>
    with WidgetsBindingObserver, RouteAware {
  static const int _kMaxMediaImages = 20;
  static const int _kMaxBodyLength = 5000;
  final CreateCircleService _circleService = const CreateCircleService();
  final TextEditingController _titleController = TextEditingController();
  final TextEditingController _bodyController = TextEditingController();
  final FocusNode _titleFocusNode = FocusNode();
  final FocusNode _bodyFocusNode = FocusNode();
  final ScrollController _scrollController = ScrollController();
  late final CreateDraftSessionController _draftSessionController;
  bool _didApplyInitialAction = false;
  bool _isPublishing = false;
  bool _isHydratingDraft = false;
  double _heroCollapseProgress = 0;
  String? _pressedMediaPath;
  ModalRoute<dynamic>? _observedRoute;
  /// 非 null 时 [ArticleEditor] 在该页展开文内图工具栏（如新插入图片后）。
  final ValueNotifier<String?> _revealArticleImageToolbarForPageId =
      ValueNotifier<String?>(null);
  /// 按 asset id 展开工具条（多图同页时优先于 [_revealArticleImageToolbarForPageId]）。
  final ValueNotifier<String?> _revealArticleImageToolbarForAssetId =
      ValueNotifier<String?>(null);
  bool get _unifiedCreateEditorEnabled =>
      ref.read(contentFeatureFlagProvider('enable_unified_create_editor'));
  bool _useImmersiveArticleExperience(CreateEditorState state) {
    return widget.initialAction == EditorStartAction.write &&
        state.editorKind == CreateEditorKind.text;
  }

  void _setMountedState(VoidCallback update) {
    if (!mounted) {
      return;
    }
    setState(update);
  }

  @override
  void initState() {
    super.initState();
    unawaited(StartupDeferredPlugins.ensureContentEntryPlugins());
    WidgetsBinding.instance.addObserver(this);
    _scrollController.addListener(_handleScroll);
    _titleFocusNode.addListener(_handleFocusLossFlush);
    _bodyFocusNode.addListener(_handleFocusLossFlush);
    _draftSessionController = CreateDraftSessionController(
      onFlushDirty: (reason) => _saveDraft(silent: true, flushReason: reason),
    )..start();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) {
        return;
      }
      final loaded = await ref.read(createDraftStoreProvider.future);
      if (!mounted) {
        return;
      }

      final wantedId = widget.initialDraftId?.trim();
      final initialDraft = wantedId == null || wantedId.isEmpty
          ? null
          : loaded.draftById(wantedId);

      final notifier = ref.read(createEditorProvider.notifier);
      _isHydratingDraft = true;
      if (initialDraft != null) {
        notifier.reset(
          editorKind: initialDraft.state.editorKind,
          draftFlowKind: initialDraft.state.draftFlowKind,
        );
        await _restoreDraft(initialDraft);
        _didApplyInitialAction = true;
        _isHydratingDraft = false;
        _draftSessionController.resumeAfterRestore();
      } else {
        notifier.reset(
          editorKind: _resolveInitialEditorKind(),
          draftFlowKind: _resolveInitialDraftFlowKind(),
        );
        if (widget.initialAction != null) {
          notifier.setStartAction(widget.initialAction);
        } else {
          notifier.setDraftFlowKind(_resolveInitialDraftFlowKind());
        }
        final anchorCircleId = widget.initialCircleId?.trim();
        if (widget.initialHomepage != null ||
            (anchorCircleId != null && anchorCircleId.isNotEmpty)) {
          var nextSettings = ref.read(createEditorProvider).settings;
          if (widget.initialHomepage != null) {
            nextSettings = nextSettings.copyWith(
              homepage: widget.initialHomepage,
            );
          }
          if (anchorCircleId != null && anchorCircleId.isNotEmpty) {
            final anchorCircleName = widget.initialCircleName?.trim();
            nextSettings = nextSettings.copyWith(
              isPublic: true,
              circleIds: <String>{
                ...nextSettings.circleIds,
                anchorCircleId,
              }.toList(growable: false),
              circleNames: <String>[
                ...nextSettings.circleNames,
                if (anchorCircleName != null && anchorCircleName.isNotEmpty)
                  anchorCircleName,
              ],
            );
          }
          notifier.setSettings(nextSettings);
        }
        _isHydratingDraft = false;
        _draftSessionController.resumeAfterRestore();
        _syncControllersFromState(ref.read(createEditorProvider));
        await _runAfterOverlayDismissed(_applyInitialActionIfNeeded);
      }

      if (!mounted) {
        return;
      }
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_editor_ready',
        createEditorSurfaceExtrasReady(
          editorKind: ref.read(createEditorProvider).editorKind,
          unifiedCreateEditorEnabled: _unifiedCreateEditorEnabled,
        ),
      );
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final route = ModalRoute.of(context);
    if (route == null || identical(route, _observedRoute)) {
      return;
    }
    if (_observedRoute is PageRoute<dynamic>) {
      createDraftRouteObserver.unsubscribe(this);
    }
    if (route is PageRoute<dynamic>) {
      createDraftRouteObserver.subscribe(this, route);
      _observedRoute = route;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (_observedRoute is PageRoute<dynamic>) {
      createDraftRouteObserver.unsubscribe(this);
    }
    _draftSessionController.dispose();
    _scrollController
      ..removeListener(_handleScroll)
      ..dispose();
    _titleController.dispose();
    _bodyController.dispose();
    _titleFocusNode
      ..removeListener(_handleFocusLossFlush)
      ..dispose();
    _bodyFocusNode
      ..removeListener(_handleFocusLossFlush)
      ..dispose();
    _revealArticleImageToolbarForPageId.dispose();
    _revealArticleImageToolbarForAssetId.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden) {
      unawaited(_flushDraftIfDirty('lifecycle'));
    }
  }

  @override
  void didPushNext() {
    unawaited(_flushDraftIfDirty('route_blur'));
  }

  void _handleScroll() {
    final next =
        (_scrollController.hasClients ? _scrollController.offset / 96 : 0.0)
            .clamp(0.0, 1.0)
            .toDouble();
    if ((next - _heroCollapseProgress).abs() < 0.02 || !mounted) {
      return;
    }
    setState(() {
      _heroCollapseProgress = next;
    });
  }

  CreateEditorKind _resolveInitialEditorKind() {
    return _resolveInitialEntryMediaMode() == null
        ? CreateEditorKind.text
        : CreateEditorKind.media;
  }

  MediaPickerEntryMode? _resolveInitialEntryMediaMode() {
    if (widget.initialAction == EditorStartAction.gallery) {
      return MediaPickerEntryMode.image;
    }
    if (widget.initialAction == EditorStartAction.video) {
      return MediaPickerEntryMode.video;
    }
    if (widget.initialAction == EditorStartAction.capture) {
      return (widget.initialTabKey ?? '').trim() == 'video'
          ? MediaPickerEntryMode.video
          : MediaPickerEntryMode.image;
    }
    switch ((widget.initialTabKey ?? '').trim()) {
      case 'photo':
        return MediaPickerEntryMode.image;
      case 'video':
        return MediaPickerEntryMode.video;
      default:
        break;
    }
    switch (widget.initialAction) {
      case EditorStartAction.write:
      case null:
        return null;
      case EditorStartAction.gallery:
        return MediaPickerEntryMode.image;
      case EditorStartAction.video:
        return MediaPickerEntryMode.video;
      case EditorStartAction.capture:
        return MediaPickerEntryMode.image;
    }
  }

  CreateDraftFlowKind _resolveInitialDraftFlowKind() {
    switch (_resolveInitialEntryMediaMode()) {
      case MediaPickerEntryMode.image:
        return CreateDraftFlowKind.image;
      case MediaPickerEntryMode.video:
        return CreateDraftFlowKind.video;
      case MediaPickerEntryMode.mixed:
        return CreateDraftFlowKind.image;
      case null:
        return CreateDraftFlowKind.article;
    }
  }

  bool _prefersVideoEntryForState(CreateEditorState state) {
    return state.editorKind == CreateEditorKind.media &&
        (state.mediaKind == CreateMediaKind.video ||
            (state.mediaKind == CreateMediaKind.none &&
                state.draftFlowKind == CreateDraftFlowKind.video));
  }

  String? get _activeDraftId {
    final draftId = ref.read(createEditorProvider).draftId?.trim() ?? '';
    if (draftId.isNotEmpty) {
      return draftId;
    }
    final initialDraftId = widget.initialDraftId?.trim() ?? '';
    return initialDraftId.isEmpty ? null : initialDraftId;
  }

  void _handleFocusLossFlush() {
    if (_titleFocusNode.hasFocus || _bodyFocusNode.hasFocus) {
      return;
    }
    unawaited(_flushDraftIfDirty('focus_blur'));
  }

  Future<void> _flushDraftIfDirty(String reason) async {
    await _draftSessionController.flushIfDirty(reason: reason);
  }

  String _draftContentFingerprint(CreateEditorState state) {
    return [
      state.draftFlowKind.name,
      state.editorKind.name,
      state.mediaKind.name,
      state.imagePaths.join('|'),
      state.videoPath,
      state.originalVideoPath,
      state.videoThumbnail,
      state.isOneTapMovie,
      state.oneTapMoviePath,
      state.oneTapMovieEffectId,
      state.videoDurationMs,
      state.videoTrimStartMs,
      state.videoTrimEndMs,
      state.videoCoverTimeMs,
      state.videoMuted,
      state.currentMediaIndex,
      state.title,
      state.body,
      state.articleDocument.title,
      state.articleDocument.body,
      state.articleTemplate.name,
      state.articlePaperTexture.name,
      state.articleFontPreset.name,
      state.articleCoverImagePath,
      state.titlePresentation.name,
      state.titleHintDismissed,
      state.settings.isPublic,
      state.settings.circleIds.join('|'),
      state.settings.circleNames.join('|'),
      state.settings.locationName,
      state.settings.locationPoi?.id ?? '',
      state.settings.summary,
      state.settings.tagRefs.join('|'),
      state.settings.entityRefs.join('|'),
      state.settings.assistantUsePolicy,
    ].join('::');
  }

  Future<void> _runAfterOverlayDismissed(Future<void> Function() action) {
    final completer = Completer<void>();
    // 让动作面板或路由退场完至少一帧后再继续 push，避免透明蒙层退场
    // 与相册/相机页首帧叠在一起时短暂闪成黑屏。
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) {
        completer.complete();
        return;
      }
      try {
        await action();
        completer.complete();
      } catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      }
    });
    return completer.future;
  }

  Future<void> _applyInitialActionIfNeeded() async {
    if (_didApplyInitialAction) {
      return;
    }
    _didApplyInitialAction = true;
    final initialMediaMode = _resolveInitialEntryMediaMode();
    switch (widget.initialAction) {
      case EditorStartAction.gallery:
        await _pickImagesForCurrentEditor(closeWhenEmptyOnCancel: true);
        return;
      case EditorStartAction.video:
        await _pickVideoForMedia(closeWhenEmptyOnCancel: true);
        return;
      case EditorStartAction.capture:
        await _openCameraForCurrentEditor(
          forcedMode: initialMediaMode == MediaPickerEntryMode.video
              ? MediaPickerEntryMode.video
              : MediaPickerEntryMode.image,
          modePolicy: CameraCaptureModePolicy.switchable,
          closeWhenEmptyOnCancel: true,
        );
        return;
      case EditorStartAction.write:
      case null:
        _focusBodyField();
        return;
    }
  }

  void _syncControllersFromState(CreateEditorState state) {
    if (_titleController.text != state.title) {
      _titleController.value = TextEditingValue(
        text: state.title,
        selection: TextSelection.collapsed(offset: state.title.length),
      );
    }
    if (_bodyController.text != state.body) {
      _bodyController.value = TextEditingValue(
        text: state.body,
        selection: TextSelection.collapsed(offset: state.body.length),
      );
    }
  }

  void _focusBodyField() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final state = ref.read(createEditorProvider);
      if (state.editorKind == CreateEditorKind.text) {
        ref
            .read(createEditorProvider.notifier)
            .setActiveArticlePage(state.articlePages.first.id);
        return;
      }
      _bodyFocusNode.requestFocus();
    });
  }

  void _focusTitleField() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _titleFocusNode.requestFocus();
      }
    });
  }

  int _mediaColumnsForWidth(double width) {
    if (width >= 720) {
      return 5;
    }
    if (width >= 520) {
      return 4;
    }
    return 3;
  }

  double _mediaTileAspectRatioForColumns(int columns) {
    switch (columns) {
      case 4:
        return 1.08;
      case 3:
        return 1.12;
      default:
        return 1.16;
    }
  }

  String _pageTitleForState(CreateEditorState state) {
    if (_useImmersiveArticleExperience(state)) {
      return UITextConstants.createArticleSurfaceLongEdit;
    }
    if (_isPhotoCreateFlow(state)) {
      return CreatePageText.photoPageTitle;
    }
    return UITextConstants.createPageTitle;
  }

  String _mediaHeaderHintForState(CreateEditorState state) {
    if (state.hasVideo) {
      return UITextConstants.createMediaHintVideoCover;
    }
    if (state.isOneTapMovie) {
      return UITextConstants.createMediaOneTapMovieLockedHint;
    }
    if (state.imagePaths.isEmpty) {
      return UITextConstants.createMediaHintAddFirst;
    }
    return UITextConstants.createMediaHintDragReorder;
  }

  bool _isPhotoCreateFlow(CreateEditorState state) {
    return state.draftFlowKind == CreateDraftFlowKind.image ||
        state.mediaKind == CreateMediaKind.images;
  }

  bool _canAddMoreImages(CreateEditorState state) {
    if (state.isOneTapMovie) {
      return false;
    }
    return !state.hasVideo && state.imagePaths.length < _kMaxMediaImages;
  }

  Future<void> _saveDraft({
    bool silent = false,
    String flushReason = 'explicit',
  }) async {
    final state = ref.read(createEditorProvider);
    if (!state.hasContent && _activeDraftId == null) {
      _draftSessionController.markIdle();
      return;
    }
    _draftSessionController.markSaving();
    final now = DateTime.now().millisecondsSinceEpoch;
    final nextId = _activeDraftId ?? state.draftId ?? 'draft_$now';
    final nextDraft = CreateDraft(
      id: nextId,
      updatedAtMs: now,
      state: state.copyWith(draftId: nextId),
    );
    try {
      ref.read(createEditorProvider.notifier).setDraftId(nextId);
      final draftStore = ref.read(createDraftStoreProvider.notifier);
      await draftStore.saveDraft(nextDraft, currentDraftId: nextId);
      await draftStore.reload();
      final verified = await draftStore.getDraft(nextId);
      if (verified == null || verified.id != nextId) {
        throw StateError('saved draft is not readable: $nextId');
      }
      _draftSessionController.markSaved();
      await reportCreateEditorSurfaceEvent(
        ref,
        flushReason == 'explicit'
            ? 'create_draft_saved'
            : 'draft_autosave_flush',
        <String, Object?>{
          ...createEditorSurfaceExtrasEditorKind(nextDraft.state.editorKind),
          'reason': flushReason,
        },
      );
      if (!silent && mounted) {
        AppToast.show(context, UITextConstants.saveDraft);
      }
    } catch (error) {
      _draftSessionController.markFailed();
      if (!silent && mounted) {
        await AppActionErrorFeedback.show(
          context,
          semantic: runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.backgroundAction,
            scope: UiErrorScope.global,
            allowRetry: false,
          ),
        );
      }
      rethrow;
    }
  }

  Future<void> _clearCurrentDraft() async {
    final currentDraftId = _activeDraftId;
    if (currentDraftId == null) {
      return;
    }
    ref.read(createEditorProvider.notifier).setDraftId(null);
    await ref
        .read(createDraftStoreProvider.notifier)
        .deleteDraft(currentDraftId);
    _draftSessionController.markIdle();
  }

  Future<void> _restoreDraft(CreateDraft draft) async {
    var effectiveDraft = draft;
    if (draft.flowKind == CreateDraftFlowKind.video &&
        draft.state.videoThumbnail.trim().isEmpty &&
        draft.state.videoPath.trim().isNotEmpty) {
      final repairedThumbnail = await _generateVideoThumbnail(
        draft.state.videoPath,
      );
      if ((repairedThumbnail?.trim().isNotEmpty ?? false) &&
          repairedThumbnail != null) {
        effectiveDraft = CreateDraft(
          id: draft.id,
          updatedAtMs: draft.updatedAtMs,
          state: draft.state.copyWith(
            draftId: draft.id,
            videoThumbnail: repairedThumbnail,
          ),
          sourceType: draft.sourceType,
        );
        await ref
            .read(createDraftStoreProvider.notifier)
            .saveDraft(effectiveDraft, currentDraftId: draft.id);
      }
    }
    ref.read(createEditorProvider.notifier).restoreFromDraft(effectiveDraft);
    _syncControllersFromState(effectiveDraft.state);
    await ref
        .read(createDraftStoreProvider.notifier)
        .setCurrentDraftId(effectiveDraft.id);
    _draftSessionController.resumeAfterRestore();
    await reportCreateEditorSurfaceEvent(
      ref,
      'draft_restore_success',
      <String, Object?>{
        ...createEditorSurfaceExtrasEditorKind(effectiveDraft.state.editorKind),
        'flowKind': effectiveDraft.flowKind.name,
      },
    );
    if (effectiveDraft.state.editorKind == CreateEditorKind.text) {
      _focusBodyField();
    }
  }

  void _doClose() {
    final navigator = Navigator.maybeOf(context);
    if (navigator != null && navigator.canPop()) {
      navigator.pop();
      return;
    }
    try {
      context.go(AppRoutePaths.home);
    } catch (_) {
      // Widget tests may not mount a GoRouter.
    }
  }

  /// 为文章编辑器在指定 node 之后插入图片（node 级操作）。
  Future<void> _pickImagesForArticleNode(String? afterNodeId) async {
    final state = ref.read(createEditorProvider);
    final remainingSlots = (_kMaxMediaImages - state.imagePaths.length).clamp(
      0,
      _kMaxMediaImages,
    );
    if (remainingSlots <= 0) {
      AppToast.show(context, CreatePageText.maxImagesToast(_kMaxMediaImages));
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: const <String>[],
    );
    if (!mounted || result == null) return;
    final paths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(remainingSlots)
        .toList(growable: false);
    if (paths.isEmpty) return;
    final notifier = ref.read(createEditorProvider.notifier);
    var anchorNodeId = afterNodeId;
    for (final path in paths) {
      anchorNodeId = notifier.insertImageAfterNode(anchorNodeId, path);
    }
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_images_selected',
      createEditorSurfaceExtrasMediaBatch(
        count: paths.length,
        editorKind: state.editorKind,
      ),
    );
  }

  Future<void> _pickImagesForArticleTextSelection(
    String nodeId,
    int selectionOffset,
  ) async {
    final state = ref.read(createEditorProvider);
    final remainingSlots = (_kMaxMediaImages - state.imagePaths.length).clamp(
      0,
      _kMaxMediaImages,
    );
    if (remainingSlots <= 0) {
      AppToast.show(context, CreatePageText.maxImagesToast(_kMaxMediaImages));
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: const <String>[],
    );
    if (!mounted || result == null) return;
    final paths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(remainingSlots)
        .toList(growable: false);
    if (paths.isEmpty) return;
    final notifier = ref.read(createEditorProvider.notifier);
    var anchorNodeId = notifier.prepareTextNodeForImageInsertion(
      nodeId,
      selectionOffset,
    );
    for (final path in paths) {
      anchorNodeId = notifier.insertImageAfterNode(anchorNodeId, path);
    }
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_images_selected',
      createEditorSurfaceExtrasMediaBatch(
        count: paths.length,
        editorKind: state.editorKind,
      ),
    );
  }

  Widget _buildCameraPageForCurrentEditor(
    BuildContext context, {
    required MediaPickerEntryMode initialMode,
    required CameraCaptureModePolicy modePolicy,
    required int selectedCountBeforeCapture,
  }) {
    final caller = CameraPhotoCaller.create;
    final entrySource = CameraPhotoEntrySource.publishEntry;
    final builder = widget.cameraPageBuilder;
    if (builder != null) {
      return builder(
        context,
        initialMode: initialMode,
        caller: caller,
        entrySource: entrySource,
        selectedCountBeforeCapture: selectedCountBeforeCapture,
      );
    }
    return CameraCapturePage(
      initialMode: initialMode,
      modePolicy: modePolicy,
      caller: caller,
      entrySource: entrySource,
      selectedCountBeforeCapture: selectedCountBeforeCapture,
    );
  }

  Future<String?> _generateVideoThumbnail(String path) async {
    try {
      return await VideoThumbnail.thumbnailFile(
        video: path,
        imageFormat: ImageFormat.JPEG,
        quality: 80,
      );
    } catch (_) {
      return null;
    }
  }

  Future<_VideoMetadataProbe> _loadVideoMetadata(String path) async {
    await waitForLocalVideoPlayable(path);
    final controller = VideoPlayerController.file(File(path));
    try {
      await controller.initialize();
      final size = controller.value.size;
      return _VideoMetadataProbe(
        durationMs: math.max(controller.value.duration.inMilliseconds, 1000),
        width: size.width.round().clamp(0, 999999999),
        height: size.height.round().clamp(0, 999999999),
      );
    } catch (_) {
      return _VideoMetadataProbe.empty;
    } finally {
      await controller.dispose();
    }
  }

  Future<List<CreateCircleOption>> _loadJoinedCircles() {
    return _circleService.listCircles(ref.read(circleRepositoryProvider));
  }

  Future<PublishSettings?> _showPublishConfirmationSheet(
    CreateEditorState state,
  ) async {
    final joinedCircles = await _loadJoinedCircles();
    if (!mounted) {
      return null;
    }
    await _flushDraftIfDirty('subpage_push');
    if (!mounted) {
      return null;
    }
    return Navigator.of(context).push<PublishSettings>(
      CupertinoPageRoute<PublishSettings>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPagePublishConfirm,
        ),
        fullscreenDialog: true,
        builder: (_) => CreatePublishConfirmSheet(
          initialSettings: state.settings,
          locationCoordinator: ref.read(createLocationCoordinatorProvider),
          joinedCircles: joinedCircles,
          recommendedCircles: publishFlowRecommendedCircleOptions(
            ref.read(circleRepositoryProvider),
          ),
        ),
      ),
    );
  }

  List<TextInputFormatter> get _bodyInputFormatters => <TextInputFormatter>[
    LengthLimitingTextInputFormatter(_kMaxBodyLength),
  ];

  bool _canPublish(CreateEditorState state) {
    if (state.editorKind == CreateEditorKind.media) {
      return state.hasImages ||
          state.hasVideo ||
          state.hasBody ||
          state.hasTitle;
    }
    return state.hasBody || state.hasTitle || state.hasImages;
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<CreateEditorState>(createEditorProvider, (previous, next) {
      if (_isHydratingDraft || previous == null) {
        return;
      }
      if (_draftContentFingerprint(previous) ==
          _draftContentFingerprint(next)) {
        return;
      }
      _draftSessionController.markDirty();
    });
    final state = ref.watch(createEditorProvider);
    _syncControllersFromState(state);
    if (_useImmersiveArticleExperience(state)) {
      return _buildImmersiveArticlePage(state);
    }
    final background = CupertinoColors.systemGroupedBackground.resolveFrom(
      context,
    );
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (!didPop) {
          await _onCloseRequest();
        }
      },
      child: CupertinoPageScaffold(
        backgroundColor: background,
        // Match [AppScaffold]: transparent Material gives Text a Material ancestor
        // so debug / fallback styling does not draw yellow underlines under labels.
        child: Material(
          type: MaterialType.transparency,
          child: KeyedSubtree(
            key: TestKeys.createPage,
            child: ColoredBox(
              color: background,
              child: SafeArea(
                top: false,
                bottom: false,
                child: Column(
                  children: <Widget>[
                    _buildHeader(
                      state: state,
                      collapseProgress: _heroCollapseProgress,
                    ),
                    Expanded(
                      child: state.editorKind == CreateEditorKind.media
                          ? SingleChildScrollView(
                              controller: _scrollController,
                              padding: EdgeInsets.fromLTRB(
                                AppSpacing.containerMd,
                                AppSpacing.containerSm,
                                AppSpacing.containerMd,
                                MediaQuery.of(context).padding.bottom +
                                    AppSpacing.containerLg,
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: <Widget>[
                                  if (!_unifiedCreateEditorEnabled)
                                    _buildRollbackBanner(
                                      CupertinoColors.secondaryLabel
                                          .resolveFrom(context),
                                    ),
                                  _buildMediaEditor(state),
                                ],
                              ),
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: <Widget>[
                                if (!_unifiedCreateEditorEnabled)
                                  Padding(
                                    padding: EdgeInsets.symmetric(
                                      horizontal: AppSpacing.containerMd,
                                    ),
                                    child: _buildRollbackBanner(
                                      CupertinoColors.secondaryLabel
                                          .resolveFrom(context),
                                    ),
                                  ),
                                Expanded(child: _buildTextEditor(state)),
                              ],
                            ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRollbackBanner(Color secondary) {
    return Container(
      margin: EdgeInsets.only(bottom: AppSpacing.interGroupMd),
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Text(
        '当前处于编辑器回退模式，保留双编辑器骨架并关闭增强提示。',
        style: TextStyle(color: secondary, fontSize: AppTypography.sm),
      ),
    );
  }

  /// 创作/沉浸文章顶栏共用：毛玻璃 + 底部分割线，并向上延伸至状态栏区域使背景连续。
  Widget _buildCreateTopChromeBar({
    required double collapseProgress,
    required Widget child,
    bool immersiveDark = false,
  }) {
    final divider = immersiveDark
        ? AppColors.white.withValues(alpha: 0.12)
        : CupertinoColors.separator.resolveFrom(context);
    final chrome = immersiveDark
        ? AppColors.black
        : CupertinoColors.systemBackground
              .resolveFrom(context)
              .withValues(alpha: lerpDouble(0.78, 0.94, collapseProgress)!);
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: AppSpacing.sm, sigmaY: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.only(
            top: MediaQuery.viewPaddingOf(context).top,
            left: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: chrome,
            border: Border(
              bottom: BorderSide(
                color: divider.withValues(alpha: immersiveDark ? 0.12 : 0.45),
                width: AppSpacing.hairline,
              ),
            ),
          ),
          child: SizedBox(height: AppSpacing.toolbarHeight, child: child),
        ),
      ),
    );
  }

  Future<void> _insertEntityMentionFromSelection(
    String nodeId,
    int start,
    int end,
  ) async {
    final selection = await pickArticleEntityMentionHomepage(context);
    if (!mounted || selection == null) return;
    final canonical = selection.canonicalEntityId?.trim() ?? '';
    if (canonical.isEmpty) {
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .attachArticleEntityMention(
          nodeId,
          start,
          end,
          targetType: 'entity',
          targetId: canonical,
          displayText: selection.title,
        );
  }

  Widget _buildMediaComposerSection({
    required CreateEditorState state,
    required String title,
    required String trailing,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildSectionHeader(title: title, trailing: trailing),
        SizedBox(height: AppSpacing.intraGroupSm),
        _buildSurfacePanel(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _buildMediaStrip(
                state: state,
                onAdd: state.hasVideo
                    ? _pickVideoForMedia
                    : _pickImagesForCurrentEditor,
                onTapImage: _editCurrentImage,
                onRemove: (index) {
                  if (state.mediaKind == CreateMediaKind.video) {
                    ref.read(createEditorProvider.notifier).clearVideo();
                  } else {
                    ref
                        .read(createEditorProvider.notifier)
                        .removeImageAt(index);
                  }
                },
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSectionHeader({required String title, String? trailing}) {
    return Row(
      children: <Widget>[
        if (title.trim().isNotEmpty)
          Text(
            title,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
              letterSpacing: 0.2,
            ),
          ),
        const Spacer(),
        if (trailing != null)
          Text(
            trailing,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
            ),
          ),
      ],
    );
  }

  Widget _buildSurfacePanel({required Widget child, EdgeInsets? padding}) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final panelBackground = CupertinoColors.secondarySystemGroupedBackground
        .resolveFrom(context);
    final separator = CupertinoColors.separator.resolveFrom(context);
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: panelBackground,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: separator.withValues(alpha: 0.18),
          width: AppSpacing.hairline,
        ),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundPrimary,
            ).withValues(alpha: isDark ? 0.2 : 0.04),
            blurRadius: AppSpacing.twenty,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}
