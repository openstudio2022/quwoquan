import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/plaza/widgets/connection_state_views.dart';

/// 连接列表四态分发器：把 [AsyncValue] 列表映射为 加载/空/错/数据 四态。
///
/// 同频连接中心四 tab 与三个独立页（附近/结伴/局）共用，避免每处重复写
/// `async.when` 与四态分支。本组件只接收已 `watch` 好的 [AsyncValue]，自身
/// 不读 Provider，便于在不同页面以不同 Provider 复用与测试。
class ConnectionListSection<T> extends StatelessWidget {
  const ConnectionListSection({
    super.key,
    required this.async,
    required this.itemBuilder,
    required this.emptyTitle,
    required this.emptySubtitle,
    required this.onRetry,
    this.emptyIcon = CupertinoIcons.sparkles,
    this.header,
  });

  final AsyncValue<List<T>> async;
  final Widget Function(BuildContext context, T item) itemBuilder;
  final String emptyTitle;
  final String emptySubtitle;
  final VoidCallback onRetry;
  final IconData emptyIcon;

  /// 列表顶部可选说明条（如附近的「模糊位置」提示）。
  final Widget? header;

  @override
  Widget build(BuildContext context) {
    return async.when(
      loading: () => const ConnectionLoadingView(),
      error: (_, _) => ConnectionErrorView(onRetry: onRetry),
      data: (items) {
        if (items.isEmpty) {
          return ConnectionEmptyView(
            title: emptyTitle,
            subtitle: emptySubtitle,
            icon: emptyIcon,
          );
        }
        final hasHeader = header != null;
        final count = items.length + (hasHeader ? 1 : 0);
        return ListView.separated(
          padding: EdgeInsets.all(AppSpacing.md),
          itemCount: count,
          separatorBuilder: (_, _) => SizedBox(height: AppSpacing.md),
          itemBuilder: (ctx, index) {
            if (hasHeader && index == 0) {
              return header!;
            }
            final item = items[index - (hasHeader ? 1 : 0)];
            return itemBuilder(ctx, item);
          },
        );
      },
    );
  }
}
