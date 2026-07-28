package api_integration

import (
	"context"
	"net/http"
	"testing"
	"time"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

func TestCreatorReleasePublicProfileUsesCanonicalIdentities(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })
	now := time.Now().UTC()
	profile := usermodel.CreatorRuntimeProfile{
		CreatorID:    "creator-release-a",
		SubAccountID: "builtin_release_creator_a",
		Handle:       "release_creator_a",
		DisplayName:  "发布创作者 A",
		Headline:     "release-bound creator",
		Bio:          "creator profile from immutable release",
		ReleaseID:    "release-a",
		Status:       "active",
		ManagedBy:    "qwq_data",
		ImportedAt:   now,
		UpdatedAt:    now,
	}
	if _, err := mongoDB.Collection("creator_runtime_profiles").InsertOne(
		context.Background(),
		profile,
	); err != nil {
		t.Fatalf("insert creator runtime profile: %v", err)
	}

	rec := doRequest(
		t,
		http.MethodGet,
		"/user/builtin_release_creator_a",
		"",
		nil,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("canonical subAccountId expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body := parseJSON(t, rec)
	if body["subAccountId"] != "builtin_release_creator_a" ||
		body["subjectType"] != "creator" ||
		body["displayName"] != "发布创作者 A" {
		t.Fatalf("unexpected creator public profile: %#v", body)
	}

	creatorIDRec := doRequest(
		t,
		http.MethodGet,
		"/user/creator-release-a",
		"",
		nil,
	)
	if creatorIDRec.Code != http.StatusOK {
		t.Fatalf(
			"canonical creatorProfileId expected 200, got %d: %s",
			creatorIDRec.Code,
			creatorIDRec.Body.String(),
		)
	}
	creatorIDBody := parseJSON(t, creatorIDRec)
	if creatorIDBody["subAccountId"] != "builtin_release_creator_a" ||
		creatorIDBody["userId"] != "creator-release-a" ||
		creatorIDBody["displayName"] != "发布创作者 A" {
		t.Fatalf("unexpected creatorProfileId readback: %#v", creatorIDBody)
	}
}
