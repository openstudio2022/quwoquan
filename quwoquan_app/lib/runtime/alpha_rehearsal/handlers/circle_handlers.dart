import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/circle_core_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/circle_membership_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/gathering_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';

final class CircleRehearsalHandler implements RehearsalObjectHandler {
  const CircleRehearsalHandler();
  @override
  Future<Object?> handle(RehearsalInvocation invocation) {
    final id = invocation.operation.canonicalOperationId;
    if (id.startsWith('circle.gathering'))
      return const GatheringRehearsalHandler().handle(invocation);
    if (id.startsWith('circle.circle_group') ||
        id.startsWith('circle.circle_membership') ||
        id.startsWith('circle.circle_post_placement'))
      return const CircleMembershipRehearsalHandler().handle(invocation);
    return const CircleCoreRehearsalHandler().handle(invocation);
  }

  @override
  Stream<Object?>? stream(RehearsalInvocation invocation) => null;
}
