part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerProvenance on _WorksImmersiveViewerState {
  /// 经历溯源轻标：回顾内容（wire gatheringRef）→「来自一次共同行动」；
  /// 种草内容（content 锚点成形级 > 0）→「他们从这条内容出发，一起去了」。
  /// 两者都不成立时返回空占位，不伪造。
  Widget _buildProvenanceBadgeLayer(
    BuildContext context,
    ContentPostViewData currentPost,
    ImmersiveViewerStageLayoutSpec layoutSpec,
  ) {
    final recapRef = _recapGatheringRefFor(currentPost);
    String label;
    VoidCallback onTap;
    if (recapRef.isNotEmpty) {
      label = GatheringText.provenanceRecapBadge;
      onTap = () => _openRecapProvenance(recapRef);
    } else {
      _ensureSeedProvenanceLoaded(currentPost);
      if (_seedProvenanceByPostId[currentPost.id] != true) {
        return const SizedBox.shrink();
      }
      label = GatheringText.provenanceSeedBadge;
      onTap = () => _openSeedProvenance(currentPost);
    }
    return Positioned(
      left: 0,
      right: 0,
      bottom: WorksImmersiveContentLayout.intersectionBottomClearance(context),
      child: ImmersiveViewerLayout.alignToRail(
        context: context,
        layoutSpec: layoutSpec,
        child: Align(
          alignment: Alignment.centerLeft,
          child: Semantics(
            button: true,
            label: label,
            child: GestureDetector(
              key: const ValueKey<String>('works-provenance-badge'),
              behavior: HitTestBehavior.opaque,
              onTap: onTap,
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.intraGroupXs,
                ),
                decoration: BoxDecoration(
                  color: AppColors.worksBackground.withValues(alpha: 0.72),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(
                      CupertinoIcons.person_2,
                      size: AppTypography.sm,
                      color: AppColors.worksAccent,
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: AppColors.worksBodyText,
                        fontSize: AppTypography.sm,
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
