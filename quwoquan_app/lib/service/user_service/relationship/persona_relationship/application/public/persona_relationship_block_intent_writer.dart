import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef PersonaRelationshipIdempotencyKeyFactory = String Function();

/// Binds one block/unblock user intent to transport idempotency metadata.
///
/// The generated command intentionally contains only business fields. The
/// stable retry identity belongs to the invocation context and must never be
/// copied into the wire body.
abstract interface class PersonaRelationshipBlockIntentCommandWriter {
  Future<BlockCommandResult> blockUserWithIntent(
    BlockUserCommand command, {
    required String idempotencyKey,
  });

  Future<BlockCommandResult> unblockUserWithIntent(
    UnblockUserCommand command, {
    required String idempotencyKey,
  });
}
