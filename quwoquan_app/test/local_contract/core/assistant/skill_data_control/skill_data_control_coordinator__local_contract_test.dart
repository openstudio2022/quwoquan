// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/assistant/skill_data_control_request/application/skill_data_control_coordinator.dart';
import 'package:quwoquan_app/assistant/assistant/skill_data_control_request/application/skill_data_control_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'unknown create result retries with the same idempotency intent',
    () async {
      final facet = _DataControlFacetFake()
        ..createFailures.add(StateError('network result unknown'));
      var sequence = 0;
      final coordinator = SkillDataControlCoordinator(
        facet: facet,
        intentFactory: () => 'intent-${++sequence}',
        delay: (_) async {},
      );

      await expectLater(
        coordinator.create(
          skillId: 'travel_companion',
          requestedActions: const <SkillDataControlAction>[
            SkillDataControlAction.hideActivityHistory,
          ],
        ),
        throwsStateError,
      );
      final state = await coordinator.retryCreate();

      expect(facet.createIntentIds, <String>['intent-1', 'intent-1']);
      expect(state.phase, SkillDataControlFlowPhase.pendingConfirmation);
      expect(state.request?.requestId, 'control-1');
    },
  );

  test(
    'revision conflict gets the same request and resumes incomplete work',
    () async {
      final facet = _DataControlFacetFake()
        ..confirmFailures.add(StateError('revision conflict'))
        ..getResults.addAll(<SkillDataControlRequest>[
          _request(
            status: SkillDataControlRequestStatus.failed,
            revision: 2,
            completedActions: const <SkillDataControlAction>[
              SkillDataControlAction.hideActivityHistory,
            ],
          ),
          _request(
            status: SkillDataControlRequestStatus.completed,
            revision: 4,
            completedActions: const <SkillDataControlAction>[
              SkillDataControlAction.hideActivityHistory,
              SkillDataControlAction.revokeConsent,
            ],
          ),
        ])
        ..confirmResults.add(
          _receipt(
            _request(
              status: SkillDataControlRequestStatus.executing,
              revision: 3,
              completedActions: const <SkillDataControlAction>[
                SkillDataControlAction.hideActivityHistory,
              ],
            ),
          ),
        );
      var sequence = 0;
      final coordinator = SkillDataControlCoordinator(
        facet: facet,
        intentFactory: () => 'intent-${++sequence}',
        delay: (_) async {},
      );
      facet.createResults.add(
        _receipt(
          _request(
            status: SkillDataControlRequestStatus.pendingConfirmation,
            revision: 1,
          ),
        ),
      );
      await coordinator.create(
        skillId: 'travel_companion',
        requestedActions: const <SkillDataControlAction>[
          SkillDataControlAction.hideActivityHistory,
          SkillDataControlAction.revokeConsent,
        ],
      );

      final state = await coordinator.confirm();

      expect(facet.confirmRequestIds, <String>['control-1', 'control-1']);
      expect(facet.confirmExpectedRevisions, <int>[1, 2]);
      expect(facet.confirmIntentIds, <String>['intent-2', 'intent-3']);
      expect(state.phase, SkillDataControlFlowPhase.completed);
      expect(state.request?.completedActions, <SkillDataControlAction>[
        SkillDataControlAction.hideActivityHistory,
        SkillDataControlAction.revokeConsent,
      ]);
    },
  );

  test(
    'unknown confirmation retries the same revision with one intent',
    () async {
      final facet = _DataControlFacetFake()
        ..confirmFailures.add(StateError('network result unknown'))
        ..getResults.add(
          _request(
            status: SkillDataControlRequestStatus.pendingConfirmation,
            revision: 1,
          ),
        )
        ..confirmResults.add(
          _receipt(
            _request(
              status: SkillDataControlRequestStatus.completed,
              revision: 2,
            ),
          ),
        );
      var sequence = 0;
      final coordinator = SkillDataControlCoordinator(
        facet: facet,
        intentFactory: () => 'intent-${++sequence}',
        delay: (_) async {},
      );
      await coordinator.create(
        skillId: 'travel_companion',
        requestedActions: const <SkillDataControlAction>[
          SkillDataControlAction.hideActivityHistory,
        ],
      );

      final state = await coordinator.confirm();

      expect(facet.confirmRequestIds, <String>['control-1', 'control-1']);
      expect(facet.confirmExpectedRevisions, <int>[1, 1]);
      expect(facet.confirmIntentIds, <String>['intent-2', 'intent-2']);
      expect(state.phase, SkillDataControlFlowPhase.completed);
    },
  );

  test('bounded polling keeps honest executing state', () async {
    final facet = _DataControlFacetFake()
      ..createResults.add(
        _receipt(
          _request(
            status: SkillDataControlRequestStatus.pendingConfirmation,
            revision: 1,
          ),
        ),
      )
      ..confirmResults.add(
        _receipt(
          _request(
            status: SkillDataControlRequestStatus.executing,
            revision: 2,
          ),
        ),
      )
      ..getResults.addAll(<SkillDataControlRequest>[
        _request(status: SkillDataControlRequestStatus.executing, revision: 2),
        _request(status: SkillDataControlRequestStatus.executing, revision: 2),
      ]);
    final coordinator = SkillDataControlCoordinator(
      facet: facet,
      intentFactory: () => 'intent',
      delay: (_) async {},
      maximumPollAttempts: 2,
    );
    await coordinator.create(
      skillId: 'travel_companion',
      requestedActions: const <SkillDataControlAction>[
        SkillDataControlAction.archiveSubscriptions,
      ],
    );

    final state = await coordinator.confirm();

    expect(state.phase, SkillDataControlFlowPhase.executing);
    expect(state.error, isNull);
    expect(facet.getRequestIds, <String>['control-1', 'control-1']);
  });

  test('resume uses the typed request id directly', () async {
    final facet = _DataControlFacetFake()
      ..getResults.add(
        _request(status: SkillDataControlRequestStatus.cancelled, revision: 2),
      );
    final coordinator = SkillDataControlCoordinator(
      facet: facet,
      intentFactory: () => 'intent',
      delay: (_) async {},
    );

    final state = await coordinator.resume('control-activity-7');

    expect(facet.getRequestIds, <String>['control-activity-7']);
    expect(state.phase, SkillDataControlFlowPhase.cancelled);
  });

  test(
    'cancelling pending work keeps the canonical request identity',
    () async {
      final facet = _DataControlFacetFake()
        ..createResults.add(
          _receipt(
            _request(
              status: SkillDataControlRequestStatus.pendingConfirmation,
              revision: 7,
            ),
          ),
        )
        ..confirmResults.add(
          _receipt(
            _request(
              status: SkillDataControlRequestStatus.cancelled,
              revision: 8,
            ),
          ),
        );
      var sequence = 0;
      final coordinator = SkillDataControlCoordinator(
        facet: facet,
        intentFactory: () => 'intent-${++sequence}',
        delay: (_) async {},
      );
      await coordinator.create(
        skillId: 'travel_companion',
        requestedActions: const <SkillDataControlAction>[
          SkillDataControlAction.archiveSubscriptions,
        ],
      );

      final state = await coordinator.cancelPending();

      expect(facet.confirmRequestIds, <String>['control-1']);
      expect(facet.confirmExpectedRevisions, <int>[7]);
      expect(facet.confirmedValues, <bool>[false]);
      expect(state.phase, SkillDataControlFlowPhase.cancelled);
      expect(state.request?.requestId, 'control-1');
    },
  );
}

SkillDataControlRequest _request({
  required SkillDataControlRequestStatus status,
  required int revision,
  List<SkillDataControlAction> completedActions =
      const <SkillDataControlAction>[],
}) {
  return SkillDataControlRequest(
    requestId: 'control-1',
    skillId: 'travel_companion',
    requestedActions: const <SkillDataControlAction>[
      SkillDataControlAction.hideActivityHistory,
      SkillDataControlAction.revokeConsent,
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

final class _DataControlFacetFake implements AssistantSkillDataControlFacet {
  final List<Object> createFailures = <Object>[];
  final List<Object> confirmFailures = <Object>[];
  final List<SkillDataControlMutationReceipt> createResults =
      <SkillDataControlMutationReceipt>[];
  final List<SkillDataControlMutationReceipt> confirmResults =
      <SkillDataControlMutationReceipt>[];
  final List<SkillDataControlRequest> getResults = <SkillDataControlRequest>[];
  final List<String> createIntentIds = <String>[];
  final List<String> confirmRequestIds = <String>[];
  final List<int> confirmExpectedRevisions = <int>[];
  final List<bool> confirmedValues = <bool>[];
  final List<String> confirmIntentIds = <String>[];
  final List<String> getRequestIds = <String>[];

  @override
  Future<SkillDataControlMutationReceipt> createSkillDataControlRequest({
    required String skillId,
    required List<SkillDataControlAction> requestedActions,
    required String clientRequestId,
  }) async {
    createIntentIds.add(clientRequestId);
    if (createFailures.isNotEmpty) {
      throw createFailures.removeAt(0);
    }
    if (createResults.isNotEmpty) {
      return createResults.removeAt(0);
    }
    return _receipt(
      _request(
        status: SkillDataControlRequestStatus.pendingConfirmation,
        revision: 1,
      ),
    );
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
    confirmIntentIds.add(clientRequestId);
    if (confirmFailures.isNotEmpty) {
      throw confirmFailures.removeAt(0);
    }
    if (confirmResults.isNotEmpty) {
      return confirmResults.removeAt(0);
    }
    return _receipt(
      _request(
        status: confirmed
            ? SkillDataControlRequestStatus.executing
            : SkillDataControlRequestStatus.cancelled,
        revision: expectedRevision + 1,
      ),
    );
  }

  @override
  Future<SkillDataControlRequest> getSkillDataControlRequest({
    required String requestId,
  }) async {
    getRequestIds.add(requestId);
    return getResults.removeAt(0);
  }
}
