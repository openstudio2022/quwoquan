import 'dart:convert';

final class ContentAddressedUploadHeaders {
  ContentAddressedUploadHeaders({
    required String contentType,
    required String expectedSha256,
  }) : contentType = contentType.trim(),
       expectedSha256 = _normalizeSha256(expectedSha256),
       checksumBase64 = base64Encode(_decodeSha256(expectedSha256)) {
    if (this.contentType.isEmpty) {
      throw ArgumentError.value(
        contentType,
        'contentType',
        'must not be empty',
      );
    }
  }

  final String contentType;
  final String expectedSha256;
  final String checksumBase64;

  Map<String, String> toHttpHeaders() => <String, String>{
    'Content-Type': contentType,
    'X-Amz-Checksum-Sha256': checksumBase64,
    'X-Amz-Meta-Sha256': expectedSha256,
  };
}

String _normalizeSha256(String value) {
  final normalized = value.trim().toLowerCase();
  final raw = normalized.startsWith('sha256:')
      ? normalized.substring('sha256:'.length)
      : normalized;
  if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(raw)) {
    throw ArgumentError.value(value, 'expectedSha256', 'must be SHA-256');
  }
  return 'sha256:$raw';
}

List<int> _decodeSha256(String value) {
  final normalized = _normalizeSha256(value);
  final raw = normalized.substring('sha256:'.length);
  return List<int>.generate(
    32,
    (index) => int.parse(raw.substring(index * 2, index * 2 + 2), radix: 16),
    growable: false,
  );
}
