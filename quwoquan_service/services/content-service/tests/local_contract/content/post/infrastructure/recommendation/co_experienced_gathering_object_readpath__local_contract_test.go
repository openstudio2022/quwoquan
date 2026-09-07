// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-005
package recommendation_test

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"

	intersection "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	recommendation "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	testsupport "quwoquan_service/services/content-service/tests/support"

	rtredis "quwoquan_service/runtime/redis"
)

type canonicalObjectSource struct {
	object []intersection.IntersectionReasonView
}

func (s canonicalObjectSource) FactReasons(context.Context, string, string) ([]intersection.IntersectionReasonView, error) {
	return nil, nil
}

func (s canonicalObjectSource) AffinityReasons(context.Context, string, string) ([]intersection.IntersectionReasonView, error) {
	return nil, nil
}

func (s canonicalObjectSource) ObjectReasons(context.Context, string, string, string) ([]intersection.IntersectionReasonView, error) {
	return s.object, nil
}

// 经历交集（DEC-003）：真实 materializer 产出的 wire 样本经 Content 读面水合后，必须在对方主页
// （host=user:<peer>）通过 host_implicit 展示合同，而不是因 reason target 被派生成幽灵对象而被隐藏。
func TestCanonicalCoExperiencedGatheringSurvivesPeerProfileDisplayContract(t *testing.T) {
	client, err := recommendation.NewIntersectionReaderClient(
		"https://recommendation.internal",
		fixedServiceCredentials("Bearer feature-profile-token"),
	)
	if err != nil {
		t.Fatal(err)
	}
	fixturePath := filepath.Join(
		testsupport.RepositoryRoot(),
		"quwoquan_service/contracts/metadata/_shared/test_fixtures/recommendation/intersection/co_experienced_gathering_reason.json",
	)
	reasonWire, err := os.ReadFile(fixturePath)
	if err != nil {
		t.Fatalf("read canonical coExperiencedGathering wire fixture: %v", err)
	}
	responseBody := []byte(`{"subjectId":"viewer","objectType":"user","objectId":"profile-target","reasons":[` + string(reasonWire) + `],"generatedAt":"2026-08-12T12:00:00Z"}`)
	client.SetTransport(roundTripFunc(func(_ *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(bytes.NewReader(responseBody)),
		}, nil
	}))
	mapped, err := client.ObjectReasons(context.Background(), "viewer", "profile-target", "user")
	if err != nil || len(mapped) != 1 {
		t.Fatalf("decode canonical coExperiencedGathering wire: reasons=%+v err=%v", mapped, err)
	}
	reason := mapped[0]
	if reason.Kind != "coExperiencedGathering" || reason.ObjectKind != "person" ||
		reason.ActionTargetID != "profile-target" || reason.RelationObjectID != "profile-target" ||
		reason.SubjectContext != "gathering:gathering-west-lake-walk" ||
		reason.PrimaryTextL10nKey != "intersection.statement.co_experienced_gathering.counted" {
		t.Fatalf("mapped coExperiencedGathering contract drifted: %+v", reason)
	}
	// 主对象是对方本人：派生 target 必须正好等于对方主页宿主，而不是 user:<gatheringId>。
	target := intersection.IntersectionTargetForReason(reason)
	if target == nil || target.ObjectType != "user" || target.ObjectID != "profile-target" ||
		target.ObjectKind != "person" || target.RouteID != "userProfile" {
		t.Fatalf("reason target must be the peer person, got %+v", target)
	}

	svc := intersection.NewIntersectionService(
		rtredis.MustNewRouter(rtredis.DefaultRouterConfig()),
		intersection.WithIntersectionSource(canonicalObjectSource{object: mapped}),
	)
	svc.SetClock(func() time.Time { return time.Date(2026, 8, 12, 12, 30, 0, 0, time.UTC) })
	served, err := svc.ObjectIntersections(context.Background(), "viewer", "profile-target", "user", 10)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(served) != 1 {
		t.Fatalf("coExperiencedGathering must survive the peer-profile display contract, got %+v", served)
	}
	got := served[0]
	if got.PrimaryText != "你们一起参加过1次行动" || intersection.JoinedSpanText(got.PrimarySpans) != got.PrimaryText {
		t.Fatalf("served statement drifted from producer template: text=%q spans=%+v", got.PrimaryText, got.PrimarySpans)
	}
	if len(got.ActionHints) == 0 || !got.ActionHints[0].IsPrimary ||
		got.ActionHints[0].ActionKey != "start_gathering" || got.ActionHints[0].Target == nil ||
		got.ActionHints[0].Target.ObjectID != "profile-target" {
		t.Fatalf("primary action must be start_gathering pointing at the peer, got %+v", got.ActionHints)
	}
}
