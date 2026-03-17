class SafeReferenceNormalizer {
  const SafeReferenceNormalizer._();

  static const List<String> _trackingKeys = <String>[
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_term',
    'utm_content',
    'utm_id',
    'fbclid',
    'gclid',
    'spm',
    'mkt_tok',
    'yclid',
    '_hsenc',
    '_hsmi',
  ];

  static Map<String, dynamic>? normalize(Map<String, dynamic> raw) {
    final originalUrl = (raw['url'] as String?)?.trim() ?? '';
    final canonicalUrl = canonicalizeUrl(originalUrl);
    if (canonicalUrl.isEmpty) return null;
    final normalizedTitle = normalizeTitle(
      (raw['title'] as String?)?.trim() ?? '',
      canonicalUrl: canonicalUrl,
    );
    final snippet = normalizeText((raw['snippet'] as String?)?.trim() ?? '');
    final source =
        normalizeText((raw['source'] as String?)?.trim() ?? '').isNotEmpty
        ? normalizeText((raw['source'] as String?)?.trim() ?? '')
        : _hostOf(canonicalUrl);
    return <String, dynamic>{
      ...raw,
      'url': canonicalUrl,
      'canonicalUrl': canonicalUrl,
      'title': normalizedTitle,
      'snippet': snippet,
      'source': source,
      'sourceHost': _hostOf(canonicalUrl),
    };
  }

  static String canonicalizeUrl(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return '';
    final unwrapped = _unwrapRedirect(trimmed).trim();
    final candidate = unwrapped.endsWith('#')
        ? unwrapped.substring(0, unwrapped.length - 1)
        : unwrapped;
    final uri = Uri.tryParse(candidate);
    if (uri == null || (!uri.isScheme('http') && !uri.isScheme('https'))) {
      return '';
    }
    final filteredQueryParts = <String>[];
    if (uri.hasQuery) {
      for (final pair in uri.query.split('&')) {
        final trimmedPair = pair.trim();
        if (trimmedPair.isEmpty) continue;
        final separatorIndex = trimmedPair.indexOf('=');
        final rawKey = separatorIndex >= 0
            ? trimmedPair.substring(0, separatorIndex)
            : trimmedPair;
        final key = Uri.decodeQueryComponent(rawKey).toLowerCase();
        if (_trackingKeys.contains(key)) continue;
        filteredQueryParts.add(trimmedPair);
      }
    }
    final base = '${uri.scheme}://${uri.authority}${uri.path}';
    if (filteredQueryParts.isEmpty) return base;
    return '$base?${filteredQueryParts.join('&')}';
  }

  static String normalizeTitle(String raw, {required String canonicalUrl}) {
    final normalized = normalizeText(raw);
    if (normalized.isNotEmpty &&
        !_looksLikeUrl(normalized) &&
        !_looksGarbled(normalized)) {
      return normalized;
    }
    final uri = Uri.tryParse(canonicalUrl);
    if (uri == null) return normalized;
    final host = uri.host.replaceFirst(RegExp(r'^www\.'), '');
    final lastSegment = uri.pathSegments.isNotEmpty
        ? uri.pathSegments.last
        : '';
    final fallback = normalizeText(
      [host, lastSegment].where((item) => item.trim().isNotEmpty).join(' '),
    );
    return fallback.isNotEmpty ? fallback : canonicalUrl;
  }

  static String normalizeText(String raw) {
    final decoded = _decodeEntities(raw);
    return decoded.replaceAll(RegExp(r'\s+'), ' ').trim();
  }

  static bool _looksLikeUrl(String text) {
    final normalized = text.toLowerCase();
    return normalized.startsWith('http://') ||
        normalized.startsWith('https://') ||
        normalized.contains('://');
  }

  static bool _looksGarbled(String text) {
    return text.contains('\uFFFD') ||
        text.contains('Ã') ||
        text.contains('â') ||
        text.contains('ï¿½');
  }

  static String _hostOf(String url) {
    final uri = Uri.tryParse(url);
    return uri?.host.replaceFirst(RegExp(r'^www\.'), '') ?? '';
  }

  static String _unwrapRedirect(String raw) {
    final uri = Uri.tryParse(raw);
    if (uri == null) return raw;
    final redirectKeys = const <String>[
      'uddg',
      'url',
      'target',
      'dest',
      'destination',
      'q',
    ];
    for (final key in redirectKeys) {
      final value = uri.queryParameters[key];
      if (value == null || value.trim().isEmpty) continue;
      final candidate = Uri.decodeComponent(value.trim()).trim();
      if (candidate.startsWith('http://') || candidate.startsWith('https://')) {
        return candidate;
      }
    }
    return raw;
  }

  static String _decodeEntities(String text) {
    var result = text
        .replaceAll('&amp;', '&')
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll('&apos;', "'")
        .replaceAll('&nbsp;', ' ');
    result = result.replaceAllMapped(RegExp(r'&#(\d+);'), (m) {
      final code = int.tryParse(m.group(1) ?? '');
      return code != null ? String.fromCharCode(code) : m.group(0)!;
    });
    result = result.replaceAllMapped(RegExp(r'&#x([0-9a-fA-F]+);'), (m) {
      final code = int.tryParse(m.group(1) ?? '', radix: 16);
      return code != null ? String.fromCharCode(code) : m.group(0)!;
    });
    return result;
  }
}
