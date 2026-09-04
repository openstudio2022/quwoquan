// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';

final DateTime _epoch = DateTime.utc(2030, 1, 1);

MediaOriginalAccessGrant _grant({
  String mediaId = 'asset-1',
  String sign = 'sig-a',
  int ttlSeconds = 300,
}) {
  return MediaOriginalAccessGrant(
    mediaId: mediaId,
    status: 'granted',
    originalUrl: Uri.parse(
      'https://media.example.test/media/objects/sha256/aa/bb/cafe.jpg'
      '?sign=$sign&t=1893456300',
    ),
    format: 'image/jpeg',
    sizeBytes: 1024,
    expiresAt: _epoch.add(Duration(seconds: ttlSeconds)),
    ttlSeconds: ttlSeconds,
    auditId: 'audit-1',
  );
}

Widget _wrap(Widget child, {required SignedMediaDeliveryCoordinator sut}) {
  return ProviderScope(
    overrides: [signedMediaDeliveryCoordinatorProvider.overrideWithValue(sut)],
    child: CupertinoApp(
      home: CupertinoPageScaffold(
        child: Center(child: SizedBox(width: 120, height: 120, child: child)),
      ),
    ),
  );
}

class _FakePathProviderPlatform extends PathProviderPlatform {
  _FakePathProviderPlatform(this.root);

  final Directory root;

  String _path(String name) {
    final directory = Directory('${root.path}/$name')
      ..createSync(recursive: true);
    return directory.path;
  }

  @override
  Future<String?> getTemporaryPath() async => _path('tmp');

  @override
  Future<String?> getApplicationSupportPath() async => _path('support');

  @override
  Future<String?> getApplicationDocumentsPath() async => _path('documents');

  @override
  Future<String?> getApplicationCachePath() async => _path('cache');
}

/// 对象级 typed double：按注入脚本响应 grant 兑换并记录全部命令。
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory cacheTestRoot;
  late PathProviderPlatform previousPathProvider;

  setUpAll(() {
    ensureSqfliteFfiInitialized();
    previousPathProvider = PathProviderPlatform.instance;
    cacheTestRoot = Directory.systemTemp.createTempSync(
      'qwq-signed-grant-image-test-',
    );
    PathProviderPlatform.instance = _FakePathProviderPlatform(cacheTestRoot);
  });

  tearDownAll(() {
    PathProviderPlatform.instance = previousPathProvider;
    try {
      if (cacheTestRoot.existsSync()) {
        cacheTestRoot.deleteSync(recursive: true);
      }
    } on FileSystemException catch (error) {
      if (error.osError?.errorCode != 2) {
        rethrow;
      }
    }
  });

  SignedMediaDeliveryCoordinator coordinator(
    _ScriptedOriginalAccessGateway gateway,
  ) {
    return SignedMediaDeliveryCoordinator(gateway: gateway, now: () => _epoch);
  }

  group('SignedGrantImage', () {
    testWidgets('signedGrant 兑换成功后渲染短签 URL，缓存键为稳定资产身份', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway((_) async => _grant());
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
            fit: BoxFit.cover,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, hasLength(1));
      expect(gateway.commands.single.mediaId, 'asset-1');
      expect(gateway.commands.single.purpose, MediaOriginalAccessPurpose.view);

      final image = tester.widget<AppCachedNetworkImage>(
        find.byType(AppCachedNetworkImage),
      );
      expect(image.imageUrl, contains('sign=sig-a'));
      // 短签 URL 单候选直传：不进入公开候选推导与 CDN 变体处理。
      expect(image.imageUrlCandidates, <String>[image.imageUrl]);
      expect(image.cdnPreset, CdnImagePreset.none);
      // 稳定缓存身份：签名 query 不参与缓存键，并透传到底层网络图片组件。
      expect(image.cacheKey, 'signed|image|asset-1');
      final cached = tester.widget<CachedNetworkImage>(
        find.byType(CachedNetworkImage),
      );
      expect(cached.cacheKey, 'signed|image|asset-1');
    });

    testWidgets('兑换等待中渲染占位，不出现错误态与成功态', (tester) async {
      final completer = Completer<MediaOriginalAccessGrant>();
      final gateway = _ScriptedOriginalAccessGateway((_) => completer.future);
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();

      expect(gateway.commands, hasLength(1));
      expect(find.byKey(appImageLoadPlaceholderKey), findsOneWidget);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
      expect(find.byKey(appImageLoadSuccessKey), findsNothing);
      expect(find.byType(AppCachedNetworkImage), findsNothing);

      // 收尾：完成挂起的兑换，避免悬挂 future 泄漏到后续用例。
      completer.complete(_grant());
      await tester.pump();
    });

    testWidgets('兑换失败渲染显式错误恢复态，不吞成 public 回退', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => throw StateError('quota exhausted'),
      );
      final failures = <Object>[];
      await tester.pumpWidget(
        _wrap(
          SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
            onLoadFailed: failures.add,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.byKey(appImageLoadPlaceholderKey), findsNothing);
      // 失败不得回退为任何公开 URL 渲染：树中不存在网络图片组件。
      expect(find.byType(AppCachedNetworkImage), findsNothing);
      expect(failures, hasLength(1));
      expect(failures.single, isA<StateError>());
    });

    testWidgets('字节 GET 失败后单次强制换签重试成功，渲染新签名 URL', (tester) async {
      var issued = 0;
      final gateway = _ScriptedOriginalAccessGateway((_) async {
        issued += 1;
        return _grant(sign: 'sig-$issued');
      });
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      final firstImage = tester.widget<AppCachedNetworkImage>(
        find.byType(AppCachedNetworkImage),
      );
      expect(firstImage.imageUrl, contains('sign=sig-1'));

      // 模拟签名字节 GET 被交付边缘拒绝（401/403 归入加载失败回调）。
      firstImage.onLoadFailed!(Exception('HTTP 401'));
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, hasLength(2), reason: '单次强制换签必须重新兑换一次');
      final retriedImage = tester.widget<AppCachedNetworkImage>(
        find.byType(AppCachedNetworkImage),
      );
      expect(retriedImage.imageUrl, contains('sign=sig-2'));
      // 换签不改变稳定缓存身份。
      expect(retriedImage.cacheKey, 'signed|image|asset-1');
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
    });

    testWidgets('单次换签重试后字节仍失败进入错误态，不再循环兑换', (tester) async {
      var issued = 0;
      final gateway = _ScriptedOriginalAccessGateway((_) async {
        issued += 1;
        return _grant(sign: 'sig-$issued');
      });
      final failures = <Object>[];
      await tester.pumpWidget(
        _wrap(
          SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
            onLoadFailed: failures.add,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      // 第一次字节失败：触发单次换签。
      tester
          .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
          .onLoadFailed!(Exception('HTTP 401'));
      await tester.pump();
      await tester.pump();
      expect(gateway.commands, hasLength(2));

      // 换签后字节仍失败：停在显式错误态，不发起第三次兑换。
      tester
          .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
          .onLoadFailed!(Exception('HTTP 403'));
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, hasLength(2), reason: '重试仅允许一次，禁止循环换签');
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.byType(AppCachedNetworkImage), findsNothing);
      expect(failures, hasLength(1));
    });

    testWidgets('强制换签本身失败同样进入错误态', (tester) async {
      var issued = 0;
      final gateway = _ScriptedOriginalAccessGateway((_) async {
        issued += 1;
        if (issued > 1) {
          throw StateError('refresh rejected');
        }
        return _grant();
      });
      final failures = <Object>[];
      await tester.pumpWidget(
        _wrap(
          SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
            onLoadFailed: failures.add,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      tester
          .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
          .onLoadFailed!(Exception('HTTP 401'));
      await tester.pump();
      await tester.pump();

      expect(gateway.commands, hasLength(2));
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(failures, hasLength(1));
      expect(failures.single, isA<StateError>());
    });

    testWidgets('public 与缺席 accessMode 不触达 coordinator，呈现错误态', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => fail('public/缺席绑定不得触达 coordinator'),
      );
      final sut = coordinator(gateway);

      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.public,
          ),
          sut: sut,
        ),
      );
      await tester.pump();
      expect(gateway.commands, isEmpty);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);

      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: null,
          ),
          sut: sut,
        ),
      );
      await tester.pump();
      expect(gateway.commands, isEmpty);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.byType(AppCachedNetworkImage), findsNothing);
    });

    testWidgets('空资产标识不触达 coordinator，呈现错误态', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => fail('空资产标识不得触达 coordinator'),
      );
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: '   ',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();

      expect(gateway.commands, isEmpty);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
    });

    testWidgets('二次失败停在终态，但终态带恢复动作可由用户点击重新兑换', (tester) async {
      var attempt = 0;
      final gateway = _ScriptedOriginalAccessGateway((_) async {
        attempt += 1;
        // 前两次（首次兑换 + 自动强制换签）都失败，把组件推到终态；
        // 用户点击后的第三次成功，证明终态不是死胡同。
        if (attempt <= 2) {
          throw StateError('quota exhausted');
        }
        return _grant(sign: 'sig-recovered');
      });
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      // 首次兑换即失败，直接落终态；自动换签只在字节 GET 失败后发生，
      // 因此此处尝试次数仍为 1，不得出现自动循环。
      expect(attempt, 1);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.text(MediaText.signedDeliveryFailedMessage), findsOneWidget);
      expect(find.text(MediaText.signedDeliveryRetryAction), findsOneWidget);

      // 用户驱动的恢复：点击终态重新兑换。第二次仍失败，仍停在终态。
      await tester.tap(find.byKey(appImageLoadErrorKey));
      await tester.pump();
      await tester.pump();
      expect(attempt, 2);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);

      // 再次点击，这次兑换成功：终态可恢复，不是永久不可用。
      await tester.tap(find.byKey(appImageLoadErrorKey));
      await tester.pump();
      await tester.pump();
      expect(attempt, 3);
      expect(find.byKey(appImageLoadErrorKey), findsNothing);
      final image = tester.widget<AppCachedNetworkImage>(
        find.byType(AppCachedNetworkImage),
      );
      expect(image.imageUrl, contains('sign=sig-recovered'));
    });

    testWidgets('组件销毁后忽略首次兑换的迟到成功与失败', (tester) async {
      for (final fails in <bool>[false, true]) {
        final pending = Completer<MediaOriginalAccessGrant>();
        final gateway = _ScriptedOriginalAccessGateway((_) => pending.future);
        await tester.pumpWidget(
          _wrap(
            const SignedGrantImage(
              assetId: 'asset-1',
              kind: MediaDeliveryKind.image,
              accessMode: MediaDeliveryAccessMode.signedGrant,
            ),
            sut: coordinator(gateway),
          ),
        );
        await tester.pumpWidget(const SizedBox.shrink());
        if (fails) {
          pending.completeError(StateError('late grant failure'));
        } else {
          pending.complete(_grant());
        }
        await tester.pump();
        expect(tester.takeException(), isNull);
      }
    });

    testWidgets('销毁后保留的字节失败回调不再触发换签', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway((_) async => _grant());
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();
      final callback = tester
          .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
          .onLoadFailed!;
      await tester.pumpWidget(const SizedBox.shrink());
      callback(StateError('late byte failure'));
      await tester.pump();
      expect(gateway.commands, hasLength(1));
    });

    testWidgets('旧绑定的字节失败 microtask 不得覆盖新代际', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway((_) async => _grant());
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();
      final callback = tester
          .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
          .onLoadFailed!;
      final dynamic state = tester.state(find.byType(SignedGrantImage));
      callback(StateError('old generation failure'));
      state.didUpdateWidget(
        const SignedGrantImage(
          assetId: 'old-asset',
          kind: MediaDeliveryKind.image,
          accessMode: MediaDeliveryAccessMode.signedGrant,
        ),
      );
      await tester.pump();
      expect(gateway.commands, hasLength(1));
      expect(find.byType(AppCachedNetworkImage), findsOneWidget);
    });

    testWidgets('组件销毁后忽略换签的迟到成功与失败', (tester) async {
      for (final fails in <bool>[false, true]) {
        final pending = Completer<MediaOriginalAccessGrant>();
        var attempt = 0;
        final gateway = _ScriptedOriginalAccessGateway((_) {
          attempt += 1;
          return attempt == 1 ? Future.value(_grant()) : pending.future;
        });
        await tester.pumpWidget(
          _wrap(
            const SignedGrantImage(
              assetId: 'asset-1',
              kind: MediaDeliveryKind.image,
              accessMode: MediaDeliveryAccessMode.signedGrant,
            ),
            sut: coordinator(gateway),
          ),
        );
        await tester.pump();
        await tester.pump();
        tester
            .widget<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
            .onLoadFailed!(StateError('refresh needed'));
        await tester.pump();
        expect(attempt, 2);
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

    testWidgets('readyBuilder 获得校验后的短签地址与稳定缓存身份', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway((_) async => _grant());
      await tester.pumpWidget(
        _wrap(
          SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            accessMode: MediaDeliveryAccessMode.signedGrant,
            readyBuilder: (context, deliveryUrl, cacheIdentity) => Text(
              '$deliveryUrl|$cacheIdentity',
              textDirection: TextDirection.ltr,
            ),
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(find.textContaining('sign=sig-a'), findsOneWidget);
      expect(find.textContaining('signed|image|asset-1'), findsOneWidget);
      expect(find.byType(AppCachedNetworkImage), findsNothing);
    });

    testWidgets('调用方分流契约误用的终态不给恢复动作', (tester) async {
      final gateway = _ScriptedOriginalAccessGateway(
        (_) async => fail('契约误用不得触达 coordinator'),
      );
      await tester.pumpWidget(
        _wrap(
          const SignedGrantImage(
            assetId: 'asset-1',
            kind: MediaDeliveryKind.image,
            // public 绑定不应进入本原子：重试不会让它变成私有交付。
            accessMode: MediaDeliveryAccessMode.public,
          ),
          sut: coordinator(gateway),
        ),
      );
      await tester.pump();

      expect(gateway.commands, isEmpty);
      expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
      expect(find.text(MediaText.signedDeliveryRetryAction), findsNothing);

      // 点击不得触发兑换：这类判否不可由用户重试消解。
      await tester.tap(find.byKey(appImageLoadErrorKey));
      await tester.pump();
      expect(gateway.commands, isEmpty);
    });
  });
}
