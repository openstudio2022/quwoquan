import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final class TerminalAccountCleanupReceipt {
  const TerminalAccountCleanupReceipt({
    required this.accountId,
    required this.personaId,
    required this.installId,
  });

  final String accountId;
  final String personaId;
  final String installId;
}

abstract interface class TerminalAccountCleanupReceiptStore {
  Future<TerminalAccountCleanupReceipt?> read();

  Future<void> save(TerminalAccountCleanupReceipt receipt);

  Future<void> clear();
}

final class SecureTerminalAccountCleanupReceiptStore
    implements TerminalAccountCleanupReceiptStore {
  const SecureTerminalAccountCleanupReceiptStore({
    FlutterSecureStorage storage = const FlutterSecureStorage(),
  }) : this._withStorage(storage);

  const SecureTerminalAccountCleanupReceiptStore._withStorage(this._storage);

  static const String _key = 'qwq.account_closure.local_cleanup_pending';
  final FlutterSecureStorage _storage;

  @override
  Future<TerminalAccountCleanupReceipt?> read() async {
    final raw = await _storage.read(key: _key);
    if (raw == null || raw.trim().isEmpty) {
      return null;
    }
    final decoded = jsonDecode(raw);
    if (decoded is! Map) {
      throw const FormatException('terminal cleanup receipt must be an object');
    }
    final object = decoded.cast<String, Object?>();
    final accountId = object['accountId']?.toString().trim() ?? '';
    final personaId = object['personaId']?.toString().trim() ?? '';
    final installId = object['installId']?.toString().trim() ?? '';
    if (accountId.isEmpty || installId.isEmpty) {
      throw const FormatException('terminal cleanup receipt is incomplete');
    }
    return TerminalAccountCleanupReceipt(
      accountId: accountId,
      personaId: personaId,
      installId: installId,
    );
  }

  @override
  Future<void> save(TerminalAccountCleanupReceipt receipt) async {
    if (receipt.accountId.trim().isEmpty || receipt.installId.trim().isEmpty) {
      throw ArgumentError('terminal cleanup receipt actor is incomplete');
    }
    final encoded = jsonEncode(<String, String>{
      'accountId': receipt.accountId.trim(),
      'personaId': receipt.personaId.trim(),
      'installId': receipt.installId.trim(),
    });
    await _storage.write(key: _key, value: encoded);
    if (await _storage.read(key: _key) != encoded) {
      throw StateError('terminal cleanup receipt persistence failed');
    }
  }

  @override
  Future<void> clear() async {
    await _storage.delete(key: _key);
    if (await _storage.read(key: _key) != null) {
      throw StateError('terminal cleanup receipt removal failed');
    }
  }
}

final terminalAccountCleanupReceiptStoreProvider =
    Provider<TerminalAccountCleanupReceiptStore>(
      (ref) => const SecureTerminalAccountCleanupReceiptStore(),
    );
