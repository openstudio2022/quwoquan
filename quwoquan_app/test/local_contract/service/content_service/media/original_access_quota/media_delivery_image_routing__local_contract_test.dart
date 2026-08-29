// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart'
    show appImageLoadErrorKey;
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 兑换永不完成的 grant 网关替身：让私有路停在 resolving 占位。
///
/// 本用例只判「分流去了哪一路」，因此用真实 coordinator 加一个不回应的网关，
/// 以「网关是否被调用」作为分流去向的证据；grant 兑换语义由 coordinator 与
/// SignedGrantImage 各自的用例覆盖，这里不重复。
final class _StallingOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  final List<RequestContentMediaOriginalAccessCommand> commands =
      <RequestContentMediaOriginalAccessCommand>[];

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) {
    commands.add(command);
    return Completer<MediaOriginalAccessGrant>().future;
  }
}

const Key _publicKey = Key('public-delivery-rendered');
const Key _errorKey = Key('delivery-error-terminal');
const Key _absentKey = Key('delivery-absent-terminal');

class _Harness {
  _Harness(this.gateway);

  final _StallingOriginalAccessGateway gateway;
  int publicBuilderCalls = 0;

  /// 私有路的兑换尝试次数：分流去向的唯一证据。
  int get resolveAttempts => gateway.commands.length;

  Widget wrap(MediaDeliveryBinding binding) {
    return ProviderScope(
      overrides: [
        signedMediaDeliveryCoordinatorProvider.overrideWithValue(
          SignedMediaDeliveryCoordinator(gateway: gateway),
        ),
      ],
      child: CupertinoApp(
        home: CupertinoPageScaffold(
          child: Center(
            child: SizedBox(
              width: 120,
              height: 120,
              child: MediaDeliveryImage(
                binding: binding,
                kind: MediaDeliveryKind.image,
                width: 120,
                height: 120,
                errorWidget: const SizedBox(key: _errorKey),
                absentWidget: const SizedBox(key: _absentKey),
                publicBuilder: (context, publicUrl) {
                  publicBuilderCalls += 1;
                  return const SizedBox(key: _publicKey);
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

void main() {
  group('MediaDeliveryImage 四种输入形态各自独立判否', () {
    testWidgets('signedGrant 且资产身份在场：走私有短签路，不触达公开委托', (tester) async {
      final harness = _Harness(_StallingOriginalAccessGateway());
      await tester.pumpWidget(
        harness.wrap(
          const MediaDeliveryBinding(
            assetId: 'asset-1',
            accessMode: MediaDeliveryAccessMode.signedGrant,
            // 私有资产即使投影同时带公开 URL，也不得走公开路。
            publicUrl: 'https://media.example.test/public/decoy.jpg',
          ),
        ),
      );

      expect(find.byType(SignedGrantImage), findsOneWidget);
      expect(harness.resolveAttempts, 1);
      expect(harness.publicBuilderCalls, 0);
      expect(find.byKey(_publicKey), findsNothing);
    });

    testWidgets('signedGrant 但资产身份缺席：落判否终态，不回退公开路', (tester) async {
      final harness = _Harness(_StallingOriginalAccessGateway());
      await tester.pumpWidget(
        harness.wrap(
          const MediaDeliveryBinding(
            assetId: '',
            accessMode: MediaDeliveryAccessMode.signedGrant,
            publicUrl: 'https://media.example.test/public/decoy.jpg',
          ),
        ),
      );

      expect(find.byKey(_errorKey), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      // 授权判定不得因资产身份缺席被跳过。
      expect(harness.publicBuilderCalls, 0);
      expect(harness.resolveAttempts, 0);
      expect(find.byType(SignedGrantImage), findsNothing);
    });

    testWidgets('public 声明且公开 URL 在场：走公开委托，不触达 coordinator', (tester) async {
      final harness = _Harness(_StallingOriginalAccessGateway());
      await tester.pumpWidget(
        harness.wrap(
          const MediaDeliveryBinding(
            assetId: 'asset-1',
            accessMode: MediaDeliveryAccessMode.public,
            publicUrl: 'https://media.example.test/public/cover.jpg',
          ),
        ),
      );

      expect(find.byKey(_publicKey), findsOneWidget);
      expect(harness.publicBuilderCalls, 1);
      expect(harness.resolveAttempts, 0);
      expect(find.byType(SignedGrantImage), findsNothing);
    });

    testWidgets('契约缺席 accessMode（存量 public 投影）：走公开委托', (tester) async {
      final harness = _Harness(_StallingOriginalAccessGateway());
      await tester.pumpWidget(
        harness.wrap(
          const MediaDeliveryBinding(
            assetId: '',
            accessMode: null,
            publicUrl: 'https://media.example.test/public/cover.jpg',
          ),
        ),
      );

      expect(find.byKey(_publicKey), findsOneWidget);
      expect(harness.publicBuilderCalls, 1);
      expect(harness.resolveAttempts, 0);
    });

    testWidgets('公开 URL 也缺席：落缺席终态，不猜一条 URL', (tester) async {
      final harness = _Harness(_StallingOriginalAccessGateway());
      await tester.pumpWidget(
        harness.wrap(const MediaDeliveryBinding.absent()),
      );

      expect(find.byKey(_absentKey), findsOneWidget);
      expect(harness.publicBuilderCalls, 0);
      expect(harness.resolveAttempts, 0);
      // 缺席与失败是两个状态，不得共用判否终态件。
      expect(find.byKey(_errorKey), findsNothing);
    });
  });
}
