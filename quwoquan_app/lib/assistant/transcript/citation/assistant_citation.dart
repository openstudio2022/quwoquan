/// 引用卡片 / WebView 入参（C7）。
class AssistantCitation {
  const AssistantCitation({
    required this.url,
    this.title = '',
    this.source = '',
    this.snippet = '',
  });

  final String url;
  final String title;
  final String source;
  final String snippet;

  factory AssistantCitation.fromReferenceMap(Map<String, dynamic> m) {
    return AssistantCitation(
      url: (m['url'] as String?)?.trim() ?? '',
      title: (m['title'] as String?)?.trim() ?? '',
      source: (m['source'] as String?)?.trim() ?? '',
      snippet: (m['snippet'] as String?)?.trim() ?? '',
    );
  }

  Map<String, dynamic> toReferenceMap() {
    return <String, dynamic>{
      'url': url,
      'title': title,
      'source': source,
      'snippet': snippet,
    };
  }
}
