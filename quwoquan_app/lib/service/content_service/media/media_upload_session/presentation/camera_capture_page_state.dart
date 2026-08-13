part of 'camera_capture_page.dart';

class _CameraCapturePageState extends State<CameraCapturePage> {
  static const Duration _focusFadeDelay = Duration(milliseconds: 1500);
  static const Duration _recordTick = Duration(milliseconds: 200);

  CameraController? _controller;
  List<CameraDescription> _cameras = const [];
  List<ImageEditorFilterPreset> _cameraFilters =
      const <ImageEditorFilterPreset>[];
  int _cameraIndex = 0;
  bool _isBusy = true;
  bool _showFocusRing = false;
  Offset? _focusPoint;
  UiErrorSemantic? _pageErrorSemantic;
  CameraPhotoSurfaceState _surfaceState = CameraPhotoSurfaceState.idle;
  CameraPhotoFlashMode _flashMode = CameraPhotoFlashMode.off;
  String _selectedFilterId = 'original';
  late MediaPickerEntryMode _mode;
  String? _capturedPhotoPath;
  Timer? _focusTimer;

  // 视频录制态
  bool _audioEnabled = false;
  bool _isRecording = false;
  int _recordedMs = 0;
  String? _recordedVideoPath;
  bool _recordedVideoPreviewFailed = false;
  Timer? _recordTimer;

  ImageEditorFilterCatalog get _filterRepository => widget.filterRepository;

  bool get _isVideoMode => _mode == MediaPickerEntryMode.video;

  CameraCaptureModePolicy get _modePolicy {
    final policy = widget.modePolicy;
    if (policy != null) {
      return policy;
    }
    if (!widget.allowVideoMode) {
      return CameraCaptureModePolicy.photoOnly;
    }
    return widget.initialMode == MediaPickerEntryMode.video
        ? CameraCaptureModePolicy.videoOnly
        : CameraCaptureModePolicy.photoOnly;
  }

  bool get _canSwitchCaptureMode =>
      _modePolicy == CameraCaptureModePolicy.switchable;

  void _setMountedState(VoidCallback update) {
    if (!mounted) {
      return;
    }
    setState(update);
  }

  MediaPickerEntryMode _normalizedInitialMode() {
    switch (_modePolicy) {
      case CameraCaptureModePolicy.photoOnly:
        return MediaPickerEntryMode.image;
      case CameraCaptureModePolicy.videoOnly:
        return MediaPickerEntryMode.video;
      case CameraCaptureModePolicy.switchable:
        return widget.initialMode == MediaPickerEntryMode.video
            ? MediaPickerEntryMode.video
            : MediaPickerEntryMode.image;
    }
  }

  @override
  void initState() {
    super.initState();
    _mode = _normalizedInitialMode();
    _audioEnabled = _isVideoMode;
    _capturedPhotoPath =
        widget.initialCapturedPhotoPath?.trim().isNotEmpty == true
        ? widget.initialCapturedPhotoPath!.trim()
        : null;
    _surfaceState = _capturedPhotoPath == null
        ? CameraPhotoSurfaceState.idle
        : CameraPhotoSurfaceState.preview;
    unawaited(_loadCameraFilters());
    _initCamera();
    unawaited(
      _isVideoMode
          ? _emitVideoTelemetry('camera_video_enter')
          : _emitTelemetry('camera_photo_enter'),
    );
  }

  @override
  void dispose() {
    _focusTimer?.cancel();
    _recordTimer?.cancel();
    final controller = _controller;
    _controller = null;
    unawaited(controller?.dispose());
    super.dispose();
  }

  Future<void> _loadCameraFilters() async {
    final presets = await _filterRepository.loadCameraPhotoPresets();
    if (!mounted || presets.isEmpty) {
      return;
    }
    setState(() {
      _cameraFilters = presets;
      if (!presets.any((preset) => preset.id == _selectedFilterId)) {
        _selectedFilterId = presets.first.id;
      }
    });
  }

  CameraPhotoSurfaceState _resolveReadySurfaceState() {
    if (_capturedPhotoPath != null) {
      return CameraPhotoSurfaceState.preview;
    }
    if (_recordedVideoPath != null) {
      return CameraPhotoSurfaceState.videoPreview;
    }
    return CameraPhotoSurfaceState.ready;
  }

  bool _isPermissionDenied(CameraException error) {
    final code = error.code.toLowerCase();
    return code.contains('accessdenied') ||
        code.contains('permission') ||
        code.contains('denied');
  }

  UiErrorSemantic _cameraUnavailableSemantic() {
    return AppUserRecoveryContract.semanticFor(
      group: AppUserRecoveryGroup.reloadLater,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  UiErrorSemantic _cameraPermissionDeniedSemantic() {
    return AppUserRecoveryContract.semanticFor(
      group: AppUserRecoveryGroup.enablePermission,
      category: UiErrorCategory.permissionRequired,
      scope: UiErrorScope.page,
    );
  }

  int _initialCameraIndex() {
    // 图片与视频都默认后置摄像头。
    final backIndex = _cameras.indexWhere(
      (camera) => camera.lensDirection == CameraLensDirection.back,
    );
    return backIndex >= 0 ? backIndex : _cameraIndex;
  }

  Future<void> _initControllerByIndex(int index, {bool? enableAudio}) async {
    final next = CameraController(
      _cameras[index],
      ResolutionPreset.high,
      enableAudio: enableAudio ?? _audioEnabled,
    );
    final previous = _controller;
    if (previous != null && mounted) {
      setState(() {
        // 先让旧 CameraPreview 离开 Widget 树，再释放 controller。
        _controller = null;
        _isBusy = true;
      });
    }
    await previous?.dispose();
    _controller = next;
    await _controller!.initialize();
    await _applyLightOrFlash();
    if (!mounted) {
      return;
    }
    setState(() {
      _cameraIndex = index;
      _pageErrorSemantic = null;
      _isBusy = false;
      _surfaceState = _resolveReadySurfaceState();
    });
  }

  Future<void> _showCaptureActionError() async {
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: const UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        title: MediaText.cameraCaptureNotCompletedTitle,
        message: MediaText.cameraCaptureFailed,
        primaryAction: UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: FoundationText.confirm,
        ),
        dismissible: true,
      ),
    );
  }

  Future<void> _showVideoCaptureActionError() async {
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: const UiErrorSemantic(
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
        title: MediaText.cameraVideoCaptureNotCompletedTitle,
        message: MediaText.cameraVideoCaptureFailed,
        primaryAction: UiErrorAction(
          type: UiErrorActionType.dismiss,
          label: FoundationText.confirm,
        ),
        dismissible: true,
      ),
    );
  }

  bool get _isFrontCamera {
    if (_cameras.isEmpty ||
        _cameraIndex < 0 ||
        _cameraIndex >= _cameras.length) {
      return false;
    }
    return _cameras[_cameraIndex].lensDirection == CameraLensDirection.front;
  }

  bool get _canUseFlash => !_isFrontCamera;

  ImageEditorFilterPreset? get _selectedFilterPreset {
    for (final preset in _cameraFilters) {
      if (preset.id == _selectedFilterId) {
        return preset;
      }
    }
    return null;
  }

  double get _selectedFilterStrength =>
      _selectedFilterPreset?.defaultStrength ?? 0;

  Future<void> _applyLightOrFlash() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return;
    }
    final effectiveMode = _canUseFlash ? _flashMode : CameraPhotoFlashMode.off;
    try {
      await controller.setFlashMode(
        _isVideoMode
            ? effectiveMode.toCameraTorchMode()
            : effectiveMode.toCameraFlashMode(),
      );
    } catch (_) {
      // 部分设备/模拟器不支持闪光灯/补光灯设置；保持 UI 可恢复，不中断链路。
    }
  }

  Future<void> _emitTelemetry(String eventName) async {
    final telemetry = widget.telemetry;
    if (telemetry == null) {
      return;
    }
    await telemetry(eventName, <String, String>{
      'entry_source': widget.entrySource.telemetryValue,
      'caller': widget.caller.telemetryValue,
      'camera_position': _isFrontCamera ? 'front' : 'back',
      'filter_id': _selectedFilterId,
      'flash_mode': _flashMode.telemetryValue,
      'selected_count_before_capture': widget.selectedCountBeforeCapture
          .toString(),
    });
  }

  Future<void> _emitVideoTelemetry(String eventName) async {
    final telemetry = widget.telemetry;
    if (telemetry == null) {
      return;
    }
    await telemetry(eventName, <String, String>{
      'entry_source': widget.entrySource.telemetryValue,
      'caller': widget.caller.telemetryValue,
      'camera_position': _isFrontCamera ? 'front' : 'back',
      'filter_id': _selectedFilterId,
      'light_mode': _flashMode.telemetryValue,
      'has_audio': _audioEnabled ? 'true' : 'false',
      'duration_ms': _recordedMs.toString(),
    });
  }

  Future<void> _emitModeTelemetry(String suffix) async {
    if (_isVideoMode) {
      await _emitVideoTelemetry('camera_video_$suffix');
    } else {
      await _emitTelemetry('camera_photo_$suffix');
    }
  }

  Future<void> _toggleCamera() async {
    if (_cameras.length <= 1 || _isBusy || _isRecording) {
      return;
    }
    final next = (_cameraIndex + 1) % _cameras.length;
    if (widget.previewBuilder != null) {
      setState(() {
        _cameraIndex = next;
        if (_isFrontCamera) {
          _flashMode = CameraPhotoFlashMode.off;
        }
      });
      await _emitModeTelemetry('switch_camera');
      return;
    }
    setState(() => _isBusy = true);
    await _initControllerByIndex(next);
    if (_isFrontCamera && _flashMode != CameraPhotoFlashMode.off) {
      setState(() => _flashMode = CameraPhotoFlashMode.off);
      await _applyLightOrFlash();
    }
    await _emitModeTelemetry('switch_camera');
  }

  void _retakePhoto() {
    setState(() {
      _capturedPhotoPath = null;
      _isBusy = false;
      _surfaceState = CameraPhotoSurfaceState.ready;
    });
    unawaited(_emitTelemetry('camera_photo_retake'));
  }

  Future<void> _useCapturedPhoto() async {
    final path = _capturedPhotoPath?.trim();
    if (path == null || path.isEmpty) {
      return;
    }
    await _emitTelemetry('camera_photo_use_photo');
    final editedPath = await _openImageEditor(path);
    if (!mounted || editedPath == null || editedPath.trim().isEmpty) {
      return;
    }
    Navigator.of(context).pop(
      CameraCaptureResult(
        path: editedPath.trim(),
        type: CreateMediaType.image,
        filterPresetId: _selectedFilterId,
        entrySource: widget.entrySource,
      ),
    );
  }

  Future<String?> _openImageEditor(String path) async {
    final request = CameraPhotoEditorRequest(
      path: path,
      filterPresetId: _selectedFilterId,
      filterStrength: _selectedFilterStrength,
      caller: widget.caller,
      entrySource: widget.entrySource,
    );
    final launcher = widget.imageEditorLauncher;
    if (launcher != null) {
      return launcher(context, request);
    }
    final result = await Navigator.of(context).push<Object?>(
      CupertinoPageRoute<Object?>(
        builder: (_) => buildImageEditorPage(
          initialPath: request.path,
          source: request.entrySource.telemetryValue,
          initialFilterPresetId: request.filterPresetId,
          initialFilterStrength: request.filterStrength,
          filterRepository: _filterRepository,
        ),
      ),
    );
    return _resolveEditedImagePath(result, path);
  }

  String? _resolveEditedImagePath(Object? result, String fallbackPath) {
    if (result == null) {
      return null;
    }
    if (result is String) {
      final path = result.trim();
      return path.isEmpty ? fallbackPath : path;
    }
    if (result is ImageEditorMultiImageDoneResult) {
      final path = result.path.trim();
      return path.isEmpty ? fallbackPath : path;
    }
    return fallbackPath;
  }

  // ===== 视频录制状态机 =====

  Future<void> _toggleRecording() async {
    if (_isRecording) {
      await _stopRecording();
    } else {
      await _startRecording();
    }
  }

  Future<bool> _defaultMicrophonePermission() async {
    if (!mounted) {
      return false;
    }
    final outcome = await AppPermissionCoordinator.instance.ensure(
      context,
      AppPermissionKind.microphone,
      showPrimer: false,
    );
    return outcome == AppPermissionEnsureOutcome.granted;
  }

  Future<void> _deleteTempFile(String? path) async {
    final trimmed = path?.trim();
    if (trimmed == null || trimmed.isEmpty) {
      return;
    }
    try {
      await (widget.fileStorageGateway ?? createFileStorageGateway()).delete(
        trimmed,
      );
    } catch (error, stackTrace) {
      // 清理失败不阻断用户重拍，但孤儿录制文件会累积占用磁盘，必须上报。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'content.camera_capture.temp_file_cleanup',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  void _retakeVideo() {
    final discarded = _recordedVideoPath;
    setState(() {
      _recordedVideoPath = null;
      _recordedVideoPreviewFailed = false;
      _recordedMs = 0;
      _isBusy = false;
      _surfaceState = CameraPhotoSurfaceState.ready;
    });
    unawaited(_deleteTempFile(discarded));
    unawaited(_emitVideoTelemetry('camera_video_retake'));
  }

  void _useRecordedVideo() {
    final path = _recordedVideoPath?.trim();
    if (path == null || path.isEmpty) {
      return;
    }
    unawaited(_emitVideoTelemetry('camera_video_use_video'));
    Navigator.of(context).pop(
      CameraCaptureResult(
        path: path,
        type: CreateMediaType.video,
        filterPresetId: _selectedFilterId,
        entrySource: widget.entrySource,
      ),
    );
  }

  Future<void> _handleBack() async {
    if (_isRecording || _recordedVideoPath != null) {
      final confirmed = await _confirmDiscardVideo();
      if (!confirmed || !mounted) {
        return;
      }
      if (_isRecording) {
        _recordTimer?.cancel();
        _recordTimer = null;
        await _safeStopRecorderForDiscard();
      }
      await _deleteTempFile(_recordedVideoPath);
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pop();
  }

  Future<void> _safeStopRecorderForDiscard() async {
    try {
      final stop = widget.videoRecordingStop;
      if (stop != null) {
        await stop();
        return;
      }
      final controller = _controller;
      if (controller != null && controller.value.isRecordingVideo) {
        await controller.stopVideoRecording();
      }
    } catch (_) {
      // 放弃路径下停止录制失败可忽略。
    }
  }

  String _formatDuration(int milliseconds) {
    final totalSeconds = (milliseconds / 1000).floor();
    final minutes = (totalSeconds ~/ 60).toString().padLeft(2, '0');
    final seconds = (totalSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    final bg = AppColors.iosGroupedBackgroundDark;
    final controller = _controller;
    final canPreview =
        widget.previewBuilder != null ||
        (controller != null && controller.value.isInitialized);
    final capturedPhotoPath = _capturedPhotoPath;
    final recordedVideoPath = _recordedVideoPath;
    final hasBlockingError =
        _pageErrorSemantic != null &&
        capturedPhotoPath == null &&
        recordedVideoPath == null;
    if (hasBlockingError) {
      return cameraForcedDarkChrome(
        context: context,
        background: bg,
        child: AppScaffold(
          backgroundColor: bg,
          body: SafeArea(
            bottom: false,
            child: Column(
              children: [
                CameraTopBar(title: _topBarTitle, onBack: _handleBack),
                Expanded(
                  child: CameraBlockingState(
                    semantic: _pageErrorSemantic!,
                    onAction: (action) =>
                        unawaited(_handleCameraErrorAction(action)),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }
    return cameraForcedDarkChrome(
      context: context,
      background: bg,
      child: AppScaffold(
        backgroundColor: bg,
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              CameraTopBar(
                title: _topBarTitle,
                onBack: _handleBack,
                trailing: _buildTopBarTrailing(),
              ),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                  ),
                  child: _buildPreviewStage(
                    canPreview: canPreview,
                    controller: controller,
                    capturedPhotoPath: capturedPhotoPath,
                    recordedVideoPath: recordedVideoPath,
                  ),
                ),
              ),
              _buildBottomDock(
                capturedPhotoPath: capturedPhotoPath,
                recordedVideoPath: recordedVideoPath,
              ),
            ],
          ),
        ),
      ),
    );
  }

  String get _topBarTitle {
    if (_isVideoMode) {
      if (_isRecording) {
        return _formatDuration(_recordedMs);
      }
      return MediaText.cameraVideoModeTitle;
    }
    return MediaText.cameraPhotoModeTitle;
  }

  Widget _wrapWithCameraFilter(Widget child) {
    final preset = _selectedFilterPreset;
    if (preset == null || preset.id == 'original') {
      return child;
    }
    return ColorFiltered(
      colorFilter: ColorFilter.matrix(
        buildImageEditorFilterColorMatrix(preset, preset.defaultStrength),
      ),
      child: child,
    );
  }

  Widget _buildPrimaryControls({
    required String? capturedPhotoPath,
    required String? recordedVideoPath,
  }) {
    if (_isVideoMode) {
      if (recordedVideoPath != null) {
        return _buildVideoConfirmationActions();
      }
      return _buildVideoControls();
    }
    if (capturedPhotoPath != null) {
      return _buildPhotoConfirmationActions();
    }
    return _buildPhotoControls();
  }

  void _toggleFilterStrip() {
    if (_isRecording) {
      return;
    }
    final opening = _surfaceState != CameraPhotoSurfaceState.filterOpen;
    setState(() {
      _surfaceState = opening
          ? CameraPhotoSurfaceState.filterOpen
          : CameraPhotoSurfaceState.ready;
    });
    unawaited(_emitModeTelemetry(opening ? 'filter_open' : 'filter_close'));
  }

  void _selectFilter(ImageEditorFilterPreset preset) {
    if (_isRecording) {
      return;
    }
    setState(() => _selectedFilterId = preset.id);
    unawaited(_emitModeTelemetry('filter_select'));
  }

  Future<void> _toggleFlashMode() async {
    if (!_canUseFlash) {
      setState(() => _flashMode = CameraPhotoFlashMode.off);
      return;
    }
    setState(() {
      _flashMode = _flashMode == CameraPhotoFlashMode.off
          ? CameraPhotoFlashMode.on
          : CameraPhotoFlashMode.off;
      _surfaceState = CameraPhotoSurfaceState.ready;
    });
    await _applyLightOrFlash();
    await _emitTelemetry('camera_photo_flash_select');
  }

  Future<void> _toggleLight() async {
    if (!_canUseFlash) {
      setState(() => _flashMode = CameraPhotoFlashMode.off);
      return;
    }
    setState(() {
      _flashMode = _flashMode == CameraPhotoFlashMode.off
          ? CameraPhotoFlashMode.on
          : CameraPhotoFlashMode.off;
    });
    await _applyLightOrFlash();
    await _emitVideoTelemetry('camera_video_light_select');
  }

  void _handlePreviewTapDown(TapDownDetails details, Size previewSize) {
    if (_surfaceState == CameraPhotoSurfaceState.filterOpen ||
        _surfaceState == CameraPhotoSurfaceState.flashOpen) {
      final wasFilterOpen = _surfaceState == CameraPhotoSurfaceState.filterOpen;
      setState(() => _surfaceState = CameraPhotoSurfaceState.ready);
      if (wasFilterOpen) {
        unawaited(_emitModeTelemetry('filter_close'));
      }
      return;
    }
    final local = details.localPosition;
    setState(() {
      _focusPoint = local;
      _showFocusRing = true;
    });
    _focusTimer?.cancel();
    _focusTimer = Timer(_focusFadeDelay, () {
      if (mounted) {
        setState(() => _showFocusRing = false);
      }
    });
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return;
    }
    final normalized = Offset(
      (local.dx / previewSize.width).clamp(0.0, 1.0),
      (local.dy / previewSize.height).clamp(0.0, 1.0),
    );
    unawaited(_setFocusPoint(controller, normalized));
  }

  Future<void> _setFocusPoint(
    CameraController controller,
    Offset normalized,
  ) async {
    try {
      await controller.setFocusPoint(normalized);
      await controller.setExposurePoint(normalized);
    } catch (_) {
      // 模拟器或部分设备不支持对焦点，保留视觉反馈即可。
    }
  }

  Future<void> _handleCameraErrorAction(UiErrorAction action) async {
    switch (action.type) {
      case UiErrorActionType.retry:
      case UiErrorActionType.resubmit:
        await _initCamera();
        return;
      case UiErrorActionType.dismiss:
        if (mounted) {
          Navigator.of(context).pop();
        }
        return;
      case UiErrorActionType.login:
      case UiErrorActionType.openUpdate:
        return;
      case UiErrorActionType.openSettings:
        await AppPermissionCoordinator.instance.openSettings(
          AppPermissionKind.camera,
          onReturn: (granted) {
            if (mounted && granted) {
              unawaited(_initCamera());
            }
          },
        );
        return;
    }
  }

  Widget _buildCapturedPhotoPreview(String path) {
    return Image(
      image: localFileImageProvider(path),
      fit: BoxFit.cover,
      width: double.infinity,
      height: double.infinity,
      errorBuilder: (context, error, stackTrace) => Center(
        child: Text(
          MediaText.cameraCaptureFailed,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.base,
          ),
        ),
      ),
    );
  }

  Widget _buildRecordedVideoPreview(String path) {
    final builder = widget.videoPreviewBuilder;
    if (builder != null) {
      return builder(context, path);
    }
    return _RecordedVideoPreview(
      key: ValueKey<String>('camera-recorded-video-$path'),
      path: path,
      readyProbe: widget.videoFileReadyProbe ?? waitForLocalVideoFileReady,
      onReady: () {
        if (mounted && _recordedVideoPreviewFailed) {
          setState(() => _recordedVideoPreviewFailed = false);
        }
      },
      onFailed: () {
        if (mounted && !_recordedVideoPreviewFailed) {
          setState(() => _recordedVideoPreviewFailed = true);
        }
      },
    );
  }

  Widget _buildPhotoConfirmationActions() {
    return _buildConfirmationActions(
      retakeKey: const ValueKey<String>('camera-retake-photo-action'),
      useKey: const ValueKey<String>('camera-use-photo-action'),
      retakeLabel: MediaText.cameraRetakePhoto,
      useLabel: MediaText.cameraUsePhoto,
      onRetake: _retakePhoto,
      onUse: () => unawaited(_useCapturedPhoto()),
    );
  }

  Widget _buildVideoConfirmationActions() {
    return _buildConfirmationActions(
      retakeKey: const ValueKey<String>('camera-retake-video-action'),
      useKey: const ValueKey<String>('camera-use-video-action'),
      retakeLabel: MediaText.cameraVideoRetake,
      useLabel: MediaText.cameraVideoNext,
      onRetake: _retakeVideo,
      onUse: _useRecordedVideo,
      previewUnavailable: _recordedVideoPreviewFailed,
    );
  }
}

class _RecordedVideoPreviewState extends State<_RecordedVideoPreview> {
  VideoPlayerController? _controller;
  bool _ready = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    unawaited(_init());
  }

  Future<void> _init() async {
    try {
      final controller = await createInitializedLocalVideoController(
        widget.path,
        readyProbe: widget.readyProbe,
      );
      _controller = controller;
      if (!mounted) {
        return;
      }
      setState(() => _ready = true);
      widget.onReady();
      unawaited(_startBestEffortPlayback(controller));
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() => _failed = true);
      widget.onFailed();
    }
  }

  Future<void> _startBestEffortPlayback(
    VideoPlayerController controller,
  ) async {
    try {
      await controller.setLooping(true);
      await controller.setVolume(0);
      await controller.play();
    } catch (_) {
      // 初始化成功即可展示首帧；自动播放失败不应降级为“视频不可预览”。
    }
  }

  @override
  void dispose() {
    unawaited(_controller?.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    if (_failed) {
      return ColoredBox(
        color: AppColors.black,
        child: Center(
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  CupertinoIcons.video_camera_solid,
                  color: AppColors.white.withValues(alpha: 0.82),
                  size: AppSpacing.iconLarge + AppSpacing.iconMedium,
                ),
                SizedBox(height: AppSpacing.interGroupSm),
                Text(
                  MediaText.cameraVideoPreviewUnavailable,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  MediaText.cameraVideoPreviewUnavailableHint,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.72),
                    fontSize: AppTypography.sm,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }
    if (controller == null || !_ready) {
      return ColoredBox(
        color: AppColors.black,
        child: AppRequestFeedback.page(),
      );
    }
    return FittedBox(
      fit: BoxFit.cover,
      clipBehavior: Clip.hardEdge,
      child: SizedBox(
        width: controller.value.size.width,
        height: controller.value.size.height,
        child: VideoPlayer(controller),
      ),
    );
  }
}
