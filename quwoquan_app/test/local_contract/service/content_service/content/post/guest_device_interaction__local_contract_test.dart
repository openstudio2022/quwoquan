import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_client_context_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_state_bridge.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 游客（未登录）会话桩：isAuthenticated=false，但带稳定 installId。
class _GuestAuthStore implements AuthSessionStore {
  @override
  Future<StoredAuthSession> read() async {
    return const StoredAuthSession(
      accessToken: '',
      refreshToken: '',
      ownerId: '',
      activePersonaId: '',
      accountState: '',
      identityOrigin: '',
      installId: 'install-guest-001',
      lastRefreshAtEpochMs: 0,
      lastForegroundAuthCheckAtEpochMs: 0,
      manualLoggedOut: false,
      launchPromptDismissed: true,
    );
  }

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActivePersona(String personaId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

void main() {
  group('deriveDeviceActorId', () {
    test('稳定、32 位 hex、非空，且按 installId 区分', () {
      final a1 = deriveDeviceActorId('install-guest-001');
      final a2 = deriveDeviceActorId('install-guest-001');
      final b = deriveDeviceActorId('install-other-002');
      expect(a1, isNotEmpty);
      expect(a1.length, 32);
      expect(RegExp(r'^[0-9a-f]{32}$').hasMatch(a1), isTrue);
      expect(a1, a2, reason: '同一 installId 必须可复算');
      expect(a1, isNot(b), reason: '不同 installId 必须区分');
    });

    test('冻结 canonical salt 字节，既有安装身份不可漂移', () {
      expect(
        deriveDeviceActorId('install-guest-001'),
        'fe1e74ae2d13dba372708a85bdaac910',
      );
    });

    test('原始 installId 不出现在派生结果中（隐私安全）', () {
      const installId = 'install-guest-001';
      expect(deriveDeviceActorId(installId).contains(installId), isFalse);
    });

    test('空 installId 派生为空', () {
      expect(deriveDeviceActorId(''), isEmpty);
      expect(deriveDeviceActorId('   '), isEmpty);
    });
  });

  group('CloudRequestHeaders 设备头注入', () {
    setUp(() {
      CloudClientContextRegistry.configure(
        const AppCloudClientContextProvider(),
      );
    });
    tearDown(() {
      AppTraceContextStore.instance.deviceActorId = null;
      CloudClientContextRegistry.configure(
        const FallbackCloudClientContextProvider(),
      );
    });

    test('设置 deviceActorId 后注入 X-Client-Device-Actor-Id', () {
      AppTraceContextStore.instance.deviceActorId = 'devactor123';
      final page = CloudRequestHeaders.forPage('test.page');
      expect(page['X-Client-Device-Actor-Id'], 'devactor123');
      final surface = CloudRequestHeaders.forSurfaceOperation(
        surfaceId: 's',
        operationId: 'o',
        clientPageId: 'p',
      );
      expect(surface['X-Client-Device-Actor-Id'], 'devactor123');
    });

    test('未设置 deviceActorId 时不注入设备头', () {
      AppTraceContextStore.instance.deviceActorId = null;
      final page = CloudRequestHeaders.forPage('test.page');
      expect(page.containsKey('X-Client-Device-Actor-Id'), isFalse);
    });
  });

  group('游客互动（设备态）', () {
    Future<WidgetRef> pumpRef(WidgetTester tester) async {
      late WidgetRef captured;
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            authSessionStoreProvider.overrideWithValue(_GuestAuthStore()),
          ],
          child: Consumer(
            builder: (context, ref, _) {
              captured = ref;
              ref.watch(authSessionControllerProvider);
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 50));
      return captured;
    }

    testWidgets('游客点赞写入乐观态（设备态可写）', (tester) async {
      final ref = await pumpRef(tester);
      expect(
        ref.read(authSessionControllerProvider).isAuthenticated,
        isFalse,
        reason: '前置：当前为游客态',
      );

      syncPostLikeIntent(
        ref,
        postId: 'post_x',
        previousLiked: false,
        isLiked: true,
        likeCount: 10,
      );
      await tester.pump();

      expect(ref.read(postInteractionStateProvider).isLiked('post_x'), isTrue);
      await tester.pumpAndSettle();
    });
  });
}
