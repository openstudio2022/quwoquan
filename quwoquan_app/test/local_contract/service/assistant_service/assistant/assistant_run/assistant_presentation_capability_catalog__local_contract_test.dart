// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';

void main() {
  test(
    'rich personal surface advertises only production-owned action intents',
    () {
      final snapshot = _snapshot(
        surfacePolicy: AssistantPresentationSurfacePolicy.personal,
        mediaEnabled: true,
        actionsEnabled: true,
      );

      expect(
        snapshot.supportedNodeKinds,
        containsAll(<AssistantPresentationNodeKind>[
          AssistantPresentationNodeKind.routeMap,
          AssistantPresentationNodeKind.comparisonTable,
          AssistantPresentationNodeKind.media,
          AssistantPresentationNodeKind.confirmationCard,
        ]),
      );
      expect(snapshot.viewportClass.wireName, isNot('any'));
      expect(snapshot.supportedActionIntents, const <String>['ApproveTool']);
      expect(snapshot.supportedActionIntents, isNot(contains('Navigate')));
      expect(
        snapshot.supportedActionIntents,
        isNot(contains('ExecuteDeviceAction')),
      );
      expect(snapshot.supportedActionIntents, isNot(contains('ProvideInput')));
    },
  );

  test('offline personal surface fails closed for media and action nodes', () {
    final snapshot = _snapshot(
      surfacePolicy: AssistantPresentationSurfacePolicy.personal,
      offline: true,
      mediaEnabled: true,
      actionsEnabled: true,
    );

    expect(
      snapshot.supportedNodeKinds,
      contains(AssistantPresentationNodeKind.routeMap),
    );
    expect(
      snapshot.supportedNodeKinds,
      isNot(contains(AssistantPresentationNodeKind.media)),
    );
    expect(
      snapshot.supportedNodeKinds,
      isNot(contains(AssistantPresentationNodeKind.confirmationCard)),
    );
    expect(snapshot.supportedActionIntents, isEmpty);
  });

  test('network surface rejects optional capability advertisement', () {
    final snapshot = _snapshot(
      surfacePolicy: AssistantPresentationSurfacePolicy.network,
      mediaEnabled: true,
      actionsEnabled: true,
    );

    expect(snapshot.supportedNodeKinds, isEmpty);
    expect(snapshot.supportedActionIntents, isEmpty);
  });

  test('viewport classification rejects unavailable runtime geometry', () {
    expect(
      () => AssistantPresentationViewportClass.fromWidth(
        0,
        compactBelow: 420,
        expandedFrom: 600,
      ),
      throwsArgumentError,
    );
    expect(
      AssistantPresentationViewportClass.fromWidth(
        390,
        compactBelow: 420,
        expandedFrom: 600,
      ),
      AssistantPresentationViewportClass.compact,
    );
    expect(
      AssistantPresentationViewportClass.fromWidth(
        500,
        compactBelow: 420,
        expandedFrom: 600,
      ),
      AssistantPresentationViewportClass.standard,
    );
    expect(
      AssistantPresentationViewportClass.fromWidth(
        800,
        compactBelow: 420,
        expandedFrom: 600,
      ),
      AssistantPresentationViewportClass.expanded,
    );
  });
}

AssistantPresentationCapabilitySnapshot _snapshot({
  required AssistantPresentationSurfacePolicy surfacePolicy,
  bool offline = false,
  bool mediaEnabled = false,
  bool actionsEnabled = false,
}) {
  return AssistantPresentationCapabilitySnapshot(
    surfacePolicy: surfacePolicy,
    viewportClass: AssistantPresentationViewportClass.standard,
    platform: 'ios',
    darkTheme: false,
    textScale: 1,
    reducedMotion: false,
    offline: offline,
    mediaEnabled: mediaEnabled,
    actionsEnabled: actionsEnabled,
  );
}
