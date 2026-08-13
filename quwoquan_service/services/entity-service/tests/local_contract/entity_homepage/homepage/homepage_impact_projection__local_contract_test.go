// spec_ref: specs/feature-tree/object-homepage-network/spec.md#dom-002
package local_contract

import (
	"context"
	"testing"

	testsupport "quwoquan_service/services/entity-service/tests/support/homepagefixture"
)

// RelatedGroups 读投影在真实链路尚无事实消费者写入口，api_integration 只能
// 证明真实存储上的诚实空态；非空 impact statement 与 introduction
// relatedObjects 的结构化组装规则由本对象级 fixture 测试守住。
func TestHomepageImpactBuildsStructuredStatementsFromRelatedGroups(t *testing.T) {
	service := testsupport.NewFixtureHomepageService()

	impact, err := service.GetHomepageImpact(context.Background(), "homepage_sight_west_lake")
	if err != nil {
		t.Fatalf("get homepage impact: %v", err)
	}
	if impact.HomepageID != "homepage_sight_west_lake" {
		t.Fatalf("expected homepageId homepage_sight_west_lake, got %q", impact.HomepageID)
	}
	if impact.Total <= 0 {
		t.Fatalf("expected positive total, got %d", impact.Total)
	}
	if len(impact.Items) == 0 {
		t.Fatalf("expected impact items")
	}
	first := impact.Items[0]
	if first.PrimaryText == "" {
		t.Fatalf("expected non-empty primaryText")
	}
	joined := ""
	hasCircleObjectSpan := false
	for _, span := range first.PrimarySpans {
		joined += span.Text
		if span.Role == "object" && span.Target != nil &&
			span.Target.ObjectType == "circle" && span.Target.ObjectID == "fixture_circle_photo" {
			hasCircleObjectSpan = true
		}
	}
	if joined != first.PrimaryText || !hasCircleObjectSpan {
		t.Fatalf(
			"invalid primarySpans: joined=%q primary=%q spans=%+v",
			joined, first.PrimaryText, first.PrimarySpans,
		)
	}
	representative := first.RepresentativeActor
	if representative == nil ||
		representative.DisplayName != "契约摄影社主理人" ||
		representative.RelationLabel != "圈子主理人" {
		t.Fatalf("expected relationship-qualified representative actor, got %+v", representative)
	}
	if representative.Target == nil ||
		representative.Target.ObjectType != "user" ||
		representative.Target.ObjectID != "fixture_user_owner" {
		t.Fatalf("expected routable user actor target, got %+v", representative.Target)
	}
	if len(first.ActionHints) == 0 {
		t.Fatalf("expected actionHints")
	}
	hint := first.ActionHints[0]
	if hint.Target == nil || hint.Target.ObjectID != "fixture_circle_photo" {
		t.Fatalf("expected action target fixture_circle_photo, got %+v", hint.Target)
	}
}

func TestHomepageIntroductionProjectsRelatedObjectsFromDetailProjection(t *testing.T) {
	service := testsupport.NewFixtureHomepageService()

	introduction, err := service.GetHomepageIntroduction(
		context.Background(),
		"homepage_sight_west_lake",
	)
	if err != nil {
		t.Fatalf("get homepage introduction: %v", err)
	}
	if len(introduction.RelatedObjects) == 0 {
		t.Fatalf("expected relatedObjects projected from detail projection")
	}
	related := introduction.RelatedObjects[0]
	if related.CircleID != "fixture_circle_photo" || related.Name != "契约摄影社" {
		t.Fatalf("expected fixture related circle, got %+v", related)
	}
}
