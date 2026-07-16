part of 'content_repository.dart';

extension _MockContentRepositorySearch on MockContentRepository {
  List<PostSearchItemView> _searchMockPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    required int limit,
  }) {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <PostSearchItemView>[];
    }
    final expectedIdentity = (identity ?? '').trim().toLowerCase();
    final expectedType = (type ?? '').trim().toLowerCase();
    final expectedCategoryId = (categoryId ?? '').trim().toLowerCase();
    final expectedSubCategory = (subCategory ?? '').trim().toLowerCase();
    final allRaw = _allDiscoveryPosts().map((e) => e.toMap()).toList();
    final results = <PostSearchItemView>[];
    for (final item in allRaw) {
      final itemIdentity =
          (item['contentIdentity'] ??
                  (item['contentType'] == 'micro' ? 'moment' : 'work'))
              .toString()
              .toLowerCase();
      final itemType = (item['contentType'] ?? item['type'] ?? '')
          .toString()
          .toLowerCase();
      final itemCategoryId =
          (item['categoryId'] ?? item['contentVertical'] ?? '')
              .toString()
              .toLowerCase();
      final itemSubCategory = (item['subCategory'] ?? '')
          .toString()
          .toLowerCase();
      if (expectedIdentity.isNotEmpty && itemIdentity != expectedIdentity) {
        continue;
      }
      if (expectedType.isNotEmpty && itemType != expectedType) {
        continue;
      }
      if (expectedCategoryId.isNotEmpty &&
          itemCategoryId != expectedCategoryId) {
        continue;
      }
      if (expectedSubCategory.isNotEmpty &&
          itemSubCategory != expectedSubCategory) {
        continue;
      }
      final searchable = <String>[
        item['title']?.toString() ?? '',
        item['displayName']?.toString() ?? '',
        item['body']?.toString() ?? '',
        item['summary']?.toString() ?? '',
        item['locationName']?.toString() ?? '',
      ];
      final matched = searchable.firstWhere(
        (value) => value.toLowerCase().contains(normalizedQuery),
        orElse: () => '',
      );
      if (matched.isEmpty) {
        continue;
      }
      results.add(
        PostSearchItemView.fromMap(<String, dynamic>{
          ...item,
          'categoryId': item['categoryId'] ?? item['contentVertical'],
          'subCategory': item['subCategory'],
          'highlightText': matched,
          'matchedField': matched == (item['title']?.toString() ?? '')
              ? 'title'
              : matched == (item['displayName']?.toString() ?? '')
              ? 'author'
              : 'body',
          'authorId': item['authorId'] ?? item['subAccountId'] ?? '',
          'authorDisplayName':
              item['displayName'] ?? item['authorDisplayNameSnapshot'] ?? '',
          'authorAvatarUrl':
              item['authorAvatarUrl'] ?? item['authorAvatarUrlSnapshot'] ?? '',
        }),
      );
    }
    results.sort((a, b) {
      final aAuthorMatch = a.matchedField == 'author' ? 0 : 1;
      final bAuthorMatch = b.matchedField == 'author' ? 0 : 1;
      final byAuthor = aAuthorMatch.compareTo(bAuthorMatch);
      if (byAuthor != 0) {
        return byAuthor;
      }
      return a.postId.compareTo(b.postId);
    });
    return results.take(limit).toList(growable: false);
  }
}
