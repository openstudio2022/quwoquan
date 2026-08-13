/// 消息首页列表的断连降级与恢复契约（typed fault 注入 → AsyncError → 恢复重试成功）。
///
/// 故障 profile 消费测试树共享闭集（disconnect），与环境边缘 harness 契约
/// 同源；断言遵循「失败以 AsyncError 表达、无伪成功行、invalidate 恢复后
/// 同装配重试成功」。
///
/// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/message_home_rows_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/fault/typed_fault_injection.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

/// 观测 noop 替身：本测试只验证读路径故障语义，隔离页面观测链路。
final class _NoopPageLifecycleObservability extends Fake
    implements PageLifecycleObservability {
  @override
  void recordPageState({
    required String pageName,
    required String phase,
    String? route,
    String? surface,
    String source = 'online',
    String? copyKey,
    Object? error,
    int? durationMs,
    int? retryCount,
    bool? hasCache,
    int? cacheAgeMs,
    int? itemCount,
    String? requestId,
    String? traceId,
    String? waitMode,
  }) {}
}

/// 组合共享 TypedFaultInjector 的消息首页读 double：故障态由测试切换，
/// 只实现被测路径用到的方法（其余走 Fake）。
final class _FaultInjectingConversationRepository extends Fake
    implements ChatConversationRepository {
  _FaultInjectingConversationRepository(this._delegate, this.injector);

  final InMemoryChatConversationRepository _delegate;
  final TypedFaultInjector injector;

  @override
  Future<List<MessageHomeRow>> listMessageHome({
    String filter = 'all',
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return injector.guard(
      () => _delegate.listMessageHome(
        filter: filter,
        cursor: cursor,
        limit: limit,
      ),
    );
  }
}

void main() {
  test('断连故障下消息首页进入 AsyncError 且恢复后 invalidate 重试成功', () async {
    final injector = TypedFaultInjector();
    final facets = ChatTestFacets();
    final container = ProviderContainer(
      // 禁用 Riverpod 自动重试退避：本测试显式控制故障与恢复时序。
      retry: (retryCount, error) => null,
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        ...chatTestRepositoryOverrides(
          facets: facets,
          conversation: _FaultInjectingConversationRepository(
            InMemoryChatConversationRepository(facets.engine),
            injector,
          ),
        ),
        pageLifecycleObservabilityProvider.overrideWithValue(
          _NoopPageLifecycleObservability(),
        ),
      ],
    );
    addTearDown(container.dispose);

    // 先激活故障，再建立订阅：订阅会立即触发 provider 构建。
    injector.activate(TypedFaultProfile.disconnect);
    // 保持订阅，避免 family provider 在无 listener 时被自动回收导致 future 悬挂。
    final subscription = container.listen(
      messageHomeRowsStateProvider('all'),
      (previous, next) {},
    );
    addTearDown(subscription.close);
    await expectLater(
      container.read(messageHomeRowsStateProvider('all').future),
      throwsA(anything),
    );
    final faulted = container.read(messageHomeRowsStateProvider('all'));
    expect(faulted.hasError, isTrue, reason: '断连必须以 AsyncError 表达');
    expect(faulted.hasValue, isFalse, reason: '故障期间不得出现伪成功快照');

    injector.deactivate();
    final recovered = await container.refresh(
      messageHomeRowsStateProvider('all').future,
    );
    expect(
      recovered.rows,
      isNotEmpty,
      reason: '恢复后同装配 invalidate 重试必须取回真实会话行',
    );
  });
}
