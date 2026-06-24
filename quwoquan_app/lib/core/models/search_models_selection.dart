part of 'search_models.dart';

class SearchObjectSelection {
  const SearchObjectSelection({
    this.targets = const <SearchObjectTarget>{},
    this.contentTypes = const <SearchContentTypeFilter>{},
  });

  final Set<SearchObjectTarget> targets;
  final Set<SearchContentTypeFilter> contentTypes;

  Set<SearchObjectTarget> get normalizedTargets =>
      targets.length == 1 ? <SearchObjectTarget>{targets.first} : const {};

  bool get isEmpty => normalizedTargets.isEmpty;
  bool get isAll => normalizedTargets.isEmpty;
  bool get isAllContent => contentTypes.isEmpty;

  SearchObjectTarget? get activeObjectTarget =>
      normalizedTargets.length == 1 ? normalizedTargets.first : null;

  Set<SearchContentTypeFilter> get enabledContentTypes =>
      isAllContent ? SearchContentTypeFilter.values.toSet() : contentTypes;

  SearchContentTypeFilter? get activeContentType {
    for (final type in SearchContentTypeFilter.values) {
      if (contentTypes.contains(type)) {
        return type;
      }
    }
    return null;
  }

  bool contains(SearchObjectTarget target) =>
      normalizedTargets.contains(target);

  bool isContentTypeEnabled(SearchContentTypeFilter type) =>
      enabledContentTypes.contains(type);

  SearchObjectSelection normalized() {
    final normalizedContentTypes =
        contentTypes.length == SearchContentTypeFilter.values.length
        ? const <SearchContentTypeFilter>{}
        : <SearchContentTypeFilter>{
            for (final type in SearchContentTypeFilter.values)
              if (contentTypes.contains(type)) type,
          };
    return SearchObjectSelection(
      targets: normalizedTargets,
      contentTypes: normalizedContentTypes,
    );
  }

  String? toFacet() {
    final normalizedSelection = normalized();
    if (normalizedSelection.isEmpty) {
      if (normalizedSelection.isAllContent) {
        return null;
      }
    }
    final params = <String, String>{};
    if (!normalizedSelection.isAll) {
      params['targets'] = normalizedSelection.activeObjectTarget!.wireValue;
    }
    if (!normalizedSelection.isAllContent) {
      params['content'] = SearchContentTypeFilter.values
          .where(normalizedSelection.contentTypes.contains)
          .map((item) => item.wireValue)
          .join(',');
    }
    if (params.isEmpty) {
      return null;
    }
    return Uri(queryParameters: params).query;
  }

  SearchObjectSelection copyWith({
    Set<SearchObjectTarget>? targets,
    Set<SearchContentTypeFilter>? contentTypes,
  }) {
    return SearchObjectSelection(
      targets: targets ?? this.targets,
      contentTypes: contentTypes ?? this.contentTypes,
    ).normalized();
  }

  static SearchObjectSelection fromFacet(String? raw) {
    final trimmed = (raw ?? '').trim();
    if (trimmed.isEmpty) {
      return const SearchObjectSelection();
    }
    try {
      final params = Uri.splitQueryString(trimmed);
      final rawTargets = (params['targets'] ?? '').split(',');
      final targets = rawTargets
          .map(SearchObjectTarget.fromWire)
          .whereType<SearchObjectTarget>()
          .take(1)
          .toSet();
      final contentTypes =
          ((params['content'] ?? '')
                  .split(',')
                  .map(SearchContentTypeFilter.fromWire)
                  .whereType<SearchContentTypeFilter>())
              .toSet();
      return SearchObjectSelection(
        targets: targets,
        contentTypes: contentTypes,
      ).normalized();
    } catch (_) {
      return const SearchObjectSelection();
    }
  }

  static SearchObjectSelection fromSearchScope(SearchScope scope) {
    switch (scope) {
      case SearchScope.content:
        return const SearchObjectSelection();
      case SearchScope.socialRelation:
        return const SearchObjectSelection(
          targets: <SearchObjectTarget>{SearchObjectTarget.contacts},
        );
      case SearchScope.messages:
        return const SearchObjectSelection();
      case SearchScope.circles:
        return const SearchObjectSelection(
          targets: <SearchObjectTarget>{SearchObjectTarget.circles},
        );
      case SearchScope.all:
        return const SearchObjectSelection();
    }
  }

  /// Riverpod `family` 等场景：内容相同即同一键，避免父组件 rebuild 时重复创建 provider。
  @override
  bool operator ==(Object other) {
    if (identical(this, other)) {
      return true;
    }
    return other is SearchObjectSelection &&
        setEquals(targets, other.targets) &&
        setEquals(contentTypes, other.contentTypes);
  }

  @override
  int get hashCode =>
      Object.hash(_enumIndexSetHash(targets), _enumIndexSetHash(contentTypes));
}
