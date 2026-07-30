package main

import (
	"strings"
	"testing"
)

func TestContentErrorGenerationIncludesObjectOwnedProfileInteractionErrors(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	errorsDefinition, err := readMergedErrors(contentDomainErrorsPaths(metadataDir))
	if err != nil {
		t.Fatalf("read Content errors: %v", err)
	}

	output := renderContentErrorsDart(errorsDefinition)
	for _, expected := range []string{
		"CONTENT.USER.interaction_type_invalid",
		"CONTENT.USER.interaction_cursor_invalid",
		"CONTENT.USER.interaction_owner_forbidden",
		"CONTENT.SYSTEM.interaction_read_model_unavailable",
		"CONTENT.USER.profile_interaction_read_fact_owner_forbidden",
		"CONTENT.SYSTEM.profile_interaction_read_fact_target_unavailable",
	} {
		if !strings.Contains(output, expected) {
			t.Fatalf("Content error output missing object-owned code %q", expected)
		}
	}
	for _, retired := range []string{
		"CONTENT.USER.assistant_mention_context_missing",
		"CONTENT.USER.circle_distribution_forbidden",
		"CONTENT.USER.invalid_moment_payload",
		"CONTENT.USER.post_immutable_after_publish",
		"CONTENT.USER.public_required_for_circle_distribution",
	} {
		if strings.Contains(output, retired) {
			t.Fatalf("Content error output resurrected dead Post error %q", retired)
		}
	}
}
