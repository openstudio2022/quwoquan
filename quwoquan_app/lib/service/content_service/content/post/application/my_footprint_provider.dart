import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/footprint_repository.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

/// 「我的足迹」列表状态（只读：type 过滤 + cursor 分页）。
class MyFootprintListState {
  const MyFootprintListState({
    this.items = const <FootprintEntry>[],
    this.isLoading = false,
    this.rawError,
    this.nextCursor,
    this.type = '',
  });

  final List<FootprintEntry> items;
  final bool isLoading;
  final Object? rawError;
  final String? nextCursor;
  final String type;

  bool get hasMore => nextCursor != null && nextCursor!.isNotEmpty;

  MyFootprintListState copyWith({
    List<FootprintEntry>? items,
    bool? isLoading,
    Object? rawError,
    bool clearError = false,
    String? nextCursor,
    bool clearCursor = false,
    String? type,
  }) {
    return MyFootprintListState(
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      rawError: clearError ? null : (rawError ?? this.rawError),
      nextCursor: clearCursor ? null : (nextCursor ?? this.nextCursor),
      type: type ?? this.type,
    );
  }
}

class MyFootprintListNotifier extends Notifier<MyFootprintListState> {
  @override
  MyFootprintListState build() => const MyFootprintListState();

  Future<void> load({String type = ''}) async {
    state = MyFootprintListState(isLoading: true, type: type);
    try {
      final page = await ref
          .read(footprintRepositoryProvider)
          .getMyFootprint(type: type.isEmpty ? null : type);
      state = MyFootprintListState(
        items: page.items,
        nextCursor: page.nextCursor,
        type: type,
      );
    } catch (e) {
      // 错误进入页面级错误态（结构化 runtime failure 由页面 resolve）。
      state = MyFootprintListState(rawError: e, type: type);
    }
  }

  Future<void> loadMore() async {
    if (state.isLoading || !state.hasMore) return;
    state = state.copyWith(isLoading: true);
    try {
      final page = await ref
          .read(footprintRepositoryProvider)
          .getMyFootprint(
            type: state.type.isEmpty ? null : state.type,
            cursor: state.nextCursor,
          );
      state = state.copyWith(
        items: <FootprintEntry>[...state.items, ...page.items],
        isLoading: false,
        nextCursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
        clearError: true,
      );
    } catch (e) {
      // 加载更多失败保留已加载内容，错误态由页面提示重试。
      state = state.copyWith(isLoading: false, rawError: e);
    }
  }
}

final myFootprintListProvider =
    NotifierProvider<MyFootprintListNotifier, MyFootprintListState>(
      MyFootprintListNotifier.new,
    );
