import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 已接受发布的进程内一致性信号。写侧只广播事实，发现流等读模型按需刷新；
/// 不允许发布页面反向 import 其他 UI 领域的 Provider。
final contentPublicationEpochProvider =
    NotifierProvider<ContentPublicationEpochNotifier, int>(
      ContentPublicationEpochNotifier.new,
    );

final class ContentPublicationEpochNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void notifyCommitted() {
    state += 1;
  }
}
