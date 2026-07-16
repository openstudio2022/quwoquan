package main

import (
	"strings"
	"testing"
)

func TestEntityHomepageMutationWiresUseOwningObjectServices(t *testing.T) {
	rendered, err := renderEntityHomepageMutationWires(map[string]*serviceFile{
		"homepage": {
			APIRoutes: []routeDef{
				{Operation: "PublishHomepageCandidate"},
			},
		},
		"homepage_claim_request": {
			APIRoutes: []routeDef{
				{
					Operation:      "ReviewHomepageClaimRequest",
					WritableFields: []string{"status", "reviewNote"},
				},
			},
		},
		"homepage_status_report": {
			APIRoutes: []routeDef{
				{
					Operation:      "ReviewHomepageStatusReport",
					WritableFields: []string{"status", "reviewNote"},
				},
			},
		},
	})
	if err != nil {
		t.Fatalf("renderEntityHomepageMutationWires() error = %v", err)
	}
	for _, want := range []string{
		"ReviewHomepageClaimRequestWire({",
		"ReviewHomepageStatusReportWire({",
		"final String? status;",
		"final String? reviewNote;",
		"const PublishHomepageCandidateWire();",
	} {
		if !strings.Contains(rendered, want) {
			t.Errorf("rendered wires missing %q:\n%s", want, rendered)
		}
	}
}

func TestEntityHomepageMutationWiresRejectMissingOwningService(t *testing.T) {
	_, err := renderEntityHomepageMutationWires(map[string]*serviceFile{
		"homepage": {
			APIRoutes: []routeDef{
				{Operation: "PublishHomepageCandidate"},
			},
		},
	})
	if err == nil || !strings.Contains(err.Error(), "homepage_claim_request") {
		t.Fatalf("renderEntityHomepageMutationWires() error = %v, want missing owning service", err)
	}
}
