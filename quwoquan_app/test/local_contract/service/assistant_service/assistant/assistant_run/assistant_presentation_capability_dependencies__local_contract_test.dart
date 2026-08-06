// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/state/accessibility_provider.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'production DI exports measured appearance and online capability truth',
    () async {
      final telemetry = _telemetry(<ConnectivityResult>[
        ConnectivityResult.wifi,
      ]);
      await telemetry.initialize();
      addTearDown(telemetry.dispose);
      final container = ProviderContainer(
        overrides: [
          appTelemetryContextProvider.overrideWithValue(telemetry),
          platformTargetProvider.overrideWithValue(AppPlatform.ios),
        ],
      );
      addTearDown(container.dispose);
      container
          .read(responsiveProvider.notifier)
          .updateFromSize(const Size(500, 900));
      container.read(themeProvider.notifier).setDark(true);
      container
          .read(accessibilityProvider.notifier)
          .updateFromMediaQueryData(
            const MediaQueryData(
              size: Size(500, 900),
              textScaler: TextScaler.linear(1.35),
              disableAnimations: true,
            ),
          );

      final factory = container.read(
        assistantPresentationCapabilitySnapshotFactoryProvider,
      );
      final snapshot = factory(AssistantPresentationSurfacePolicy.personal);

      expect(
        snapshot.viewportClass,
        AssistantPresentationViewportClass.standard,
      );
      expect(snapshot.platform, 'ios');
      expect(snapshot.themeWireName, 'dark');
      expect(snapshot.textScale, closeTo(1.35, 0.0001));
      expect(snapshot.reducedMotion, isTrue);
      expect(snapshot.offline, isFalse);
      expect(
        snapshot.supportedNodeKinds,
        contains(AssistantPresentationNodeKind.routeMap),
      );
      expect(
        snapshot.supportedNodeKinds,
        contains(AssistantPresentationNodeKind.comparisonTable),
      );
      expect(
        snapshot.supportedNodeKinds,
        contains(AssistantPresentationNodeKind.confirmationCard),
      );
      expect(
        snapshot.supportedNodeKinds,
        isNot(contains(AssistantPresentationNodeKind.media)),
      );
    },
  );

  test(
    'production DI treats no connectivity as offline and strips actions',
    () async {
      final telemetry = _telemetry(<ConnectivityResult>[
        ConnectivityResult.none,
      ]);
      await telemetry.initialize();
      addTearDown(telemetry.dispose);
      final container = ProviderContainer(
        overrides: [
          appTelemetryContextProvider.overrideWithValue(telemetry),
          platformTargetProvider.overrideWithValue(AppPlatform.android),
        ],
      );
      addTearDown(container.dispose);
      container
          .read(responsiveProvider.notifier)
          .updateFromSize(const Size(390, 844));

      final snapshot = container
          .read(assistantPresentationCapabilitySnapshotFactoryProvider)
          .call(AssistantPresentationSurfacePolicy.personal);

      expect(snapshot.offline, isTrue);
      expect(
        snapshot.viewportClass,
        AssistantPresentationViewportClass.compact,
      );
      expect(snapshot.platform, 'android');
      expect(
        snapshot.supportedNodeKinds,
        isNot(contains(AssistantPresentationNodeKind.confirmationCard)),
      );
    },
  );
}

AppTelemetryContextProvider _telemetry(List<ConnectivityResult> connectivity) {
  return AppTelemetryContextProvider(
    staticContextLoader: () async => const AppTelemetryStaticContext(
      deviceManufacturer: 'test',
      deviceModel: 'test',
      appVersion: 'test',
      devicePlatform: 'test',
    ),
    connectivityLoader: () async => connectivity,
    connectivityChanges: const Stream<List<ConnectivityResult>>.empty(),
  );
}
