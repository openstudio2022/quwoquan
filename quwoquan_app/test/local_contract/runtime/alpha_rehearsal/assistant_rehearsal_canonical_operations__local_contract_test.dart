// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/search_assistant_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  var sequence = 0;
  final now = DateTime.utc(2026, 9, 13);
  const handler = SearchAssistantRehearsalHandler();
  Future<Object?> call(
    AlphaRehearsalStore store,
    String actor,
    String operation, {
    Map<String, String> path = const {},
    Map<String, String> query = const {},
    Map<String, Object?> body = const {},
  }) => handler.handle(
    RehearsalInvocation(
      operation: appCloudOperationContracts[operation]!,
      payload: CloudOperationRequestPayload(
        pathParameters: path,
        queryParameters: query,
        body: body,
      ),
      context: CloudOperationInvocationContext(
        surfaceId: 'test',
        clientPageId: 'test',
        actor: CloudOperationActorContext(personaId: actor),
      ),
      store: store,
      now: () => now.add(Duration(seconds: sequence)),
      nextId: (prefix) => '$prefix${++sequence}',
    ),
  );
  test('session/run/turn 支持权限、分页、取消与重启', () async {
    final persistence = MemoryRehearsalPersistence();
    final store = AlphaRehearsalStore(persistence: persistence);
    final session = await call(
      store,
      'a',
      'assistant.assistant_session.CreateAssistantSession',
    ) as Map;
    final sid = session['sessionId'] as String;
    final run = await call(
      store,
      'a',
      'assistant.assistant_run.StartAssistantRun',
      path: {'sessionId': sid},
      body: {'goal': 'hello'},
    ) as Map;
    await expectLater(
      call(
        store,
        'b',
        'assistant.assistant_run.GetAssistantRun',
        path: {'runId': run['runId'] as String},
      ),
      throwsA(isA<CloudException>()),
    );
    await call(
      store,
      'a',
      'assistant.assistant_run.PauseAssistantRun',
      path: {'runId': run['runId'] as String},
    );
    final tasks = await call(
      store,
      'a',
      'assistant.assistant_task_view.ListAssistantTasks',
      query: {'status': 'paused'},
    ) as Map;
    expect(tasks['items'], hasLength(1));
    await call(
      store,
      'a',
      'assistant.assistant_run.ResumeAssistantRun',
      path: {'runId': run['runId'] as String},
    );
    await call(
      store,
      'a',
      'assistant.assistant_run.SteerAssistantRun',
      path: {'runId': run['runId'] as String},
      body: {'goal': 'revised'},
    );
    await call(
      store,
      'a',
      'assistant.assistant_run.CancelAssistantRun',
      path: {'runId': run['runId'] as String},
    );
    final restored = AlphaRehearsalStore(persistence: persistence);
    await restored.ensureLoaded();
    final turns = await call(
      restored,
      'a',
      'assistant.assistant_turn_view.ListSessionTurns',
      path: {'sessionId': sid},
      query: {'limit': '1'},
    ) as Map;
    expect((turns['items'] as List).single['inputText'], 'hello');
    expect(
      (await call(
        restored,
        'a',
        'assistant.assistant_run.GetAssistantRun',
        path: {'runId': run['runId'] as String},
      ) as Map)['status'],
      'cancelled',
    );
  });
  test('consent/settings/subscription/data-control 是隔离状态机', () async {
    final store = AlphaRehearsalStore();
    await call(
      store,
      'a',
      'assistant.skill_consent.GrantSkillConsent',
      path: {'skillId': 'calendar'},
      body: {
        'scopes': ['read'],
      },
    );
    await call(
      store,
      'a',
      'assistant.skill_user_setting.PutSkillUserSetting',
      path: {'skillId': 'calendar'},
      body: {'status': 'enabled', 'memoryPolicy': 'disabled'},
    );
    final sub = await call(
      store,
      'a',
      'assistant.skill_subscription.CreateSkillSubscription',
      body: {'skillId': 'calendar'},
    ) as Map;
    await call(
      store,
      'a',
      'assistant.skill_subscription.UpdateSkillSubscriptionStatus',
      path: {'subscriptionId': sub['subscriptionId'] as String},
      body: {'status': 'paused'},
    );
    final request = await call(
      store,
      'a',
      'assistant.skill_data_control_request.CreateSkillDataControlRequest',
      path: {'skillId': 'calendar'},
      body: {
        'requestedActions': ['delete_configuration', 'revoke_consent'],
      },
    ) as Map;
    final rid = (request['request'] as Map)['requestId'] as String;
    await call(
      store,
      'a',
      'assistant.skill_data_control_request.ConfirmSkillDataControlRequest',
      path: {'requestId': rid},
    );
    final consents =
        await call(store, 'a', 'assistant.skill_consent.ListConsents') as Map;
    expect(consents['items'], isEmpty);
    await expectLater(
      call(
        store,
        'a',
        'assistant.skill_user_setting.GetSkillUserSetting',
        path: {'skillId': 'calendar'},
      ),
      throwsA(isA<CloudException>()),
    );
    await expectLater(
      call(
        store,
        'b',
        'assistant.skill_subscription.GetSkillSubscription',
        path: {'subscriptionId': sub['subscriptionId'] as String},
      ),
      throwsA(isA<CloudException>()),
    );
  });
  test('设备动作与外部 provider 不冒充成功', () async {
    final store = AlphaRehearsalStore();
    await expectLater(
      call(
        store,
        'a',
        'assistant.assistant_run.SubmitDeviceActionReceipt',
        path: {'runId': 'missing', 'toolInvocationId': 'tool'},
      ),
      throwsA(
        isA<CloudException>().having(
          (e) => e.runtimeFailure.kind,
          'kind',
          RuntimeFailureKind.unsupported,
        ),
      ),
    );
    await expectLater(
      call(
        store,
        'a',
        'assistant.assistant_run.ApproveAssistantToolUse',
        path: {'runId': 'missing', 'toolInvocationId': 'tool'},
      ),
      throwsA(
        isA<CloudException>().having(
          (e) => e.runtimeFailure.kind,
          'kind',
          RuntimeFailureKind.unsupported,
        ),
      ),
    );
  });
}
