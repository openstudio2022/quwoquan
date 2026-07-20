import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/content/filter_catalog/filter_catalog_coordinator.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/infrastructure/local/content/filter_catalog/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FilterCatalogSnapshot validSnapshot;

  setUpAll(() async {
    validSnapshot = await const AssetFilterCatalogBootstrapReader().read();
  });

  test('bootstrap replica verifies the canonical cross-language digest', () {
    expect(
      const CanonicalFilterCatalogIntegrityVerifier().hasValidCanonicalDigest(
        validSnapshot,
      ),
      isTrue,
    );
    expect(validSnapshot.categoryCount, validSnapshot.categories.length);
    expect(validSnapshot.presetCount, validSnapshot.presets.length);
  });

  test('valid remote catalog wins and populates the verified cache', () async {
    final store = _MemoryVerifiedStore();
    final observer = _RecordingObserver();
    final coordinator = _coordinator(
      remote: _FakeRemote(snapshot: validSnapshot),
      store: store,
      bootstrap: _FakeBootstrap(snapshot: validSnapshot),
      observer: observer,
    );

    final resolved = await coordinator.load();

    expect(resolved.source, FilterCatalogSource.remote);
    expect(store.snapshot, same(validSnapshot));
    expect(observer.selected, <FilterCatalogSource>[
      FilterCatalogSource.remote,
    ]);
  });

  test(
    'cache persistence failure does not discard a valid remote catalog',
    () async {
      final observer = _RecordingObserver();
      final coordinator = _coordinator(
        remote: _FakeRemote(snapshot: validSnapshot),
        store: _MemoryVerifiedStore(failWrites: true),
        bootstrap: _FakeBootstrap(snapshot: validSnapshot),
        observer: observer,
      );

      final resolved = await coordinator.load();

      expect(resolved.source, FilterCatalogSource.remote);
      expect(observer.rejected, contains(FilterCatalogSource.verifiedCache));
    },
  );

  test('remote failure falls back to a digest-verified cache', () async {
    final observer = _RecordingObserver();
    final coordinator = _coordinator(
      remote: _FakeRemote(error: StateError('offline')),
      store: _MemoryVerifiedStore(snapshot: validSnapshot),
      bootstrap: _FakeBootstrap(error: StateError('must not be called')),
      observer: observer,
    );

    final resolved = await coordinator.load();

    expect(resolved.source, FilterCatalogSource.verifiedCache);
    expect(observer.selected, <FilterCatalogSource>[
      FilterCatalogSource.verifiedCache,
    ]);
  });

  test(
    'invalid cache is cleared before the bootstrap replica is selected',
    () async {
      final store = _MemoryVerifiedStore(
        snapshot: _withDigest(
          validSnapshot,
          '0000000000000000000000000000000000000000000000000000000000000000',
        ),
      );
      final observer = _RecordingObserver();
      final coordinator = _coordinator(
        remote: _FakeRemote(error: StateError('offline')),
        store: store,
        bootstrap: _FakeBootstrap(snapshot: validSnapshot),
        observer: observer,
      );

      final resolved = await coordinator.load();

      expect(resolved.source, FilterCatalogSource.bootstrapReplica);
      expect(store.clearCount, 1);
      expect(store.snapshot, same(validSnapshot));
    },
  );

  test(
    'all invalid candidates fail with the canonical runtime error',
    () async {
      final coordinator = _coordinator(
        remote: _FakeRemote(error: StateError('offline')),
        store: _MemoryVerifiedStore(),
        bootstrap: _FakeBootstrap(error: const FormatException('invalid')),
        observer: _RecordingObserver(),
      );

      await expectLater(
        coordinator.load(),
        throwsA(
          isA<RuntimeFailure>()
              .having(
                (failure) => failure.code,
                'code',
                ContentErrorCode.filterCatalogUnavailable.code,
              )
              .having(
                (failure) => failure.recovery.action,
                'recovery.action',
                ContentErrorCode.filterCatalogUnavailable.recoveryAction,
              ),
        ),
      );
    },
  );
}

FilterCatalogCoordinator _coordinator({
  required ContentFilterCatalogQuery remote,
  required VerifiedFilterCatalogStore store,
  required FilterCatalogBootstrapReader bootstrap,
  required FilterCatalogResolutionObserver observer,
}) {
  return FilterCatalogCoordinator(
    remote: remote,
    verifiedStore: store,
    bootstrapReader: bootstrap,
    integrityVerifier: const CanonicalFilterCatalogIntegrityVerifier(),
    observer: observer,
  );
}

final class _FakeRemote implements ContentFilterCatalogQuery {
  const _FakeRemote({this.snapshot, this.error});

  final FilterCatalogSnapshot? snapshot;
  final Object? error;

  @override
  Future<FilterCatalogSnapshot> getActiveFilterCatalog() async {
    final failure = error;
    if (failure != null) throw failure;
    return snapshot!;
  }
}

final class _FakeBootstrap implements FilterCatalogBootstrapReader {
  const _FakeBootstrap({this.snapshot, this.error});

  final FilterCatalogSnapshot? snapshot;
  final Object? error;

  @override
  Future<FilterCatalogSnapshot> read() async {
    final failure = error;
    if (failure != null) throw failure;
    return snapshot!;
  }
}

final class _MemoryVerifiedStore implements VerifiedFilterCatalogStore {
  _MemoryVerifiedStore({this.snapshot, this.failWrites = false});

  FilterCatalogSnapshot? snapshot;
  final bool failWrites;
  int clearCount = 0;

  @override
  Future<void> clear() async {
    clearCount += 1;
    snapshot = null;
  }

  @override
  Future<FilterCatalogSnapshot?> read() async => snapshot;

  @override
  Future<void> write(FilterCatalogSnapshot value) async {
    if (failWrites) throw StateError('cache unavailable');
    snapshot = value;
  }
}

final class _RecordingObserver implements FilterCatalogResolutionObserver {
  final List<FilterCatalogSource> selected = <FilterCatalogSource>[];
  final List<FilterCatalogSource> rejected = <FilterCatalogSource>[];

  @override
  void candidateRejected(FilterCatalogSource source, Object error) {
    rejected.add(source);
  }

  @override
  void sourceSelected(FilterCatalogSource source, String releaseId) {
    selected.add(source);
  }
}

FilterCatalogSnapshot _withDigest(
  FilterCatalogSnapshot source,
  String canonicalDigest,
) {
  return FilterCatalogSnapshot(
    releaseId: source.releaseId,
    canonicalDigest: canonicalDigest,
    status: source.status,
    categoryCount: source.categoryCount,
    presetCount: source.presetCount,
    categories: source.categories,
    presets: source.presets,
    recommendedFallbackPresetIds: source.recommendedFallbackPresetIds,
    importedAt: source.importedAt,
    activatedAt: source.activatedAt,
  );
}
