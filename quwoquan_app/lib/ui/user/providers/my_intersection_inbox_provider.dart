import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 「我的交集」聚合摘要状态：总数 + 各维度计数 / 未读新增。
class MyIntersectionSummaryState {
  final IntersectionInboxSummary? summary;
  final bool isLoading;
  final Object? rawError;

  const MyIntersectionSummaryState({
    this.summary,
    this.isLoading = false,
    this.rawError,
  });

  bool get hasNew => (summary?.totalNewCount ?? 0) > 0;
  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  MyIntersectionSummaryState copyWith({
    IntersectionInboxSummary? summary,
    bool? isLoading,
    Object? Function()? rawError,
  }) {
    return MyIntersectionSummaryState(
      summary: summary ?? this.summary,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}

class MyIntersectionSummaryNotifier
    extends Notifier<MyIntersectionSummaryState> {
  @override
  MyIntersectionSummaryState build() => const MyIntersectionSummaryState();

  Future<void> load() async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, rawError: () => null);
    try {
      final summary = await ref
          .read(intersectionRepositoryProvider)
          .getMyIntersectionSummary();
      if (!ref.mounted) return;
      state = state.copyWith(summary: summary, isLoading: false);
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }
}

/// 「我的交集」分维度列表状态：自上次查看新增在前；打开即推进已读水位清零。
class MyIntersectionListState {
  final String dimension;
  final List<IntersectionReason> items;
  final bool isLoading;
  final Object? rawError;

  const MyIntersectionListState({
    this.dimension = '',
    this.items = const <IntersectionReason>[],
    this.isLoading = false,
    this.rawError,
  });

  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  MyIntersectionListState copyWith({
    String? dimension,
    List<IntersectionReason>? items,
    bool? isLoading,
    Object? Function()? rawError,
  }) {
    return MyIntersectionListState(
      dimension: dimension ?? this.dimension,
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}

class MyIntersectionListNotifier extends Notifier<MyIntersectionListState> {
  @override
  MyIntersectionListState build() => const MyIntersectionListState();

  /// 加载某维度（空 = 全部）列表，并立即推进已读水位以清零红点。
  Future<void> loadAndMarkVisited({String dimension = ''}) async {
    state = state.copyWith(
      dimension: dimension,
      isLoading: true,
      rawError: () => null,
    );
    final repo = ref.read(intersectionRepositoryProvider);
    try {
      final items = await repo.listMyIntersections(
        dimension: dimension.isEmpty ? null : dimension,
      );
      if (!ref.mounted) return;
      state = state.copyWith(items: items, isLoading: false);
      await repo.markIntersectionsVisited(
        dimension: dimension.isEmpty ? null : dimension,
      );
      if (!ref.mounted) return;
      ref.read(myIntersectionSummaryProvider.notifier).load();
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

final myIntersectionListProvider =
    NotifierProvider.autoDispose<
      MyIntersectionListNotifier,
      MyIntersectionListState
    >(MyIntersectionListNotifier.new);
