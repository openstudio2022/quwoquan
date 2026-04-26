import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';

class TurnSynthesisState {
  const TurnSynthesisState({
    this.contractId = 'turn_synthesis_state',
    this.interactionDirective = const InteractionDirective(),
    this.completedIntentIds = const <String>[],
    this.remainingIntentIds = const <String>[],
    this.blockedIntentIds = const <String>[],
  });

  final String contractId;
  final InteractionDirective interactionDirective;
  final List<String> completedIntentIds;
  final List<String> remainingIntentIds;
  final List<String> blockedIntentIds;

  Map<String, dynamic> toJson() => <String, dynamic>{
        'contractId': contractId,
        'interactionDirective': interactionDirective.toJson(),
        'completedIntentIds': completedIntentIds,
        'remainingIntentIds': remainingIntentIds,
        'blockedIntentIds': blockedIntentIds,
      };

  factory TurnSynthesisState.fromJson(Map<String, dynamic> json) {
    return TurnSynthesisState(
      contractId:
          (json['contractId'] as String?)?.trim() ?? 'turn_synthesis_state',
      interactionDirective: InteractionDirective.fromJson(
        json['interactionDirective'],
      ),
      completedIntentIds: _stringList(json['completedIntentIds']),
      remainingIntentIds: _stringList(json['remainingIntentIds']),
      blockedIntentIds: _stringList(json['blockedIntentIds']),
    );
  }
}

List<String> _stringList(Object? value) {
  if (value is! List) {
    return const <String>[];
  }
  return value
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}
