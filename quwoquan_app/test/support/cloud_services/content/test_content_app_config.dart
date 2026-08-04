import 'package:quwoquan_app/cloud/runtime/models/app_remote_config_snapshot.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

Map<String, Object?> testSignedAppConfigRoot({
  Map<String, Object?> content = const <String, Object?>{},
  String defaultActivation = 'next_session',
  DateTime? fetchedAt,
  int maxAgeSec = 60,
}) {
  final root = <String, Object?>{
    'schema': AppRemoteConfigSnapshot.canonicalSchema,
    'fetchedAt': (fetchedAt ?? DateTime.utc(2026, 7, 29)).toIso8601String(),
    'maxAgeSec': maxAgeSec,
    'activationPolicy': <String, Object?>{
      'default': defaultActivation,
      'kill_switches': 'immediate',
    },
    'content': <String, Object?>{
      'feature_flags': const <String, Object?>{},
      'gray_release': const <String, Object?>{
        'experiment_bucket': 'control',
        'current_stage': 'control',
        'canary_matrix': <Object?>[],
      },
      ...content,
    },
  };
  root['configHash'] = AppRemoteConfigSnapshot.calculateConfigHash(root);
  return root;
}

AppConfigSlice testAppConfigSlice({
  Map<String, Object?> content = const <String, Object?>{},
  String defaultActivation = 'next_session',
  DateTime? fetchedAt,
  int maxAgeSec = 60,
}) {
  return AppConfigSlice.fromWire(
    testSignedAppConfigRoot(
      content: content,
      defaultActivation: defaultActivation,
      fetchedAt: fetchedAt,
      maxAgeSec: maxAgeSec,
    ),
  );
}
