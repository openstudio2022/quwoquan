import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/core/constants/plaza_text_constants.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/plaza/providers/connection_providers.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_action_dispatch.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_cards.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_list_section.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_state_views.dart';

/// 附近同趣页（全屏聚焦版）。
///
/// 从同频连接中心「附近」通道、或实体页「附近也想去」深入。展示模糊位置态：
/// 默认未授权定位 → [ConnectionPermissionView] 引导；授权后展示同趣的人，
/// 仅显示模糊距离（不暴露精确位置），陌生人破冰走双向同意请求箱。
class NearbyAffinityPage extends ConsumerStatefulWidget {
  const NearbyAffinityPage({super.key});

  static const Key viewKey = ValueKey<String>('nearby-affinity-page');

  @override
  ConsumerState<NearbyAffinityPage> createState() => _NearbyAffinityPageState();
}

class _NearbyAffinityPageState extends ConsumerState<NearbyAffinityPage> {
  bool _locationGranted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref
          .read(visitRecorderServiceProvider)
          .recordVisit(const VisitTarget.page('plaza_nearby_page'));
    });
  }

  void _onAction(PeerConnection peer, ConnectionActionHint action) {
    unawaited(
      dispatchConnectionAction(
        context,
        ref,
        action,
        targetSubAccountId: peer.id,
        source: 'plaza_nearby',
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      key: NearbyAffinityPage.viewKey,
      backgroundColor: AppColors.iosGroupedSurface(context),
      navigationBar: CupertinoNavigationBar(
        middle: Text(PlazaTextConstants.nearbyPageTitle),
      ),
      child: SafeArea(
        child: _locationGranted
            ? ConnectionListSection<PeerConnection>(
                async: ref.watch(nearbyPeersProvider),
                emptyTitle: PlazaTextConstants.emptyNearbyTitle,
                emptySubtitle: PlazaTextConstants.emptyNearbySubtitle,
                emptyIcon: CupertinoIcons.location,
                onRetry: () => ref.invalidate(nearbyPeersProvider),
                header: const _FuzzyLocationBanner(),
                itemBuilder: (_, peer) =>
                    PeerConnectionCard(peer: peer, onAction: (a) => _onAction(peer, a)),
              )
            : ConnectionPermissionView(
                onGrant: () => setState(() => _locationGranted = true),
              ),
      ),
    );
  }
}

class _FuzzyLocationBanner extends StatelessWidget {
  const _FuzzyLocationBanner();

  @override
  Widget build(BuildContext context) {
    final color = AppColors.iosSecondaryLabel(context);
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        children: <Widget>[
          Icon(
            CupertinoIcons.location_circle,
            size: AppSpacing.fourteen,
            color: color,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              PlazaTextConstants.permissionSubtitle,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: color,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
