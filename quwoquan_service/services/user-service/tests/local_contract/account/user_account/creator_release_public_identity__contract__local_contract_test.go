package local_contract

import (
	"context"
	"strings"
	"testing"
	"time"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

type creatorPublicIdentityPersonaStore struct{}

func (creatorPublicIdentityPersonaStore) FindByID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}

func (creatorPublicIdentityPersonaStore) FindByUserID(context.Context, string) ([]usermodel.Persona, error) {
	return nil, nil
}

func (creatorPublicIdentityPersonaStore) FindActiveByUserID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}

func (creatorPublicIdentityPersonaStore) FindByUserHandle(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}

func (creatorPublicIdentityPersonaStore) FindByPersonaID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}

func (creatorPublicIdentityPersonaStore) Create(context.Context, *usermodel.Persona) error {
	return nil
}

func (creatorPublicIdentityPersonaStore) Update(context.Context, *usermodel.Persona) error {
	return nil
}

type staticContentFenceReader struct{}

func (staticContentFenceReader) ActiveContentReleaseFence(context.Context) (userports.ContentReleaseFence, bool, error) {
	return userports.ContentReleaseFence{Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-a", ManifestDigest: "sha256:" + strings.Repeat("a", 64)}, true, nil
}

type creatorPublicIdentityReader struct {
	profile *userports.CreatorRuntimeProfileView
}

func (r creatorPublicIdentityReader) FindByExactContentFence(
	_ context.Context,
	_ userports.ContentReleaseFence,
	identity string,
) (*userports.CreatorRuntimeProfileView, bool, error) {
	if r.profile != nil &&
		(identity == r.profile.PersonaID || identity == r.profile.CreatorID) {
		return r.profile, true, nil
	}
	return nil, false, nil
}

func (r creatorPublicIdentityReader) ListWorksByExactContentFence(
	ctx context.Context,
	fence userports.ContentReleaseFence,
	identity string,
) ([]userports.CreatorWorkView, bool, error) {
	profile, found, err := r.FindByExactContentFence(ctx, fence, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return append([]userports.CreatorWorkView(nil), profile.Works...), true, nil
}

func TestCreatorReleasePublicIdentityContract(t *testing.T) {
	now := time.Now().UTC()
	profile := &userports.CreatorRuntimeProfileView{
		CreatorID:   "qwq_creator_highland_travel_blogger_001",
		PersonaID:   "builtin_highland_travel_blogger",
		Handle:      "highland_slow_travel",
		DisplayName: "高原慢旅笔记",
		UpdatedAt:   now,
	}
	service := application.NewPersonaService(
		creatorPublicIdentityPersonaStore{},
		nil,
		nil,
		nil,
		nil,
		application.WithCreatorRuntimeProfiles(
			creatorPublicIdentityReader{profile: profile},
			staticContentFenceReader{},
		),
	)

	for _, identity := range []string{profile.PersonaID, profile.CreatorID} {
		view, err := service.GetPersonaProfileView(context.Background(), identity)
		if err != nil {
			t.Fatalf("read creator by %q: %v", identity, err)
		}
		if view["personaId"] != profile.PersonaID ||
			view["userHandle"] != profile.Handle ||
			view["displayName"] != profile.DisplayName {
			t.Fatalf("creator identity %q resolved unexpected view: %#v", identity, view)
		}
		if _, leaked := view["userId"]; leaked {
			t.Fatalf("creator identity %q leaked owner mapping: %#v", identity, view)
		}
	}

	view, err := service.GetPersonaProfileView(
		context.Background(),
		profile.Handle,
	)
	if err != nil {
		t.Fatalf("read creator by non-canonical handle: %v", err)
	}
	if view != nil {
		t.Fatalf("creator handle must not become a public identity: %#v", view)
	}
}

type creatorLegacyPersonaStore struct{ persona usermodel.Persona }

func (s *creatorLegacyPersonaStore) FindByID(context.Context, string) (*usermodel.Persona, error) {
	value := s.persona
	return &value, nil
}
func (s *creatorLegacyPersonaStore) FindByUserID(context.Context, string) ([]usermodel.Persona, error) {
	return []usermodel.Persona{s.persona}, nil
}
func (s *creatorLegacyPersonaStore) FindActiveByUserID(context.Context, string) (*usermodel.Persona, error) {
	value := s.persona
	return &value, nil
}
func (s *creatorLegacyPersonaStore) FindByUserHandle(_ context.Context, value string) (*usermodel.Persona, error) {
	if value == s.persona.UserHandle {
		copy := s.persona
		return &copy, nil
	}
	return nil, nil
}
func (s *creatorLegacyPersonaStore) FindByPersonaID(_ context.Context, value string) (*usermodel.Persona, error) {
	if value == s.persona.PersonaID {
		copy := s.persona
		return &copy, nil
	}
	return nil, nil
}
func (*creatorLegacyPersonaStore) Create(context.Context, *usermodel.Persona) error { return nil }
func (*creatorLegacyPersonaStore) Update(context.Context, *usermodel.Persona) error { return nil }

type creatorLegacyProfileStore struct{ profile usermodel.UserProfile }

func (s *creatorLegacyProfileStore) FindByID(_ context.Context, value string) (*usermodel.UserProfile, error) {
	if value == s.profile.UserID {
		copy := s.profile
		return &copy, nil
	}
	return nil, nil
}
func (*creatorLegacyProfileStore) FindByNickname(context.Context, string) (*usermodel.UserProfile, error) {
	return nil, nil
}
func (*creatorLegacyProfileStore) SearchProfiles(context.Context, string, int) ([]usermodel.UserProfile, error) {
	return nil, nil
}
func (*creatorLegacyProfileStore) CreateAccount(context.Context, userports.UserAccountCreate) error {
	return nil
}
func (*creatorLegacyProfileStore) PromoteRegistration(context.Context, userports.RegistrationPromotion) error {
	return nil
}

func TestLegacyContentReleasePersonaIsNotCreatorFallback(t *testing.T) {
	legacyPersona := usermodel.Persona{PersonaID: "legacy-release-persona", UserID: "legacy-release-owner", UserHandle: "legacy_release", DisplayName: "Legacy", IsActive: true, Status: "active"}
	personaStore := &creatorLegacyPersonaStore{persona: legacyPersona}
	profileStore := &creatorLegacyProfileStore{profile: usermodel.UserProfile{UserID: legacyPersona.UserID, IdentityOrigin: "content_release"}}
	service := application.NewPersonaService(personaStore, nil, nil, profileStore, nil)
	view, err := service.GetPersonaProfileView(context.Background(), legacyPersona.PersonaID)
	if err != nil {
		t.Fatal(err)
	}
	if view != nil {
		t.Fatalf("legacy content_release Persona became a fallback: %#v", view)
	}
}
