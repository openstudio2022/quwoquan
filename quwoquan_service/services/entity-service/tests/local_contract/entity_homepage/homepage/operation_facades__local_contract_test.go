// spec_ref: specs/feature-tree/object-homepage-network/spec.md#dom-002
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
// readiness_case: search-homepages-local
// readiness_case: list-homepage-candidates-local
// readiness_case: intake-homepage-candidate-local
// readiness_case: suggest-homepage-candidate-local
// readiness_case: publish-homepage-candidate-local
// readiness_case: get-homepage-detail-local
// readiness_case: get-homepage-shell-local
// readiness_case: get-homepage-introduction-local
// readiness_case: get-object-page-bundle-local
// readiness_case: get-entity-impact-local
// readiness_case: get-homepage-review-summary-local
// readiness_case: get-homepage-related-groups-local
// readiness_case: update-claimed-homepage-basics-local
package local_contract

import (
	"context"
	"testing"

	"quwoquan_service/runtime/operation"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	testsupport "quwoquan_service/services/entity-service/tests/support/homepagefixture"
)

func TestHomepageOperationFacadesPreserveObjectLifecycleAndReadSlices(t *testing.T) {
	service, _ := testsupport.NewEmptyHomepageService()
	operator := homepageReadinessContext("intake", "operator-readiness")
	created, err := service.IntakeHomepageCandidate(operator, homepageapp.HomepageInput{
		Title: "readiness homepage", HomepageType: "sight", City: "Hangzhou",
	}, "owner_created")
	if err != nil {
		t.Fatalf("intake candidate: %v", err)
	}

	candidates, err := service.SearchHomepages(
		context.Background(), "readiness", "sight", "Hangzhou", "candidate", "", 20,
	)
	if err != nil || len(candidates.Items) != 1 || candidates.Items[0].HomepageID != created.ID {
		t.Fatalf("list candidate slice: %+v err=%v", candidates, err)
	}

	suggested, err := service.SuggestHomepageCandidate(
		homepageReadinessContext("suggest", "persona-suggester"),
		homepageapp.HomepageInput{Title: "suggested readiness homepage", HomepageType: "city"},
	)
	if err != nil || suggested.ID == "" || suggested.Status != "candidate" {
		t.Fatalf("suggest candidate: %+v err=%v", suggested, err)
	}

	published, err := service.PublishHomepageCandidate(
		homepageReadinessContext("publish", "operator-readiness"), created.ID,
	)
	if err != nil || published.Status != "published" {
		t.Fatalf("publish candidate: %+v err=%v", published, err)
	}

	detail, err := service.GetHomepage(context.Background(), created.ID)
	if err != nil || detail.ID != created.ID {
		t.Fatalf("get detail: %+v err=%v", detail, err)
	}
	shell, err := service.GetHomepageShell(context.Background(), created.ID)
	if err != nil || shell.Homepage.ID != created.ID || shell.ContentPreview == nil {
		t.Fatalf("get shell: %+v err=%v", shell, err)
	}
	introduction, err := service.GetHomepageIntroduction(context.Background(), created.ID)
	if err != nil || introduction.HomepageID != created.ID || introduction.Sections == nil {
		t.Fatalf("get introduction: %+v err=%v", introduction, err)
	}
	bundle, err := service.GetObjectPageBundle(
		context.Background(), "", created.ID, "readiness", "", "", "", "",
	)
	if err != nil || bundle.ObjectID != created.ID || bundle.HighlightItems == nil {
		t.Fatalf("get object page bundle: %+v err=%v", bundle, err)
	}
	impact, err := service.GetHomepageImpact(context.Background(), created.ID)
	if err != nil || impact.HomepageID != created.ID || impact.Items == nil {
		t.Fatalf("get impact: %+v err=%v", impact, err)
	}
	reviewSummary, err := service.GetHomepageReviewSummary(context.Background(), created.ID)
	if err != nil || reviewSummary.RatingCount != 0 || reviewSummary.HighlightTags == nil {
		t.Fatalf("get review summary: %+v err=%v", reviewSummary, err)
	}
	relatedGroups, err := service.GetHomepageRelatedGroups(context.Background(), created.ID)
	if err != nil || relatedGroups.Groups == nil {
		t.Fatalf("get related groups: %+v err=%v", relatedGroups, err)
	}

	if err := service.ApplyClaimReviewedProjection(
		homepageReadinessContext("claim", "projector"),
		"claim-reviewed-readiness", created.ID, "persona-owner", true,
	); err != nil {
		t.Fatalf("apply claim projection: %v", err)
	}
	updated, err := service.UpdateClaimedHomepageBasics(
		homepageReadinessContext("update", "persona-owner"),
		created.ID,
		homepageapp.HomepageBasicInput{Subtitle: "owner maintained"},
	)
	if err != nil || updated.Subtitle != "owner maintained" {
		t.Fatalf("update claimed basics: %+v err=%v", updated, err)
	}
}

func homepageReadinessContext(key, personaID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID:    "entity-homepage-readiness",
		RequestID:      "request-" + key,
		TraceID:        "trace-" + key,
		IdempotencyKey: "idempotency-" + key,
		Actor: operation.ActorContext{
			AccountID: personaID + "-account",
			PersonaID: personaID,
		},
	})
}
