part of 'customizable_chat_input_bar.dart';

extension _CustomizableChatInputBarVoice on _CustomizableChatInputBarState {
  void _toggleVoiceMode() {
    if (widget.disabled) return;
    _updateState(() {
      _isVoiceMode = !_isVoiceMode;
      _panelMode = ChatInputPanelMode.none;
      if (_isVoiceMode) {
        _focusNode.unfocus();
      } else {
        _focusNode.requestFocus();
      }
    });
  }

  Future<void> _startVoiceRecord() async {
    if (_isRecording) return;
    final hasPermission =
        await (widget.onRequestMicPermission?.call() ??
            Future<bool>.value(true));
    if (!mounted) return;
    if (!hasPermission) {
      return;
    }
    if (!_voicePointerActive) {
      return;
    }
    _recordStartAt = DateTime.now();
    final didStart = await (widget.onStartRecord?.call() ?? Future.value(true));
    if (!mounted || !didStart) {
      _recordStartAt = null;
      _voicePointerActive = false;
      _voicePointerStartGlobal = null;
      return;
    }
    if (!_voicePointerActive) {
      _recordStartAt = null;
      _voicePointerStartGlobal = null;
      await widget.onCancelRecord?.call();
      return;
    }
    _updateState(() {
      _isRecording = true;
      _isVoiceCancelling = false;
    });
    _voiceMaxTimer?.cancel();
    _voiceMaxTimer = Timer(const Duration(minutes: 2), () {
      if (!mounted || !_isRecording) return;
      _voicePointerActive = false;
      _voicePointerStartGlobal = null;
      unawaited(_stopVoiceRecordAndSend());
    });
    _startVoiceElapsedTicker();
    _startWave();
  }

  Future<void> _stopVoiceRecordAndSend() async {
    if (!_isRecording) return;
    if (_isVoiceCancelling) {
      await _cancelVoiceRecord();
      return;
    }
    final start = _recordStartAt ?? DateTime.now();
    final duration = DateTime.now().difference(start);
    _recordStartAt = null;
    _voicePointerActive = false;
    _voicePointerStartGlobal = null;
    _voiceMaxTimer?.cancel();
    _voiceMaxTimer = null;
    _voiceElapsedTimer?.cancel();
    _voiceElapsedTimer = null;
    _stopWave();
    _updateState(() {
      _isRecording = false;
      _isVoiceCancelling = false;
    });
    await widget.onStopRecord?.call(duration);
  }

  Future<void> _cancelVoiceRecord() async {
    if (!_isRecording) return;
    _recordStartAt = null;
    _voicePointerActive = false;
    _voicePointerStartGlobal = null;
    _voiceMaxTimer?.cancel();
    _voiceMaxTimer = null;
    _voiceElapsedTimer?.cancel();
    _voiceElapsedTimer = null;
    _stopWave();
    _updateState(() {
      _isRecording = false;
      _isVoiceCancelling = false;
    });
    await widget.onCancelRecord?.call();
  }

  void _updateVoiceCancelState(Offset globalPosition) {
    if (!_isRecording) return;
    final start = _voicePointerStartGlobal;
    if (start == null) return;
    final shouldCancel = globalPosition.dy < start.dy - AppSpacing.buttonHeight;
    if (shouldCancel == _isVoiceCancelling) return;
    _updateState(() => _isVoiceCancelling = shouldCancel);
  }

  void _startWave() {
    if (!_waveController.isAnimating) {
      _waveController.repeat(reverse: true);
    }
    _voiceAmplitudeSub?.cancel();
    final stream = widget.voiceAmplitudeStream;
    if (stream != null) {
      _voiceAmplitudeSub = stream.listen((samples) {
        if (!mounted || !_isRecording || samples.isEmpty) return;
        _pushVoiceAmplitude(_normalizeRawAmplitude(samples.last));
      });
      return;
    }
    _waveTicker?.cancel();
    _waveTicker = Timer.periodic(const Duration(milliseconds: 120), (_) {
      if (!mounted || !_isRecording) return;
      _pushVoiceAmplitude(0.15);
    });
  }

  void _startVoiceElapsedTicker() {
    _voiceElapsedTimer?.cancel();
    _voiceElapsedTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted || !_isRecording) return;
      _updateState(() {});
    });
  }

  void _stopWave() {
    _waveTicker?.cancel();
    _waveTicker = null;
    _voiceAmplitudeSub?.cancel();
    _voiceAmplitudeSub = null;
    _waveController.stop();
    _waveController.reset();
    _updateState(() {
      for (var i = 0; i < _waveBars.length; i++) {
        _waveBars[i] = 0.2;
      }
    });
  }

  double _normalizeRawAmplitude(double db) {
    const minDb = -60.0;
    if (db <= minDb) return 0.05;
    if (db >= 0) return 1.0;
    return ((db - minDb) / -minDb).clamp(0.05, 1.0).toDouble();
  }

  void _pushVoiceAmplitude(double value) {
    _updateState(() {
      _waveBars
        ..removeAt(0)
        ..add(value.clamp(0.05, 1.0).toDouble());
    });
  }

  Duration get _voiceElapsed {
    final start = _recordStartAt;
    if (!_isRecording || start == null) return Duration.zero;
    return DateTime.now().difference(start);
  }

  String _voiceElapsedText() {
    final elapsed = _voiceElapsed;
    final totalSeconds = elapsed.inSeconds.clamp(0, 120);
    final minutes = totalSeconds ~/ 60;
    final seconds = totalSeconds % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }

  bool get _isVoiceMaxDurationSoon =>
      _isRecording && _voiceElapsed >= const Duration(seconds: 110);

  Widget _buildVoicePanel() {
    final isPressed = _isRecording;
    final fill = _composerInputFill(context);
    final sepIdle = _separatorColor(context).withValues(alpha: 0.12);
    final canceling = _isVoiceCancelling;
    return ClipRRect(
      borderRadius: BorderRadius.circular(
        _CustomizableChatInputBarState._fieldCornerRadius,
      ),
      child: ColoredBox(
        color: fill,
        child: SizedBox(
          height: _CustomizableChatInputBarState._composerCenterMinHeight,
          width: double.infinity,
          child: Listener(
            key: TestKeys.chatInputVoiceHoldButton,
            behavior: HitTestBehavior.opaque,
            onPointerDown: (event) {
              if (widget.disabled) {
                return;
              }
              _voicePointerActive = true;
              _voicePointerStartGlobal = event.position;
              unawaited(_startVoiceRecord());
            },
            onPointerMove: widget.disabled
                ? null
                : (event) => _updateVoiceCancelState(event.position),
            onPointerUp: (_) {
              if (widget.disabled) {
                return;
              }
              _voicePointerActive = false;
              _voicePointerStartGlobal = null;
              unawaited(_stopVoiceRecordAndSend());
            },
            onPointerCancel: (_) {
              if (widget.disabled) {
                return;
              }
              _voicePointerActive = false;
              _voicePointerStartGlobal = null;
              unawaited(_cancelVoiceRecord());
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              curve: Curves.easeOut,
              alignment: Alignment.center,
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
              decoration: BoxDecoration(
                color: isPressed
                    ? (canceling
                          ? AppColors.error.withValues(alpha: 0.1)
                          : AppColors.primaryColor.withValues(alpha: 0.08))
                    : AppColors.transparent,
                border: Border.all(
                  color: isPressed
                      ? (canceling ? AppColors.error : AppColors.primaryColor)
                      : sepIdle,
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Flexible(
                    child: Text(
                      isPressed
                          ? (canceling
                                ? ChatText.chatVoiceReleaseCancel
                                : ChatText.chatVoiceReleaseToSend)
                          : ChatText.chatVoiceHoldToTalk,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                      style: _composerTextStyle(context).copyWith(
                        color: isPressed
                            ? (canceling
                                  ? AppColors.error
                                  : AppColors.primaryColor)
                            : _foregroundPrimary(context),
                        fontWeight: AppTypography.regular,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildVoiceRecordHud() {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 180),
      switchInCurve: Curves.easeOut,
      switchOutCurve: Curves.easeIn,
      child: !_isRecording
          ? const SizedBox.shrink()
          : Padding(
              key: TestKeys.chatInputVoiceRecordHud,
              padding: EdgeInsets.only(bottom: AppSpacing.sm),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color:
                      (_isVoiceCancelling
                              ? AppColors.error
                              : AppColors.primaryColor)
                          .withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                  border: Border.all(
                    color:
                        (_isVoiceCancelling
                                ? AppColors.error
                                : AppColors.primaryColor)
                            .withValues(alpha: 0.2),
                  ),
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupSm,
                  ),
                  child: Row(
                    children: [
                      Icon(
                        _isVoiceCancelling
                            ? CupertinoIcons.xmark_circle_fill
                            : CupertinoIcons.mic_fill,
                        size: AppSpacing.iconSmall,
                        color: _isVoiceCancelling
                            ? AppColors.error
                            : AppColors.primaryColor,
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _isVoiceCancelling
                                  ? ChatText.chatVoiceReleaseCancel
                                  : (_isVoiceMaxDurationSoon
                                        ? ChatText.chatVoiceMaxDurationSoon
                                        : ChatText.chatVoiceSlideCancel),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                fontWeight: AppTypography.medium,
                                color: _isVoiceCancelling
                                    ? AppColors.error
                                    : AppColors.primaryColor,
                              ),
                            ),
                            SizedBox(height: AppSpacing.intraGroupXs),
                            Text(
                              '${ChatText.chatVoiceRecording} ${_voiceElapsedText()}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.xs,
                                color:
                                    (_isVoiceCancelling
                                            ? AppColors.error
                                            : AppColors.primaryColor)
                                        .withValues(alpha: 0.72),
                              ),
                            ),
                          ],
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      SizedBox(height: AppSpacing.md, child: _buildWaveBars()),
                    ],
                  ),
                ),
              ),
            ),
    );
  }

  Widget _buildWaveBars() {
    return AnimatedBuilder(
      key: TestKeys.chatInputVoiceWaveform,
      animation: _waveController,
      builder: (context, _) {
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: _waveBars
              .map((value) {
                final h = 3 + (AppSpacing.md * 0.85 * value);
                return Container(
                  width: AppSpacing.three,
                  height: h,
                  margin: EdgeInsets.symmetric(horizontal: AppSpacing.oneHalf),
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(
                      alpha: 0.45 + value * 0.5,
                    ),
                    borderRadius: BorderRadius.circular(AppSpacing.three),
                  ),
                );
              })
              .toList(growable: false),
        );
      },
    );
  }
}
