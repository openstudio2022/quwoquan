import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/persona_relationship_block_intent_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

typedef PersonaRelationshipInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// PersonaRelationship 拉黑命令与列表查询的 production Remote adapter。
/// path/auth/retry/idempotency/decoder 全部由 generated client 承担。
final class RemotePersonaRelationshipFacet
    implements
        BlockCommandWriter,
        BlockedListQuery,
        RelationshipCapabilityQuery,
        PersonaRelationshipBlockIntentCommandWriter {
  RemotePersonaRelationshipFacet({
    required this.client,
    required this.invocationContext,
    PersonaRelationshipIdempotencyKeyFactory? idempotencyKeyFactory,
  }) : _idempotencyKeyFactory = idempotencyKeyFactory ?? const Uuid().v4;

  final GeneratedCloudOperationClient client;
  final PersonaRelationshipInvocationContextFactory invocationContext;
  final PersonaRelationshipIdempotencyKeyFactory _idempotencyKeyFactory;
  final Map<String, String> _pendingCommandIntentKeys = <String, String>{};

  static const int _maxRetainedCommandIntents = 8;

  @override
  Future<BlockCommandResult> blockUser(BlockUserCommand command) {
    return _runStableCommandIntent(
      canonicalOperationId:
          AppCloudOperationIds.userPersonaRelationshipBlockUser,
      clientPageId: UserRequestPageIds.blockUser,
      targetPersonaId: command.targetPersonaId,
      expectedBlocked: true,
      send: (idempotencyKey, baseContext) => _sendBlockUser(
        command,
        idempotencyKey: idempotencyKey,
        baseContext: baseContext,
      ),
    );
  }

  @override
  Future<BlockCommandResult> blockUserWithIntent(
    BlockUserCommand command, {
    required String idempotencyKey,
  }) async {
    final normalizedKey = _normalizeIdempotencyKey(idempotencyKey);
    return _sendBlockUser(
      command,
      idempotencyKey: normalizedKey,
      baseContext: invocationContext(UserRequestPageIds.blockUser),
    );
  }

  Future<BlockCommandResult> _sendBlockUser(
    BlockUserCommand command, {
    required String idempotencyKey,
    required CloudOperationInvocationContext baseContext,
  }) async {
    final result = await client.userPersonaRelationshipBlockUser(
      command,
      context: _commandContext(baseContext, idempotencyKey),
    );
    return _validateCommandResult(
      result,
      targetPersonaId: command.targetPersonaId,
      expectedBlocked: true,
      operation: 'BlockUser',
    );
  }

  @override
  Future<BlockCommandResult> unblockUser(UnblockUserCommand command) {
    return _runStableCommandIntent(
      canonicalOperationId:
          AppCloudOperationIds.userPersonaRelationshipUnblockUser,
      clientPageId: UserRequestPageIds.unblockUser,
      targetPersonaId: command.targetPersonaId,
      expectedBlocked: false,
      send: (idempotencyKey, baseContext) => _sendUnblockUser(
        command,
        idempotencyKey: idempotencyKey,
        baseContext: baseContext,
      ),
    );
  }

  @override
  Future<BlockCommandResult> unblockUserWithIntent(
    UnblockUserCommand command, {
    required String idempotencyKey,
  }) async {
    final normalizedKey = _normalizeIdempotencyKey(idempotencyKey);
    return _sendUnblockUser(
      command,
      idempotencyKey: normalizedKey,
      baseContext: invocationContext(UserRequestPageIds.unblockUser),
    );
  }

  Future<BlockCommandResult> _sendUnblockUser(
    UnblockUserCommand command, {
    required String idempotencyKey,
    required CloudOperationInvocationContext baseContext,
  }) async {
    final result = await client.userPersonaRelationshipUnblockUser(
      command,
      context: _commandContext(baseContext, idempotencyKey),
    );
    return _validateCommandResult(
      result,
      targetPersonaId: command.targetPersonaId,
      expectedBlocked: false,
      operation: 'UnblockUser',
    );
  }

  @override
  Future<BlockedUserSlice> listBlockedUsers(ListBlockedUsersQuery query) async {
    final result = await client.userPersonaRelationshipListBlockedUsers(
      query,
      context: invocationContext(UserRequestPageIds.listBlockedUsers),
    );
    final seenTargets = <String>{};
    for (final item in result.items) {
      final targetPersonaId = item.targetPersonaId.trim();
      if (targetPersonaId.isEmpty ||
          item.displayName.trim().isEmpty ||
          item.userHandle.trim().isEmpty ||
          !seenTargets.add(targetPersonaId)) {
        throw CloudErrorMapper.invalidResponse(
          message: 'ListBlockedUsers returned an invalid typed item',
          functionModule: 'persona_relationship_remote',
        );
      }
    }
    if (result.nextCursor != null && result.nextCursor!.trim().isEmpty) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ListBlockedUsers returned a blank next cursor',
        functionModule: 'persona_relationship_remote',
      );
    }
    return result;
  }

  @override
  Future<RelationshipCapabilityView> getRelationshipCapability(
    GetRelationshipCapabilityQuery query,
  ) async {
    final result = await client
        .userPersonaRelationshipGetRelationshipCapability(
          query,
          context: invocationContext(
            UserRequestPageIds.getRelationshipCapability,
          ),
        );
    if (result.viewerPersonaId.trim().isEmpty ||
        result.targetPersonaId.trim().isEmpty ||
        result.targetPersonaId != query.targetPersonaId) {
      throw CloudErrorMapper.invalidResponse(
        message: 'GetRelationshipCapability returned a mismatched typed result',
        functionModule: 'persona_relationship_remote',
      );
    }
    return result;
  }

  Future<BlockCommandResult> _runStableCommandIntent({
    required String canonicalOperationId,
    required String clientPageId,
    required String targetPersonaId,
    required bool expectedBlocked,
    required Future<BlockCommandResult> Function(
      String idempotencyKey,
      CloudOperationInvocationContext baseContext,
    )
    send,
  }) async {
    final baseContext = invocationContext(clientPageId);
    final actorPersonaId = baseContext.actor.personaId?.trim() ?? '';
    if (actorPersonaId.isEmpty) {
      throw CloudErrorMapper.invalidResponse(
        message: '$canonicalOperationId requires an active persona actor',
        functionModule: 'persona_relationship_remote',
      );
    }
    final intentIdentity = <String>[
      canonicalOperationId,
      actorPersonaId,
      targetPersonaId,
      expectedBlocked.toString(),
    ].join('\u0000');
    var idempotencyKey = _pendingCommandIntentKeys[intentIdentity];
    if (idempotencyKey == null) {
      if (_pendingCommandIntentKeys.length >= _maxRetainedCommandIntents) {
        _pendingCommandIntentKeys.remove(_pendingCommandIntentKeys.keys.first);
      }
      idempotencyKey = _normalizeIdempotencyKey(_idempotencyKeyFactory());
      _pendingCommandIntentKeys[intentIdentity] = idempotencyKey;
    }
    final result = await send(idempotencyKey, baseContext);
    _pendingCommandIntentKeys.remove(intentIdentity);
    return result;
  }

  CloudOperationInvocationContext _commandContext(
    CloudOperationInvocationContext base,
    String idempotencyKey,
  ) {
    return CloudOperationInvocationContext(
      surfaceId: base.surfaceId,
      clientPageId: base.clientPageId,
      actor: base.actor,
      routeId: base.routeId,
      referralSource: base.referralSource,
      feedRequestId: base.feedRequestId,
      shareId: base.shareId,
      modelId: base.modelId,
      experimentBucket: base.experimentBucket,
      idempotencyKey: idempotencyKey,
      deadlineAt: base.deadlineAt,
      cancellation: base.cancellation,
    );
  }

  String _normalizeIdempotencyKey(String candidate) {
    final normalized = candidate.trim();
    if (normalized.isEmpty || normalized.length > 128) {
      throw CloudErrorMapper.invalidResponse(
        message: 'PersonaRelationship produced an invalid idempotency key',
        functionModule: 'persona_relationship_remote',
      );
    }
    return normalized;
  }

  BlockCommandResult _validateCommandResult(
    BlockCommandResult result, {
    required String targetPersonaId,
    required bool expectedBlocked,
    required String operation,
  }) {
    if (result.targetPersonaId.trim().isEmpty ||
        result.targetPersonaId != targetPersonaId ||
        result.blocked != expectedBlocked) {
      throw CloudErrorMapper.invalidResponse(
        message: '$operation returned a mismatched typed result',
        functionModule: 'persona_relationship_remote',
      );
    }
    return result;
  }
}
