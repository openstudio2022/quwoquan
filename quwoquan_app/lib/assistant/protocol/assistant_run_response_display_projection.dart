import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

abstract final class AssistantRunResponseDisplayProjector {
  static AssistantDisplayProjection? resolveDisplayProjection(
    AssistantRunResponse response,
  ) {
    final fromDisplayState = _projectFromDisplayState(response);
    if (fromDisplayState != null) return fromDisplayState;

    final fromStructuredResponse = _projectFromStructuredResponse(
      response.structuredResponse,
    );
    if (fromStructuredResponse != null) return fromStructuredResponse;

    final runArtifacts = response.runArtifacts;
    if (runArtifacts != null) {
      final normalizedMarkdown =
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
            runArtifacts.displayMarkdown,
            allowJsonExtraction: false,
          );
      if (normalizedMarkdown.isNotEmpty) {
        return AssistantDisplayProjection(markdown: normalizedMarkdown);
      }
      final normalizedPlainText =
          AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
            runArtifacts.displayPlainText,
            allowJsonExtraction: false,
          );
      if (normalizedPlainText.isNotEmpty) {
        return AssistantDisplayProjection(markdown: normalizedPlainText);
      }
    }

    return _projectFromRawText(response.finalText);
  }

  static String resolveDisplayMarkdown(AssistantRunResponse response) {
    return resolveDisplayProjection(response)?.markdown.trim() ?? '';
  }

  static String resolveDisplayPlainText(AssistantRunResponse response) {
    return resolveDisplayProjection(response)?.plainText.trim() ?? '';
  }

  static AssistantDisplayProjection? _projectFromDisplayState(
    AssistantRunResponse response,
  ) {
    final displayState = resolveAssistantDisplayStateFromRunResponse(response);
    if (displayState.answer.blocks.isNotEmpty) {
      final markdown = renderAnswerBlocksToMarkdown(
        displayState.answer.blocks,
      ).trim();
      if (markdown.isNotEmpty) {
        return AssistantDisplayProjection(markdown: markdown);
      }
      final plainText = renderAnswerBlocksToPlainText(
        displayState.answer.blocks,
      ).trim();
      if (plainText.isNotEmpty) {
        return AssistantDisplayProjection(markdown: plainText);
      }
    }
    return null;
  }

  static AssistantDisplayProjection? _projectFromStructuredResponse(
    Map<String, dynamic> payload,
  ) {
    if (payload.isEmpty) return null;
    final direct = _projectFromAssistantTurnMap(payload);
    if (direct != null) return direct;
    final nested =
        (payload['answerPayload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return _projectFromAssistantTurnMap(nested);
  }

  static AssistantDisplayProjection? _projectFromRawText(String raw) {
    final markdown =
        AssistantDisplayTextResolver.extractDisplayMarkdownFromStructuredText(
          raw,
        ).trim();
    final plainText =
        AssistantDisplayTextResolver.extractPlainTextFromStructuredText(
          raw,
        ).trim();
    if (markdown.isEmpty && plainText.isEmpty) return null;
    final effectiveMarkdown = markdown.isNotEmpty ? markdown : plainText;
    return AssistantDisplayProjection(markdown: effectiveMarkdown);
  }

  static AssistantDisplayProjection? _projectFromAssistantTurnMap(
    Map<String, dynamic> payload,
  ) {
    if (payload.isEmpty) return null;
    final turn = tryParseAssistantTurnOutput(payload);
    if (turn == null) return null;
    final projection = AssistantDisplayTextResolver.projectTurn(
      AssistantDisplayTextResolver.normalizeTurn(turn),
    );
    if (!projection.hasRenderableContent) return null;
    return projection;
  }
}
