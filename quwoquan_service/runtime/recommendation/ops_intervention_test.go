package recommendation

import (
	"testing"
	"time"

	"quwoquan_service/runtime/recpolicy"
)

func opsScored() []ScoredCandidate {
	return []ScoredCandidate{
		{Candidate: ContentCandidate{ContentID: "a", AuthorID: "auth1", Tags: []string{"Topic/旅行"}}, Score: 10},
		{Candidate: ContentCandidate{ContentID: "b", AuthorID: "auth2", Tags: []string{"Topic/美食"}}, Score: 8},
		{Candidate: ContentCandidate{ContentID: "c", AuthorID: "auth1", Tags: []string{"Topic/旅行"}}, Score: 6},
	}
}

func ids(scored []ScoredCandidate) []string {
	out := make([]string, len(scored))
	for i, s := range scored {
		out[i] = s.Candidate.ContentID
	}
	return out
}

func TestApplyOpsInterventions_DisabledNoop(t *testing.T) {
	in := opsScored()
	out := applyOpsInterventions(in, recpolicy.OpsInterventionConfig{Enabled: false, Interventions: []recpolicy.OpsIntervention{
		{ID: "x", Action: "block", TargetType: "content", Target: "a"},
	}}, "homepage", time.Now())
	if len(out) != 3 {
		t.Fatalf("disabled config must be no-op, got %v", ids(out))
	}
}

func TestApplyOpsInterventions_BlockRemovesContent(t *testing.T) {
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "blk", Action: "block", TargetType: "content", Target: "b"},
	}}, "homepage", time.Now())
	got := ids(out)
	if len(got) != 2 || got[0] != "a" || got[1] != "c" {
		t.Fatalf("block should remove b, got %v", got)
	}
}

func TestApplyOpsInterventions_BlockAuthorRemovesAll(t *testing.T) {
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "blkA", Action: "block", TargetType: "author", Target: "auth1"},
	}}, "homepage", time.Now())
	got := ids(out)
	if len(got) != 1 || got[0] != "b" {
		t.Fatalf("block author auth1 should leave only b, got %v", got)
	}
}

func TestApplyOpsInterventions_DemoteScalesScore(t *testing.T) {
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "dem", Action: "demote", TargetType: "content", Target: "a", Weight: 0.1},
	}}, "homepage", time.Now())
	var a *ScoredCandidate
	for i := range out {
		if out[i].Candidate.ContentID == "a" {
			a = &out[i]
		}
	}
	if a == nil || a.Score != 1.0 {
		t.Fatalf("demote should scale a's score 10*0.1=1.0, got %+v", a)
	}
}

func TestApplyOpsInterventions_PinForcesTop(t *testing.T) {
	// Pin the lowest-scored c via its tag; it must lead the result.
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "pin", Action: "pin", TargetType: "content", Target: "c", Weight: 5},
	}}, "homepage", time.Now())
	got := ids(out)
	if got[0] != "c" {
		t.Fatalf("pinned c must lead, got %v", got)
	}
}

func TestApplyOpsInterventions_ScenarioScoping(t *testing.T) {
	// Rule scoped to circle must not affect a homepage request.
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "blk", Action: "block", TargetType: "content", Target: "a", Scenario: "circle"},
	}}, "homepage", time.Now())
	if len(out) != 3 {
		t.Fatalf("circle-scoped rule must not apply to homepage, got %v", ids(out))
	}
}

func TestApplyOpsInterventions_ExpiredIgnored(t *testing.T) {
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "blk", Action: "block", TargetType: "content", Target: "a", ExpiresAt: "2000-01-01T00:00:00Z"},
	}}, "homepage", time.Now())
	if len(out) != 3 {
		t.Fatalf("expired rule must be ignored, got %v", ids(out))
	}
}

func TestApplyOpsInterventions_BlockBeatsPin(t *testing.T) {
	// Candidate a matches both pin (by tag) and block (by content): block wins.
	out := applyOpsInterventions(opsScored(), recpolicy.OpsInterventionConfig{Enabled: true, Interventions: []recpolicy.OpsIntervention{
		{ID: "pinTag", Action: "pin", TargetType: "tag", Target: "Topic/旅行", Weight: 5},
		{ID: "blkA", Action: "block", TargetType: "content", Target: "a"},
	}}, "homepage", time.Now())
	for _, id := range ids(out) {
		if id == "a" {
			t.Fatalf("block must beat pin for a, got %v", ids(out))
		}
	}
}
