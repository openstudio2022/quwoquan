package orchestration

import (
	"context"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/streaming"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// DurableRunExecutor adapts the production AgentLoop to the canonical
// AssistantRun worker. The execution-shaped AssistantTurn below is ephemeral:
// it is never written as an aggregate and its internal execution ID is not
// the public Run ID. All durable output is projected into typed RunItems by the
// worker callback.
type DurableRunExecutor struct {
	loop *AgentLoop
}

func NewDurableRunExecutor(loop *AgentLoop) *DurableRunExecutor {
	if loop == nil {
		panic("assistant agent loop is required")
	}
	return &DurableRunExecutor{loop: loop}
}

// VerifiesCompletionWithinExecutionBudget marks the production executor as
// the path that invokes completion verification before its request-scoped
// policy and durable usage ledger leave scope.
func (*DurableRunExecutor) VerifiesCompletionWithinExecutionBudget() bool {
	return true
}

func (e *DurableRunExecutor) Execute(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	emit func(runruntime.ExecutionItemUpdate) error,
) (runruntime.ExecutionResult, error) {
	if e == nil || e.loop == nil || strings.TrimSpace(request.RunID) == "" ||
		strings.TrimSpace(request.Goal) == "" ||
		strings.TrimSpace(request.SkillPackageID) == "" ||
		strings.TrimSpace(request.SkillPackageReleaseDigest) == "" ||
		emit == nil {
		return runruntime.ExecutionResult{}, runruntime.ErrInvalidRun
	}
	var err error
	ctx, err = e.loop.WithDurableReasoningProfile(ctx, request.ReasoningPolicy)
	if err != nil {
		return runruntime.ExecutionResult{}, err
	}
	ctx = withExecutionBudgetConsumption(
		ctx,
		ExecutionBudgetConsumption{
			ToolCalls: request.BudgetConsumption.ToolCalls,
			Tokens:    request.BudgetConsumption.Tokens,
			CostUnits: request.BudgetConsumption.CostUnits,
		},
		request.BudgetReceiptSequence,
		func(snapshot executionBudgetConsumptionSnapshot) error {
			return emit(runruntime.ExecutionItemUpdate{
				Budget: &runruntime.BudgetConsumptionReceipt{
					Scope:    request.IdempotencyPrefix,
					Sequence: snapshot.Sequence,
					Consumption: runruntime.BudgetConsumption{
						ToolCalls: snapshot.Consumption.ToolCalls,
						Tokens:    snapshot.Consumption.Tokens,
						CostUnits: snapshot.Consumption.CostUnits,
					},
				},
			})
		},
	)
	ctx = skillpkg.WithPackageRelease(ctx, skillpkg.PackageReleaseIdentity{
		PackageID:     request.SkillPackageID,
		ReleaseDigest: request.SkillPackageReleaseDigest,
	})
	if receipt, completed := executionCompletedDeviceAction(request.Checkpoint); completed {
		answer := "设备操作已完成。"
		if provider, ok := e.loop.React.Tools.(ToolMetadataProvider); ok {
			if metadata, found := provider.ToolMetadata(receipt.Capability); found &&
				strings.TrimSpace(metadata.Confirmation.CompletionSummary) != "" {
				answer = strings.TrimSpace(metadata.Confirmation.CompletionSummary)
			}
		}
		prepared, err := e.prepareDeviceCompletionPresentation(ctx, request)
		if err != nil {
			return runruntime.ExecutionResult{}, err
		}
		var presentation map[string]any
		if prepared.SkillID != "" {
			presentation, err = e.buildExecutionPresentation(
				ctx, request, prepared, answer, nil,
			)
			if err != nil {
				return runruntime.ExecutionResult{}, err
			}
		}
		artifactRefs := []string{
			executionAnswerArtifactRef(request.RunID),
			"device_action_receipt:" + strings.TrimSpace(receipt.IdempotencyKey),
		}
		result := runruntime.ExecutionResult{
			AnswerText:   answer,
			ArtifactRefs: artifactRefs,
			VerificationEvidence: verificationEvidenceForExecution(
				request.DefinitionOfDone,
				true,
				answer,
				nil,
				nil,
				artifactRefs,
			),
			Presentation: presentation,
		}
		return verifyDurableExecutionCompletion(ctx, request, result)
	}
	turn := executionTurn(request)
	answer := strings.Builder{}
	processes := make(map[string]assistant.AssistantRunVisibleProcess)
	processOrder := make([]string, 0)
	startedItems := make(map[string]bool)
	taskTracker := newExecutionTaskTracker(request)
	waitingState := generated.AssistantRunState("")
	waitReason := ""
	pendingApproval := map[string]any(nil)
	pendingApprovalRef := ""
	completed := false
	firstAnswerObserved := false
	var prepared *PreparedExecution
	_, failure, err := e.loop.RunTurnWithPreparedExecution(
		ctx,
		turn,
		func(envelope streaming.Envelope) error {
			switch envelope.EventType {
			case string(assistantstreaming.AssistantStreamEventAnswerDelta):
				if !firstAnswerObserved && !request.CreatedAt.IsZero() {
					firstAnswerObserved = true
					recordAssistantFirstVisibleResponse(
						time.Since(request.CreatedAt),
					)
				}
				if text, ok := envelope.Payload["text"].(string); ok {
					answer.WriteString(text)
				}
			case string(assistantstreaming.AssistantStreamEventCompleted):
				completed = true
				if !firstAnswerObserved && !request.CreatedAt.IsZero() {
					firstAnswerObserved = true
					recordAssistantFirstVisibleResponse(
						time.Since(request.CreatedAt),
					)
				}
				if finalAnswer, ok := envelope.Payload["finalAnswer"].(string); ok && strings.TrimSpace(finalAnswer) != "" {
					answer.Reset()
					answer.WriteString(finalAnswer)
				}
			case string(generated.AssistantStreamEventTypeWaitingInput):
				waitingState = generated.AssistantRunStateWaitingUser
				waitReason = executionString(envelope.Payload, "reason")
				if waitReason == "" {
					waitReason = "waiting_user_input"
				}
			case string(generated.AssistantStreamEventTypeWaitingApproval):
				waitingState = generated.AssistantRunStateWaitingApproval
				waitReason = executionString(envelope.Payload, "reason")
				pendingApproval = cloneObject(envelope.Payload)
				pendingApprovalRef = executionString(envelope.Payload, "toolUseId")
				if waitReason == "" {
					waitReason = "waiting_tool_approval"
				}
			}
			return projectExecutionProcesses(
				envelope,
				request,
				emit,
				processes,
				&processOrder,
				startedItems,
				taskTracker,
			)
		},
		func(value PreparedExecution) error {
			if prepared != nil {
				return fmt.Errorf("assistant execution prepared more than once")
			}
			prepared = &value
			return nil
		},
	)
	if err != nil {
		result := runruntime.ExecutionResult{}
		if prepared != nil {
			result.ConfirmedSlots = prepared.ConfirmedSlots.Clone()
		}
		return result, err
	}
	if failure != nil {
		return runruntime.ExecutionResult{}, &runruntime.ExecutionFailure{
			Code:   failure.Code,
			Origin: string(failure.Origin),
			Kind:   string(failure.Kind),
			Nature: string(failure.Nature),
		}
	}
	if prepared == nil {
		return runruntime.ExecutionResult{}, fmt.Errorf(
			"assistant execution completed without a frozen Skill/Context preparation",
		)
	}
	if waitingState == "" && !completed {
		waitingState = generated.AssistantRunStateWaitingUser
		waitReason = "waiting_user_input"
	}
	visibleProcesses := make([]assistant.AssistantRunVisibleProcess, 0, len(processOrder))
	for _, processID := range processOrder {
		visibleProcesses = append(visibleProcesses, processes[processID])
	}
	finalAnswer := strings.TrimSpace(answer.String())
	evidenceRefs := collectExecutionEvidenceRefs(visibleProcesses)
	artifactRefs := append([]string{}, evidenceRefs...)
	if completed && finalAnswer != "" {
		artifactRefs = append(
			artifactRefs,
			executionAnswerArtifactRef(request.RunID),
		)
	}
	verificationEvidence := verificationEvidenceForExecution(
		request.DefinitionOfDone,
		completed,
		finalAnswer,
		visibleProcesses,
		evidenceRefs,
		artifactRefs,
	)
	presentationDocument, presentationErr := e.buildExecutionPresentation(
		ctx,
		request,
		*prepared,
		finalAnswer,
		pendingApproval,
	)
	if presentationErr != nil {
		return runruntime.ExecutionResult{}, presentationErr
	}
	result := runruntime.ExecutionResult{
		AnswerText:           finalAnswer,
		Processes:            visibleProcesses,
		ArtifactRefs:         artifactRefs,
		EvidenceRefs:         evidenceRefs,
		VerificationEvidence: verificationEvidence,
		Presentation:         presentationDocument,
		WaitingState:         waitingState,
		WaitReason:           waitReason,
		PendingApprovalRef:   pendingApprovalRef,
		ConfirmedSlots:       prepared.ConfirmedSlots.Clone(),
	}
	return verifyDurableExecutionCompletion(ctx, request, result)
}

var _ runruntime.RunExecutor = (*DurableRunExecutor)(nil)
