/// Cross-object presentation value for an uploaded MediaAsset while a Message command is
/// optimistic. The command boundary consumes only [assetId]; delivery details
/// are replaced by the server's MediaAsset projection after reload.
final class ChatMessageMediaViewData {
  ChatMessageMediaViewData({
    required String assetId,
    required String deliveryUrl,
    required String mediaType,
    required String mimeType,
    required this.fileSizeBytes,
    this.durationMs,
    Iterable<double> waveform = const <double>[],
    String? thumbnailUrl,
    String? fileName,
  }) : assetId = _required(assetId, 'assetId'),
       deliveryUrl = _required(deliveryUrl, 'deliveryUrl'),
       mediaType = _required(mediaType, 'mediaType'),
       mimeType = _required(mimeType, 'mimeType'),
       waveform = List<double>.unmodifiable(
         waveform.map((sample) => sample.clamp(0, 1).toDouble()),
       ),
       thumbnailUrl = _optional(thumbnailUrl),
       fileName = _optional(fileName) {
    if (fileSizeBytes <= 0) {
      throw ArgumentError.value(fileSizeBytes, 'fileSizeBytes', 'must be > 0');
    }
    if (durationMs != null && durationMs! <= 0) {
      throw ArgumentError.value(durationMs, 'durationMs', 'must be > 0');
    }
  }

  final String assetId;
  final String deliveryUrl;
  final String mediaType;
  final String mimeType;
  final int fileSizeBytes;
  final int? durationMs;
  final List<double> waveform;
  final String? thumbnailUrl;
  final String? fileName;
}

String _required(String value, String field) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, field, 'must be a non-empty string');
  }
  return normalized;
}

String? _optional(String? value) {
  final normalized = value?.trim() ?? '';
  return normalized.isEmpty ? null : normalized;
}
