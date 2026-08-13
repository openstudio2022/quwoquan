import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_list_page_semantics.dart';
import 'package:quwoquan_app/design_system/navigation/secondary_tab_bar.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/my_gatherings_provider.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

/// 「我的行动」分组页（REQ-008）：我公开发起的行动按云侧事实三分组。
///
/// 数据只来自 `ListGatheringsByHost` 公开披露读面（audiencePolicy=public 的
/// published/cancelled/completed）；分组由 lifecycleStatus × temporalPhase 派生，
/// 端不推断「等回应/到场」等公开卡不含的事实。读取失败展示结构化错误态 + 重试，
/// 不伪造「暂无行动」空态。
class MyGatheringsPage extends ConsumerStatefulWidget {
  const MyGatheringsPage({super.key, this.segment = ''});

  factory MyGatheringsPage.fromQuery(Map<String, String> query) {
    return MyGatheringsPage(segment: query['segment'] ?? '');
  }

  final String segment;

  @override
  ConsumerState<MyGatheringsPage> createState() => _MyGatheringsPageState();
}

class _MyGatheringsPageState extends ConsumerState<MyGatheringsPage> {
  late MyGatheringsSegment _selected;

  static const List<AppSecondaryTabItem> _segmentTabs = <AppSecondaryTabItem>[
    AppSecondaryTabItem(
      id: 'upcoming',
      label: GatheringText.myGatheringsSegmentUpcoming,
    ),
    AppSecondaryTabItem(
      id: 'draft',
      label: GatheringText.myGatheringsSegmentDraft,
    ),
    AppSecondaryTabItem(
      id: 'ended',
      label: GatheringText.myGatheringsSegmentEnded,
    ),
    AppSecondaryTabItem(
      id: 'cancelled',
      label: GatheringText.myGatheringsSegmentCancelled,
    ),
  ];

  @override
  void initState() {
    super.initState();
    _selected = MyGatheringsSegment.fromQueryValue(widget.segment);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final personaId = ref.watch(currentUserIdProvider);
    final page = ref.watch(myGatheringsProvider(personaId));
    return AppListPageScaffold(
      isDark: isDark,
      kind: AppListPageKind.multiOptionList,
      middle: Text(GatheringText.myGatheringsTitle),
      backgroundColor: AppColors.iosIntersectionTimelineBackground(context),
      onBack: () => context.pop(),
      body: page.when(
        loading: () => Center(child: AppRequestFeedback.section()),
        error: (error, _) => _buildErrorState(context, personaId, error),
        data: (data) => _buildBody(context, data, isDark),
      ),
    );
  }

  Widget _buildErrorState(
    BuildContext context,
    String personaId,
    Object error,
  ) {
    final semantic = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    return ListView(
      padding: EdgeInsets.all(
        SettingsSemanticConstants.insetFormListHorizontalPadding,
      ),
      children: <Widget>[
        AppPageErrorState(
          semantic: semantic,
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              ref.invalidate(myGatheringsProvider(personaId));
              return UiRecoveryOutcome.recovered;
            }
            return UiRecoveryOutcome.cancelled;
          },
        ),
      ],
    );
  }

  Widget _buildBody(
    BuildContext context,
    GatheringHostCardPage data,
    bool isDark,
  ) {
    if (data.items.isEmpty) {
      return ListView(
        padding: EdgeInsets.all(
          SettingsSemanticConstants.insetFormListHorizontalPadding,
        ),
        children: const <Widget>[
          AppEmptyState(
            icon: CupertinoIcons.calendar,
            title: GatheringText.myGatheringsEmptyTitle,
            subtitle: GatheringText.myGatheringsEmptyDescription,
          ),
        ],
      );
    }
    final visible = data.items
        .where((card) => myGatheringsSegmentOf(card) == _selected)
        .toList(growable: false);
    return ListView(
      padding: EdgeInsets.fromLTRB(
        SettingsSemanticConstants.insetFormListHorizontalPadding,
        AppSpacing.containerSm,
        SettingsSemanticConstants.insetFormListHorizontalPadding,
        AppSpacing.containerLg,
      ),
      children: <Widget>[
        AppSecondaryTabBar(
          tabs: _segmentTabs,
          selectedId: _selected.wireValue,
          isDark: isDark,
          onSelected: (value) {
            final segment = MyGatheringsSegment.fromQueryValue(value);
            if (segment == _selected) return;
            setState(() => _selected = segment);
          },
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        if (visible.isEmpty)
          Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.xl),
            child: Center(
              child: Text(
                GatheringText.myGatheringsSegmentEmpty,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  color: AppColors.iosSecondaryLabel(context),
                ),
              ),
            ),
          )
        else
          _GatheringCardGroup(cards: visible),
      ],
    );
  }
}

class _GatheringCardGroup extends StatelessWidget {
  const _GatheringCardGroup({required this.cards});

  final List<GatheringHostCardSummary> cards;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.10),
          width: AppSpacing.hairline,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: <Widget>[
          for (var index = 0; index < cards.length; index++) ...<Widget>[
            _GatheringCardRow(card: cards[index]),
            if (index < cards.length - 1)
              Padding(
                padding: EdgeInsets.only(left: AppSpacing.forty),
                child: Container(
                  height: AppSpacing.hairline,
                  color: AppColors.iosSeparator(
                    context,
                  ).withValues(alpha: 0.30),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _GatheringCardRow extends StatelessWidget {
  const _GatheringCardRow({required this.card});

  final GatheringHostCardSummary card;

  @override
  Widget build(BuildContext context) {
    final secondary = AppColors.iosSecondaryLabel(context);
    final dateLabel = (card.dateLabel ?? '').trim();
    final showSeats =
        myGatheringsSegmentOf(card) == MyGatheringsSegment.upcoming;
    final seatLabel = card.full
        ? GatheringText.sourceGatheringFullLabel
        : GatheringText.sourceGatheringSeatsRemaining(card.remainingSeats);
    return CupertinoButton(
      key: ValueKey<String>('my-gathering-card-${card.gatheringId}'),
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: () =>
          context.push(AppRoutePaths.gatheringDetail(id: card.gatheringId)),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupSm,
        ),
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
                  fontSize: AppTypography.iosSubheadline,
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
            if (showSeats) ...<Widget>[
              SizedBox(width: AppSpacing.intraGroupSm),
              Text(
                seatLabel,
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: secondary,
                ),
              ),
            ],
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }
}
