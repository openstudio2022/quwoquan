import 'dart:convert' show utf8;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/canonical_search_query_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/fixtures/object_contract_example_reader.dart';

/// canonical Search 对象级替身：仅消费 metadata fixture bundle，不调用 content
/// repository，也不在端侧合成 related terms。
final class CanonicalSearchTypedDouble implements CanonicalSearchQueryFacet {
  @override
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    cancellation?.throwIfCancelled();
    final normalized = query.query.trim().toLowerCase();
    final posts = _contentPosts();
    final allowedTargets = query.objectTypes.toSet();
    final hits = <CanonicalSearchHit>[];
    for (final post in posts) {
      final contentType = _text(post['contentType'], fallback: 'image');
      final target = switch (contentType) {
        'article' => 'article',
        'video' => 'video',
        _ => 'photo',
      };
      if (allowedTargets.isNotEmpty && !allowedTargets.contains(target)) {
        continue;
      }
      final title = _text(post['title']);
      final summary = _text(post['summary']);
      final body = _text(post['body']);
      final author = _text(post['authorDisplayName']);
      final matched = <String>[
        title,
        summary,
        body,
        author,
      ].any((value) => value.toLowerCase().contains(normalized));
      if (!matched) {
        continue;
      }
      final postID = _text(post['postId']);
      if (postID.isEmpty) {
        continue;
      }
      final contentIdentity = _optionalText(post['contentIdentity']);
      final content = CanonicalSearchContentHit(
        postId: postID,
        contentType: ContentType.fromWire(
          contentType,
          'CanonicalSearchTypedDouble.contentType',
        ),
        contentIdentity: contentIdentity == null
            ? null
            : ContentIdentity.fromWire(
                contentIdentity,
                'CanonicalSearchTypedDouble.contentIdentity',
              ),
        title: title.isEmpty ? postID : title,
        summary: _optionalText(post['summary']),
        coverUrl: _optionalText(post['coverUrl']),
        authorId: _optionalText(post['authorId']),
        authorDisplayName: _optionalText(post['authorDisplayName']),
        authorAvatarUrl: _optionalText(post['authorAvatarUrl']),
        categoryId: _optionalText(post['categoryId']),
        subCategory: _optionalText(post['subCategory']),
        likeCount: _integer(post['likeCount']),
        publishedAt: _dateTime(post['publishedAt']),
      );
      final matchedField = title.toLowerCase().contains(normalized)
          ? 'title'
          : 'body';
      hits.add(
        CanonicalSearchHit(
          target: target,
          objectType: 'content.post',
          objectId: postID,
          title: content.title ?? postID,
          snippet: content.summary,
          score: 1,
          matchedTerms: <String>[normalized],
          matchedTags: const <String>[],
          evidence: <CanonicalSearchEvidence>[
            CanonicalSearchEvidence(field: matchedField, snippet: title),
          ],
          rankReasons: const <CanonicalSearchRankReason>[],
          rankPosition: hits.length + 1,
          content: content,
        ),
      );
      if (hits.length >= query.limit) {
        break;
      }
    }
    final digest = sha256.convert(
      utf8.encode('${query.mode.wireValue}:$normalized'),
    );
    return SearchResponseView(
      hits: hits,
      provenance: CanonicalSearchProvenance(
        provider: 'alpha-typed-double',
        generatedAt: DateTime.utc(2026, 7, 31),
      ),
      requestId: 'alpha_${digest.toString().substring(0, 16)}',
    );
  }

  static List<Map<String, Object?>> _contentPosts() {
    final decoded = objectContractExampleReader.document('content');
    final examples = decoded['examples'];
    if (examples is! Map) {
      return const <Map<String, Object?>>[];
    }
    final discovery = examples['content_discovery_core'];
    if (discovery is! Map || discovery['posts'] is! List) {
      return const <Map<String, Object?>>[];
    }
    return (discovery['posts'] as List)
        .whereType<Map>()
        .map(
          (post) => post.map(
            (key, value) => MapEntry(key.toString(), value as Object?),
          ),
        )
        .toList(growable: false);
  }
}

String _text(Object? value, {String fallback = ''}) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

String? _optionalText(Object? value) {
  final text = _text(value);
  return text.isEmpty ? null : text;
}

int _integer(Object? value) {
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

DateTime? _dateTime(Object? value) {
  final text = _text(value);
  return text.isEmpty ? null : DateTime.tryParse(text)?.toUtc();
}
