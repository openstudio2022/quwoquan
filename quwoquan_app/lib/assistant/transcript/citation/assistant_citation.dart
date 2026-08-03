import 'package:quwoquan_app/assistant/transcript/citation/citation_destination_resolver.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CitationDestination, CitationDestinationKind;

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
    return AssistantCitation.fromDestination(
      destination: CitationDestination(
        kind: CitationDestinationKind.external,
        url: url.trim(),
      ),
      title: title,
      source: source,
      snippet: snippet,
    );
  }

  factory AssistantCitation.fromDestination({
    required CitationDestination destination,
    String title = '',
    String source = '',
    String snippet = '',
  }) {
    if (CitationDestinationResolver.resolve(destination) == null) {
      throw const FormatException('invalid citation destination');
    }
    return AssistantCitation(
      destination: destination,
      title: title.trim(),
      source: source.trim(),
      snippet: snippet.trim(),
    );
  }

  factory AssistantCitation.fromReferenceMap(Map<String, Object?> m) {
    final rawDestination = m['destination'];
    return AssistantCitation.fromDestination(
      destination: citationDestinationFromWireObject(rawDestination),
      title: (m['title'] as String?)?.trim() ?? '',
      source: (m['source'] as String?)?.trim() ?? '',
      snippet: (m['snippet'] as String?)?.trim() ?? '',
    );
  }

  static AssistantCitation? tryFromReferenceMap(Map<String, Object?> m) {
    try {
      return AssistantCitation.fromReferenceMap(m);
    } on FormatException {
      return null;
    }
  }

  factory AssistantCitation.internal({
    required String objectTypeRef,
    required String objectId,
    String title = '',
    String source = '',
    String snippet = '',
  }) {
    return AssistantCitation.fromDestination(
      destination: CitationDestination(
        kind: CitationDestinationKind.internal,
        objectTypeRef: objectTypeRef.trim(),
        objectId: objectId.trim(),
      ),
      title: title,
      source: source,
      snippet: snippet,
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

  String get externalUrl {
    final resolved = resolvedDestination;
    return resolved is ExternalCitationDestination
        ? resolved.uri.toString()
        : '';
  }
}
