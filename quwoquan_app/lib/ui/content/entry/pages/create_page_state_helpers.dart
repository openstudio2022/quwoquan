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
    if (_isPublishing) {
      if (_publicationCancellationSignal != null) {
        _cancelPublicationUpload();
      } else {
        AppToast.show(context, CreatePageText.publicationSubmitting);
      }
      return;
    }
    final state = ref.read(createEditorProvider);
    if (!state.hasContent &&
        _activeDraftId == null &&
        !_draftSessionController.isDirty) {
      _doClose();
      return;
    }
    await showAppCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) {
        return CupertinoAlertDialog(
          title: const Text(CreationText.createExitConfirmTitle),
          content: const Text(CreationText.createExitConfirmDesc),
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
              child: const Text(CreationText.discard),
            ),
            CupertinoDialogAction(
              key: TestKeys.createSaveAndExitButton,
              isDefaultAction: true,
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                try {
                  await _saveDraft(flushReason: 'explicit');
                  _doClose();
                } catch (error, stackTrace) {
                  // 保存失败时留在编辑器，顶栏显示失败状态；独立记录已处理异常。
                  unawaited(
                    AppExceptionTelemetryService.instance
                        .recordHandledException(
                          source: 'content.create.save_and_exit',
                          error: error,
                          stackTrace: stackTrace,
                          operationId: 'content.local_draft.save',
                        ),
                  );
                }
              },
              child: const Text(CreationText.saveDraft),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(FoundationText.cancel),
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
          filterRepository: ref.read(imageEditorFilterRepositoryProvider),
        ),
      ),
    );
  }

  Future<void> _pickImagesForCurrentEditor({
    bool closeWhenEmptyOnCancel = false,
  }) async {
    if (!await _requireCreateActionLogin(
      CreateActionContinuationKind.pickImages,
      closeWhenEmptyOnCancel: closeWhenEmptyOnCancel,
    )) {
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
      AppToast.show(context, CreationText.createDeleteVideoBeforeImages);
      return;
    }
    final remainingSlots =
        (_CreatePageState._kMaxMediaImages - state.imagePaths.length).clamp(
          0,
          _CreatePageState._kMaxMediaImages,
        );
    if (remainingSlots <= 0) {
      AppToast.show(
        context,
        CreatePageText.maxImagesToast(_CreatePageState._kMaxMediaImages),
      );
      return;
    }
    final result = await _openMediaPicker(
      mode: MediaPickerEntryMode.image,
      maxSelection: remainingSlots,
      initialPaths: const <String>[],
    );
    if (!mounted || result == null || result.items.isEmpty) {
      if (closeWhenEmptyOnCancel &&
          !ref.read(createEditorProvider).hasContent) {
        _doClose();
      }
      return;
    }
    if (result.openOneTapMovie && result.lockedSingleMedia) {
      var generated = '';
      for (final item in result.items) {
        if (item.source == CreateMediaSource.generated) {
          generated = item.path;
          break;
        }
      }
      final sourceImages = result.items
          .where((item) => item.isImage)
          .map((item) => item.path)
          .where((path) => path.trim().isNotEmpty)
          .toList(growable: false);
      if (sourceImages.isEmpty) {
        return;
      }
      ref
          .read(createEditorProvider.notifier)
          .setOneTapMovie(
            sourceImagePaths: sourceImages,
            generatedMediaPath: generated,
            effectId: result.oneTapMovieEffectId,
          );
      await reportCreateEditorSurfaceEvent(
        ref,
        'create_media_one_tap_movie_selected',
        createEditorSurfaceExtrasMediaBatch(
          count: 1,
          editorKind: CreateEditorKind.media,
        ),
      );
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

  Future<void> _pickVideoForMedia({bool closeWhenEmptyOnCancel = false}) async {
    if (!await _requireCreateActionLogin(
      CreateActionContinuationKind.pickVideo,
      closeWhenEmptyOnCancel: closeWhenEmptyOnCancel,
    )) {
      return;
    }
    if (!mounted) return;
    final state = ref.read(createEditorProvider);
    if (state.imagePaths.isNotEmpty) {
      AppToast.show(context, CreationText.createClearImagesBeforeVideo);
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
      if (closeWhenEmptyOnCancel &&
          !ref.read(createEditorProvider).hasContent) {
        _doClose();
      }
      return;
    }
    final item = result.items.first;
    if (!item.isVideo) {
      AppToast.show(context, MediaText.mediaPickerVideoOnly);
      return;
    }
    final prepared = await _prepareVideoForMediaEditor(item.path);
    final preserved = _deriveVideoEditContext(
      previousState: state,
      nextDurationMs: prepared.durationMs,
    );
    ref
        .read(createEditorProvider.notifier)
        .setVideo(
          item.path,
          editorKind: CreateEditorKind.media,
          thumbnail: prepared.thumbnailPath,
          originalPath: item.path,
          durationMs: prepared.durationMs,
          trimStartMs: preserved.trimStartMs,
          trimEndMs: preserved.trimEndMs,
          coverTimeMs: preserved.coverTimeMs,
          coverStrategy: preserved.coverTimeMs > 0 ? 'manual' : 'first_frame',
          width: prepared.width,
          height: prepared.height,
          muted: preserved.muted,
        );
    await reportCreateEditorSurfaceEvent(ref, 'create_media_video_selected');
    if (mounted) {
      await _editCurrentVideo();
    }
  }

  Future<void> _applyVideoPathToMediaEditor(
    String path, {
    required CreateEditorState previousState,
  }) async {
    final prepared = await _prepareVideoForMediaEditor(path);
    final preserved = _deriveVideoEditContext(
      previousState: previousState,
      nextDurationMs: prepared.durationMs,
    );
    ref
        .read(createEditorProvider.notifier)
        .setVideo(
          path,
          editorKind: CreateEditorKind.media,
          thumbnail: prepared.thumbnailPath,
          originalPath: path,
          durationMs: prepared.durationMs,
          trimStartMs: preserved.trimStartMs,
          trimEndMs: preserved.trimEndMs,
          coverTimeMs: preserved.coverTimeMs,
          coverStrategy: preserved.coverTimeMs > 0 ? 'manual' : 'first_frame',
          width: prepared.width,
          height: prepared.height,
          muted: preserved.muted,
        );
    await reportCreateEditorSurfaceEvent(ref, 'create_media_video_selected');
  }

  Future<void> _openCameraForCurrentEditor({
    MediaPickerEntryMode? forcedMode,
    CameraCaptureModePolicy modePolicy = CameraCaptureModePolicy.photoOnly,
    bool closeWhenEmptyOnCancel = false,
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
      AppToast.show(
        context,
        CreatePageText.maxImagesToast(_CreatePageState._kMaxMediaImages),
      );
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
          modePolicy: modePolicy,
          selectedCountBeforeCapture: state.imagePaths.length,
        ),
      ),
    );
    if (!mounted || result == null) {
      if (closeWhenEmptyOnCancel &&
          !ref.read(createEditorProvider).hasContent) {
        _doClose();
      }
      return;
    }
    if (state.editorKind == CreateEditorKind.text) {
      if (result.type == CreateMediaType.video) {
        AppToast.show(
          context,
          CreationText.createTextEditorVideoNotSupported,
        );
        return;
      }
      ref
          .read(createEditorProvider.notifier)
          .insertImageAfterNode(state.activeArticleBlockId, result.path);
      return;
    }
    if (result.type == CreateMediaType.video) {
      if (state.imagePaths.isNotEmpty) {
        AppToast.show(context, CreationText.createClearImagesBeforeVideo);
        return;
      }
      await _applyVideoPathToMediaEditor(result.path, previousState: state);
      if (mounted) {
        await _editCurrentVideo();
      }
      return;
    }
    if (state.hasVideo) {
      AppToast.show(context, CreationText.createDeleteVideoBeforeImages);
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
    final launcher = widget.videoEditorLauncher;
    if (launcher == null &&
        !ref.read(platformCapabilitiesProvider).nativeVideoEditing) {
      AppToast.show(context, MediaText.videoEditorCapabilityUnavailable);
      return;
    }
    await _flushDraftIfDirty('subpage_push');
    if (!mounted) {
      return;
    }
    final result = launcher != null
        ? await launcher(context, state: state)
        : await Navigator.of(context).push<VideoEditorResult>(
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

  Future<CreateVideoPreparationResult> _prepareVideoForMediaEditor(
    String path,
  ) async {
    final probe = widget.videoPreparationProbe;
    if (probe != null) {
      return probe(path);
    }
    await waitForLocalVideoPlayable(path);
    final thumbnail = await _generateVideoThumbnail(path);
    final metadata = await _loadVideoMetadata(path);
    return CreateVideoPreparationResult(
      durationMs: metadata.durationMs,
      thumbnailPath: thumbnail ?? '',
      width: metadata.width,
      height: metadata.height,
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

  Widget _buildDraftToolbarAction({bool immersiveDark = false}) {
    return ValueListenableBuilder<CreateDraftSaveStatus>(
      valueListenable: _draftSessionController.saveStatusListenable,
      builder: (context, status, _) {
        final label = _draftToolbarLabel(status);
        final isRetry = status == CreateDraftSaveStatus.failed;
        final isDraftEntry = status == CreateDraftSaveStatus.idle;
        final foreground = immersiveDark
            ? AppColors.white.withValues(alpha: isRetry ? 0.96 : 0.74)
            : CupertinoColors.secondaryLabel.resolveFrom(context);
        return ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 132),
          child: CupertinoButton(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerXs),
            minimumSize: const Size(0, AppSpacing.buttonHeightSm),
            onPressed: isRetry
                ? () => unawaited(
                    _draftSessionController.flushIfDirty(
                      reason: 'toolbar_retry',
                    ),
                  )
                : isDraftEntry
                ? _openLocalDrafts
                : null,
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.right,
              style: TextStyle(
                color: foreground,
                fontSize: AppTypography.iosCaption1,
                fontWeight: isRetry
                    ? AppTypography.semiBold
                    : AppTypography.medium,
                height: AppTypography.lineHeightTight,
              ),
            ),
          ),
        );
      },
    );
  }

  String _draftToolbarLabel(CreateDraftSaveStatus status) {
    return switch (status) {
      CreateDraftSaveStatus.idle => CreationText.createDraftToolbar,
      CreateDraftSaveStatus.dirty => CreationText.createDraftSaving,
      CreateDraftSaveStatus.saving => CreationText.createDraftSaving,
      CreateDraftSaveStatus.saved => CreationText.createDraftSaved,
      CreateDraftSaveStatus.failed => CreationText.createDraftSaveFailed,
    };
  }

  void _openLocalDrafts() {
    // Widget tests可在无 GoRouter 的最小树中渲染页面；此时入口安全地保持原地。
    GoRouter.maybeOf(context)?.push(AppRoutePaths.localDrafts);
  }

  Widget _buildMediaEditor(CreateEditorState state) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildMediaComposerSection(
          state: state,
          title: _mediaHeaderHintForState(state),
          trailing: state.hasVideo
              ? CreationText.createMediaSingleVideoCaption
              : state.isOneTapMovie
              ? CreationText.createMediaOneTapMovieSingleCaption
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
          label: CreationText.createMediaBodySectionLabel,
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
            placeholder: CreationText.createMediaBodyPlaceholder,
            decoration: const BoxDecoration(),
            onChanged: (value) {
              ref.read(createEditorProvider.notifier).updateMediaBody(value);
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
                    CreationText.createAddTitleWithOptional,
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
                _buildSectionHeader(
                  title: CreatePageText.titleFieldLabel,
                  trailing: CreationText.createFieldOptionalTag,
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                CupertinoTextField(
                  key: titleFieldKey,
                  controller: _titleController,
                  focusNode: _titleFocusNode,
                  padding: EdgeInsets.zero,
                  placeholder: CreationText.createTitleSummaryPlaceholder,
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
