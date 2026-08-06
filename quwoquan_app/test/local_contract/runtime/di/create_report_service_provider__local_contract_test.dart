import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

import '../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  test('production composition 只装配 Remote Report adapter', () {
    final container = ProviderContainer(
      overrides: generatedClientBoundaryOverrides(
        transport: MockClient(
          (_) async => throw StateError('unexpected report transport call'),
        ),
      ),
    );
    addTearDown(container.dispose);

    for (final provider in [
      homeFeedContentReportCommandWriterProvider,
      workBrowserContentReportCommandWriterProvider,
      userProfileContentReportCommandWriterProvider,
    ]) {
      expect(container.read(provider), isA<RemoteContentReportAdapter>());
    }
  });
}
