package api_integration

// WP1·T2 contract：六类交集事实 kind 必须由真实 Mongo 数据源产出，
// kind 全部使用注册表标准名（specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md §5.4），
// primaryText 由云侧产出且非空可枚举（G2：端侧只读直出）。

import (
	"context"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

const (
	ixViewer = "ixsrc_viewer"
	ixObject = "ixsrc_object"
	ixEntity = "地点/取景地/横竖影像馆取景地"
)

func seedIntersectionSourceFixtures(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	relationships := mongoDB.Collection("persona_follow_projection")
	members := mongoDB.Collection("circle_members")
	events := mongoDB.Collection("rm_behavior_events")
	posts := mongoDB.Collection("posts")
	cleanup := func() {
		_, _ = relationships.DeleteMany(ctx, bson.M{"sourcePersonaId": bson.M{"$regex": "^ixsrc_"}})
		_, _ = members.DeleteMany(ctx, bson.M{"userId": bson.M{"$regex": "^ixsrc_"}})
		_, _ = events.DeleteMany(ctx, bson.M{"userId": bson.M{"$regex": "^ixsrc_"}})
		_, _ = posts.DeleteMany(ctx, bson.M{"authorId": bson.M{"$regex": "^ixsrc_"}})
	}
	cleanup()
	t.Cleanup(cleanup)

	// sharedFollowees：viewer 与 object 共同关注 third_a / third_b。
	relationshipDocs := []any{
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_third_a", "following": true},
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_third_b", "following": true},
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_only_viewer", "following": true},
		bson.M{"sourcePersonaId": ixObject, "targetPersonaId": "ixsrc_third_a", "following": true},
		bson.M{"sourcePersonaId": ixObject, "targetPersonaId": "ixsrc_third_b", "following": true},
		bson.M{"sourcePersonaId": ixObject, "targetPersonaId": "ixsrc_only_object", "following": true},
		// followeeVisited：viewer 关注 visitor_c，visitor_c 到访过 ixEntity。
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_visitor_c", "following": true},
	}
	if _, err := relationships.InsertMany(ctx, relationshipDocs); err != nil {
		t.Fatalf("seed persona follow projection: %v", err)
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
		bson.M{"userId": ixViewer, "clientEventId": "ixsrc-event-comment-viewer", "occurredAt": time.Now(), "action": "comment", "contentId": "ixsrc_post_1", "createdAt": time.Now()},
		bson.M{"userId": ixObject, "clientEventId": "ixsrc-event-comment-object", "occurredAt": time.Now(), "action": "comment", "contentId": "ixsrc_post_1", "createdAt": time.Now()},
		bson.M{"userId": ixViewer, "clientEventId": "ixsrc-event-entity-viewer", "occurredAt": time.Now(), "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		bson.M{"userId": ixObject, "clientEventId": "ixsrc-event-entity-object", "occurredAt": time.Now(), "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		bson.M{"userId": "ixsrc_visitor_c", "clientEventId": "ixsrc-event-entity-visitor", "occurredAt": time.Now(), "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
	}
	if _, err := events.InsertMany(ctx, eventDocs); err != nil {
		t.Fatalf("seed rm_behavior_events: %v", err)
	}

	// 交集事实句只能使用内容域内已投影的真实作者展示快照。测试数据显式写入
	// 该权威读模型，禁止实现用 userId、占位名或客户端文案猜测用户身份。
	profileDocs := []any{
		bson.M{"authorId": ixObject, "status": "published", "authorDisplayNameSnapshot": "陆衡", "authorAvatarUrlSnapshot": "https://static.quwoquan.test/ix-object.png", "updatedAt": time.Now()},
		bson.M{"authorId": "ixsrc_visitor_c", "status": "published", "authorDisplayNameSnapshot": "周屿", "authorAvatarUrlSnapshot": "https://static.quwoquan.test/visitor-c.png", "updatedAt": time.Now()},
		bson.M{"authorId": "ixsrc_homepage_friend", "status": "published", "authorDisplayNameSnapshot": "林清越", "authorAvatarUrlSnapshot": "https://static.quwoquan.test/homepage-friend.png", "updatedAt": time.Now()},
		bson.M{"authorId": "ixsrc_circle_friend", "status": "published", "authorDisplayNameSnapshot": "顾南", "authorAvatarUrlSnapshot": "https://static.quwoquan.test/circle-friend.png", "updatedAt": time.Now()},
	}
	if _, err := posts.InsertMany(ctx, profileDocs); err != nil {
		t.Fatalf("seed author display projections: %v", err)
	}
}

func newRealIntersectionService(t *testing.T) *intersectionapp.IntersectionService {
	t.Helper()
	src := recinfra.NewMongoIntersectionSource(
		recinfra.NewMongoSocialGraphProvider(mongoDB), nil, nil)
	return intersectionapp.NewIntersectionService(nil, intersectionapp.WithIntersectionSource(src))
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

	kinds := map[string]intersectionapp.IntersectionPointView{}
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

// TestIntersectionSource_SharedCircleDoesNotUsePersonNameAsCircleName（V3）：
// 人↔人的 sharedCircle reason 只有共同圈子数量，没有圈子对象 target；此时必须按
// 「具名样本 → 纯计数 → 隐藏」降级为可证计数句，禁止把对方人名冒充圈子名。
func TestIntersectionSource_SharedCircleDoesNotUsePersonNameAsCircleName(t *testing.T) {
	ctx := context.Background()
	const (
		viewerID = "ixsrc_circle_only_viewer"
		objectID = "ixsrc_circle_only_object"
		circleID = "ixsrc_circle_only_circle"
	)
	members := mongoDB.Collection("circle_members")
	posts := mongoDB.Collection("posts")
	cleanup := func() {
		_, _ = members.DeleteMany(ctx, bson.M{
			"circleId": circleID,
			"userId":   bson.M{"$in": []string{viewerID, objectID}},
		})
		_, _ = posts.DeleteMany(ctx, bson.M{"authorId": objectID})
	}
	cleanup()
	t.Cleanup(cleanup)

	if _, err := members.InsertMany(ctx, []any{
		bson.M{"circleId": circleID, "userId": viewerID},
		bson.M{"circleId": circleID, "userId": objectID},
	}); err != nil {
		t.Fatalf("seed circle_members: %v", err)
	}
	if _, err := posts.InsertOne(ctx, bson.M{
		"authorId":                  objectID,
		"status":                    "published",
		"authorDisplayNameSnapshot": "交集约伴体验号",
		"updatedAt":                 time.Now(),
	}); err != nil {
		t.Fatalf("seed author display projection: %v", err)
	}

	reasons, err := newRealIntersectionService(t).ObjectIntersections(
		ctx,
		viewerID,
		objectID,
		"user",
		8,
	)
	if err != nil {
		t.Fatalf("object intersections: %v", err)
	}
	if len(reasons) != 1 {
		t.Fatalf("want one sharedCircle reason, got %+v", reasons)
	}
	reason := reasons[0]
	if strings.Contains(reason.PrimaryText, "都加入了「交集约伴体验号」") {
		t.Fatalf("person display name must not pose as circle name: %q", reason.PrimaryText)
	}
	if !strings.Contains(reason.PrimaryText, "1个共同圈子") {
		t.Fatalf("counted sharedCircle fallback expected, got %q", reason.PrimaryText)
	}
	var joined strings.Builder
	for _, span := range reason.PrimarySpans {
		joined.WriteString(span.Text)
	}
	if joined.String() != reason.PrimaryText {
		t.Fatalf("spans invariant broken: joined=%q primary=%q", joined.String(), reason.PrimaryText)
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
	var relation *intersectionapp.IntersectionReasonView
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
// 产出桥接型 followeeVisited（N位你关注的人来过「具体对象名」）。
func TestIntersectionSource_EntityObjectProducesFolloweeVisited(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	svc := newRealIntersectionService(t)

	reasons, err := svc.ObjectIntersections(context.Background(), ixViewer, ixEntity, "sight", 8)
	if err != nil {
		t.Fatalf("entity intersections: %v", err)
	}
	var hit *intersectionapp.IntersectionReasonView
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
	if !strings.Contains(hit.PrimaryText, "1位你关注的人来过「横竖影像馆取景地」") {
		t.Fatalf("followeeVisited primaryText off-dictionary: %q", hit.PrimaryText)
	}
	if len(hit.IntersectionPoints) == 0 {
		t.Fatalf("followeeVisited points must be enumerable")
	}
}

func TestIntersectionSource_HomepageAndCircleObjectsUseConcreteActionSemantics(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	ctx := context.Background()
	relationships := mongoDB.Collection("persona_follow_projection")
	events := mongoDB.Collection("rm_behavior_events")
	docs := []any{
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_homepage_friend", "following": true},
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_circle_friend", "following": true},
	}
	if _, err := relationships.InsertMany(ctx, docs); err != nil {
		t.Fatalf("seed relationship projection: %v", err)
	}
	eventDocs := []any{
		bson.M{
			"userId":        "ixsrc_homepage_friend",
			"clientEventId": "ixsrc-event-homepage-friend",
			"occurredAt":    time.Now(),
			"action":        "entity_page_view",
			"entityRefs":    []string{"homepage_sight_west_lake"},
			"displayName":   "西湖景区",
			"createdAt":     time.Now(),
		},
		bson.M{
			"userId":        "ixsrc_circle_friend",
			"clientEventId": "ixsrc-event-circle-friend",
			"occurredAt":    time.Now(),
			"action":        "entity_page_view",
			"entityRefs":    []string{"fixture_circle_photo"},
			"displayName":   "契约摄影社",
			"createdAt":     time.Now(),
		},
	}
	if _, err := events.InsertMany(ctx, eventDocs); err != nil {
		t.Fatalf("seed object visit display names: %v", err)
	}

	svc := newRealIntersectionService(t)
	assertFolloweeVisitedReason := func(objectID, objectType, wantName, wantObjectKind string) {
		t.Helper()
		reasons, err := svc.ObjectIntersections(ctx, ixViewer, objectID, objectType, 8)
		if err != nil {
			t.Fatalf("object intersections %s: %v", objectID, err)
		}
		var hit *intersectionapp.IntersectionReasonView
		for i := range reasons {
			for _, p := range reasons[i].IntersectionPoints {
				if p.SourceRef == "followeeVisited" {
					hit = &reasons[i]
				}
			}
		}
		if hit == nil {
			t.Fatalf("missing followeeVisited for %s", objectID)
		}
		if !strings.Contains(hit.PrimaryText, wantName) {
			t.Fatalf("followeeVisited primaryText for %s = %q, want contain %q", objectID, hit.PrimaryText, wantName)
		}
		if hit.ActionType != "view_object" {
			t.Fatalf("followeeVisited actionType for %s = %q, want view_object", objectID, hit.ActionType)
		}
		if hit.ObjectKind != wantObjectKind {
			t.Fatalf("followeeVisited objectKind for %s = %q, want %q", objectID, hit.ObjectKind, wantObjectKind)
		}
		if len(hit.ActionHints) == 0 || hit.ActionHints[0].Target == nil {
			t.Fatalf("followeeVisited actionHints for %s must target object", objectID)
		}
		if got := hit.ActionHints[0].Target.ObjectID; got != objectID {
			t.Fatalf("followeeVisited target objectId for %s = %q", objectID, got)
		}
	}

	assertFolloweeVisitedReason("homepage_sight_west_lake", "homepage", "西湖景区", "place")
	assertFolloweeVisitedReason("fixture_circle_photo", "circle", "契约摄影社", "circle")
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
			case "circleTag", "tagRef", "social_friend":
				t.Fatalf("point kind must be registry standard name, got data-source id %q", p.SourceRef)
			}
		}
	}
	if !found {
		t.Fatalf("want at least one registry-kind fact point, reasons=%d", len(reasons))
	}
}

func kindNames(kinds map[string]intersectionapp.IntersectionPointView) []string {
	out := make([]string, 0, len(kinds))
	for k := range kinds {
		out = append(out, k)
	}
	return out
}
