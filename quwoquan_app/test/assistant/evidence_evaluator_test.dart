import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/context/assembly/evidence_evaluator.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

void main() {
  group('DefaultEvidenceEvaluator', () {
    const evaluator = DefaultEvidenceEvaluator();

    test('canonicalizes fallback fetch data and preserves display source', () {
      final ledger = evaluator.buildLedger(
        domainId: 'weather',
        toolResults: <Map<String, dynamic>>[
          <String, dynamic>{
            'toolName': 'web_fetch',
            'data': <String, dynamic>{
              'url':
                  'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.cma.cn%2Fshenzhen%3Futm_source%3Dfeed',
              'title': 'Ã¤Â¸Â­å›½å¤©æ°”',
              'source': '中国气象局',
              'content': '深圳今天晴，约 25°C。',
              'queryTaskId': 'weather_now',
              'dimension': 'current_weather',
            },
          },
        ],
        slotState: const SlotStateSnapshot(domainId: 'weather'),
        retrievalPolicy: const <String, dynamic>{},
      );

      expect(ledger, hasLength(1));
      expect(ledger.first.url, equals('https://weather.cma.cn/shenzhen'));
      expect(ledger.first.source, equals('中国气象局'));
      expect(ledger.first.sourceHost, equals('weather.cma.cn'));
      expect(ledger.first.title, equals('weather.cma.cn shenzhen'));
      expect(ledger.first.snippet, contains('深圳今天晴'));
    });

    test('deduplicates tracked variants after canonicalization', () {
      final ledger = evaluator.buildLedger(
        domainId: 'weather',
        toolResults: <Map<String, dynamic>>[
          <String, dynamic>{
            'toolName': 'web_search',
            'data': <String, dynamic>{
              'references': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '深圳天气预报',
                  'url':
                      'https://duckduckgo.com/l/?uddg=https%3A%2F%2Fweather.cma.cn%2Fshenzhen%3Futm_source%3Dfeed',
                  'source': '中国气象局',
                  'snippet': '深圳今天晴，约 25°C。',
                },
                <String, dynamic>{
                  'title': '深圳天气预报',
                  'url': 'https://weather.cma.cn/shenzhen?utm_medium=card',
                  'source': '中国气象局',
                  'snippet': '深圳今天晴，约 25°C。',
                },
              ],
            },
          },
        ],
        slotState: const SlotStateSnapshot(domainId: 'weather'),
        retrievalPolicy: const <String, dynamic>{},
      );

      expect(ledger, hasLength(1));
      expect(ledger.first.url, equals('https://weather.cma.cn/shenzhen'));
      expect(ledger.first.source, equals('中国气象局'));
    });
  });
}
