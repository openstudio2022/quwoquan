// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004.t2
// readiness_case: circle_file_get_circle_file_app_api
// readiness_case: circle_file_list_circle_files_app_api
// readiness_case: circle_file_update_circle_file_app_api

/// CircleFile operation-level production API source contract.
///
/// Disposable actors and the owning Circle/CircleFile hierarchy are acquired
/// only through public generated operations. Create/Delete are exercised as
/// setup and lifecycle probes, but do not declare readiness until a public
/// ready-MediaAsset acquisition and non-empty-folder delete guard are proven.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/circle_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiContractBaseUrl = String.fromEnvironment('API_CONTRACT_BASE_URL');

const _fileOperationIds = <String>{
  AppCloudOperationIds.circleCircleFileListCircleFiles,
  AppCloudOperationIds.circleCircleFileGetCircleFile,
  AppCloudOperationIds.circleCircleFileCreateCircleFile,
  AppCloudOperationIds.circleCircleFileUpdateCircleFile,
  AppCloudOperationIds.circleCircleFileDeleteCircleFile,
};

void main() {
  test(
    'CircleFile owner reads and update converge through a real process',
    () async {
      _requireGammaCandidate();
      final harnesses = <CircleApiContractHarness>[];
      addTearDown(() async {
        for (final harness in harnesses.reversed) {
          await harness.close();
        }
      });

      Future<CircleApiContractHarness> createHarness() async {
        final harness = await CircleApiContractHarness.create();
        harnesses.add(harness);
        return harness;
      }

      final owner = await createHarness();
      final outsider = await createHarness();
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final ownerPersonaId = await _loginPersona(
        owner,
        'circle-file-owner-$suffix',
      );
      await _loginPersona(outsider, 'circle-file-outsider-$suffix');
      final telemetry = _TelemetryLedger();

      final circle = await owner.withIdempotencyKey(
        'circle-file-parent-$suffix',
        () => owner.lifecycle.createCircle(
          CreateCircleCommand(
            name: 'CircleFile API contract $suffix',
            category: 'collaboration',
          ),
        ),
      );
      final circleId = circle.circleId;
      addTearDown(() async {
        await owner.withIdempotencyKey(
          'circle-file-parent-cleanup-$circleId',
          () => owner.lifecycle.archiveCircle(
            ArchiveCircleCommand(circleId: circleId),
          ),
        );
      });

      Future<CircleFileCommandResult> createFolder({
        required String key,
        required String name,
        String? parentFolderId,
      }) => telemetry.observe(
        AppCloudOperationIds.circleCircleFileCreateCircleFile,
        () => owner.withIdempotencyKey(
          key,
          () => owner.fileWriter.create(
            CreateCircleFileCommand(
              circleId: circleId,
              parentFolderId: parentFolderId,
              name: name,
              fileType: CircleFileType.folder,
            ),
          ),
        ),
      );

      final sourceRoot = await createFolder(
        key: 'circle-file-source-root-$suffix',
        name: 'Source $suffix',
      );
      final destinationRoot = await createFolder(
        key: 'circle-file-destination-root-$suffix',
        name: 'Destination $suffix',
      );
      final childKey = 'circle-file-child-a-$suffix';
      final childCommand = CreateCircleFileCommand(
        circleId: circleId,
        parentFolderId: sourceRoot.fileId,
        name: 'Child A $suffix',
        fileType: CircleFileType.folder,
      );
      final childA = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileCreateCircleFile,
        () => owner.withIdempotencyKey(
          childKey,
          () => owner.fileWriter.create(childCommand),
        ),
      );
      final childAReplay = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileCreateCircleFile,
        () => owner.withIdempotencyKey(
          childKey,
          () => owner.fileWriter.create(childCommand),
        ),
      );
      final childB = await createFolder(
        key: 'circle-file-child-b-$suffix',
        name: 'Child B $suffix',
        parentFolderId: sourceRoot.fileId,
      );
      expect(sourceRoot.version, 1);
      expect(destinationRoot.version, 1);
      expect(childA.version, 1);
      expect(childA.idempotentReplay, isFalse);
      expect(childAReplay.fileId, childA.fileId);
      expect(childAReplay.version, childA.version);
      expect(childAReplay.idempotentReplay, isTrue);
      expect(childB.version, 1);

      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleFileCreateCircleFile,
          () => owner.withIdempotencyKey(
            'circle-file-invalid-asset-$suffix',
            () => owner.fileWriter.create(
              CreateCircleFileCommand(
                circleId: circleId,
                name: 'Unavailable asset $suffix',
                fileType: CircleFileType.file,
                assetId: 'missing-owned-ready-asset-$suffix',
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleFileCreateCircleFile,
        codes: const <String>{'CIRCLE.USER.file_asset_invalid'},
        statusCodes: const <int>{422},
      );

      final listed = await _readTwoPages(
        telemetry,
        owner,
        circleId: circleId,
        parentFolderId: sourceRoot.fileId,
      );
      expect(
        listed.expand((page) => page.items).map((item) => item.fileId).toSet(),
        <String>{childA.fileId, childB.fileId},
      );

      final createdReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileGetCircleFile,
        () => owner.fileReader.get(
          CircleFileQuery(circleId: circleId, fileId: childA.fileId),
        ),
      );
      _expectFolder(
        createdReadback,
        circleId: circleId,
        fileId: childA.fileId,
        version: childA.version,
        parentFolderId: sourceRoot.fileId,
        name: 'Child A $suffix',
        uploaderPersonaId: ownerPersonaId,
      );

      final outsiderCalls =
          <({String operationId, Future<Object?> Function() invoke})>[
            (
              operationId: AppCloudOperationIds.circleCircleFileListCircleFiles,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleFileListCircleFiles,
                () => outsider.fileReader.list(
                  CircleFileListQuery(
                    circleId: circleId,
                    parentFolderId: sourceRoot.fileId,
                    limit: 1,
                  ),
                ),
              ),
            ),
            (
              operationId: AppCloudOperationIds.circleCircleFileGetCircleFile,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleFileGetCircleFile,
                () => outsider.fileReader.get(
                  CircleFileQuery(circleId: circleId, fileId: childA.fileId),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleFileCreateCircleFile,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleFileCreateCircleFile,
                () => outsider.withIdempotencyKey(
                  'circle-file-outsider-create-$suffix',
                  () => outsider.fileWriter.create(
                    CreateCircleFileCommand(
                      circleId: circleId,
                      name: 'Forbidden $suffix',
                      fileType: CircleFileType.folder,
                    ),
                  ),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleFileUpdateCircleFile,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleFileUpdateCircleFile,
                () => outsider.withIdempotencyKey(
                  'circle-file-outsider-update-$suffix',
                  () => outsider.fileWriter.update(
                    UpdateCircleFileCommand(
                      circleId: circleId,
                      fileId: childA.fileId,
                      expectedVersion: childA.version,
                      name: 'Forbidden update',
                    ),
                  ),
                ),
              ),
            ),
            (
              operationId:
                  AppCloudOperationIds.circleCircleFileDeleteCircleFile,
              invoke: () => telemetry.observe(
                AppCloudOperationIds.circleCircleFileDeleteCircleFile,
                () => outsider.withIdempotencyKey(
                  'circle-file-outsider-delete-$suffix',
                  () => outsider.fileWriter.delete(
                    DeleteCircleFileCommand(
                      circleId: circleId,
                      fileId: childA.fileId,
                    ),
                  ),
                ),
              ),
            ),
          ];
      for (final call in outsiderCalls) {
        await _expectCanonicalFailure(
          call.invoke(),
          operationId: call.operationId,
          codes: const <String>{
            'CIRCLE.USER.not_member',
            'CIRCLE.USER.permission_denied',
          },
          statusCodes: const <int>{403},
        );
      }
      final afterBola = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileGetCircleFile,
        () => owner.fileReader.get(
          CircleFileQuery(circleId: circleId, fileId: childA.fileId),
        ),
      );
      expect(afterBola.version, childA.version);
      expect(afterBola.name, 'Child A $suffix');

      final updateKey = 'circle-file-update-$suffix';
      final updateCommand = UpdateCircleFileCommand(
        circleId: circleId,
        fileId: childA.fileId,
        expectedVersion: childA.version,
        parentFolderId: destinationRoot.fileId,
        name: 'Moved child A $suffix',
      );
      final updated = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileUpdateCircleFile,
        () => owner.withIdempotencyKey(
          updateKey,
          () => owner.fileWriter.update(updateCommand),
        ),
      );
      final updateReplay = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileUpdateCircleFile,
        () => owner.withIdempotencyKey(
          updateKey,
          () => owner.fileWriter.update(updateCommand),
        ),
      );
      expect(updated.fileId, childA.fileId);
      expect(updated.version, childA.version + 1);
      expect(updated.status, CircleFileStatus.active);
      expect(updated.idempotentReplay, isFalse);
      expect(updateReplay.fileId, updated.fileId);
      expect(updateReplay.version, updated.version);
      expect(updateReplay.idempotentReplay, isTrue);

      final updatedReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileGetCircleFile,
        () => owner.fileReader.get(
          CircleFileQuery(circleId: circleId, fileId: childA.fileId),
        ),
      );
      _expectFolder(
        updatedReadback,
        circleId: circleId,
        fileId: childA.fileId,
        version: updated.version,
        parentFolderId: destinationRoot.fileId,
        name: 'Moved child A $suffix',
        uploaderPersonaId: ownerPersonaId,
      );

      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleFileUpdateCircleFile,
          () => owner.withIdempotencyKey(
            updateKey,
            () => owner.fileWriter.update(
              UpdateCircleFileCommand(
                circleId: circleId,
                fileId: childA.fileId,
                expectedVersion: childA.version,
                parentFolderId: destinationRoot.fileId,
                name: 'Conflicting digest $suffix',
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleFileUpdateCircleFile,
        codes: const <String>{'CIRCLE.USER.file_idempotency_conflict'},
        statusCodes: const <int>{409},
      );
      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleFileUpdateCircleFile,
          () => owner.withIdempotencyKey(
            'circle-file-stale-update-$suffix',
            () => owner.fileWriter.update(
              UpdateCircleFileCommand(
                circleId: circleId,
                fileId: childA.fileId,
                expectedVersion: childA.version,
                name: 'Stale update',
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleFileUpdateCircleFile,
        codes: const <String>{'CIRCLE.USER.file_version_conflict'},
        statusCodes: const <int>{409},
      );
      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleFileUpdateCircleFile,
          () => owner.withIdempotencyKey(
            'circle-file-cycle-update-$suffix',
            () => owner.fileWriter.update(
              UpdateCircleFileCommand(
                circleId: circleId,
                fileId: destinationRoot.fileId,
                expectedVersion: destinationRoot.version,
                parentFolderId: childA.fileId,
              ),
            ),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleFileUpdateCircleFile,
        codes: const <String>{'CIRCLE.USER.file_parent_invalid'},
        statusCodes: const <int>{422},
      );
      final finalUpdatedReadback = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileGetCircleFile,
        () => owner.fileReader.get(
          CircleFileQuery(circleId: circleId, fileId: childA.fileId),
        ),
      );
      expect(finalUpdatedReadback.version, updated.version);
      expect(finalUpdatedReadback.name, 'Moved child A $suffix');
      expect(finalUpdatedReadback.parentFolderId, destinationRoot.fileId);

      final deleteKey = 'circle-file-delete-$suffix';
      final deleteCommand = DeleteCircleFileCommand(
        circleId: circleId,
        fileId: childA.fileId,
      );
      final deleted = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileDeleteCircleFile,
        () => owner.withIdempotencyKey(
          deleteKey,
          () => owner.fileWriter.delete(deleteCommand),
        ),
      );
      final deleteReplay = await telemetry.observe(
        AppCloudOperationIds.circleCircleFileDeleteCircleFile,
        () => owner.withIdempotencyKey(
          deleteKey,
          () => owner.fileWriter.delete(deleteCommand),
        ),
      );
      expect(deleted.fileId, childA.fileId);
      expect(deleted.version, updated.version + 1);
      expect(deleted.status, CircleFileStatus.deleted);
      expect(deleted.idempotentReplay, isFalse);
      expect(deleteReplay.fileId, deleted.fileId);
      expect(deleteReplay.version, deleted.version);
      expect(deleteReplay.idempotentReplay, isTrue);
      await _expectCanonicalFailure(
        telemetry.observe(
          AppCloudOperationIds.circleCircleFileGetCircleFile,
          () => owner.fileReader.get(
            CircleFileQuery(circleId: circleId, fileId: childA.fileId),
          ),
        ),
        operationId: AppCloudOperationIds.circleCircleFileGetCircleFile,
        codes: const <String>{'CIRCLE.USER.file_not_found'},
        statusCodes: const <int>{404},
      );

      await telemetry.expectExactEvidence(harnesses);
    },
  );
}

void _requireGammaCandidate() {
  if (_apiContractBaseUrl.isEmpty) {
    throw StateError('L3: API_CONTRACT_BASE_URL not set');
  }
  if (_apiContractEnv != 'gamma') {
    throw StateError('CircleFile App API contract requires gamma candidate');
  }
  final baseUri = Uri.tryParse(_apiContractBaseUrl);
  if (baseUri == null ||
      baseUri.scheme != 'https' ||
      !baseUri.hasAuthority ||
      baseUri.host != 'api.gamma.quwoquan.com') {
    throw StateError(
      'CircleFile App API contract requires the canonical Gamma HTTPS endpoint',
    );
  }
}

Future<String> _loginPersona(
  CircleApiContractHarness harness,
  String purpose,
) async {
  final session = await harness.loginDisposableAccount(purpose);
  final personaId = session.activePersona?.personaId;
  expect(personaId, isNotNull);
  expect(personaId, isNotEmpty);
  return personaId!;
}

Future<List<CircleFilePageSlice>> _readTwoPages(
  _TelemetryLedger telemetry,
  CircleApiContractHarness owner, {
  required String circleId,
  required String parentFolderId,
}) async {
  final first = await telemetry.observe(
    AppCloudOperationIds.circleCircleFileListCircleFiles,
    () => owner.fileReader.list(
      CircleFileListQuery(
        circleId: circleId,
        parentFolderId: parentFolderId,
        limit: 1,
      ),
    ),
  );
  expect(first.items, hasLength(1));
  expect(first.cursor, isNotNull);
  expect(first.cursor, isNotEmpty);
  final second = await telemetry.observe(
    AppCloudOperationIds.circleCircleFileListCircleFiles,
    () => owner.fileReader.list(
      CircleFileListQuery(
        circleId: circleId,
        parentFolderId: parentFolderId,
        cursor: first.cursor,
        limit: 1,
      ),
    ),
  );
  expect(second.items, hasLength(1));
  expect(second.items.single.fileId, isNot(first.items.single.fileId));
  for (final item in <CircleFileSlice>[...first.items, ...second.items]) {
    expect(item.circleId, circleId);
    expect(item.parentFolderId, parentFolderId);
    expect(item.fileType, CircleFileType.folder);
    expect(item.assetId, isNull);
    expect(item.mimeType, isNull);
    expect(item.sizeBytes, 0);
    expect(item.status, CircleFileStatus.active);
    expect(item.version, greaterThan(0));
    expect(item.createdAt.isUtc, isTrue);
    expect(item.updatedAt.isUtc, isTrue);
  }
  return <CircleFilePageSlice>[first, second];
}

void _expectFolder(
  CircleFileSlice file, {
  required String circleId,
  required String fileId,
  required int version,
  required String parentFolderId,
  required String name,
  required String uploaderPersonaId,
}) {
  expect(file.fileId, fileId);
  expect(file.version, version);
  expect(file.circleId, circleId);
  expect(file.groupId, isNull);
  expect(file.parentFolderId, parentFolderId);
  expect(file.name, name);
  expect(file.fileType, CircleFileType.folder);
  expect(file.assetId, isNull);
  expect(file.mimeType, isNull);
  expect(file.sizeBytes, 0);
  expect(file.uploaderPersonaId, uploaderPersonaId);
  expect(file.status, CircleFileStatus.active);
  expect(file.createdAt.isUtc, isTrue);
  expect(file.updatedAt.isUtc, isTrue);
}

Future<void> _expectCanonicalFailure(
  Future<Object?> call, {
  required String operationId,
  required Set<String> codes,
  required Set<int> statusCodes,
}) async {
  await expectLater(
    call,
    throwsA(
      isA<CloudException>()
          .having((error) => error.code, 'code', isIn(codes))
          .having((error) => error.statusCode, 'statusCode', isIn(statusCodes))
          .having(
            (error) => error.sourceOperationId,
            'sourceOperationId',
            operationId,
          )
          .having((error) => error.requestId, 'requestId', isNotEmpty)
          .having((error) => error.traceId, 'traceId', isNotEmpty),
    ),
  );
}

final class _TelemetryLedger {
  final Map<String, int> _success = <String, int>{};
  final Map<String, int> _failure = <String, int>{};

  Future<T> observe<T>(
    String operationId,
    Future<T> Function() operation,
  ) async {
    try {
      final value = await operation();
      _success.update(operationId, (count) => count + 1, ifAbsent: () => 1);
      return value;
    } catch (_) {
      _failure.update(operationId, (count) => count + 1, ifAbsent: () => 1);
      rethrow;
    }
  }

  Future<void> expectExactEvidence(
    List<CircleApiContractHarness> harnesses,
  ) async {
    final events = <ProductionCloudOperationTelemetryEvent>[];
    for (final harness in harnesses) {
      events.addAll(await harness.telemetry.waitForEvents(minimumCount: 1));
    }
    final fileEvents = events
        .where(
          (event) => _fileOperationIds.contains(event.canonicalOperationId),
        )
        .toList(growable: false);
    expect(
      fileEvents.map((event) => event.canonicalOperationId).toSet(),
      _fileOperationIds,
    );
    for (final operationId in _fileOperationIds) {
      final operationEvents = fileEvents
          .where((event) => event.canonicalOperationId == operationId)
          .toList(growable: false);
      final succeeded = operationEvents
          .where((event) => event.succeeded)
          .toList(growable: false);
      final failed = operationEvents
          .where((event) => !event.succeeded)
          .toList(growable: false);
      expect(succeeded, hasLength(_success[operationId] ?? 0));
      expect(failed, hasLength(_failure[operationId] ?? 0));
      expect(
        operationEvents.every(
          (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
        ),
        isTrue,
      );
      expect(
        succeeded.every(
          (event) =>
              event.statusCode != null &&
              event.statusCode! >= 200 &&
              event.statusCode! < 300,
        ),
        isTrue,
      );
      expect(
        failed.every(
          (event) => event.statusCode != null && event.statusCode! >= 400,
        ),
        isTrue,
      );
    }
  }
}
