/// 与集合迭代顺序无关的稳定 hash（用于 [SearchObjectSelection.hashCode]）。
int _enumIndexSetHash<T extends Enum>(Set<T> values) {
  if (values.isEmpty) {
    return 0;
  }
  final indices = values.map((value) => value.index).toList()..sort();
  return Object.hashAll(indices);
}

bool _setEquals<T>(Set<T> left, Set<T> right) =>
    left.length == right.length && left.containsAll(right);

enum SearchScope {
  all,
  content,
  socialRelation,
  messages,
  circles;

  String get wireValue => switch (this) {
    SearchScope.all => 'all',
    SearchScope.content => 'content',
    SearchScope.socialRelation => 'social_relation',
    SearchScope.messages => 'messages',
    SearchScope.circles => 'circles',
  };

  static SearchScope fromWire(String? raw) {
    final normalized = (raw ?? '').trim();
    return SearchScope.values.firstWhere(
      (scope) => scope.wireValue == normalized,
      orElse: () => SearchScope.all,
    );
  }
}

enum SearchObjectTarget {
  contacts,
  directChats,
  groupChats,
  circles;

  String get wireValue => switch (this) {
    SearchObjectTarget.contacts => 'contacts',
    SearchObjectTarget.directChats => 'direct_chats',
    SearchObjectTarget.groupChats => 'group_chats',
    SearchObjectTarget.circles => 'circles',
  };

  static SearchObjectTarget? fromWire(String raw) {
    switch (raw.trim()) {
      case 'contacts':
        return SearchObjectTarget.contacts;
      case 'direct_chats':
        return SearchObjectTarget.directChats;
      case 'group_chats':
        return SearchObjectTarget.groupChats;
      case 'circles':
        return SearchObjectTarget.circles;
      default:
        return null;
    }
  }
}

enum SearchContentTypeFilter {
  article,
  image,
  video,
  micro;

  String get wireValue => switch (this) {
    SearchContentTypeFilter.article => 'article',
    SearchContentTypeFilter.image => 'image',
    SearchContentTypeFilter.video => 'video',
    SearchContentTypeFilter.micro => 'micro',
  };

  String get identity => switch (this) {
    SearchContentTypeFilter.micro => 'moment',
    SearchContentTypeFilter.article ||
    SearchContentTypeFilter.image ||
    SearchContentTypeFilter.video => 'work',
  };

  String get contentType => switch (this) {
    SearchContentTypeFilter.article => 'article',
    SearchContentTypeFilter.image => 'image',
    SearchContentTypeFilter.video => 'video',
    SearchContentTypeFilter.micro => 'micro',
  };

  static SearchContentTypeFilter? fromWire(String raw) {
    switch (raw.trim()) {
      case 'article':
        return SearchContentTypeFilter.article;
      case 'image':
        return SearchContentTypeFilter.image;
      case 'video':
        return SearchContentTypeFilter.video;
      case 'micro':
        return SearchContentTypeFilter.micro;
      default:
        return null;
    }
  }
}

final class SearchObjectSelection {
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
    if (normalizedSelection.isEmpty && normalizedSelection.isAllContent) {
      return null;
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
    } on FormatException {
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

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) {
      return true;
    }
    return other is SearchObjectSelection &&
        _setEquals(targets, other.targets) &&
        _setEquals(contentTypes, other.contentTypes);
  }

  @override
  int get hashCode =>
      Object.hash(_enumIndexSetHash(targets), _enumIndexSetHash(contentTypes));
}
