package recommendation

import (
	"strings"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

// applyOpsInterventions applies manual operational interventions (pin/demote/block)
// to the score-sorted candidate list. It is the single runtime consumer of
// recpolicy.OpsInterventionConfig (the config truth source) and the only place
// that mutates ranking for运营 governance.
//
// Semantics (priority block > pin > demote when a candidate matches multiple):
//   - block:  candidate removed from the feed entirely.
//   - pin:    candidate force-moved to the top (config order), with an optional
//     score boost recorded for transparency.
//   - demote: candidate score scaled by Weight ∈ [0,1), keeping it in place but
//     pushed down by the subsequent ordering.
//
// scenario scopes a rule to one feed surface ("" = all). Expired rules (ExpiresAt
// in the past) are ignored. Every applied rule is audited via
// RecordOpsInterventionApplied. Empty / disabled config returns the input intact.
func applyOpsInterventions(scored []ScoredCandidate, cfg recpolicy.OpsInterventionConfig, scenario string, now time.Time) []ScoredCandidate {
	if !cfg.Enabled || len(cfg.Interventions) == 0 || len(scored) == 0 {
		return scored
	}

	active := activeInterventions(cfg.Interventions, scenario, now)
	if len(active) == 0 {
		return scored
	}

	pinned := make([]ScoredCandidate, 0, len(scored))
	kept := make([]ScoredCandidate, 0, len(scored))
	for _, sc := range scored {
		iv, matched := resolveIntervention(active, sc.Candidate)
		if !matched {
			kept = append(kept, sc)
			continue
		}
		RecordOpsInterventionApplied(iv.Action, iv.TargetType)
		switch iv.Action {
		case recpolicy.OpsActionBlock:
			// removed from feed
		case recpolicy.OpsActionPin:
			sc.Score += iv.Weight
			pinned = append(pinned, sc)
		case recpolicy.OpsActionDemote:
			sc.Score *= iv.Weight
			kept = append(kept, sc)
		default:
			kept = append(kept, sc)
		}
	}
	if len(pinned) == 0 {
		return kept
	}
	// Pins lead in config priority order; the rest preserve their incoming
	// (score-sorted) order. Caller re-sorts only the non-pinned tail downstream.
	return append(pinned, kept...)
}

// activeInterventions filters to rules in scope for the scenario and not expired,
// preserving config order (which defines pin priority).
func activeInterventions(rules []recpolicy.OpsIntervention, scenario string, now time.Time) []recpolicy.OpsIntervention {
	out := make([]recpolicy.OpsIntervention, 0, len(rules))
	for _, iv := range rules {
		if iv.Scenario != "" && iv.Scenario != scenario {
			continue
		}
		if exp := strings.TrimSpace(iv.ExpiresAt); exp != "" {
			if t, err := time.Parse(time.RFC3339, exp); err == nil && !now.Before(t) {
				continue
			}
		}
		out = append(out, iv)
	}
	return out
}

// resolveIntervention returns the highest-priority rule matching the candidate
// (block > pin > demote), or matched=false when none apply.
func resolveIntervention(rules []recpolicy.OpsIntervention, c ContentCandidate) (recpolicy.OpsIntervention, bool) {
	var best recpolicy.OpsIntervention
	bestRank := -1
	for _, iv := range rules {
		if !interventionMatchesCandidate(iv, c) {
			continue
		}
		if r := opsActionRank(iv.Action); r > bestRank {
			best = iv
			bestRank = r
		}
	}
	return best, bestRank >= 0
}

func interventionMatchesCandidate(iv recpolicy.OpsIntervention, c ContentCandidate) bool {
	switch iv.TargetType {
	case recpolicy.OpsTargetContent:
		return iv.Target == c.ContentID
	case recpolicy.OpsTargetAuthor:
		return iv.Target == c.AuthorID
	case recpolicy.OpsTargetTag:
		for _, tag := range c.Tags {
			if tag == iv.Target {
				return true
			}
		}
	}
	return false
}

// opsActionRank encodes the conflict-resolution priority: block > pin > demote.
func opsActionRank(action string) int {
	switch action {
	case recpolicy.OpsActionBlock:
		return 3
	case recpolicy.OpsActionPin:
		return 2
	case recpolicy.OpsActionDemote:
		return 1
	default:
		return 0
	}
}
