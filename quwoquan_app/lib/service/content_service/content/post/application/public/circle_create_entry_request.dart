/// Stable circle context carried into the Content creation entry.
final class CircleCreateEntryRequest {
  const CircleCreateEntryRequest({
    required this.circleId,
    this.circleName,
  });

  final String circleId;
  final String? circleName;
}
