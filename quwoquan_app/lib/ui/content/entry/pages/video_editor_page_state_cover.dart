part of 'video_editor_page.dart';

extension _VideoEditorPageStateCover on _VideoEditorPageState {
  Widget _buildPreviewTimelineStrip() {
    if (_frames.isEmpty) {
      return Container(
        height: AppSpacing.buttonHeight + AppSpacing.lg + AppSpacing.xs,
        decoration: BoxDecoration(
          color: CupertinoColors.systemBackground.resolveFrom(context),
          borderRadius: BorderRadius.circular(AppSpacing.containerSm),
        ),
        alignment: Alignment.center,
        child: Text(
          _framesLoading ? '正在缓存更细颗粒度视频帧...' : '暂无可用预览帧',
          style: TextStyle(
            color: CupertinoColors.secondaryLabel.resolveFrom(context),
            fontSize: AppTypography.sm,
          ),
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
        final playheadRing = AppColorsFunctional.getColor(
          isDark,
          ColorType.white,
        );
        final width = constraints.maxWidth;
        final fraction =
            ((_previewTimeMs - _trimStartMs) /
                    math.max(_trimEndMs - _trimStartMs, 1))
                .clamp(0.0, 1.0);
        final playheadLeft = width * fraction;

        Future<void> previewAtOffset(double dx) async {
          final value = _timelineValueForDx(dx, width);
          _handlePreviewChanged(value);
        }

        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: (details) async {
            await _beginPreviewDrag();
            await previewAtOffset(details.localPosition.dx);
            await _endPreviewDrag();
          },
          onHorizontalDragStart: (_) => _beginPreviewDrag(),
          onHorizontalDragUpdate: (details) =>
              previewAtOffset(details.localPosition.dx),
          onHorizontalDragEnd: (_) => _endPreviewDrag(),
          child: SizedBox(
            height: AppSpacing.buttonHeight + AppSpacing.lg + AppSpacing.xs,
            child: Stack(
              children: <Widget>[
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppSpacing.containerSm),
                  child: Row(
                    children: _frames
                        .map(
                          (frame) => Expanded(
                            child: Image.file(
                              File(frame.path),
                              fit: BoxFit.cover,
                              errorBuilder: (context, error, stackTrace) =>
                                  const ColoredBox(
                                    color: AppColors
                                        .createMediaFallbackGradientBottom,
                                  ),
                            ),
                          ),
                        )
                        .toList(growable: false),
                  ),
                ),
                Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(
                        AppSpacing.containerSm,
                      ),
                      border: Border.all(
                        color: CupertinoColors.separator
                            .resolveFrom(context)
                            .withValues(alpha: 0.16),
                        width: AppSpacing.hairline,
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: (playheadLeft - AppSpacing.oneHalf).clamp(
                    0.0,
                    math.max(width - AppSpacing.three, 0.0),
                  ),
                  top: 0,
                  bottom: 0,
                  child: Container(
                    width: AppSpacing.three,
                    decoration: BoxDecoration(
                      color: AppColors.iosAccentLight,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.radiusNinetyNine,
                      ),
                      boxShadow: <BoxShadow>[
                        BoxShadow(
                          color: AppColors.iosAccentLight.withValues(
                            alpha: 0.32,
                          ),
                          blurRadius: 10,
                        ),
                      ],
                    ),
                  ),
                ),
                Positioned(
                  left: (playheadLeft - AppSpacing.eighteen / 2).clamp(
                    0.0,
                    math.max(width - AppSpacing.eighteen, 0.0),
                  ),
                  top: AppSpacing.six,
                  child: Container(
                    width: AppSpacing.eighteen,
                    height: AppSpacing.eighteen,
                    decoration: BoxDecoration(
                      color: AppColors.iosAccentLight,
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: playheadRing,
                        width: AppSpacing.two,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildCoverSection() {
    return _EditorSection(
      title: '封面时间轴',
      trailing: _framesLoading ? '生成中' : '${_frames.length} 帧',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Slider(
            value: _coverTimeMs.clamp(_trimStartMs, _trimEndMs),
            min: _trimStartMs,
            max: _trimEndMs,
            divisions: math.max(((_trimEndMs - _trimStartMs) / 120).round(), 1),
            label: _formatMs(_coverTimeMs.round()),
            onChanged: _handleCoverChanged,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          SizedBox(
            height: AppSpacing.largeAvatarSize + AppSpacing.lg + AppSpacing.xs,
            child: _frames.isEmpty
                ? Center(
                    child: Text(
                      _framesLoading ? '正在生成视频帧...' : '暂无可选封面帧',
                      style: TextStyle(
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
                        fontSize: AppTypography.sm,
                      ),
                    ),
                  )
                : ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: _frames.length,
                    separatorBuilder: (_, _) =>
                        SizedBox(width: AppSpacing.intraGroupSm),
                    itemBuilder: (context, index) {
                      final isDark =
                          CupertinoTheme.of(context).brightness ==
                          Brightness.dark;
                      final scrimBlack = AppColorsFunctional.getColor(
                        isDark,
                        ColorType.black,
                      );
                      final onVideoFg = AppColorsFunctional.getColor(
                        isDark,
                        ColorType.mediaThumbnailOverlayForeground,
                      );
                      final frame = _frames[index];
                      final selected =
                          frame.timeMs ==
                          _closestFrameTo(
                            _coverTimeMs.round(),
                            _frames,
                          )?.timeMs;
                      return GestureDetector(
                        onTap: () => _selectFrame(frame),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          width: AppSpacing.largeAvatarSize + AppSpacing.ten,
                          padding: EdgeInsets.all(
                            selected ? AppSpacing.two : 0,
                          ),
                          decoration: BoxDecoration(
                            color: CupertinoColors
                                .secondarySystemGroupedBackground
                                .resolveFrom(context),
                            borderRadius: BorderRadius.circular(
                              AppSpacing.containerSm,
                            ),
                            border: Border.all(
                              color: selected
                                  ? AppColors.iosAccentLight
                                  : CupertinoColors.separator
                                        .resolveFrom(context)
                                        .withValues(alpha: 0.16),
                              width: selected
                                  ? AppSpacing.oneHalf
                                  : AppSpacing.hairline,
                            ),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(
                              AppSpacing.containerSm - 2,
                            ),
                            child: Stack(
                              fit: StackFit.expand,
                              children: <Widget>[
                                Image.file(
                                  File(frame.path),
                                  fit: BoxFit.cover,
                                  errorBuilder: (context, error, stackTrace) =>
                                      const ColoredBox(
                                        color: AppColors
                                            .createMediaFallbackGradientBottom,
                                      ),
                                ),
                                Positioned(
                                  left: AppSpacing.intraGroupXs,
                                  right: AppSpacing.intraGroupXs,
                                  bottom: AppSpacing.intraGroupXs,
                                  child: DecoratedBox(
                                    decoration: BoxDecoration(
                                      color: scrimBlack.withValues(alpha: 0.44),
                                      borderRadius: BorderRadius.circular(
                                        AppSpacing.radiusTwenty,
                                      ),
                                    ),
                                    child: Padding(
                                      padding: EdgeInsets.symmetric(
                                        horizontal: AppSpacing.intraGroupXs,
                                        vertical: AppSpacing.intraGroupXs / 2,
                                      ),
                                      child: Text(
                                        _formatMs(frame.timeMs),
                                        textAlign: TextAlign.center,
                                        style: TextStyle(
                                          color: onVideoFg,
                                          fontSize: AppTypography.xsPlus,
                                          fontWeight: AppTypography.medium,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
