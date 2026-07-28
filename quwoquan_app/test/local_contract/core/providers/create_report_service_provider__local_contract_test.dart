import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/remote/report_command_remote.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void main() {
  test('production composition 只装配 Remote Report adapter', () {
    final container = ProviderContainer();
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
