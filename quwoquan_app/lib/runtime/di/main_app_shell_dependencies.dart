import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participants_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_session_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/active_call_bar.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/pip_call_overlay.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/my_profile_page.dart';

class MainAppShellActiveCallRoute {
  const MainAppShellActiveCallRoute({
    required this.callId,
    required this.isVideo,
  });

  final String callId;
  final bool isVideo;
}

/// AppRoot shell 的唯一业务组合 binding。runtime shell 只消费这些无领域类型的
/// builder/action；真实对象 provider 与 presentation 只在 runtime/di 装配。
class MainAppShellBindings {
  const MainAppShellBindings({
    required this.ref,
    required this.activeCallRoute,
  });

  final Ref ref;
  final MainAppShellActiveCallRoute? activeCallRoute;

  Widget buildHome({
    required String routeLocation,
    required bool isStartupHomeActive,
  }) {
    return HomePage(
      routeLocation: routeLocation,
      isStartupHomeActive: isStartupHomeActive,
    );
  }

  Widget buildChat() => const ChatPage();

  Widget buildFeatured({required VoidCallback onExitToHome}) {
    return HomeFeaturedImmersivePage(onExitToHome: onExitToHome);
  }

  Widget buildProfile() => const MyProfilePage();

  Widget buildActiveCallBar({required VoidCallback onTap}) {
    return ActiveCallBar(onTap: onTap);
  }

  Widget buildPipCallOverlay({
    required VoidCallback onReturnToCall,
    required VoidCallback onHangup,
  }) {
    return PipCallOverlay(
      activeSpeaker: ref.read(callParticipantsProvider).activeSpeaker,
      onReturnToCall: onReturnToCall,
      onHangup: onHangup,
    );
  }

  String synchronizeIncomingCall({
    required String boundUserId,
    required String nextUserId,
  }) {
    final decision = resolveIncomingCallSync(
      boundUserId: boundUserId,
      nextUserId: nextUserId,
    );
    if (!decision.shouldStop && !decision.shouldStart) {
      return decision.boundUserId;
    }
    final coordinator = ref.read(incomingCallCoordinatorProvider);
    if (decision.shouldStop) {
      coordinator.stop();
    }
    if (decision.shouldStart) {
      coordinator.start(nextUserId);
    }
    return decision.boundUserId;
  }

  void exitPipMode() {
    ref.read(activeCallProvider.notifier).exitPipMode();
  }

  Future<void> hangupActiveCall() async {
    final result = await ref
        .read(callSessionProvider.notifier)
        .hangupCall(clearActiveCall: false);
    if (result.succeeded) {
      ref.read(activeCallProvider.notifier).endCall();
    }
  }
}

final mainAppShellBindingsProvider = Provider<MainAppShellBindings>((ref) {
  final activeCall = ref.watch(activeCallProvider);
  ref.watch(callParticipantsProvider);
  final callId = activeCall.callId?.trim() ?? '';
  return MainAppShellBindings(
    ref: ref,
    activeCallRoute: callId.isEmpty
        ? null
        : MainAppShellActiveCallRoute(
            callId: callId,
            isVideo: activeCall.callType == 'video',
          ),
  );
});
