bool isTrustedHttpsUrl(String rawUrl, Iterable<String> rawBaseUrls) {
  final candidate = Uri.tryParse(rawUrl.trim());
  if (candidate == null) return false;
  return rawBaseUrls.any((rawBaseUrl) {
    final base = Uri.tryParse(rawBaseUrl.trim());
    return base != null && isUriWithinTrustedHttpsBase(candidate, base);
  });
}

bool isUriWithinTrustedHttpsBase(Uri candidate, Uri base) {
  if (base.scheme.toLowerCase() != 'https' ||
      base.host.isEmpty ||
      base.userInfo.isNotEmpty ||
      base.query.isNotEmpty ||
      base.fragment.isNotEmpty ||
      candidate.scheme.toLowerCase() != base.scheme.toLowerCase() ||
      candidate.host.toLowerCase() != base.host.toLowerCase() ||
      candidate.port != base.port ||
      candidate.userInfo.isNotEmpty ||
      candidate.fragment.isNotEmpty) {
    return false;
  }
  final basePath = base.path.replaceFirst(RegExp(r'/+$'), '');
  return basePath.isEmpty ||
      candidate.path == basePath ||
      candidate.path.startsWith('$basePath/');
}
