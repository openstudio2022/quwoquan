package skill

import "fmt"

type ExecutionProposal struct {
	SkillID string         `json:"skillId"`
	Target  string         `json:"target"`
	Action  string         `json:"action"`
	Payload map[string]any `json:"payload,omitempty"`
}

type Executor struct{}

func (Executor) BuildProposal(manifest Manifest, input map[string]any) (ExecutionProposal, error) {
	switch manifest.ExecutionTarget {
	case "", "cloud", "tool_chain", "knowledge_qa":
		return ExecutionProposal{SkillID: manifest.SkillID, Target: "cloud", Action: "execute", Payload: input}, nil
	case "device_action", "hybrid":
		return ExecutionProposal{SkillID: manifest.SkillID, Target: manifest.ExecutionTarget, Action: "proposal", Payload: input}, nil
	default:
		return ExecutionProposal{}, fmt.Errorf("unsupported skill execution target %q", manifest.ExecutionTarget)
	}
}
