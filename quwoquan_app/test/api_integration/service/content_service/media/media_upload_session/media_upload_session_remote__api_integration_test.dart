// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// readiness_case: media_upload_session_remote_app_api

import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;

  setUpAll(() async => harness = await ContentApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('production Remote init -> readback -> abort 保持同一上传会话', () async {
    final nonce = DateTime.now().microsecondsSinceEpoch;
    final payload = utf8.encode('content-media-upload-session-$nonce');
    final initKey = 'content-media-upload-init-$nonce';
    final initialized = await harness.withIdempotencyKey(
      initKey,
      () => harness.mediaUploads.initUpload(
        InitContentMediaUploadCommand(
          mediaType: MediaType.file,
          mimeType: 'application/octet-stream',
          fileSize: payload.length,
          expectedSha256: sha256.convert(payload).toString(),
        ),
        ContentMediaUploadCommandContext(idempotencyKey: initKey),
      ),
    );

    expect(initialized.status, MediaUploadSessionStatus.pending);
    expect(initialized.sessionId, isNotEmpty);
    expect(initialized.uploadUrl, isNotNull);
    expect(initialized.replayed, isFalse);
    expect(initialized.expiresAt.isAfter(DateTime.now().toUtc()), isTrue);

    final pending = await harness.mediaUploads.getUploadSession(
      GetContentMediaUploadSessionQuery(sessionId: initialized.sessionId),
    );
    expect(pending.sessionId, initialized.sessionId);
    expect(pending.status, MediaUploadSessionStatus.pending);
    expect(pending.mediaType, MediaType.file);
    expect(pending.fileSize, payload.length);
    expect(pending.version, greaterThan(0));

    final abortKey = 'content-media-upload-abort-$nonce';
    final aborted = await harness.withIdempotencyKey(
      abortKey,
      () => harness.mediaUploads.abortUpload(
        AbortContentMediaUploadCommand(sessionId: initialized.sessionId),
        ContentMediaUploadCommandContext(idempotencyKey: abortKey),
      ),
    );
    expect(aborted.sessionId, initialized.sessionId);
    expect(aborted.status, MediaUploadSessionStatus.aborted);

    final readback = await harness.mediaUploads.getUploadSession(
      GetContentMediaUploadSessionQuery(sessionId: initialized.sessionId),
    );
    expect(readback.sessionId, initialized.sessionId);
    expect(readback.status, MediaUploadSessionStatus.aborted);
    expect(readback.updatedAt.isBefore(DateTime.now().toUtc()), isTrue);
  });
}
