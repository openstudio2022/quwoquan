/// Vendor-neutral web hit after raw JSON parse (S-Search). Downstream still uses
/// `Map<String, dynamic>` references; this type captures the normalized triple only.
class NormalizedWebReference {
  const NormalizedWebReference({
    required this.title,
    required this.url,
    this.snippet = '',
  });

  final String title;
  final String url;
  final String snippet;

  bool get isUsable => url.trim().isNotEmpty;

  /// Serp-style organic row (`title` / `url` / `snippet`).
  factory NormalizedWebReference.fromSerpOrganicItem(Map<String, dynamic> item) {
    return NormalizedWebReference(
      title: (item['title'] as String?)?.trim() ?? '',
      url: (item['url'] as String?)?.trim() ?? '',
      snippet: (item['snippet'] as String?)?.trim() ?? '',
    );
  }

  /// Brave `web.results[]` row (`title` / `url` / `description`).
  factory NormalizedWebReference.fromBraveWebResult(Map<String, dynamic> item) {
    return NormalizedWebReference(
      title: (item['title'] as String?)?.trim() ?? '',
      url: (item['url'] as String?)?.trim() ?? '',
      snippet: (item['description'] as String?)?.trim() ?? '',
    );
  }

  /// SerpAPI / compatible organic row (`title` / `link` / `snippet`).
  factory NormalizedWebReference.fromSerpApiOrganic(Map<String, dynamic> item) {
    return NormalizedWebReference(
      title: (item['title'] as String?)?.trim() ?? '',
      url: (item['link'] as String?)?.trim() ?? '',
      snippet: (item['snippet'] as String?)?.trim() ?? '',
    );
  }

  /// DuckDuckGo `RelatedTopics[]` row (`Text` / `FirstURL`).
  factory NormalizedWebReference.fromDuckduckgoRelatedTopic(
    Map<String, dynamic> item,
  ) {
    final text = (item['Text'] as String?)?.trim() ?? '';
    final url = (item['FirstURL'] as String?)?.trim() ?? '';
    return NormalizedWebReference(title: text, url: url, snippet: text);
  }

  Map<String, String> get coreMap => <String, String>{
    'title': title.isNotEmpty ? title : url,
    'url': url,
    'snippet': snippet,
  };
}
