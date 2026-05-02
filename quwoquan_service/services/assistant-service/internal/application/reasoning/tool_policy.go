package reasoning

import (
	"fmt"
	"strings"
)

type ToolExecutionGuard struct {
	AllowedTools map[string]bool
}

func (g ToolExecutionGuard) Allow(toolName string) error {
	toolName = strings.TrimSpace(toolName)
	if toolName == "" {
		return fmt.Errorf("tool name is required")
	}
	if len(g.AllowedTools) == 0 {
		return nil
	}
	if !g.AllowedTools[toolName] {
		return fmt.Errorf("tool %q is not allowed by policy", toolName)
	}
	return nil
}

type ToolResultAssessor struct{}

func (ToolResultAssessor) Assess(result map[string]any) Observation {
	if len(result) == 0 {
		return Observation{Empty: true}
	}
	summary, _ := result["summary"].(string)
	return Observation{Summary: summary}
}

type ToolResultTruncator struct {
	MaxSummaryRunes int
}

func (t ToolResultTruncator) Truncate(result map[string]any) map[string]any {
	if result == nil {
		return map[string]any{}
	}
	out := make(map[string]any, len(result))
	for key, value := range result {
		out[key] = value
	}
	max := t.MaxSummaryRunes
	if max <= 0 {
		max = 240
	}
	if summary, ok := out["summary"].(string); ok {
		runes := []rune(summary)
		if len(runes) > max {
			out["summary"] = string(runes[:max])
		}
	}
	return out
}
