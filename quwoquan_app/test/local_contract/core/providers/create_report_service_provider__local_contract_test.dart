import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/content/remote/report_command_remote.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';

void main() {
  for (final mode in AppDataSourceMode.values) {
    test(
      'production composition 在 ${mode.name} 模式仍只装配 Remote Report adapter',
      () {
        final container = ProviderContainer(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              () => _FixedModeNotifier(mode),
            ),
          ],
        );
        addTearDown(container.dispose);

        for (final provider in [
          homeFeedContentReportCommandWriterProvider,
          workBrowserContentReportCommandWriterProvider,
          userProfileContentReportCommandWriterProvider,
        ]) {
          expect(container.read(provider), isA<RemoteContentReportAdapter>());
        }
      },
    );
  }
}

final class _FixedModeNotifier extends AppDataSourceModeNotifier {
  _FixedModeNotifier(this.mode);

  final AppDataSourceMode mode;

  @override
  AppDataSourceMode build() => mode;
}
