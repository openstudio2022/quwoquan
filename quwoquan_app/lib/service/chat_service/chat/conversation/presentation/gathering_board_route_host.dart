import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/gathering_board_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/route_unavailable_state.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/gathering_board_page.dart';

/// Chat-owned composition host for the Gathering board embedded in a
/// conversation.
class GatheringBoardPageRouteHost extends ConsumerWidget {
  const GatheringBoardPageRouteHost({super.key, required this.conversationId});

  final String conversationId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    try {
      if (conversationId.trim().isEmpty) {
        throw StateError('gathering board conversation id is required');
      }
      final query = ref.watch(gatheringBoardQueryProvider);
      Future<void> openGathering(GatheringBoardNavigationTarget target) {
        return context.push<void>(
          AppRoutePaths.gatheringDetail(id: target.gatheringId),
        );
      }

      return GatheringBoardPage(
        conversationId: conversationId,
        query: query,
        onBack: () {
          if (context.canPop()) {
            context.pop();
          } else {
            context.go(AppRoutePaths.chatDetail(id: conversationId));
          }
        },
        navigation: GatheringBoardNavigationCallbacks(
          openAnnouncement: (target) => context.push<void>(
            AppRoutePaths.chatAnnouncement(id: target.conversationId),
          ),
          openPlan: openGathering,
          openMap: openGathering,
          openCalendar: openGathering,
          openMembers: (target) => context.push<void>(
            AppRoutePaths.chatManage(id: target.conversationId),
          ),
        ),
      );
    } catch (error) {
      return RouteUnavailableState(
        error: error,
        surface: AppUiSurfaces.gatheringBoard,
        pageTitle: ChatText.groupCapabilityActivity,
      );
    }
  }
}
