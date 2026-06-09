package controlplane

import (
	"sort"
	"strings"
)

type BacklogCandidate struct {
	ID             string         `json:"id"`
	Category       string         `json:"category"`
	Severity       string         `json:"severity"`
	Title          string         `json:"title"`
	Summary        string         `json:"summary"`
	Owner          string         `json:"owner"`
	NextAction     string         `json:"nextAction"`
	DrilldownRoute string         `json:"drilldownRoute,omitempty"`
	RunbookID      string         `json:"runbookId,omitempty"`
	RunbookRoute   string         `json:"runbookRoute,omitempty"`
	RepairEntry    string         `json:"repairEntry,omitempty"`
	AlertID        string         `json:"alertId,omitempty"`
	AuditRoute     string         `json:"auditRoute,omitempty"`
	Evidence       map[string]any `json:"evidence,omitempty"`
}

func SortBacklogCandidates(items []BacklogCandidate) []BacklogCandidate {
	out := append([]BacklogCandidate(nil), items...)
	sort.Slice(out, func(i, j int) bool {
		iRank := backlogSeverityRank(out[i].Severity)
		jRank := backlogSeverityRank(out[j].Severity)
		if iRank == jRank {
			if out[i].Category == out[j].Category {
				return out[i].ID < out[j].ID
			}
			return out[i].Category < out[j].Category
		}
		return iRank > jRank
	})
	return out
}

func LimitBacklogCandidates(items []BacklogCandidate, limit int) []BacklogCandidate {
	if limit <= 0 || len(items) <= limit {
		return append([]BacklogCandidate(nil), items...)
	}
	out := make([]BacklogCandidate, limit)
	copy(out, items[:limit])
	return out
}

func backlogSeverityRank(raw string) int {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "critical":
		return 4
	case "warning":
		return 3
	case "info":
		return 2
	case "low":
		return 1
	default:
		return 0
	}
}
