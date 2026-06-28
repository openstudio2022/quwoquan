import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/plaza/providers/connection_providers.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_action_dispatch.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_cards.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_list_section.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_state_views.dart';

/// 同频连接中心（同频/广场一级 tab body）。
///
/// 在 [MainAppShell] 的 IndexedStack 中作为「同频」频道渲染，游客可浏览、无登录门。
/// 承载四条连接通道：同趣（兴趣）/ 同行（结伴）/ 附近（模糊位置）/ 局（线下）。
/// 每个通道复用 [ConnectionListSection] 的四态（加载骨架 / 空引导 / 错重试 / 权限），
/// 数据经 plaza Provider → `appDataSourceModeProvider` 透明切换 Mock/Remote。
/// 曝光埋点：tab 切换记录 `plaza_<channel>` 访问（复用 [VisitTarget]）。
class ConnectionHubPage extends ConsumerStatefulWidget {
  const ConnectionHubPage({super.key});

  static const Key viewKey = ValueKey<String>('connection-hub-page');
  static const Key segmentKey = ValueKey<String>('connection-hub-segment');

  @override
  ConsumerState<ConnectionHubPage> createState() => _ConnectionHubPageState();
}

class _ConnectionHubPageState extends ConsumerState<ConnectionHubPage> {
  static const int _tabAffinity = 0;
  static const int _tabCompanion = 1;
  static const int _tabNearby = 2;
  static const int _tabMeetup = 3;

  static const List<String> _channelIds = <String>[
    'affinity',
    'companion',
    'nearby',
    'meetup',
  ];

  int _activeTab = _tabAffinity;

  /// 附近通道的定位授权态（原型本地模拟，端云授权与 LBS 后端挂 backlog）。
  bool _nearbyLocationGranted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _recordVisit(_activeTab);
    });
  }

  void _recordVisit(int tab) {
    ref
        .read(visitRecorderServiceProvider)
        .recordVisit(VisitTarget.page('plaza_${_channelIds[tab]}'));
  }

  void _onTabChanged(int? value) {
    if (value == null || value == _activeTab) {
      return;
    }
    setState(() => _activeTab = value);
    _recordVisit(value);
  }

  void _onPeerAction(
    PeerConnection peer,
    String source,
    ConnectionActionHint action,
  ) {
    unawaited(
      dispatchConnectionAction(
        context,
        ref,
        action,
        targetSubAccountId: peer.id,
        source: source,
      ),
    );
  }

  void _onGroupAction(String source, ConnectionActionHint action) {
    unawaited(
      dispatchConnectionAction(context, ref, action, source: source),
    );
  }

  Widget _seeAllHeader(String routePath) {
    final accent = AppColors.iosAccent(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => context.push(routePath),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: <Widget>[
          Text(
            PlazaTextConstants.seeAllLabel,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              fontWeight: AppTypography.medium,
              color: accent,
            ),
          ),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.fourteen,
            color: accent,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      key: ConnectionHubPage.viewKey,
      backgroundColor: AppColors.iosGroupedSurface(context),
      child: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _buildHeader(context),
            _buildSummaryBar(context),
            Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              child: SizedBox(
                width: double.infinity,
                child: CupertinoSlidingSegmentedControl<int>(
                  key: ConnectionHubPage.segmentKey,
                  groupValue: _activeTab,
                  onValueChanged: _onTabChanged,
                  children: const <int, Widget>{
                    _tabAffinity: _SegmentLabel(PlazaTextConstants.tabAffinity),
                    _tabCompanion: _SegmentLabel(
                      PlazaTextConstants.tabCompanion,
                    ),
                    _tabNearby: _SegmentLabel(PlazaTextConstants.tabNearby),
                    _tabMeetup: _SegmentLabel(PlazaTextConstants.tabMeetup),
                  },
                ),
              ),
            ),
            Expanded(child: _buildTabBody(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.xs,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            AppConceptConstants.plazaTitle,
            style: TextStyle(
              fontSize: AppTypography.iosTitle2,
              fontWeight: AppTypography.bold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            AppConceptConstants.plazaSubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryBar(BuildContext context) {
    final summary = ref.watch(connectionHubSummaryProvider);
    return summary.maybeWhen(
      data: (s) {
        final color = AppColors.iosSecondaryLabel(context);
        final items = <String>[
          '${PlazaTextConstants.tabAffinity} ${s.affinityCount}',
          '${PlazaTextConstants.tabCompanion} ${s.companionCount}',
          '${PlazaTextConstants.tabNearby} ${s.nearbyCount}',
          '${PlazaTextConstants.tabMeetup} ${s.meetupCount}',
        ];
        return Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
          child: Row(
            children: <Widget>[
              for (var i = 0; i < items.length; i++) ...<Widget>[
                if (i > 0)
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                    child: Text('·', style: TextStyle(color: color)),
                  ),
                Text(
                  items[i],
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: color,
                  ),
                ),
              ],
            ],
          ),
        );
      },
      orElse: () => const SizedBox.shrink(),
    );
  }

  Widget _buildTabBody(BuildContext context) {
    switch (_activeTab) {
      case _tabCompanion:
        return ConnectionListSection<CompanionTrip>(
          async: ref.watch(companionTripsProvider),
          emptyTitle: PlazaTextConstants.emptyCompanionTitle,
          emptySubtitle: PlazaTextConstants.emptyCompanionSubtitle,
          emptyIcon: CupertinoIcons.map,
          onRetry: () => ref.invalidate(companionTripsProvider),
          header: _seeAllHeader(AppRoutePaths.plazaCompanion),
          itemBuilder: (_, trip) => CompanionTripCard(
            trip: trip,
            onAction: (action) => _onGroupAction('plaza_companion', action),
          ),
        );
      case _tabNearby:
        if (!_nearbyLocationGranted) {
          return ConnectionPermissionView(
            onGrant: () => setState(() => _nearbyLocationGranted = true),
          );
        }
        return ConnectionListSection<PeerConnection>(
          async: ref.watch(nearbyPeersProvider),
          emptyTitle: PlazaTextConstants.emptyNearbyTitle,
          emptySubtitle: PlazaTextConstants.emptyNearbySubtitle,
          emptyIcon: CupertinoIcons.location,
          onRetry: () => ref.invalidate(nearbyPeersProvider),
          header: _seeAllHeader(AppRoutePaths.plazaNearby),
          itemBuilder: (_, peer) => PeerConnectionCard(
            peer: peer,
            onAction: (action) => _onPeerAction(peer, 'plaza_nearby', action),
          ),
        );
      case _tabMeetup:
        return ConnectionListSection<OfflineMeetup>(
          async: ref.watch(offlineMeetupsProvider),
          emptyTitle: PlazaTextConstants.emptyMeetupTitle,
          emptySubtitle: PlazaTextConstants.emptyMeetupSubtitle,
          emptyIcon: CupertinoIcons.person_3,
          onRetry: () => ref.invalidate(offlineMeetupsProvider),
          header: _seeAllHeader(AppRoutePaths.plazaMeetup),
          itemBuilder: (_, meetup) => OfflineMeetupCard(
            meetup: meetup,
            onAction: (action) => _onGroupAction('plaza_meetup', action),
          ),
        );
      case _tabAffinity:
      default:
        return ConnectionListSection<PeerConnection>(
          async: ref.watch(affinityPeersProvider),
          emptyTitle: PlazaTextConstants.emptyAffinityTitle,
          emptySubtitle: PlazaTextConstants.emptyAffinitySubtitle,
          emptyIcon: CupertinoIcons.sparkles,
          onRetry: () => ref.invalidate(affinityPeersProvider),
          itemBuilder: (_, peer) => PeerConnectionCard(
            peer: peer,
            onAction: (action) => _onPeerAction(peer, 'plaza_affinity', action),
          ),
        );
    }
  }
}

class _SegmentLabel extends StatelessWidget {
  const _SegmentLabel(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
      child: Text(label, style: const TextStyle(fontSize: AppTypography.iosFootnote)),
    );
  }
}
