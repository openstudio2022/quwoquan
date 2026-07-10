part of 'camera_capture_page.dart';

extension _CameraCapturePageStateHelpers on _CameraCapturePageState {
  Future<void> _initCamera() async {
    if (mounted) {
      _setMountedState(() {
        _isBusy = true;
        _pageErrorSemantic = null;
        if (_capturedPhotoPath == null && _recordedVideoPath == null) {
          _surfaceState = CameraPhotoSurfaceState.idle;
        }
      });
    }
    try {
      if (widget.previewBuilder != null) {
        _cameras = widget.previewCameraDescriptions;
        if (!mounted) {
          return;
        }
        _setMountedState(() {
          _cameraIndex = _cameras.isEmpty ? 0 : _initialCameraIndex();
          _pageErrorSemantic = null;
          _isBusy = false;
          _surfaceState = _resolveReadySurfaceState();
        });
        return;
      }
      _cameras = await widget.cameraDiscovery();
      if (_cameras.isEmpty) {
        _setMountedState(() {
          if (_capturedPhotoPath == null && _recordedVideoPath == null) {
            _pageErrorSemantic = _cameraUnavailableSemantic();
            _surfaceState = CameraPhotoSurfaceState.error;
          }
          _isBusy = false;
        });
        return;
      }
      await _initControllerByIndex(_initialCameraIndex());
    } on CameraException catch (error) {
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        _pageErrorSemantic = _isPermissionDenied(error)
            ? _cameraPermissionDeniedSemantic()
            : _cameraUnavailableSemantic();
        _surfaceState = _isPermissionDenied(error)
            ? CameraPhotoSurfaceState.permissionDenied
            : CameraPhotoSurfaceState.error;
        _isBusy = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        _pageErrorSemantic = _cameraUnavailableSemantic();
        _surfaceState = CameraPhotoSurfaceState.error;
        _isBusy = false;
      });
    }
  }

  Future<void> _takePhoto() async {
    final controller = _controller;
    final capture = widget.photoCapture;
    if (_isBusy ||
        (capture == null &&
            (controller == null || !controller.value.isInitialized))) {
      return;
    }
    await _emitTelemetry('camera_photo_capture_click');
    _setMountedState(() {
      _isBusy = true;
      _surfaceState = CameraPhotoSurfaceState.capturing;
    });
    try {
      final path = capture == null
          ? (await controller!.takePicture()).path
          : await capture();
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        _capturedPhotoPath = path;
        _isBusy = false;
        _surfaceState = CameraPhotoSurfaceState.preview;
      });
      await _emitTelemetry('camera_photo_capture_success');
    } catch (_) {
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        _isBusy = false;
        _surfaceState = CameraPhotoSurfaceState.ready;
      });
      await _emitTelemetry('camera_photo_capture_failed');
      await _showCaptureActionError();
    }
  }

  Future<void> _startRecording() async {
    if (_isBusy || _isRecording) {
      return;
    }
    if (_surfaceState == CameraPhotoSurfaceState.filterOpen) {
      _setMountedState(() => _surfaceState = CameraPhotoSurfaceState.ready);
    }
    final decision = await _ensureMicrophoneForRecording();
    if (!mounted || decision == _MicrophoneDecision.abort) {
      return;
    }
    if (decision == _MicrophoneDecision.muted) {
      final wasAudioEnabled = _audioEnabled;
      _audioEnabled = false;
      if (wasAudioEnabled && widget.videoRecordingStart == null) {
        await _initControllerByIndex(_cameraIndex, enableAudio: false);
        if (!mounted) {
          return;
        }
      }
    }
    final start = widget.videoRecordingStart;
    try {
      if (start != null) {
        await start();
      } else {
        final controller = _controller;
        if (controller == null || !controller.value.isInitialized) {
          return;
        }
        await controller.startVideoRecording();
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      await _emitVideoTelemetry('camera_video_record_failed');
      await _showVideoCaptureActionError();
      return;
    }
    if (!mounted) {
      return;
    }
    _setMountedState(() {
      _isRecording = true;
      _recordedMs = 0;
      _surfaceState = CameraPhotoSurfaceState.recording;
    });
    _recordTimer = Timer.periodic(_CameraCapturePageState._recordTick, (_) {
      if (!mounted) {
        return;
      }
      _setMountedState(
        () => _recordedMs += _CameraCapturePageState._recordTick.inMilliseconds,
      );
      if (_recordedMs >= widget.maxRecordingMs) {
        unawaited(_stopRecording());
      }
    });
    await _emitVideoTelemetry('camera_video_record_start');
  }

  Future<void> _stopRecording() async {
    if (!_isRecording) {
      return;
    }
    _recordTimer?.cancel();
    _recordTimer = null;
    final elapsed = _recordedMs;
    String? path;
    try {
      final stop = widget.videoRecordingStop;
      if (stop != null) {
        path = await stop();
      } else {
        final controller = _controller;
        if (controller != null && controller.value.isRecordingVideo) {
          final file = await controller.stopVideoRecording();
          path = file.path;
        }
      }
    } catch (_) {
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        _isRecording = false;
        _recordedMs = 0;
        _surfaceState = CameraPhotoSurfaceState.ready;
      });
      await _emitVideoTelemetry('camera_video_record_failed');
      await _showVideoCaptureActionError();
      return;
    }
    if (!mounted) {
      return;
    }
    if (elapsed < widget.minRecordingMs ||
        path == null ||
        path.trim().isEmpty) {
      _setMountedState(() {
        _isRecording = false;
        _recordedMs = 0;
        _surfaceState = CameraPhotoSurfaceState.ready;
      });
      AppToast.show(context, UITextConstants.cameraVideoRecordTooShort);
      await _deleteTempFile(path);
      await _emitVideoTelemetry('camera_video_record_too_short');
      return;
    }
    _setMountedState(() {
      _isRecording = false;
      _recordedVideoPath = path;
      _recordedVideoPreviewFailed = false;
      _surfaceState = CameraPhotoSurfaceState.videoPreview;
    });
    await _emitVideoTelemetry('camera_video_record_success');
  }

  Future<_MicrophoneDecision> _ensureMicrophoneForRecording() async {
    final request = widget.microphonePermissionRequest;
    final granted = request != null
        ? await request()
        : await _defaultMicrophonePermission();
    if (granted) {
      return _MicrophoneDecision.audio;
    }
    if (!mounted) {
      return _MicrophoneDecision.abort;
    }
    final choice = await showAppActionSheet<_MicrophoneChoice>(
      context,
      title: UITextConstants.cameraMicrophonePermissionTitle,
      message: UITextConstants.cameraMicrophonePermission,
      sections: <AppActionSheetSection<_MicrophoneChoice>>[
        AppActionSheetSection<_MicrophoneChoice>(
          items: <AppActionSheetItem<_MicrophoneChoice>>[
            const AppActionSheetItem<_MicrophoneChoice>(
              value: _MicrophoneChoice.openSettings,
              label: UITextConstants.openSettings,
              icon: CupertinoIcons.settings,
            ),
            const AppActionSheetItem<_MicrophoneChoice>(
              value: _MicrophoneChoice.continueMuted,
              label: UITextConstants.cameraMicrophoneContinueMuted,
              icon: CupertinoIcons.mic_slash,
            ),
          ],
        ),
      ],
    );
    if (choice == _MicrophoneChoice.openSettings) {
      await AppPermissionCoordinator.instance.openSettings(
        AppPermissionKind.microphone,
      );
      return _MicrophoneDecision.abort;
    }
    if (choice == _MicrophoneChoice.continueMuted) {
      return _MicrophoneDecision.muted;
    }
    return _MicrophoneDecision.abort;
  }

  Future<bool> _confirmDiscardVideo() async {
    final choice = await showAppBottomModal<bool>(
      context: context,
      builder: (sheetContext) {
        final isDark =
            (CupertinoTheme.of(sheetContext).brightness ??
                MediaQuery.platformBrightnessOf(sheetContext)) ==
            Brightness.dark;
        final background = CupertinoColors.systemGroupedBackground.resolveFrom(
          sheetContext,
        );
        final cardBackground = CupertinoColors.secondarySystemGroupedBackground
            .resolveFrom(sheetContext);
        final titleColor = AppColors.iosLabel(sheetContext);
        final messageColor = AppColors.iosSecondaryLabel(sheetContext);
        final neutralBorder = AppColors.iosSeparator(
          sheetContext,
        ).withValues(alpha: isDark ? 0.22 : 0.16);
        return AppBottomModalSurface(
          onDismiss: () => Navigator.of(sheetContext).pop(),
          backgroundColor: background,
          contentPadding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            0,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: AppSpacing.xl,
                  height: AppSpacing.xs,
                  margin: EdgeInsets.only(bottom: AppSpacing.containerMd),
                  decoration: BoxDecoration(
                    color: AppColors.iosQuaternaryLabel(
                      sheetContext,
                    ).withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.radiusNinetyNine,
                    ),
                  ),
                ),
              ),
              Text(
                UITextConstants.cameraVideoDiscardTitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: titleColor,
                  fontSize: AppTypography.iosTitle3,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                UITextConstants.cameraVideoDiscardMessage,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: messageColor,
                  fontSize: AppTypography.iosBody,
                  height: AppSpacing.textLineHeightBody,
                ),
              ),
              SizedBox(height: AppSpacing.interGroupMd),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: cardBackground,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                  border: Border.all(
                    color: neutralBorder,
                    width: AppSpacing.hairline,
                  ),
                ),
                child: CupertinoButton(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                    vertical: AppSpacing.containerSm,
                  ),
                  onPressed: () => Navigator.of(sheetContext).pop(true),
                  child: Center(
                    child: Text(
                      UITextConstants.cameraVideoDiscardConfirm,
                      style: TextStyle(
                        color: AppColors.iosAccent(sheetContext),
                        fontSize: AppTypography.lg,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.containerSm),
              DecoratedBox(
                decoration: BoxDecoration(
                  color: cardBackground,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                  border: Border.all(
                    color: neutralBorder,
                    width: AppSpacing.hairline,
                  ),
                ),
                child: CupertinoButton(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                    vertical: AppSpacing.containerSm,
                  ),
                  onPressed: () => Navigator.of(sheetContext).pop(false),
                  child: Center(
                    child: Text(
                      UITextConstants.cameraVideoDiscardCancel,
                      style: TextStyle(
                        color: titleColor,
                        fontSize: AppTypography.lg,
                        fontWeight: AppTypography.medium,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
    return choice ?? false;
  }

  Widget? _buildTopBarTrailing() {
    if (_isVideoMode) {
      if (_recordedVideoPath != null) {
        return null;
      }
      return CameraRoundIconButton(
        key: const ValueKey<String>('camera-light-action'),
        icon: _flashMode == CameraPhotoFlashMode.off
            ? CupertinoIcons.lightbulb_slash_fill
            : CupertinoIcons.lightbulb_fill,
        label: UITextConstants.cameraVideoLight,
        enabled: _canUseFlash,
        onTap: () => unawaited(_toggleLight()),
      );
    }
    if (_capturedPhotoPath != null) {
      return null;
    }
    return CameraRoundIconButton(
      key: const ValueKey<String>('camera-flash-action'),
      icon: _flashMode == CameraPhotoFlashMode.off
          ? CupertinoIcons.bolt_slash_fill
          : CupertinoIcons.bolt_fill,
      label: UITextConstants.cameraFlash,
      enabled: _canUseFlash,
      onTap: () => unawaited(_toggleFlashMode()),
    );
  }

  Widget _buildPreviewStage({
    required bool canPreview,
    required CameraController? controller,
    required String? capturedPhotoPath,
    required String? recordedVideoPath,
  }) {
    final isLivePreview =
        capturedPhotoPath == null && recordedVideoPath == null;
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: isLivePreview
              ? (details) => _handlePreviewTapDown(details, size)
              : null,
          child: Container(
            key: const ValueKey<String>('camera-preview-stage'),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.zero,
              color: AppColorsFunctional.getColor(
                true,
                ColorType.backgroundSecondary,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: Stack(
              fit: StackFit.expand,
              children: [
                if (capturedPhotoPath != null)
                  _wrapWithCameraFilter(
                    _buildCapturedPhotoPreview(capturedPhotoPath),
                  )
                else if (recordedVideoPath != null)
                  _wrapWithCameraFilter(
                    _buildRecordedVideoPreview(recordedVideoPath),
                  )
                else if (widget.previewBuilder != null)
                  _wrapWithCameraFilter(widget.previewBuilder!(context))
                else if (canPreview && controller != null)
                  _wrapWithCameraFilter(CameraPreview(controller))
                else
                  const Center(child: CupertinoActivityIndicator()),
                if (isLivePreview) const CameraRuleOfThirdsGrid(),
                if (_showFocusRing && _focusPoint != null)
                  CameraFocusRing(center: _focusPoint!),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildBottomDock({
    required String? capturedPhotoPath,
    required String? recordedVideoPath,
  }) {
    final canShowModeSwitcher =
        _canSwitchCaptureMode &&
        capturedPhotoPath == null &&
        recordedVideoPath == null &&
        !_isRecording;
    return SafeArea(
      key: const ValueKey<String>('camera-bottom-dock'),
      top: false,
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
          AppSpacing.containerSm,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (canShowModeSwitcher) ...[
              _buildModeSwitcher(),
              SizedBox(height: AppSpacing.containerSm),
            ],
            _buildPrimaryControls(
              capturedPhotoPath: capturedPhotoPath,
              recordedVideoPath: recordedVideoPath,
            ),
            if (_surfaceState == CameraPhotoSurfaceState.filterOpen) ...[
              SizedBox(height: AppSpacing.containerXs),
              CameraFilterStrip(
                presets: _cameraFilters,
                selectedPresetId: _selectedFilterId,
                onSelected: _selectFilter,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildModeSwitcher() {
    final surface = AppColors.white.withValues(alpha: 0.14);
    return Center(
      child: Container(
        key: const ValueKey<String>('camera-mode-switcher'),
        height: AppSpacing.buttonHeightSm,
        padding: EdgeInsets.all(AppSpacing.hairline * 2),
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _buildModeSegment(
              key: const ValueKey<String>('camera-mode-photo'),
              label: UITextConstants.cameraPhotoMode,
              selected: !_isVideoMode,
              mode: MediaPickerEntryMode.image,
            ),
            _buildModeSegment(
              key: const ValueKey<String>('camera-mode-video'),
              label: UITextConstants.cameraVideoRecord,
              selected: _isVideoMode,
              mode: MediaPickerEntryMode.video,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildModeSegment({
    required Key key,
    required String label,
    required bool selected,
    required MediaPickerEntryMode mode,
  }) {
    final foreground = selected
        ? AppColors.black
        : AppColors.white.withValues(alpha: 0.78);
    return CupertinoButton(
      key: key,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: 0,
      ),
      minimumSize: Size(
        AppSpacing.buttonHeightSm - AppSpacing.hairline * 4,
        AppSpacing.buttonHeightSm - AppSpacing.hairline * 4,
      ),
      onPressed: selected || _isBusy
          ? null
          : () => unawaited(_switchCaptureMode(mode)),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 140),
        alignment: Alignment.center,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerXs),
        decoration: BoxDecoration(
          color: selected ? AppColors.white : AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: foreground,
            fontSize: AppTypography.iosCaption1,
            fontWeight: AppTypography.bold,
            height: AppTypography.lineHeightTight,
          ),
        ),
      ),
    );
  }

  Future<void> _switchCaptureMode(MediaPickerEntryMode mode) async {
    if (!_canSwitchCaptureMode ||
        _mode == mode ||
        _isBusy ||
        _isRecording ||
        _capturedPhotoPath != null ||
        _recordedVideoPath != null) {
      return;
    }
    _setMountedState(() {
      _mode = mode;
      _audioEnabled = _isVideoMode;
      _flashMode = CameraPhotoFlashMode.off;
      _surfaceState = CameraPhotoSurfaceState.ready;
    });
    if (widget.previewBuilder == null && _controller != null) {
      await _initControllerByIndex(_cameraIndex, enableAudio: _audioEnabled);
    }
    await (_isVideoMode
        ? _emitVideoTelemetry('camera_video_enter')
        : _emitTelemetry('camera_photo_enter'));
  }

  Widget _buildPhotoControls() {
    return Row(
      children: [
        Expanded(
          child: Align(
            alignment: Alignment.center,
            child: CameraBottomTextAction(
              key: const ValueKey<String>('camera-filter-action'),
              icon: CupertinoIcons.slider_horizontal_3,
              label: UITextConstants.cameraFilter,
              onTap: _toggleFilterStrip,
              semanticIconKey: kEditorIconFilterRings,
              selected: _surfaceState == CameraPhotoSurfaceState.filterOpen,
            ),
          ),
        ),
        SizedBox(
          width: CameraShellMetrics.primaryButtonOuterSize,
          child: Center(
            child: CameraShutterButton(busy: _isBusy, onTap: _takePhoto),
          ),
        ),
        Expanded(
          child: Align(
            alignment: Alignment.center,
            child: _cameras.length > 1
                ? CameraBottomTextAction(
                    key: const ValueKey<String>('camera-rotate-action'),
                    icon: CupertinoIcons.camera_rotate_fill,
                    label: UITextConstants.cameraSwitchLens,
                    onTap: () => unawaited(_toggleCamera()),
                  )
                : SizedBox.square(dimension: AppSpacing.minInteractiveSize),
          ),
        ),
      ],
    );
  }

  Widget _buildVideoControls() {
    final locked = _isRecording;
    return Row(
      children: [
        Expanded(
          child: Align(
            alignment: Alignment.center,
            child: CameraBottomTextAction(
              key: const ValueKey<String>('camera-filter-action'),
              icon: CupertinoIcons.slider_horizontal_3,
              label: UITextConstants.cameraFilter,
              onTap: _toggleFilterStrip,
              semanticIconKey: kEditorIconFilterRings,
              selected: _surfaceState == CameraPhotoSurfaceState.filterOpen,
              enabled: !locked,
            ),
          ),
        ),
        SizedBox(
          width: CameraShellMetrics.primaryButtonOuterSize,
          child: Center(
            child: CameraRecordButton(
              recording: _isRecording,
              busy: _isBusy,
              onTap: () => unawaited(_toggleRecording()),
            ),
          ),
        ),
        Expanded(
          child: Align(
            alignment: Alignment.center,
            child: _cameras.length > 1
                ? CameraBottomTextAction(
                    key: const ValueKey<String>('camera-rotate-action'),
                    icon: CupertinoIcons.camera_rotate_fill,
                    label: UITextConstants.cameraSwitchLens,
                    onTap: () => unawaited(_toggleCamera()),
                    enabled: !locked,
                  )
                : SizedBox.square(dimension: AppSpacing.minInteractiveSize),
          ),
        ),
      ],
    );
  }

  Widget _buildConfirmationActions({
    required Key retakeKey,
    required Key useKey,
    required String retakeLabel,
    required String useLabel,
    required VoidCallback onRetake,
    required VoidCallback onUse,
    bool previewUnavailable = false,
  }) {
    const isDarkChrome = true;
    final mediaForeground = AppColorsFunctional.getColor(
      isDarkChrome,
      ColorType.mediaThumbnailOverlayForeground,
    );
    final mediaMutedForeground = AppColorsFunctional.getColor(
      isDarkChrome,
      ColorType.mediaThumbnailOverlayForegroundMuted,
    );
    final inverseForeground = AppColorsFunctional.getColor(
      isDarkChrome,
      ColorType.foregroundInverse,
    );
    final retakeFill = previewUnavailable
        ? mediaForeground.withValues(alpha: 0.92)
        : mediaForeground.withValues(alpha: 0.14);
    final retakeBorder = previewUnavailable
        ? mediaForeground.withValues(alpha: 0.24)
        : mediaForeground.withValues(alpha: 0.24);
    final retakeTextColor = previewUnavailable
        ? inverseForeground.withValues(alpha: 0.92)
        : mediaForeground;
    final useFill = previewUnavailable
        ? mediaForeground.withValues(alpha: 0.08)
        : AppColors.primaryColor;
    final useBorder = previewUnavailable
        ? mediaForeground.withValues(alpha: 0.14)
        : AppColors.primaryColor;
    final useTextColor = previewUnavailable
        ? mediaMutedForeground.withValues(alpha: 0.62)
        : mediaForeground;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: [
          Expanded(
            child: CupertinoButton(
              key: retakeKey,
              padding: EdgeInsets.zero,
              onPressed: onRetake,
              child: Container(
                height: AppSpacing.buttonHeight,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: retakeFill,
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  border: Border.all(
                    color: retakeBorder,
                    width: AppSpacing.hairline,
                  ),
                ),
                child: Text(
                  retakeLabel,
                  style: TextStyle(
                    color: retakeTextColor,
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: CupertinoButton(
              key: useKey,
              padding: EdgeInsets.zero,
              onPressed: onUse,
              child: Container(
                height: AppSpacing.buttonHeight,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: useFill,
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  border: Border.all(
                    color: useBorder,
                    width: AppSpacing.hairline,
                  ),
                ),
                child: Center(
                  child: Text(
                    useLabel,
                    style: TextStyle(
                      color: useTextColor,
                      fontSize: AppTypography.base,
                      fontWeight: previewUnavailable
                          ? FontWeight.w600
                          : FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
