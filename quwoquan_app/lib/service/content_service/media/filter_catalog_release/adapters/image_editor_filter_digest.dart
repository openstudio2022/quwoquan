import 'dart:convert';

import 'package:crypto/crypto.dart';

String computeImageEditorFilterDigest(String canonicalJson) {
  return sha256.convert(utf8.encode(canonicalJson)).toString();
}
