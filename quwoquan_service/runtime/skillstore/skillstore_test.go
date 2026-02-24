package skillstore

import (
	"testing"
)

func TestValidTransitions(t *testing.T) {
	cases := []struct {
		from, to SkillStatus
		want     bool
	}{
		{StatusDraft, StatusReview, true},
		{StatusDraft, StatusPublished, false},
		{StatusReview, StatusApproved, true},
		{StatusReview, StatusRejected, true},
		{StatusReview, StatusPublished, false},
		{StatusApproved, StatusGray, true},
		{StatusApproved, StatusPublished, true},
		{StatusGray, StatusPublished, true},
		{StatusGray, StatusArchived, true},
		{StatusGray, StatusDraft, false},
		{StatusPublished, StatusArchived, true},
		{StatusPublished, StatusGray, true},
		{StatusPublished, StatusDraft, false},
		{StatusArchived, StatusDraft, true},
		{StatusArchived, StatusPublished, false},
		{StatusRejected, StatusDraft, true},
		{StatusRejected, StatusPublished, false},
	}

	for _, c := range cases {
		got := isValidTransition(c.from, c.to)
		if got != c.want {
			t.Errorf("isValidTransition(%s→%s)=%v, want %v", c.from, c.to, got, c.want)
		}
	}
}

func TestAutoChecks_InternalPass(t *testing.T) {
	s := &Store{}
	reg := &SkillRegistration{
		Provider: "internal",
		Manifest: SkillManifestRef{
			ContextRequirements: []string{"page", "session"},
			ToolDependencies:    []string{"content.search"},
			DataClassMax:        "SENSITIVE",
		},
	}

	checks := s.runAutoChecks(reg)
	if len(checks) != 3 {
		t.Fatalf("expected 3 checks, got %d", len(checks))
	}
	for _, c := range checks {
		if !c.Passed {
			t.Errorf("check %q should pass for internal, got passed=%v", c.Name, c.Passed)
		}
	}
}

func TestAutoChecks_EcosystemSensitiveFails(t *testing.T) {
	s := &Store{}
	reg := &SkillRegistration{
		Provider: "ecosystem",
		Manifest: SkillManifestRef{
			ContextRequirements: []string{"page"},
			ToolDependencies:    []string{"content.search"},
			DataClassMax:        "SENSITIVE",
		},
	}

	checks := s.runAutoChecks(reg)
	dataClassCheck := checks[2]
	if dataClassCheck.Passed {
		t.Error("ecosystem skill with SENSITIVE data class should fail data_class_policy check")
	}
}

func TestAutoChecks_ExcessiveContextFails(t *testing.T) {
	s := &Store{}
	reg := &SkillRegistration{
		Provider: "ecosystem",
		Manifest: SkillManifestRef{
			ContextRequirements: []string{"page", "session", "profile", "raw_data"},
			ToolDependencies:    []string{"t1"},
			DataClassMax:        "PUBLIC",
		},
	}

	checks := s.runAutoChecks(reg)
	if checks[0].Passed {
		t.Error("4 context requirements should fail context_scope_reasonable check")
	}
}

func TestSkillMetricsZeroValue(t *testing.T) {
	var m SkillMetrics
	if m.TotalCalls != 0 || m.SuccessRate != 0 || m.UserRating != 0 {
		t.Error("zero value metrics should be all zeros")
	}
}

func TestSandboxConfigDefaults(t *testing.T) {
	cfg := SandboxConfig{
		MaxMemoryMB:    256,
		MaxCPUPercent:  50,
		TimeoutSeconds: 30,
		AllowedAPIs:    []string{"content.search", "location.nearby"},
		NetworkPolicy:  NetworkInternal,
	}
	if cfg.MaxMemoryMB != 256 {
		t.Errorf("expected 256, got %d", cfg.MaxMemoryMB)
	}
	if cfg.NetworkPolicy != NetworkInternal {
		t.Errorf("expected internal, got %s", cfg.NetworkPolicy)
	}
}
