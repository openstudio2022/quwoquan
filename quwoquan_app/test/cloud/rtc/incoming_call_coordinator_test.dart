import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/app_router.dart';
import 'package:quwoquan_app/cloud/rtc/incoming_call_coordinator.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // 协调器装配：在不同平台能力位下都能解析（不依赖被删除的 goRouterProvider）。
  // ──────────────────────────────────────────────────────────────────
  group('IncomingCallCoordinator — 装配与能力位', () {
    ProviderContainer makeContainer(PlatformCapabilities caps) {
      return ProviderContainer(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(caps),
          appRouterProvider.overrideWithValue(
            GoRouter(
              routes: [
                GoRoute(
                  path: '/',
                  builder: (context, state) => const _Empty(),
                ),
              ],
            ),
          ),
        ],
      );
    }

    test('mobile 能力位下可解析协调器', () {
      final container = makeContainer(CapabilityProfile.mobile);
      addTearDown(container.dispose);
      expect(
        container.read(incomingCallCoordinatorProvider),
        isA<IncomingCallCoordinator>(),
      );
    });

    test('web 能力位下可解析协调器', () {
      final container = makeContainer(CapabilityProfile.web);
      addTearDown(container.dispose);
      expect(
        container.read(incomingCallCoordinatorProvider),
        isA<IncomingCallCoordinator>(),
      );
    });

    test('ohos（无 RTC）能力位下可解析协调器（来电通道 unsupported）', () {
      final container = makeContainer(CapabilityProfile.ohos);
      addTearDown(container.dispose);
      final caps = container.read(platformCapabilitiesProvider);
      expect(
        resolveIncomingCallChannel(caps),
        IncomingCallChannel.unsupported,
      );
      expect(
        container.read(incomingCallCoordinatorProvider),
        isA<IncomingCallCoordinator>(),
      );
    });
  });

  // ──────────────────────────────────────────────────────────────────
  // 登录态唯一启停（与 shell 同源的纯函数决策）。
  // ──────────────────────────────────────────────────────────────────
  group('resolveIncomingCallSync — 启停幂等', () {
    test('登录 start / 登出 stop / 切换先停后启 / 同用户幂等', () {
      expect(
        resolveIncomingCallSync(boundUserId: '', nextUserId: 'u1').shouldStart,
        isTrue,
      );
      expect(
        resolveIncomingCallSync(boundUserId: 'u1', nextUserId: '').shouldStop,
        isTrue,
      );
      final swap = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: 'u2');
      expect(swap.shouldStop && swap.shouldStart, isTrue);
      final same = resolveIncomingCallSync(boundUserId: 'u1', nextUserId: 'u1');
      expect(same.shouldStop || same.shouldStart, isFalse);
    });
  });
}

class _Empty extends StatelessWidget {
  const _Empty();
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
