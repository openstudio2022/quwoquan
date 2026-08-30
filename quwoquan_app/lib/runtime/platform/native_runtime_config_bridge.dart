import 'dart:async';

import 'package:flutter/services.dart';

import 'native_runtime_config_bridge_stub.dart'
    if (dart.library.js_interop) 'native_runtime_config_bridge_web.dart'
    as platform_config;

const MethodChannel _runtimeConfigChannel = MethodChannel(
  'quwoquan/runtime/config',
);

abstract interface class RuntimeConfigChannelClient {
  Future<Object?> invokeMethod(String method);
}

class MethodChannelRuntimeConfigClient implements RuntimeConfigChannelClient {
  const MethodChannelRuntimeConfigClient();

  @override
  Future<Object?> invokeMethod(String method) {
    return _runtimeConfigChannel.invokeMethod<Object?>(method);
  }
}

enum NativeRuntimeConfigReadFailureReason {
  missingPlugin,
  platform,
  timeout,
  emptyPackage,
  malformedPackage,
}

class NativeRuntimeConfigReadException implements Exception {
  const NativeRuntimeConfigReadException({
    required this.reason,
    required this.attempts,
    this.platformCode,
  });

  final NativeRuntimeConfigReadFailureReason reason;
  final int attempts;
  final String? platformCode;

  @override
  String toString() =>
      'NativeRuntimeConfigReadException(reason: ${reason.name}, '
      'attempts: $attempts, platformCode: $platformCode)';
}

class NativeRuntimeConfigBridge {
  const NativeRuntimeConfigBridge({
    this.client,
    this.maxAttempts = 3,
    this.retryDelay = const Duration(milliseconds: 80),
    this.attemptTimeout = const Duration(seconds: 2),
  });

  final RuntimeConfigChannelClient? client;
  final int maxAttempts;
  final Duration retryDelay;
  final Duration attemptTimeout;

  Future<Map<String, Object?>> readRuntimePackage() async {
    final injectedClient = client;
    if (injectedClient == null) {
      try {
        final webPackage = platform_config.readVerifiedRuntimeConfigPackage();
        if (webPackage != null) {
          return webPackage;
        }
      } on Object {
        throw const NativeRuntimeConfigReadException(
          reason: NativeRuntimeConfigReadFailureReason.malformedPackage,
          attempts: 1,
        );
      }
    }
    final channelClient =
        injectedClient ?? const MethodChannelRuntimeConfigClient();
    NativeRuntimeConfigReadException? lastFailure;
    for (var attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        final raw = await channelClient
            .invokeMethod('readRuntimeConfig')
            .timeout(attemptTimeout);
        if (raw is! Map) {
          lastFailure = NativeRuntimeConfigReadException(
            reason: NativeRuntimeConfigReadFailureReason.malformedPackage,
            attempts: attempt,
          );
        } else {
          try {
            final package = Map<String, Object?>.from(raw);
            if (package.isNotEmpty) {
              return package;
            }
            lastFailure = NativeRuntimeConfigReadException(
              reason: NativeRuntimeConfigReadFailureReason.emptyPackage,
              attempts: attempt,
            );
          } on TypeError {
            lastFailure = NativeRuntimeConfigReadException(
              reason: NativeRuntimeConfigReadFailureReason.malformedPackage,
              attempts: attempt,
            );
          }
        }
      } on MissingPluginException {
        lastFailure = NativeRuntimeConfigReadException(
          reason: NativeRuntimeConfigReadFailureReason.missingPlugin,
          attempts: attempt,
        );
      } on PlatformException catch (error) {
        lastFailure = NativeRuntimeConfigReadException(
          reason: NativeRuntimeConfigReadFailureReason.platform,
          attempts: attempt,
          platformCode: error.code,
        );
      } on TimeoutException {
        lastFailure = NativeRuntimeConfigReadException(
          reason: NativeRuntimeConfigReadFailureReason.timeout,
          attempts: attempt,
        );
      }
      if (attempt < maxAttempts) {
        await Future<void>.delayed(retryDelay);
      }
    }
    throw lastFailure ??
        NativeRuntimeConfigReadException(
          reason: NativeRuntimeConfigReadFailureReason.emptyPackage,
          attempts: maxAttempts,
        );
  }
}
