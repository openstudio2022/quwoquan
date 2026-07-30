final class AppMessageDestination {
  const AppMessageDestination({required this.type, required this.id});

  final String type;
  final String id;
}

final class AppMessageRouteQuery {
  const AppMessageRouteQuery({this.dimension});

  final String? dimension;
}

final class AppMessageTarget {
  const AppMessageTarget({
    required this.targetType,
    required this.targetId,
    this.routeId,
    this.routePath,
    this.query = const AppMessageRouteQuery(),
  });

  final String targetType;
  final String targetId;
  final String? routeId;
  final String? routePath;
  final AppMessageRouteQuery query;
}

final class AppMessage {
  const AppMessage({
    required this.messageId,
    required this.userId,
    required this.messageType,
    required this.source,
    required this.sourceId,
    required this.destination,
    required this.title,
    required this.summary,
    required this.target,
    required this.read,
    required this.createdAt,
    this.deliveredAt,
    this.ackedAt,
    this.readAt,
  });

  final String messageId;
  final String userId;
  final String messageType;
  final String source;
  final String sourceId;
  final AppMessageDestination destination;
  final String title;
  final String summary;
  final AppMessageTarget target;
  final bool read;
  final DateTime createdAt;
  final DateTime? deliveredAt;
  final DateTime? ackedAt;
  final DateTime? readAt;
}
