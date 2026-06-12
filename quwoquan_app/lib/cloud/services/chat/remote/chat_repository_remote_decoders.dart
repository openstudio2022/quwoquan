part of 'chat_repository_remote.dart';

typedef _ChatRemoteFromMap<T> = T Function(Map<String, dynamic> map);

extension _RemoteChatRepositoryDecoders on RemoteChatRepository {
  List<T> _decodeCursorPageItems<T>(
    Object? decoded, {
    required String context,
    required _ChatRemoteFromMap<T> fromMap,
  }) {
    final page = CloudResponseDecoder.asCursorPage(decoded, context: context);
    return page.items.map(fromMap).toList(growable: false);
  }

  List<T> _decodeObjectItems<T>(
    Object? decoded, {
    required String context,
    required _ChatRemoteFromMap<T> fromMap,
  }) {
    final obj = CloudResponseDecoder.asObject(decoded, context: context);
    final items = obj['items'];
    if (items is! List) {
      return <T>[];
    }
    return items
        .whereType<Map>()
        .map((item) => fromMap(Map<String, dynamic>.from(item)))
        .toList(growable: false);
  }
}
