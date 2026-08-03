import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum FilterCatalogSource { remote, verifiedCache, bootstrapReplica }

final class ResolvedFilterCatalog {
  const ResolvedFilterCatalog({
    required this.snapshot,
    required this.source,
    this.cacheVerifiedAt,
  });

  final FilterCatalogSlice snapshot;
  final FilterCatalogSource source;
  final DateTime? cacheVerifiedAt;
}

final class VerifiedFilterCatalogCacheEntry {
  const VerifiedFilterCatalogCacheEntry({
    required this.snapshot,
    required this.verifiedAt,
  });

  final FilterCatalogSlice snapshot;
  final DateTime verifiedAt;
}

abstract interface class VerifiedFilterCatalogStore {
  Future<VerifiedFilterCatalogCacheEntry?> read();

  Future<void> write(FilterCatalogSlice snapshot);

  Future<void> clear();
}

abstract interface class FilterCatalogBootstrapReader {
  Future<FilterCatalogSlice> read();
}

abstract interface class FilterCatalogIntegrityVerifier {
  bool hasValidCanonicalDigest(FilterCatalogSlice snapshot);
}

abstract interface class FilterCatalogResolutionObserver {
  void sourceSelected(ResolvedFilterCatalog resolved);

  void candidateRejected(FilterCatalogSource source, Object error);
}

final class FilterCatalogCoordinator {
  const FilterCatalogCoordinator({
    required this.remote,
    required this.verifiedStore,
    required this.bootstrapReader,
    required this.integrityVerifier,
    required this.observer,
  });

  final ContentFilterCatalogQuery remote;
  final VerifiedFilterCatalogStore verifiedStore;
  final FilterCatalogBootstrapReader bootstrapReader;
  final FilterCatalogIntegrityVerifier integrityVerifier;
  final FilterCatalogResolutionObserver observer;

  Future<ResolvedFilterCatalog> load() async {
    try {
      final snapshot = await remote.getActiveFilterCatalog();
      _validate(snapshot);
      await _writeVerifiedBestEffort(snapshot);
      final resolved = ResolvedFilterCatalog(
        snapshot: snapshot,
        source: FilterCatalogSource.remote,
      );
      observer.sourceSelected(resolved);
      return resolved;
    } catch (error) {
      observer.candidateRejected(FilterCatalogSource.remote, error);
    }

    try {
      final cachedEntry = await verifiedStore.read();
      if (cachedEntry != null) {
        _validate(cachedEntry.snapshot);
        final resolved = ResolvedFilterCatalog(
          snapshot: cachedEntry.snapshot,
          source: FilterCatalogSource.verifiedCache,
          cacheVerifiedAt: cachedEntry.verifiedAt,
        );
        observer.sourceSelected(resolved);
        return resolved;
      }
    } catch (error) {
      observer.candidateRejected(FilterCatalogSource.verifiedCache, error);
      await _clearInvalidCache();
    }

    try {
      final bootstrap = await bootstrapReader.read();
      _validate(bootstrap);
      await _writeVerifiedBestEffort(bootstrap);
      final resolved = ResolvedFilterCatalog(
        snapshot: bootstrap,
        source: FilterCatalogSource.bootstrapReplica,
      );
      observer.sourceSelected(resolved);
      return resolved;
    } catch (error) {
      observer.candidateRejected(FilterCatalogSource.bootstrapReplica, error);
    }

    throw _filterCatalogUnavailableFailure();
  }

  Future<void> _writeVerifiedBestEffort(FilterCatalogSlice snapshot) async {
    try {
      await verifiedStore.write(snapshot);
    } catch (error) {
      observer.candidateRejected(FilterCatalogSource.verifiedCache, error);
    }
  }

  Future<void> _clearInvalidCache() async {
    try {
      await verifiedStore.clear();
    } catch (error) {
      observer.candidateRejected(FilterCatalogSource.verifiedCache, error);
    }
  }

  void _validate(FilterCatalogSlice snapshot) {
    if (snapshot.releaseId.trim().isEmpty ||
        snapshot.status != FilterCatalogReleaseStatus.active ||
        !RegExp(r'^[0-9a-f]{64}$').hasMatch(snapshot.canonicalDigest) ||
        snapshot.categoryCount != snapshot.categories.length ||
        snapshot.presetCount != snapshot.presets.length ||
        snapshot.categories.isEmpty ||
        snapshot.categories.length > 32 ||
        snapshot.presets.isEmpty ||
        snapshot.presets.length > 256) {
      throw const FormatException('invalid FilterCatalogSlice envelope');
    }

    final categories = <String, FilterCategoryDefinition>{};
    final categorySorts = <int>{};
    for (final category in snapshot.categories) {
      if (category.categoryId.trim().isEmpty ||
          category.displayNameZhHans.trim().isEmpty ||
          !categorySorts.add(category.sort) ||
          categories.containsKey(category.categoryId)) {
        throw const FormatException('invalid filter catalog category');
      }
      categories[category.categoryId] = category;
    }

    FilterPresetDefinition? original;
    final presetIds = <String>{};
    final presetSorts = <String, Set<int>>{};
    for (final preset in snapshot.presets) {
      final category = categories[preset.categoryId];
      final adjustmentValues = <double>[
        preset.adjustments.lightSense,
        preset.adjustments.brightness,
        preset.adjustments.exposure,
        preset.adjustments.contrast,
        preset.adjustments.saturation,
        preset.adjustments.vibrance,
        preset.adjustments.texture,
        preset.adjustments.sharpen,
        preset.adjustments.structure,
        preset.adjustments.highlight,
        preset.adjustments.shadow,
        preset.adjustments.temperature,
        preset.adjustments.tint,
        preset.adjustments.grain,
        preset.adjustments.fade,
      ];
      if (preset.presetId.trim().isEmpty ||
          preset.displayNameZhHans.trim().isEmpty ||
          !presetIds.add(preset.presetId) ||
          category == null ||
          preset.enabled && !category.enabled ||
          preset.defaultStrength < 0 ||
          preset.defaultStrength > 100 ||
          adjustmentValues.any(
            (value) => !value.isFinite || value < -100 || value > 100,
          ) ||
          !(presetSorts[preset.categoryId] ??= <int>{}).add(preset.sort)) {
        throw const FormatException('invalid filter catalog preset');
      }
      if (preset.presetId == 'original') original = preset;
    }

    if (original == null ||
        !original.enabled ||
        original.defaultStrength != 0 ||
        !_isIdentityAdjustments(original.adjustments) ||
        snapshot.recommendedFallbackPresetIds.toSet().length !=
            snapshot.recommendedFallbackPresetIds.length ||
        !snapshot.recommendedFallbackPresetIds.every(presetIds.contains) ||
        !integrityVerifier.hasValidCanonicalDigest(snapshot)) {
      throw const FormatException('filter catalog invariant mismatch');
    }
  }
}

bool _isIdentityAdjustments(FilterAdjustmentValues values) =>
    values.lightSense == 0 &&
    values.brightness == 0 &&
    values.exposure == 0 &&
    values.contrast == 0 &&
    values.saturation == 0 &&
    values.vibrance == 0 &&
    values.texture == 0 &&
    values.sharpen == 0 &&
    values.structure == 0 &&
    values.highlight == 0 &&
    values.shadow == 0 &&
    values.temperature == 0 &&
    values.tint == 0 &&
    values.grain == 0 &&
    values.fade == 0;

RuntimeFailure _filterCatalogUnavailableFailure() {
  final error = ContentErrorCode.filterCatalogUnavailable;
  return RuntimeFailure(
    code: error.code,
    transportStatus: error.httpStatus,
    origin: RuntimeFailureOrigin.localClient,
    kind: RuntimeFailureKind.unavailable,
    nature: RuntimeFailureNature.transient,
    location: const RuntimeFailureLocation(
      businessObject: 'content.filter_catalog_release',
      functionModule: 'filter_catalog_coordinator',
    ),
    context: const RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(
          key: 'operation',
          value: AppCloudOperationIds
              .contentFilterCatalogReleaseGetActiveFilterCatalog,
        ),
        RuntimeContextAttribute(
          key: 'source',
          value: 'remote_verified_cache_bootstrap',
        ),
      ],
    ),
    recovery: RuntimeRecoveryDirective(
      action: error.recoveryAction,
      afterSeconds: error.recoveryAfterSeconds,
      disruptionLevel: 'fullPage',
    ),
  );
}
