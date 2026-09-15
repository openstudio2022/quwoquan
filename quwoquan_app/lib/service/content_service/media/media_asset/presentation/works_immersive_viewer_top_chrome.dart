part of 'works_immersive_viewer.dart';

@immutable
class _WorksTopChromeTheme {
  const _WorksTopChromeTheme({
    required this.overlayStyle,
    required this.foregroundColor,
    required this.mutedForegroundColor,
  });

  final SystemUiOverlayStyle overlayStyle;
  final Color foregroundColor;
  final Color mutedForegroundColor;
}

/// Work Browser 顶部栏：极简，仅「返回」与「更多」。
/// 禁止媒体类型指示、页码、形态 tab；媒体筛选入口收敛到「更多」菜单。
/// 顶栏空白区保留横滑手势用于宿主一级 tab 切换（首页嵌入态）。
class _WorksPrimaryTopBar extends StatelessWidget {
  const _WorksPrimaryTopBar({
    required this.layoutSpec,
    required this.onHorizontalDragEnd,
    required this.foregroundColor,
    this.onTapClose,
    this.onTapMore,
    this.title = '',
    this.landscape = false,
    this.landscapeGeometry,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final GestureDragEndCallback onHorizontalDragEnd;
  final Color foregroundColor;
  final VoidCallback? onTapClose;
  final VoidCallback? onTapMore;
  final String title;
  final bool landscape;
  final ImmersiveLandscapeGeometry? landscapeGeometry;

  @override
  Widget build(BuildContext context) {
    final geometry = landscapeGeometry;
    if (landscape && geometry != null) {
      return SizedBox(
        key: const ValueKey<String>('works-top-rail'),
        width: double.infinity,
        height: AppSpacing.appChromeTopBarHeight(context),
        child: Stack(
          children: [
            Positioned(
              left: geometry.leftControlSlot.left,
              width: geometry.leftControlSlot.width,
              top: 0,
              bottom: 0,
              child: Center(
                child: Semantics(
                  key: const ValueKey<String>('works-top-back'),
                  identifier: 'works-top-back',
                  child: ImmersiveToolbarIconButton(
                    key: const ValueKey('works-media-landscape-exit'),
                    icon: CupertinoIcons.back,
                    onPressed: onTapClose,
                    foregroundColor: foregroundColor,
                  ),
                ),
              ),
            ),
            if (title.isNotEmpty && !geometry.visibleMediaRect.isEmpty)
              Positioned(
                left: geometry.visibleMediaRect.left,
                width: geometry.visibleMediaRect.width,
                top: 0,
                bottom: 0,
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    title,
                    key: const ValueKey('works-landscape-title'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.base,
                    ),
                  ),
                ),
              ),
            Positioned(
              left: geometry.rightControlSlot.left,
              width: geometry.rightControlSlot.width,
              top: 0,
              bottom: 0,
              child: Center(
                child: KeyedSubtree(
                  key: const ValueKey<String>('works-top-more'),
                  child: ImmersiveToolbarIconButton(
                    icon: CupertinoIcons.ellipsis,
                    onPressed: onTapMore,
                    foregroundColor: foregroundColor,
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }
    return ImmersiveViewerLayout.alignToRail(
      context: context,
      layoutSpec: layoutSpec,
      child: SizedBox(
        key: const ValueKey<String>('works-top-rail'),
        width: double.infinity,
        height: AppSpacing.appChromeTopBarHeight(context),
        child: Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onHorizontalDragEnd: onHorizontalDragEnd,
                child: const SizedBox.expand(),
              ),
            ),
            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: Opacity(
                  opacity: onTapClose == null ? 0 : 1,
                  child: Semantics(
                    key: const ValueKey<String>('works-top-back'),
                    identifier: 'works-top-back',
                    child: ImmersiveToolbarIconButton(
                      icon: CupertinoIcons.back,
                      onPressed: onTapClose,
                      foregroundColor: foregroundColor,
                    ),
                  ),
                ),
              ),
            ),
            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: KeyedSubtree(
                  key: const ValueKey<String>('works-top-more'),
                  child: ImmersiveToolbarIconButton(
                    icon: CupertinoIcons.ellipsis,
                    onPressed: onTapMore,
                    foregroundColor: foregroundColor,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
