// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/travel/trip_plan_creation_coordinator.dart';
import 'package:quwoquan_app/application/travel/trip_plan_creation_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'blank Trip draft freezes normalized command and one retry key',
    () async {
      final facet = _RecordingCreationFacet();
      final coordinator = TripPlanCreationCoordinator(
        facet,
        () => 'trip-create-intent-1',
      );
      final intent = coordinator.prepareDraft(title: '  西湖七日同行  ');

      await coordinator.create(intent);
      await coordinator.create(intent);

      expect(intent.directCommand?.title, '西湖七日同行');
      expect(intent.directCommand?.items, isEmpty);
      expect(facet.keys, <String>[
        'trip-create-intent-1',
        'trip-create-intent-1',
      ]);
    },
  );

  test(
    'template creation freezes template identity and rejects bad range',
    () async {
      final facet = _RecordingCreationFacet();
      final coordinator = TripPlanCreationCoordinator(
        facet,
        () => 'template-create-intent-1',
      );
      final intent = coordinator.prepareFromTemplate(
        templateId: ' template-1 ',
        title: '  西湖周末  ',
      );

      await coordinator.create(intent);
      await coordinator.create(intent);

      expect(intent.templateCommand?.templateId, 'template-1');
      expect(intent.templateCommand?.title, '西湖周末');
      expect(facet.keys, <String>[
        'template-create-intent-1',
        'template-create-intent-1',
      ]);
      expect(
        () => coordinator.prepareDraft(
          title: '错误日期',
          startAt: DateTime.utc(2026, 8, 3),
          endAt: DateTime.utc(2026, 8, 2),
        ),
        throwsArgumentError,
      );
    },
  );
}

final class _RecordingCreationFacet implements TripPlanCreationFacet {
  final List<String> keys = <String>[];

  @override
  Future<TripPlanCommandResult> create(
    CreateTripPlanCommand command, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _result();
  }

  @override
  Future<TripPlanCommandResult> createFromTemplate(
    CreateTripPlanFromTemplateCommand command, {
    required String idempotencyKey,
  }) async {
    keys.add(idempotencyKey);
    return _result();
  }
}

TripPlanCommandResult _result() => const TripPlanCommandResult(
  tripId: 'trip-1',
  version: 1,
  currentRevisionId: 'revision-1',
  currentRevisionNumber: 1,
  status: TripPlanStatus.planning,
  idempotentReplay: false,
);
