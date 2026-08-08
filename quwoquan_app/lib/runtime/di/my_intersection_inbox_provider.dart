import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/cache/provider_cache.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/my_intersection_inbox_state.dart';

/// runtime/di 我的主页交集预览短时缓存窗口：卡片被长列表回收或 push 进入详情再返回会重建消费方，
/// 在窗口内复用已取结果，避免 `initState` 重打 `listMyIntersections`
/// （backlog R-ID09 验收项④）。
const Duration _myIntersectionPreviewCacheTtl = Duration(seconds: 90);

/// 预览缓存固定单键（无入参变体）；容器作用域，随 ProviderContainer 释放回收。
const String _myIntersectionPreviewCacheKey = 'fact';

/// 容器作用域预览缓存：autoDispose Notifier 重建时先查命中即复用，无定时器。
final _myIntersectionPreviewCacheProvider =
    Provider<TtlCache<List<IntersectionReason>>>(
      (ref) => TtlCache<List<IntersectionReason>>(),
    );

class MyIntersectionSummaryNotifier
    extends Notifier<MyIntersectionSummaryState> {
  @override
  MyIntersectionSummaryState build() => const MyIntersectionSummaryState();

  Future<void> load() async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, rawError: () => null);
    final repo = ref.read(intersectionRepositoryProvider);
    try {
      final summary = await repo.getMyIntersectionSummary();
      if (!ref.mounted) return;
      state = state.copyWith(summary: summary, isLoading: false);
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }
}

class MyIntersectionPreviewNotifier
    extends Notifier<MyIntersectionPreviewState> {
  DateTime? _loadedAt;

  @override
  MyIntersectionPreviewState build() {
    // 重建时优先复用容器作用域缓存：命中即直接呈现已取结果，initState 的 load 随后
    // 经 _loadedAt 守卫短路，避免长列表回收 / 路由往返触发重复 listMyIntersections。
    final hit = ref
        .read(_myIntersectionPreviewCacheProvider)
        .readFresh(
          _myIntersectionPreviewCacheKey,
          _myIntersectionPreviewCacheTtl,
        );
    if (hit != null) {
      _loadedAt = hit.storedAt;
      return MyIntersectionPreviewState(items: hit.value);
    }
    return const MyIntersectionPreviewState();
  }

  /// 加载主页交集预览。窗口内已有成功结果时直接复用，避免卡片重建重打服务；
  /// [force] 用于显式刷新（如下拉刷新）绕过去重。
  Future<void> load({bool force = false}) async {
    if (state.isLoading) return;
    final loadedAt = _loadedAt;
    if (!force &&
        loadedAt != null &&
        DateTime.now().difference(loadedAt) < _myIntersectionPreviewCacheTtl) {
      return;
    }
    state = state.copyWith(isLoading: true, rawError: () => null);
    final repo = ref.read(intersectionRepositoryProvider);
    try {
      final items = await repo.listMyIntersections(filter: 'fact');
      if (!ref.mounted) return;
      _loadedAt = DateTime.now();
      ref
          .read(_myIntersectionPreviewCacheProvider)
          .write(_myIntersectionPreviewCacheKey, items);
      state = state.copyWith(items: items, isLoading: false);
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }
}

class MyIntersectionListNotifier extends Notifier<MyIntersectionListState> {
  @override
  MyIntersectionListState build() => const MyIntersectionListState();

  /// 加载某维度（空 = 全部）列表，并立即推进已读水位以清零红点。
  Future<void> loadAndMarkVisited({
    String dimension = '',
    String filter = 'fact',
    String sourceRef = '',
    String timeBucket = '',
  }) async {
    state = state.copyWith(
      dimension: dimension,
      filter: filter,
      sourceRef: sourceRef,
      timeBucket: timeBucket,
      isLoading: true,
      rawError: () => null,
    );
    final repo = ref.read(intersectionRepositoryProvider);
    try {
      final items = await repo.listMyIntersections(
        dimension: dimension.isEmpty ? null : dimension,
        filter: filter.isEmpty ? null : filter,
        sourceRef: sourceRef.isEmpty ? null : sourceRef,
        timeBucket: timeBucket.isEmpty ? null : timeBucket,
      );
      if (!ref.mounted) return;
      state = state.copyWith(items: items, isLoading: false);
      // 清红点走 IntersectionVisitState typed 写面；失败不阻断列表展示，
      // 水位单调收敛下次进入可重放（降级容忍），异常经结构化遥测上报。
      try {
        await ref
            .read(intersectionVisitWriterProvider)
            .markIntersectionsVisited(
              dimension: dimension.isEmpty
                  ? null
                  : IntersectionDimension.fromWire(
                      dimension,
                      'MyIntersectionInbox.dimension',
                    ),
            );
        if (!ref.mounted) return;
        ref.read(myIntersectionSummaryProvider.notifier).load();
      } catch (visitError, stackTrace) {
        unawaited(
          ref
              .read(exceptionTelemetryPortProvider)
              .recordGlobalException(
                source: 'my_intersection_inbox.mark_visited',
                exceptionText: visitError.toString(),
                stackText: stackTrace.toString(),
              ),
        );
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }
}

final myIntersectionSummaryProvider =
    NotifierProvider.autoDispose<
      MyIntersectionSummaryNotifier,
      MyIntersectionSummaryState
    >(MyIntersectionSummaryNotifier.new);

final myIntersectionPreviewProvider =
    NotifierProvider.autoDispose<
      MyIntersectionPreviewNotifier,
      MyIntersectionPreviewState
    >(MyIntersectionPreviewNotifier.new);

final myIntersectionListProvider =
    NotifierProvider.autoDispose<
      MyIntersectionListNotifier,
      MyIntersectionListState
    >(MyIntersectionListNotifier.new);
