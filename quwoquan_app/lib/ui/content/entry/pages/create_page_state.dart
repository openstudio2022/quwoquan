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
  double? _publishUploadProgress;
  ContentMediaUploadCancellationSignal? _publicationCancellationSignal;
  bool _isHydratingDraft = false;
  bool _authContinuationResumeScheduled = false;
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

  Future<bool> _requireCreateActionLogin(
    CreateActionContinuationKind action, {
    bool closeWhenEmptyOnCancel = false,
  }) async {
    if (AuthGate.isAuthenticated(ref)) {
      return true;
    }
    await _flushDraftIfDirty('reauth');
    if (!mounted) {
      return false;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          ResumeCreateActionContinuation(
            action: action,
            closeWhenEmptyOnCancel: closeWhenEmptyOnCancel,
          ),
          ownerToken: 'create:${action.name}',
        );
    if (!accepted) {
      return false;
    }
    await requireLogin(
      ref,
      context,
      action == CreateActionContinuationKind.publish
          ? AuthGateReason.createPost
          : AuthGateReason.mediaUpload,
      dismissFallback: AppRoutePaths.home,
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
    return false;
  }

  void _resumeCreateActionContinuation({int remainingFrames = 30}) {
    if (!mounted ||
        !AuthGate.isAuthenticated(ref) ||
        _authContinuationResumeScheduled) {
      return;
    }
    _authContinuationResumeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _authContinuationResumeScheduled = false;
      if (!mounted || !AuthGate.isAuthenticated(ref)) {
        return;
      }
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) {
        if (remainingFrames > 0) {
          _resumeCreateActionContinuation(remainingFrames: remainingFrames - 1);
        }
        return;
      }
      final pending = ref
          .read(authContinuationProvider.notifier)
          .take<ResumeCreateActionContinuation>();
      if (pending == null) {
        return;
      }
      switch (pending.action) {
        case CreateActionContinuationKind.publish:
          unawaited(_publish());
          return;
        case CreateActionContinuationKind.pickImages:
          unawaited(
            _pickImagesForCurrentEditor(
              closeWhenEmptyOnCancel: pending.closeWhenEmptyOnCancel,
            ),
          );
          return;
        case CreateActionContinuationKind.pickVideo:
          unawaited(
            _pickVideoForMedia(
              closeWhenEmptyOnCancel: pending.closeWhenEmptyOnCancel,
            ),
          );
          return;
      }
    });
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
      onFlushFailure: (error, stackTrace, reason) {
        unawaited(
          AppExceptionTelemetryService.instance.recordHandledException(
            source: 'content.create.draft_autosave.$reason',
            error: error,
            stackTrace: stackTrace,
          ),
        );
      },
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
    _publicationCancellationSignal?.cancel();
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

  @override
  void didPopNext() {
    _resumeCreateActionContinuation();
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
    if (width >= AppSpacing.wideBreakpoint) {
      return 5;
    }
    if (width >= AppSpacing.expandedBreakpoint) {
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

  void _doClose() {
    final navigator = Navigator.maybeOf(context);
    if (navigator != null && navigator.canPop()) {
      navigator.pop();
      return;
    }
    // Widget tests may not mount a GoRouter；无路由时已经没有可关闭的页面栈。
    GoRouter.maybeOf(context)?.go(AppRoutePaths.home);
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
      filterRepository: ref.read(imageEditorFilterRepositoryProvider),
    );
  }

  Future<String?> _generateVideoThumbnail(String path) async {
    try {
      return await IosVideoEditingService().generateThumbnail(
        videoPath: path,
        maxDimension: 360,
      );
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'content.create.video_thumbnail',
          error: error,
          stackTrace: stackTrace,
        ),
      );
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
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'content.create.video_metadata',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      return _VideoMetadataProbe.empty;
    } finally {
      await controller.dispose();
    }
  }

  Future<List<CreateCircleOption>> _loadJoinedCircles() {
    return _circleService.listCircles(ref.read(circlesListQueryProvider));
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
        // 推荐圈子位需要真实推荐 operation（规格增量走 /prd）；
        // 在此之前只展示已加入圈子，不再用本地合成推荐。
        builder: (_) => CreatePublishConfirmSheet(
          initialSettings: state.settings,
          locationCoordinator: ref.read(createLocationCoordinatorProvider),
          joinedCircles: joinedCircles,
          recommendedCircles: const [],
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
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      if (next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated)) {
        _resumeCreateActionContinuation();
      }
    });
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _resumeCreateActionContinuation();
        }
      });
    }
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
}
