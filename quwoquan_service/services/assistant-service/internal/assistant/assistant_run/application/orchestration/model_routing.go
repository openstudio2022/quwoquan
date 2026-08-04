package orchestration

import (
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// ModelRoutingInput 是档位决策的全部输入。不接受 skillId、userId 或租户维度，避免把
// 模型选择变成第二套业务分支。
type ModelRoutingInput struct {
	Stage            ports.ModelStage
	ProblemClass     assistantgenerated.ProblemClass
	SearchIntensity  assistantgenerated.SearchIntensity
	ReasoningProfile assistantgenerated.AssistantReasoningProfile
}

// ResolveModelTier 按运行阶段与问题类型决定档位。同一输入必须得到同一档位，便于回放
// 与成本核算。
func ResolveModelTier(input ModelRoutingInput) ports.ModelTier {
	if input.Stage != ports.ModelStageSkillSelection {
		switch input.ReasoningProfile {
		case assistantgenerated.AssistantReasoningProfileFast:
			return ports.ModelTierFast
		case assistantgenerated.AssistantReasoningProfileDeep,
			assistantgenerated.AssistantReasoningProfileBackgroundLong:
			return ports.ModelTierReasoning
		}
	}
	switch input.Stage {
	case ports.ModelStageSkillSelection:
		// 技能选择是受 manifest 约束的单选分类，最快档位即可。
		return ports.ModelTierFast
	case ports.ModelStagePresentation:
		// Presentation 只在服务端给出的有限候选中选择，不承担事实推理。
		return ports.ModelTierFast
	case ports.ModelStageOrchestration:
		// 拆分子任务要看懂问题里有几件事，用与推理同源的档位判断。
		if requiresReasoningTier(input.ProblemClass) {
			return ports.ModelTierReasoning
		}
		return ports.ModelTierBalanced
	case ports.ModelStageEvidenceProcessing:
		if requiresReasoningTier(input.ProblemClass) {
			return ports.ModelTierReasoning
		}
		return ports.ModelTierBalanced
	case ports.ModelStageReasoning, ports.ModelStageFinal:
		if requiresReasoningTier(input.ProblemClass) ||
			input.SearchIntensity == assistantgenerated.SearchIntensityHigh {
			return ports.ModelTierReasoning
		}
		if input.ProblemClass == assistantgenerated.ProblemClassSimpleQa &&
			input.SearchIntensity == assistantgenerated.SearchIntensityLow {
			return ports.ModelTierFast
		}
		return ports.ModelTierBalanced
	default:
		return ports.ModelTierBalanced
	}
}

// ModelTierDegradeOrder 返回从当前档位向下的降级顺序，用于主档位不可用时继续本次运行。
// 只允许向下降级，避免故障时把成本推高。
func ModelTierDegradeOrder(tier ports.ModelTier) []ports.ModelTier {
	switch tier {
	case ports.ModelTierReasoning:
		return []ports.ModelTier{
			ports.ModelTierReasoning,
			ports.ModelTierBalanced,
			ports.ModelTierFast,
		}
	case ports.ModelTierBalanced:
		return []ports.ModelTier{ports.ModelTierBalanced, ports.ModelTierFast}
	case ports.ModelTierFast:
		return []ports.ModelTier{ports.ModelTierFast}
	default:
		return []ports.ModelTier{ports.ModelTierBalanced, ports.ModelTierFast}
	}
}

// requiresReasoningTier 只有多步推理与任务执行两类需要最强档位；实时信息与证据查证的
// 难点在检索而不在推理。
func requiresReasoningTier(problemClass assistantgenerated.ProblemClass) bool {
	switch problemClass {
	case assistantgenerated.ProblemClassComplexReasoning,
		assistantgenerated.ProblemClassTaskExecution:
		return true
	default:
		return false
	}
}
