part of 'app_router.dart';

/// 创作入口抽屉的独立路由页（避免在 Shell 内 setState 导致 build scope 断言）
class _CreateEntryRoutePage extends ConsumerWidget {
  const _CreateEntryRoutePage();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return CreateEntrySheet(
      isOpen: true,
      onClose: () => context.pop(),
      onSelect: (EditorStartAction action) {
        final router = GoRouter.of(context);
        context.pop();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          router.go(AppRoutePaths.create(type: action.name));
        });
      },
      onStartGathering: () => _runAfterEntryClosed(
        context,
        (navContext) =>
            GlobalQuickActionSheet.openGatedStartGathering(navContext, ref),
      ),
      onStartGroupChat: () => _runAfterEntryClosed(
        context,
        (navContext) =>
            GlobalQuickActionSheet.openGatedStartGroupChat(navContext, ref),
      ),
    );
  }

  void _runAfterEntryClosed(
    BuildContext context,
    Future<void> Function(BuildContext navContext) action,
  ) {
    final router = GoRouter.of(context);
    final navContext = router.routerDelegate.navigatorKey.currentContext;
    context.pop();
    if (navContext == null) {
      return;
    }
    // 先关闭入口，再在同一事件栈内读取 route page 的 WidgetRef 并登记 gate /
    // continuation；避免等到下一帧页面已销毁后再访问 ref。
    unawaited(action(navContext));
  }
}
