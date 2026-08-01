package api_integration

// WP1·T2 contract：六类交集事实 kind 必须由真实 Mongo 数据源产出，
// kind 全部使用注册表标准名（specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md §5.4），
// primaryText 由云侧产出且非空可枚举（G2：端侧只读直出）。

import (
	"context"
	"fmt"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/sharedtags"
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
		// followeeViewedObject：viewer 关注 visitor_c，visitor_c 浏览过 ixEntity。
		bson.M{"sourcePersonaId": ixViewer, "targetPersonaId": "ixsrc_visitor_c", "following": true},
		// commonFollower：fan_a / fan_b 同时关注 viewer 与 object（共同粉丝，
		// 与 sharedFollowees 方向相反）；fan_c 只关注 viewer，不得计入。
		bson.M{"sourcePersonaId": "ixsrc_fan_a", "targetPersonaId": ixViewer, "following": true},
		bson.M{"sourcePersonaId": "ixsrc_fan_a", "targetPersonaId": ixObject, "following": true},
		bson.M{"sourcePersonaId": "ixsrc_fan_b", "targetPersonaId": ixViewer, "following": true},
		bson.M{"sourcePersonaId": "ixsrc_fan_b", "targetPersonaId": ixObject, "following": true},
		bson.M{"sourcePersonaId": "ixsrc_fan_c", "targetPersonaId": ixViewer, "following": true},
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

	// coCommented：双方评论过同一篇内容；sharedEntityAttention：双方都浏览过 ixEntity；
	// followeeViewedObject：visitor_c 浏览过 ixEntity。
	// entity_page_view 只证明浏览，不证明到访；到访类 kind（coVisitedEntity /
	// followeeVisited）只允许由可证到访生产者产出，不得由本数据源产出。
	eventDocs := []any{
		bson.M{"userId": ixViewer, "clientEventId": "ixsrc-event-comment-viewer", "occurredAt": time.Now(), "action": "comment", "contentId": "ixsrc_post_1", "createdAt": time.Now()},
		bson.M{"userId": ixObject, "clientEventId": "ixsrc-event-comment-object", "occurredAt": time.Now(), "action": "comment", "contentId": "ixsrc_post_1", "createdAt": time.Now()},
		bson.M{"userId": ixViewer, "clientEventId": "ixsrc-event-entity-viewer", "occurredAt": time.Now(), "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		bson.M{"userId": ixObject, "clientEventId": "ixsrc-event-entity-object", "occurredAt": time.Now(), "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		bson.M{"userId": "ixsrc_visitor_c", "clientEventId": "ixsrc-event-entity-visitor", "occurredAt": time.Now(), "action": "entity_page_view", "contentId": "", "entityRefs": []string{ixEntity}, "createdAt": time.Now()},
		// coSharedContent / coLiked：双方都转发过 post_2、都点赞过 post_3。
		bson.M{"userId": ixViewer, "clientEventId": "ixsrc-event-share-viewer", "occurredAt": time.Now(), "action": "share", "contentId": "ixsrc_post_2", "createdAt": time.Now()},
		bson.M{"userId": ixObject, "clientEventId": "ixsrc-event-share-object", "occurredAt": time.Now(), "action": "share", "contentId": "ixsrc_post_2", "createdAt": time.Now()},
		bson.M{"userId": ixViewer, "clientEventId": "ixsrc-event-like-viewer", "occurredAt": time.Now(), "action": "like", "contentId": "ixsrc_post_3", "createdAt": time.Now()},
		bson.M{"userId": ixObject, "clientEventId": "ixsrc-event-like-object", "occurredAt": time.Now(), "action": "like", "contentId": "ixsrc_post_3", "createdAt": time.Now()},
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
// 交集由真实数据源产出 sharedFollowees / sharedCircle / coCommented /
// sharedEntityAttention 四类标准 kind，且 count 与 displayText 可枚举。
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

	// commonFollower 与 sharedFollowees 是同一条关注边的两个方向，必须分别产出，
	// 且不得互相污染计数：共同粉丝 2 位（fan_a / fan_b），只关注 viewer 的 fan_c 不算。
	followers, ok := kinds["commonFollower"]
	if !ok {
		t.Fatalf("missing commonFollower point, got kinds %v", kindNames(kinds))
	}
	if followers.Count != 2 {
		t.Fatalf("commonFollower count want 2, got %d", followers.Count)
	}
	if !strings.Contains(followers.DisplayText, "2位共同粉丝") {
		t.Fatalf("commonFollower displayText off-dictionary: %q", followers.DisplayText)
	}
	if followers.Dimension != "relationship" {
		t.Fatalf("commonFollower must stay on the relationship axis, got %q", followers.Dimension)
	}

	// 行为边求交（R2）：转发与点赞分别成点，不得合并为同一 kind——
	// 转发是公开二次传播、点赞是低成本认可，说服力不同，排序权重也不同。
	for _, expected := range []struct {
		kind        string
		count       int
		displayText string
	}{
		{kind: "coSharedContent", count: 1, displayText: "转发过1篇相同内容"},
		{kind: "coLiked", count: 1, displayText: "点赞过1篇相同内容"},
	} {
		point, ok := kinds[expected.kind]
		if !ok {
			t.Fatalf("missing %s point, got kinds %v", expected.kind, kindNames(kinds))
		}
		if point.Count != expected.count {
			t.Fatalf("%s count want %d, got %d", expected.kind, expected.count, point.Count)
		}
		if point.DisplayText != expected.displayText {
			t.Fatalf("%s displayText off-dictionary: %q", expected.kind, point.DisplayText)
		}
		if point.Dimension != "content" {
			t.Fatalf("%s must stay on the content axis, got %q", expected.kind, point.Dimension)
		}
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

	attention, ok := kinds["sharedEntityAttention"]
	if !ok {
		t.Fatalf("missing sharedEntityAttention point, got kinds %v", kindNames(kinds))
	}
	if attention.Count != 1 {
		t.Fatalf("sharedEntityAttention count want 1, got %d", attention.Count)
	}

	// 关注状态本身不再是交集点：互关/单向点不得出现。
	for kind := range kinds {
		if kind == "commonFollow" || kind == "mutualFollow" {
			t.Fatalf("relation-state kind %q must not be emitted as intersection point", kind)
		}
	}

	// P0 诚实红线：entity_page_view 只能证明浏览，禁止产出到访类事实。
	for _, visitKind := range []string{"coVisitedEntity", "followeeVisited"} {
		if _, exists := kinds[visitKind]; exists {
			t.Fatalf("physical visit kind %q must not be produced from entity_page_view", visitKind)
		}
	}
	for _, r := range reasons {
		if strings.Contains(r.PrimaryText, "去过") || strings.Contains(r.PrimaryText, "来过") {
			t.Fatalf("browsing-derived reason must not claim physical visit: %q", r.PrimaryText)
		}
	}
}

// TestIntersectionSource_SharedCircleDoesNotUsePersonNameAsCircleName：
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

// TestIntersectionSource_EntityObjectProducesFolloweeViewedObject 断言实体对象页
// 产出桥接型 followeeViewedObject（N位你关注的人也看过「具体对象名」）。
// P0 诚实红线：数据源是 entity_page_view，句子只能说「看过」，不能说「来过」。
func TestIntersectionSource_EntityObjectProducesFolloweeViewedObject(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	svc := newRealIntersectionService(t)

	reasons, err := svc.ObjectIntersections(context.Background(), ixViewer, ixEntity, "sight", 8)
	if err != nil {
		t.Fatalf("entity intersections: %v", err)
	}
	var hit *intersectionapp.IntersectionReasonView
	for i := range reasons {
		for _, p := range reasons[i].IntersectionPoints {
			if p.SourceRef == "followeeViewedObject" {
				hit = &reasons[i]
			}
		}
	}
	if hit == nil {
		t.Fatalf("missing followeeViewedObject reason for entity object")
	}
	if !strings.Contains(hit.PrimaryText, "1位你关注的人也看过「横竖影像馆取景地」") {
		t.Fatalf("followeeViewedObject primaryText off-dictionary: %q", hit.PrimaryText)
	}
	if strings.Contains(hit.PrimaryText, "来过") {
		t.Fatalf("browsing-derived bridge must not claim physical visit: %q", hit.PrimaryText)
	}
	if len(hit.IntersectionPoints) == 0 {
		t.Fatalf("followeeViewedObject points must be enumerable")
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
			"entityRefs":    []string{"circle_photo"},
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
		reasons, err := svc.ObjectIntersections(ctx, ixViewer, objectID, objectType, 32)
		if err != nil {
			t.Fatalf("object intersections %s: %v", objectID, err)
		}
		var hit *intersectionapp.IntersectionReasonView
		for i := range reasons {
			for _, p := range reasons[i].IntersectionPoints {
				if p.SourceRef == "followeeViewedObject" {
					hit = &reasons[i]
				}
			}
		}
		if hit == nil {
			t.Fatalf("missing followeeViewedObject for %s", objectID)
		}
		if !strings.Contains(hit.PrimaryText, wantName) {
			t.Fatalf("followeeViewedObject primaryText for %s = %q, want contain %q", objectID, hit.PrimaryText, wantName)
		}
		if hit.ActionType != "view_object" {
			t.Fatalf("followeeViewedObject actionType for %s = %q, want view_object", objectID, hit.ActionType)
		}
		if hit.ObjectKind != wantObjectKind {
			t.Fatalf("followeeViewedObject objectKind for %s = %q, want %q", objectID, hit.ObjectKind, wantObjectKind)
		}
		if len(hit.ActionHints) == 0 || hit.ActionHints[0].Target == nil {
			t.Fatalf("followeeViewedObject actionHints for %s must target object", objectID)
		}
		if got := hit.ActionHints[0].Target.ObjectID; got != objectID {
			t.Fatalf("followeeViewedObject target objectId for %s = %q", objectID, got)
		}
	}

	assertFolloweeVisitedReason("homepage_sight_west_lake", "homepage", "西湖景区", "place")
	assertFolloweeVisitedReason("circle_photo", "circle", "契约摄影社", "circle")
}

// stubSharedTagReader 是共享标签能力的对象级 typed double：
// 只替换跨服务读（tag-service），本进程内的交集计算仍走真实 Mongo 数据。
type stubSharedTagReader struct {
	tags  []sharedtags.SharedTag
	err   error
	calls int
}

func (r *stubSharedTagReader) SharedTags(
	_ context.Context,
	_ sharedtags.ObjectRef,
	_ sharedtags.ObjectRef,
	_ int,
) ([]sharedtags.SharedTag, error) {
	r.calls++
	if r.err != nil {
		return nil, r.err
	}
	return r.tags, nil
}

// identity 维度只能由共享职业标签产出「同行」：
// 兴趣偏好标签属 interest 维度，不得升格为身份事实；读不到时整点缺席而非造假。
func TestIntersectionSource_SameIndustryComesFromSharedOccupationTag(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	ctx := context.Background()

	newServiceWithTags := func(reader *stubSharedTagReader) *intersectionapp.IntersectionService {
		src := recinfra.NewMongoIntersectionSource(
			recinfra.NewMongoSocialGraphProvider(mongoDB), nil, nil,
			recinfra.WithSharedTagReader(reader),
		)
		return intersectionapp.NewIntersectionService(
			nil, intersectionapp.WithIntersectionSource(src),
		)
	}
	findPoint := func(svc *intersectionapp.IntersectionService, kind string) (intersectionapp.IntersectionPointView, string, bool) {
		t.Helper()
		reasons, err := svc.ObjectIntersections(ctx, ixViewer, ixObject, "user", 8)
		if err != nil {
			t.Fatalf("object intersections: %v", err)
		}
		for _, r := range reasons {
			for _, p := range r.IntersectionPoints {
				if p.SourceRef == kind {
					return p, r.PrimaryText, true
				}
			}
		}
		return intersectionapp.IntersectionPointView{}, "", false
	}

	reader := &stubSharedTagReader{tags: []sharedtags.SharedTag{
		{TagRef: "Audience/用户/职业/文化艺术/摄影师", Label: "摄影师", Strength: 0.9, Source: "tagRef"},
		{TagRef: "Audience/用户/兴趣偏好/旅行摄影/旅行", Label: "旅行", Strength: 1, Source: "tagRef"},
	}}
	point, _, ok := findPoint(newServiceWithTags(reader), "sameIndustry")
	if !ok {
		t.Fatalf("shared occupation tag must produce sameIndustry")
	}
	if point.Dimension != "identity" {
		t.Fatalf("sameIndustry must land on the identity axis, got %q", point.Dimension)
	}
	if point.SampleText != "摄影师" || point.DisplayText != "都是摄影师" {
		t.Fatalf("sameIndustry must name the shared occupation, got %+v", point)
	}
	if point.Count != 1 {
		t.Fatalf("only occupation tags may be counted as identity facts, got %d", point.Count)
	}
	if reader.calls == 0 {
		t.Fatalf("identity supply must be read from tag-service, not guessed")
	}

	// 只有兴趣标签时不得产出身份交集。
	interestOnly := &stubSharedTagReader{tags: []sharedtags.SharedTag{
		{TagRef: "Audience/用户/兴趣偏好/旅行摄影/旅行", Label: "旅行", Strength: 1, Source: "tagRef"},
	}}
	if _, _, leaked := findPoint(newServiceWithTags(interestOnly), "sameIndustry"); leaked {
		t.Fatalf("interest tags must not be promoted to an identity fact")
	}

	// tag-service 不可用时缺席，不得回退成「查过、没有共同职业」的假事实。
	unavailable := &stubSharedTagReader{err: context.DeadlineExceeded}
	if _, _, leaked := findPoint(newServiceWithTags(unavailable), "sameIndustry"); leaked {
		t.Fatalf("unavailable identity supply must not fabricate an intersection")
	}
	if unavailable.calls == 0 {
		t.Fatalf("unavailable case must still attempt the read")
	}
}

// 到访事实只能来自作者声明的 visitedAt：
//   - 双方都声明到访同一地点 → coVisitedEntity（都去过）
//   - 关注的人声明到访本地点 → followeeVisited（来过这里）
//
// 只浏览过对象页、或只把地点加进 wishlist，都不得升级成到访。
func TestIntersectionSource_DeclaredVisitsProduceVisitFacts(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	ctx := context.Background()
	posts := mongoDB.Collection("posts")
	relationships := mongoDB.Collection("persona_follow_projection")

	visitPost := func(authorID string, visitedAt time.Time) bson.M {
		return bson.M{
			"authorId":          authorID,
			"status":            "published",
			"visibility":        "public",
			"primaryHomepageId": "ixsrc_place_laojunshan",
			"geoTagRef":         "Geo/中国/河南省/洛阳市/栾川县",
			"locationName":      "老君山观景台",
			"visitedAt":         visitedAt,
			"publishedAt":       visitedAt,
			"updatedAt":         visitedAt,
		}
	}
	// viewer 与对象方各自声明过到访同一个地点（时间不同：同地不等于同期）。
	// 另有一位 viewer 关注的人也声明到访过该地点。
	if _, err := relationships.InsertOne(ctx, bson.M{
		"sourcePersonaId": ixViewer,
		"targetPersonaId": "ixsrc_visitor_c",
		"following":       true,
	}); err != nil {
		t.Fatalf("seed relationship projection: %v", err)
	}
	if _, err := posts.InsertMany(ctx, []any{
		visitPost(ixViewer, time.Date(2026, 4, 5, 8, 0, 0, 0, time.UTC)),
		visitPost(ixObject, time.Date(2025, 10, 1, 8, 0, 0, 0, time.UTC)),
		visitPost("ixsrc_visitor_c", time.Date(2026, 6, 20, 8, 0, 0, 0, time.UTC)),
		// 只想去、没到访：不得进入到访事实。
		bson.M{
			"authorId": ixObject, "status": "published", "visibility": "public",
			"authorDisplayNameSnapshot": "陆衡",
			"authorAvatarUrlSnapshot":   "https://static.quwoquan.test/ix-object.png",
			"primaryHomepageId":         "ixsrc_place_wishonly",
			"locationName":              "只被想去的地方",
			"updatedAt":                 time.Now(),
		},
	}); err != nil {
		t.Fatalf("seed declared visits: %v", err)
	}
	// 冷启动供给：到访池必须跨过区分度阈值（registry coldStartSupply
	// post_declared_visit），否则「都去过」在语料里人人成立，闸门会整类拦下。
	supplyDocs := make([]any, 0, 8)
	for i := 0; i < 8; i++ {
		supplyDocs = append(supplyDocs, bson.M{
			"authorId":          fmt.Sprintf("ixsrc_supply_author_%d", i),
			"status":            "published",
			"primaryHomepageId": fmt.Sprintf("ixsrc_place_supply_%d", i),
			"locationName":      fmt.Sprintf("语料地点%d", i),
			"visitedAt":         time.Date(2026, 1, 1+i, 8, 0, 0, 0, time.UTC),
			"updatedAt":         time.Now(),
		})
	}
	if _, err := posts.InsertMany(ctx, supplyDocs); err != nil {
		t.Fatalf("seed declared visit supply: %v", err)
	}

	src := recinfra.NewMongoIntersectionSource(
		recinfra.NewMongoSocialGraphProvider(mongoDB), nil, nil,
	)
	rawReasons, err := src.ObjectReasons(ctx, ixViewer, ixObject, "user")
	if err != nil {
		t.Fatalf("raw declared-visit reasons: %v", err)
	}
	svc := intersectionapp.NewIntersectionService(
		nil,
		intersectionapp.WithIntersectionSource(src),
	)
	findPoint := func(objectID, objectType, kind string) (intersectionapp.IntersectionReasonView, bool) {
		t.Helper()
		reasons, err := svc.ObjectIntersections(ctx, ixViewer, objectID, objectType, 32)
		if err != nil {
			t.Fatalf("object intersections %s: %v", objectID, err)
		}
		for _, r := range reasons {
			for _, p := range r.IntersectionPoints {
				if p.SourceRef == kind {
					return r, true
				}
			}
		}
		return intersectionapp.IntersectionReasonView{}, false
	}

	// ── 人页：你和 TA 都去过 ──
	visited, ok := findPoint(ixObject, "user", "coVisitedEntity")
	if !ok {
		t.Fatalf(
			"both declared visits must produce coVisitedEntity; raw=%v served=%v",
			reasonKinds(rawReasons),
			reasonKinds(mustObjectIntersections(t, svc, ctx, ixViewer, ixObject, "user", 32)),
		)
	}
	if visited.Dimension != "location" || visited.ObjectKind != "person" {
		t.Fatalf("coVisitedEntity must stay a location fact on the person surface: %+v", visited)
	}
	if !strings.Contains(visited.PrimaryText, "都去过") ||
		!strings.Contains(visited.PrimaryText, "老君山观景台") {
		t.Fatalf("coVisitedEntity must name the declared place, got %q", visited.PrimaryText)
	}
	// 只有一处共同到访：计数不得把「想去」的地点算进来。
	for _, p := range visited.IntersectionPoints {
		if p.SourceRef == "coVisitedEntity" && p.Count != 1 {
			t.Fatalf("visit count must only include declared visits, got %d", p.Count)
		}
	}

	// ── 地点页：你关注的人来过这里 ──
	followeeVisited, ok := findPoint("ixsrc_place_laojunshan", "homepage", "followeeVisited")
	if !ok {
		t.Fatalf("followee declared visit must produce followeeVisited")
	}
	if !strings.Contains(followeeVisited.PrimaryText, "来过") {
		t.Fatalf("followeeVisited must say 来过, got %q", followeeVisited.PrimaryText)
	}
	if len(followeeVisited.ActorEvidence) != 1 ||
		followeeVisited.ActorEvidence[0].ActorID != "ixsrc_visitor_c" {
		t.Fatalf("followeeVisited evidence must be enumerable: %+v", followeeVisited.ActorEvidence)
	}

	// ── 没有到访声明的地点不得出到访事实 ──
	if _, leaked := findPoint("ixsrc_place_wishonly", "homepage", "followeeVisited"); leaked {
		t.Fatalf("a place without any declared visit must not claim 来过")
	}
}

func mustObjectIntersections(
	t *testing.T,
	svc *intersectionapp.IntersectionService,
	ctx context.Context,
	viewerID string,
	objectID string,
	objectType string,
	limit int,
) []intersectionapp.IntersectionReasonView {
	t.Helper()
	reasons, err := svc.ObjectIntersections(ctx, viewerID, objectID, objectType, limit)
	if err != nil {
		t.Fatalf("object intersections %s: %v", objectID, err)
	}
	return reasons
}

func reasonKinds(reasons []intersectionapp.IntersectionReasonView) []string {
	out := make([]string, 0, len(reasons))
	for _, reason := range reasons {
		for _, point := range reason.IntersectionPoints {
			out = append(out, point.SourceRef)
		}
	}
	return out
}

// followeeInObject 只能由可证成员事实产出：圈子页看到「你关注的人在这里」，
// 地点/实体主页没有成员表，不得用浏览行为冒充「在这里」（那是 followeeViewedObject）。
func TestIntersectionSource_FolloweeInObjectRequiresProvableMembership(t *testing.T) {
	seedIntersectionSourceFixtures(t)
	ctx := context.Background()
	relationships := mongoDB.Collection("persona_follow_projection")
	members := mongoDB.Collection("circle_members")
	if _, err := relationships.InsertOne(ctx, bson.M{
		"sourcePersonaId": ixViewer,
		"targetPersonaId": "ixsrc_circle_friend",
		"following":       true,
	}); err != nil {
		t.Fatalf("seed relationship projection: %v", err)
	}
	if _, err := members.InsertOne(ctx, bson.M{
		"circleId": "ixsrc_circle_member_page",
		"userId":   "ixsrc_circle_friend",
	}); err != nil {
		t.Fatalf("seed circle membership: %v", err)
	}
	// 圈子展示名同样必须来自域内已投影的真实读模型：没有可证名字的容器对象
	// 不允许进入结论句（禁止用 circleId 当名字）。
	if _, err := mongoDB.Collection("rm_behavior_events").InsertOne(ctx, bson.M{
		"userId":      ixViewer,
		"action":      "entity_page_view",
		"entityRefs":  []string{"ixsrc_circle_member_page"},
		"displayName": "摄影胶片观察站",
		"createdAt":   time.Now(),
	}); err != nil {
		t.Fatalf("seed circle display projection: %v", err)
	}

	svc := newRealIntersectionService(t)
	findKind := func(objectID, objectType, kind string) *intersectionapp.IntersectionReasonView {
		t.Helper()
		reasons, err := svc.ObjectIntersections(ctx, ixViewer, objectID, objectType, 8)
		if err != nil {
			t.Fatalf("object intersections %s: %v", objectID, err)
		}
		for i := range reasons {
			for _, p := range reasons[i].IntersectionPoints {
				if p.SourceRef == kind {
					return &reasons[i]
				}
			}
		}
		return nil
	}

	hit := findKind("ixsrc_circle_member_page", "circle", "followeeInObject")
	if hit == nil {
		t.Fatalf("circle membership must produce followeeInObject")
	}
	if !strings.Contains(hit.PrimaryText, "顾南") {
		t.Fatalf("followeeInObject must name the real member, got %q", hit.PrimaryText)
	}
	if hit.ObjectKind != "circle" {
		t.Fatalf("followeeInObject objectKind = %q, want circle", hit.ObjectKind)
	}
	if len(hit.ActorEvidence) != 1 || hit.ActorEvidence[0].ActorID != "ixsrc_circle_friend" {
		t.Fatalf("followeeInObject actor evidence must be enumerable: %+v", hit.ActorEvidence)
	}

	// 实体主页只有浏览事实，没有成员事实：只能出 followeeViewedObject。
	if leaked := findKind(ixEntity, "homepage", "followeeInObject"); leaked != nil {
		t.Fatalf("entity homepage has no membership fact, must not claim followeeInObject: %+v", leaked)
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
