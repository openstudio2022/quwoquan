export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/generated/run_artifacts.g.dart';
export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/run_artifacts_map_partition.dart';
export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/generated/run_artifacts_map_stable_keys.g.dart';
export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/slot_value_codec.dart';
export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart'
    show
        DisplayBlockKind,
        DisplayListStyle,
        ProcessStepId,
        ProcessDisplayBlockKind,
        SlotValueStatus,
        TraceVisibility,
        parseDisplayBlockKind,
        parseDisplayListStyle,
        parseProcessStepId,
        parseProcessDisplayBlockKind,
        parseSlotValueStatus,
        parseTraceVisibility;

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/generated/run_artifacts.g.dart';

RunArtifacts parseRunArtifacts(Map<String, dynamic> json) =>
    RunArtifacts.fromJson(json);
