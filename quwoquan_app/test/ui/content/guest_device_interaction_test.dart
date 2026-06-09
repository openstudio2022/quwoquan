import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';

/// 游客（未登录）会话桩：isAuthenticated=false，但带稳定 installId。
class _GuestAuthStore implements AuthSessionStore {
  @override
  Future<StoredAuthSession> read() async {
    return const StoredAuthSession(
      accessToken: '',
      refreshToken: '',
      ownerId: '',
      activeSubAccountId: '',
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
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
  }) async {}
  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}
  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}
  @override
  Future<void> clearSession({required bool manualLogout}) async {}
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
    tearDown(() => AppTraceContextStore.instance.deviceActorId = null);

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

      syncPostLikeIntent(ref, postId: 'post_x', isLiked: true, likeCount: 10);
      await tester.pump();

      expect(ref.read(postInteractionStateProvider).isLiked('post_x'), isTrue);
      await tester.pumpAndSettle();
    });

    testWidgets('游客收藏被拦截：不写乐观态（收藏仍需登录）', (tester) async {
      final ref = await pumpRef(tester);
      syncPostSaveIntent(
        ref,
        postId: 'post_y',
        isSaved: true,
        bookmarkCount: 5,
      );
      await tester.pump();

      expect(
        ref.read(postInteractionStateProvider).isSaved('post_y'),
        isFalse,
        reason: '收藏属个人资产，游客不得写入',
      );
      await tester.pumpAndSettle();
    });
  });
}
