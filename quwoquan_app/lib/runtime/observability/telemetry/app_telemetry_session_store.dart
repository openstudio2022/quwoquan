import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/widgets.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class AppTelemetryGuestKeyStore {
  Future<String?> read();

  Future<void> write(String value);
}

final class SecureAppTelemetryGuestKeyStore
    implements AppTelemetryGuestKeyStore {
  const SecureAppTelemetryGuestKeyStore()
    : _storage = const FlutterSecureStorage();

  static const _key = 'qwq.telemetry.guest_key';
  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: _key);

  @override
  Future<void> write(String value) => _storage.write(key: _key, value: value);
}

final class AppTelemetrySessionChange {
  const AppTelemetrySessionChange({
    required this.previousSessionId,
    required this.currentSessionId,
    required this.reason,
  });

  final String previousSessionId;
  final String currentSessionId;
  final String reason;
}

/// 产品遥测的主体与 App 生命周期会话真相源。
///
/// `inactive` 不切会话；`paused/hidden/detached` 结束，下一次 resumed 重建。
/// actor 变化立即切会话，旧 actor outbox 的处理由组合根负责，禁止重绑。
final class AppTelemetrySessionStore with WidgetsBindingObserver {
  AppTelemetrySessionStore({
    AppTelemetryGuestKeyStore? guestKeyStore,
    DateTime Function()? now,
    Random? random,
  }) : _guestKeyStore =
           guestKeyStore ?? const SecureAppTelemetryGuestKeyStore(),
       _now = now ?? DateTime.now,
       _random = random ?? Random.secure();

  static final AppTelemetrySessionStore instance = AppTelemetrySessionStore();

  final AppTelemetryGuestKeyStore _guestKeyStore;
  final DateTime Function() _now;
  final Random _random;
  final StreamController<AppTelemetrySessionChange> _changes =
      StreamController<AppTelemetrySessionChange>.broadcast(sync: true);

  String _guestKey = '';
  String _actorKey = '';
  String _sessionId = '';
  int _lastSessionStartMs = -1;
  bool _endedForBackground = false;
  bool _initialized = false;

  Stream<AppTelemetrySessionChange> get changes => _changes.stream;

  bool get isInitialized => _initialized;

  String get actorKey => _actorKey;

  String get sessionId {
    if (!_initialized) {
      throw StateError(
        'AppTelemetrySessionStore.initialize must complete first',
      );
    }
    if (_sessionId.isEmpty) {
      _rotate(reason: 'lazy_session');
    }
    return _sessionId;
  }

  /// 冷启动同步入口：立刻给出可用 guest/session，不触碰 SecureStorage。
  ///
  /// Android KeyStore / algorithm migration 可能耗数秒；若在 `runApp` 前
  /// `await` 会挤爆原生 6 秒首帧预算，误触 `native_first_frame_timeout`。
  void bootstrapForColdStart({String authenticatedUserKey = ''}) {
    if (!_initialized) {
      _guestKey = 'guest_${_newUlid()}';
      _initialized = true;
      try {
        WidgetsBinding.instance.addObserver(this);
      } catch (_) {
        // Unit tests can run without a WidgetsBinding.
      }
      updateActor(authenticatedUserKey, reason: 'initialize');
      return;
    }
    updateActor(authenticatedUserKey, reason: 'initialize');
  }

  /// 将内存 guest key 与 SecureStorage 对齐；允许在首帧后并行完成。
  Future<void> reconcilePersistedGuestKey() async {
    if (!_initialized) {
      bootstrapForColdStart();
    }
    final stored = (await _guestKeyStore.read())?.trim() ?? '';
    if (_isValidGuestKey(stored)) {
      if (stored == _guestKey) {
        return;
      }
      final previousActor = _actorKey;
      _guestKey = stored;
      if (previousActor.isEmpty || previousActor.startsWith('guest_')) {
        updateActor('', reason: 'guest_key_hydrate');
      }
      return;
    }
    await _guestKeyStore.write(_guestKey);
  }

  Future<void> initialize({String authenticatedUserKey = ''}) async {
    if (!_initialized) {
      bootstrapForColdStart(authenticatedUserKey: authenticatedUserKey);
      await reconcilePersistedGuestKey();
      return;
    }
    updateActor(authenticatedUserKey, reason: 'initialize');
  }

  void updateActor(String authenticatedUserKey, {String reason = 'actor'}) {
    if (!_initialized) {
      throw StateError(
        'AppTelemetrySessionStore.initialize must complete first',
      );
    }
    final next = authenticatedUserKey.trim().isEmpty
        ? _guestKey
        : authenticatedUserKey.trim();
    if (next == _actorKey && _sessionId.isNotEmpty) return;
    _actorKey = next;
    _endedForBackground = false;
    _rotate(reason: reason);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.inactive:
        return;
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
      case AppLifecycleState.detached:
        _endedForBackground = true;
        return;
      case AppLifecycleState.resumed:
        if (_endedForBackground) {
          _endedForBackground = false;
          _rotate(reason: 'foreground_resume');
        }
        return;
    }
  }

  void dispose() {
    try {
      WidgetsBinding.instance.removeObserver(this);
    } catch (_) {
      // Ignore when initialization happened without a binding.
    }
    unawaited(_changes.close());
  }

  static String encodeUserKey(String userKey) =>
      base64Url.encode(utf8.encode(userKey)).replaceAll('=', '');

  static String decodeUserKey(String encoded) {
    final padding = '=' * ((4 - encoded.length % 4) % 4);
    return utf8.decode(base64Url.decode('$encoded$padding'));
  }

  static ({String userKey, int startedAtMs}) parseSessionId(String sessionId) {
    if (!sessionId.startsWith('s.')) {
      throw const FormatException('invalid session prefix');
    }
    final separator = sessionId.lastIndexOf('.');
    if (separator <= 2 || separator == sessionId.length - 1) {
      throw const FormatException('invalid session shape');
    }
    final startedAtMs = int.tryParse(sessionId.substring(separator + 1));
    if (startedAtMs == null || startedAtMs < 0) {
      throw const FormatException('invalid session timestamp');
    }
    return (
      userKey: decodeUserKey(sessionId.substring(2, separator)),
      startedAtMs: startedAtMs,
    );
  }

  void _rotate({required String reason}) {
    if (_actorKey.isEmpty) {
      throw StateError('telemetry actor key is empty');
    }
    final previous = _sessionId;
    var startedAtMs = _now().millisecondsSinceEpoch;
    if (startedAtMs <= _lastSessionStartMs) {
      startedAtMs = _lastSessionStartMs + 1;
    }
    _lastSessionStartMs = startedAtMs;
    _sessionId = 's.${encodeUserKey(_actorKey)}.$startedAtMs';
    _changes.add(
      AppTelemetrySessionChange(
        previousSessionId: previous,
        currentSessionId: _sessionId,
        reason: reason,
      ),
    );
  }

  bool _isValidGuestKey(String value) =>
      value.startsWith('guest_') && value.length == 32;

  String _newUlid() {
    const alphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
    var value = BigInt.from(_now().millisecondsSinceEpoch);
    value =
        (value << 80) |
        BigInt.parse(
          List<int>.generate(
            10,
            (_) => _random.nextInt(256),
          ).map((value) => value.toRadixString(16).padLeft(2, '0')).join(),
          radix: 16,
        );
    final chars = List<String>.filled(26, '0');
    for (var index = chars.length - 1; index >= 0; index--) {
      chars[index] = alphabet[(value & BigInt.from(31)).toInt()];
      value >>= 5;
    }
    return chars.join();
  }
}
