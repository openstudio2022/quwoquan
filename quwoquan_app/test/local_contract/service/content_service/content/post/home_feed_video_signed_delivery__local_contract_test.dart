import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// 首页信息流视频侧交付判定的验收锚点（DEC-033）。
///
/// 两条语义都靠源码结构锚定，而不是把视频卡整棵树 pump 起来：视频卡依赖播放器、
/// 可见性网关与埋点端口，其行为级覆盖属 media_asset 的既有 suite。这里要钉住的
/// 是「取哪个资产身份、私有走哪条路」这两个判定不被悄悄改回去。
void main() {
  final source = File(
    'lib/service/content_service/content/post/presentation/home_multi_form_feed_media_grid.dart',
  ).readAsStringSync();

  test('视频资产身份不以 post 标识冒充', () {
    // 封面侧已锁定禁止该冒充；视频侧同禁，否则缓存与埋点按错误身份归并。
    expect(
      source.contains('mediaAssetId.isEmpty ? dto.id : mediaAssetId'),
      isFalse,
      reason: '视频交付引用不得以 dto.id 兜底冒充媒体资产标识',
    );
    expect(source.contains('assetId: mediaAssetId,'), isTrue);
  });

  test('私有视频经 typed 分流入口播放，判据取自投影声明', () {
    // 私有视频按公开地址播放会跳过授权判定；分流判据只允许来自投影 accessMode，
    // 不允许端侧从 URL 形态反推。
    expect(
      source.contains('mediaDeliveryVideo('),
      isTrue,
      reason: '视频消费点必须经 typed 分流入口，不再自写 accessMode 三元判断；'
          '跨对象消费面经组合根转发函数取用该入口',
    );
    expect(
      source.contains('accessMode: videoDelivery?.accessMode'),
      isTrue,
      reason: '私有判据取自投影声明，不由端侧猜测',
    );
    expect(
      source.contains('signedBuilder:'),
      isTrue,
      reason: '私有路必须有真实播放委托，而不是停在判否终态',
    );
  });

  test('公开与私有两路都不把封面退回裸 URL', () {
    // 同一封面在播放态由 typed 绑定交付，静态态若改回裸 URL，私有封面就会在
    // 未播放时空图——两态必须同源。
    expect(source.contains('coverBinding: coverBinding'), isTrue);
    expect(
      source.contains('thumbnailUrl:'),
      isFalse,
      reason: '封面不得回潮为裸 URL 入参',
    );
  });

  test('私有视频不再落「暂时无法播放」终态', () {
    // 端侧短签渐进式 MP4 通道已就位，旧的能力缺口判否若残留，会把可播放的私有
    // 视频挡在一个已经不成立的解释后面。
    expect(
      source.contains('videoRequiresSignedGrant'),
      isFalse,
      reason: '私有视频判否已被真实播放通道取代',
    );
    expect(
      source.contains("ValueKey<String>('home-video-signed-grant-unsupported')"),
      isFalse,
      reason: '判否终态 key 必须与实现同步移除，否则 UAT 会定位到不存在的态',
    );
  });
}
