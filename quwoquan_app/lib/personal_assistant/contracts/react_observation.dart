export 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/react_observation.g.dart';

import 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/react_observation.g.dart';

class ReactObservation extends ReactObservationDto {
  const ReactObservation({
    super.status = '',
    super.retryable = false,
    super.errorClass = '',
    super.coverage = 0.0,
    super.confidence = 0.0,
    super.freshnessHours = 0.0,
  });

  factory ReactObservation.fromObservationMap(Map<String, dynamic> raw) {
    final data = (raw['data'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return ReactObservation(
      status: (raw['status'] as String?)?.trim() ?? '',
      retryable: raw['retryable'] == true,
      errorClass: (raw['errorClass'] as String?)?.trim() ?? '',
      coverage: _toDouble(data['coverage'] ?? data['coverageScore']),
      confidence: _toDouble(data['confidence'] ?? data['confidenceScore']),
      freshnessHours: _toDouble(data['freshnessHours']),
    );
  }

  static double _toDouble(Object? value) {
    if (value is num) return value.toDouble();
    return double.tryParse((value ?? '').toString()) ?? 0;
  }
}
