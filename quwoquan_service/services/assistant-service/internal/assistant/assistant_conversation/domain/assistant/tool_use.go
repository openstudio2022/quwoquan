package assistant

import (
	"time"

	rtfailures "quwoquan_service/runtime/failures"
)

type ToolUse struct {
	ToolUseID            string              `json:"toolUseId"`
	TurnID               string              `json:"turnId"`
	ToolName             string              `json:"toolName"`
	Placement            string              `json:"placement"`
	Input                map[string]any      `json:"input"`
	Status               string              `json:"status"`
	RequiresConfirmation bool                `json:"requiresConfirmation"`
	Result               map[string]any      `json:"result"`
	Failure              *rtfailures.Failure `json:"failure,omitempty"`
	CreatedAt            time.Time           `json:"createdAt"`
	CompletedAt          *time.Time          `json:"completedAt,omitempty"`
}
