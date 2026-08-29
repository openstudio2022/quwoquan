// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart'
    show MediaDeliveryBinding;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final DateTime _epoch = DateTime.utc(2030, 1, 1);

MediaOriginalAccessGrant _grant({
  required String mediaId,
  String sign = 'sig-a',
  int ttlSeconds = 300,
}) {
  return MediaOriginalAccessGrant(
    mediaId: mediaId,
    status: 'granted',
    originalUrl: Uri.parse(
      'https://media.example.test/media/objects/sha256/aa/bb/$mediaId.jpg'
      '?sign=$sign&t=1893456300',
    ),
    format: 'image/jpeg',
    sizeBytes: 1024,
    expiresAt: _epoch.add(Duration(seconds: ttlSeconds)),
    ttlSeconds: ttlSeconds,
    auditId: 'audit-1',
  );
}

/// 对象级 typed double：记录全部 grant 命令并按脚本响应。
final class _ScriptedOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  _ScriptedOriginalAccessGateway(this._respond);

  final Future<MediaOriginalAccessGrant> Function(
    RequestContentMediaOriginalAccessCommand command,
  )
  _respond;
  final List<RequestContentMediaOriginalAccessCommand> commands =
      <RequestContentMediaOriginalAccessCommand>[];

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) {
    commands.add(command);
    return _respond(command);
  }
}

/// 记录实际拿到的候选地址；不做真实网络解码。
final class _RecordingImageLoader {
  final List<List<String>> candidateBatches = <List<String>>[];
  final Completer<void> _gate = Completer<void>();

  ImageBookImageLoadOperation call({
    required BuildContext context,
    required int pageIndex,
    required List<String> candidates,
    required Size pageSize,
  }) {
    candidateBatches.add(List<String>.unmodifiable(candidates));
    return _StubOperation(_gate.future);
  }
}

final class _StubOperation implements ImageBookImageLoadOperation {
  _StubOperation(Future<void> gate)
    : _result = gate.then(
        (_) => throw StateError('decode is not the subject of this contract'),
      );

  final Future<ImageBookImageLoadResult> _result;

  @override
  Future<ImageBookImageLoadResult> get result => _result;

  @override
  int get candidatesTried => 0;

  @override
  void cancel() {}
}

Widget _host(
  List<MediaDeliveryBinding> deliveries, {
  required SignedMediaDeliveryCoordinator coordinator,
  required _RecordingImageLoader loader,
}) {
  return ProviderScope(
    overrides: [
      signedMediaDeliveryCoordinatorProvider.overrideWithValue(coordinator),
    ],
    child: CupertinoApp(
      home: CupertinoPageScaffold(
        child: Center(
          child: SizedBox(
            width: 320,
            height: 480,
            child: ImageBookCanvas(
              deliveries: deliveries,
              imageLoader: loader.call,
              onImageChanged: (_) {},
              now: () => _epoch,
            ),
          ),
        ),
      ),
    ),
  );
}

void main() {
  SignedMediaDeliveryCoordinator coordinator(
    _ScriptedOriginalAccessGateway gateway,
  ) => SignedMediaDeliveryCoordinator(gateway: gateway, now: () => _epoch);

  group('ImageBookCanvas typed 交付分流', () {
    testWidgets('私有页经协调器换签后单候选直传短签地址', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (command) async => _grant(mediaId: command.mediaId),
      );
      final loader = _RecordingImageLoader();
      await tester.pumpWidget(
        _host(
          const <MediaDeliveryBinding>[
            MediaDeliveryBinding(
              assetId: 'asset-book-1',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              publicUrl: '',
            ),
          ],
          coordinator: coordinator(gateway),
          loader: loader,
        ),
      );
      await tester.pump();
      await tester.pump();

      // grant 兑换只经协调器发生一次，purpose 固定 view。
      expect(gateway.commands, hasLength(1));
      expect(gateway.commands.single.mediaId, 'asset-book-1');
      expect(gateway.commands.single.purpose, MediaOriginalAccessPurpose.view);

      // 短签地址单候选直传：不推导公开候选，也不经 CDN cover 变体改写签名。
      expect(loader.candidateBatches, hasLength(1));
      expect(loader.candidateBatches.single, hasLength(1));
      final candidate = loader.candidateBatches.single.single;
      expect(candidate, contains('sign=sig-a'));
      expect(candidate, contains('asset-book-1'));
      expect(candidate, isNot(contains('/media/image/')));
    });

    testWidgets('公开页不触达协调器且仍走 CDN cover 候选推导', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (command) async => _grant(mediaId: command.mediaId),
      );
      final loader = _RecordingImageLoader();
      await tester.pumpWidget(
        _host(
          const <MediaDeliveryBinding>[
            MediaDeliveryBinding(
              assetId: '',
              accessMode: null,
              publicUrl: 'media/image/s/fixture/v1/public-1.jpg',
            ),
          ],
          coordinator: coordinator(gateway),
          loader: loader,
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, isEmpty);
      expect(loader.candidateBatches, hasLength(1));
      expect(loader.candidateBatches.single, isNotEmpty);
    });

    testWidgets('声明私有但资产身份缺席：显式判否且不回退公开 URL', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (command) async => _grant(mediaId: command.mediaId),
      );
      final loader = _RecordingImageLoader();
      await tester.pumpWidget(
        _host(
          const <MediaDeliveryBinding>[
            MediaDeliveryBinding(
              assetId: '',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              publicUrl: 'https://cdn.example.test/media/objects/leak-1.jpg',
            ),
          ],
          coordinator: coordinator(gateway),
          loader: loader,
        ),
      );
      await tester.pump();
      await tester.pump();

      // 既不换签，也不拿公开 URL 顶替——私有资产走公开路径会跳过授权判定。
      expect(gateway.commands, isEmpty);
      expect(loader.candidateBatches, isEmpty);
    });

    testWidgets('换签失败停在判否，不回退公开候选', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => throw StateError('quota exhausted'),
      );
      final loader = _RecordingImageLoader();
      await tester.pumpWidget(
        _host(
          const <MediaDeliveryBinding>[
            MediaDeliveryBinding(
              assetId: 'asset-book-2',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              publicUrl: 'https://cdn.example.test/media/objects/leak-2.jpg',
            ),
          ],
          coordinator: coordinator(gateway),
          loader: loader,
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, hasLength(1));
      expect(loader.candidateBatches, isEmpty);
    });
  });
}