// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/filter_catalog_coordinator.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late FilterCatalogSlice validSnapshot;

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
    expect(resolved.cacheVerifiedAt, DateTime.utc(2026));
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

  final FilterCatalogSlice? snapshot;
  final Object? error;

  @override
  Future<FilterCatalogSlice> getActiveFilterCatalog() async {
    final failure = error;
    if (failure != null) throw failure;
    return snapshot!;
  }
}

final class _FakeBootstrap implements FilterCatalogBootstrapReader {
  const _FakeBootstrap({this.snapshot, this.error});

  final FilterCatalogSlice? snapshot;
  final Object? error;

  @override
  Future<FilterCatalogSlice> read() async {
    final failure = error;
    if (failure != null) throw failure;
    return snapshot!;
  }
}

final class _MemoryVerifiedStore implements VerifiedFilterCatalogStore {
  _MemoryVerifiedStore({FilterCatalogSlice? snapshot, this.failWrites = false})
    : _entry = snapshot == null
          ? null
          : VerifiedFilterCatalogCacheEntry(
              snapshot: snapshot,
              verifiedAt: DateTime.utc(2026),
            );

  VerifiedFilterCatalogCacheEntry? _entry;
  final bool failWrites;
  int clearCount = 0;

  FilterCatalogSlice? get snapshot => _entry?.snapshot;

  set snapshot(FilterCatalogSlice? value) {
    _entry = value == null
        ? null
        : VerifiedFilterCatalogCacheEntry(
            snapshot: value,
            verifiedAt: DateTime.utc(2026),
          );
  }

  @override
  Future<void> clear() async {
    clearCount += 1;
    _entry = null;
  }

  @override
  Future<VerifiedFilterCatalogCacheEntry?> read() async => _entry;

  @override
  Future<void> write(FilterCatalogSlice value) async {
    if (failWrites) throw StateError('cache unavailable');
    _entry = VerifiedFilterCatalogCacheEntry(
      snapshot: value,
      verifiedAt: DateTime.now().toUtc(),
    );
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
  void sourceSelected(ResolvedFilterCatalog resolved) {
    selected.add(resolved.source);
  }
}

FilterCatalogSlice _withDigest(
  FilterCatalogSlice source,
  String canonicalDigest,
) {
  return FilterCatalogSlice(
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
