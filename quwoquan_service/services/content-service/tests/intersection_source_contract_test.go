package tests

// WP1·T2 contract：六类交集事实 kind 必须由真实 Mongo 数据源产出，
// kind 全部使用注册表标准名（specs/product/intersection-definition-and-application.md §5.4），
// primaryText 由云侧产出且非空可枚举（G2：端侧只读直出）。

import (
	"context"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/content-service/internal/application"
	recinfra "quwoquan_service/services/content-service/internal/infrastructure/recommendation"
)

const (
	ixViewer = "ixsrc_viewer"
	ixObject = "ixsrc_object"
	ixEntity = "ixsrc_entity_lake"
)

func seedIntersectionSourceFixtures(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	follow := mongoDB.Collection("follow_edges")
	members := mongoDB.Collection("circle_members")
	events := mongoDB.Collection("rm_behavior_events")
	cleanup := func() {
		_, _ = follow.DeleteMany(ctx, bson.M{"followerId": bson.M{"$regex": "^ixsrc_"}})
		_, _ = members.DeleteMany(ctx, bson.M{"userId": bson.M{"$regex": "^ixsrc_"}})
		_, _ = events.DeleteMany(ctx, bson.M{"userId": bson.M{"$regex": "^ixsrc_"}})
	}
	cleanup()
	t.Cleanup(cleanup)

	// sharedFollowees：viewer 与 object 共同关注 third_a / third_b。
	followDocs := []any{
		bson.M{"followerId": ixViewer, "followeeId": "ixsrc_third_a"},
		bson.M{"followerId": ixViewer, "followeeId": "ixsrc_third_b"},
		bson.M{"followerId": ixViewer, "followeeId": "ixsrc_only_viewer"},
		bson.M{"followerId": ixObject, "followeeId": "ixsrc_third_a"},
		bson.M{"followerId": ixObject, "followeeId": "ixsrc_third_b"},
		bson.M{"followerId": ixObject, "followeeId": "ixsrc_only_object"},
		// followeeVisited：viewer 关注 visitor_c，visitor_c 到访过 ixEntity。
		bson.M{"followerId": ixViewer, "followeeId": "ixsrc_visitor_c"},
	}
	if _, err := follow.InsertMany(ctx, followDocs); err != nil {
		t.Fatalf("seed follow_edges: %v", err)
	}

	// sharedCircle：双方同在一个圈子。
	memberDocs := []any{
		bson.M{"circleId": "ixsrc_circle_1", "userId": ixViewer},
		bson.M{"circleId": "ixsrc_circle_1", "userId": ixObject},
	}
	if _, err := members.InsertMany(ctx, memberDocs); err != nil {
		t.Fatalf("seed circle_members: %v", err)
	}

	// coCommented：双方评论过同一篇内容；coVisitedEntity：双方都到访过 ixEntity；
	// followeeVisited：visitor_c 到访过 ixEntity。
	eventDocs := []any{
		bson.M{"userId": ixViewer, "action": "comment", "contentId": "ixsrc_post_1", "createdAt": time.Now()},
		bson.M{"userId": ixObject, "action": "comment", "contentId": "ixsrc_post_1", "createdAt": time.Now()},
		bson.M{"userId": ixViewer, "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		bson.M{"userId": ixObject, "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		bson.M{"userId": "ixsrc_visitor_c", "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
	}
	if _, err := events.InsertMany(ctx, eventDocs); err != nil {
		t.Fatalf("seed rm_behavior_events: %v", err)
	}
}

func newRealIntersectionService(t *testing.T) *application.IntersectionService {
	t.Helper()
	src := recinfra.NewMongoIntersectionSource(
		recinfra.NewMongoSocialGraphProvider(mongoDB), nil, nil)
	return application.NewIntersectionService(nil, application.WithIntersectionSource(src))
}

// TestIntersectionSource_PersonObjectProducesStandardFactKinds 断言人↔人对象页
// 交集由真实数据源产出 sharedFollowees / sharedCircle / coCommented / coVisitedEntity
// 四类标准 kind，且 count 与 displayText 可枚举。
func TestIntersectionSource_PersonObjectProducesStandardFactKinds(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	svc := newRealIntersectionService(t)

	reasons, err := svc.ObjectIntersections(context.Background(), ixViewer, ixObject, "user", 8)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(reasons) == 0 {
		t.Fatalf("want relation reason, got none")
	}

	kinds := map[string]application.IntersectionPointView{}
	for _, r := range reasons {
		if strings.TrimSpace(r.PrimaryText) == "" {
			t.Fatalf("reason %s missing primaryText (G2 cloud-authored copy)", r.IntersectionID)
		}
		for _, p := range r.IntersectionPoints {
			kinds[p.SourceRef] = p
		}
	}

	shared, ok := kinds["sharedFollowees"]
	if !ok {
		t.Fatalf("missing sharedFollowees point, got kinds %v", kindNames(kinds))
	}
	if shared.Count != 2 {
		t.Fatalf("sharedFollowees count want 2, got %d", shared.Count)
	}
	if !strings.Contains(shared.DisplayText, "2位共同关注的人") {
		t.Fatalf("sharedFollowees displayText off-dictionary: %q", shared.DisplayText)
	}

	circle, ok := kinds["sharedCircle"]
	if !ok {
		t.Fatalf("missing sharedCircle point, got kinds %v", kindNames(kinds))
	}
	if circle.Count != 1 {
		t.Fatalf("sharedCircle count want 1, got %d", circle.Count)
	}

	commented, ok := kinds["coCommented"]
	if !ok {
		t.Fatalf("missing coCommented point, got kinds %v", kindNames(kinds))
	}
	if commented.Count != 1 || strings.TrimSpace(commented.DisplayText) == "" {
		t.Fatalf("coCommented point not enumerable: %+v", commented)
	}

	visited, ok := kinds["coVisitedEntity"]
	if !ok {
		t.Fatalf("missing coVisitedEntity point, got kinds %v", kindNames(kinds))
	}
	if visited.Count != 1 {
		t.Fatalf("coVisitedEntity count want 1, got %d", visited.Count)
	}

	// 关注状态本身不再是交集点：互关/单向点不得出现。
	for kind := range kinds {
		if kind == "commonFollow" || kind == "mutualFollow" {
			t.Fatalf("relation-state kind %q must not be emitted as intersection point", kind)
		}
	}
}

// TestIntersectionSource_PersonReasonBackfillsDisplayProfile（WP1·T3）：
// 人级 reason 必须从 posts 作者快照读模型回填 displayName/avatarUrl，
// 不得下发占位 label 进 spotlight 候选窗。
func TestIntersectionSource_PersonReasonBackfillsDisplayProfile(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	ctx := context.Background()
	posts := mongoDB.Collection("posts")
	cleanup := func() {
		_, _ = posts.DeleteMany(ctx, bson.M{"authorId": bson.M{"$regex": "^ixsrc_"}})
	}
	cleanup()
	t.Cleanup(cleanup)
	if _, err := posts.InsertOne(ctx, bson.M{
		"authorId":                  ixObject,
		"status":                    "published",
		"authorDisplayNameSnapshot": "陆衡",
		"authorAvatarUrlSnapshot":   "https://static.quwoquan.test/luheng.png",
		"updatedAt":                 time.Now(),
	}); err != nil {
		t.Fatalf("seed posts snapshot: %v", err)
	}

	svc := newRealIntersectionService(t)
	reasons, err := svc.ObjectIntersections(context.Background(), ixViewer, ixObject, "user", 8)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	var relation *application.IntersectionReasonView
	for i := range reasons {
		if reasons[i].Dimension == "relationship" {
			relation = &reasons[i]
		}
	}
	if relation == nil {
		t.Fatalf("missing relationship reason")
	}
	if relation.DisplayName != "陆衡" {
		t.Fatalf("displayName must backfill from posts snapshot, got %q", relation.DisplayName)
	}
	if relation.AvatarURL != "https://static.quwoquan.test/luheng.png" {
		t.Fatalf("avatarUrl must backfill from posts snapshot, got %q", relation.AvatarURL)
	}
}

// TestIntersectionSource_EntityObjectProducesFolloweeVisited 断言实体对象页
// 产出桥接型 followeeVisited（N位你关注的人来过这里）。
func TestIntersectionSource_EntityObjectProducesFolloweeVisited(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	svc := newRealIntersectionService(t)

	reasons, err := svc.ObjectIntersections(context.Background(), ixViewer, ixEntity, "sight", 8)
	if err != nil {
		t.Fatalf("entity intersections: %v", err)
	}
	var hit *application.IntersectionReasonView
	for i := range reasons {
		for _, p := range reasons[i].IntersectionPoints {
			if p.SourceRef == "followeeVisited" {
				hit = &reasons[i]
			}
		}
	}
	if hit == nil {
		t.Fatalf("missing followeeVisited reason for entity object")
	}
	if !strings.Contains(hit.PrimaryText, "1位你关注的人来过这里") {
		t.Fatalf("followeeVisited primaryText off-dictionary: %q", hit.PrimaryText)
	}
	if len(hit.IntersectionPoints) == 0 {
		t.Fatalf("followeeVisited points must be enumerable")
	}
}

// TestIntersectionSource_FeedFactReasonUsesRegistryKinds 断言 feed 事实理由
// （圈子兴趣 / 关注的人在看）的 point kind 使用注册表标准名而非数据源标识。
func TestIntersectionSource_FeedFactReasonUsesRegistryKinds(t *testing.T) {
	ctx := context.Background()
	members := mongoDB.Collection("circle_members")
	aggregates := mongoDB.Collection("circle_tag_aggregates")
	cleanup := func() {
		_, _ = members.DeleteMany(ctx, bson.M{"userId": bson.M{"$regex": "^ixfeed_"}})
		_, _ = aggregates.DeleteMany(ctx, bson.M{"circleId": bson.M{"$regex": "^ixfeed_"}})
	}
	cleanup()
	t.Cleanup(cleanup)
	if _, err := members.InsertOne(ctx, bson.M{"circleId": "ixfeed_circle", "userId": "ixfeed_user"}); err != nil {
		t.Fatalf("seed circle_members: %v", err)
	}
	if _, err := aggregates.InsertOne(ctx, bson.M{
		"circleId": "ixfeed_circle",
		"tags":     bson.M{"骑行": 3.0, "露营": 2.0},
	}); err != nil {
		t.Fatalf("seed circle_tag_aggregates: %v", err)
	}

	src := recinfra.NewMongoIntersectionSource(
		recinfra.NewMongoSocialGraphProvider(mongoDB), nil, nil)
	reasons, err := src.FactReasons(ctx, "ixfeed_user", "")
	if err != nil {
		t.Fatalf("fact reasons: %v", err)
	}
	found := false
	for _, r := range reasons {
		for _, p := range r.IntersectionPoints {
			switch p.SourceRef {
			case "sharedTagSample", "followeeDiscussedThis", "followeeViewing":
				found = true
			case "circleTag", "followEdge", "tagRef", "social_friend":
				t.Fatalf("point kind must be registry standard name, got data-source id %q", p.SourceRef)
			}
		}
	}
	if !found {
		t.Fatalf("want at least one registry-kind fact point, reasons=%d", len(reasons))
	}
}

func kindNames(kinds map[string]application.IntersectionPointView) []string {
	out := make([]string, 0, len(kinds))
	for k := range kinds {
		out = append(out, k)
	}
	return out
}
