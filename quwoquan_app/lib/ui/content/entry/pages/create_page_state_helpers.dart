part of 'create_page.dart';

extension _CreatePageStateHelpers on _CreatePageState {
  void _autoScrollDuringMediaDrag(Offset globalPosition) {
    if (!_scrollController.hasClients || !mounted) {
      return;
    }
    final overlay = Overlay.maybeOf(context);
    final renderBox = overlay?.context.findRenderObject() as RenderBox?;
    if (renderBox == null) {
      return;
    }
    final local = renderBox.globalToLocal(globalPosition);
    final viewportHeight = MediaQuery.sizeOf(context).height;
    final topBoundary =
        MediaQuery.paddingOf(context).top + AppSpacing.toolbarHeight;
    final bottomBoundary =
        viewportHeight - MediaQuery.paddingOf(context).bottom;
    const edgeThreshold = 96.0;
    const maxDelta = 18.0;

    double delta = 0;
    if (local.dy < topBoundary + edgeThreshold) {
      final ratio = ((topBoundary + edgeThreshold - local.dy) / edgeThreshold)
          .clamp(0.0, 1.0);
      delta = -maxDelta * ratio;
    } else if (local.dy > bottomBoundary - edgeThreshold) {
      final ratio =
          ((local.dy - (bottomBoundary - edgeThreshold)) / edgeThreshold).clamp(
            0.0,
            1.0,
          );
      delta = maxDelta * ratio;
    }

    if (delta.abs() < 0.5) {
      return;
    }

    final nextOffset = (_scrollController.offset + delta).clamp(
      0.0,
      _scrollController.position.maxScrollExtent,
    );
    if ((nextOffset - _scrollController.offset).abs() < 0.1) {
      return;
    }
    _scrollController.jumpTo(nextOffset);
  }

  Future<void> _onCloseRequest() async {
    final state = ref.read(createEditorProvider);
    if (!state.hasContent &&
        _activeDraftId == null &&
        !_draftSessionController.isDirty) {
      _doClose();
      return;
    }
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(UITextConstants.createExitConfirmTitle),
          content: const Text(UITextConstants.createExitConfirmDesc),
          actions: <Widget>[
            CupertinoDialogAction(
              key: TestKeys.createDiscardAndExitButton,
              isDestructiveAction: true,
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                _draftSessionController.suppressAfterDiscard();
                await _clearCurrentDraft();
                await reportCreateEditorSurfaceEvent(
                  ref,
                  'draft_autosave_drop_on_discard',
                  createEditorSurfaceExtrasEditorKind(state.editorKind),
                );
                _doClose();
              },
              child: const Text(UITextConstants.discard),
            ),
            CupertinoDialogAction(
              key: TestKeys.createSaveAndExitButton,
              isDefaultAction: true,
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                await _saveDraft(flushReason: 'explicit');
                _doClose();
              },
              child: const Text(UITextConstants.saveDraft),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(UITextConstants.cancel),
            ),
          ],
        );
      },
    );
  }

  Future<CreateMediaPickerResult?> _openMediaPicker({
    required MediaPickerEntryMode mode,
    required int maxSelection,
    List<String> initialPaths = const <String>[],
  }) async {
    final initialSelection = initialPaths
        .map(
          (path) => CreateMediaItem(
            id: path,
            path: path,
            type: mode == MediaPickerEntryMode.video
                ? CreateMediaType.video
                : CreateMediaType.image,
            source: CreateMediaSource.album,
          ),
        )
        .toList(growable: false);
    await _flushDraftIfDirty('subpage_push');
    if (!mounted) {
      return null;
    }
    final launcher = widget.mediaPickerLauncher;
    if (launcher != null) {
      return launcher(
        context,
        mode: mode,
        maxSelection: maxSelection,
        initialPaths: initialPaths,
      );
    }
    // 能力位路由（非平台名分叉）：桌面无系统相册（mediaLibrary == false）但有本机文件
    // 系统（hasLocalFileSystem），图片选择改走「选目录 + 递归扫描」的桌面选择器；
    // 其余平台（含 web 的 mediaLibrary）仍走系统相册 CreateMediaPickerPage。
    final caps = ref.read(platformCapabilitiesProvider);
    if (shouldUseDesktopImagePicker(caps, mode)) {
      return Navigator.of(context).push<CreateMediaPickerResult>(
        MaterialPageRoute<CreateMediaPickerResult>(
          settings: const RouteSettings(
            name: PageAccessInternalRoutes.createMediaPicker,
          ),
          fullscreenDialog: true,
          builder: (_) => DesktopImagePickerPage(maxSelection: maxSelection),
        ),
      );
    }
    return Navigator.of(context).push<CreateMediaPickerResult>(
      MaterialPageRoute<CreateMediaPickerResult>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createMediaPicker,
        ),
        fullscreenDialog: true,
        builder: (_) => CreateMediaPickerPage(
          entryMode: mode,
          maxSelection: maxSelection,
          initialSelection: initialSelection,
        ),
      ),
    );
  }

  Future<void> _pickImagesForCurrentEditor() async {
    if (!await requireLogin(ref, context, AuthGateReason.mediaUpload)) {
      return;
    }
    if (!mounted) return;
    // 文本编辑器走 node 级插入
    final state = ref.read(createEditorProvider);
    if (state.editorKind == CreateEditorKind.text) {
      await _pickImagesForArticleNode(null);
      return;
    }
    if (state.hasVideo && state.editorKind == CreateEditorKind.media) {
      AppToast.show(context, '请先删除当前视频，再改为图片');
      return;
    }
    final remainingSlots =
        (_CreatePageState._kMaxMediaImages - state.imagePaths.length).clamp(
          0,
          _CreatePageState._kMaxMediaImages,
        );
    if (remainingSlots <= 0) {
      AppToast.show(context, '最多添加 ${_CreatePageState._kMaxMediaImages} 张图片');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: const <String>[],
    );
    if (!mounted || result == null) {
      return;
    }
    final paths = result.items
        .where((item) => item.isImage)
        .map((item) => item.path)
        .take(_CreatePageState._kMaxMediaImages)
        .toList(growable: false);
    if (state.editorKind == CreateEditorKind.text) {
      final notifier = ref.read(createEditorProvider.notifier);
      if (paths.isNotEmpty) {
        var anchorNodeId = state.activeArticleBlockId;
        for (final path in paths) {
          anchorNodeId = notifier.insertImageAfterNode(anchorNodeId, path);
        }
      }
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_media_images_selected',
        createEditorSurfaceExtrasMediaBatch(
          count: paths.length,
          editorKind: state.editorKind,
        ),
      );
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .appendImages(
          paths,
          editorKind: state.editorKind,
          maxImages: _CreatePageState._kMaxMediaImages,
        );
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_images_selected',
      createEditorSurfaceExtrasMediaBatch(
        count: paths.length,
        editorKind: state.editorKind,
      ),
    );
  }

  Future<void> _pickVideoForMedia() async {
    if (!await requireLogin(ref, context, AuthGateReason.mediaUpload)) {
      return;
    }
    if (!mounted) return;
    final state = ref.read(createEditorProvider);
    if (state.imagePaths.isNotEmpty) {
      AppToast.show(context, '请先删空图片，再改为视频');
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.video,
      maxSelection: 1,
      initialPaths: state.videoPath.trim().isEmpty
          ? const <String>[]
          : <String>[state.videoPath],
    );
    if (!mounted || result == null || result.items.isEmpty) {
      return;
    }
    final item = result.items.first;
    await waitForLocalVideoPlayable(item.path);
    final thumbnail = await _generateVideoThumbnail(item.path);
    final metadata = await _loadVideoMetadata(item.path);
    final preserved = _deriveVideoEditContext(
      previousState: state,
      nextDurationMs: metadata.durationMs,
    );
    ref
        .read(createEditorProvider.notifier)
        .setVideo(
          item.path,
          editorKind: CreateEditorKind.media,
          thumbnail: thumbnail ?? '',
          originalPath: item.path,
          durationMs: metadata.durationMs,
          trimStartMs: preserved.trimStartMs,
          trimEndMs: preserved.trimEndMs,
          coverTimeMs: preserved.coverTimeMs,
          coverStrategy: preserved.coverTimeMs > 0 ? 'manual' : 'first_frame',
          width: metadata.width,
          height: metadata.height,
          muted: preserved.muted,
        );
    await reportCreateEditorSurfaceEvent(ref, 'create_media_video_selected');
    if (mounted) {
      await _editCurrentVideo();
    }
  }

  Future<void> _openCameraForCurrentEditor({
    MediaPickerEntryMode? forcedMode,
  }) async {
    final state = ref.read(createEditorProvider);
    final initialMode =
        forcedMode ??
        (_prefersVideoEntryForState(state)
            ? MediaPickerEntryMode.video
            : MediaPickerEntryMode.image);
    if (initialMode == MediaPickerEntryMode.image &&
        state.editorKind != CreateEditorKind.text &&
        state.imagePaths.length >= _CreatePageState._kMaxMediaImages) {
      AppToast.show(context, '最多添加 ${_CreatePageState._kMaxMediaImages} 张图片');
      return;
    }
    await _flushDraftIfDirty('subpage_push');
    if (!mounted) {
      return;
    }
    final result = await Navigator.of(context).push<CameraCaptureResult>(
      MaterialPageRoute<CameraCaptureResult>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageCamera,
        ),
        fullscreenDialog: true,
        builder: (context) => _buildCameraPageForCurrentEditor(
          context,
          initialMode: initialMode,
          selectedCountBeforeCapture: state.imagePaths.length,
        ),
      ),
    );
    if (!mounted || result == null) {
      return;
    }
    if (state.editorKind == CreateEditorKind.text) {
      if (result.type == CreateMediaType.video) {
        AppToast.show(context, '写文字编辑器暂不支持视频');
        return;
      }
      ref
          .read(createEditorProvider.notifier)
          .insertImageAfterNode(state.activeArticleBlockId, result.path);
      return;
    }
    if (result.type == CreateMediaType.video) {
      if (state.imagePaths.isNotEmpty) {
        AppToast.show(context, '请先删空图片，再改为视频');
        return;
      }
      await waitForLocalVideoPlayable(result.path);
      final thumbnail = await _generateVideoThumbnail(result.path);
      final metadata = await _loadVideoMetadata(result.path);
      final preserved = _deriveVideoEditContext(
        previousState: state,
        nextDurationMs: metadata.durationMs,
      );
      ref
          .read(createEditorProvider.notifier)
          .setVideo(
            result.path,
            editorKind: CreateEditorKind.media,
            thumbnail: thumbnail ?? '',
            originalPath: result.path,
            durationMs: metadata.durationMs,
            trimStartMs: preserved.trimStartMs,
            trimEndMs: preserved.trimEndMs,
            coverTimeMs: preserved.coverTimeMs,
            coverStrategy: preserved.coverTimeMs > 0 ? 'manual' : 'first_frame',
            width: metadata.width,
            height: metadata.height,
            muted: preserved.muted,
          );
      if (mounted) {
        await _editCurrentVideo();
      }
      return;
    }
    if (state.hasVideo) {
      AppToast.show(context, '请先删除当前视频，再改为图片');
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .appendImages(
          <String>[result.path],
          editorKind: CreateEditorKind.media,
          maxImages: _CreatePageState._kMaxMediaImages,
        );
  }

  Future<void> _editCurrentVideo() async {
    final state = ref.read(createEditorProvider);
    if (!state.hasVideo) {
      return;
    }
    await _flushDraftIfDirty('subpage_push');
    if (!mounted) {
      return;
    }
    final result = await Navigator.of(context).push<VideoEditorResult>(
      MaterialPageRoute<VideoEditorResult>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageVideoEditor,
        ),
        fullscreenDialog: true,
        builder: (_) => VideoEditorPage(
          sourceVideoPath: state.originalVideoPath.trim().isEmpty
              ? state.videoPath
              : state.originalVideoPath,
          initialVideoPath: state.videoPath,
          initialThumbnailPath: state.videoThumbnail,
          initialDurationMs: state.videoDurationMs,
          initialTrimStartMs: state.videoTrimStartMs,
          initialTrimEndMs: state.videoTrimEndMs,
          initialCoverTimeMs: state.videoCoverTimeMs,
          initialMuted: state.videoMuted,
        ),
      ),
    );
    if (!mounted || result == null) {
      return;
    }
    ref
        .read(createEditorProvider.notifier)
        .applyVideoEditing(
          videoPath: result.videoPath,
          thumbnailPath: result.thumbnailPath,
          videoDurationMs: result.durationMs,
          trimStartMs: result.trimStartMs,
          trimEndMs: result.trimEndMs,
          coverTimeMs: result.coverTimeMs,
          coverStrategy: result.coverStrategy,
          width: result.width,
          height: result.height,
          muted: result.muted,
          originalVideoPath: result.originalVideoPath,
        );
    await reportCreateEditorSurfaceEvent(
      ref,
      'create_media_video_edited',
      createEditorSurfaceExtrasVideoEdited(
        muted: result.muted,
        trimStartMs: result.trimStartMs,
        trimEndMs: result.trimEndMs,
      ),
    );
  }

  _VideoEditContext _deriveVideoEditContext({
    required CreateEditorState previousState,
    required int nextDurationMs,
  }) {
    if (!previousState.hasVideo || nextDurationMs <= 0) {
      return _VideoEditContext(
        trimStartMs: 0,
        trimEndMs: 0,
        coverTimeMs: 0,
        muted: false,
      );
    }
    final previousDuration = previousState.videoDurationMs > 0
        ? previousState.videoDurationMs
        : math.max(previousState.videoTrimEndMs, 1000);
    final previousStart = previousState.videoTrimStartMs.clamp(
      0,
      previousDuration,
    );
    final previousEnd = previousState.videoTrimEndMs > 0
        ? previousState.videoTrimEndMs.clamp(
            previousStart + 100,
            previousDuration,
          )
        : previousDuration;
    final startRatio = previousStart / previousDuration;
    final endRatio = previousEnd / previousDuration;
    final coverRatio = previousState.videoCoverTimeMs > 0
        ? previousState.videoCoverTimeMs.clamp(previousStart, previousEnd) /
              previousDuration
        : startRatio;
    final nextStart =
        (nextDurationMs * startRatio).round().clamp(
              0,
              math.max(nextDurationMs - 100, 0),
            )
            as int;
    final rawNextEnd = (nextDurationMs * endRatio).round();
    final nextEnd = rawNextEnd.clamp(nextStart + 100, nextDurationMs);
    final nextCover = (nextDurationMs * coverRatio).round().clamp(
      nextStart,
      nextEnd,
    );
    final keepsFullRange = nextStart == 0 && nextEnd == nextDurationMs;
    return _VideoEditContext(
      trimStartMs: nextStart,
      trimEndMs: keepsFullRange ? 0 : nextEnd,
      coverTimeMs: nextCover,
      muted: previousState.videoMuted,
    );
  }

  Future<void> _editCurrentImage(int index) async {
    final state = ref.read(createEditorProvider);
    if (index < 0 || index >= state.imagePaths.length) {
      return;
    }
    await _flushDraftIfDirty('subpage_push');
    if (!mounted) {
      return;
    }
    final result = await Navigator.of(context).push<Object?>(
      MaterialPageRoute<Object?>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.createPageImagePreview,
        ),
        fullscreenDialog: true,
        builder: (_) => ImageEditorPage(
          initialPath: state.imagePaths[index],
          source: 'create',
          index: index,
          total: state.imagePaths.length,
          imagePaths: state.imagePaths,
        ),
      ),
    );
    if (!mounted) {
      return;
    }
    // 单图：返回编辑后的路径字符串。
    if (result is String && result.trim().isEmpty) {
      return;
    }
    if (result is String) {
      final next = List<String>.from(state.imagePaths);
      next[index] = result;
      ref
          .read(createEditorProvider.notifier)
          .setImages(next, editorKind: state.editorKind, currentIndex: index);
      return;
    }
    // 多图：返回 {'index', 'path', 'paths'} —— 既写回当前编辑结果，也同步编辑器内重排顺序。
    if (result is Map) {
      final payload = Map<String, dynamic>.from(result);
      final reordered = (payload['paths'] as List?)
          ?.map((e) => e.toString())
          .where((e) => e.trim().isNotEmpty)
          .toList(growable: true);
      final editedPath = (payload['path'] as String?)?.trim();
      final returnedIndex = (payload['index'] as num?)?.toInt() ?? index;
      final next = reordered != null && reordered.isNotEmpty
          ? reordered
          : List<String>.from(state.imagePaths);
      final coverIndex = returnedIndex.clamp(0, next.length - 1);
      ref
          .read(createEditorProvider.notifier)
          .setImages(
            next,
            editorKind: state.editorKind,
            currentIndex: coverIndex,
          );
      // editedPath 已由编辑器写入 reordered 对应槽位（多图编辑只改当前图），无需重复落盘。
      assert(
        editedPath == null ||
            next.isEmpty ||
            next.contains(editedPath) ||
            reordered == null,
      );
    }
  }

  Widget _buildImmersiveArticlePage(CreateEditorState state) {
    final background = CupertinoColors.systemBackground.resolveFrom(context);
    final brightness =
        CupertinoTheme.of(context).brightness ?? Brightness.light;
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarBrightness: brightness,
        statusBarIconBrightness: brightness == Brightness.dark
            ? Brightness.light
            : Brightness.dark,
      ),
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
        // Same transparent Material host as main create route (see [AppScaffold]).
        child: Material(
          type: MaterialType.transparency,
          child: KeyedSubtree(
            key: TestKeys.createPage,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              color: background,
              child: SafeArea(
                top: false,
                bottom: false,
                child: Column(
                  children: <Widget>[
                    _buildImmersiveArticleTopBar(state: state),
                    Expanded(
                      child: Padding(
                        padding: EdgeInsets.only(top: AppSpacing.containerSm),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: <Widget>[
                            if (!_unifiedCreateEditorEnabled) ...<Widget>[
                              Padding(
                                padding: EdgeInsets.symmetric(
                                  horizontal: AppSpacing.containerMd,
                                ),
                                child: _buildRollbackBanner(
                                  CupertinoColors.secondaryLabel.resolveFrom(
                                    context,
                                  ),
                                ),
                              ),
                              SizedBox(height: AppSpacing.interGroupSm),
                            ],
                            Expanded(child: _buildTextEditor(state)),
                          ],
                        ),
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

  Widget _buildImmersiveArticleTopBar({required CreateEditorState state}) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentLabel = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final title = _pageTitleForState(state);
    final titleColor = AppNavigationSemanticConstants.barTitleColor(isDark);

    return _buildCreateTopChromeBar(
      collapseProgress: 1,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          KeyedSubtree(
            key: TestKeys.createCloseButton,
            child: AppNavigationBarIconButton(
              icon: CupertinoIcons.back,
              onPressed: _onCloseRequest,
            ),
          ),
          Expanded(
            child: Center(
              child: Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: titleColor,
                  fontSize: AppTypography.iosNavTitle,
                  fontWeight: AppTypography.regular,
                ),
              ),
            ),
          ),
          CupertinoButton(
            key: TestKeys.createPublishButton,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            minimumSize: const Size.square(AppSpacing.buttonHeightSm),
            color: AppColors.iosAccentLight,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            onPressed: _isPublishing ? null : _publish,
            child: _isPublishing
                ? CupertinoActivityIndicator(color: onAccentLabel)
                : Text(
                    UITextConstants.mediaPickerNextStep,
                    style: TextStyle(
                      color: onAccentLabel,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildHeader({
    required CreateEditorState state,
    required double collapseProgress,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final onAccentLabel = AppColorsFunctional.getColor(
      isDark,
      ColorType.badgeForeground,
    );
    final title = _pageTitleForState(state);
    final titleColor = AppNavigationSemanticConstants.barTitleColor(isDark);
    return _buildCreateTopChromeBar(
      collapseProgress: collapseProgress,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          KeyedSubtree(
            key: TestKeys.createCloseButton,
            child: AppNavigationBarIconButton(
              icon: CupertinoIcons.back,
              onPressed: _onCloseRequest,
            ),
          ),
          Expanded(
            child: Center(
              child: Opacity(
                opacity: lerpDouble(0.34, 1, collapseProgress)!,
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: titleColor,
                    fontSize: AppTypography.iosNavTitle,
                    fontWeight: AppTypography.regular,
                  ),
                ),
              ),
            ),
          ),
          CupertinoButton(
            key: TestKeys.createPublishButton,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
            minimumSize: const Size.square(AppSpacing.buttonHeightSm),
            color: AppColors.iosAccentLight,
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            onPressed: _isPublishing ? null : _publish,
            child: _isPublishing
                ? CupertinoActivityIndicator(color: onAccentLabel)
                : Text(
                    UITextConstants.mediaPickerNextStep,
                    style: TextStyle(
                      color: onAccentLabel,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildMediaEditor(CreateEditorState state) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildMediaComposerSection(
          state: state,
          title: _mediaHeaderHintForState(state),
          trailing: state.hasVideo
              ? '仅 1 个视频'
              : '${state.imagePaths.length} / ${_CreatePageState._kMaxMediaImages}',
        ),
        SizedBox(height: AppSpacing.interGroupMd),
        _buildTitleSection(
          state: state,
          titleFieldKey: state.mediaKind == CreateMediaKind.video
              ? TestKeys.createVideoTitleInput
              : TestKeys.createPhotoTitleInput,
        ),
        SizedBox(height: AppSpacing.interGroupSm),
        _buildInputPanel(
          label: '正文',
          currentLength: state.body.length,
          input: CupertinoTextField(
            key: state.mediaKind == CreateMediaKind.video
                ? TestKeys.createVideoBodyInput
                : TestKeys.createPhotoBodyInput,
            controller: _bodyController,
            focusNode: _bodyFocusNode,
            inputFormatters: _bodyInputFormatters,
            maxLines: null,
            minLines: 4,
            padding: EdgeInsets.zero,
            placeholder: '补一段配文，让内容更完整',
            decoration: const BoxDecoration(),
            onChanged: (value) {
              ref.read(createEditorProvider.notifier).updateBody(value);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildInputPanel({
    required String label,
    required int currentLength,
    required Widget input,
  }) {
    return _buildSurfacePanel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                label,
                style: const TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              const Spacer(),
              Text(
                '$currentLength / ${_CreatePageState._kMaxBodyLength}',
                style: TextStyle(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.containerSm,
            ),
            decoration: BoxDecoration(
              color: CupertinoColors.systemBackground.resolveFrom(context),
              borderRadius: BorderRadius.circular(AppSpacing.containerSm),
            ),
            child: DefaultTextStyle(
              style: TextStyle(
                fontSize: AppTypography.base,
                color: CupertinoColors.label.resolveFrom(context),
                height: AppTypography.bodyLineHeight,
              ),
              child: input,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTitleSection({
    required CreateEditorState state,
    required Key titleFieldKey,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (state.titlePresentation == TitlePresentation.collapsed &&
            state.title.trim().isEmpty)
          CupertinoButton(
            key: TestKeys.createTitleToggle,
            padding: EdgeInsets.zero,
            alignment: Alignment.centerLeft,
            onPressed: () {
              ref.read(createEditorProvider.notifier).expandTitle();
              _focusTitleField();
            },
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupSm,
              ),
              decoration: BoxDecoration(
                color: CupertinoColors.secondarySystemGroupedBackground
                    .resolveFrom(context),
                borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                border: Border.all(
                  color: CupertinoColors.separator
                      .resolveFrom(context)
                      .withValues(alpha: 0.14),
                  width: AppSpacing.hairline,
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Icon(
                    CupertinoIcons.text_badge_plus,
                    size: AppSpacing.iconMedium,
                    color: AppColors.iosAccentLight,
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  Text(
                    '添加标题（可选）',
                    style: TextStyle(
                      color: AppColors.iosAccentLight,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          _buildSurfacePanel(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                _buildSectionHeader(title: '标题', trailing: '可选'),
                SizedBox(height: AppSpacing.intraGroupSm),
                CupertinoTextField(
                  key: titleFieldKey,
                  controller: _titleController,
                  focusNode: _titleFocusNode,
                  padding: EdgeInsets.zero,
                  placeholder: '补一个能概括内容的标题',
                  decoration: const BoxDecoration(),
                  onChanged: (value) {
                    ref.read(createEditorProvider.notifier).updateTitle(value);
                  },
                  onEditingComplete: () {
                    if (_titleController.text.trim().isEmpty) {
                      ref
                          .read(createEditorProvider.notifier)
                          .collapseTitleIfEmpty();
                    }
                  },
                ),
              ],
            ),
          ),
      ],
    );
  }
}
