package domain_test

import (
	"testing"

	intersectionmodel "quwoquan_service/services/content-service/internal/content/intersection_visit_state/domain/model"
)

func TestIntersectionVisitStateAcceptsOnlyCanonicalPositiveWatermarks(t *testing.T) {
	state := intersectionmodel.State{
		PersonaID: "persona-intersection",
		Watermarks: map[string]int64{
			"identity":     100,
			"relationship": 200,
		},
	}
	if err := state.Validate(); err != nil {
		t.Fatalf("valid IntersectionVisitState rejected: %v", err)
	}
	state.Watermarks["legacy_dimension"] = 300
	if err := state.Validate(); err == nil {
		t.Fatal("non-canonical intersection dimension must be rejected")
	}
}
