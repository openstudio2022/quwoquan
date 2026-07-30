import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

Future<Object?> decodeJsonInBackground(Uint8List bytes) {
  final transferable = TransferableTypedData.fromList(<Uint8List>[bytes]);
  return Isolate.run<Object?>(() {
    final transferredBytes = transferable.materialize().asUint8List();
    return jsonDecode(utf8.decode(transferredBytes));
  }, debugName: 'cloud_json_decode');
}
