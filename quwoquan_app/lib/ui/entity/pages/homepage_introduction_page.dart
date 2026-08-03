import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/core/models/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_tab.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_type_labels.dart';
import 'package:quwoquan_app/ui/entity/providers/homepage_introduction_provider.dart';
import 'package:url_launcher/url_launcher.dart';

part 'homepage_introduction_page_content.dart';
part 'homepage_introduction_page_related.dart';

const double _introHeroHeight = AppSpacing.twoHundredTwenty;
const double _introTimelineDateWidth =
    AppSpacing.homepageIntroductionTimelineDateWidth;
const double _introAssetStripHeight = AppSpacing.commentComposerMaxHeight;
const double _introHorizontalCardWidth =
    AppSpacing.homepageIntroductionHorizontalCardWidth;
const double _introRelatedObjectHeight = AppSpacing.homeObjectCardRailHeight;

/// 正文块级内嵌图（三段结构 role=inline）统一横图比例。
const double _introInlineFigureAspectRatio =
    AppSpacing.homepageIntroductionInlineFigureAspectRatio;

class HomepageIntroductionPage extends ConsumerStatefulWidget {
  const HomepageIntroductionPage({
    super.key,
    required this.homepageId,
    this.referralSource = ReferralSource.entityPage,
  });

  final String homepageId;
  final ReferralSource referralSource;

  @override
  ConsumerState<HomepageIntroductionPage> createState() =>
      _HomepageIntroductionPageState();
}

class _HomepageIntroductionPageState
    extends ConsumerState<HomepageIntroductionPage> {
  final ScrollController _scrollController = ScrollController();
  final DateTime _enteredAt = DateTime.now();
  double _maxDepth = 0;
  late final JourneyEventTracker _journeyTracker;

  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _scrollController.addListener(_trackDepth);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackJourney('enter', payload: _basePayload());
    });
  }

  @override
  void dispose() {
    _scrollController.removeListener(_trackDepth);
    _trackJourney(
      'exit',
      payload: <String, Object?>{
        ..._basePayload(),
        'durationMs': DateTime.now().difference(_enteredAt).inMilliseconds,
        'maxDepth': _maxDepth,
      },
    );
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final asyncValue = ref.watch(
      homepageIntroductionProvider(widget.homepageId),
    );
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      navigationBar: CupertinoNavigationBar(
        middle: const Text(ObjectHomepageText.objectIntroNavigationTitle),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.homepageDetail(id: widget.homepageId));
            }
          },
          child: const Icon(CupertinoIcons.chevron_back),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: asyncValue.when(
          loading: () => AppRequestFeedback.section(),
          error: (error, _) => AppPageErrorState(
            semantic: runtimeErrorSemantic(
              context,
              error: error,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
            ),
            onAction: (action) {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                ref.invalidate(homepageIntroductionProvider(widget.homepageId));
              }
              return Future<void>.value();
            },
          ),
          data: (introduction) {
            if (introduction == null ||
                introduction.summary.trim().isEmpty ||
                introduction.sections.isEmpty) {
              return _IntroductionEmptyState(
                onBack: () {
                  context.go(
                    AppRoutePaths.homepageDetail(id: widget.homepageId),
                  );
                },
              );
            }
            return _buildContent(context, introduction);
          },
        ),
      ),
    );
  }

  Widget _buildContent(
    BuildContext context,
    HomepageIntroduction introduction,
  ) {
    final title = introduction.displayName.trim().isEmpty
        ? widget.homepageId
        : introduction.displayName.trim();
    return ListView(
      controller: _scrollController,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        AppSpacing.containerXl,
      ),
      children: <Widget>[
        _IntroductionHero(introduction: introduction),
        SizedBox(height: AppSpacing.containerSm),
        _IntroductionCard(
          child: Text(
            introduction.summary,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              height: AppTypography.lineHeightRelaxed,
              color: AppColors.iosLabel(context),
            ),
          ),
        ),
        for (final section in introduction.sections) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _IntroductionSectionCard(section: section),
        ],
        if (introduction.relatedObjects.isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _RelatedObjectsSection(
            items: introduction.relatedObjects,
            onTap: (item) {
              _trackJourney(
                'related_object_click',
                targetKey: item.linkedHomepageId ?? item.circleId,
                payload: _basePayload(),
              );
              final target = (item.linkedHomepageId ?? '').trim();
              if (target.isNotEmpty) {
                context.push(AppRoutePaths.homepageDetail(id: target));
                return;
              }
              final circleId = item.circleId.trim();
              if (circleId.isNotEmpty) {
                context.push(
                  AppRoutePaths.circleDetail(id: circleId),
                  extra: const CircleDetailPageRouteExtra(
                    referralSource: ReferralSource.entityPage,
                  ),
                );
              }
            },
          ),
        ],
        SizedBox(height: AppSpacing.containerSm),
        _ReturnLinksCard(
          title: title,
          onTap: (target) {
            _trackJourney(
              'return_link_click',
              targetKey: target.name,
              payload: _basePayload(),
            );
            context.go(
              AppRoutePaths.homepageDetail(id: widget.homepageId),
              extra: HomepageDetailPageRouteExtra(initialTabTarget: target),
            );
          },
        ),
        if (introduction.primarySource != null) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _HomepageSourceCard(source: introduction.primarySource!),
        ],
      ],
    );
  }

  void _trackDepth() {
    if (!_scrollController.hasClients) {
      return;
    }
    final maxExtent = _scrollController.position.maxScrollExtent;
    final depth = maxExtent <= 0
        ? 1.0
        : (_scrollController.offset / maxExtent).clamp(0.0, 1.0);
    if (depth > _maxDepth) {
      _maxDepth = depth;
    }
  }

  Map<String, Object?> _basePayload() {
    return <String, Object?>{
      'homepageId': widget.homepageId,
      'referralSource': widget.referralSource.value,
    };
  }

  void _trackJourney(
    String action, {
    String targetKey = '',
    Map<String, Object?> payload = const <String, Object?>{},
  }) {
    unawaited(
      _journeyTracker.trackAction(
        journey: 'homepage_introduction',
        action: action,
        pageName: 'homepage_introduction',
        targetType: targetKey.isEmpty ? '' : 'homepage',
        targetKey: targetKey,
        entityType: 'homepage',
        entityId: widget.homepageId,
        payload: payload,
      ),
    );
  }
}
