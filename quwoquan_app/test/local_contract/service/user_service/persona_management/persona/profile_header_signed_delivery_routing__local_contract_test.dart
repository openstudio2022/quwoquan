// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_failure_state.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_header.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        MediaDeliveryAccessMode,
        MediaOriginalAccessGrant,
        RequestContentMediaOriginalAccessCommand;

/// 对象级 typed double：grant 兑换永挂起，让 SignedGrantImage 停在占位态。
/// 接线测试只断言「typed 声明分流到桥接原子」，不消费兑换结果。
final class _HangingOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  final Completer<MediaOriginalAccessGrant> _never =
      Completer<MediaOriginalAccessGrant>();

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => _never.future;
}

final class _FailingOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  int attempts = 0;

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) async {
    attempts += 1;
    throw StateError('signed avatar unavailable');
  }
}

Widget _host(ProfileHeader header, {OriginalAccessQuotaGateway? gateway}) {
  return ProviderScope(
    overrides: [
      signedMediaDeliveryCoordinatorProvider.overrideWithValue(
        SignedMediaDeliveryCoordinator(
          gateway: gateway ?? _HangingOriginalAccessGateway(),
        ),
      ),
    ],
    child: CupertinoApp(
      home: CupertinoPageScaffold(child: SingleChildScrollView(child: header)),
    ),
  );
}

void main() {
  testWidgets('signedGrant persona 头像分流到 SignedGrantImage（kind=avatar）', (
    tester,
  ) async {
    await tester.pumpWidget(
      _host(
        const ProfileHeader(
          isDark: false,
          // 私有头像的 URL 为相对 objectKey，分流只认 typed 声明。
          avatarUrl: 'media/avatar/private-persona.jpg',
          avatarAssetId: 'asset-persona-avatar-1',
          avatarAccessMode: MediaDeliveryAccessMode.signedGrant,
          displayName: 'Signed Persona',
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    final signed = tester.widget<SignedGrantImage>(
      find.byType(SignedGrantImage),
    );
    expect(signed.assetId, 'asset-persona-avatar-1');
    expect(signed.kind, MediaDeliveryKind.avatar);
    expect(find.byType(AppAvatarImage), findsNothing);
  });

  testWidgets('URL-less signedGrant persona 头像仍进入 typed 私有路', (tester) async {
    await tester.pumpWidget(
      _host(
        const ProfileHeader(
          isDark: false,
          avatarUrl: '',
          avatarAssetId: 'asset-persona-avatar-url-less',
          avatarAccessMode: MediaDeliveryAccessMode.signedGrant,
          displayName: 'URL-less Persona',
        ),
      ),
    );
    await tester.pump();

    final signed = tester.widget<SignedGrantImage>(
      find.byType(SignedGrantImage),
    );
    expect(signed.assetId, 'asset-persona-avatar-url-less');
    expect(find.byType(AppAvatarImage), findsNothing);
  });

  testWidgets('signedGrant persona 失败呈现可见重试并可再次兑换', (tester) async {
    final gateway = _FailingOriginalAccessGateway();
    await tester.pumpWidget(
      _host(
        const ProfileHeader(
          isDark: false,
          avatarUrl: '',
          avatarAssetId: 'asset-persona-avatar-failed',
          avatarAccessMode: MediaDeliveryAccessMode.signedGrant,
          displayName: 'Failed Persona',
        ),
        gateway: gateway,
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
    expect(find.byType(MediaDeliveryFailureState), findsOneWidget);
    expect(gateway.attempts, 1);

    await tester.tap(find.byKey(appImageLoadErrorKey));
    await tester.pump();
    await tester.pump();
    expect(gateway.attempts, 2);
    expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
  });

  testWidgets('public persona 头像维持既有 AppAvatarImage 路径', (tester) async {
    await tester.pumpWidget(
      _host(
        const ProfileHeader(
          isDark: false,
          avatarUrl: 'https://cdn.example.test/avatar-public.jpg',
          displayName: 'Public Persona',
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byType(SignedGrantImage), findsNothing);
    expect(find.byType(AppAvatarImage), findsOneWidget);
  });
}
