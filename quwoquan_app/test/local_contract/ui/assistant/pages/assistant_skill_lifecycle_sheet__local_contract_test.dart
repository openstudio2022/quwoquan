// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/assistant/skill_activity_view/application/skill_activity_query.dart';
import 'package:quwoquan_app/application/assistant/skill_data_control/skill_data_control_facet.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_lifecycle_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _skillId = 'travel_companion';
const _skillName = '贴身旅行管家';

Widget _host({
  required AssistantSkillActivityQuery activityQuery,
  required AssistantSkillDataControlFacet dataControlFacet,
}) {
  return CupertinoApp(
    locale: const Locale('zh'),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: Builder(
      builder: (context) => CupertinoButton(
        key: const ValueKey<String>('open_skill_lifecycle'),
        onPressed: () => showAssistantSkillLifecycleSheet(
          context: context,
          skillId: _skillId,
          skillName: _skillName,
          activityQuery: activityQuery,
          dataControlFacet: dataControlFacet,
          onProductAction: (_) {},
        ),
        child: const Text('open'),
      ),
    ),
  );
}

Future<void> _openSheet(
  WidgetTester tester, {
  required AssistantSkillActivityQuery activityQuery,
  required AssistantSkillDataControlFacet dataControlFacet,
}) async {
  await tester.pumpWidget(
    _host(activityQuery: activityQuery, dataControlFacet: dataControlFacet),
  );
  await tester.tap(find.byKey(const ValueKey<String>('open_skill_lifecycle')));
  await tester.pumpAndSettle();
}

Future<void> _selectActionAndCreate(
  WidgetTester tester,
  SkillDataControlAction action,
) async {
  final choice = find.byKey(
    ValueKey<String>('assistant_skill_data_control_${action.wireName}'),
  );
  await tester.ensureVisible(choice);
  await tester.tap(choice);
  await tester.pump();
  final create = find.byKey(
    const ValueKey<String>('assistant_skill_data_control_create'),
  );
  await tester.ensureVisible(create);
  await tester.tap(create);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'activity recovery uses typed dataControlRequestId and ignores source ref',
    (tester) async {
      const typedRequestId = 'control-typed-7';
      const sourceObjectRef =
          'assistant.SkillDataControlRequest:forged-control-99';
      final activityQuery = _ActivityQueryFake(
        items: <SkillActivityView>[
          _activity(
            activityId: 'activity-recover',
            sourceObjectRef: sourceObjectRef,
            dataControlRequestId: typedRequestId,
            displayKey: SkillActivityDisplayKey.dataControlFailed,
            recoveryAction: SkillActivityRecoveryAction.retryDataControl,
          ),
        ],
      );
      final dataControlFacet = _DataControlFacetFake()
        ..getResults.add(
          _request(
            requestId: typedRequestId,
            status: SkillDataControlRequestStatus.cancelled,
            revision: 3,
          ),
        );

      await _openSheet(
        tester,
        activityQuery: activityQuery,
        dataControlFacet: dataControlFacet,
      );
      expect(find.text(sourceObjectRef), findsNothing);
      expect(find.text(typedRequestId), findsNothing);

      await tester.tap(
        find.byKey(
          const ValueKey<String>(
            'assistant_skill_activity_resume_activity-recover',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(dataControlFacet.getRequestIds, <String>[typedRequestId]);
      expect(
        dataControlFacet.getRequestIds,
        isNot(contains('forged-control-99')),
      );
      expect(
        find.text(AssistantText.assistantSkillDataControlCancelled),
        findsWidgets,
      );
    },
  );

  testWidgets('selected actions create and confirm the same request', (
    tester,
  ) async {
    final dataControlFacet = _DataControlFacetFake()
      ..createResults.add(
        _receipt(
          _request(
            requestId: 'control-same-1',
            status: SkillDataControlRequestStatus.pendingConfirmation,
            revision: 4,
          ),
        ),
      )
      ..confirmResults.add(
        _receipt(
          _request(
            requestId: 'control-same-1',
            status: SkillDataControlRequestStatus.completed,
            revision: 5,
            completedActions: const <SkillDataControlAction>[
              SkillDataControlAction.revokeConsent,
            ],
          ),
        ),
      );
    await _openSheet(
      tester,
      activityQuery: const _ActivityQueryFake(),
      dataControlFacet: dataControlFacet,
    );

    await _selectActionAndCreate(tester, SkillDataControlAction.revokeConsent);
    expect(
      find.text(AssistantText.assistantSkillDataControlConfirmTitle),
      findsOneWidget,
    );
    await tester.tap(find.text(AssistantText.assistantSkillDataControlConfirm));
    await tester.pumpAndSettle();

    expect(dataControlFacet.createdSkillIds, <String>[_skillId]);
    expect(dataControlFacet.createdActions.single, <SkillDataControlAction>[
      SkillDataControlAction.revokeConsent,
    ]);
    expect(dataControlFacet.confirmRequestIds, <String>['control-same-1']);
    expect(dataControlFacet.confirmExpectedRevisions, <int>[4]);
    expect(dataControlFacet.confirmedValues, <bool>[true]);
    expect(
      find.text(AssistantText.assistantSkillDataControlCompleted),
      findsWidgets,
    );
  });

  testWidgets('closing a pending recovery sends an explicit cancel', (
    tester,
  ) async {
    const requestId = 'control-pending-close';
    final activityQuery = _ActivityQueryFake(
      items: <SkillActivityView>[
        _activity(
          activityId: 'activity-pending',
          sourceObjectRef: 'assistant.SkillDataControlRequest:opaque-source',
          dataControlRequestId: requestId,
          displayKey: SkillActivityDisplayKey.dataControlPendingConfirmation,
          recoveryAction: SkillActivityRecoveryAction.retryDataControl,
        ),
      ],
    );
    final dataControlFacet = _DataControlFacetFake()
      ..getResults.add(
        _request(
          requestId: requestId,
          status: SkillDataControlRequestStatus.pendingConfirmation,
          revision: 9,
        ),
      )
      ..confirmResults.add(
        _receipt(
          _request(
            requestId: requestId,
            status: SkillDataControlRequestStatus.cancelled,
            revision: 10,
          ),
        ),
      );
    await _openSheet(
      tester,
      activityQuery: activityQuery,
      dataControlFacet: dataControlFacet,
    );

    await tester.tap(
      find.byKey(
        const ValueKey<String>(
          'assistant_skill_activity_resume_activity-pending',
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text(AssistantText.assistantSkillDataControlCancel));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey<String>('assistant_skill_lifecycle_close')),
    );
    await tester.pumpAndSettle();

    expect(dataControlFacet.confirmRequestIds, <String>[requestId]);
    expect(dataControlFacet.confirmExpectedRevisions, <int>[9]);
    expect(dataControlFacet.confirmedValues, <bool>[false]);
    expect(
      find.byKey(const ValueKey<String>('assistant_skill_lifecycle_close')),
      findsNothing,
    );
  });

  testWidgets('bounded executing state is not presented as completion', (
    tester,
  ) async {
    final dataControlFacet = _DataControlFacetFake()
      ..createResults.add(
        _receipt(
          _request(
            requestId: 'control-executing',
            status: SkillDataControlRequestStatus.pendingConfirmation,
            revision: 1,
          ),
        ),
      )
      ..confirmResults.add(
        _receipt(
          _request(
            requestId: 'control-executing',
            status: SkillDataControlRequestStatus.executing,
            revision: 2,
          ),
        ),
      )
      ..fallbackGetResult = _request(
        requestId: 'control-executing',
        status: SkillDataControlRequestStatus.executing,
        revision: 2,
      );
    await _openSheet(
      tester,
      activityQuery: const _ActivityQueryFake(),
      dataControlFacet: dataControlFacet,
    );

    await _selectActionAndCreate(
      tester,
      SkillDataControlAction.archiveSubscriptions,
    );
    await tester.tap(find.text(AssistantText.assistantSkillDataControlConfirm));
    await tester.pumpAndSettle();

    expect(dataControlFacet.getRequestIds, hasLength(6));
    expect(
      find.text(AssistantText.assistantSkillDataControlExecuting),
      findsWidgets,
    );
    expect(
      find.text(AssistantText.assistantSkillDataControlCompleted),
      findsNothing,
    );
  });

  testWidgets('failed operations show safe copy without raw error or IDs', (
    tester,
  ) async {
    const rawFailure =
        'socket failed account-secret-42 control-sensitive-98 trace-private';
    final dataControlFacet = _DataControlFacetFake()
      ..createFailures.add(StateError(rawFailure));
    await _openSheet(
      tester,
      activityQuery: _ActivityQueryFake(
        items: <SkillActivityView>[
          _activity(
            activityId: 'activity-safe-copy',
            sourceObjectRef: 'assistant.Run:run-sensitive-11',
            displayKey: SkillActivityDisplayKey.runFailed,
            recoveryAction: SkillActivityRecoveryAction.retryRun,
          ),
        ],
      ),
      dataControlFacet: dataControlFacet,
    );

    await _selectActionAndCreate(
      tester,
      SkillDataControlAction.hideActivityHistory,
    );

    expect(
      find.text(AssistantText.assistantSkillDataControlFailed),
      findsOneWidget,
    );
    expect(find.textContaining(rawFailure), findsNothing);
    expect(find.textContaining('account-secret-42'), findsNothing);
    expect(find.textContaining('control-sensitive-98'), findsNothing);
    expect(find.textContaining('run-sensitive-11'), findsNothing);
  });
}

SkillActivityView _activity({
  required String activityId,
  required String sourceObjectRef,
  required SkillActivityDisplayKey displayKey,
  required SkillActivityRecoveryAction recoveryAction,
  String? dataControlRequestId,
}) {
  return SkillActivityView(
    activityId: activityId,
    skillId: _skillId,
    activityKind: dataControlRequestId == null
        ? SkillActivityKind.run
        : SkillActivityKind.dataControl,
    status: displayKey.wireName,
    displayKey: displayKey,
    sourceObjectRef: sourceObjectRef,
    sourceRevision: 1,
    dataControlRequestId: dataControlRequestId,
    recoveryAction: recoveryAction,
    occurredAt: '2026-08-04T00:00:00Z',
  );
}

SkillDataControlRequest _request({
  required String requestId,
  required SkillDataControlRequestStatus status,
  required int revision,
  List<SkillDataControlAction> completedActions =
      const <SkillDataControlAction>[],
}) {
  return SkillDataControlRequest(
    requestId: requestId,
    skillId: _skillId,
    requestedActions: const <SkillDataControlAction>[
      SkillDataControlAction.hideActivityHistory,
      SkillDataControlAction.revokeConsent,
      SkillDataControlAction.archiveSubscriptions,
    ],
    completedActions: completedActions,
    status: status,
    createdAt: '2026-08-04T00:00:00Z',
    updatedAt: '2026-08-04T00:01:00Z',
    revision: revision,
  );
}

SkillDataControlMutationReceipt _receipt(SkillDataControlRequest request) {
  return SkillDataControlMutationReceipt(request: request, replayed: false);
}

final class _ActivityQueryFake implements AssistantSkillActivityQuery {
  const _ActivityQueryFake({this.items = const <SkillActivityView>[]});

  final List<SkillActivityView> items;

  @override
  Future<SkillActivitySlice> listSkillActivities({
    required String skillId,
    String cursor = '',
    int limit = kAssistantSkillActivityDefaultLimit,
  }) async {
    return SkillActivitySlice(
      items: items,
      nextCursor: null,
      externalSources: const [],
    );
  }
}

final class _DataControlFacetFake implements AssistantSkillDataControlFacet {
  final List<Object> createFailures = <Object>[];
  final List<SkillDataControlMutationReceipt> createResults =
      <SkillDataControlMutationReceipt>[];
  final List<SkillDataControlMutationReceipt> confirmResults =
      <SkillDataControlMutationReceipt>[];
  final List<SkillDataControlRequest> getResults = <SkillDataControlRequest>[];
  SkillDataControlRequest? fallbackGetResult;

  final List<String> createdSkillIds = <String>[];
  final List<List<SkillDataControlAction>> createdActions =
      <List<SkillDataControlAction>>[];
  final List<String> confirmRequestIds = <String>[];
  final List<int> confirmExpectedRevisions = <int>[];
  final List<bool> confirmedValues = <bool>[];
  final List<String> getRequestIds = <String>[];

  @override
  Future<SkillDataControlMutationReceipt> createSkillDataControlRequest({
    required String skillId,
    required List<SkillDataControlAction> requestedActions,
    required String clientRequestId,
  }) async {
    createdSkillIds.add(skillId);
    createdActions.add(List<SkillDataControlAction>.of(requestedActions));
    if (createFailures.isNotEmpty) throw createFailures.removeAt(0);
    return createResults.removeAt(0);
  }

  @override
  Future<SkillDataControlMutationReceipt> confirmSkillDataControlRequest({
    required String requestId,
    required int expectedRevision,
    required bool confirmed,
    required String clientRequestId,
  }) async {
    confirmRequestIds.add(requestId);
    confirmExpectedRevisions.add(expectedRevision);
    confirmedValues.add(confirmed);
    return confirmResults.removeAt(0);
  }

  @override
  Future<SkillDataControlRequest> getSkillDataControlRequest({
    required String requestId,
  }) async {
    getRequestIds.add(requestId);
    if (getResults.isNotEmpty) return getResults.removeAt(0);
    final fallback = fallbackGetResult;
    if (fallback == null) {
      throw StateError('unexpected getSkillDataControlRequest');
    }
    return fallback;
  }
}
