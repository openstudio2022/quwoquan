package http

import (
	"testing"

	operationsecurity "quwoquan_service/generated/operationsecurity"
)

func TestContentReadOperationsRemainCommerciallyReady(t *testing.T) {
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

	for operationID, want := range map[string]string{
		"content.post.GetAppConfig":                             "public",
		"content.post.GetFeed":                                  "optional",
		"content.post.ListProfileInteractionActivitiesReceived": "required",
		"content.post.ListProfileInteractionActivitiesSent":     "required",
	} {
		descriptor, ok := descriptors[operationID]
		if !ok {
			t.Fatalf("generated operation descriptor missing %q", operationID)
		}
		if descriptor.authMode != want {
			t.Fatalf("%s auth mode = %q, want %q", operationID, descriptor.authMode, want)
		}
		if descriptor.commercialStatus != "ready" {
			t.Fatalf("%s commercial status = %q, want ready", operationID, descriptor.commercialStatus)
		}
		if descriptor.timeoutMillis <= 0 {
			t.Fatalf("%s timeout must be generated from metadata, got %d", operationID, descriptor.timeoutMillis)
		}
	}
}
