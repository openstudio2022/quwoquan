// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/application/filter_catalog_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/filter_catalog_release/adapters/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/content_service/media/filter_catalog_release/filter_catalog_query_typed_double.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('FilterCatalogRelease typed contract', () {
    test('alpha fixture bundle exposes canonical active release', () async {
      final snapshot = await InMemoryFilterCatalogQuery()
          .getActiveFilterCatalog();

      expect(snapshot.releaseId, 'filter-catalog-20260720-001');
      expect(
        snapshot.canonicalDigest,
        '9ccd581f6ac73b1e8a623b345fc8b64605fc99b67d2c71017d4f18177cb70a0d',
      );
      expect(snapshot.status, FilterCatalogReleaseStatus.active);
      expect(snapshot.categoryCount, 10);
      expect(snapshot.presetCount, 85);
      expect(snapshot.categories, hasLength(snapshot.categoryCount));
      expect(snapshot.presets, hasLength(snapshot.presetCount));
    });

    test('remote success is verified and atomically cached', () async {
      final snapshot = await InMemoryFilterCatalogQuery()
          .getActiveFilterCatalog();
      final store = _MemoryVerifiedStore();
      final observer = _RecordingObserver();
      final result = await _coordinator(
        remote: InMemoryFilterCatalogQuery(snapshot: snapshot),
        store: store,
        bootstrap: _SnapshotBootstrap(snapshot),
        observer: observer,
      ).load();

      expect(result.source, FilterCatalogSource.remote);
      expect(result.snapshot.releaseId, snapshot.releaseId);
      expect(store.value?.canonicalDigest, snapshot.canonicalDigest);
      expect(observer.selected, <FilterCatalogSource>[
        FilterCatalogSource.remote,
      ]);
      expect(observer.rejected, isEmpty);
    });

    test('offline restart resolves verified cache before bootstrap', () async {
      final snapshot = await InMemoryFilterCatalogQuery()
          .getActiveFilterCatalog();
      final store = _MemoryVerifiedStore()..value = snapshot;
      final observer = _RecordingObserver();
      final result = await _coordinator(
        remote: const _ThrowingFilterCatalogQuery(),
        store: store,
        bootstrap: _SnapshotBootstrap(snapshot),
        observer: observer,
      ).load();

      expect(result.source, FilterCatalogSource.verifiedCache);
      expect(observer.rejected, <FilterCatalogSource>[
        FilterCatalogSource.remote,
      ]);
      expect(observer.selected, <FilterCatalogSource>[
        FilterCatalogSource.verifiedCache,
      ]);
    });

    test(
      'invalid cache is cleared and canonical bootstrap repairs it',
      () async {
        final snapshot = await InMemoryFilterCatalogQuery()
            .getActiveFilterCatalog();
        final store = _MemoryVerifiedStore()
          ..value = _withDigest(snapshot, List<String>.filled(64, '0').join());
        final observer = _RecordingObserver();
        final result = await _coordinator(
          remote: const _ThrowingFilterCatalogQuery(),
          store: store,
          bootstrap: _SnapshotBootstrap(snapshot),
          observer: observer,
        ).load();

        expect(result.source, FilterCatalogSource.bootstrapReplica);
        expect(store.clearCount, 1);
        expect(store.value?.canonicalDigest, snapshot.canonicalDigest);
        expect(observer.rejected, <FilterCatalogSource>[
          FilterCatalogSource.remote,
          FilterCatalogSource.verifiedCache,
        ]);
      },
    );

    test('all sources unavailable emits structured runtime failure', () async {
      final observer = _RecordingObserver();

      await expectLater(
        _coordinator(
          remote: const _ThrowingFilterCatalogQuery(),
          store: _MemoryVerifiedStore(),
          bootstrap: const _ThrowingBootstrap(),
          observer: observer,
        ).load(),
        throwsA(
          isA<RuntimeFailure>()
              .having(
                (failure) => failure.code,
                'code',
                'CONTENT.SYSTEM.filter_catalog_unavailable',
              )
              .having(
                (failure) => failure.kind,
                'kind',
                RuntimeFailureKind.unavailable,
              ),
        ),
      );
    });

    test(
      'SharedPreferences verified cache round-trips typed snapshot',
      () async {
        SharedPreferences.setMockInitialValues(<String, Object>{});
        final snapshot = await InMemoryFilterCatalogQuery()
            .getActiveFilterCatalog();
        const store = SharedPreferencesVerifiedFilterCatalogStore();

        await store.write(snapshot);
        final restored = await store.read();

        expect(restored?.snapshot.releaseId, snapshot.releaseId);
        expect(restored?.snapshot.canonicalDigest, snapshot.canonicalDigest);
        expect(restored?.snapshot.categoryCount, snapshot.categoryCount);
        expect(restored?.snapshot.presetCount, snapshot.presetCount);
        expect(restored?.verifiedAt, isNotNull);
      },
    );
  });
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

final class _MemoryVerifiedStore implements VerifiedFilterCatalogStore {
  VerifiedFilterCatalogCacheEntry? _entry;
  int clearCount = 0;

  FilterCatalogSlice? get value => _entry?.snapshot;

  set value(FilterCatalogSlice? snapshot) {
    _entry = snapshot == null
        ? null
        : VerifiedFilterCatalogCacheEntry(
            snapshot: snapshot,
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
  Future<void> write(FilterCatalogSlice snapshot) async {
    _entry = VerifiedFilterCatalogCacheEntry(
      snapshot: snapshot,
      verifiedAt: DateTime.now().toUtc(),
    );
  }
}

final class _SnapshotBootstrap implements FilterCatalogBootstrapReader {
  const _SnapshotBootstrap(this.snapshot);

  final FilterCatalogSlice snapshot;

  @override
  Future<FilterCatalogSlice> read() async => snapshot;
}

final class _ThrowingBootstrap implements FilterCatalogBootstrapReader {
  const _ThrowingBootstrap();

  @override
  Future<FilterCatalogSlice> read() {
    throw StateError('bootstrap unavailable');
  }
}

final class _ThrowingFilterCatalogQuery implements ContentFilterCatalogQuery {
  const _ThrowingFilterCatalogQuery();

  @override
  Future<FilterCatalogSlice> getActiveFilterCatalog() {
    throw StateError('remote unavailable');
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
