package local_contract

import (
	"context"
	rt "quwoquan_service/runtime/search"
	app "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	"strings"
	"testing"
)

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t6
type creatorSearchSource struct {
	snapshot *rt.CreatorSearchCandidateSnapshot
}

func (s creatorSearchSource) Read(context.Context, rt.ReleaseCandidateBinding) (*rt.CreatorSearchCandidateSnapshot, error) {
	return s.snapshot, nil
}

type creatorSearchPersona struct{ collision bool }

func (p creatorSearchPersona) FindByPersonaID(context.Context, string) (*model.Persona, error) {
	if p.collision {
		return &model.Persona{}, nil
	}
	return nil, nil
}
func (p creatorSearchPersona) FindByUserHandle(context.Context, string) (*model.Persona, error) {
	return nil, nil
}

type creatorSearchAccount struct{}

func (creatorSearchAccount) FindByID(context.Context, string) (*model.UserProfile, error) {
	return nil, nil
}
func TestCreatorPublicOwnerDelegatesWithoutLoginAccount(t *testing.T) {
	d := "sha256:" + strings.Repeat("a", 64)
	release := rt.ReleaseCandidateBinding{"gamma", "qwq_data", "candidate", d}
	s := &rt.CreatorSearchCandidateSnapshot{Release: release, SourceClosureDigest: d, Profiles: []rt.CreatorSearchPublicSnapshot{{ObjectType: "user.profile", ObjectID: "builtin", PersonaID: "builtin", CreatorID: "creator", AuthorID: "author", UserHandle: "builtin", DisplayName: "作者", IdentityTags: []string{}, SourceVersion: 1, ProfileDigest: d, UpdatedAt: "2026-09-12T00:00:00Z"}}}
	_ = s.Seal()
	f := app.NewCreatorSearchCandidateQueryFacade(creatorSearchSource{s}, creatorSearchPersona{}, creatorSearchAccount{}, "gamma")
	result, err := f.Read(t.Context(), release)
	if err != nil || !result.Found || result.Snapshot.Profiles[0].ObjectID != "builtin" {
		t.Fatal(result, err)
	}
	f = app.NewCreatorSearchCandidateQueryFacade(creatorSearchSource{s}, creatorSearchPersona{true}, creatorSearchAccount{}, "gamma")
	if _, err = f.Read(t.Context(), release); err == nil {
		t.Fatal("Persona collision accepted")
	}
	release.Environment = "beta"
	if _, err = f.Read(t.Context(), release); err == nil {
		t.Fatal("wrong target environment accepted")
	}
}
