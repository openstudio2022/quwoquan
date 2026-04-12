// ASSISTANT_WEAK_TYPE: JSON_BOUNDARY — Run `structuredResponse` 根 Map 的单根只读投影；持久化仍为 Map。

import 'package:quwoquan_app/assistant/contracts/assistant_structured_response_wire.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

/// 与端云 Run `structuredResponse` **同一张根 JSON** 对齐的只读 bundle（非第二份序列化形状）。
///
/// 将 [runArtifacts] 与 [AssistantStructuredResponseWire] 子树从同一 [structuredResponseRoot] 投影出来，
/// 供业务路径避免手写键名拼装。
final class AssistantRunStructuredBundle {
  const AssistantRunStructuredBundle({
    required this.structuredResponseRoot,
    this.runArtifacts,
    required this.structuredWire,
  });

  final Map<String, dynamic> structuredResponseRoot;
  final RunArtifacts? runArtifacts;
  final AssistantStructuredResponseWire structuredWire;

  factory AssistantRunStructuredBundle.fromStructuredResponseRoot(
    Map<String, dynamic> json,
  ) {
    final raRaw = (json['runArtifacts'] as Map?)?.cast<String, dynamic>();
    return AssistantRunStructuredBundle(
      structuredResponseRoot: json,
      runArtifacts: raRaw == null ? null : parseRunArtifacts(raRaw),
      structuredWire: assistantStructuredWireFromStructuredRoot(json),
    );
  }
}
