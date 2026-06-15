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
        context.pop();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!context.mounted) {
            return;
          }
          context.go(AppRoutePaths.create(type: action.name));
        });
      },
      onContinueFromDraft: () {
        final router = GoRouter.of(context);
        context.pop();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          final navContext = router.routerDelegate.navigatorKey.currentContext;
          if (navContext != null) {
            unawaited(presentCreateDraftPickerAndGo(navContext, router));
          }
        });
      },
      onCreateCircle: () {
        context.pop();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!context.mounted) {
            return;
          }
          GlobalQuickActionSheet.openCreateCircle(context);
        });
      },
    );
  }
}
