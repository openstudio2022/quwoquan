// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
package recommendation_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	transport "quwoquan_service/services/content-service/generated/content/post"
	recommendation "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	testsupport "quwoquan_service/services/content-service/tests/support"
)

func TestIntersectionReaderClientUsesGeneratedTypedOwnerForAllReads(t *testing.T) {
	client, err := recommendation.NewIntersectionReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatalf("new intersection reader: %v", err)
	}
	channel := "feed"
	reason := transport.IntersectionReason{
		IntersectionId: "intersection-001", IntersectionClass: "fact",
		SubjectId: "persona one", Kind: "sharedFollowees", Dimension: "relationship",
		IntersectionPoints: []transport.IntersectionPoint{{
			PointId: "point-001", PointClass: "fact", Dimension: "relationship",
			SourceRef: "sharedFollowees", SampleVisuals: []transport.IntersectionVisual{{
				AssetKind: "avatar", DisplayName: "公开昵称",
				Target: &transport.IntersectionTarget{ObjectType: "user", ObjectId: "persona-002"},
			}},
		}},
		PrimarySpans: []transport.IntersectionTextSpan{{
			Text: "公开昵称", Role: "person",
			Visual: &transport.IntersectionVisual{AssetKind: "avatar", DisplayName: "公开昵称"},
		}},
		DimensionPointSummary: []transport.IntersectionDimensionTally{{
			Dimension: "relationship", Count: 1, BriefSpans: []transport.IntersectionTextSpan{{Text: "1 个交集", Role: "plain"}},
			CountObjectKind: "person", IconKey: "relationship",
		}},
	}
	client.SetTransport(roundTripFunc(func(request *http.Request) (*http.Response, error) {
		if request.Header.Get("Authorization") != "Bearer feature-profile-token" {
			t.Fatalf("authorization=%q", request.Header.Get("Authorization"))
		}
		switch request.URL.EscapedPath() {
		case "/internal/recommendation/subjects/persona%20one/intersections":
			if request.Method != transport.ListRecommendationSubjectIntersectionsMethod ||
				request.URL.Query().Get("intersectionClass") != "fact" ||
				request.URL.Query().Get("channel") != channel {
				t.Fatalf("subject request=%s %s", request.Method, request.URL.String())
			}
			return typedJSONResponse(t, transport.RecommendationIntersectionReasonSlice{
				SubjectId: "persona one", IntersectionClass: "fact", Channel: &channel,
				Reasons: []transport.IntersectionReason{reason}, GeneratedAt: time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
			}), nil
		case "/internal/recommendation/subjects/persona%20one/objects/post/post%20one/intersections":
			return typedJSONResponse(t, transport.RecommendationObjectIntersectionReasonSlice{
				SubjectId: "persona one", ObjectType: "post", ObjectId: "post one",
				Reasons: []transport.IntersectionReason{reason}, GeneratedAt: time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
			}), nil
		case "/internal/recommendation/intersection-supply/circle_membership":
			return typedJSONResponse(t, transport.RecommendationIntersectionSupply{
				SupplyKey: "circle_membership", DistinctObjectCount: 7,
				ComputedAt: time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
			}), nil
		default:
			t.Fatalf("unexpected path=%q", request.URL.EscapedPath())
			return nil, nil
		}
	}))

	facts, err := client.FactReasons(context.Background(), "persona one", channel)
	if err != nil {
		t.Fatalf("fact reasons: %v", err)
	}
	if len(facts) != 1 || facts[0].IntersectionID != "intersection-001" ||
		len(facts[0].PrimarySpans) != 1 || facts[0].PrimarySpans[0].Visual == nil ||
		facts[0].DimensionPointSummary[0].CountObjectKind != "person" {
		t.Fatalf("mapped facts=%+v", facts)
	}
	objects, err := client.ObjectReasons(context.Background(), "persona one", "post one", "post")
	if err != nil || len(objects) != 1 {
		t.Fatalf("object reasons=%+v err=%v", objects, err)
	}
	count, err := client.DistinctObjectSupply(context.Background(), "circle_membership")
	if err != nil || count != 7 {
		t.Fatalf("supply count=%d err=%v", count, err)
	}
}

func TestIntersectionReaderClientMapsCanonicalCoWishlistedEntityWire(t *testing.T) {
	client, err := recommendation.NewIntersectionReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatal(err)
	}
	fixturePath := filepath.Join(
		testsupport.RepositoryRoot(),
		"quwoquan_service/contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_wishlisted_entity_reason.json",
	)
	reasonWire, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Fatalf("read canonical coWishlistedEntity wire fixture: %v", err)
	}
	responseBody := []byte(`{"subjectId":"viewer","intersectionClass":"fact","channel":"feed","reasons":[` + string(reasonWire) + `],"generatedAt":"2026-08-12T12:00:00Z"}`)
	client.SetTransport(roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(bytes.NewReader(responseBody)),
		}, nil
	}))

	reasons, err := client.FactReasons(context.Background(), "viewer", "feed")
	if err != nil {
		t.Fatalf("decode and map canonical coWishlistedEntity wire: %v", err)
	}
	if len(reasons) != 1 {
		t.Fatalf("mapped reasons=%+v", reasons)
	}
	reason := reasons[0]
	if reason.Kind != "coWishlistedEntity" || reason.ObjectKind != "place" ||
		reason.DisplayBinding != "explicit_link" ||
		reason.SubjectContext != "homepage:homepage-west-lake" {
		t.Fatalf("mapped reason contract drifted: %+v", reason)
	}
	if len(reason.PrimarySpans) != 2 || reason.PrimarySpans[1].Target == nil ||
		reason.PrimarySpans[1].Target.ObjectType != "homepage" ||
		reason.PrimarySpans[1].Target.ObjectID != "homepage-west-lake" ||
		reason.PrimarySpans[1].Target.RouteID != "homepageDetail" {
		t.Fatalf("mapped primary spans=%+v", reason.PrimarySpans)
	}
	// 行动阶梯来自注册表 actionHintsByKind.coWishlistedEntity，首位 primary 必须是 start_gathering。
	if len(reason.ActionHints) < 1 || reason.ActionHints[0].Target == nil || !reason.ActionHints[0].IsPrimary ||
		reason.ActionHints[0].ActionKey != "start_gathering" ||
		reason.ActionHints[0].Dispatch != "gathering" ||
		reason.ActionHints[0].Target.ObjectID != "homepage-west-lake" {
		t.Fatalf("mapped action hints=%+v", reason.ActionHints)
	}
}

func TestIntersectionReaderClientFailsClosedOnIdentityAndDecoderDrift(t *testing.T) {
	client, err := recommendation.NewIntersectionReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatal(err)
	}
	client.SetTransport(roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Body: io.NopCloser(strings.NewReader(`{
				"subjectId":"another-persona","intersectionClass":"fact","channel":"feed",
				"reasons":[],"generatedAt":"2026-08-02T12:00:00Z","unknownReasons":[]
			}`)),
		}, nil
	}))
	if _, err := client.FactReasons(context.Background(), "persona-001", "feed"); err == nil ||
		!strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("expected strict decoder failure, got %v", err)
	}
}

func TestIntersectionReaderClientAcceptsExplicitCanonicalGlobalSnapshot(t *testing.T) {
	client, err := recommendation.NewIntersectionReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatal(err)
	}
	client.SetTransport(roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return typedJSONResponse(t, transport.RecommendationIntersectionReasonSlice{
			SubjectId: "persona-001", IntersectionClass: "fact", Channel: nil,
			Reasons:     []transport.IntersectionReason{},
			GeneratedAt: time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC),
		}), nil
	}))
	if _, err := client.FactReasons(context.Background(), "persona-001", "video_book"); err != nil {
		t.Fatalf("canonical global snapshot: %v", err)
	}
}

func typedJSONResponse(t *testing.T, value any) *http.Response {
	t.Helper()
	payload, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal response: %v", err)
	}
	return &http.Response{
		StatusCode: http.StatusOK,
		Header:     http.Header{"Content-Type": []string{"application/json"}},
		Body:       io.NopCloser(bytes.NewReader(payload)),
	}
}
