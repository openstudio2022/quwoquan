import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/location_query_remote.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void main() {
  test('production composition 只装配 Remote Location adapter', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    expect(
      container.read(createLocationNearbyReaderProvider),
      isA<RemoteLocationQueryAdapter>(),
    );
    expect(
      container.read(createLocationSearchReaderProvider),
      isA<RemoteLocationQueryAdapter>(),
    );
    expect(
      container.read(createLocationCoordinatorProvider),
      isA<CreateLocationCoordinator>(),
    );
  });
}
