// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  final epoch = DateTime.utc(2030, 1, 1);

  MediaOriginalAccessGrant grant({
    String mediaId = 'asset-1',
    String originalUrl =
        'https://media.example.test/media/objects/sha256/aa/bb/cafe.jpg'
        '?sign=abc123&t=1893456300',
    DateTime? expiresAt,
    int ttlSeconds = 300,
  }) {
    return MediaOriginalAccessGrant(
      mediaId: mediaId,
      status: 'granted',
      originalUrl: Uri.parse(originalUrl),
      format: 'image/jpeg',
      sizeBytes: 1024,
      expiresAt: expiresAt ?? epoch.add(Duration(seconds: ttlSeconds)),
      ttlSeconds: ttlSeconds,
      auditId: 'audit-1',
    );
  }

  test('成功兑换：委托 gateway（purpose=view）并产出稳定缓存身份的租约', () async {
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => grant(ttlSeconds: 300),
    );
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    final lease = await coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );

    expect(gateway.commands, hasLength(1));
    expect(gateway.commands.single.mediaId, 'asset-1');
    expect(gateway.commands.single.purpose, MediaOriginalAccessPurpose.view);
    expect(lease.assetId, 'asset-1');
    expect(lease.kind, MediaDeliveryKind.image);
    expect(lease.deliveryUri.queryParameters['sign'], 'abc123');
    expect(lease.expiresAt, epoch.add(const Duration(seconds: 300)));
    // 缓存身份不含签名 query：签名轮换不得导致缓存失效。
    expect(lease.cacheIdentity, 'signed|image|asset-1');
    expect(lease.cacheIdentity.contains('abc123'), isFalse);
    expect(lease.cacheIdentity.contains('?'), isFalse);
  });

  test('空资产标识 fail closed，抛 typed 异常而不是返回 null', () async {
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => fail('空资产标识不得触达 gateway'),
    );
    final coordinator = SignedMediaDeliveryCoordinator(gateway: gateway);

    await expectLater(
      coordinator.resolve(
        assetId: '   ',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.signedGrant,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.emptyAssetId),
    );
    expect(gateway.commands, isEmpty);
  });

  test('公开资产（accessMode=public）不经本层，直接拒绝', () async {
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => fail('public 资产不得触达 gateway'),
    );
    final coordinator = SignedMediaDeliveryCoordinator(gateway: gateway);

    await expectLater(
      coordinator.resolve(
        assetId: 'asset-1',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.public,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.publicAccessMode),
    );
    expect(gateway.commands, isEmpty);
  });

  test('单飞合并：同一资产的并发请求共享同一次 gateway 兑换', () async {
    final completer = Completer<MediaOriginalAccessGrant>();
    final gateway = _ScriptedOriginalAccessGateway((_) => completer.future);
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    final first = coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );
    final second = coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );

    expect(gateway.commands, hasLength(1));
    completer.complete(grant());
    final leases = await Future.wait(<Future<SignedMediaDeliveryLease>>[
      first,
      second,
    ]);
    expect(identical(leases[0], leases[1]), isTrue);
    expect(gateway.commands, hasLength(1));
  });

  test('TTL 复用与到期换签：安全窗（min(30s, ttl×20%)）内复用，过窗重新兑换', () async {
    // ttl=300s → 余量 min(30s, 60s)=30s → 复用窗截止 epoch+270s。
    var issued = 0;
    final gateway = _ScriptedOriginalAccessGateway((_) async {
      issued += 1;
      return grant(ttlSeconds: 300);
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    Future<SignedMediaDeliveryLease> resolve() => coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );

    await resolve();
    clock.current = epoch.add(const Duration(seconds: 269));
    await resolve();
    expect(issued, 1, reason: '复用窗内不得重复兑换');

    clock.current = epoch.add(const Duration(seconds: 270));
    await resolve();
    expect(issued, 2, reason: '到达复用窗边界必须重新兑换');
  });

  test('短 TTL 余量按 ttl×20% 收敛：ttl=60s 时余量为 12s', () async {
    // ttl=60s → 余量 min(30s, 12s)=12s → 复用窗截止 epoch+48s。
    var issued = 0;
    final gateway = _ScriptedOriginalAccessGateway((_) async {
      issued += 1;
      return grant(ttlSeconds: 60);
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    Future<SignedMediaDeliveryLease> resolve() => coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );

    await resolve();
    clock.current = epoch.add(const Duration(seconds: 47));
    await resolve();
    expect(issued, 1);

    clock.current = epoch.add(const Duration(seconds: 48));
    await resolve();
    expect(issued, 2);
  });

  test('响应 mediaId 与请求资产标识漂移时 fail closed', () async {
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => grant(mediaId: 'asset-other'),
    );
    final coordinator = SignedMediaDeliveryCoordinator(gateway: gateway);

    await expectLater(
      coordinator.resolve(
        assetId: 'asset-1',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.signedGrant,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.grantIdentityMismatch),
    );
  });

  test('非 https 交付 URL fail closed', () async {
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => grant(
        originalUrl:
            'http://media.example.test/media/objects/sha256/aa/bb/cafe.jpg'
            '?sign=abc&t=1893456300',
      ),
    );
    final coordinator = SignedMediaDeliveryCoordinator(gateway: gateway);

    await expectLater(
      coordinator.resolve(
        assetId: 'asset-1',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.signedGrant,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.insecureDeliveryUri),
    );
  });

  test('交付 URL 缺 sign 或缺 t 均 fail closed', () async {
    final coordinatorMissingSign = SignedMediaDeliveryCoordinator(
      gateway: _ScriptedOriginalAccessGateway(
        (_) async => grant(
          originalUrl:
              'https://media.example.test/media/objects/sha256/aa/bb/cafe.jpg'
              '?t=1893456300',
        ),
      ),
    );
    await expectLater(
      coordinatorMissingSign.resolve(
        assetId: 'asset-1',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.signedGrant,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.incompleteSignatureQuery),
    );

    final coordinatorMissingExpiry = SignedMediaDeliveryCoordinator(
      gateway: _ScriptedOriginalAccessGateway(
        (_) async => grant(
          originalUrl:
              'https://media.example.test/media/objects/sha256/aa/bb/cafe.jpg'
              '?sign=abc123',
        ),
      ),
    );
    await expectLater(
      coordinatorMissingExpiry.resolve(
        assetId: 'asset-1',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.signedGrant,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.incompleteSignatureQuery),
    );
  });

  test('grant 到达时已过期 fail closed', () async {
    final clock = _ManualClock(epoch);
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => grant(expiresAt: epoch.subtract(const Duration(seconds: 1))),
    );
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    await expectLater(
      coordinator.resolve(
        assetId: 'asset-1',
        kind: MediaDeliveryKind.image,
        accessMode: MediaDeliveryAccessMode.signedGrant,
      ),
      _throwsFailure(SignedMediaDeliveryFailure.expiredGrant),
    );
  });

  test('gateway 失败原样传播且不落缓存，重试重新兑换', () async {
    var calls = 0;
    final gateway = _ScriptedOriginalAccessGateway((_) async {
      calls += 1;
      if (calls == 1) {
        throw StateError('quota exhausted');
      }
      return grant();
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    Future<SignedMediaDeliveryLease> resolve() => coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );

    await expectLater(resolve(), throwsStateError);
    final lease = await resolve();
    expect(calls, 2, reason: '失败不得缓存，重试必须重新触达 gateway');
    expect(lease.assetId, 'asset-1');
  });

  test('租约缓存有界：超出上限按 LRU 逐出，命中会刷新访问序', () async {
    final issuedAssetIds = <String>[];
    final gateway = _ScriptedOriginalAccessGateway((command) async {
      issuedAssetIds.add(command.mediaId);
      return grant(mediaId: command.mediaId);
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
      maxCachedLeases: 2,
    );

    Future<SignedMediaDeliveryLease> resolve(String assetId) =>
        coordinator.resolve(
          assetId: assetId,
          kind: MediaDeliveryKind.image,
          accessMode: MediaDeliveryAccessMode.signedGrant,
        );

    await resolve('asset-a'); // 缓存 [a]
    await resolve('asset-b'); // 缓存 [a, b]
    await resolve('asset-a'); // 命中，访问序变 [b, a]
    await resolve('asset-c'); // 超上限，逐出最久未用的 b → [a, c]
    expect(issuedAssetIds, <String>['asset-a', 'asset-b', 'asset-c']);

    await resolve('asset-a'); // 仍在缓存，不重新兑换
    expect(issuedAssetIds, hasLength(3));

    await resolve('asset-b'); // 已被逐出，必须重新兑换
    expect(issuedAssetIds, <String>[
      'asset-a',
      'asset-b',
      'asset-c',
      'asset-b',
    ]);
  });

  test('refresh 丢弃该键缓存重新兑换，新租约照常落缓存参与后续复用', () async {
    var issued = 0;
    final gateway = _ScriptedOriginalAccessGateway((_) async {
      issued += 1;
      return grant(
        originalUrl:
            'https://media.example.test/media/objects/sha256/aa/bb/cafe.jpg'
            '?sign=sign-$issued&t=1893456300',
      );
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    final first = await coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );
    expect(first.deliveryUri.queryParameters['sign'], 'sign-1');

    // 字节 GET 被交付边缘拒绝后强制换签：绕过缓存重新兑换，签名更新。
    final refreshed = await coordinator.refresh(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
    );
    expect(issued, 2, reason: 'refresh 必须绕过缓存重新触达 gateway');
    expect(refreshed.deliveryUri.queryParameters['sign'], 'sign-2');
    // 缓存身份保持稳定：换签不得改变缓存键。
    expect(refreshed.cacheIdentity, first.cacheIdentity);

    // 新租约照常落缓存：安全窗内的后续 resolve 复用，不再兑换。
    final reused = await coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );
    expect(issued, 2);
    expect(reused.deliveryUri.queryParameters['sign'], 'sign-2');
  });

  test('refresh 只作用于该键，不影响其他资产的缓存租约', () async {
    final issuedAssetIds = <String>[];
    final gateway = _ScriptedOriginalAccessGateway((command) async {
      issuedAssetIds.add(command.mediaId);
      return grant(mediaId: command.mediaId);
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    Future<SignedMediaDeliveryLease> resolve(String assetId) =>
        coordinator.resolve(
          assetId: assetId,
          kind: MediaDeliveryKind.image,
          accessMode: MediaDeliveryAccessMode.signedGrant,
        );

    await resolve('asset-a');
    await resolve('asset-b');
    await coordinator.refresh(
      assetId: 'asset-a',
      kind: MediaDeliveryKind.image,
    );
    expect(issuedAssetIds, <String>['asset-a', 'asset-b', 'asset-a']);

    // asset-b 的缓存租约不受影响，仍然复用。
    await resolve('asset-b');
    expect(issuedAssetIds, hasLength(3));
  });

  test('refresh 空资产标识 fail closed，不触达 gateway', () async {
    final gateway = _ScriptedOriginalAccessGateway(
      (_) async => fail('空资产标识不得触达 gateway'),
    );
    final coordinator = SignedMediaDeliveryCoordinator(gateway: gateway);

    await expectLater(
      coordinator.refresh(assetId: '   ', kind: MediaDeliveryKind.image),
      _throwsFailure(SignedMediaDeliveryFailure.emptyAssetId),
    );
    expect(gateway.commands, isEmpty);
  });

  test('refresh 校验链路与 resolve 同源：响应漂移 fail closed 且失败不落缓存', () async {
    var calls = 0;
    final gateway = _ScriptedOriginalAccessGateway((_) async {
      calls += 1;
      if (calls == 2) {
        return grant(mediaId: 'asset-other');
      }
      return grant();
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    await coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );
    await expectLater(
      coordinator.refresh(assetId: 'asset-1', kind: MediaDeliveryKind.image),
      _throwsFailure(SignedMediaDeliveryFailure.grantIdentityMismatch),
    );

    // 失败不落缓存：refresh 已丢弃旧租约，后续 resolve 必须重新兑换。
    await coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );
    expect(calls, 3);
  });

  test('clearAll 清空租约缓存，后续请求重新兑换', () async {
    var issued = 0;
    final gateway = _ScriptedOriginalAccessGateway((_) async {
      issued += 1;
      return grant();
    });
    final clock = _ManualClock(epoch);
    final coordinator = SignedMediaDeliveryCoordinator(
      gateway: gateway,
      now: clock.now,
    );

    Future<SignedMediaDeliveryLease> resolve() => coordinator.resolve(
      assetId: 'asset-1',
      kind: MediaDeliveryKind.image,
      accessMode: MediaDeliveryAccessMode.signedGrant,
    );

    await resolve();
    coordinator.clearAll();
    await resolve();
    expect(issued, 2);
  });
}

Matcher _throwsFailure(SignedMediaDeliveryFailure failure) => throwsA(
  isA<SignedMediaDeliveryException>().having(
    (exception) => exception.failure,
    'failure',
    failure,
  ),
);

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

/// 手动推进的测试时钟：TTL 复用与到期换签断言不依赖真实时间。
final class _ManualClock {
  _ManualClock(this.current);

  DateTime current;

  DateTime now() => current;
}
