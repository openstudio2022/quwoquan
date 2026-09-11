// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019

import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart'
    show MediaDeliveryBinding;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

final DateTime _epoch = DateTime.utc(2030, 1, 1);
final _endpoints = MediaEndpointConfig(
  avatarBaseUrl: 'https://media.example.test/media/avatar',
  imageBaseUrl: 'https://media.example.test/media/image',
  videoBaseUrl: 'https://media.example.test/media/video',
  attachmentBaseUrl: 'https://media.example.test',
);

MediaOriginalAccessGrant _grant({
  required String mediaId,
  String sign = 'sig-a',
  int ttlSeconds = 300,
}) => MediaOriginalAccessGrant(
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

/// 只替换 typed gateway 的传输响应，授权校验、缓存与刷新仍运行真实协调器。
final class _ScriptedOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  _ScriptedOriginalAccessGateway(this._respond);

  final Future<MediaOriginalAccessGrant> Function(
    RequestContentMediaOriginalAccessCommand command,
  )
  _respond;
  final commands = <RequestContentMediaOriginalAccessCommand>[];

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) {
    commands.add(command);
    return _respond(command);
  }
}

/// 获取通过后才替换最后的网络图片解码；不复制 grant 判定或 URL 处理。
final class _AcquisitionSpy implements PublicMediaDeliveryPort {
  _AcquisitionSpy(_ScriptedOriginalAccessGateway gateway) {
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: () => _epoch,
    );
    remote = RemotePublicMediaDelivery(
      _endpoints,
      signedMedia: (binding, kind, refresh) => refresh
          ? coordinator.refresh(
              assetId: binding.assetId,
              kind: MediaDeliveryKind.image,
            )
          : coordinator.resolve(
              assetId: binding.assetId,
              kind: MediaDeliveryKind.image,
              accessMode: binding.accessMode!,
            ),
    );
  }

  late final RemotePublicMediaDelivery remote;
  final requests =
      <
        ({
          String reference,
          MediaDeliveryBinding binding,
          CdnImagePreset profile,
          bool refresh,
        })
      >[];
  final acquired = <CachedNetworkImageProvider>[];
  final decoders = <_ControlledImageProvider>[];

  @override
  Future<ImageProvider<Object>> acquireImage(
    String reference, {
    required MediaDeliveryBinding binding,
    CdnImagePreset profile = CdnImagePreset.none,
    bool refresh = false,
  }) async {
    requests.add((
      reference: reference,
      binding: binding,
      profile: profile,
      refresh: refresh,
    ));
    final provider = await remote.acquireImage(
      reference,
      binding: binding,
      profile: profile,
      refresh: refresh,
    );
    acquired.add(provider as CachedNetworkImageProvider);
    final decoder = _ControlledImageProvider();
    decoders.add(decoder);
    return decoder;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('画布绕过了统一 acquireImage 边界：${invocation.memberName}');
}

final class _ControlledImageProvider
    extends ImageProvider<_ControlledImageProvider> {
  final result = Completer<ImageInfo>();

  @override
  Future<_ControlledImageProvider> obtainKey(
    ImageConfiguration configuration,
  ) => SynchronousFuture(this);

  @override
  void resolveStreamForKey(
    ImageConfiguration configuration,
    ImageStream stream,
    _ControlledImageProvider key,
    ImageErrorListener handleError,
  ) => stream.setCompleter(OneFrameImageStreamCompleter(result.future));
}

Widget _host(
  List<MediaDeliveryBinding> deliveries, {
  required _AcquisitionSpy delivery,
  ValueChanged<ImageBookMediaLoadEvent>? onMediaLoad,
}) => ProviderScope(
  overrides: [
    ...sealedCloudBoundaryOverrides(),
    publicMediaDeliveryProvider.overrideWithValue(delivery),
  ],
  child: CupertinoApp(
    home: CupertinoPageScaffold(
      child: Center(
        child: SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: deliveries,
            onImageChanged: (_) {},
            onMediaLoad: onMediaLoad,
            now: () => _epoch,
          ),
        ),
      ),
    ),
  ),
);

void main() {
  setUp(MediaLoadFailureCache.instance.clear);
  tearDown(MediaLoadFailureCache.instance.clear);

  group('ImageBookCanvas typed 交付分流', () {
    testWidgets('私有绑定原样进入获取器，真实协调器换签且 query 字节不改写', (tester) async {
      final grant = _grant(mediaId: 'asset-book-1', sign: 'sig%2Fa%2Bb');
      final gateway = _ScriptedOriginalAccessGateway((_) async => grant);
      final delivery = _AcquisitionSpy(gateway);
      const binding = MediaDeliveryBinding(
        assetId: 'asset-book-1',
        accessMode: MediaDeliveryAccessMode.signedGrant,
        publicUrl:
            'https://media.example.test/media/objects/ignored.jpg?sign=old&t=1',
      );
      await tester.pumpWidget(_host(const [binding], delivery: delivery));
      await tester.pump();
      await tester.pump();

      expect(delivery.requests, hasLength(1));
      expect(delivery.requests.single.reference, binding.publicUrl);
      expect(delivery.requests.single.binding, same(binding));
      expect(delivery.requests.single.profile, CdnImagePreset.full);
      expect(delivery.requests.single.refresh, isFalse);
      expect(gateway.commands, hasLength(1));
      expect(gateway.commands.single.mediaId, binding.assetId);
      expect(gateway.commands.single.purpose, MediaOriginalAccessPurpose.view);
      expect(delivery.acquired.single.url, grant.originalUrl.toString());
      expect(delivery.acquired.single.cacheKey, 'signed|image|asset-book-1');
      expect(delivery.acquired.single.url, isNot(contains('imageMogr2')));
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('公开页原样进入获取器，full 原图而非 cover 且不触达协调器', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (command) async => _grant(mediaId: command.mediaId),
      );
      final delivery = _AcquisitionSpy(gateway);
      const path = 'media/image/s/fixture/v1/public-1.jpg';
      const binding = MediaDeliveryBinding.public(publicUrl: path);
      await tester.pumpWidget(_host(const [binding], delivery: delivery));
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, isEmpty);
      expect(delivery.requests.single.reference, path);
      expect(delivery.requests.single.binding, same(binding));
      expect(delivery.requests.single.profile, CdnImagePreset.full);
      expect(delivery.acquired.single.url, 'https://media.example.test/$path');
      expect(
        delivery.acquired.single.cacheManager,
        same(
          AppImageCacheController.cacheManagerForPreset(CdnImagePreset.full),
        ),
      );
      await tester.pumpWidget(const SizedBox.shrink());
    });

    for (final binding in <MediaDeliveryBinding>[
      const MediaDeliveryBinding(
        assetId: '',
        accessMode: MediaDeliveryAccessMode.signedGrant,
        publicUrl: 'https://media.example.test/media/image/leak.jpg',
      ),
      const MediaDeliveryBinding(
        assetId: 'asset-without-access-mode',
        accessMode: null,
        publicUrl: 'https://media.example.test/media/image/leak.jpg',
      ),
      const MediaDeliveryBinding(
        assetId: '',
        accessMode: null,
        publicUrl: 'media/image/s/fixture/v1/public-looking.jpg',
      ),
    ]) {
      testWidgets('矛盾绑定 fail closed：${binding.accessMode}/${binding.assetId}', (
        tester,
      ) async {
        final gateway = _ScriptedOriginalAccessGateway(
          (command) async => _grant(mediaId: command.mediaId),
        );
        final delivery = _AcquisitionSpy(gateway);
        final events = <ImageBookMediaLoadEvent>[];
        await tester.pumpWidget(
          _host([binding], delivery: delivery, onMediaLoad: events.add),
        );
        await tester.pump();
        await tester.pump();

        expect(gateway.commands, isEmpty);
        expect(delivery.requests, isEmpty);
        expect(delivery.decoders, isEmpty);
        expect(events.single.result, 'failure');
        expect(events.single.candidatesTried, 0);
        expect(
          find.byKey(const ValueKey('image-book-status-failed')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('image-book-status-absent')),
          findsNothing,
        );
        await tester.pumpWidget(const SizedBox.shrink());
      });
    }

    testWidgets('换签失败停在判否，不回退公开候选', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => throw StateError('quota exhausted'),
      );
      final delivery = _AcquisitionSpy(gateway);
      final events = <ImageBookMediaLoadEvent>[];
      await tester.pumpWidget(
        _host(
          const [
            MediaDeliveryBinding(
              assetId: 'asset-book-2',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              publicUrl: 'https://media.example.test/media/image/leak-2.jpg',
            ),
          ],
          delivery: delivery,
          onMediaLoad: events.add,
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, hasLength(1));
      expect(delivery.requests, hasLength(1));
      expect(delivery.acquired, isEmpty);
      expect(delivery.decoders, isEmpty);
      expect(events.single.result, 'failure');
      expect(
        find.byKey(const ValueKey('image-book-status-failed')),
        findsOneWidget,
      );
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('grant 资产身份不匹配由真实协调器拒绝，不进入图片解码', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => _grant(mediaId: 'wrong-asset'),
      );
      final delivery = _AcquisitionSpy(gateway);
      final events = <ImageBookMediaLoadEvent>[];
      await tester.pumpWidget(
        _host(
          const [
            MediaDeliveryBinding(
              assetId: 'asset-book-3',
              accessMode: MediaDeliveryAccessMode.signedGrant,
              publicUrl: '',
            ),
          ],
          delivery: delivery,
          onMediaLoad: events.add,
        ),
      );
      await tester.pump();
      await tester.pump();
      expect(gateway.commands, hasLength(1));
      expect(delivery.acquired, isEmpty);
      expect(delivery.decoders, isEmpty);
      expect(
        events.single.error,
        isA<SignedMediaDeliveryException>().having(
          (error) => error.failure,
          'failure',
          SignedMediaDeliveryFailure.grantIdentityMismatch,
        ),
      );
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('私有页解码失败后用户重试清负缓存并强制重新换签', (tester) async {
      var exchangeCount = 0;
      final gateway = _ScriptedOriginalAccessGateway(
        (command) async =>
            _grant(mediaId: command.mediaId, sign: 'sig-${++exchangeCount}'),
      );
      final delivery = _AcquisitionSpy(gateway);
      const binding = MediaDeliveryBinding(
        assetId: 'asset-retry',
        accessMode: MediaDeliveryAccessMode.signedGrant,
        publicUrl: '',
      );
      await tester.pumpWidget(_host(const [binding], delivery: delivery));
      await tester.pump();
      delivery.decoders.single.result.completeError(
        StateError('HTTP status code: 403'),
      );
      // ImageStream 的 onError 先完成 operation，下一帧才提交失败页面。
      await tester.pump();
      await tester.pump();
      expect(
        find.byKey(const ValueKey('image-book-status-failed')),
        findsOneWidget,
      );
      expect(
        MediaLoadFailureCache.instance.activeFailure(
          'signed|image|asset-retry',
        ),
        isNotNull,
      );
      await tester.tap(find.byKey(const ValueKey('image-book-retry')));
      await tester.pump();
      expect(gateway.commands, hasLength(2));
      expect(delivery.requests.map((request) => request.refresh), [
        false,
        true,
      ]);
      expect(
        delivery.requests.every(
          (request) => identical(request.binding, binding),
        ),
        isTrue,
      );
      expect(delivery.acquired.map((provider) => provider.url), [
        _grant(mediaId: binding.assetId, sign: 'sig-1').originalUrl.toString(),
        _grant(mediaId: binding.assetId, sign: 'sig-2').originalUrl.toString(),
      ]);
      expect(delivery.acquired.map((provider) => provider.cacheKey).toSet(), {
        'signed|image|asset-retry',
      });
      expect(
        MediaLoadFailureCache.instance.activeFailure(
          'signed|image|asset-retry',
        ),
        isNull,
      );
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });
}
