import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContactDiscoveryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

typedef ContactDiscoveryIdempotencyKeyFactory = String Function();

/// ContactDiscoveryRecord 对象的 production generated-client adapter。
final class RemoteContactDiscoveryFacet
    implements
        ContactDiscoveryCommandWriter,
        ContactDiscoveryIntentCommandWriter,
        ContactDiscoveryQuery {
  const RemoteContactDiscoveryFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContactDiscoveryInvocationContextFactory invocationContext;

  @override
  Future<ContactDiscoveryResult> initiateContactDiscovery(
    InitiateContactDiscoveryCommand command,
  ) {
    return client.userContactDiscoveryRecordInitiateContactDiscovery(
      command,
      context: invocationContext(UserRequestPageIds.initiateContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryResult> initiateContactDiscoveryWithIntent(
    InitiateContactDiscoveryCommand command, {
    required String idempotencyKey,
  }) {
    return client.userContactDiscoveryRecordInitiateContactDiscovery(
      command,
      context: invocationContext(
        UserRequestPageIds.initiateContactDiscovery,
        idempotencyKey: idempotencyKey,
      ),
    );
  }

  @override
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  ) {
    return client.userContactDiscoveryRecordGetLatestContactDiscovery(
      query,
      context: invocationContext(UserRequestPageIds.getLatestContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  ) {
    return client.userContactDiscoveryRecordDismissContactDiscovery(
      command,
      context: invocationContext(UserRequestPageIds.dismissContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryDismissResult> dismissContactDiscoveryWithIntent(
    DismissContactDiscoveryCommand command, {
    required String idempotencyKey,
  }) {
    return client.userContactDiscoveryRecordDismissContactDiscovery(
      command,
      context: invocationContext(
        UserRequestPageIds.dismissContactDiscovery,
        idempotencyKey: idempotencyKey,
      ),
    );
  }
}

final class RemoteContactDiscoveryRepository
    implements ContactDiscoveryRepository {
  RemoteContactDiscoveryRepository({
    required this.commandWriter,
    required this.query,
    this.idempotencyKeyFactory,
  });

  final ContactDiscoveryCommandWriter commandWriter;
  final ContactDiscoveryQuery query;
  final ContactDiscoveryIdempotencyKeyFactory? idempotencyKeyFactory;
  final Map<String, String> _initiationIntentKeys = <String, String>{};
  final Map<String, String> _dismissIntentKeys = <String, String>{};

  static const int _maxRetainedInitiationIntents = 8;

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    final intentWriter = commandWriter;
    if (intentWriter is! ContactDiscoveryIntentCommandWriter) {
      throw CloudErrorMapper.invalidResponse(
        message:
            'ContactDiscovery command writer cannot bind an idempotency intent',
        functionModule: 'contact_discovery_remote',
      );
    }
    final idempotentWriter =
        intentWriter as ContactDiscoveryIntentCommandWriter;
    final normalizedHashes = _normalizeSnapshot(hashedPhones);
    final snapshotIdentity = normalizedHashes.join('\u0000');
    var idempotencyKey = _initiationIntentKeys[snapshotIdentity];
    if (idempotencyKey == null) {
      if (_initiationIntentKeys.length >= _maxRetainedInitiationIntents) {
        _initiationIntentKeys.remove(_initiationIntentKeys.keys.first);
      }
      idempotencyKey = _createIdempotencyKey();
      _initiationIntentKeys[snapshotIdentity] = idempotencyKey;
    }
    final result = await idempotentWriter.initiateContactDiscoveryWithIntent(
      InitiateContactDiscoveryCommand(hashedPhones: normalizedHashes),
      idempotencyKey: idempotencyKey,
    );
    final view = ContactDiscoveryResultView.fromWire(result);
    _initiationIntentKeys.remove(snapshotIdentity);
    return view;
  }

  @override
  Future<ContactDiscoveryResultView> getLatest() async {
    final result = await query.getLatestContactDiscovery(
      GetLatestContactDiscoveryQuery(),
    );
    if (result.id.trim().isEmpty) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscoveryResult.id must not be blank',
        functionModule: 'contact_discovery_remote',
      );
    }
    return ContactDiscoveryResultView.fromWire(result);
  }

  @override
  Future<void> dismiss(String id) async {
    final normalizedId = id.trim();
    if (normalizedId.isEmpty) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscovery dismiss requires a non-blank id',
        functionModule: 'contact_discovery_remote',
      );
    }
    final intentWriter = commandWriter;
    if (intentWriter is! ContactDiscoveryIntentCommandWriter) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscovery command writer cannot bind a dismiss intent',
        functionModule: 'contact_discovery_remote',
      );
    }
    final idempotentWriter =
        intentWriter as ContactDiscoveryIntentCommandWriter;
    var idempotencyKey = _dismissIntentKeys[normalizedId];
    if (idempotencyKey == null) {
      if (_dismissIntentKeys.length >= _maxRetainedInitiationIntents) {
        _dismissIntentKeys.remove(_dismissIntentKeys.keys.first);
      }
      idempotencyKey = _createIdempotencyKey();
      _dismissIntentKeys[normalizedId] = idempotencyKey;
    }
    await idempotentWriter.dismissContactDiscoveryWithIntent(
      DismissContactDiscoveryCommand(discoveryId: normalizedId),
      idempotencyKey: idempotencyKey,
    );
    _dismissIntentKeys.remove(normalizedId);
  }

  List<String> _normalizeSnapshot(List<String> hashedPhones) {
    final normalized =
        hashedPhones
            .map((hash) => hash.trim())
            .where((hash) => hash.isNotEmpty)
            .toSet()
            .toList(growable: false)
          ..sort();
    if (normalized.isEmpty) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscovery requires at least one phone hash',
        functionModule: 'contact_discovery_remote',
      );
    }
    return normalized;
  }

  String _createIdempotencyKey() {
    final factory = idempotencyKeyFactory;
    if (factory == null) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscovery has no idempotency key factory',
        functionModule: 'contact_discovery_remote',
      );
    }
    final key = factory().trim();
    if (key.isEmpty || key.length > 128) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscovery produced an invalid idempotency key',
        functionModule: 'contact_discovery_remote',
      );
    }
    return key;
  }
}
