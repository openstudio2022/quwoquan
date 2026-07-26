package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	integration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func TestTagServiceProfileTagValidatorForwardsTaxonomyPrecondition(t *testing.T) {
	const releaseID = "taxonomy-release-current"
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.URL.Path != "/tag/validate" ||
			request.Header.Get("X-Internal-Service") != "user-service" {
			t.Fatalf("unexpected tag validation request: %s", request.URL.Path)
		}
		var body struct {
			ExpectedTaxonomyReleaseID string   `json:"expectedTaxonomyReleaseId"`
			TagRefs                   []string `json:"tagRefs"`
		}
		if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
			t.Fatalf("decode tag validation request: %v", err)
		}
		if body.ExpectedTaxonomyReleaseID != releaseID ||
			len(body.TagRefs) != 2 {
			t.Fatalf("unexpected tag validation request: %#v", body)
		}
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"taxonomyReleaseId": releaseID,
			"valid":             body.TagRefs,
			"invalid":           []string{},
		})
	}))
	defer server.Close()

	validator := integration.NewTagServiceProfileTagValidator(
		server.URL,
		server.Client(),
	)
	err := validator.ValidateProfileTags(
		context.Background(),
		releaseID,
		"Audience/用户/职业/产品运营/产品经理",
		[]string{"Audience/用户/兴趣偏好/旅行摄影/旅行"},
	)
	if err != nil {
		t.Fatalf("valid profile tag request rejected: %v", err)
	}
}

func TestTagServiceProfileTagValidatorRejectsReleaseDriftAndMissingAdapter(
	t *testing.T,
) {
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"taxonomyReleaseId": "taxonomy-release-new",
			"valid":             []string{},
			"invalid":           []string{},
		})
	}))
	defer server.Close()

	validator := integration.NewTagServiceProfileTagValidator(
		server.URL,
		server.Client(),
	)
	err := validator.ValidateProfileTags(
		context.Background(),
		"taxonomy-release-old",
		"",
		nil,
	)
	if !errors.Is(err, application.ErrProfileTaxonomyReleaseConflict) {
		t.Fatalf("expected taxonomy release conflict, got %v", err)
	}

	missing := integration.NewTagServiceProfileTagValidator("", nil)
	if err := missing.ValidateProfileTags(
		context.Background(),
		"taxonomy-release-old",
		"",
		nil,
	); err == nil {
		t.Fatal("missing tag-service adapter must fail closed")
	}
}
