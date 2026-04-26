import 'package:flutter/services.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class MethodChannelAdapter {
  MethodChannelAdapter({MethodChannel? channel})
    : _channel =
          channel ?? const MethodChannel('personal_assistant/native_api');

  final MethodChannel _channel;

  Future<Map<String, dynamic>> invoke(
    String method,
    Map<String, dynamic> arguments,
  ) async {
    try {
      final result = await _channel.invokeMethod<dynamic>(method, arguments);
      if (result is Map) {
        return Map<String, dynamic>.from(result);
      }
      return <String, dynamic>{'result': result};
    } on PlatformException catch (error) {
      final permissionLike =
          error.code.toLowerCase().contains('permission') ||
          error.code.toLowerCase().contains('denied');
      final failure = RuntimeFailure(
        code: permissionLike
            ? 'APP.PERMISSION.native_bridge_denied'
            : 'APP.SYSTEM.native_bridge_failure',
        origin: RuntimeFailureOrigin.localClient,
        kind: permissionLike
            ? RuntimeFailureKind.permission
            : RuntimeFailureKind.internal,
        nature: permissionLike
            ? RuntimeFailureNature.requiresPermission
            : RuntimeFailureNature.bug,
        location: const RuntimeFailureLocation(
          businessObject: 'native_bridge',
          functionModule: 'method_channel_adapter',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            RuntimeContextAttribute(key: 'method', value: method),
            RuntimeContextAttribute(key: 'platformCode', value: error.code),
          ],
        ),
      );
      return <String, dynamic>{'runtimeFailure': failure.toJson()};
    } catch (error) {
      final failure = RuntimeFailure(
        code: 'APP.SYSTEM.native_bridge_failure',
        origin: RuntimeFailureOrigin.localClient,
        kind: RuntimeFailureKind.internal,
        nature: RuntimeFailureNature.bug,
        location: const RuntimeFailureLocation(
          businessObject: 'native_bridge',
          functionModule: 'method_channel_adapter',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            RuntimeContextAttribute(key: 'method', value: method),
            RuntimeContextAttribute(
              key: 'errorType',
              value: error.runtimeType.toString(),
            ),
          ],
        ),
      );
      return <String, dynamic>{'runtimeFailure': failure.toJson()};
    }
  }
}
