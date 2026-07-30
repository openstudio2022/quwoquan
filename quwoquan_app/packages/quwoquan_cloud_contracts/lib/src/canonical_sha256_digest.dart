/// Returns whether [value] is the canonical wire identity for one SHA-256
/// digest: `sha256:` followed by exactly 64 lowercase hexadecimal characters.
bool isCanonicalSha256Digest(String value) =>
    _canonicalSha256DigestPattern.hasMatch(value);

final RegExp _canonicalSha256DigestPattern = RegExp(r'^sha256:[0-9a-f]{64}$');
