// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t2
package http_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
	"time"

	. "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

type sourceAttributionPostDetailReader struct {
	details map[postports.PostID]postports.PostDetailSlice
}

func (reader sourceAttributionPostDetailReader) FindPostDetail(
	_ context.Context,
	postID postports.PostID,
) (postports.PostDetailSlice, bool, error) {
	detail, found := reader.details[postID]
	return detail, found, nil
}

func TestGetPostProjectsCompleteArticleAndImageSourceAttribution(t *testing.T) {
	t.Parallel()

	collectedAt := time.Date(2026, time.August, 11, 1, 2, 3, 0, time.UTC)
	tests := []struct {
		name        string
		postID      postports.PostID
		contentType postports.ContentType
		attribution *postports.PostSourceAttributionSlice
		want        map[string]any
	}{
		{
			name:        "article",
			postID:      postports.NewPostID("data_article_source_attribution_complete"),
			contentType: postports.ContentType("article"),
			attribution: completeSourceAttributionFixture(
				"article",
				"Wikimedia Commons",
				collectedAt,
			),
			want: completeSourceAttributionWire(
				"article",
				"Wikimedia Commons",
				collectedAt,
			),
		},
		{
			name:        "image",
			postID:      postports.NewPostID("data_image_source_attribution_complete"),
			contentType: postports.ContentType("image"),
			attribution: completeSourceAttributionFixture(
				"image",
				"Openverse",
				collectedAt.Add(time.Minute),
			),
			want: completeSourceAttributionWire(
				"image",
				"Openverse",
				collectedAt.Add(time.Minute),
			),
		},
	}

	details := make(map[postports.PostID]postports.PostDetailSlice, len(tests))
	for _, test := range tests {
		details[test.postID] = postports.PostDetailSlice{
			PostID:            test.postID,
			ContentType:       test.contentType,
			SourceAttribution: test.attribution,
			Status:            postports.PostStatus("published"),
			Visibility:        postports.PostVisibility("public"),
			ModerationStatus:  "approved",
		}
	}
	handler := NewContentHandler(
		nil,
		nil,
		postapp.NewPostQueryFacade(postapp.PostQueryDependencies{
			Detail: sourceAttributionPostDetailReader{details: details},
		}),
		nil,
		nil,
		nil,
		nil,
	).Routes()

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := httptest.NewRequest(
				http.MethodGet,
				"/content/posts/"+string(test.postID),
				nil,
			)
			recorder := httptest.NewRecorder()

			handler.ServeHTTP(recorder, request)

			if recorder.Code != http.StatusOK {
				t.Fatalf("GetPost status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			var response map[string]any
			if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
				t.Fatalf("decode GetPost response: %v", err)
			}
			got, ok := response["sourceAttribution"].(map[string]any)
			if !ok {
				t.Fatalf("GetPost sourceAttribution missing or not an object: %s", recorder.Body.String())
			}
			if len(got) != len(test.want) || !reflect.DeepEqual(got, test.want) {
				t.Fatalf("GetPost sourceAttribution\n got: %#v\nwant: %#v", got, test.want)
			}
		})
	}
}

func completeSourceAttributionFixture(
	kind string,
	platform string,
	collectedAt time.Time,
) *postports.PostSourceAttributionSlice {
	return &postports.PostSourceAttributionSlice{
		IsOriginal:                    false,
		OriginalCreatorID:             kind + "-creator-id",
		OriginalCreatorName:           kind + " creator",
		OriginalCreatorProfileURL:     "https://media.example/creators/" + kind,
		Platform:                      platform,
		SourcePostURL:                 "https://media.example/posts/" + kind,
		OriginalAssetURL:              "https://media.example/assets/" + kind,
		AttributionText:               kind + " creator / CC BY-SA 4.0",
		RightsBasis:                   "CC BY-SA 4.0",
		CommercialAuthorizationStatus: "unverified",
		PublicationAdmission:          "research_release",
		AuthorizationProofURL:         "https://media.example/proofs/" + kind,
		TermsURL:                      "https://creativecommons.org/licenses/by-sa/4.0/",
		RiskAcceptanceID:              kind + "-risk-acceptance",
		WatermarkStatus:               "absent",
		AudioRightsStatus:             "no_audio",
		ModelReleaseStatus:            "not_required",
		PropertyReleaseStatus:         "not_required",
		CollectedAt:                   collectedAt,
		TakedownPolicy:                "quwoquan_standard_notice_and_takedown",
	}
}

func completeSourceAttributionWire(
	kind string,
	platform string,
	collectedAt time.Time,
) map[string]any {
	return map[string]any{
		"isOriginal":                    false,
		"originalCreatorId":             kind + "-creator-id",
		"originalCreatorName":           kind + " creator",
		"originalCreatorProfileUrl":     "https://media.example/creators/" + kind,
		"platform":                      platform,
		"sourcePostUrl":                 "https://media.example/posts/" + kind,
		"originalAssetUrl":              "https://media.example/assets/" + kind,
		"attributionText":               kind + " creator / CC BY-SA 4.0",
		"rightsBasis":                   "CC BY-SA 4.0",
		"commercialAuthorizationStatus": "unverified",
		"publicationAdmission":          "research_release",
		"authorizationProofUrl":         "https://media.example/proofs/" + kind,
		"termsUrl":                      "https://creativecommons.org/licenses/by-sa/4.0/",
		"riskAcceptanceId":              kind + "-risk-acceptance",
		"watermarkStatus":               "absent",
		"audioRightsStatus":             "no_audio",
		"modelReleaseStatus":            "not_required",
		"propertyReleaseStatus":         "not_required",
		"collectedAt":                   collectedAt.Format(time.RFC3339),
		"takedownPolicy":                "quwoquan_standard_notice_and_takedown",
	}
}
