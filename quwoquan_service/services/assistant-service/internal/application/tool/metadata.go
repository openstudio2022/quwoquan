package tool

const (
	PlacementCloud         = "cloud"
	PlacementDeviceContext = "device_context"
	PlacementDeviceAction  = "device_action"
	PlacementHybrid        = "hybrid"
)

type Metadata struct {
	ToolName             string           `json:"toolName"`
	DisplayName          string           `json:"displayName,omitempty"`
	Description          string           `json:"description,omitempty"`
	Placement            string           `json:"placement"`
	RequiredInputKeys    []string         `json:"requiredInputKeys,omitempty"`
	RequiredOutputKeys   []string         `json:"requiredOutputKeys,omitempty"`
	RequiresConfirmation bool             `json:"requiresConfirmation"`
	Resilience           ResiliencePolicy `json:"resilience"`
	Recovery             RecoveryPolicy   `json:"recovery"`
}

type ResiliencePolicy struct {
	TimeoutMs           int `json:"timeoutMs"`
	MaxAttempts         int `json:"maxAttempts"`
	RetryBackoffMs      int `json:"retryBackoffMs"`
	LoopDetectionWindow int `json:"loopDetectionWindow"`
}

type RecoveryPolicy struct {
	Action             string `json:"action"`
	DisruptionLevel    string `json:"disruptionLevel"`
	UserVisibleSummary string `json:"userVisibleSummary,omitempty"`
}

func DefaultMetadata(toolName string) Metadata {
	return Metadata{
		ToolName:             toolName,
		DisplayName:          toolName,
		Placement:            PlacementCloud,
		RequiredInputKeys:    []string{"query"},
		RequiredOutputKeys:   []string{"summary"},
		RequiresConfirmation: false,
		Resilience: ResiliencePolicy{
			TimeoutMs:           5000,
			MaxAttempts:         1,
			RetryBackoffMs:      0,
			LoopDetectionWindow: 3,
		},
		Recovery: RecoveryPolicy{
			Action:          "fail_turn",
			DisruptionLevel: "partial",
		},
	}
}
