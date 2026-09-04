// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/runtime/transport/media/signed_video_delivery.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart'
    show MediaDeliveryBinding, MediaDeliveryImage;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_failure_state.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_video.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final DateTime _epoch = DateTime.utc(2030, 1, 1);
const Key _publicKey = Key('video-public');
const Key _signedKey = Key('video-signed');
const Key _placeholderKey = Key('video-placeholder');
const Key _errorKey = Key('video-error');
const Key _absentKey = Key('video-absent');

MediaOriginalAccessGrant _grant({String sign = 'sig-a'}) =>
    MediaOriginalAccessGrant(
      mediaId: 'asset-video',
      status: 'granted',
      originalUrl: Uri.parse(
        'https://media.example.test/video.mp4?sign=$sign&t=1893456300',
      ),
      format: 'video/mp4',
      sizeBytes: 1024,
      expiresAt: _epoch.add(const Duration(minutes: 5)),
      ttlSeconds: 300,
      auditId: 'audit-video',
    );

final class _ScriptedGateway implements OriginalAccessQuotaGateway {
  _ScriptedGateway(this.respond);

  final Future<MediaOriginalAccessGrant> Function(int attempt) respond;
  int attempts = 0;

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) {
    attempts += 1;
    return respond(attempts);
  }
}

Widget _host(
  MediaDeliveryBinding binding, {
  required SignedMediaDeliveryCoordinator coordinator,
  bool useCustomTerminals = true,
}) {
  return ProviderScope(
    overrides: [
      signedMediaDeliveryCoordinatorProvider.overrideWithValue(coordinator),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: MediaDeliveryVideo(
          binding: binding,
          placeholder: useCustomTerminals
              ? const SizedBox(key: _placeholderKey)
              : null,
          errorWidget: useCustomTerminals
              ? const SizedBox(key: _errorKey)
              : null,
          absentWidget: useCustomTerminals
              ? const SizedBox(key: _absentKey)
              : null,
          publicBuilder: (_, _) => const SizedBox(key: _publicKey),
          signedBuilder: (_, delivery) =>
              SizedBox(key: _signedKey, child: _SignedDeliveryProbe(delivery)),
        ),
      ),
    ),
  );
}

final class _SignedDeliveryProbe extends StatelessWidget {
  const _SignedDeliveryProbe(this.delivery);

  final SignedVideoDelivery delivery;

  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}

void main() {
  SignedMediaDeliveryCoordinator coordinator(_ScriptedGateway gateway) =>
      SignedMediaDeliveryCoordinator(gateway: gateway, now: () => _epoch);

  testWidgets('signed grant resolves and one re-sign refreshes the player', (
    tester,
  ) async {
    final gateway = _ScriptedGateway(
      (attempt) async => _grant(sign: 'sig-$attempt'),
    );
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: coordinator(gateway),
      ),
    );
    expect(find.byKey(_placeholderKey), findsOneWidget);
    await tester.pump();
    await tester.pump();

    var probe = tester.widget<_SignedDeliveryProbe>(
      find.byType(_SignedDeliveryProbe),
    );
    expect(probe.delivery.deliveryUri.queryParameters['sign'], 'sig-1');
    expect(probe.delivery.cacheIdentity, 'signed|video|asset-video');
    expect(probe.delivery.assetId, 'asset-video');

    probe.delivery.onReSignRequested!();
    await tester.pump();
    await tester.pump();
    probe = tester.widget<_SignedDeliveryProbe>(
      find.byType(_SignedDeliveryProbe),
    );
    expect(probe.delivery.deliveryUri.queryParameters['sign'], 'sig-2');
    expect(gateway.attempts, 2);
  });

  testWidgets('second re-sign failure stops at the explicit terminal', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((attempt) async {
      if (attempt == 3) throw StateError('refresh rejected');
      return _grant(sign: 'sig-$attempt');
    });
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: coordinator(gateway),
      ),
    );
    await tester.pump();
    await tester.pump();

    var delivery = tester
        .widget<_SignedDeliveryProbe>(find.byType(_SignedDeliveryProbe))
        .delivery;
    delivery.onReSignRequested!();
    await tester.pump();
    await tester.pump();
    delivery = tester
        .widget<_SignedDeliveryProbe>(find.byType(_SignedDeliveryProbe))
        .delivery;
    delivery.onReSignRequested!();
    await tester.pump();
    await tester.pump();

    expect(find.byKey(_errorKey), findsOneWidget);
    expect(
      gateway.attempts,
      2,
      reason: 'automatic re-sign is bounded to one refresh',
    );
  });

  testWidgets('initial grant failure exposes retry and recovers', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((attempt) async {
      if (attempt == 1) throw StateError('grant unavailable');
      return _grant(sign: 'sig-recovered');
    });
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: coordinator(gateway),
        useCustomTerminals: false,
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byType(MediaDeliveryFailureState), findsOneWidget);
    await tester.tap(find.byType(MediaDeliveryFailureState));
    await tester.pump();
    await tester.pump();
    expect(find.byType(_SignedDeliveryProbe), findsOneWidget);
    expect(gateway.attempts, 2);
  });

  testWidgets('failed refresh reaches terminal and can resolve again', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((attempt) async {
      if (attempt == 2) throw StateError('refresh unavailable');
      return _grant(sign: 'sig-$attempt');
    });
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: coordinator(gateway),
        useCustomTerminals: false,
      ),
    );
    await tester.pump();
    await tester.pump();
    tester
        .widget<_SignedDeliveryProbe>(find.byType(_SignedDeliveryProbe))
        .delivery
        .onReSignRequested!();
    await tester.pump();
    await tester.pump();

    expect(find.byType(MediaDeliveryFailureState), findsOneWidget);
    await tester.tap(find.byType(MediaDeliveryFailureState));
    await tester.pump();
    await tester.pump();
    expect(find.byType(_SignedDeliveryProbe), findsOneWidget);
    expect(gateway.attempts, 3);
  });

  testWidgets('updating public delivery to signed starts resolution', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((_) async => _grant());
    final sut = coordinator(gateway);
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding.public(publicUrl: 'https://cdn.test/v.mp4'),
        coordinator: sut,
      ),
    );
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: sut,
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.byType(_SignedDeliveryProbe), findsOneWidget);

    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: sut,
      ),
    );
    expect(find.byType(_SignedDeliveryProbe), findsOneWidget);
  });

  testWidgets('empty public URL resolves to the absent terminal', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((_) async => _grant());
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding.public(publicUrl: '  '),
        coordinator: coordinator(gateway),
      ),
    );
    expect(find.byKey(_absentKey), findsOneWidget);
    expect(gateway.attempts, 0);
  });

  testWidgets('binding updates invalidate stale resolve results', (
    tester,
  ) async {
    final pending = Completer<MediaOriginalAccessGrant>();
    final gateway = _ScriptedGateway((_) => pending.future);
    final sut = coordinator(gateway);
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: sut,
      ),
    );
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding.public(publicUrl: 'https://cdn.test/v.mp4'),
        coordinator: sut,
      ),
    );
    pending.complete(_grant());
    await tester.pump();

    expect(find.byKey(_publicKey), findsOneWidget);
    expect(find.byKey(_signedKey), findsNothing);
  });

  testWidgets('disposed initial resolve ignores late success and failure', (
    tester,
  ) async {
    for (final fails in <bool>[false, true]) {
      final pending = Completer<MediaOriginalAccessGrant>();
      final gateway = _ScriptedGateway((_) => pending.future);
      await tester.pumpWidget(
        _host(
          const MediaDeliveryBinding(
            assetId: 'asset-video',
            accessMode: MediaDeliveryAccessMode.signedGrant,
            publicUrl: '',
          ),
          coordinator: coordinator(gateway),
        ),
      );
      await tester.pumpWidget(const SizedBox.shrink());
      if (fails) {
        pending.completeError(StateError('late failure'));
      } else {
        pending.complete(_grant());
      }
      await tester.pump();
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('disposed player ignores retained re-sign callback', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((_) async => _grant());
    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: 'asset-video',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: '',
        ),
        coordinator: coordinator(gateway),
      ),
    );
    await tester.pump();
    await tester.pump();
    final callback = tester
        .widget<_SignedDeliveryProbe>(find.byType(_SignedDeliveryProbe))
        .delivery
        .onReSignRequested!;
    await tester.pumpWidget(const SizedBox.shrink());
    callback();
    await tester.pump();
    expect(gateway.attempts, 1);
  });

  testWidgets('disposed player ignores late refresh success and failure', (
    tester,
  ) async {
    for (final fails in <bool>[false, true]) {
      final pending = Completer<MediaOriginalAccessGrant>();
      final gateway = _ScriptedGateway((attempt) {
        return attempt == 1 ? Future.value(_grant()) : pending.future;
      });
      await tester.pumpWidget(
        _host(
          const MediaDeliveryBinding(
            assetId: 'asset-video',
            accessMode: MediaDeliveryAccessMode.signedGrant,
            publicUrl: '',
          ),
          coordinator: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();
      tester
          .widget<_SignedDeliveryProbe>(find.byType(_SignedDeliveryProbe))
          .delivery
          .onReSignRequested!();
      await tester.pump();
      await tester.pumpWidget(const SizedBox.shrink());
      if (fails) {
        pending.completeError(StateError('late refresh failure'));
      } else {
        pending.complete(_grant(sign: 'late-refresh'));
      }
      await tester.pump();
      expect(tester.takeException(), isNull);
    }
  });

  testWidgets('image empty public URL and compact failure render terminals', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Column(
          children: <Widget>[
            MediaDeliveryImage(
              binding: const MediaDeliveryBinding.public(publicUrl: '  '),
              kind: MediaDeliveryKind.image,
              publicBuilder: (_, _) => const SizedBox(key: _publicKey),
            ),
            const SizedBox(
              width: 20,
              height: 20,
              child: MediaDeliveryFailureState(),
            ),
          ],
        ),
      ),
    );

    expect(find.byKey(_publicKey), findsNothing);
    expect(find.byType(Icon), findsOneWidget);
  });

  testWidgets('public, absent and invalid private bindings stay independent', (
    tester,
  ) async {
    final gateway = _ScriptedGateway((_) async => _grant());
    final sut = coordinator(gateway);

    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding.public(publicUrl: 'https://cdn.test/v.mp4'),
        coordinator: sut,
      ),
    );
    expect(find.byKey(_publicKey), findsOneWidget);

    await tester.pumpWidget(
      _host(const MediaDeliveryBinding.absent(), coordinator: sut),
    );
    expect(find.byKey(_absentKey), findsOneWidget);

    await tester.pumpWidget(
      _host(
        const MediaDeliveryBinding(
          assetId: '',
          accessMode: MediaDeliveryAccessMode.signedGrant,
          publicUrl: 'https://cdn.test/private.m3u8',
        ),
        coordinator: sut,
      ),
    );
    expect(find.byKey(_errorKey), findsOneWidget);
    expect(gateway.attempts, 0);
  });
}
