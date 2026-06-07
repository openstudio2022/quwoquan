import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';

void main() {
  test('mock mode uses idle/active without remote transport', () {
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(
          () => _FixedModeNotifier(AppDataSourceMode.mock),
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(realtimeConnectionManagerProvider.notifier);
    notifier.onAppForeground();
    expect(container.read(realtimeConnectionManagerProvider), TransportState.idle);

    notifier.onEnterChatDetail('conv_001');
    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.active,
    );
  });

  test('switching app data source mode recreates delegate state', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.mock);

    final notifier = container.read(realtimeConnectionManagerProvider.notifier);
    notifier.onAppForeground();
    notifier.onEnterChatDetail('conv_001');
    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.active,
    );

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);

    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.disconnected,
    );
  });

  test('mode switch tears down active mock delegate before delayed push arrives', () async {
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(
          () => _FixedModeNotifier(AppDataSourceMode.mock),
        ),
      ],
    );
    addTearDown(container.dispose);

    final notifier = container.read(realtimeConnectionManagerProvider.notifier);
    notifier.onAppForeground();
    notifier.onEnterChatDetail('conv_001');

    expect(container.read(realtimeConnectionManagerProvider), TransportState.active);
    final beforeCount =
        container.read(chatMessageProvider('conv_001')).messages.length;

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);

    expect(
      container.read(realtimeConnectionManagerProvider),
      TransportState.disconnected,
    );

    await Future<void>.delayed(const Duration(milliseconds: 450));

    final afterCount =
        container.read(chatMessageProvider('conv_001')).messages.length;
    expect(afterCount, beforeCount);
  });
}

class _FixedModeNotifier extends AppDataSourceModeNotifier {
  _FixedModeNotifier(this.mode);

  final AppDataSourceMode mode;

  @override
  AppDataSourceMode build() => mode;
}
