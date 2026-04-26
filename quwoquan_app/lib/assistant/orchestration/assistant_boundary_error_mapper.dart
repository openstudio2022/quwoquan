import 'package:quwoquan_app/assistant/contracts/assistant_boundary_outcome.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

class AssistantBoundaryErrorMapper {
  const AssistantBoundaryErrorMapper();

  AssistantBoundaryOutcome failed({
    required String boundary,
    required String stage,
    required String code,
    required RuntimeFailureKind kind,
    RuntimeFailureOrigin origin = RuntimeFailureOrigin.system,
    RuntimeFailureNature nature = RuntimeFailureNature.bug,
    String businessObject = 'assistant_turn',
    String functionModule = 'pipeline_engine',
    List<RuntimeContextAttribute> attributes =
        const <RuntimeContextAttribute>[],
    UserDisruptionLevel disruptionLevel = UserDisruptionLevel.inlineCard,
    bool canContinue = false,
    bool canAnswerPartially = false,
  }) {
    return AssistantBoundaryOutcome(
      status: canAnswerPartially
          ? AssistantBoundaryStatus.partial
          : AssistantBoundaryStatus.failed,
      boundary: boundary,
      stage: stage,
      failure: RuntimeFailure(
        code: code,
        origin: origin,
        kind: kind,
        nature: nature,
        location: RuntimeFailureLocation(
          businessObject: businessObject,
          functionModule: functionModule,
        ),
        context: RuntimeFailureContext(attributes: attributes),
      ),
      disruptionLevel: disruptionLevel,
      canContinue: canContinue,
      canAnswerPartially: canAnswerPartially,
    );
  }

  AssistantBoundaryOutcome blocked({
    required String boundary,
    required String stage,
    required RuntimeFailureBase failure,
    UserDisruptionLevel disruptionLevel = UserDisruptionLevel.inlineCard,
  }) {
    return AssistantBoundaryOutcome(
      status: AssistantBoundaryStatus.blocked,
      boundary: boundary,
      stage: stage,
      failure: failure,
      disruptionLevel: disruptionLevel,
      canContinue: false,
    );
  }
}
