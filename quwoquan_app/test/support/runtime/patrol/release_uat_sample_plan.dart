library;

import 'dart:convert';
import 'dart:typed_data';

const List<String> releaseUatEntries = <String>[
  'feed',
  'search',
  'recommendation',
  'direct_or_object_route',
];
const List<String> releaseUatCarriers = <String>[
  'homepage',
  'article',
  'image',
  'video',
];

final class ReleaseUatSample {
  const ReleaseUatSample({
    required this.sampleId,
    required this.carrier,
    required this.objectId,
    required this.objectRef,
    required this.objectDigest,
    required this.runtimeObjectId,
  });

  final String sampleId;
  final String carrier;
  final String objectId;
  final String objectRef;
  final String objectDigest;
  final String runtimeObjectId;
}

final class ReleaseUatSlot {
  const ReleaseUatSlot({
    required this.sample,
    required this.entrySurface,
    required this.specRef,
    required this.runnerIdentity,
  });

  final ReleaseUatSample sample;
  final String entrySurface;
  final String specRef;
  final String runnerIdentity;

  String get captureId =>
      '${sample.sampleId}--$entrySurface--${sample.carrier}';
}

final class ReleaseUatSampleMatrix {
  const ReleaseUatSampleMatrix({
    required this.releaseId,
    required this.exactPlanBytes,
    required this.samples,
    required this.slots,
  });

  final String releaseId;
  final Uint8List exactPlanBytes;
  final List<ReleaseUatSample> samples;
  final List<ReleaseUatSlot> slots;
}

ReleaseUatSampleMatrix parseReleaseUatSampleMatrix({
  required String encodedPlan,
  required String encodedRuntimeBinding,
}) {
  final planBytes = _decodeBase64(encodedPlan, label: 'ReleaseUatSamplePlan');
  final plan = _decodeObject(planBytes, label: 'ReleaseUatSamplePlan');
  final binding = _decodeObject(
    _decodeBase64(encodedRuntimeBinding, label: 'release runtime binding'),
    label: 'release runtime binding',
  );
  if (plan['schema'] != 'quwoquan_data.release_uat_sample_plan') {
    throw const FormatException('ReleaseUatSamplePlan schema is invalid');
  }
  if (binding['schema'] != 'quwoquan_ops.app_uat_sample_runtime_binding.v1') {
    throw const FormatException('release runtime binding schema is invalid');
  }
  final releaseId = _text(plan['releaseId'], 'ReleaseUatSamplePlan.releaseId');
  if (binding['releaseId'] != releaseId) {
    throw const FormatException('release runtime binding releaseId drifted');
  }

  final rawSamples = _list(plan['samples'], 'ReleaseUatSamplePlan.samples');
  if (rawSamples.length != releaseUatCarriers.length ||
      plan['sampleCount'] != rawSamples.length) {
    throw const FormatException(
      '16-slot Patrol UAT requires exactly one sample per carrier',
    );
  }
  final rawBindings = _list(
    binding['samples'],
    'release runtime binding.samples',
  );
  final runtimeBySample = <String, Map<String, Object?>>{};
  for (var index = 0; index < rawBindings.length; index += 1) {
    final row = _object(rawBindings[index], 'runtime sample $index');
    if (row.keys.toSet().difference(const <String>{
          'sampleId',
          'carrier',
          'sourceObjectId',
          'readObjectId',
        }).isNotEmpty ||
        row.length != 4) {
      throw FormatException('runtime sample $index fields are invalid');
    }
    final sampleId = _text(row['sampleId'], 'runtime sample $index.sampleId');
    if (runtimeBySample.putIfAbsent(sampleId, () => row) != row) {
      throw const FormatException('release runtime sampleId is duplicated');
    }
  }

  final samples = <ReleaseUatSample>[];
  final observedCarriers = <String>{};
  final observedIds = <String>{};
  for (var index = 0; index < rawSamples.length; index += 1) {
    final row = _object(rawSamples[index], 'sample $index');
    if (row.length != 5 ||
        row.keys.toSet().difference(const <String>{
          'sampleId',
          'carrier',
          'objectId',
          'objectRef',
          'objectDigest',
        }).isNotEmpty) {
      throw FormatException('sample $index fields are invalid');
    }
    final sampleId = _text(row['sampleId'], 'sample $index.sampleId');
    final carrier = _text(row['carrier'], 'sample $index.carrier');
    final objectId = _text(row['objectId'], 'sample $index.objectId');
    final objectRef = _text(row['objectRef'], 'sample $index.objectRef');
    final objectDigest = _text(
      row['objectDigest'],
      'sample $index.objectDigest',
    );
    if (!releaseUatCarriers.contains(carrier) ||
        !observedCarriers.add(carrier) ||
        !observedIds.add(sampleId)) {
      throw const FormatException(
        'sample carrier/sampleId is duplicated or unknown',
      );
    }
    if (!RegExp(r'^sha256:[0-9a-f]{64}$').hasMatch(objectDigest)) {
      throw FormatException('sample $index.objectDigest is invalid');
    }
    final runtime = runtimeBySample[sampleId];
    if (runtime == null ||
        runtime['carrier'] != carrier ||
        runtime['sourceObjectId'] != objectId) {
      throw FormatException('runtime binding for $sampleId drifted');
    }
    samples.add(
      ReleaseUatSample(
        sampleId: sampleId,
        carrier: carrier,
        objectId: objectId,
        objectRef: objectRef,
        objectDigest: objectDigest,
        runtimeObjectId: _text(
          runtime['readObjectId'],
          'runtime binding $sampleId.readObjectId',
        ),
      ),
    );
  }
  if (observedCarriers.length != releaseUatCarriers.length ||
      runtimeBySample.length != samples.length) {
    throw const FormatException(
      'release sample/runtime coverage is incomplete',
    );
  }

  final sampleByCarrier = <String, ReleaseUatSample>{
    for (final sample in samples) sample.carrier: sample,
  };
  final rawCells = _list(
    plan['entryCarrierCells'],
    'ReleaseUatSamplePlan.entryCarrierCells',
  );
  if (rawCells.length != 16) {
    throw const FormatException('ReleaseUatSamplePlan must declare 16 cells');
  }
  final slots = <ReleaseUatSlot>[];
  for (var index = 0; index < rawCells.length; index += 1) {
    final row = _object(rawCells[index], 'entryCarrierCells[$index]');
    final expectedEntry = releaseUatEntries[index ~/ releaseUatCarriers.length];
    final expectedCarrier =
        releaseUatCarriers[index % releaseUatCarriers.length];
    if (row['entry'] != expectedEntry || row['carrier'] != expectedCarrier) {
      throw FormatException('entryCarrierCells[$index] order/identity drifted');
    }
    if (row['applicability'] != 'required') {
      throw FormatException('entryCarrierCells[$index] is not required');
    }
    slots.add(
      ReleaseUatSlot(
        sample: sampleByCarrier[expectedCarrier]!,
        entrySurface: expectedEntry,
        specRef: _text(row['specRef'], 'entryCarrierCells[$index].specRef'),
        runnerIdentity: _text(
          row['runnerClass'],
          'entryCarrierCells[$index].runnerClass',
        ),
      ),
    );
  }
  if (slots.map((slot) => slot.captureId).toSet().length != 16) {
    throw const FormatException(
      'ReleaseUatSamplePlan slot identity is duplicated',
    );
  }
  return ReleaseUatSampleMatrix(
    releaseId: releaseId,
    exactPlanBytes: Uint8List.fromList(planBytes),
    samples: List<ReleaseUatSample>.unmodifiable(samples),
    slots: List<ReleaseUatSlot>.unmodifiable(slots),
  );
}

Uint8List _decodeBase64(String encoded, {required String label}) {
  if (encoded.trim().isEmpty || encoded != encoded.trim()) {
    throw FormatException('$label base64 is missing or non-canonical');
  }
  try {
    return base64Decode(encoded);
  } on FormatException catch (error) {
    throw FormatException('$label base64 is invalid', error);
  }
}

Map<String, Object?> _decodeObject(Uint8List bytes, {required String label}) {
  try {
    return _object(jsonDecode(utf8.decode(bytes)), label);
  } on FormatException {
    rethrow;
  } catch (error) {
    throw FormatException('$label is not UTF-8 JSON', error);
  }
}

Map<String, Object?> _object(Object? value, String label) {
  if (value is! Map) throw FormatException('$label must be an object');
  return value.map<String, Object?>((key, value) {
    if (key is! String) throw FormatException('$label key is invalid');
    return MapEntry<String, Object?>(key, value);
  });
}

List<Object?> _list(Object? value, String label) {
  if (value is! List) throw FormatException('$label must be a list');
  return List<Object?>.from(value);
}

String _text(Object? value, String label) {
  if (value is! String || value.isEmpty || value != value.trim()) {
    throw FormatException('$label must be a non-empty canonical string');
  }
  return value;
}
