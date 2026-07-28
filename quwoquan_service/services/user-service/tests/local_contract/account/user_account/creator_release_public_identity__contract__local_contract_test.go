package local_contract

import (
	"context"
	"testing"
	"time"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
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

func (creatorPublicIdentityPersonaStore) FindBySubAccountID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}

func (creatorPublicIdentityPersonaStore) Create(context.Context, *usermodel.Persona) error {
	return nil
}

func (creatorPublicIdentityPersonaStore) Update(context.Context, *usermodel.Persona) error {
	return nil
}

type creatorPublicIdentityReader struct {
	profile *usermodel.CreatorRuntimeProfile
}

func (r creatorPublicIdentityReader) FindActiveByPublicIdentity(
	_ context.Context,
	identity string,
) (*usermodel.CreatorRuntimeProfile, bool, error) {
	if r.profile != nil &&
		(identity == r.profile.SubAccountID || identity == r.profile.CreatorID) {
		return r.profile, true, nil
	}
	return nil, false, nil
}

func (r creatorPublicIdentityReader) ListActiveWorks(
	ctx context.Context,
	identity string,
) ([]usermodel.CreatorWorkRef, bool, error) {
	profile, found, err := r.FindActiveByPublicIdentity(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return append([]usermodel.CreatorWorkRef(nil), profile.Works...), true, nil
}

func TestCreatorReleasePublicIdentityContract(t *testing.T) {
	now := time.Now().UTC()
	profile := &usermodel.CreatorRuntimeProfile{
		CreatorID:    "qwq_creator_highland_travel_blogger_001",
		SubAccountID: "builtin_highland_travel_blogger",
		Handle:       "highland_slow_travel",
		DisplayName:  "高原慢旅笔记",
		Status:       "active",
		UpdatedAt:    now,
	}
	service := application.NewSubAccountService(
		creatorPublicIdentityPersonaStore{},
		nil,
		nil,
		nil,
		application.WithCreatorRuntimeProfiles(
			creatorPublicIdentityReader{profile: profile},
		),
	)

	for _, identity := range []string{profile.SubAccountID, profile.CreatorID} {
		view, err := service.GetSubAccountProfileView(context.Background(), identity)
		if err != nil {
			t.Fatalf("read creator by %q: %v", identity, err)
		}
		if view["subAccountId"] != profile.SubAccountID ||
			view["userId"] != profile.CreatorID ||
			view["displayName"] != profile.DisplayName {
			t.Fatalf("creator identity %q resolved unexpected view: %#v", identity, view)
		}
	}

	view, err := service.GetSubAccountProfileView(
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
