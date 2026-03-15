import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('web pipeline templates and thresholds are wired', () {
    final manifest = File('assets/assistant/prompts/manifest.json');
    expect(manifest.existsSync(), isTrue);
    final manifestDecoded = jsonDecode(manifest.readAsStringSync()) as Map;
    final templates =
        (manifestDecoded['templates'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final metaPaths = templates
        .map((item) => (item['metaPath'] ?? '').toString())
        .toList(growable: false);
    expect(
      metaPaths.contains(
        'assets/assistant/prompts/web/domain.web_query_plan.meta.json',
      ),
      isTrue,
    );
    expect(
      metaPaths.contains(
        'assets/assistant/prompts/web/domain.web_result_judge.meta.json',
      ),
      isTrue,
    );
    expect(
      metaPaths.contains(
        'assets/assistant/prompts/web/domain.web_key_fact_extract.meta.json',
      ),
      isTrue,
    );
    expect(
      metaPaths.contains(
        'assets/assistant/prompts/web/domain.web_evidence_pack.meta.json',
      ),
      isTrue,
    );

    final slotContract = File(
      'assets/assistant/prompts/_standards/slot_fill_contract.json',
    );
    expect(slotContract.existsSync(), isTrue);
    final slotDecoded = jsonDecode(slotContract.readAsStringSync()) as Map;
    final thresholds =
        (slotDecoded['evidenceThresholds'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(thresholds['coverageMin'], equals(0.7));
    expect(thresholds['confidenceMin'], equals(0.65));
    expect(thresholds['freshnessHoursMax'], equals(72));
  });
}
