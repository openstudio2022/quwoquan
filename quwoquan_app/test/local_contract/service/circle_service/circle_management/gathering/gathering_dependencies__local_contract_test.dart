// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show ProviderException;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers_gathering_journey.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

Object _unwrap(Object error) {
  var current = error;
  while (current is ProviderException) {
    current = current.exception;
  }
  return current;
}

void _expectGatheringAdapterUnavailable({
  required Object Function() readPort,
  required String portName,
}) {
  Object? thrown;
  try {
    readPort();
  } catch (error) {
    thrown = _unwrap(error);
  }

  expect(thrown, isA<RuntimeFailureBase>());
  final failure = thrown! as RuntimeFailureBase;
  expect(failure.kind, RuntimeFailureKind.unavailable);
  expect(failure.semanticReason, 'gathering_remote_adapter_unavailable');
  expect(failure.location.businessObject, 'circle.gathering');
  expect(
    failure.context.attributes
        .singleWhere((attribute) => attribute.key == 'port')
        .value,
    portName,
  );
}

void main() {
  test('缺 generated adapter 时 production Gathering port 结构化 fail-fast', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    for (final entry in <({String portName, Object Function() readPort})>[
      (
        portName: 'GatheringCommandWriter',
        readPort: () => container.read(gatheringCommandWriterProvider),
      ),
      (
        portName: 'GatheringQueryReader',
        readPort: () => container.read(gatheringQueryReaderProvider),
      ),
    ]) {
      _expectGatheringAdapterUnavailable(
        readPort: entry.readPort,
        portName: entry.portName,
      );
    }
  });

  test('Journey handoff 缺失时十六个 Circle-owned typed port 全部 fail-fast', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    for (final entry in <({String portName, Object Function() readPort})>[
      (
        portName: 'GatheringJourneyCapabilityQuery',
        readPort: () => container.read(gatheringJourneyCapabilityQueryProvider),
      ),
      (
        portName: 'GatheringJourneyParticipationWriter',
        readPort: () =>
            container.read(gatheringJourneyParticipationWriterProvider),
      ),
      (
        portName: 'GatheringJourneyPlacementQuery',
        readPort: () => container.read(gatheringJourneyPlacementQueryProvider),
      ),
      (
        portName: 'GatheringJourneyPlacementWriter',
        readPort: () => container.read(gatheringJourneyPlacementWriterProvider),
      ),
      (
        portName: 'GatheringJourneyContentReferenceWriter',
        readPort: () =>
            container.read(gatheringJourneyContentReferenceWriterProvider),
      ),
      (
        portName: 'GatheringJourneySupportAssignmentWriter',
        readPort: () =>
            container.read(gatheringJourneySupportAssignmentWriterProvider),
      ),
      (
        portName: 'GatheringJourneyExperienceWriter',
        readPort: () =>
            container.read(gatheringJourneyExperienceWriterProvider),
      ),
      (
        portName: 'GatheringPlanCommandWriter',
        readPort: () => container.read(gatheringPlanCommandWriterProvider),
      ),
      (
        portName: 'GatheringPlanQueryReader',
        readPort: () => container.read(gatheringPlanQueryReaderProvider),
      ),
      (
        portName: 'GatheringJourneyQuery',
        readPort: () => container.read(gatheringJourneyQueryProvider),
      ),
      (
        portName: 'GatheringJourneyShareSnapshotQuery',
        readPort: () =>
            container.read(gatheringJourneyShareSnapshotQueryProvider),
      ),
      (
        portName: 'GatheringJourneyShareSnapshotWriter',
        readPort: () =>
            container.read(gatheringJourneyShareSnapshotWriterProvider),
      ),
      (
        portName: 'GatheringJourneyTemplateQuery',
        readPort: () => container.read(gatheringJourneyTemplateQueryProvider),
      ),
      (
        portName: 'GatheringJourneyTemplateWriter',
        readPort: () => container.read(gatheringJourneyTemplateWriterProvider),
      ),
      (
        portName: 'GatheringJourneyTravelogueDraftWriter',
        readPort: () =>
            container.read(gatheringJourneyTravelogueDraftWriterProvider),
      ),
      (
        portName: 'GatheringJourneyPostPublicationContinuationRegistry',
        readPort: () => container.read(
          gatheringJourneyPostPublicationContinuationRegistryProvider,
        ),
      ),
    ]) {
      _expectGatheringAdapterUnavailable(
        readPort: entry.readPort,
        portName: entry.portName,
      );
    }
  });
}
