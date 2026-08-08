/// 解析「我的二维码」名片 payload。
///
/// 名片 payload 使用 publicWeb role 下的 `/u/{handle}?qr={token}`：`handle` 在
/// 路径段、`token` 在 `qr` query。端侧只负责提取 `handle` + `qr`，再交由
/// `ResolveProfileQrToken` 在云侧校验落地，禁止自解析 payload 直跳他人主页。
class QrPayloadParseResult {
  const QrPayloadParseResult({
    required this.handle,
    required this.token,
    required this.publicProfileUrl,
  });

  final String handle;
  final String token;
  final String publicProfileUrl;

  bool get isValid =>
      handle.isNotEmpty && token.isNotEmpty && publicProfileUrl.isNotEmpty;
}

class QrPayloadParser {
  const QrPayloadParser._();

  /// 解析扫描得到的原始字符串；非当前运行包 public Web origin 的规范名片返回 null。
  static QrPayloadParseResult? parse(
    String raw, {
    required Uri trustedPublicOrigin,
  }) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty || !_isTrustedOrigin(trustedPublicOrigin)) {
      return null;
    }
    final uri = Uri.tryParse(trimmed);
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.userInfo.isNotEmpty ||
        uri.fragment.isNotEmpty ||
        uri.host.toLowerCase() != trustedPublicOrigin.host.toLowerCase() ||
        uri.hasPort != trustedPublicOrigin.hasPort ||
        (uri.hasPort && uri.port != trustedPublicOrigin.port)) {
      return null;
    }
    final segments = uri.pathSegments;
    if (segments.length != 2 || segments.first != 'u') {
      return null;
    }
    final handle = segments.last;
    if (handle.isEmpty ||
        handle != handle.trim() ||
        handle.contains('/') ||
        handle.contains(RegExp(r'[\u0000-\u001f\u007f]'))) {
      return null;
    }

    final query = uri.queryParametersAll;
    final tokens = query['qr'];
    if (query.length != 1 || tokens == null || tokens.length != 1) {
      return null;
    }
    final queryStart = trimmed.indexOf('?');
    if (queryStart <= 0) {
      return null;
    }
    final rawQuery = trimmed.substring(queryStart + 1);
    final token = tokens.single;
    if (token.isEmpty ||
        token != token.trim() ||
        !RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(token) ||
        rawQuery != 'qr=${Uri.encodeQueryComponent(token)}') {
      return null;
    }

    final canonicalProfileUrl = Uri(
      scheme: 'https',
      host: trustedPublicOrigin.host,
      port: trustedPublicOrigin.hasPort ? trustedPublicOrigin.port : null,
      pathSegments: <String>['u', handle],
    ).toString();
    if (trimmed.substring(0, queryStart) != canonicalProfileUrl) {
      return null;
    }

    return QrPayloadParseResult(
      handle: handle,
      token: token,
      publicProfileUrl: canonicalProfileUrl,
    );
  }

  static bool _isTrustedOrigin(Uri origin) {
    return origin.scheme == 'https' &&
        origin.userInfo.isEmpty &&
        origin.host.isNotEmpty &&
        (origin.path.isEmpty || origin.path == '/') &&
        origin.query.isEmpty &&
        origin.fragment.isEmpty;
  }
}
