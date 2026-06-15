part of 'app_providers.dart';

final footprintRepositoryProvider = Provider<FootprintRepository>(
  (ref) => cloudRepositoryImplForMode(
    ref.watch(appDataSourceModeProvider),
    remote: () => RemoteFootprintRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
    mock: MockFootprintRepository.new,
  ),
);
