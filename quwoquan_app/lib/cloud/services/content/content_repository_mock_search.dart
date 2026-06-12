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
      final circleIds = <String>{
        if ((item['circleId'] ?? '').toString().trim().isNotEmpty)
          (item['circleId'] ?? '').toString().trim(),
        ...((item['circleIds'] as List?)
                ?.map((value) => value.toString().trim())
                .where((value) => value.isNotEmpty) ??
            const <String>[]),
      };
      final associatedCircles = circleIds
          .map(CircleMockData.tryResolveCircleDto)
          .whereType<CircleDto>()
          .toList(growable: false);
      final matchedCategory = associatedCircles
          .where(
            (circle) =>
                (expectedCategoryId.isEmpty ||
                    (circle.category ?? '').toLowerCase() ==
                        expectedCategoryId) &&
                (expectedSubCategory.isEmpty ||
                    (circle.subCategory ?? '').toLowerCase() ==
                        expectedSubCategory),
          )
          .toList(growable: false);
      final matchedCircle = matchedCategory.isNotEmpty
          ? matchedCategory.first
          : (associatedCircles.isEmpty ? null : associatedCircles.first);
      final fallbackCategoryId = _mockCategoryForCircleIds(circleIds);
      final itemIdentity =
          (item['contentIdentity'] ??
                  (item['contentType'] == 'micro' ? 'moment' : 'work'))
              .toString()
              .toLowerCase();
      final itemType = (item['contentType'] ?? item['type'] ?? '')
          .toString()
          .toLowerCase();
      final itemCategoryId =
          (item['categoryId'] ?? matchedCircle?.category ?? fallbackCategoryId)
              .toString()
              .toLowerCase();
      final itemSubCategory =
          (item['subCategory'] ?? matchedCircle?.subCategory ?? '')
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
          'categoryId': item['categoryId'] ?? matchedCircle?.category,
          'subCategory': item['subCategory'] ?? matchedCircle?.subCategory,
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
