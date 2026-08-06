import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// Message-home application boundary for locally cached canonical rows.
///
/// The concrete conversation cache remains hidden behind runtime DI. The
/// message object exchanges generated value types only.
abstract interface class MessageHomeCache {
  void putMessageHomeRows(Iterable<MessageHomeRow> rows);

  List<MessageHomeRow> readMessageHomeRows();
}
