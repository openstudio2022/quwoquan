// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
/// 受管 Gamma 身份的真实 ContactDiscovery production Remote runner。
///
/// 目标手机号与 persona identity 只从进程环境读取；手机号仅在 App 侧经
/// [ContactHashService] 转成 canonical hash，绝不进入 dart-define、日志、断言文本
/// 或 wire。当前不登记 readiness_case：物理通讯录权限、Follow UI、故障恢复和同
/// candidate 双真机证据由 user_acceptance/ResultBundle 独立验收。
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_discovery_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/domain/contact_hash_service.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';
import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const _hasher = ContactHashService();

void main() {
  test(
    'production Remote discovers a registered Provider identity and dismisses the record',
    () async {
      final inputs = _ContactDiscoveryProviderInputs.fromProcessEnvironment();
      UserApiContractHarness? accountHarness;
      _ContactDiscoveryProviderHarness? discoveryHarness;
      var discoveryId = '';
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

      try {
        accountHarness = await UserApiContractHarness.create();
        final session = await accountHarness.loginDisposableAccount(
          'contact-discovery-$suffix',
        );
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('discovery actor requires an active persona');
        }
        discoveryHarness = await _ContactDiscoveryProviderHarness.create(
          session: session,
          personaId: personaId,
        );

        final targetHash = _hasher.hash(inputs.targetPhone);
        if (targetHash.isEmpty) {
          throw StateError('managed contact identity is invalid');
        }
        final initial = await discoveryHarness.repository.initiate(<String>[
          targetHash,
        ]);
        discoveryId = initial.id;
        final completed = await _awaitTargetMatch(
          repository: discoveryHarness.repository,
          initial: initial,
          targetHash: targetHash,
          targetPersonaId: inputs.targetPersonaId,
        );
        _validateTargetMatch(
          completed,
          targetHash: targetHash,
          targetPersonaId: inputs.targetPersonaId,
        );

        await discoveryHarness.repository.dismiss(completed.id);
        discoveryId = '';
        final events = await discoveryHarness.telemetry.waitForEvents(
          minimumCount: 3,
        );
        final operations = events
            .map((event) => event.canonicalOperationId)
            .toSet();
        if (events.any((event) => !event.succeeded) ||
            !operations.contains(
              AppCloudOperationIds
                  .userContactDiscoveryRecordInitiateContactDiscovery,
            ) ||
            !operations.contains(
              AppCloudOperationIds
                  .userContactDiscoveryRecordGetLatestContactDiscovery,
            ) ||
            !operations.contains(
              AppCloudOperationIds
                  .userContactDiscoveryRecordDismissContactDiscovery,
            )) {
          throw StateError(
            'contact discovery did not emit the canonical successful operation set',
          );
        }
      } finally {
        try {
          if (discoveryId.isNotEmpty && discoveryHarness != null) {
            try {
              await discoveryHarness.repository.dismiss(discoveryId);
            } catch (_) {
              // The primary failure remains authoritative; account closure
              // below is the final cleanup boundary for a partial record.
            }
          }
          if (accountHarness != null) {
            await accountHarness.accountLifecycle.closeAccount(
              CloseAccountCommand(
                clientRequestId: 'contact-discovery-cleanup-$suffix',
              ),
            );
          }
        } finally {
          try {
            if (accountHarness != null) {
              await accountHarness.close();
            }
          } finally {
            await discoveryHarness?.close();
          }
        }
      }
    },
  );
}

Future<ContactDiscoveryResultView> _awaitTargetMatch({
  required ContactDiscoveryRepository repository,
  required ContactDiscoveryResultView initial,
  required String targetHash,
  required String targetPersonaId,
}) async {
  var current = initial;
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (_containsTarget(current, targetHash, targetPersonaId)) {
      return current;
    }
    await Future<void>.delayed(const Duration(milliseconds: 500));
    final latest = await repository.getLatest();
    if (latest != null) {
      current = latest;
    }
  }
  throw StateError('managed contact discovery did not converge');
}

bool _containsTarget(
  ContactDiscoveryResultView result,
  String targetHash,
  String targetPersonaId,
) {
  return result.matchedPersonaIds.contains(targetPersonaId) &&
      result.matches.any(
        (match) =>
            match.personaId == targetPersonaId &&
            match.hashedPhone == targetHash,
      );
}

void _validateTargetMatch(
  ContactDiscoveryResultView result, {
  required String targetHash,
  required String targetPersonaId,
}) {
  if (result.id.trim().isEmpty ||
      result.status != 'completed' ||
      result.matchCount <= 0 ||
      result.matchedPersonaIds.toSet().length !=
          result.matchedPersonaIds.length) {
    throw StateError('managed contact discovery result is invalid');
  }
  final matches = result.matches
      .where(
        (match) =>
            match.personaId == targetPersonaId &&
            match.hashedPhone == targetHash,
      )
      .toList(growable: false);
  if (matches.length != 1 ||
      matches.single.userHandle.trim().isEmpty ||
      matches.single.displayName.trim().isEmpty ||
      !matches.single.relationshipCapability.canFollow ||
      matches.single.relationshipCapability.isBlocked ||
      matches.single.relationshipCapability.isBlockedBy) {
    throw StateError('managed contact discovery capability is invalid');
  }
}

final class _ContactDiscoveryProviderInputs {
  const _ContactDiscoveryProviderInputs({
    required this.targetPhone,
    required this.targetPersonaId,
  });

  final String targetPhone;
  final String targetPersonaId;

  static _ContactDiscoveryProviderInputs fromProcessEnvironment() {
    final targetPhone =
        Platform.environment['QWQ_CONTACT_DISCOVERY_TARGET_PHONE']?.trim() ??
        '';
    final targetPersonaId =
        Platform.environment['QWQ_CONTACT_DISCOVERY_TARGET_PERSONA_ID']
            ?.trim() ??
        '';
    if (!RegExp(r'^\+?[0-9]{8,15}$').hasMatch(targetPhone) ||
        targetPersonaId.isEmpty) {
      throw StateError('managed contact discovery target is not configured');
    }
    return _ContactDiscoveryProviderInputs(
      targetPhone: targetPhone,
      targetPersonaId: targetPersonaId,
    );
  }
}

final class _ContactDiscoveryProviderHarness {
  const _ContactDiscoveryProviderHarness({
    required this.repository,
    required this.telemetry,
    required this._httpClient,
  });

  final RemoteContactDiscoveryRepository repository;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final CloudHttpClient _httpClient;

  static Future<_ContactDiscoveryProviderHarness> create({
    required AuthSessionGrant session,
    required String personaId,
  }) async {
    if (_apiContractEnv != 'gamma') {
      throw StateError('contact discovery Provider runner requires gamma');
    }
    final gateway = Uri.tryParse(_apiBase);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.scheme != 'https' ||
        gateway.host.isEmpty ||
        gateway.userInfo.isNotEmpty ||
        gateway.hasFragment) {
      throw StateError(
        'contact discovery Provider runner requires an HTTPS gateway',
      );
    }
    const clientContext = _ContactDiscoveryClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final httpClient = CloudHttpClient(
      authTokenProvider: _FixedTokenProvider(session.accessToken),
    );
    try {
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: gateway,
        ),
      );
      final facet = RemoteContactDiscoveryFacet(
        client: client,
        invocationContext: (clientPageId, {idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.addContactPhone.id,
              routeId: AppUiSurfaces.addContactPhone.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: CloudOperationActorContext(
                accountId: session.ownerId,
                personaId: personaId,
                deviceActorId: 'contact-discovery-api-runner',
              ),
            ),
      );
      var intentSequence = 0;
      return _ContactDiscoveryProviderHarness(
        repository: RemoteContactDiscoveryRepository(
          commandWriter: facet,
          query: facet,
          idempotencyKeyFactory: () =>
              'contact-discovery-api-${DateTime.now().toUtc().microsecondsSinceEpoch}-${intentSequence++}',
        ),
        telemetry: telemetry,
        httpClient: httpClient,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  Future<void> close() async {
    _httpClient.close();
    await telemetry.dispose();
  }
}

final class _FixedTokenProvider implements CloudAuthTokenProvider {
  const _FixedTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class _ContactDiscoveryClientContext
    implements CloudClientContextProvider {
  const _ContactDiscoveryClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'contact-discovery-api-runner',
      deviceActorId: 'contact-discovery-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
