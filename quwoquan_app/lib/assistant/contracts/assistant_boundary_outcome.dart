import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum AssistantBoundaryStatus { ok, partial, blocked, failed }

class AssistantBoundaryOutcome {
  const AssistantBoundaryOutcome({
    required this.status,
    required this.boundary,
    required this.stage,
    this.failure,
    this.disruptionLevel = UserDisruptionLevel.silent,
    this.canContinue = true,
    this.canAnswerPartially = false,
  });

  const AssistantBoundaryOutcome.ok({
    required String boundary,
    required String stage,
  }) : this(
         status: AssistantBoundaryStatus.ok,
         boundary: boundary,
         stage: stage,
       );

  final AssistantBoundaryStatus status;
  final String boundary;
  final String stage;
  final RuntimeFailureBase? failure;
  final UserDisruptionLevel disruptionLevel;
  final bool canContinue;
  final bool canAnswerPartially;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'status': status.name,
      'boundary': boundary,
      'stage': stage,
      if (failure != null) 'failure': _failureToJson(failure!),
      'disruptionLevel': disruptionLevel.name,
      'canContinue': canContinue,
      'canAnswerPartially': canAnswerPartially,
    };
  }

  factory AssistantBoundaryOutcome.fromJson(Map<String, dynamic> json) {
    return AssistantBoundaryOutcome(
      status: _enumByName(
        AssistantBoundaryStatus.values,
        json['status'],
        AssistantBoundaryStatus.ok,
      ),
      boundary: (json['boundary'] as String?) ?? '',
      stage: (json['stage'] as String?) ?? '',
      failure: json['failure'] is Map
          ? RuntimeFailure.fromJson(
              (json['failure'] as Map).cast<String, dynamic>(),
            )
          : null,
      disruptionLevel: _enumByName(
        UserDisruptionLevel.values,
        json['disruptionLevel'],
        UserDisruptionLevel.silent,
      ),
      canContinue: json['canContinue'] != false,
      canAnswerPartially: json['canAnswerPartially'] == true,
    );
  }
}

Map<String, dynamic> _failureToJson(RuntimeFailureBase failure) {
  return <String, dynamic>{
    'code': failure.code,
    'origin': failure.origin.name,
    'kind': failure.kind.name,
    'nature': failure.nature.name,
    'location': failure.location.toJson(),
    'context': failure.context.toJson(),
  };
}

T _enumByName<T extends Enum>(List<T> values, Object? raw, T fallback) {
  if (raw is! String) return fallback;
  for (final value in values) {
    if (value.name == raw.trim()) return value;
  }
  return fallback;
}
