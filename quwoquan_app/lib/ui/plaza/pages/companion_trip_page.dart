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

/// 结伴出发页（全屏聚焦版）。
///
/// 从同频连接中心「同行」通道、或实体页「想去/正在去/结伴」模块深入。
/// 围绕目的地实体沉淀「想去 / 正在去 / 结伴」的人；发起/加入结伴复用建群页
/// 形成同行群（[dispatchConnectionAction] 路由到 `start_group_chat`）。
class CompanionTripPage extends ConsumerStatefulWidget {
  const CompanionTripPage({super.key});

  static const Key viewKey = ValueKey<String>('companion-trip-page');

  @override
  ConsumerState<CompanionTripPage> createState() => _CompanionTripPageState();
}

class _CompanionTripPageState extends ConsumerState<CompanionTripPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref
          .read(visitRecorderServiceProvider)
          .recordVisit(const VisitTarget.page('plaza_companion_page'));
    });
  }

  void _onAction(ConnectionActionHint action) {
    unawaited(
      dispatchConnectionAction(context, ref, action, source: 'plaza_companion'),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      key: CompanionTripPage.viewKey,
      backgroundColor: AppColors.iosGroupedSurface(context),
      navigationBar: CupertinoNavigationBar(
        middle: Text(PlazaTextConstants.companionPageTitle),
      ),
      child: SafeArea(
        child: ConnectionListSection<CompanionTrip>(
          async: ref.watch(companionTripsProvider),
          emptyTitle: PlazaTextConstants.emptyCompanionTitle,
          emptySubtitle: PlazaTextConstants.emptyCompanionSubtitle,
          emptyIcon: CupertinoIcons.map,
          onRetry: () => ref.invalidate(companionTripsProvider),
          itemBuilder: (_, trip) =>
              CompanionTripCard(trip: trip, onAction: _onAction),
        ),
      ),
    );
  }
}
