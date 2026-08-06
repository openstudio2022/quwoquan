final class PreparedPostPublicationPayload {
  const PreparedPostPublicationPayload({
    required this.payload,
    required this.mediaAssetIds,
  });

  final Map<String, Object?> payload;
  final List<String> mediaAssetIds;
}
