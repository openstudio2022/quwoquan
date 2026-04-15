import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/intent_bridge/adapters/method_channel_adapter.dart';
import 'package:quwoquan_app/assistant/tool/impl/device/local_context_tool.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class _FakeMethodChannelAdapter extends MethodChannelAdapter {
  _FakeMethodChannelAdapter(this._handler)
    : super(channel: const MethodChannel('test/local_context'));

  final Future<Map<String, dynamic>> Function(
    String method,
    Map<String, dynamic> arguments,
  )
  _handler;

  @override
  Future<Map<String, dynamic>> invoke(
    String method,
    Map<String, dynamic> arguments,
  ) {
    return _handler(method, arguments);
  }
}

void main() {
  group('LocalContextTool', () {
    test('uses explicit typed arguments for method channel invocation', () async {
      late String invokedMethod;
      late Map<String, dynamic> invokedArguments;
      final tool = LocalContextTool(
        _FakeMethodChannelAdapter((method, arguments) async {
          invokedMethod = method;
          invokedArguments = arguments;
          return <String, dynamic>{
            'city': '深圳',
            'location': <String, dynamic>{'city': '深圳'},
          };
        }),
      );

      final result = await tool.execute(
        AssistantToolArguments.fromJson(<String, dynamic>{
          'requestedFields': <String>['location', 'device', 'unknown'],
          'needPreciseLocation': true,
          'maxAgeSeconds': '60',
        }),
      );

      expect(result.success, isTrue);
      expect(invokedMethod, equals('getLocalContext'));
      expect(
        invokedArguments,
        equals(<String, dynamic>{
          'requestedFields': <String>['location', 'device'],
          'needPreciseLocation': true,
          'maxAgeSeconds': 60,
        }),
      );
    });

    test('returns structured failure payload instead of loose object bag', () async {
      final tool = LocalContextTool(
        _FakeMethodChannelAdapter((_, __) async {
          return <String, dynamic>{'error': 503};
        }),
      );

      final result = await tool.execute(AssistantToolArguments());

      expect(result.success, isFalse);
      expect(result.errorCode, AssistantErrorCode.executionFailed);
      expect(result.data?['userMessage'], equals('本地上下文暂不可用'));
      expect(result.data?['internalError'], equals('503'));
    });

    test('normalizes successful payload into explicit local context contract', () async {
      final tool = LocalContextTool(
        _FakeMethodChannelAdapter((_, __) async {
          return <String, dynamic>{
            'currentCity': '上海',
            'gpsLocation': <String, dynamic>{
              'lat': 31.23,
              'lon': 121.47,
              'accuracy': 12,
              'source': 'gps',
            },
            'permissions': <String, dynamic>{
              'location': 'granted',
              'camera': false,
            },
            'device': <String, dynamic>{
              'os': 'ios',
              'model': 'iPhone',
              'locale': 'zh_CN',
              'timezone': 'Asia/Shanghai',
            },
          };
        }),
      );

      final result = await tool.execute(AssistantToolArguments());

      expect(result.success, isTrue);
      expect(result.data?['contextVersion'], equals('local_context_v1'));
      expect(result.data?['city'], equals('上海'));
      expect((result.data?['location'] as Map?)?['latitude'], equals(31.23));
      expect((result.data?['permissions'] as Map?)?['location'], isTrue);
      expect((result.data?['device'] as Map?)?['timezone'], equals('Asia/Shanghai'));
      expect((result.data?['media'] as Map?)?['included'], isFalse);
    });
  });
}
