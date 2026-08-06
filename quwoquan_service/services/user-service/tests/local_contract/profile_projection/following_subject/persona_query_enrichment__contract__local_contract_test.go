// readiness_case: list-following-subjects-local
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
package local_contract

import (
	"context"
	"testing"
	"time"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
)

type canonicalFollowingSubjectReader struct{}

func (canonicalFollowingSubjectReader) List(
	context.Context,
	string,
	string,
	int,
) ([]followingapp.Row, error) {
	return []followingapp.Row{{
		ViewerPersonaID: "persona-viewer",
		SubjectType:     "persona",
		SubjectID:       "persona-target",
		FollowedAt:      time.Unix(1, 0).UTC(),
	}}, nil
}

type canonicalPersonaDisplayReader struct{}

func (canonicalPersonaDisplayReader) FindByPersonaID(
	context.Context,
	string,
) (*usermodel.Persona, error) {
	return &usermodel.Persona{
		PersonaID:   "persona-target",
		DisplayName: "Canonical Persona",
		AvatarURL:   "https://media.example/avatar.png",
	}, nil
}

func TestPersonaFollowingSubjectRetainsRouteAndDisplayEnrichment(t *testing.T) {
	t.Parallel()

	service := followingapp.NewQueryService(
		canonicalFollowingSubjectReader{},
		canonicalPersonaDisplayReader{},
		nil,
	)
	items, err := service.ListFollowingSubjects(
		context.Background(),
		"persona-viewer",
		"persona",
		20,
	)
	if err != nil {
		t.Fatalf("ListFollowingSubjects: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("items len = %d, want 1", len(items))
	}
	item := items[0]
	if item.TargetRouteID != "user_profile" ||
		item.DisplayName != "Canonical Persona" ||
		item.AvatarURL != "https://media.example/avatar.png" {
		t.Fatalf("persona query lost canonical route/enrichment: %+v", item)
	}
}
