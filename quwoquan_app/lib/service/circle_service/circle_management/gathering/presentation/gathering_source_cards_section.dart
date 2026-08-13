import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show homepageDetailSocialProofReaderProvider;
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart'
    show gatheringQueryReaderProvider;
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show exceptionTelemetryPortProvider;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

/// 来源对象（实体主页等）「近期行动」L0 氛围层区块。
///
/// 牵线搭桥 UX：融在页面里、一行标题 + 至多 [maxCards] 条公开行动卡，
/// 用户不看不损失任何功能。独立加载独立降级——加载中/为空/读取失败均
/// 整块不渲染、不占位、不伪造（发起入口由动作栏「在这里发起」常驻承担）。
class GatheringSourceCardsSection extends ConsumerStatefulWidget {
  const GatheringSourceCardsSection({
    super.key,
    required this.sourceObjectTypeRef,
    required this.sourceObjectId,
    required this.isDark,
    this.maxCards = 3,
  });

  final String sourceObjectTypeRef;
  final String sourceObjectId;
  final bool isDark;
  final int maxCards;

  @override
  ConsumerState<GatheringSourceCardsSection> createState() =>
      _GatheringSourceCardsSectionState();
}

class _GatheringSourceCardsSectionState
    extends ConsumerState<GatheringSourceCardsSection> {
  List<GatheringSourceCardSummary> _cards =
      const <GatheringSourceCardSummary>[];
  bool _loaded = false;

  // 实体锚点社会证明（成形级诚实计数）：读取失败或零成形不显示，不伪造。
  int _formedCount = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_load());
      unawaited(_loadSocialProof());
    });
  }

  Future<void> _loadSocialProof() async {
    if (widget.sourceObjectTypeRef != 'homepage') {
      return;
    }
    try {
      final proof = await ref
          .read(homepageDetailSocialProofReaderProvider)
          .getGatheringSocialProof(
            anchorKind: 'entity',
            objectId: widget.sourceObjectId,
          );
      if (!mounted) return;
      setState(() => _formedCount = proof.formedCount.toInt());
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'circle.gathering.source_cards_social_proof',
              error: error,
              stackTrace: stackTrace,
            ),
      );
    }
  }

  Future<void> _load() async {
    try {
      final cards = await ref
          .read(gatheringQueryReaderProvider)
          .listBySource(
            GatheringBySourceListQuery(
              sourceObjectTypeRef: widget.sourceObjectTypeRef,
              sourceObjectId: widget.sourceObjectId,
              limit: widget.maxCards,
            ),
          );
      if (!mounted) {
        return;
      }
      setState(() {
        // L0 区块只展示可加入语义明确的发布态行动；诚实不补造。
        _cards = cards
            .where((card) => card.lifecycleStatusWire == 'published')
            .take(widget.maxCards)
            .toList(growable: false);
        _loaded = true;
      });
    } catch (error, stackTrace) {
      // 氛围层读取失败静默降级（不阻塞主页），进观测通道。
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordHandledException(
              source: 'circle.gathering.source_cards_section',
              error: error,
              stackTrace: stackTrace,
            ),
      );
      if (!mounted) {
        return;
      }
      setState(() => _loaded = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded || _cards.isEmpty) {
      return const SizedBox.shrink();
    }
    final secondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    return Container(
      key: const ValueKey<String>('gathering-source-cards-section'),
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyFour),
        border: Border.all(
          color: AppColors.iosCardBorder(context),
          width: AppSpacing.hairline,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  GatheringText.sourceRecentGatheringsTitle,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.iosLabel(context),
                  ),
                ),
              ),
              if (_formedCount > 0)
                Text(
                  GatheringText.sourceFormedCountLabel(_formedCount),
                  key: const ValueKey<String>(
                    'gathering-source-formed-count',
                  ),
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: secondary,
                  ),
                ),
            ],
          ),
          for (final card in _cards) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            _buildCardRow(context, card, secondary),
          ],
        ],
      ),
    );
  }

  Widget _buildCardRow(
    BuildContext context,
    GatheringSourceCardSummary card,
    Color secondary,
  ) {
    final seatLabel = card.full
        ? GatheringText.sourceGatheringFullLabel
        : GatheringText.sourceGatheringSeatsRemaining(card.remainingSeats);
    final dateLabel = (card.dateLabel ?? '').trim();
    return CupertinoButton(
      key: ValueKey<String>('gathering-source-card-${card.gatheringId}'),
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: () =>
          context.push(AppRoutePaths.gatheringDetail(id: card.gatheringId)),
      child: Row(
        children: <Widget>[
          Icon(
            CupertinoIcons.calendar,
            size: AppSpacing.iconSmall,
            color: AppColors.iosAccent(context),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              card.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: AppColors.iosLabel(context),
              ),
            ),
          ),
          if (dateLabel.isNotEmpty) ...<Widget>[
            SizedBox(width: AppSpacing.intraGroupSm),
            Text(
              dateLabel,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: secondary,
              ),
            ),
          ],
          SizedBox(width: AppSpacing.intraGroupSm),
          Text(
            seatLabel,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: secondary,
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.iconSmall,
            color: secondary,
          ),
        ],
      ),
    );
  }
}
