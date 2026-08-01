package recommendation

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
	generated "quwoquan_service/services/content-service/generated/content/post"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/sharedtags"
)

// SharedTagReader 读两个对象在 tag-service object_tag_index 上的共享标签，
// 是 identity 维度交集（同行/同校等）唯一的可证事实源。
//
// 读不到 ≠ 没有交集：读失败必须返回结构化错误，由调用方降级为「本次不产出该维度
// 交集点」，禁止把不可用伪装成空交集（§24.10 诚实红线 + Mock 隔离军规）。
type SharedTagReader interface {
	SharedTags(
		ctx context.Context,
		first sharedtags.ObjectRef,
		second sharedtags.ObjectRef,
		limit int,
	) ([]sharedtags.SharedTag, error)
}

type MongoIntersectionSource struct {
	social     *MongoSocialGraphProvider
	entityTags rtrec.EntityTagIndex
	candidates rtrec.SocialCandidateDB
	// sharedTags 为 nil 表示 identity 供给能力未装配（tag-service 不可达）：
	// 消费方跳过 identity 点，不得用空标签集合冒充「查过、没有交集」。
	sharedTags SharedTagReader

	supplyMu    sync.RWMutex
	supplyCache map[string]coldStartSupplySample
}

// MongoIntersectionSourceOption 是交集计算源的可选依赖装配项。
type MongoIntersectionSourceOption func(*MongoIntersectionSource)

// WithSharedTagReader 注入 identity 维度供给能力（tag-service 共享标签读）。
func WithSharedTagReader(reader SharedTagReader) MongoIntersectionSourceOption {
	return func(s *MongoIntersectionSource) {
		if reader != nil {
			s.sharedTags = reader
		}
	}
}

func NewMongoIntersectionSource(
	social *MongoSocialGraphProvider,
	entityTags rtrec.EntityTagIndex,
	candidates rtrec.SocialCandidateDB,
	options ...MongoIntersectionSourceOption,
) *MongoIntersectionSource {
	if entityTags == nil {
		entityTags = &rtrec.NullEntityTagIndex{}
	}
	if candidates == nil {
		candidates = &rtrec.NullSocialCandidateDB{}
	}
	source := &MongoIntersectionSource{
		social:      social,
		entityTags:  entityTags,
		candidates:  candidates,
		supplyCache: map[string]coldStartSupplySample{},
	}
	for _, option := range options {
		if option != nil {
			option(source)
		}
	}
	return source
}

func (s *MongoIntersectionSource) FactReasons(ctx context.Context, userID, channel string) ([]intersectionapp.IntersectionReasonView, error) {
	now := time.Now().UTC()
	reasons := make([]intersectionapp.IntersectionReasonView, 0, 3)

	if circleTags, err := s.socialCircleTags(ctx, userID); err == nil && len(circleTags) > 0 {
		reasons = append(reasons, buildTagReason(
			now,
			"interest",
			"circle_tags",
			"circleTag",
			"sharedTagSample",
			"view_object",
			circleTags,
			7*24*time.Hour,
		))
	}

	if friendTags, err := s.socialFriendTags(ctx, userID); err == nil && len(friendTags) > 0 {
		reasons = append(reasons, buildTagReason(
			now,
			"relationship",
			"friend_tags",
			"relationship",
			"followeeDiscussedThis",
			"view_object",
			friendTags,
			7*24*time.Hour,
		))
	}

	if contentReason, ok := s.friendContentReason(ctx, now, userID); ok {
		reasons = append(reasons, contentReason)
	}

	return reasons, nil
}

func (s *MongoIntersectionSource) AffinityReasons(ctx context.Context, userID, channel string) ([]intersectionapp.IntersectionReasonView, error) {
	now := time.Now().UTC()
	reasons := make([]intersectionapp.IntersectionReasonView, 0, 2)

	if circleIDs, err := s.social.GetUserCircleIDs(ctx, userID); err == nil && len(circleIDs) > 0 {
		candidates, err := s.candidates.GetCircleHotContent(ctx, circleIDs, 4, 7*24*time.Hour)
		if err == nil && len(candidates) > 0 {
			reasons = append(reasons, buildContentReason(
				now,
				"content",
				"circle_hot",
				"social_circle",
				"sharedCircle",
				"open_object",
				candidates,
				7*24*time.Hour,
				"affinity",
			))
		}
	}

	if friendContentReason, ok := s.friendContentReason(ctx, now, userID); ok {
		friendContentReason.IntersectionClass = "affinity"
		friendContentReason.Source = "social_friend"
		friendContentReason.ActionType = "open_object"
		reasons = append(reasons, friendContentReason)
	}

	return reasons, nil
}

func (s *MongoIntersectionSource) ObjectReasons(ctx context.Context, viewerID, objectID, objectType string) ([]intersectionapp.IntersectionReasonView, error) {
	now := time.Now().UTC()
	// objectType 由注册表收口到闭集 objectKind；不再按 objectId 子串反推类型。
	kind := objectKindForObjectType(objectType)
	dimension := objectDimension(objectType)
	objectTags, err := s.entityTags.GetEntityTags(ctx, objectID)
	if err != nil {
		objectTags = nil
	}

	reasons := make([]intersectionapp.IntersectionReasonView, 0, 3)
	if len(objectTags) > 0 {
		tagReason := buildTagReason(
			now,
			dimension,
			objectID+"_tags",
			"tagRef",
			"sharedTagSample",
			relationActionType(objectType),
			objectTags,
			30*24*time.Hour,
		)
		tagReason.RelationObjectID = objectID
		tagReason.ActionTargetID = objectID
		tagReason.ObjectKind = kind
		reasons = append(reasons, tagReason)
	}

	if relReason, ok := s.viewerRelationReason(ctx, now, viewerID, objectID, objectType); ok {
		reasons = append(reasons, relReason)
	}

	if kind == "person" {
		if wishReason, ok := s.coWishlistedEntityReason(ctx, now, viewerID, objectID); ok {
			reasons = append(reasons, wishReason)
		}
		// 到访事实（都去过）与意图事实（都想去）并列而不互斥：前者来自 visitedAt，
		// 后者来自 wishlist，语义正交，同时成立时两条都是真话。
		if visitedReason, ok := s.coVisitedEntityReason(ctx, now, viewerID, objectID); ok {
			reasons = append(reasons, visitedReason)
		}
	}

	if kind != "person" {
		if viewedReason, ok := s.followeeViewedObjectReason(ctx, now, viewerID, objectID, objectType); ok {
			reasons = append(reasons, viewedReason)
		}
		// 「来过这里」必须由声明到访支撑；只看过页面的走上面的 followeeViewedObject。
		if visitedReason, ok := s.followeeVisitedReason(ctx, now, viewerID, objectID, objectType); ok {
			reasons = append(reasons, visitedReason)
		}
	}

	// followeeInObject 需要可证的「在里面」成员事实，目前只有圈子有成员表；
	// 地点/实体主页没有成员关系，不得用浏览行为冒充「在这里」。
	if kind == "circle" {
		if inObjectReason, ok := s.followeeInObjectReason(ctx, now, viewerID, objectID, objectType); ok {
			reasons = append(reasons, inObjectReason)
		}
	}

	for i := range reasons {
		if reasons[i].ObjectKind == "" {
			reasons[i].ObjectKind = kind
		}
	}
	return reasons, nil
}

type wishlistEntityRef struct {
	EntityID    string
	ObjectType  string
	DisplayName string
}

func (s *MongoIntersectionSource) socialCircleTags(ctx context.Context, userID string) ([]string, error) {
	tags, err := s.social.GetUserCircleTags(ctx, userID)
	if err != nil || len(tags) == 0 {
		return nil, err
	}
	return topWeightKeys(tags, 3), nil
}

func (s *MongoIntersectionSource) socialFriendTags(ctx context.Context, userID string) ([]string, error) {
	tags, err := s.social.GetFriendInterestIntersection(ctx, userID)
	if err != nil || len(tags) == 0 {
		return nil, err
	}
	return topWeightKeys(tags, 3), nil
}

func (s *MongoIntersectionSource) friendContentReason(ctx context.Context, now time.Time, userID string) (intersectionapp.IntersectionReasonView, bool) {
	contentIDs, err := s.social.GetFriendInteractedContent(ctx, userID, 5)
	if err != nil || len(contentIDs) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	candidates, err := s.candidates.GetCandidatesByIDs(ctx, contentIDs)
	if err != nil || len(candidates) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	return buildContentReason(
		now,
		"content",
		"friend_content",
		"social_friend",
		"followeeViewing",
		"open_object",
		candidates,
		7*24*time.Hour,
		"fact",
	), true
}

// 真实数据源查询上限：限制单次交集计算扫描的边数，保证对象页拉取 P99 可控。
const (
	maxFolloweeScan      = 200
	maxBehaviorScan      = 300
	maxIntersectionPoint = 3
	maxSharedTagFetch    = 20
)

// followeeSet reads the relationship projection for targets currently followed
// by userID (bounded to protect page-fetch latency).
func (s *MongoIntersectionSource) followeeSet(ctx context.Context, userID string) map[string]struct{} {
	out := map[string]struct{}{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("persona_follow_projection").Find(ctx,
		bson.M{"sourcePersonaId": userID, "following": true}, mongoFindLimit(maxFolloweeScan))
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		var doc struct {
			TargetPersonaID string `bson:"targetPersonaId"`
		}
		if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.TargetPersonaID) != "" {
			out[doc.TargetPersonaID] = struct{}{}
		}
	}
	return out
}

// occupationTagPathPrefix 是用户档案职业标签在分类树中的唯一路径前缀。
// object_tag_index 只接收 `Audience/用户/职业/**` 与 `Audience/用户/兴趣偏好/**`
// 两支（tag-service user_profile_tag_consumer 强校验），identity 维度只能用职业支：
// 兴趣偏好属 interest 维度，混用会把兴趣相似说成身份相同。
const occupationTagPathPrefix = "Audience/用户/职业/"

// sharedOccupationLabel 是双方共享职业标签的展示名与共享条数。
type sharedOccupationLabel struct {
	label string
	count int
}

// sharedOccupationTag 读取双方共享的职业标签（identity 维度事实源）。
//
// 能力未装配或 tag-service 读失败时返回 false：这表示「本次问不到」，
// 不代表「没有交集」，因此调用方只是不产出该点，不写入任何替代事实。
func (s *MongoIntersectionSource) sharedOccupationTag(
	ctx context.Context,
	viewerID, objectID string,
) (sharedOccupationLabel, bool) {
	if s.sharedTags == nil ||
		strings.TrimSpace(viewerID) == "" ||
		strings.TrimSpace(objectID) == "" ||
		viewerID == objectID {
		return sharedOccupationLabel{}, false
	}
	tags, err := s.sharedTags.SharedTags(
		ctx,
		sharedtags.ObjectRef{ID: viewerID, Type: "user"},
		sharedtags.ObjectRef{ID: objectID, Type: "user"},
		maxSharedTagFetch,
	)
	if err != nil {
		return sharedOccupationLabel{}, false
	}
	best := sharedOccupationLabel{}
	strongest := 0.0
	for _, tag := range tags {
		if !strings.HasPrefix(tag.TagRef, occupationTagPathPrefix) {
			continue
		}
		label := strings.TrimSpace(tag.Label)
		if label == "" {
			label = occupationLabelFromTagRef(tag.TagRef)
		}
		if label == "" {
			continue
		}
		best.count++
		if best.label == "" || tag.Strength > strongest {
			best.label = label
			strongest = tag.Strength
		}
	}
	if best.label == "" {
		return sharedOccupationLabel{}, false
	}
	return best, true
}

// occupationLabelFromTagRef 取路径末级作为展示名（tag-service 未回填 label 时的兜底，
// 仍来自真实 tagRef，不造名）。
func occupationLabelFromTagRef(tagRef string) string {
	segments := strings.Split(strings.TrimSpace(tagRef), "/")
	if len(segments) == 0 {
		return ""
	}
	return strings.TrimSpace(segments[len(segments)-1])
}

// followerSet 读取关系投影里当前关注 userID 的第三方集合（粉丝方向）。
//
// 与 followeeSet 方向相反：followeeSet 问「TA 关注了谁」，followerSet 问「谁关注了 TA」。
// 两者求交分别对应 sharedFollowees（共同关注的人）与 commonFollower（共同粉丝）。
func (s *MongoIntersectionSource) followerSet(ctx context.Context, userID string) map[string]struct{} {
	out := map[string]struct{}{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("persona_follow_projection").Find(ctx,
		bson.M{"targetPersonaId": userID, "following": true}, mongoFindLimit(maxFolloweeScan))
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		var doc struct {
			SourcePersonaID string `bson:"sourcePersonaId"`
		}
		if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.SourcePersonaID) != "" {
			out[doc.SourcePersonaID] = struct{}{}
		}
	}
	return out
}

// behaviorRefs 读取 rm_behavior_events 中 userID 指定 action 的目标引用集合。
// useEntityRefs=true 时取 entityRefs（实体到访），否则取 contentId（内容互动）。
func (s *MongoIntersectionSource) behaviorRefs(ctx context.Context, userID, action string, useEntityRefs bool) map[string]struct{} {
	out := map[string]struct{}{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("rm_behavior_events").Find(ctx,
		bson.M{"userId": userID, "action": action}, mongoFindLimit(maxBehaviorScan))
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		var doc struct {
			ContentID  string   `bson:"contentId"`
			EntityRefs []string `bson:"entityRefs"`
		}
		if err := cur.Decode(&doc); err != nil {
			continue
		}
		if useEntityRefs {
			for _, ref := range doc.EntityRefs {
				if strings.TrimSpace(ref) != "" {
					out[ref] = struct{}{}
				}
			}
		} else if strings.TrimSpace(doc.ContentID) != "" {
			out[doc.ContentID] = struct{}{}
		}
	}
	return out
}

// wishlistRefs 读取稳定意图行为源 entity_wishlist_events：
// {userId, entityId, objectType, displayName, status, createdAt}。
// status 缺省或 active/wishlisted 视为有效；撤销/删除态不参与事实交集。
func (s *MongoIntersectionSource) wishlistRefs(ctx context.Context, userID string) map[string]wishlistEntityRef {
	out := map[string]wishlistEntityRef{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("entity_wishlist_events").Find(ctx,
		bson.M{
			"userId": userID,
			"$or": []bson.M{
				{"status": bson.M{"$exists": false}},
				{"status": ""},
				{"status": "active"},
				{"status": "wishlisted"},
			},
		},
		mongoFindLimit(maxBehaviorScan),
	)
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		var doc struct {
			EntityID    string `bson:"entityId"`
			ObjectType  string `bson:"objectType"`
			DisplayName string `bson:"displayName"`
		}
		if err := cur.Decode(&doc); err != nil {
			continue
		}
		entityID := strings.TrimSpace(doc.EntityID)
		if entityID == "" {
			continue
		}
		out[entityID] = wishlistEntityRef{
			EntityID:    entityID,
			ObjectType:  strings.TrimSpace(doc.ObjectType),
			DisplayName: strings.TrimSpace(doc.DisplayName),
		}
	}
	return out
}

func intersectWishlistRefs(a, b map[string]wishlistEntityRef) []wishlistEntityRef {
	out := make([]wishlistEntityRef, 0)
	for id, av := range a {
		bv, ok := b[id]
		if !ok {
			continue
		}
		next := av
		if next.DisplayName == "" {
			next.DisplayName = bv.DisplayName
		}
		if next.ObjectType == "" {
			next.ObjectType = bv.ObjectType
		}
		out = append(out, next)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].EntityID < out[j].EntityID })
	return out
}

// intersectKeys 返回两集合交集（排除 exclude 中的 key），结果排序保证幂等。
func intersectKeys(a, b map[string]struct{}, exclude ...string) []string {
	skip := map[string]struct{}{}
	for _, e := range exclude {
		skip[e] = struct{}{}
	}
	out := make([]string, 0)
	for k := range a {
		if _, ok := b[k]; !ok {
			continue
		}
		if _, ok := skip[k]; ok {
			continue
		}
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// coldStartSupplyTTL 是供给探针的缓存有效期。
//
// 语料供给是慢变量（新增 POI / 圈子是运营动作，不是逐请求变化），缓存既保证冷启动
// 闸门判定在同一时间窗内稳定，也避免每次对象页拉取都做一次 distinct 扫描。
const coldStartSupplyTTL = 5 * time.Minute

// maxColdStartSupplyScan 是供给探针单次 distinct 的扫描上限。
//
// 闸门只关心「供给是否已经跨过区分度阈值」，不需要精确总量；扫描上限保证语料变大后
// 探针成本恒定，不会随内容规模退化成全表统计。
const maxColdStartSupplyScan = 500

type coldStartSupplySample struct {
	count      int
	measuredAt time.Time
}

// DistinctObjectSupply 报告某供给口径在语料中的去重对象数（冷启动稀释闸门数据源）。
//
// supplyKey 取值来自注册表 coldStartSupply.supplyKeyByKind；未识别的 key 返回 error，
// 由服务端 fail-open 并记录降级指标，不静默当成「供给充足」或「供给为零」。
func (s *MongoIntersectionSource) DistinctObjectSupply(ctx context.Context, supplyKey string) (int, error) {
	supplyKey = strings.TrimSpace(supplyKey)
	if s.social == nil || s.social.db == nil {
		return 0, fmt.Errorf("intersection supply probe: mongo unavailable")
	}
	if cached, ok := s.cachedSupply(supplyKey); ok {
		return cached, nil
	}
	var (
		collection string
		field      string
		filter     bson.M
	)
	switch supplyKey {
	case "entity_page_view":
		collection, field = "rm_behavior_events", "entityRefs"
		filter = bson.M{"action": "entity_page_view"}
	case "entity_wishlist":
		collection, field = "entity_wishlist_events", "entityId"
		filter = bson.M{"$or": []bson.M{
			{"status": bson.M{"$exists": false}},
			{"status": ""},
			{"status": "active"},
			{"status": "wishlisted"},
		}}
	case "circle_membership":
		collection, field = "circle_members", "circleId"
		filter = bson.M{}
	case "post_declared_visit":
		// 到访供给按「被声明到访过的地点数」计量：只有作者自己声明了到访时间的
		// 带定位发布才计入（浏览、想去都不算），与 coVisitedEntity 的事实口径同源。
		collection, field = "posts", "primaryHomepageId"
		filter = declaredVisitFilter(nil)
	default:
		return 0, fmt.Errorf("intersection supply probe: unknown supplyKey %q", supplyKey)
	}

	cur, err := s.social.db.Collection(collection).Find(ctx, filter,
		mongoFindLimit(maxColdStartSupplyScan),
		mongoopts.Find().SetProjection(bson.M{field: 1}))
	if err != nil {
		return 0, err
	}
	defer cur.Close(ctx)
	distinct := map[string]struct{}{}
	for cur.Next(ctx) {
		raw, lookupErr := cur.Current.LookupErr(field)
		if lookupErr != nil {
			continue
		}
		if refs, ok := raw.ArrayOK(); ok {
			values, arrErr := refs.Values()
			if arrErr != nil {
				continue
			}
			for _, v := range values {
				if id, ok := v.StringValueOK(); ok && strings.TrimSpace(id) != "" {
					distinct[id] = struct{}{}
				}
			}
			continue
		}
		if id, ok := raw.StringValueOK(); ok && strings.TrimSpace(id) != "" {
			distinct[id] = struct{}{}
		}
	}
	if err := cur.Err(); err != nil {
		return 0, err
	}
	count := len(distinct)
	s.storeSupply(supplyKey, count)
	return count, nil
}

func (s *MongoIntersectionSource) cachedSupply(supplyKey string) (int, bool) {
	s.supplyMu.RLock()
	defer s.supplyMu.RUnlock()
	sample, ok := s.supplyCache[supplyKey]
	if !ok || time.Since(sample.measuredAt) > coldStartSupplyTTL {
		return 0, false
	}
	return sample.count, true
}

func (s *MongoIntersectionSource) storeSupply(supplyKey string, count int) {
	s.supplyMu.Lock()
	defer s.supplyMu.Unlock()
	if s.supplyCache == nil {
		s.supplyCache = map[string]coldStartSupplySample{}
	}
	s.supplyCache[supplyKey] = coldStartSupplySample{count: count, measuredAt: time.Now()}
}

// viewerRelationReason 产出 viewer↔object（人）之间的事实交集证据组：
// sharedFollowees（共同关注的人）/ sharedCircle（共同圈子）/
// coCommented（共同讨论）/ sharedEntityAttention（共同浏览过的实体）。
// 关注状态本身（互关/单向）不再作为交集点，由 relationKind 承载。
func (s *MongoIntersectionSource) viewerRelationReason(ctx context.Context, now time.Time, viewerID, objectID, objectType string) (intersectionapp.IntersectionReasonView, bool) {
	if s.social == nil || s.social.db == nil {
		return intersectionapp.IntersectionReasonView{}, false
	}
	relationshipColl := s.social.db.Collection("persona_follow_projection")
	var follow struct {
		SourcePersonaID string `bson:"sourcePersonaId"`
		TargetPersonaID string `bson:"targetPersonaId"`
	}
	viewerFollows := relationshipColl.FindOne(ctx, bson.M{"sourcePersonaId": viewerID, "targetPersonaId": objectID, "following": true}).Decode(&follow) == nil
	objectFollows := relationshipColl.FindOne(ctx, bson.M{"sourcePersonaId": objectID, "targetPersonaId": viewerID, "following": true}).Decode(&follow) == nil

	points := make([]intersectionapp.IntersectionPointView, 0, 4)

	// sharedFollowees：双方共同关注的第三方集合（排除彼此）。
	sharedFollowees := intersectKeys(
		s.followeeSet(ctx, viewerID), s.followeeSet(ctx, objectID), viewerID, objectID)
	if n := len(sharedFollowees); n > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_shared_followees",
			PointClass: "fact",
			Dimension:  "relationship",
			SourceRef:  "sharedFollowees",
			Visibility: "public",
			Count:      n,
			SampleText: strings.Join(headKeys(sharedFollowees, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
		})
	}

	// commonFollower：同时关注了你和 TA 的第三方（共同粉丝）。
	// 与 sharedFollowees 是同一条关系边的两个方向，不是同一事实的第二份表达：
	// 「你们都关注了谁」与「谁都关注了你们」在社交语义上不可互换。
	commonFollowers := intersectKeys(
		s.followerSet(ctx, viewerID), s.followerSet(ctx, objectID), viewerID, objectID)
	if n := len(commonFollowers); n > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_common_followers",
			PointClass: "fact",
			Dimension:  "relationship",
			SourceRef:  "commonFollower",
			Visibility: "public",
			Count:      n,
			SampleText: strings.Join(headKeys(commonFollowers, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
		})
	}

	// sharedCircle：共同圈子。
	if circleCount := s.sharedCircleCount(ctx, viewerID, objectID); circleCount > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_circle",
			PointClass: "fact",
			Dimension:  "relationship",
			SourceRef:  "sharedCircle",
			Visibility: "public",
			Count:      circleCount,
		})
	}

	// coCommented：双方都评论过的内容。
	coCommented := intersectKeys(
		s.behaviorRefs(ctx, viewerID, "comment", false),
		s.behaviorRefs(ctx, objectID, "comment", false))
	if n := len(coCommented); n > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_co_commented",
			PointClass: "fact",
			Dimension:  "content",
			SourceRef:  "coCommented",
			Visibility: "public",
			Count:      n,
			SampleText: strings.Join(headKeys(coCommented, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
		})
	}

	// sameIndustry：双方都声明过同一职业标签（identity 维度唯一可证口径）。
	// 只到「同行」为止：职业标签没有组织实例，说不出同公司/同团队。
	if occupation, ok := s.sharedOccupationTag(ctx, viewerID, objectID); ok {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_same_industry",
			PointClass: "fact",
			Dimension:  "identity",
			SourceRef:  "sameIndustry",
			Visibility: "public",
			Count:      occupation.count,
			SampleText: occupation.label,
		})
	}

	// coSharedContent：双方都转发过的内容（share 行为求交）。
	coShared := intersectKeys(
		s.behaviorRefs(ctx, viewerID, "share", false),
		s.behaviorRefs(ctx, objectID, "share", false))
	if n := len(coShared); n > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_co_shared",
			PointClass: "fact",
			Dimension:  "content",
			SourceRef:  "coSharedContent",
			Visibility: "public",
			Count:      n,
			SampleText: strings.Join(headKeys(coShared, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
		})
	}

	// coLiked：双方都点赞过的内容（like 行为求交）。价值层最低（T4），
	// 只做次级证据：点赞成本低，单独成句说服力不足，靠 evidenceRank 排在后面。
	coLiked := intersectKeys(
		s.behaviorRefs(ctx, viewerID, "like", false),
		s.behaviorRefs(ctx, objectID, "like", false))
	if n := len(coLiked); n > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_co_liked",
			PointClass: "fact",
			Dimension:  "content",
			SourceRef:  "coLiked",
			Visibility: "public",
			Count:      n,
			SampleText: strings.Join(headKeys(coLiked, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
		})
	}

	// sharedEntityAttention：双方都浏览过的实体（实体页浏览行为的 entityRefs 交集）。
	// entity_page_view 只能证明「共同关注同一对象」，不能证明物理到访；到访事实需要
	// 带定位发布 / 显式打卡 / 行程回执进入 coVisitedEntity 的可证到访生产链。
	coAttended := intersectKeys(
		s.behaviorRefs(ctx, viewerID, "entity_page_view", true),
		s.behaviorRefs(ctx, objectID, "entity_page_view", true))
	if n := len(coAttended); n > 0 {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:    objectID + "_shared_entity_attention",
			PointClass: "fact",
			Dimension:  "interest",
			SourceRef:  "sharedEntityAttention",
			Visibility: "public",
			Count:      n,
			SampleText: strings.Join(headKeys(coAttended, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
		})
	}

	if len(points) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	relationKind := "mutual"
	if !viewerFollows && objectFollows {
		relationKind = "followed_by"
	} else if viewerFollows && !objectFollows {
		relationKind = "following"
	} else if !viewerFollows && !objectFollows {
		relationKind = "none"
	}
	// T3 空窗治理：人级 reason 回填对方真实展示资料，避免 spotlight 空头像。
	displayName, avatarURL := s.userDisplayProfile(ctx, objectID)
	if displayName == "" {
		displayName = objectLabel(objectType)
	}
	return intersectionapp.IntersectionReasonView{
		IntersectionID:     objectID + "_relationship",
		IntersectionClass:  "fact",
		Kind:               points[0].SourceRef,
		Dimension:          "relationship",
		DisplayName:        displayName,
		AvatarURL:          avatarURL,
		Strength:           scoreFromCount(len(points), 4),
		ConfidenceLabel:    "",
		RelationKind:       relationKind,
		RelationObjectID:   objectID,
		ActionType:         relationActionType(objectType),
		ActionTargetID:     objectID,
		Source:             "relationship",
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(7 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     len(points),
		TotalPointCount:    len(points),
		ObjectKind:         objectKindForObjectType(objectType),
	}, true
}

// coWishlistedEntityReason 是 C0「共同想去 → 发起结伴」最薄事实闭环。
// 真相源为 entity_wishlist_events，只有 viewer 与目标 person 都存在相同 entityId 的有效
// wishlist 事件时才产出；不从内容 fixture 或端侧文案反推，避免把规划口径伪装成事实。
func (s *MongoIntersectionSource) coWishlistedEntityReason(ctx context.Context, now time.Time, viewerID, objectID string) (intersectionapp.IntersectionReasonView, bool) {
	shared := intersectWishlistRefs(
		s.wishlistRefs(ctx, viewerID),
		s.wishlistRefs(ctx, objectID),
	)
	if len(shared) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	head := shared[0]
	entityName := strings.TrimSpace(head.DisplayName)
	if entityName == "" {
		entityName = head.EntityID
	}
	objectKind := objectKindForObjectType(head.ObjectType)
	if objectKind == "" || objectKind == "person" {
		objectKind = "place"
	}
	displayName, avatarURL := s.userDisplayProfile(ctx, objectID)
	if displayName == "" {
		displayName = objectID
	}
	points := []intersectionapp.IntersectionPointView{{
		PointID:    objectID + "_wishlisted_" + head.EntityID,
		PointClass: "fact",
		Dimension:  "location",
		SourceRef:  "coWishlistedEntity",
		Visibility: "public",
		Count:      len(shared),
		SampleText: strings.Join(wishlistSampleNames(shared, maxIntersectionPoint), generated.IntersectionListSeparator.Text),
	}}
	_ = objectKind
	// SVO 对象页合同（host_plain）：reason 对象必须是宿主 person（「你和 TA 都想去 X」
	// 的关系主体是 TA），否则整条被 reasonTarget!=host 校验淘汰；entity 是证据与
	// point 承载（SampleText=想去地名），约伴行动承接对象也是 person（dispatch=gathering
	// 复用建群，M0.7），故 ActionTargetID/RelationObjectID 归 person。
	return intersectionapp.IntersectionReasonView{
		IntersectionID:     objectID + "_co_wishlisted_entity",
		IntersectionClass:  "fact",
		Kind:               "coWishlistedEntity",
		Vertical:           "travel_photography",
		Dimension:          "location",
		DisplayName:        displayName,
		AvatarURL:          avatarURL,
		Strength:           scoreFromCount(len(shared), 4),
		ConfidenceLabel:    "",
		RelationKind:       "shared_intent",
		RelationObjectID:   objectID,
		ActionType:         "start_gathering",
		ActionTargetID:     objectID,
		Source:             "coWishlistedEntity",
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(14 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     1,
		TotalPointCount:    1,
		ObjectKind:         "person",
	}, true
}

// declaredVisit 是一条「作者自己声明的到访事实」：某人在某个地点、某个时间到访过。
//
// 真相源是 posts 上作者主动填写的 visitedAt（发布时可选，见 content/post fields.yaml），
// 与浏览（entity_page_view）、想去（entity_wishlist_events）三者互不替代：
// 浏览只证明看过、想去只证明意图，只有 visitedAt 是到访事实，因此只有它能说「都去过」。
type declaredVisit struct {
	// placeKey 是地点同一性判据：优先实体主页 ID（精确到 POI），
	// 退化到行政区 tagRef（只能说到区域，不能说到具体地点）。
	placeKey string
	// placeName 是可展示地名（作者填写的 locationName 或实体主页展示名）；
	// 无可证地名时该到访不进结论句，禁止用 ID 冒充地名。
	placeName string
	// entityID 非空表示地点是可导航的实体主页对象。
	entityID  string
	visitedAt time.Time
}

// declaredVisitFilter 是「已声明到访」的公共查询条件。
// extra 用于叠加作者或地点约束；nil 表示只要到访事实本身（供给探针口径）。
func declaredVisitFilter(extra bson.M) bson.M {
	filter := bson.M{
		"status":    "published",
		"visitedAt": bson.M{"$exists": true, "$ne": nil},
		"$or": []bson.M{
			{"primaryHomepageId": bson.M{"$nin": []any{nil, ""}}},
			{"geoTagRef": bson.M{"$nin": []any{nil, ""}}},
		},
	}
	for k, v := range extra {
		filter[k] = v
	}
	return filter
}

// declaredVisits 读取某人声明过到访的地点集合（同一地点保留最近一次到访）。
func (s *MongoIntersectionSource) declaredVisits(
	ctx context.Context,
	userID string,
) map[string]declaredVisit {
	out := map[string]declaredVisit{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("posts").Find(ctx,
		declaredVisitFilter(bson.M{"authorId": userID}),
		mongoFindLimit(maxBehaviorScan),
	)
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		visit, ok := decodeDeclaredVisit(cur)
		if !ok {
			continue
		}
		if prev, exists := out[visit.placeKey]; exists {
			if visit.visitedAt.Before(prev.visitedAt) {
				continue
			}
			if visit.placeName == "" {
				visit.placeName = prev.placeName
			}
			if visit.entityID == "" {
				visit.entityID = prev.entityID
			}
		}
		out[visit.placeKey] = visit
	}
	return out
}

type declaredVisitCursor interface {
	Decode(any) error
}

func decodeDeclaredVisit(cur declaredVisitCursor) (declaredVisit, bool) {
	var doc struct {
		PrimaryHomepageID string    `bson:"primaryHomepageId"`
		GeoTagRef         string    `bson:"geoTagRef"`
		LocationName      string    `bson:"locationName"`
		PrimaryHomepage   string    `bson:"primaryHomepageSnapshot"`
		VisitedAt         time.Time `bson:"visitedAt"`
	}
	if err := cur.Decode(&doc); err != nil {
		return declaredVisit{}, false
	}
	if doc.VisitedAt.IsZero() {
		return declaredVisit{}, false
	}
	entityID := strings.TrimSpace(doc.PrimaryHomepageID)
	placeName := strings.TrimSpace(doc.LocationName)
	visit := declaredVisit{
		placeName: placeName,
		entityID:  entityID,
		visitedAt: doc.VisitedAt.UTC(),
	}
	switch {
	case entityID != "":
		// 精确到实体主页：可导航、可说具体地名。
		visit.placeKey = "homepage:" + entityID
	case strings.TrimSpace(doc.GeoTagRef) != "":
		// 只有行政区：地点同一性只到区域级，不得声称同一个具体地点。
		visit.placeKey = "region:" + strings.TrimSpace(doc.GeoTagRef)
	default:
		return declaredVisit{}, false
	}
	if visit.placeName == "" {
		return declaredVisit{}, false
	}
	return visit, true
}

// intersectDeclaredVisits 取双方共同声明到访的地点，按到访时间就近排序（近的在前）。
func intersectDeclaredVisits(a, b map[string]declaredVisit) []declaredVisit {
	out := make([]declaredVisit, 0)
	for key, mine := range a {
		theirs, ok := b[key]
		if !ok {
			continue
		}
		shared := mine
		if shared.placeName == "" {
			shared.placeName = theirs.placeName
		}
		if shared.entityID == "" {
			shared.entityID = theirs.entityID
		}
		// 双方到访时间取较近的一次，作为该地点交集的保鲜时间。
		if theirs.visitedAt.After(shared.visitedAt) {
			shared.visitedAt = theirs.visitedAt
		}
		out = append(out, shared)
	}
	sort.Slice(out, func(i, j int) bool {
		if !out[i].visitedAt.Equal(out[j].visitedAt) {
			return out[i].visitedAt.After(out[j].visitedAt)
		}
		return out[i].placeKey < out[j].placeKey
	})
	return out
}

// coVisitedEntityReason 事实型交集：你和 TA 都声明过到访同一个地点。
//
// 只用作者声明的 visitedAt 到访事实，不用浏览（那是 sharedEntityAttention）也不用
// 想去（那是 coWishlistedEntity）。句子不带时间断言：同地不等于同期，「同期」需要
// 双方到访时间落在同一窗口才能说，当前只承诺「都去过」。
func (s *MongoIntersectionSource) coVisitedEntityReason(
	ctx context.Context,
	now time.Time,
	viewerID, objectID string,
) (intersectionapp.IntersectionReasonView, bool) {
	if strings.TrimSpace(viewerID) == "" ||
		strings.TrimSpace(objectID) == "" ||
		viewerID == objectID {
		return intersectionapp.IntersectionReasonView{}, false
	}
	shared := intersectDeclaredVisits(
		s.declaredVisits(ctx, viewerID),
		s.declaredVisits(ctx, objectID),
	)
	if len(shared) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	head := shared[0]
	displayName, avatarURL := s.userDisplayProfile(ctx, objectID)
	if displayName == "" {
		// 无可证展示资料的人不进人级结论句（与其它 person reason 一致）。
		return intersectionapp.IntersectionReasonView{}, false
	}
	sampleNames := make([]string, 0, maxIntersectionPoint)
	for _, visit := range shared {
		if len(sampleNames) >= maxIntersectionPoint {
			break
		}
		sampleNames = append(sampleNames, visit.placeName)
	}
	points := []intersectionapp.IntersectionPointView{{
		PointID:    objectID + "_co_visited_" + head.placeKey,
		PointClass: "fact",
		Dimension:  "location",
		SourceRef:  "coVisitedEntity",
		Visibility: "public",
		Count:      len(shared),
		SampleText: strings.Join(sampleNames, generated.IntersectionListSeparator.Text),
	}}
	return intersectionapp.IntersectionReasonView{
		IntersectionID:     objectID + "_co_visited_entity",
		IntersectionClass:  "fact",
		Kind:               "coVisitedEntity",
		Vertical:           "travel_photography",
		Dimension:          "location",
		DisplayName:        displayName,
		AvatarURL:          avatarURL,
		Strength:           scoreFromCount(len(shared), 4),
		RelationKind:       "shared_fact",
		RelationObjectID:   objectID,
		ActionType:         relationActionType("user"),
		ActionTargetID:     objectID,
		Source:             "coVisitedEntity",
		FreshAt:            head.visitedAt.Format(time.RFC3339),
		ExpiresAt:          now.Add(180 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     1,
		TotalPointCount:    1,
		ObjectKind:         "person",
	}, true
}

// followeeVisitedReason 桥接型交集：你关注的人里有谁声明过到访这个地点。
//
// 与 followeeViewedObject 的差别是事实等级：那条只证明看过对象页，这条证明本人声明到访。
// 因此这条可以说「来过」，那条只能说「也看过」。
func (s *MongoIntersectionSource) followeeVisitedReason(
	ctx context.Context,
	now time.Time,
	viewerID, objectID, objectType string,
) (intersectionapp.IntersectionReasonView, bool) {
	if s.social == nil || s.social.db == nil ||
		strings.TrimSpace(viewerID) == "" ||
		strings.TrimSpace(objectID) == "" {
		return intersectionapp.IntersectionReasonView{}, false
	}
	followees := s.followeeSet(ctx, viewerID)
	if len(followees) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	followeeIDs := make([]string, 0, len(followees))
	for id := range followees {
		followeeIDs = append(followeeIDs, id)
	}
	cur, err := s.social.db.Collection("posts").Find(ctx,
		declaredVisitFilter(bson.M{
			"authorId": bson.M{"$in": followeeIDs},
			"$and": []bson.M{{"$or": []bson.M{
				{"primaryHomepageId": objectID},
				{"geoTagRef": objectID},
			}}},
		}),
		mongoFindLimit(maxFolloweeScan),
	)
	if err != nil {
		return intersectionapp.IntersectionReasonView{}, false
	}
	defer cur.Close(ctx)
	type visitorFact struct {
		visitedAt time.Time
		placeName string
	}
	visitors := map[string]visitorFact{}
	for cur.Next(ctx) {
		var doc struct {
			AuthorID     string    `bson:"authorId"`
			LocationName string    `bson:"locationName"`
			VisitedAt    time.Time `bson:"visitedAt"`
		}
		if err := cur.Decode(&doc); err != nil {
			continue
		}
		authorID := strings.TrimSpace(doc.AuthorID)
		if authorID == "" || doc.VisitedAt.IsZero() {
			continue
		}
		if prev, ok := visitors[authorID]; ok && prev.visitedAt.After(doc.VisitedAt) {
			continue
		}
		visitors[authorID] = visitorFact{
			visitedAt: doc.VisitedAt.UTC(),
			placeName: strings.TrimSpace(doc.LocationName),
		}
	}
	if len(visitors) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	visitorIDs := make([]string, 0, len(visitors))
	for id := range visitors {
		visitorIDs = append(visitorIDs, id)
	}
	sort.Strings(visitorIDs)

	actorEvidence := make([]intersectionapp.IntersectionActorEvidenceView, 0, len(visitorIDs))
	sampleNames := make([]string, 0, maxIntersectionPoint)
	latestVisit := time.Time{}
	for _, visitorID := range visitorIDs {
		personName, avatarURL := s.userDisplayProfile(ctx, visitorID)
		if personName == "" {
			continue
		}
		fact := visitors[visitorID]
		if fact.visitedAt.After(latestVisit) {
			latestVisit = fact.visitedAt
		}
		if len(sampleNames) < maxIntersectionPoint {
			sampleNames = append(sampleNames, personName)
		}
		actorEvidence = append(actorEvidence, intersectionapp.IntersectionActorEvidenceView{
			ActorID:      visitorID,
			DisplayName:  personName,
			AvatarURL:    avatarURL,
			SourceRef:    "followeeVisited",
			PrivacyState: "visible",
			Target: &intersectionapp.IntersectionTargetView{
				ObjectType: "user",
				ObjectID:   visitorID,
				ObjectKind: "person",
				RouteID:    "userProfile",
			},
		})
	}
	if len(actorEvidence) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	placeName := s.objectDisplayName(ctx, objectID, objectType)
	if placeName == "" {
		// 作者填写的地名是域内可证的第二来源。
		for _, id := range visitorIDs {
			if name := visitors[id].placeName; name != "" {
				placeName = name
				break
			}
		}
	}
	if placeName == "" {
		return intersectionapp.IntersectionReasonView{}, false
	}
	n := len(actorEvidence)
	points := []intersectionapp.IntersectionPointView{{
		PointID:    objectID + "_followee_visited",
		PointClass: "fact",
		Dimension:  "location",
		SourceRef:  "followeeVisited",
		Visibility: "public",
		Count:      n,
		SampleText: strings.Join(sampleNames, generated.IntersectionListSeparator.Text),
	}}
	if latestVisit.IsZero() {
		latestVisit = now
	}
	return intersectionapp.IntersectionReasonView{
		IntersectionID:            objectID + "_followee_visited",
		IntersectionClass:         "fact",
		Kind:                      "followeeVisited",
		Vertical:                  "travel_photography",
		Dimension:                 "location",
		DisplayName:               placeName,
		Strength:                  scoreFromCount(n, 4),
		RelationKind:              "bridge",
		RelationObjectID:          objectID,
		ActionType:                relationActionType(objectType),
		ActionTargetID:            objectID,
		Source:                    "followeeVisited",
		FreshAt:                   latestVisit.Format(time.RFC3339),
		ExpiresAt:                 now.Add(180 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints:        points,
		FactPointCount:            1,
		TotalPointCount:           1,
		ActorEvidenceTotalCount:   len(actorEvidence),
		ActorEvidenceCompleteness: "complete",
		ActorEvidence:             actorEvidence,
		ObjectKind:                objectKindForObjectType(objectType),
	}, true
}

func wishlistSampleNames(refs []wishlistEntityRef, limit int) []string {
	if limit <= 0 || limit > len(refs) {
		limit = len(refs)
	}
	out := make([]string, 0, limit)
	for _, ref := range refs[:limit] {
		name := strings.TrimSpace(ref.DisplayName)
		if name == "" {
			name = strings.TrimSpace(ref.EntityID)
		}
		if name != "" {
			out = append(out, name)
		}
	}
	return out
}

// followeeViewedObjectReason 桥接型交集：viewer 关注的人里有谁浏览过该对象（实体/地点页）。
// 数据源 rm_behavior_events{action:entity_page_view} 只证明浏览，不证明到访；
// 物理到访由 followeeVisited 承载，只接受可证到访源。
func (s *MongoIntersectionSource) followeeViewedObjectReason(ctx context.Context, now time.Time, viewerID, objectID, objectType string) (intersectionapp.IntersectionReasonView, bool) {
	if s.social == nil || s.social.db == nil || strings.TrimSpace(viewerID) == "" {
		return intersectionapp.IntersectionReasonView{}, false
	}
	followees := s.followeeSet(ctx, viewerID)
	if len(followees) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	followeeIDs := make([]string, 0, len(followees))
	for id := range followees {
		followeeIDs = append(followeeIDs, id)
	}
	cur, err := s.social.db.Collection("rm_behavior_events").Find(ctx, bson.M{
		"userId":     bson.M{"$in": followeeIDs},
		"action":     "entity_page_view",
		"entityRefs": objectID,
	}, mongoFindLimit(maxBehaviorScan))
	if err != nil {
		return intersectionapp.IntersectionReasonView{}, false
	}
	defer cur.Close(ctx)
	visitors := map[string]struct{}{}
	for cur.Next(ctx) {
		var doc struct {
			UserID string `bson:"userId"`
		}
		if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.UserID) != "" {
			visitors[doc.UserID] = struct{}{}
		}
	}
	if len(visitors) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	visitorIDs := make([]string, 0, len(visitors))
	for id := range visitors {
		visitorIDs = append(visitorIDs, id)
	}
	sort.Strings(visitorIDs)
	actorEvidence := make([]intersectionapp.IntersectionActorEvidenceView, 0, len(visitorIDs))
	sampleNames := make([]string, 0, maxIntersectionPoint)
	for _, visitorID := range visitorIDs {
		displayName, avatarURL := s.userDisplayProfile(ctx, visitorID)
		if displayName == "" {
			// 事实展示必须有可解释的真实用户资料；禁止用 userId 猜展示名。
			continue
		}
		if len(sampleNames) < maxIntersectionPoint {
			sampleNames = append(sampleNames, displayName)
		}
		actorEvidence = append(actorEvidence, intersectionapp.IntersectionActorEvidenceView{
			ActorID:      visitorID,
			DisplayName:  displayName,
			AvatarURL:    avatarURL,
			SourceRef:    "followeeViewedObject",
			PrivacyState: "visible",
			Target: &intersectionapp.IntersectionTargetView{
				ObjectType: "user",
				ObjectID:   visitorID,
				ObjectKind: "person",
				RouteID:    "userProfile",
			},
		})
	}
	if len(actorEvidence) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	n := len(actorEvidence)
	// R-ID01：桥接型统一为单聚合点 Count=n（取代 reason 级 SharedCount），
	// 端/Explain 经 anchor.Count 取数；样本走 SampleText（前 maxIntersectionPoint 个访客）。
	points := []intersectionapp.IntersectionPointView{{
		PointID:    objectID + "_followee_viewed_object",
		PointClass: "fact",
		Dimension:  "relationship",
		SourceRef:  "followeeViewedObject",
		Visibility: "public",
		Count:      n,
		SampleText: strings.Join(sampleNames, generated.IntersectionListSeparator.Text),
	}}
	displayName := s.objectDisplayName(ctx, objectID, objectType)
	return intersectionapp.IntersectionReasonView{
		IntersectionID:            objectID + "_followee_viewed_object",
		IntersectionClass:         "fact",
		Kind:                      "followeeViewedObject",
		Dimension:                 "relationship",
		DisplayName:               displayName,
		Strength:                  scoreFromCount(n, 4),
		RelationKind:              "bridge",
		RelationObjectID:          objectID,
		ActionType:                relationActionType(objectType),
		ActionTargetID:            objectID,
		Source:                    "relationship",
		FreshAt:                   now.Format(time.RFC3339),
		ExpiresAt:                 now.Add(7 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints:        points,
		FactPointCount:            1,
		TotalPointCount:           1,
		ActorEvidenceTotalCount:   len(actorEvidence),
		ActorEvidenceCompleteness: "complete",
		ActorEvidence:             actorEvidence,
		ObjectKind:                objectKindForObjectType(objectType),
	}, true
}

// followeeInObjectReason 桥接型交集：viewer 关注的人里有谁已经在这个圈子里。
//
// 真相源是 circle_members 成员事实（不是浏览、不是推荐）：成员关系可证、可撤销，
// 且与 followeeViewedObject（只证明看过）语义正交，二者可同时出现而不重复表达。
func (s *MongoIntersectionSource) followeeInObjectReason(
	ctx context.Context,
	now time.Time,
	viewerID, objectID, objectType string,
) (intersectionapp.IntersectionReasonView, bool) {
	if s.social == nil || s.social.db == nil || strings.TrimSpace(viewerID) == "" {
		return intersectionapp.IntersectionReasonView{}, false
	}
	if strings.TrimSpace(objectID) == "" {
		return intersectionapp.IntersectionReasonView{}, false
	}
	followees := s.followeeSet(ctx, viewerID)
	if len(followees) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	followeeIDs := make([]string, 0, len(followees))
	for id := range followees {
		followeeIDs = append(followeeIDs, id)
	}
	cur, err := s.social.db.Collection("circle_members").Find(ctx, bson.M{
		"circleId": objectID,
		"userId":   bson.M{"$in": followeeIDs},
	}, mongoFindLimit(maxFolloweeScan))
	if err != nil {
		return intersectionapp.IntersectionReasonView{}, false
	}
	defer cur.Close(ctx)
	members := map[string]struct{}{}
	for cur.Next(ctx) {
		var doc struct {
			UserID string `bson:"userId"`
		}
		if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.UserID) != "" {
			members[doc.UserID] = struct{}{}
		}
	}
	if len(members) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	memberIDs := make([]string, 0, len(members))
	for id := range members {
		memberIDs = append(memberIDs, id)
	}
	sort.Strings(memberIDs)
	actorEvidence := make([]intersectionapp.IntersectionActorEvidenceView, 0, len(memberIDs))
	sampleNames := make([]string, 0, maxIntersectionPoint)
	for _, memberID := range memberIDs {
		displayName, avatarURL := s.userDisplayProfile(ctx, memberID)
		if displayName == "" {
			// 无可证展示资料的成员不进事实句：禁止用 userId 猜展示名。
			continue
		}
		if len(sampleNames) < maxIntersectionPoint {
			sampleNames = append(sampleNames, displayName)
		}
		actorEvidence = append(actorEvidence, intersectionapp.IntersectionActorEvidenceView{
			ActorID:      memberID,
			DisplayName:  displayName,
			AvatarURL:    avatarURL,
			SourceRef:    "followeeInObject",
			PrivacyState: "visible",
			Target: &intersectionapp.IntersectionTargetView{
				ObjectType: "user",
				ObjectID:   memberID,
				ObjectKind: "person",
				RouteID:    "userProfile",
			},
		})
	}
	if len(actorEvidence) == 0 {
		return intersectionapp.IntersectionReasonView{}, false
	}
	n := len(actorEvidence)
	points := []intersectionapp.IntersectionPointView{{
		PointID:    objectID + "_followee_in_object",
		PointClass: "fact",
		Dimension:  "relationship",
		SourceRef:  "followeeInObject",
		Visibility: "public",
		Count:      n,
		SampleText: strings.Join(sampleNames, generated.IntersectionListSeparator.Text),
	}}
	return intersectionapp.IntersectionReasonView{
		IntersectionID:            objectID + "_followee_in_object",
		IntersectionClass:         "fact",
		Kind:                      "followeeInObject",
		Dimension:                 "relationship",
		DisplayName:               s.objectDisplayName(ctx, objectID, objectType),
		Strength:                  scoreFromCount(n, 4),
		RelationKind:              "bridge",
		RelationObjectID:          objectID,
		ActionType:                relationActionType(objectType),
		ActionTargetID:            objectID,
		Source:                    "relationship",
		FreshAt:                   now.Format(time.RFC3339),
		ExpiresAt:                 now.Add(30 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints:        points,
		FactPointCount:            1,
		TotalPointCount:           1,
		ActorEvidenceTotalCount:   len(actorEvidence),
		ActorEvidenceCompleteness: "complete",
		ActorEvidence:             actorEvidence,
		ObjectKind:                objectKindForObjectType(objectType),
	}, true
}

func (s *MongoIntersectionSource) objectDisplayName(ctx context.Context, objectID, objectType string) string {
	if s.social != nil && s.social.db != nil && strings.TrimSpace(objectID) != "" {
		var doc struct {
			DisplayName string `bson:"displayName"`
		}
		err := s.social.db.Collection("rm_behavior_events").FindOne(
			ctx,
			bson.M{
				"action":     "entity_page_view",
				"entityRefs": objectID,
				"displayName": bson.M{
					"$exists": true,
					"$ne":     "",
				},
			},
			mongoopts.FindOne().SetSort(bson.M{"createdAt": -1}),
		).Decode(&doc)
		if err == nil && strings.TrimSpace(doc.DisplayName) != "" {
			return strings.TrimSpace(doc.DisplayName)
		}
	}
	return concreteObjectDisplayName(objectID, objectType)
}

// userDisplayProfile 从 posts 集合的作者快照回填用户展示资料（T3 空窗治理：
// content-service 域内唯一的用户展示读模型；无发布内容的用户回退空，由
// 候选窗完备性过滤兜底，不下发空头像的人级 reason 进 spotlight）。
func (s *MongoIntersectionSource) userDisplayProfile(ctx context.Context, userID string) (displayName, avatarURL string) {
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return "", ""
	}
	var doc struct {
		AuthorDisplayNameSnapshot string `bson:"authorDisplayNameSnapshot"`
		AuthorAvatarUrlSnapshot   string `bson:"authorAvatarUrlSnapshot"`
	}
	err := s.social.db.Collection("posts").FindOne(ctx,
		bson.M{"authorId": userID, "status": "published"},
		mongoopts.FindOne().SetSort(bson.M{"updatedAt": -1}),
	).Decode(&doc)
	if err != nil {
		return "", ""
	}
	return strings.TrimSpace(doc.AuthorDisplayNameSnapshot), strings.TrimSpace(doc.AuthorAvatarUrlSnapshot)
}

// headKeys 取有序切片前 limit 个。
func headKeys(keys []string, limit int) []string {
	if limit <= 0 || limit >= len(keys) {
		return keys
	}
	return keys[:limit]
}

func mongoFindLimit(limit int64) *mongoopts.FindOptionsBuilder {
	return mongoopts.Find().SetLimit(limit)
}

func (s *MongoIntersectionSource) sharedCircleCount(ctx context.Context, viewerID, objectID string) int {
	if s.social == nil || s.social.db == nil {
		return 0
	}
	coll := s.social.db.Collection("circle_members")
	viewerCircles := map[string]struct{}{}
	cur, err := coll.Find(ctx, bson.M{"userId": viewerID})
	if err == nil {
		for cur.Next(ctx) {
			var doc struct {
				CircleID string `bson:"circleId"`
			}
			if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.CircleID) != "" {
				viewerCircles[doc.CircleID] = struct{}{}
			}
		}
		_ = cur.Close(ctx)
	}
	if len(viewerCircles) == 0 {
		return 0
	}
	count := 0
	cur2, err := coll.Find(ctx, bson.M{"userId": objectID})
	if err != nil {
		return 0
	}
	defer cur2.Close(ctx)
	for cur2.Next(ctx) {
		var doc struct {
			CircleID string `bson:"circleId"`
		}
		if err := cur2.Decode(&doc); err == nil {
			if _, ok := viewerCircles[doc.CircleID]; ok {
				count++
			}
		}
	}
	return count
}

func buildTagReason(
	now time.Time,
	dimension string,
	intersectionID string,
	source string,
	pointKind string,
	actionType string,
	values []string,
	ttl time.Duration,
) intersectionapp.IntersectionReasonView {
	points := make([]intersectionapp.IntersectionPointView, 0, len(values))
	for i, value := range values {
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:     intersectionID + "_p_" + strconv.Itoa(i),
			PointClass:  "fact",
			Dimension:   dimension,
			Label:       value,
			DisplayText: value,
			SourceRef:   pointKind,
			Visibility:  "public",
			Count:       1,
			SampleText:  value,
		})
	}
	return intersectionapp.IntersectionReasonView{
		IntersectionID:     intersectionID,
		IntersectionClass:  "fact",
		Dimension:          dimension,
		Strength:           scoreFromCount(len(points), 6),
		RelationKind:       "mutual",
		RelationObjectID:   intersectionID,
		ActionType:         actionType,
		ActionTargetID:     intersectionID,
		Source:             source,
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(ttl).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     len(points),
		TotalPointCount:    len(points),
	}
}

func buildContentReason(
	now time.Time,
	dimension string,
	intersectionID string,
	source string,
	pointKind string,
	actionType string,
	candidates []rtrec.ContentCandidate,
	ttl time.Duration,
	class string,
) intersectionapp.IntersectionReasonView {
	limit := len(candidates)
	if limit > 3 {
		limit = 3
	}
	points := make([]intersectionapp.IntersectionPointView, 0, limit)
	for i := 0; i < limit; i++ {
		c := candidates[i]
		points = append(points, intersectionapp.IntersectionPointView{
			PointID:     c.ContentID,
			PointClass:  "fact",
			Dimension:   dimension,
			Label:       c.Title,
			DisplayText: c.Title,
			SourceRef:   pointKind,
			Visibility:  "public",
			Count:       1,
			SampleText:  c.Title,
		})
	}
	return intersectionapp.IntersectionReasonView{
		IntersectionID:     intersectionID,
		IntersectionClass:  class,
		Dimension:          dimension,
		Strength:           scoreFromCount(len(points), 4),
		RelationKind:       "mutual",
		RelationObjectID:   intersectionID,
		ActionType:         actionType,
		ActionTargetID:     firstCandidateID(candidates),
		Source:             source,
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(ttl).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     len(points),
		TotalPointCount:    len(points),
	}
}

func topWeightKeys(values map[string]float64, limit int) []string {
	type kv struct {
		key   string
		value float64
	}
	items := make([]kv, 0, len(values))
	for key, value := range values {
		items = append(items, kv{key: key, value: value})
	}
	sort.SliceStable(items, func(i, j int) bool {
		if items[i].value != items[j].value {
			return items[i].value > items[j].value
		}
		return items[i].key < items[j].key
	})
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	out := make([]string, 0, limit)
	for i := 0; i < limit; i++ {
		out = append(out, items[i].key)
	}
	return out
}

func firstCandidateID(candidates []rtrec.ContentCandidate) string {
	if len(candidates) == 0 {
		return ""
	}
	return candidates[0].ContentID
}

func scoreFromCount(count, saturate int) float64 {
	if saturate <= 0 {
		saturate = 1
	}
	if count <= 0 {
		return 0.5
	}
	v := 0.5 + 0.5*float64(count)/float64(saturate)
	if v > 1.0 {
		return 1.0
	}
	return v
}
