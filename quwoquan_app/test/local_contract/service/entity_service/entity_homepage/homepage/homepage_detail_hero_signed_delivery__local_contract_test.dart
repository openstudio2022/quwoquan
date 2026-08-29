// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// 对象主页 hero 封面的私有交付接线（DEC-033）结构锚点。
///
/// 本面的运行时装配依赖整页 shell 的 provider 图与远端投影，逐 widget pump 的
/// 代价远高于它能锚定的判据。这里锚定的是不可回潮的接线形状：交付形态只从
/// 投影声明读取、三个 hero 渲染位都经 typed 分流入口、没有任何一处按 URL
/// 形态反推交付形态。真实私有渲染由 app-content-uat 在 research 相位覆盖。
void main() {
  final root = Directory.current.path;
  final builders = File(
    '$root/lib/service/entity_service/entity_homepage/homepage/'
    'presentation/homepage_detail_shell_builders.dart',
  );
  final viewData = File(
    '$root/lib/service/entity_service/entity_homepage/homepage/'
    'application/public/homepage_view_data.dart',
  );

  test('detail 投影把 coverAssetId 与 coverAccessMode 带进 ViewData', () {
    final source = viewData.readAsStringSync();
    expect(source.contains('final String? coverAssetId;'), isTrue);
    expect(
      source.contains('final wire.MediaDeliveryAccessMode? coverAccessMode;'),
      isTrue,
    );
    // 映射不得丢字段：wire 有值而 ViewData 不接等于私有资产永远走公开路。
    expect(source.contains('coverAssetId: source.coverAssetId'), isTrue);
    expect(source.contains('coverAccessMode: source.coverAccessMode'), isTrue);
  });

  test('三个 hero 渲染位都经 typed 分流入口，且绑定只从投影声明构造', () {
    final source = builders.readAsStringSync();
    expect(source.contains('MediaDeliveryBinding _resolvedHeroBinding()'), isTrue);
    // 绑定的 accessMode 只能来自投影，不能是本地推断出来的常量。
    expect(source.contains('accessMode: detail.coverAccessMode'), isTrue);
    expect(source.contains('assetId: detail.coverAssetId?.trim()'), isTrue);

    for (final key in <String>[
      'homepage-identity-media',
      'homepage-detail-compact-avatar',
      'homepage-background-media',
    ]) {
      expect(
        source.contains(key),
        isTrue,
        reason: '$key 渲染位必须仍在场',
      );
    }
    // 三处 hero 都经 typed 分流入口：出现次数不得少于渲染位数量。跨对象消费面
    // 走组合根的转发函数而非直接构造该对象的私有表现件，故按入口名断言。
    expect(
      'mediaDeliveryImage('.allMatches(source).length,
      greaterThanOrEqualTo(3),
    );
  });

  test('hero 不再按裸 URL 直连公开图片原子', () {
    final source = builders.readAsStringSync();
    // AppMediaImage 只允许作为 publicBuilder 回调内的渲染委托出现。
    for (final line in source.split('\n')) {
      if (!line.contains('AppMediaImage(')) {
        continue;
      }
      expect(
        line.contains('publicBuilder') || line.trim().startsWith('AppMediaImage('),
        isTrue,
        reason: '直连公开图片原子的行必须位于 publicBuilder 委托内: $line',
      );
    }
    // 候选链只决定用哪个 URL，不得再直接把它当成渲染入参。
    expect(source.contains('imageSource: coverUrl'), isFalse);
  });
}
