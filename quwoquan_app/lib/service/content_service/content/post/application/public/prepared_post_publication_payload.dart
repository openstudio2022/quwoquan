/// Post 发布准备阶段的跨对象公开载荷。
final class PreparedPostPublicationPayload {
  const PreparedPostPublicationPayload({
    required this.payload,
    required this.mediaAssetIds,
  });

  final Map<String, Object?> payload;
  final List<String> mediaAssetIds;
}
