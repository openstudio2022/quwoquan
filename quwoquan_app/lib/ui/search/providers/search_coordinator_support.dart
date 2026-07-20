part of 'search_coordinator.dart';

class _SuggestionDomainOutcome {
  const _SuggestionDomainOutcome({this.error});

  final Object? error;
  bool get failed => error != null;
}

class _LocalSuggestionResult {
  const _LocalSuggestionResult({required this.sections, this.error});

  final List<SearchSuggestionSection> sections;
  final Object? error;
}

String _historyKeyForEntry(RecentSearchEntryView entry) {
  return '${entry.scope.wireValue}|${entry.facet ?? ''}|${entry.query.toLowerCase()}';
}

SearchScope _scopeForSelection(SearchObjectSelection selection) {
  switch (selection.normalized().activeObjectTarget) {
    case SearchObjectTarget.contacts:
      return SearchScope.socialRelation;
    case SearchObjectTarget.directChats:
    case SearchObjectTarget.groupChats:
      return SearchScope.messages;
    case SearchObjectTarget.circles:
      return SearchScope.circles;
    case null:
      return SearchScope.all;
  }
}

class SearchRecentHistoryStore {
  const SearchRecentHistoryStore();

  static const String _storageKey = 'global_search_recent_entries_v1';

  Future<List<RecentSearchEntryView>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_storageKey);
    if (raw == null || raw.trim().isEmpty) {
      return const <RecentSearchEntryView>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return const <RecentSearchEntryView>[];
      }
      return decoded
          .whereType<Map>()
          .map(
            (item) =>
                RecentSearchEntryView.fromMap(item.cast<String, dynamic>()),
          )
          .where((item) => item.query.trim().isNotEmpty)
          .toList(growable: false);
    } on Object catch (error) {
      if (kDebugMode) {
        debugPrint('recent search local cache decode failed: $error');
      }
      return const <RecentSearchEntryView>[];
    }
  }

  Future<void> save(List<RecentSearchEntryView> entries) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _storageKey,
      jsonEncode(entries.map((entry) => entry.toMap()).toList(growable: false)),
    );
  }

  Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_storageKey);
  }
}

class _ChatRecordAccumulator {
  _ChatRecordAccumulator({
    required this.conversationId,
    required this.conversationTitle,
    required this.conversationType,
    required this.avatarUrl,
    required this.matchedPreview,
    required this.matchCount,
    this.messageAnchorId,
    this.timestamp,
  });

  factory _ChatRecordAccumulator.fromConversation(
    ConversationSearchItemView conversation,
  ) {
    return _ChatRecordAccumulator(
      conversationId: conversation.conversationId,
      conversationTitle: conversation.title,
      conversationType: conversation.type,
      avatarUrl: conversation.avatarUrl,
      matchedPreview:
          conversation.highlightText ??
          conversation.lastMessagePreview ??
          ChatText.searchOpenChat,
      matchCount: 1,
      timestamp: conversation.lastMessageTime,
    );
  }

  factory _ChatRecordAccumulator.fromMessage(
    MessageSearchItemView message, {
    ConversationSearchItemView? seedConversation,
  }) {
    // 会话头像只保留 authoritative conversation avatar；
    // direct/group 的成员回退统一由共享 ConversationAvatar 组件负责。
    return _ChatRecordAccumulator(
      conversationId: message.conversationId,
      conversationTitle:
          message.conversationTitle ??
          seedConversation?.title ??
          ChatText.searchChatRecord,
      conversationType: seedConversation?.type ?? 'group',
      avatarUrl: message.conversationAvatarUrl ?? seedConversation?.avatarUrl,
      matchedPreview: message.highlightText ?? message.contentPreview,
      matchCount: 1,
      messageAnchorId: message.messageId,
      timestamp: message.timestamp,
    );
  }

  final String conversationId;
  String conversationTitle;
  String conversationType;
  String? avatarUrl;
  String matchedPreview;
  int matchCount;
  String? messageAnchorId;
  DateTime? timestamp;

  void includeConversationHit(ConversationSearchItemView conversation) {
    conversationTitle = conversation.title;
    conversationType = conversation.type;
    avatarUrl = avatarUrl ?? conversation.avatarUrl;
    matchedPreview =
        conversation.highlightText ??
        conversation.lastMessagePreview ??
        matchedPreview;
    timestamp = _maxTimestamp(timestamp, conversation.lastMessageTime);
  }

  void includeMessageHit(MessageSearchItemView message) {
    matchCount += 1;
    matchedPreview = message.highlightText ?? message.contentPreview;
    messageAnchorId ??= message.messageId;
    timestamp = _maxTimestamp(timestamp, message.timestamp);
    avatarUrl = avatarUrl ?? message.conversationAvatarUrl;
  }

  ChatRecordSearchSuggestion build() {
    return ChatRecordSearchSuggestion(
      conversationId: conversationId,
      conversationTitle: conversationTitle,
      conversationType: conversationType,
      matchedPreview: matchedPreview,
      matchCount: matchCount,
      avatarUrl: avatarUrl,
      messageAnchorId: messageAnchorId,
      timestamp: timestamp,
    );
  }

  DateTime? _maxTimestamp(DateTime? left, DateTime? right) {
    if (left == null) {
      return right;
    }
    if (right == null) {
      return left;
    }
    return left.isAfter(right) ? left : right;
  }
}
