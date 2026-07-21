import 'package:quwoquan_app/assistant/transcript/citation/citation_destination_resolver.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';

/// 引用卡片的单轨 destination。URL 仅能作为 external destination 的字段存在。
class AssistantCitation {
  const AssistantCitation({
    required this.destination,
    this.title = '',
    this.source = '',
    this.snippet = '',
  });

  final CitationDestination destination;
  final String title;
  final String source;
  final String snippet;

  factory AssistantCitation.external({
    required String url,
    String title = '',
    String source = '',
    String snippet = '',
  }) {
    return AssistantCitation(
      destination: CitationDestination(kind: 'external', url: url.trim()),
      title: title,
      source: source,
      snippet: snippet,
    );
  }

  factory AssistantCitation.fromReferenceMap(Map<String, dynamic> m) {
    final rawDestination = m['destination'];
    final destination = rawDestination is Map
        ? CitationDestination.fromJson(rawDestination.cast<String, dynamic>())
        : CitationDestination(
            kind: 'external',
            url: (m['url'] as String?)?.trim() ?? '',
          );
    return AssistantCitation(
      destination: destination,
      title: (m['title'] as String?)?.trim() ?? '',
      source: (m['source'] as String?)?.trim() ?? '',
      snippet: (m['snippet'] as String?)?.trim() ?? '',
    );
  }

  Map<String, dynamic> toReferenceMap() {
    return <String, dynamic>{
      'destination': destination.toJson(),
      'title': title,
      'source': source,
      'snippet': snippet,
    };
  }

  ResolvedCitationDestination? get resolvedDestination =>
      CitationDestinationResolver.resolve(destination);
}
