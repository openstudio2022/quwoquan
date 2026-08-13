/// 会话消息加载的断连降级与恢复契约（typed fault 注入 → 结构化错误态 → 恢复重试成功）。
///
/// 故障 profile 消费测试树共享闭集（disconnect / latency），与环境边缘
/// harness 契约同源；断言遵循「无伪成功、错误进入结构化 state.error、
/// 恢复后同装配重试成功」。
///
/// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/fault/typed_fault_injection.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';

const _conversationId = 'fixture_conv_direct';

final class _ChatPersonaQuery extends Fake implements PersonaQuery {
  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    return ActivePersonaContextViewData(
      personaId: 'fixture_user_current',
      ownerUserId: 'fixture_user_current',
      subjectType: 'persona',
      displayName: '可靠性测试用户',
      avatarUrl: '',
      contextVersion: 1,
    );
  }
}

/// 组合共享 TypedFaultInjector 的消息读 double：故障态由测试切换，
/// 只实现被测路径用到的方法（其余走 Fake）。
final class _FaultInjectingMessageRepository extends Fake
    implements ChatMessageRepository {
  _FaultInjectingMessageRepository(this._delegate, this.injector);

  final InMemoryChatMessageRepository _delegate;
  final TypedFaultInjector injector;

  @override
  Future<List<ChatMessageViewData>> listMessages({
    required String conversationId,
    String? before,
    int limit = CloudApiDefaults.pageLimit,
  }) {
    return injector.guard(
      () => _delegate.listMessages(
        conversationId: conversationId,
        before: before,
        limit: limit,
      ),
    );
  }
}

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  test('断连故障下消息加载进入结构化错误态且恢复后同装配重试成功', () async {
    final injector = TypedFaultInjector();
    final facets = ChatTestFacets();
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        ...chatTestRepositoryOverrides(
          facets: facets,
          message: _FaultInjectingMessageRepository(
            InMemoryChatMessageRepository(facets.engine),
            injector,
          ),
        ),
        personaQueryProvider(
          AppUiSurfaces.appShell,
        ).overrideWithValue(_ChatPersonaQuery()),
        mediaEndpointConfigProvider.overrideWithValue(
          MediaEndpointConfig(
            avatarBaseUrl: 'https://avatar.example.test/media/avatar',
            imageBaseUrl: 'https://image.example.test/media/image',
            videoBaseUrl: 'https://video.example.test/media/video',
            attachmentBaseUrl: 'https://image.example.test/media/image',
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(chatMessageProvider(_conversationId).notifier);

    injector.activate(TypedFaultProfile.disconnect);
    await notifier.loadMessages();
    final faulted = container.read(chatMessageProvider(_conversationId));
    expect(faulted.isLoading, isFalse);
    // 消息域为「离线可读」设计：断连不得静默为伪成功——本地副本命中时
    // 必须表达为离线只读来源；本地为空时必须进入结构化错误态。
    // 两者不得混为同一态（message-reliability REQ-001/REQ-003）。
    if (faulted.messages.isNotEmpty) {
      expect(
        faulted.source,
        ChatTimelineContentSource.offlineReadOnly,
        reason: '本地命中且断连必须标记为离线只读来源',
      );
      expect(
        faulted.error,
        isNull,
        reason: '离线只读不得与远端失败混为同一错误态',
      );
    } else {
      expect(faulted.error, isNotNull, reason: '断连且无本地内容必须进入结构化错误态');
      expect(faulted.source, ChatTimelineContentSource.none);
    }

    injector.deactivate();
    await notifier.loadMessages();
    final recovered = container.read(chatMessageProvider(_conversationId));
    expect(recovered.error, isNull, reason: '恢复后错误态必须清除');
    expect(recovered.messages, isNotEmpty, reason: '同装配重试必须取回真实消息');
    expect(
      recovered.source,
      ChatTimelineContentSource.remoteSynced,
      reason: '恢复后内容来源必须收敛为远端已同步',
    );
  });

  test('弱网延迟 profile 下消息加载变慢但最终成功且无重复条目', () async {
    final injector = TypedFaultInjector();
    final facets = ChatTestFacets();
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        ...chatTestRepositoryOverrides(
          facets: facets,
          message: _FaultInjectingMessageRepository(
            InMemoryChatMessageRepository(facets.engine),
            injector,
          ),
        ),
        personaQueryProvider(
          AppUiSurfaces.appShell,
        ).overrideWithValue(_ChatPersonaQuery()),
        mediaEndpointConfigProvider.overrideWithValue(
          MediaEndpointConfig(
            avatarBaseUrl: 'https://avatar.example.test/media/avatar',
            imageBaseUrl: 'https://image.example.test/media/image',
            videoBaseUrl: 'https://video.example.test/media/video',
            attachmentBaseUrl: 'https://image.example.test/media/image',
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final notifier = container.read(chatMessageProvider(_conversationId).notifier);

    injector.activate(
      TypedFaultProfile.latency,
      latency: const Duration(milliseconds: 150),
    );
    await notifier.loadMessages();
    final state = container.read(chatMessageProvider(_conversationId));
    expect(state.error, isNull, reason: '弱网变慢不是失败，必须最终成功');
    expect(state.messages, isNotEmpty);
    expect(
      state.messages.map((message) => message.id).toSet().length,
      state.messages.length,
      reason: '弱网重放不得引入重复消息',
    );
  });
}
