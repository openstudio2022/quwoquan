import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

void main() {
  test(
    'fixture delegate enters active and pushes catalog MessageSent',
    () async {
      ensureSqfliteFfiInitialized();
      final container = ProviderContainer(
        overrides: [
          // 读 timeline 会经 chatRepositoryComposition 触达 generated operation
          // client；本用例只验证 fixture delegate 推送，边界必须封死。
          ...sealedCloudBoundaryOverrides(),
          ...chatTestRepositoryOverrides(),
          activePersonaContextLoaderProvider.overrideWithValue(
            () async => ActivePersonaContextViewData.fallback(
              personaId: 'realtime-test-persona',
              ownerUserId: 'realtime-test-owner',
              displayName: '实时连接测试用户',
              avatarUrl: '',
            ),
          ),
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
          _fixtureOverride,
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        realtimeConnectionManagerProvider.notifier,
      );
      notifier.onAppForeground();
      expect(
        container.read(realtimeConnectionManagerProvider),
        TransportState.idle,
      );

      notifier.onEnterConversation('conv_001');
      expect(
        container.read(realtimeConnectionManagerProvider),
        TransportState.active,
      );

      final beforeCount = container
          .read(chatMessageTimelineProvider('conv_001'))
          .messages
          .length;

      await Future<void>.delayed(const Duration(milliseconds: 400));

      final afterMessages = container
          .read(chatMessageTimelineProvider('conv_001'))
          .messages;
      expect(afterMessages.length, greaterThan(beforeCount));
      expect(
        afterMessages.any(
          (message) => message.id == 'fixture_rt_conv_001_msg_13',
        ),
        isTrue,
      );
      expect(
        afterMessages.any(
          (message) =>
              message.content?.contains('Fixture Realtime 新消息：咖啡馆门口见。') ??
              false,
        ),
        isTrue,
      );
    },
  );

  test('fixture delegate switches to idle immediately on leave', () {
    final container = ProviderContainer(
      overrides: [
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        _fixtureOverride,
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(realtimeConnectionManagerProvider.notifier);
    notifier.onAppForeground();
    notifier.onEnterConversation('conv_001');

    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.active,
    );

    notifier.onLeaveConversation();

    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.idle,
    );
  });
}

final _fixtureOverride = realtimeConnectionManagerProvider.overrideWith(
  () => RealtimeConnectionNotifier(
    delegateFactory:
        ({
          required ref,
          required onStateChanged,
          required currentUserIdResolver,
        }) => FixtureRealtimeConnectionDelegate(
          read: ref.read,
          invalidate: ref.invalidate,
          onStateChanged: onStateChanged,
        ),
  ),
);

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'realtime-test-token',
    refreshToken: 'realtime-test-refresh-token',
    ownerId: 'realtime-test-owner',
    activePersonaId: 'realtime-test-persona',
    accountState: 'active',
    installId: 'realtime-test-install',
  );
}
