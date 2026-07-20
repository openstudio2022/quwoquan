package http

import (
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
)

func TestContentReadOperationsExposeTruthfulCommercialStatus(t *testing.T) {
	t.Parallel()

	descriptors := map[string]struct {
		authMode         string
		commercialStatus string
		timeoutMillis    int
	}{}
	for _, descriptor := range operationsecurity.ForDomain("content") {
		descriptors[descriptor.CanonicalOperationID] = struct {
			authMode         string
			commercialStatus string
			timeoutMillis    int
		}{
			authMode:         descriptor.AuthMode,
			commercialStatus: descriptor.CommercialStatus,
			timeoutMillis:    descriptor.TimeoutMilliseconds,
		}
	}

	for operationID, want := range map[string]struct {
		authMode         string
		commercialStatus string
	}{
		"content.post.GetAppConfig": {
			authMode:         "public",
			commercialStatus: "ready",
		},
		"content.post.GetFeed": {
			authMode:         "optional",
			commercialStatus: "ready",
		},
		"content.profile_interaction_activity_view.ListProfileInteractionActivitiesReceived": {
			authMode:         "required",
			commercialStatus: "blocked",
		},
		"content.profile_interaction_activity_view.ListProfileInteractionActivitiesSent": {
			authMode:         "required",
			commercialStatus: "blocked",
		},
	} {
		descriptor, ok := descriptors[operationID]
		if !ok {
			t.Fatalf("generated operation descriptor missing %q", operationID)
		}
		if descriptor.authMode != want.authMode {
			t.Fatalf("%s auth mode = %q, want %q", operationID, descriptor.authMode, want.authMode)
		}
		if descriptor.commercialStatus != want.commercialStatus {
			t.Fatalf(
				"%s commercial status = %q, want %q",
				operationID,
				descriptor.commercialStatus,
				want.commercialStatus,
			)
		}
		if descriptor.timeoutMillis <= 0 {
			t.Fatalf("%s timeout must be generated from metadata, got %d", operationID, descriptor.timeoutMillis)
		}
	}
}
