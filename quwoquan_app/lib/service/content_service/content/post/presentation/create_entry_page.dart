import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_entry_sheet.dart';

typedef CreateEntrySelection =
    void Function(BuildContext navigationContext, EditorStartAction action);
typedef CreateEntryCrossObjectAction =
    Future<void> Function(BuildContext navigationContext);

/// Content-owned host for the create entry sheet.
///
/// Cross-object actions are injected by runtime composition. This keeps the
/// presentation owner independent from Circle/Chat implementation details and
/// leaves the router responsible only for typed navigation wiring.
class CreateEntryRouteHost extends StatelessWidget {
  const CreateEntryRouteHost({
    super.key,
    required this.onSelect,
    required this.onStartGathering,
    required this.onStartGroupChat,
  });

  final CreateEntrySelection onSelect;
  final CreateEntryCrossObjectAction onStartGathering;
  final CreateEntryCrossObjectAction onStartGroupChat;

  @override
  Widget build(BuildContext context) {
    return CreateEntrySheet(
      isOpen: true,
      onClose: () => context.pop(),
      onSelect: (action) => _select(context, action),
      onStartGathering: () => _runAfterEntryClosed(context, onStartGathering),
      onStartGroupChat: () => _runAfterEntryClosed(context, onStartGroupChat),
    );
  }

  void _select(BuildContext context, EditorStartAction action) {
    final navigationContext = _navigationContext(context);
    context.pop();
    if (navigationContext == null) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      onSelect(navigationContext, action);
    });
  }

  void _runAfterEntryClosed(
    BuildContext context,
    CreateEntryCrossObjectAction action,
  ) {
    final navigationContext = _navigationContext(context);
    context.pop();
    if (navigationContext == null) {
      return;
    }
    // Preserve the original same-stack continuation: the route-owned WidgetRef
    // remains valid while the content sheet is removed.
    unawaited(action(navigationContext));
  }

  BuildContext? _navigationContext(BuildContext context) {
    return GoRouter.of(context).routerDelegate.navigatorKey.currentContext;
  }
}
