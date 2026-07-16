package application

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type emptyPersonaStore struct{}

func (emptyPersonaStore) FindByID(context.Context, string) (*model.Persona, error) {
	return nil, nil
}
func (emptyPersonaStore) FindByUserID(context.Context, string) ([]model.Persona, error) {
	return nil, nil
}
func (emptyPersonaStore) FindActiveByUserID(context.Context, string) (*model.Persona, error) {
	return nil, nil
}
func (emptyPersonaStore) FindByUserHandle(context.Context, string) (*model.Persona, error) {
	return nil, nil
}
func (emptyPersonaStore) FindBySubAccountID(context.Context, string) (*model.Persona, error) {
	return nil, nil
}
func (emptyPersonaStore) HasAttributedHistory(context.Context, string) (bool, error) {
	return false, nil
}
func (emptyPersonaStore) Create(context.Context, *model.Persona) error { return nil }
func (emptyPersonaStore) Update(context.Context, *model.Persona) error { return nil }
func (emptyPersonaStore) Delete(context.Context, string) error         { return nil }
func (emptyPersonaStore) SwitchActive(context.Context, string, string) error {
	return nil
}

type emptyUserProfileStore struct{}

func (emptyUserProfileStore) FindByID(context.Context, string) (*model.UserProfile, error) {
	return nil, nil
}
func (emptyUserProfileStore) FindByNickname(context.Context, string) (*model.UserProfile, error) {
	return nil, nil
}
func (emptyUserProfileStore) SearchProfiles(context.Context, string, int) ([]model.UserProfile, error) {
	return nil, nil
}
func (emptyUserProfileStore) Create(context.Context, *model.UserProfile) error { return nil }
func (emptyUserProfileStore) Update(context.Context, *model.UserProfile) error { return nil }
func (emptyUserProfileStore) IncrementCounter(context.Context, string, string, int64) error {
	return nil
}

type emptyUserWorkReader struct{}

func (emptyUserWorkReader) ListByUserID(context.Context, string, string, int) ([]model.UserWork, string, error) {
	return nil, "", nil
}

type creatorRuntimeFixtureReader struct {
	profile model.CreatorRuntimeProfile
}

func (reader creatorRuntimeFixtureReader) FindActiveByIdentity(
	_ context.Context,
	identity string,
) (*model.CreatorRuntimeProfile, bool, error) {
	if identity != reader.profile.CreatorID &&
		identity != reader.profile.SubAccountID &&
		identity != reader.profile.Handle {
		return nil, false, nil
	}
	profile := reader.profile
	return &profile, true, nil
}

func (reader creatorRuntimeFixtureReader) ListActiveWorks(
	ctx context.Context,
	identity string,
) ([]model.CreatorWorkRef, bool, error) {
	profile, found, err := reader.FindActiveByIdentity(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return append([]model.CreatorWorkRef(nil), profile.Works...), true, nil
}

func TestCreatorRuntimeProfileUsesExistingPublicProfileContract(t *testing.T) {
	reader := creatorRuntimeFixtureReader{profile: model.CreatorRuntimeProfile{
		CreatorID:            "sys_travelphoto_0800",
		SubAccountID:         "sys_travelphoto_0800_sub_01",
		Handle:               "set-marker",
		DisplayName:          "片场坐标",
		Headline:             "旅行摄影手账",
		Bio:                  "路线写给脚步，照片写给回忆。",
		AvatarURL:            "https://media.example/media/objects/avatar.png",
		AvatarObjectKey:      "media/objects/avatar.png",
		AvatarSHA256:         "2af8bc6160d483e73f44c2919af87a1f4f4a707c70e008110f29109349014a1f",
		CoverURL:             "https://media.example/media/objects/cover.jpg",
		TagRefs:              []string{"Topic/摄影/旅行摄影"},
		PublicProfileTagRefs: []string{"Topic/摄影"},
		Roles:                []string{"creator"},
		Verticals:            []string{"travel", "photography"},
		Works: []model.CreatorWorkRef{{
			Ref: "posts/article/demo", Title: "示例作品", WorkType: "article",
		}},
		UpdatedAt: time.Date(2026, 7, 11, 1, 2, 3, 0, time.UTC),
	}}
	service := NewSubAccountService(
		emptyPersonaStore{},
		emptyPersonaStore{},
		emptyPersonaStore{},
		emptyUserProfileStore{},
		nil,
		WithCreatorRuntimeProfiles(reader),
	)
	view, err := service.GetSubAccountProfileView(context.Background(), "set-marker")
	if err != nil {
		t.Fatalf("GetSubAccountProfileView: %v", err)
	}
	if got := view["subjectType"]; got != "creator" {
		t.Fatalf("subjectType=%v", got)
	}
	if got := view["subAccountId"]; got != "sys_travelphoto_0800_sub_01" {
		t.Fatalf("subAccountId=%v", got)
	}
	if got := view["avatarUrl"]; got != reader.profile.AvatarURL {
		t.Fatalf("avatarUrl=%v", got)
	}
	if got := view["backgroundUrl"]; got != reader.profile.CoverURL {
		t.Fatalf("backgroundUrl=%v", got)
	}
	if got := view["postCount"]; got != int64(1) {
		t.Fatalf("postCount=%v", got)
	}
	for _, privateField := range []string{
		"avatarObjectKey", "avatarSha256", "packageDigest", "sourceRefs", "primaryEvidenceRef",
	} {
		if _, exposed := view[privateField]; exposed {
			t.Fatalf("public profile leaked %s", privateField)
		}
	}
}

func TestCreatorRuntimeWorksUseExistingWorksContractWithoutBodyCopy(t *testing.T) {
	reader := creatorRuntimeFixtureReader{profile: model.CreatorRuntimeProfile{
		CreatorID: "creator_1",
		Works: []model.CreatorWorkRef{
			{Ref: "posts/article/one", Title: "一", WorkType: "article", SortOrder: 1},
			{Ref: "posts/image/two", Title: "二", WorkType: "image", SortOrder: 2},
		},
	}}
	service := NewWorkService(emptyUserWorkReader{}, WithCreatorRuntimeWorks(reader))
	works, cursor, err := service.ListUserWorks(context.Background(), "creator_1", "", 1)
	if err != nil {
		t.Fatalf("ListUserWorks: %v", err)
	}
	if len(works) != 1 || works[0].RefID != "posts/article/one" {
		t.Fatalf("works=%+v", works)
	}
	if cursor != "posts/article/one" {
		t.Fatalf("cursor=%q", cursor)
	}
	if works[0].ID != works[0].RefID {
		t.Fatalf("work ID must remain canonical ref: %+v", works[0])
	}
}
