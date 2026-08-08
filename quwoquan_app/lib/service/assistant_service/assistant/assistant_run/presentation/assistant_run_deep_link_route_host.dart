import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/personal_assistant_stream_controller.dart';

/// Assistant-owned route host that opens the run identified by an App message.
///
/// Navigation only supplies the canonical [runId] and the already composed
/// assistant page. The object presentation owns the run-open lifecycle so the
/// application call cannot leak into the runtime navigation composition root.
class AssistantRunDeepLinkRouteHost extends ConsumerStatefulWidget {
  const AssistantRunDeepLinkRouteHost({
    super.key,
    required this.runId,
    required this.child,
  });

  final String runId;
  final Widget child;

  @override
  ConsumerState<AssistantRunDeepLinkRouteHost> createState() =>
      _AssistantRunDeepLinkRouteHostState();
}

class _AssistantRunDeepLinkRouteHostState
    extends ConsumerState<AssistantRunDeepLinkRouteHost> {
  String _scheduledRunId = '';

  @override
  void initState() {
    super.initState();
    _scheduleRunOpen();
  }

  @override
  void didUpdateWidget(covariant AssistantRunDeepLinkRouteHost oldWidget) {
    super.didUpdateWidget(oldWidget);
    _scheduleRunOpen();
  }

  void _scheduleRunOpen() {
    final runId = widget.runId.trim();
    if (runId.isEmpty || runId == _scheduledRunId) {
      return;
    }
    _scheduledRunId = runId;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.runId.trim() != runId) {
        return;
      }
      unawaited(
        ref
            .read(personalAssistantStreamControllerProvider.notifier)
            .openRunFromAppMessage(runId),
      );
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
