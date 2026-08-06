package runruntime

import generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"

var allowedTransitions = map[generated.AssistantRunState]map[generated.AssistantRunState]bool{
	generated.AssistantRunStateAccepted: states(
		generated.AssistantRunStateOrienting,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateOrienting: states(
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStatePlanning: states(
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateExecuting: states(
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal,
		generated.AssistantRunStateCheckpointing,
	),
	generated.AssistantRunStateObserving: states(
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateReflecting: states(
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStateSynthesizing,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateCheckpointing: states(
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateSynthesizing,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateWaitingUser: states(
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateWaitingApproval: states(
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateWaitingExternal,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStateWaitingExternal: states(
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStatePaused,
	),
	generated.AssistantRunStatePaused: states(
		generated.AssistantRunStateOrienting,
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal,
	),
	generated.AssistantRunStateSynthesizing: states(
		generated.AssistantRunStateVerifying,
		generated.AssistantRunStateCheckpointing,
	),
	generated.AssistantRunStateVerifying: states(
		generated.AssistantRunStateCompleted,
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStateWaitingUser,
	),
}

func states(values ...generated.AssistantRunState) map[generated.AssistantRunState]bool {
	result := make(map[generated.AssistantRunState]bool, len(values)+2)
	for _, value := range values {
		result[value] = true
	}
	result[generated.AssistantRunStateFailed] = true
	result[generated.AssistantRunStateCancelled] = true
	return result
}

func terminalState(state generated.AssistantRunState) bool {
	return state == generated.AssistantRunStateCompleted ||
		state == generated.AssistantRunStateFailed ||
		state == generated.AssistantRunStateCancelled
}

func safeBoundary(state generated.AssistantRunState) bool {
	switch state {
	case generated.AssistantRunStateAccepted,
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateObserving,
		generated.AssistantRunStateReflecting,
		generated.AssistantRunStateCheckpointing,
		generated.AssistantRunStateWaitingUser,
		generated.AssistantRunStateWaitingApproval,
		generated.AssistantRunStateWaitingExternal:
		return true
	default:
		return false
	}
}
