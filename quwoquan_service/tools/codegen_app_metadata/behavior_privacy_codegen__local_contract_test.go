package main

import (
	"strings"
	"testing"
)

func TestOnboardingBehaviorStaysOffBestEffortGeneratedTracker(t *testing.T) {
	t.Parallel()

	generated := renderContentBehaviorsDart(&behaviorsFile{
		BehaviorEvents: []behaviorEventDef{
			{
				Type:          "onboarding_interest",
				Batch:         true,
				BatchRoute:    "POST /content/behaviors",
				PayloadFields: []string{"taxonomyReleaseId", "tagRefs"},
			},
		},
	})

	if strings.Contains(generated, "trackOnboardingInterest") {
		t.Fatalf("confirmed onboarding behavior leaked into best-effort tracker:\n%s", generated)
	}
	// Retired catalogVersion must not be regenerated as a parameter or wire key.
	if strings.Contains(generated, "catalogVersion") {
		t.Fatalf("generated onboarding behavior retained retired identity:\n%s", generated)
	}
}

func TestContentBehaviorTrackerUsesCanonicalContentIdentity(t *testing.T) {
	t.Parallel()

	generated := renderContentBehaviorsDart(&behaviorsFile{
		BehaviorEvents: []behaviorEventDef{
			{
				Type:          "impression",
				DartMethod:    "trackImpression",
				Batch:         true,
				BatchRoute:    "POST /content/behaviors",
				PayloadFields: []string{"contentId", "state", "contentType"},
			},
		},
	})

	for _, marker := range []string{
		"trackImpression(String contentId, String state",
		"'contentId': contentId",
	} {
		if !strings.Contains(generated, marker) {
			t.Fatalf("generated behavior tracker missing %q:\n%s", marker, generated)
		}
	}
	if strings.Contains(generated, "String postId") ||
		strings.Contains(generated, "'postId': postId") {
		t.Fatalf("retired Post-specific identity leaked into behavior tracker:\n%s", generated)
	}
}
