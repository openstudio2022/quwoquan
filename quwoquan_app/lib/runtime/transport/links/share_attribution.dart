import 'dart:math';

/// 对外分享归因参数（运行时按渠道注入到 web/中转页链接）。
///
/// 结构真相源：`contracts/metadata/_shared/link_templates.yaml` 的 `attribution_params`
/// （codegen `AppShareLinks` 落地前的客户端实现；key 名与该 metadata 一一对应，
/// codegen 就绪后本类应改为消费生成常量，禁止再维护第二套 key）。
///
/// 用途：每次分享生成唯一 [shareId] + UTM，注入对外链接，使站外回流可按
/// share_id / 渠道 / 活动归因（对接 `share-attribution-and-token`）。
class ShareAttribution {
  ShareAttribution({
    required this.shareId,
    required this.utmSource,
    required this.utmMedium,
    this.utmCampaign,
    this.referral,
  });

  /// 生成单次分享事件归因：[shareId] 自动生成（与埋点/落库同源）。
  factory ShareAttribution.forShareEvent({
    required String utmSource,
    required String utmMedium,
    String? utmCampaign,
    String? referral,
  }) {
    return ShareAttribution(
      shareId: _generateShareId(),
      utmSource: utmSource,
      utmMedium: utmMedium,
      utmCampaign: utmCampaign,
      referral: referral,
    );
  }

  final String shareId;
  final String utmSource;
  final String utmMedium;
  final String? utmCampaign;
  final String? referral;

  /// metadata attribution_params key（与 link_templates.yaml 对齐）。
  static const String keyShareId = 'share_id';
  static const String keyUtmSource = 'utm_source';
  static const String keyUtmMedium = 'utm_medium';
  static const String keyUtmCampaign = 'utm_campaign';
  static const String keyReferral = 'referral';

  /// 默认 utm_medium（社交分享）。
  static const String mediumSocial = 'social';

  /// 默认 utm_source（App 内分享面板触发）。
  static const String sourceApp = 'app';

  static final Random _random = Random();

  static String _generateShareId() {
    final ts = DateTime.now().millisecondsSinceEpoch;
    final r = _random.nextInt(0xFFFFFF).toRadixString(16).padLeft(6, '0');
    return 'shr_$ts$r';
  }

  Map<String, String> toQueryParameters() => <String, String>{
    keyShareId: shareId,
    keyUtmSource: utmSource,
    keyUtmMedium: utmMedium,
    if (utmCampaign != null && utmCampaign!.trim().isNotEmpty)
      keyUtmCampaign: utmCampaign!.trim(),
    if (referral != null && referral!.trim().isNotEmpty)
      keyReferral: referral!.trim(),
  };

  /// 将归因参数追加到 web HTTPS 链接（保留原有 query）。
  /// 仅处理 http/https；空串或非法 URI 原样返回（scheme 深链经透传字段携带归因，不在此追加）。
  String applyTo(String url) {
    final trimmed = url.trim();
    if (trimmed.isEmpty) return trimmed;
    final uri = Uri.tryParse(trimmed);
    if (uri == null || (!uri.isScheme('http') && !uri.isScheme('https'))) {
      return trimmed;
    }
    final merged = <String, String>{
      ...uri.queryParameters,
      ...toQueryParameters(),
    };
    return uri.replace(queryParameters: merged).toString();
  }
}
