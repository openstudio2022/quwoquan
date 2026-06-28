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

/// 线下局页（全屏聚焦版）。
///
/// 从同频连接中心「局」通道深入。展示可报名的同城聚会；报名/发起局复用建群页
/// 形成局群（[dispatchConnectionAction] 路由到 `start_group_chat`）。
class OfflineMeetupPage extends ConsumerStatefulWidget {
  const OfflineMeetupPage({super.key});

  static const Key viewKey = ValueKey<String>('offline-meetup-page');

  @override
  ConsumerState<OfflineMeetupPage> createState() => _OfflineMeetupPageState();
}

class _OfflineMeetupPageState extends ConsumerState<OfflineMeetupPage> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref
          .read(visitRecorderServiceProvider)
          .recordVisit(const VisitTarget.page('plaza_meetup_page'));
    });
  }

  void _onAction(ConnectionActionHint action) {
    unawaited(
      dispatchConnectionAction(context, ref, action, source: 'plaza_meetup'),
    );
  }

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      key: OfflineMeetupPage.viewKey,
      backgroundColor: AppColors.iosGroupedSurface(context),
      navigationBar: CupertinoNavigationBar(
        middle: Text(PlazaTextConstants.meetupPageTitle),
      ),
      child: SafeArea(
        child: ConnectionListSection<OfflineMeetup>(
          async: ref.watch(offlineMeetupsProvider),
          emptyTitle: PlazaTextConstants.emptyMeetupTitle,
          emptySubtitle: PlazaTextConstants.emptyMeetupSubtitle,
          emptyIcon: CupertinoIcons.person_3,
          onRetry: () => ref.invalidate(offlineMeetupsProvider),
          itemBuilder: (_, meetup) =>
              OfflineMeetupCard(meetup: meetup, onAction: _onAction),
        ),
      ),
    );
  }
}
