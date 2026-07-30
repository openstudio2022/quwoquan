import 'dart:convert';
import 'dart:typed_data';

Future<Object?> decodeJsonInBackground(Uint8List bytes) async {
  // Let the current frame finish first. Unlike native targets, Dart web does
  // not expose a transferable worker isolate through this pure runtime layer.
  await Future<void>.delayed(Duration.zero);
  return jsonDecode(utf8.decode(bytes));
}
