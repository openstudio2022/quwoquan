/// 解析「我的二维码」名片 payload。
///
/// 名片 payload 形如 `https://app.quwoquan.com/u/{handle}?qr={token}`：`handle` 在
/// 路径段、`token` 在 `qr` query。端侧只负责提取 `handle` + `qr`，再交由
/// `ResolveProfileQrToken` 在云侧校验落地，禁止自解析 payload 直跳他人主页。
class QrPayloadParseResult {
  const QrPayloadParseResult({required this.handle, required this.token});

  final String handle;
  final String token;

  bool get isValid => token.isNotEmpty;
}

class QrPayloadParser {
  const QrPayloadParser._();

  /// 解析扫描得到的原始字符串；非趣我圈名片或缺少 token 时返回 null。
  static QrPayloadParseResult? parse(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    final uri = Uri.tryParse(trimmed);
    if (uri == null) {
      return null;
    }
    final token = uri.queryParameters['qr']?.trim() ?? '';
    if (token.isEmpty) {
      return null;
    }
    var handle = '';
    final segments = uri.pathSegments;
    final uIndex = segments.indexOf('u');
    if (uIndex >= 0 && uIndex + 1 < segments.length) {
      handle = segments[uIndex + 1].trim();
    } else if (segments.isNotEmpty) {
      handle = segments.last.trim();
    }
    return QrPayloadParseResult(handle: handle, token: token);
  }
}
