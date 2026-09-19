import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/synthetic_login_form.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/alpha_content_composition.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/application/public/synthetic_session_port.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/video_preview_track_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/alpha_rehearsal_install.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/alpha_rehearsal_observation.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';

/// 只读已安装observer，不解析/创建auth、pending或rehearsal存储。
final alphaStorageObservationReaderProvider =
    Provider<RehearsalStorageObservation Function()>(
      (ref) =>
          () => _unavailableStorageObservation(),
    );

RehearsalStorageObservation _unavailableStorageObservation({
  bool invalidated = false,
  bool verified = false,
}) => RehearsalStorageObservation.fromWire({
  'schema': runtimeDocumentSchemaValues['rehearsal_storage_observation'],
  'status': RehearsalObservationStatus.unavailable.wireName,
  'configurationState': invalidated
      ? RehearsalConfigurationObservationState.invalidated.wireName
      : verified
      ? RehearsalConfigurationObservationState.verified.wireName
      : RehearsalConfigurationObservationState.notObserved.wireName,
  'startupAttemptId': '',
  'generation': '',
  'bindingDigest': '',
  'consumers': {
    for (final name in ['auth', 'installId', 'pending', 'rehearsal'])
      name: {
        'state': invalidated
            ? RehearsalConsumerObservationState.invalidated.wireName
            : RehearsalConsumerObservationState.notObserved.wireName,
        'namespaceDigest': '',
        'successfulOperations': <String>[],
      },
  },
});

/// Alpha 制品的唯一装配入口；校验 source 后才安装真实包内读取器。
void configureAlphaDependencies() {
  configureAppReadGeneration(() {
    if (CloudRuntimeConfig.contentSource != AppContentSource.bundledSnapshot) {
      throw StateError(
        'Alpha read generation requires a verified bundled source',
      );
    }
    installVideoPreviewTrackQuery(const BundledVideoPreviewTrackQuery());
    return installAlphaContentComposition(installMedia: true);
  });
  configureAppStartupScope(() {
    if (CloudRuntimeConfig.contentSource != AppContentSource.bundledSnapshot) {
      return StartupScopeComposition(dispose: () {});
    }
    final lifecycle = installingStartupScopeLifecycle;
    final confirmed = lifecycle?.confirmedAttempt;
    final space = CloudRuntimeConfig.rehearsalSpace;
    var disposed = false;
    final observer =
        space?.isIsolated == true && confirmed != null && lifecycle != null
        ? RehearsalStorageObserver(
            space: space!,
            currentSpace: () => disposed || !lifecycle.isCurrent
                ? null
                : CloudRuntimeConfig.rehearsalSpace,
            startupAttemptId: confirmed.attemptId,
            generation: lifecycle.generation.toString(),
            currentStartupAttemptId: () =>
                disposed ? null : lifecycle.confirmedAttempt?.attemptId,
            currentGeneration: () => !disposed && lifecycle.isCurrent
                ? lifecycle.generation.toString()
                : null,
          )
        : null;
    final composition = installAlphaRehearsalRuntime(storageObserver: observer);
    final uatObservation = space?.isIsolated == true && confirmed != null
        ? AlphaRehearsalObservation.install(attemptId: confirmed.attemptId)
        : null;
    final synthetic = composition.synthetic;
    if (composition.space.isIsolated &&
        (synthetic == null ||
            composition.challengePort == null ||
            composition.sessionPort == null ||
            composition.storageNamespace == null)) {
      composition.dispose();
      throw StateError(
        'Isolated Alpha startup requires complete typed login ports',
      );
    }
    final sessionPort = composition.sessionPort;
    final observedSession = sessionPort == null || uatObservation == null
        ? sessionPort
        : _ObservingSyntheticSessionPort(sessionPort, uatObservation);
    final capability = composition.space.isIsolated
        ? SyntheticLoginCapability(
            space: composition.space,
            currentSpace: () =>
                disposed ? null : CloudRuntimeConfig.rehearsalSpace,
            challengePort: composition.challengePort!,
            sessionPort: observedSession!,
            createIdentityLabel: synthetic!.createIdentityLabel,
            createRequestKey: synthetic.createRequestKey,
          )
        : null;
    return StartupScopeComposition(
      overrides: [
        if (uatObservation != null)
          syntheticLoginObservationAdmissionProvider.overrideWithValue(
            uatObservation.requireAdmission,
          ),
        if (uatObservation?.caseId == 'login-success')
          syntheticLoginCommittedObserverProvider.overrideWithValue((
            result,
          ) async {
            if (disposed || lifecycle?.isCurrent != true) {
              throw StateError('stale auth observation scope');
            }
            await uatObservation!.recordSessionEstablished(
              includeEditableControl: true,
            );
          }),
        if (uatObservation?.caseId == 'identity-restart' &&
            int.parse(uatObservation!.generation) < 2)
          syntheticLoginCommittedObserverProvider.overrideWithValue((
            result,
          ) async {
            if (disposed || lifecycle?.isCurrent != true) {
              throw StateError('stale auth observation scope');
            }
            await uatObservation!.recordSessionEstablished(
              includeEditableControl: false,
            );
          }),
        if (uatObservation?.caseId == 'identity-restart' &&
            int.parse(uatObservation!.generation) >= 2)
          syntheticSessionRestoredObserverProvider.overrideWithValue((
            session,
          ) async {
            if (disposed || lifecycle?.isCurrent != true) {
              throw StateError('stale auth observation scope');
            }
            if (!session.isAuthenticated) {
              throw StateError(
                'identity-restart restore did not re-establish session',
              );
            }
            await uatObservation!.recordSessionEstablished(
              includeEditableControl: false,
            );
          }),
        localCommandExecutionEnabledProvider.overrideWithValue(true),
        generatedCloudOperationExecutorProvider.overrideWithValue(
          composition.executor,
        ),
        generatedCloudOperationClientProvider.overrideWithValue(
          GeneratedCloudOperationClient(composition.executor),
        ),
        unauthenticatedGeneratedCloudOperationClientProvider.overrideWithValue(
          GeneratedCloudOperationClient(composition.executor),
        ),
        activePersonaContextProvider.overrideWith((ref) async {
          final session = ref.watch(authSessionControllerProvider);
          final personaId = session.activePersonaId.trim();
          final ownerId = session.ownerId.trim();
          if (!session.isAuthenticated ||
              personaId.isEmpty ||
              ownerId.isEmpty) {
            throw contentCapabilityUnavailable('active_persona');
          }
          return ActivePersonaContextViewData.fallback(
            personaId: personaId,
            ownerUserId: ownerId,
            displayName: session.rememberedDisplayName,
            avatarUrl: session.rememberedAvatarUrl,
          );
        }),
        alphaStorageObservationReaderProvider.overrideWithValue(() {
          if (disposed ||
              lifecycle?.isCurrent == false ||
              !identical(space, CloudRuntimeConfig.rehearsalSpace)) {
            observer?.invalidate();
            return _unavailableStorageObservation(invalidated: true);
          }
          return observer?.read() ??
              _unavailableStorageObservation(verified: true);
        }),
        if (capability != null)
          syntheticLoginCapabilityProvider.overrideWithValue(capability),
      ],
      dispose: () {
        if (disposed) return;
        disposed = true;
        observer?.invalidate();
        uatObservation?.invalidate();
        composition.dispose();
        if (!composition.space.isIsolated &&
            identical(installedAlphaRehearsalStore, composition.store)) {
          clearAlphaRehearsalRuntime();
        }
      },
    );
  });
}

final class _ObservingSyntheticSessionPort implements SyntheticSessionPort {
  _ObservingSyntheticSessionPort(this._inner, this._observation);

  final SyntheticSessionPort _inner;
  final AlphaRehearsalObservation _observation;

  @override
  Future<SyntheticSessionResult> complete(
    CompleteSyntheticChallenge command,
  ) async {
    try {
      return await _inner.complete(command);
    } on SyntheticLoginFailure catch (failure) {
      if (_observation.caseId == 'login-error' &&
          failure.reason == SyntheticLoginFailureReason.mismatch) {
        await _observation.recordRecoverableAuthError();
      }
      rethrow;
    }
  }
}
