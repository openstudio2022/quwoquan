import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_page_remote_helpers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// UI composition bridge. Pure payload/media preparation deliberately lives
/// outside this file so its contract tests do not load the application root.
Future<void> reportCreateEditorSurfaceEvent(
  WidgetRef ref,
  String event, [
  Map<String, Object?> extras = const {},
  String surfaceId = 'create_editor',
]) async {
  try {
    final row = <String, Object?>{
      'event': event,
      'surface': surfaceId,
      'timestamp': DateTime.now().toIso8601String(),
      ...extras,
    };
    await ref
        .read(contentEngagementRepositoryProvider)
        .reportBehaviors(
          events: <ContentBehaviorBatchEventDto>[
            ContentBehaviorBatchEventDto.fromMap(
              Map<String, dynamic>.from(row),
            ),
          ],
        );
  } catch (error, stackTrace) {
    developer.log(
      'reportCreateEditorSurfaceEvent failed: event=$event',
      name: 'CreateEditor',
      error: error,
      stackTrace: stackTrace,
    );
  }
}

Future<CreateContentPostCommand> attachActivePersonaToCreateCommand(
  WidgetRef ref,
  Map<String, Object?> payload,
) async {
  final activeContext = await ref.read(activePersonaContextProvider.future);
  if (ref
          .read(contentConfigRepositoryProvider)
          .requiresResolvedPersonaForMutations &&
      activeContext.isFallback) {
    throw StateError('active persona context unavailable');
  }
  final personaVersion = int.tryParse(activeContext.personaContextVersion);
  return createContentPostCommandFromPreparedPayload(
    payload,
    authorDisplayNameSnapshot: activeContext.displayName,
    authorAvatarUrlSnapshot: activeContext.avatarUrl,
    personaContextVersion: personaVersion,
  );
}
