package recommendation

import (
	"context"
	"fmt"
	"log/slog"
	"math"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
	postevent "quwoquan_service/services/content-service/internal/content/post/domain/event"
)

// RecommendFeatureProjector maintains the rm_recommend_feature read model.
// Aligned with contracts/metadata/_projections/recommend_feature.yaml.
type RecommendFeatureProjector struct {
	coll              *mongo.Collection
	searchIntentColl  *mongo.Collection
	entityPropagation *rtrec.EntityInterestPropagation
	signalProcessor   rtrec.SignalProcessor
	interestAgg       *InterestProfileAggregator
}

func NewRecommendFeatureProjector(db *mongo.Database, opts ...RecommendFeatureProjectorOption) *RecommendFeatureProjector {
	p := &RecommendFeatureProjector{
		coll:             db.Collection("rm_recommend_feature"),
		searchIntentColl: db.Collection("rm_search_intent"),
	}
	for _, opt := range opts {
		opt(p)
	}
	return p
}

func (p *RecommendFeatureProjector) EnsureIndexes(ctx context.Context) error {
	if p == nil || p.coll == nil {
		return fmt.Errorf("RecommendFeature projector is not configured")
	}
	_, err := p.coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "userId", Value: 1}},
		Options: options.Index().
			SetName("uq_recommend_feature_user").
			SetUnique(true),
	})
	if err != nil {
		return fmt.Errorf("create RecommendFeature user index: %w", err)
	}
	_, err = p.searchIntentColl.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().
			SetName("idx_rm_search_intent_expire").
			SetExpireAfterSeconds(0),
	})
	if err != nil {
		return fmt.Errorf("create search intent TTL index: %w", err)
	}
	// One-way cleanup for the pre-TTL embedded shape. Short-term search intent now
	// lives only in rm_search_intent, where Mongo can physically enforce expiry.
	if _, err := p.coll.UpdateMany(ctx, bson.M{}, bson.M{"$unset": bson.M{
		"userFeatures.searchTermAffinity":      "",
		"userFeatures.searchTopObjectAffinity": "",
		"userFeatures.searchTermHeat":          "",
		"userFeatures.searchTermUpdatedAt":     "",
	}}); err != nil {
        return fmt.Errorf("remove retired embedded search intent: %w", err)
	}
	return nil
}

type RecommendFeatureProjectorOption func(*RecommendFeatureProjector)

func WithEntityPropagation(ep *rtrec.EntityInterestPropagation) RecommendFeatureProjectorOption {
	return func(p *RecommendFeatureProjector) { p.entityPropagation = ep }
}

func WithSignalProcessor(sp rtrec.SignalProcessor) RecommendFeatureProjectorOption {
	return func(p *RecommendFeatureProjector) { p.signalProcessor = sp }
}

// WithInterestAggregator wires the derived interest-profile aggregator so the
// projector recomputes the interest profile and population segments after each
// behavior batch: segments are persisted into rm_recommend_feature.segments and
// UserInterestRecomputed is published (the profile itself lives in the user
// domain's rm_user_profile_view, not in this wide table).
func WithInterestAggregator(agg *InterestProfileAggregator) RecommendFeatureProjectorOption {
	return func(p *RecommendFeatureProjector) { p.interestAgg = agg }
}

func (p *RecommendFeatureProjector) Name() string { return "RecommendFeatureProjector" }

func (p *RecommendFeatureProjector) EventTypes() []string {
	return []string{
		postevent.PostPublished, "BehaviorBatchReported",
		"PersonaFollowStateChanged", "CircleMemberJoined", "SearchRecommendationSignalPublished",
	}
}

func (p *RecommendFeatureProjector) Project(ctx context.Context, event ProjectorEvent) error {
	switch event.Type {
	case postevent.PostPublished:
		return p.onPostPublished(ctx, event)
	case "BehaviorBatchReported":
		return p.onBehaviorBatch(ctx, event)
	case "PersonaFollowStateChanged":
		return p.onPersonaFollowStateChanged(ctx, event)
	case "CircleMemberJoined":
		return p.onCircleMemberJoined(ctx, event)
	case "SearchRecommendationSignalPublished":
		return p.onSearchRecommendationSignal(ctx, event)
	default:
		return nil
	}
}

const SearchIntentTTL = 24 * time.Hour

func (p *RecommendFeatureProjector) onSearchRecommendationSignal(ctx context.Context, event ProjectorEvent) error {
	userID := StrVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	now := time.Now().UTC()
	if !event.OccurredAt.IsZero() {
		now = event.OccurredAt.UTC()
	}
	expiresAt := now.Add(SearchIntentTTL)
	switch StrVal(event.Payload, "signalType") {
	case "query":
		terms := uniqueNonEmpty(append(
			[]string{StrVal(event.Payload, "normalizedQuery")},
			AnySlice(event.Payload, "relatedTerms")...,
		))
		if len(terms) == 0 {
			return fmt.Errorf("search query signal has no normalized terms")
		}
		if len(terms) > 16 {
			terms = terms[:16]
		}
		heat := math.Log1p(float64(IntVal(event.Payload, "resultCount") + len(terms)))
		_, err := p.searchIntentColl.UpdateOne(
			ctx,
			bson.M{"_id": userID},
			bson.M{"$set": bson.M{
				"userId":           userID,
				"terms":            terms,
				"engagedObjectIds": []string{},
				"termHeat":         heat,
				"updatedAt":        now,
				"expiresAt":        expiresAt,
			}},
			options.UpdateOne().SetUpsert(true),
		)
		return err
	case "click":
		objects := uniqueNonEmpty(AnySlice(event.Payload, "engagedObjectIds"))
		if len(objects) == 0 {
			return fmt.Errorf("search click signal has no engaged objects")
		}
		if len(objects) > 8 {
			objects = objects[:8]
		}
		_, err := p.searchIntentColl.UpdateOne(
			ctx,
			bson.M{"_id": userID},
			bson.M{
				"$set": bson.M{
					"userId":    userID,
					"updatedAt": now,
					"expiresAt": expiresAt,
				},
				"$addToSet": bson.M{
					"engagedObjectIds": bson.M{"$each": objects},
				},
			},
			options.UpdateOne().SetUpsert(true),
		)
		return err
	default:
		return fmt.Errorf("unsupported search recommendation signal type")
	}
}

func (p *RecommendFeatureProjector) onPostPublished(ctx context.Context, event ProjectorEvent) error {
	userID := StrVal(event.Payload, "authorId")
	if userID == "" {
		userID = StrVal(event.Payload, "userId")
	}
	if userID == "" {
		return nil
	}

	contentType := StrVal(event.Payload, "contentType")
	tags := AnySlice(event.Payload, "tagRefs")
	if contentType == "" && len(tags) == 0 {
		return nil
	}

	inc := bson.M{}
	for _, tag := range tags {
		inc["userFeatures.tagInteraction."+tag] = 1
		dim := rtrec.ClassifyTagDimension(tag)
		switch dim {
		case rtrec.DimensionTopic:
			inc["userFeatures.topicAffinities."+tag] = 0.3
		case rtrec.DimensionAudience:
			inc["userFeatures.audienceAffinities."+tag] = 0.3
		case rtrec.DimensionFormat:
			inc["userFeatures.formatAffinities."+tag] = 0.3
		case rtrec.DimensionEntity:
			inc["userFeatures.entityAffinities."+tag] = 0.3
		}
	}
	if contentType != "" {
		inc["userFeatures.typeImpressions."+contentType] = 1
	}

	update := bson.M{
		"$inc": inc,
		"$set": bson.M{
			"userId":    userID,
			"updatedAt": time.Now().UTC(),
		},
	}
	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
}

func (p *RecommendFeatureProjector) onBehaviorBatch(ctx context.Context, event ProjectorEvent) error {
	userID := StrVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	events := BehaviorPayloadEvents(event.Payload["events"])
	if len(events) == 0 {
		return nil
	}

	tagCounts := map[string]int{}
	authorCounts := map[string]int{}

	topicInc := map[string]float64{}
	audienceInc := map[string]float64{}
	formatInc := map[string]float64{}
	entityInc := map[string]float64{}
	entityInstanceInc := map[string]float64{}
	depthDist := map[string]int{}
	depthSum := 0
	depthCount := 0

	typeImpressions := map[string]int{}
	typeEngagements := map[string]int{}

	// intersectionKindCounts 是 viewer 对各交集 kind（§5.4 标准名）的揭示偏好直方图：
	// 仅在「真正参与」（点击/互动/转化或深度≥2）的事件上累计，曝光本身不计入，
	// 使该特征反映「哪些交集 kind 驱动了用户行动」而非单纯被推送。WP-4 交集特征回流。
	intersectionKindCounts := map[string]int{}

	for _, ev := range events {
		tags := AnySlice(ev, "tagRefs")
		for _, t := range tags {
			tagCounts[t]++
		}
		if authorID := StrVal(ev, "authorId"); authorID != "" {
			authorCounts[authorID]++
		}

		depth := IntVal(ev, "engagementDepth")
		source := StrVal(ev, "referralSource")
		action := StrVal(ev, "action")
		contentType := StrVal(ev, "contentType")
		state := StrVal(ev, "state")

		if kind := StrVal(ev, "intersectionSourceRef"); kind != "" && IsIntersectionEngagementAction(action, depth) {
			intersectionKindCounts[kind]++
		}

		if contentType != "" {
			// 七态漏斗：仅「真实曝光 impressed / 停留 dwell」计入 typeImpressions（served/impressed
			// 双轨的 impressed 侧）；弱可见 visible 不计入，避免稀释曝光分母与 CTR。
			// impression 的 state 已在行为入口强校验，禁止缺失 state 的兼容兜底。
			if state == "impressed" || state == "dwell" || action == "dwell" {
				typeImpressions[contentType]++
			}
			// 点击（click）与显式互动（like/share/comment）及深度≥2 计入 typeEngagements（CTR / 互动率分子）。
			if action == "click" || state == "interaction" || depth >= 2 ||
				action == "like" || action == "share" || action == "comment" {
				typeEngagements[contentType]++
			}
		}

		if len(tags) > 0 {
			delta := rtrec.ClassifyAndWeightTags(tags, depth, source)
			for k, v := range delta.Topic {
				topicInc[k] += v
			}
			for k, v := range delta.Audience {
				audienceInc[k] += v
			}
			for k, v := range delta.Format {
				formatInc[k] += v
			}
			for k, v := range delta.Entity {
				entityInc[k] += v
			}
		}

		entityRefs := AnySlice(ev, "entityRefs")
		if len(entityRefs) > 0 && p.entityPropagation != nil {
			propResult, err := p.entityPropagation.Propagate(ctx, entityRefs, depth)
			if err == nil && propResult != nil {
				for eid, delta := range propResult.EntityInstanceDeltas {
					entityInstanceInc[eid] += delta
				}
				for tag, delta := range propResult.PropagatedTagDeltas {
					entityInc[tag] += delta
				}
			}
		}

		if depth > 0 {
			depthKey := "userFeatures.depthDistribution." + depthLevelKey(depth)
			depthDist[depthKey]++
			depthSum += depth
			depthCount++
		}
	}

	inc := bson.M{}
	for tag, count := range tagCounts {
		inc["userFeatures.tagInteraction."+tag] = count
	}
	for author, count := range authorCounts {
		inc["userFeatures.authorInteraction."+author] = count
	}
	inc["userFeatures.totalEvents"] = len(events)
	if depthCount > 0 {
		// 单条 relay 事件必须累加充分统计量；不能把当前事件的均值
		// 直接覆盖历史 avg，否则每个新行为都会抹掉此前样本。
		inc["userFeatures.engagementDepthSum"] = depthSum
		inc["userFeatures.engagementDepthCount"] = depthCount
	}

	for k, v := range topicInc {
		inc["userFeatures.topicAffinities."+k] = v
	}
	for k, v := range audienceInc {
		inc["userFeatures.audienceAffinities."+k] = v
	}
	for k, v := range formatInc {
		inc["userFeatures.formatAffinities."+k] = v
	}
	for k, v := range entityInc {
		inc["userFeatures.entityAffinities."+k] = v
	}
	for k, v := range entityInstanceInc {
		inc["userFeatures.entityInstanceAffinities."+k] = v
	}
	for k, v := range depthDist {
		inc[k] = v
	}
	for ct, cnt := range typeImpressions {
		inc["userFeatures.typeImpressions."+ct] = cnt
	}
	for ct, cnt := range typeEngagements {
		inc["userFeatures.typeEngagements."+ct] = cnt
	}
	for kind, cnt := range intersectionKindCounts {
		inc["socialFeatures.intersection.kindCounts."+kind] = cnt
	}

	setFields := bson.M{
		"userId":                   userID,
		"behaviorProjectionLastId": event.ID,
		"updatedAt":                time.Now().UTC(),
	}

	update := bson.M{
		"$inc": inc,
		"$set": setFields,
	}

	applied, err := p.applyBehaviorUpdate(ctx, userID, event.ID, update)
	if err != nil {
		return err
	}
	if !applied {
		return nil
	}
	// 派生消费侧兴趣画像。这里失败不回滚已原子提交的计数；下一条事件或周期
	// recompute 会继续收敛派生画像。
	if p.interestAgg != nil {
		if rerr := p.interestAgg.Recompute(ctx, userID); rerr != nil {
			slog.Warn("interest profile recompute failed", "userId", userID, "err", rerr)
		}
	}
	return nil
}

// applyBehaviorUpdate 用每条 rm_behavior_events ObjectID 的十六进制全序作为
// 用户特征文档水位，使 $inc 与去重标记在同一原子 UpdateOne 中提交。
// relay lease 负责全局顺序；checkpoint 保存失败重放时，旧/同一事件成为 no-op。
func (p *RecommendFeatureProjector) applyBehaviorUpdate(
	ctx context.Context,
	userID, eventID string,
	update bson.M,
) (bool, error) {
	if strings.TrimSpace(eventID) == "" {
		return false, fmt.Errorf("BehaviorBatchReported requires a projection event id")
	}
	filter := bson.M{
		"userId": userID,
		"$or": []bson.M{
			{"behaviorProjectionLastId": bson.M{"$exists": false}},
			{"behaviorProjectionLastId": bson.M{"$lt": eventID}},
		},
	}
	result, err := p.coll.UpdateOne(ctx, filter, update)
	if err != nil {
		return false, fmt.Errorf("project behavior features: %w", err)
	}
	if result.MatchedCount > 0 {
		return true, nil
	}

	// MatchedCount=0 可能是重放，也可能是该用户第一条事件。先判存在，
	// 再用唯一 userId 索引保护首次 upsert 的并发竞态。
	existing, err := p.coll.CountDocuments(
		ctx,
		bson.M{"userId": userID},
		options.Count().SetLimit(1),
	)
	if err != nil {
		return false, fmt.Errorf("check RecommendFeature replay: %w", err)
	}
	if existing > 0 {
		return false, nil
	}
	result, err = p.coll.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true))
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("create RecommendFeature behavior projection: %w", err)
	}
	return result.UpsertedCount > 0 || result.MatchedCount > 0, nil
}

// intersectionEngagementActions are actions that signal the viewer actively
// engaged with intersection-driven content (vs mere exposure). They build the
// revealed intersection-kind preference histogram (WP-4 交集特征回流).
var intersectionEngagementActions = map[string]struct{}{
	"click": {}, "like": {}, "share": {}, "comment": {}, "favorite": {},
	"follow": {}, "join_circle": {}, "add_contact": {}, "open_object": {},
}

func IsIntersectionEngagementAction(action string, depth int) bool {
	if _, ok := intersectionEngagementActions[action]; ok {
		return true
	}
	return depth >= 2
}

// IntersectionFeatureValues is the viewer-level derived intersection feature set
// (mirrors rtrec.UserFeatureVector intersection fact fields). Kept pure for tests.
type IntersectionFeatureValues struct {
	SharedFolloweesCount   int
	SharedCircleCount      int
	CoCommentedCount       int
	CoVisitedEntityCount   int
	FolloweeInObjectActive int
	FolloweeViewingActive  int
	SourceRefTop           string
}

// DeriveIntersectionFeatures maps the revealed intersection-kind histogram
// (§5.4 standard kinds) to the viewer-level ranking fact features. SourceRefTop is
// the most-engaged kind (deterministic lexicographic tie-break).
func DeriveIntersectionFeatures(kindCounts map[string]int) IntersectionFeatureValues {
	out := IntersectionFeatureValues{}
	bestKind, bestCount := "", 0
	for kind, count := range kindCounts {
		if count <= 0 {
			continue
		}
		switch kind {
		case "sharedFollowees":
			out.SharedFolloweesCount += count
		case "sharedCircle":
			out.SharedCircleCount += count
		case "coCommented":
			out.CoCommentedCount += count
		case "coVisitedEntity":
			out.CoVisitedEntityCount += count
		case "followeeInObject":
			out.FolloweeInObjectActive = 1
		case "followeeViewing":
			out.FolloweeViewingActive = 1
		}
		if count > bestCount || (count == bestCount && (bestKind == "" || kind < bestKind)) {
			bestKind, bestCount = kind, count
		}
	}
	out.SourceRefTop = bestKind
	return out
}

func BehaviorPayloadEvents(raw any) []map[string]any {
	switch items := raw.(type) {
	case []map[string]any:
		return items
	case []any:
		out := make([]map[string]any, 0, len(items))
		for _, item := range items {
			if m, ok := item.(map[string]any); ok {
				out = append(out, m)
			}
		}
		return out
	default:
		return nil
	}
}

func uniqueNonEmpty(values []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

func depthLevelKey(level int) string {
	switch {
	case level <= 0:
		return "L0"
	case level == 1:
		return "L1"
	case level == 2:
		return "L2"
	case level == 3:
		return "L3"
	default:
		return "L4"
	}
}

func IntVal(m map[string]any, key string) int {
	switch v := m[key].(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	default:
		return 0
	}
}

func (p *RecommendFeatureProjector) injectSignal(ctx context.Context, userID, contentID, action string, tags []string) {
	if p.signalProcessor == nil {
		return
	}
	_ = p.signalProcessor.ProcessSignalBatch(ctx, []rtrec.BehaviorSignal{{
		UserID:    userID,
		ContentID: contentID,
		Action:    action,
		Tags:      tags,
		Timestamp: time.Now().UTC(),
	}})
}

func (p *RecommendFeatureProjector) onPersonaFollowStateChanged(ctx context.Context, event ProjectorEvent) error {
	userID := StrVal(event.Payload, "sourcePersonaId")
	if userID == "" {
		return nil
	}
	delta := -0.1
	if boolVal(event.Payload, "following") {
		delta = 0.1
	}

	update := bson.M{
		"$inc": bson.M{
			"userFeatures.socialInterestScore": delta,
		},
		"$set": bson.M{
			"userId":    userID,
			"updatedAt": time.Now().UTC(),
		},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
}

func (p *RecommendFeatureProjector) onCircleMemberJoined(ctx context.Context, event ProjectorEvent) error {
	userID := StrVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	circleTags := AnySlice(event.Payload, "circleTags")
	inc := bson.M{
		"userFeatures.socialInterestScore": 0.2,
	}
	for _, tag := range circleTags {
		inc["userFeatures.circleTagAffinities."+tag] = 1.0
	}

	update := bson.M{
		"$inc": inc,
		"$set": bson.M{
			"userId":    userID,
			"updatedAt": time.Now().UTC(),
		},
	}

	opts := options.UpdateOne().SetUpsert(true)
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
}

// FeatureStore reads pre-computed recommendation features for scoring.
// Implements rtrec.FeatureProvider interface for direct use in the Engine.
type FeatureStore struct {
	coll             *mongo.Collection
	searchIntentColl *mongo.Collection
	cache            *featureLRU
}

func NewFeatureStore(db *mongo.Database) *FeatureStore {
	return &FeatureStore{
		coll:             db.Collection("rm_recommend_feature"),
		searchIntentColl: db.Collection("rm_search_intent"),
		cache:            newFeatureLRU(5000, 60*time.Second),
	}
}

// UserFeatures holds aggregated user-level features for scoring.
type UserFeatures struct {
	UserID                   string             `bson:"userId"`
	TagInteraction           map[string]int     `bson:"tagInteraction"`
	ExplicitTagAffinities    map[string]float64 `bson:"explicitTagAffinities"`
	AuthorInteraction        map[string]int     `bson:"authorInteraction"`
	TotalEvents              int                `bson:"totalEvents"`
	TotalLikes               int                `bson:"totalLikes"`
	TotalShares              int                `bson:"totalShares"`
	TopicAffinities          map[string]float64 `bson:"topicAffinities"`
	AudienceAffinities       map[string]float64 `bson:"audienceAffinities"`
	FormatAffinities         map[string]float64 `bson:"formatAffinities"`
	EntityAffinities         map[string]float64 `bson:"entityAffinities"`
	EngagementDepthSum       int                `bson:"engagementDepthSum"`
	EngagementDepthCount     int                `bson:"engagementDepthCount"`
	DepthDistribution        map[string]int     `bson:"depthDistribution"`
	SearchTermAffinities     map[string]float64 `bson:"-"`
	SearchTopObjectAffinity  map[string]float64 `bson:"-"`
	SearchTermHeat           float64            `bson:"-"`
	SearchTermUpdatedAt      time.Time          `bson:"-"`
	CircleTagAffinities      map[string]float64 `bson:"circleTagAffinities"`
	SocialInterestScore      float64            `bson:"socialInterestScore"`
	EntityInstanceAffinities map[string]float64 `bson:"entityInstanceAffinities"`
	TypeImpressions          map[string]int     `bson:"typeImpressions"`
	TypeEngagements          map[string]int     `bson:"typeEngagements"`
	// IntersectionKindCounts is the viewer's revealed engagement histogram per
	// intersection kind (§5.4), sourced from socialFeatures.intersection.kindCounts.
	IntersectionKindCounts map[string]int `bson:"-"`
	// Segments is the rule-based population membership (top-level field), set by
	// InterestProfileAggregator.Recompute. Drives policy segment targeting.
	Segments []string `bson:"segments"`
}

func (s *FeatureStore) GetUserFeatures(ctx context.Context, userID string) (*UserFeatures, error) {
	var doc struct {
		UserID         string   `bson:"userId"`
		Segments       []string `bson:"segments"`
		SocialFeatures struct {
			Intersection struct {
				KindCounts map[string]int `bson:"kindCounts"`
			} `bson:"intersection"`
		} `bson:"socialFeatures"`
		UserFeatures struct {
			TagInteraction           map[string]int     `bson:"tagInteraction"`
			ExplicitTagAffinities    map[string]float64 `bson:"explicitTagAffinities"`
			AuthorInteraction        map[string]int     `bson:"authorInteraction"`
			TotalEvents              int                `bson:"totalEvents"`
			TotalLikes               int                `bson:"totalLikes"`
			TotalShares              int                `bson:"totalShares"`
			TopicAffinities          map[string]float64 `bson:"topicAffinities"`
			AudienceAffinities       map[string]float64 `bson:"audienceAffinities"`
			FormatAffinities         map[string]float64 `bson:"formatAffinities"`
			EntityAffinities         map[string]float64 `bson:"entityAffinities"`
			EngagementDepthSum       int                `bson:"engagementDepthSum"`
			EngagementDepthCount     int                `bson:"engagementDepthCount"`
			DepthDistribution        map[string]int     `bson:"depthDistribution"`
			CircleTagAffinities      map[string]float64 `bson:"circleTagAffinities"`
			SocialInterestScore      float64            `bson:"socialInterestScore"`
			EntityInstanceAffinities map[string]float64 `bson:"entityInstanceAffinities"`
			TypeImpressions          map[string]int     `bson:"typeImpressions"`
			TypeEngagements          map[string]int     `bson:"typeEngagements"`
		} `bson:"userFeatures"`
	}

	err := s.coll.FindOne(ctx, bson.M{"userId": userID}).Decode(&doc)
	if err == mongo.ErrNoDocuments {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	var intent struct {
		Terms            []string  `bson:"terms"`
		EngagedObjectIDs []string  `bson:"engagedObjectIds"`
		TermHeat         float64   `bson:"termHeat"`
		UpdatedAt        time.Time `bson:"updatedAt"`
		ExpiresAt        time.Time `bson:"expiresAt"`
	}
	intentErr := s.searchIntentColl.FindOne(ctx, bson.M{
		"_id":       userID,
		"expiresAt": bson.M{"$gt": time.Now().UTC()},
	}).Decode(&intent)
	if intentErr != nil && intentErr != mongo.ErrNoDocuments {
		return nil, intentErr
	}
	searchTermAffinities := map[string]float64(nil)
	searchObjectAffinities := map[string]float64(nil)
	searchTermHeat := 0.0
	searchUpdatedAt := time.Time{}
	if intentErr == nil {
		searchTermAffinities = weightedSearchAffinities(intent.Terms, 1.0, 0.6)
		searchObjectAffinities = weightedSearchAffinities(
			intent.EngagedObjectIDs,
			1.0,
			1.0,
		)
		searchTermHeat = intent.TermHeat
		searchUpdatedAt = intent.UpdatedAt
	}

	return &UserFeatures{
		UserID:                   doc.UserID,
		Segments:                 doc.Segments,
		IntersectionKindCounts:   doc.SocialFeatures.Intersection.KindCounts,
		TagInteraction:           doc.UserFeatures.TagInteraction,
		ExplicitTagAffinities:    doc.UserFeatures.ExplicitTagAffinities,
		AuthorInteraction:        doc.UserFeatures.AuthorInteraction,
		TotalEvents:              doc.UserFeatures.TotalEvents,
		TotalLikes:               doc.UserFeatures.TotalLikes,
		TotalShares:              doc.UserFeatures.TotalShares,
		TopicAffinities:          doc.UserFeatures.TopicAffinities,
		AudienceAffinities:       doc.UserFeatures.AudienceAffinities,
		FormatAffinities:         doc.UserFeatures.FormatAffinities,
		EntityAffinities:         doc.UserFeatures.EntityAffinities,
		EngagementDepthSum:       doc.UserFeatures.EngagementDepthSum,
		EngagementDepthCount:     doc.UserFeatures.EngagementDepthCount,
		DepthDistribution:        doc.UserFeatures.DepthDistribution,
		SearchTermAffinities:     searchTermAffinities,
		SearchTopObjectAffinity:  searchObjectAffinities,
		SearchTermHeat:           searchTermHeat,
		SearchTermUpdatedAt:      searchUpdatedAt,
		CircleTagAffinities:      doc.UserFeatures.CircleTagAffinities,
		SocialInterestScore:      doc.UserFeatures.SocialInterestScore,
		EntityInstanceAffinities: doc.UserFeatures.EntityInstanceAffinities,
		TypeImpressions:          doc.UserFeatures.TypeImpressions,
		TypeEngagements:          doc.UserFeatures.TypeEngagements,
	}, nil
}

// Invalidate removes one actor's cached vector after an asynchronous feature
// projection commits. The projection itself remains Mongo-authoritative; this
// only prevents the 60-second read cache from masking a fresh explicit choice.
func (s *FeatureStore) Invalidate(userID string) {
	if s == nil || s.cache == nil {
		return
	}
	s.cache.delete(userID)
}

func weightedSearchAffinities(
	values []string,
	firstWeight float64,
	followingWeight float64,
) map[string]float64 {
	cleaned := uniqueNonEmpty(values)
	if len(cleaned) == 0 {
		return nil
	}
	out := make(map[string]float64, len(cleaned))
	for index, value := range cleaned {
		weight := firstWeight
		if index > 0 {
			weight = followingWeight / float64(index+1)
		}
		out[value] = weight
	}
	return out
}

// GetFeatures implements rtrec.FeatureProvider.
func (s *FeatureStore) GetFeatures(ctx context.Context, userID string) (*rtrec.UserFeatureVector, error) {
	if cached, ok := s.cache.get(userID); ok {
		return cached, nil
	}
	raw, err := s.GetUserFeatures(ctx, userID)
	if err != nil || raw == nil {
		return nil, err
	}

	tagAffinities := make(map[string]float64, len(raw.TagInteraction))
	for tag, count := range raw.TagInteraction {
		tagAffinities[tag] = float64(count)
	}
	for tag, weight := range raw.ExplicitTagAffinities {
		tagAffinities[tag] += weight
	}

	authorAffinities := make(map[string]float64, len(raw.AuthorInteraction))
	for author, count := range raw.AuthorInteraction {
		authorAffinities[author] = float64(count)
	}

	var engagementRate float64
	if raw.TotalEvents > 0 {
		engagementRate = float64(raw.TotalLikes+raw.TotalShares) / float64(raw.TotalEvents)
	}
	avgEngagementDepth := 0.0
	if raw.EngagementDepthCount > 0 {
		avgEngagementDepth = float64(raw.EngagementDepthSum) / float64(raw.EngagementDepthCount)
	}

	depthDist := make(map[string]int, len(raw.DepthDistribution))
	for k, v := range raw.DepthDistribution {
		depthDist[k] += v
	}

	typeENER := make(map[string]float64, len(raw.TypeImpressions))
	for ct, imp := range raw.TypeImpressions {
		if imp > 0 {
			eng := raw.TypeEngagements[ct]
			typeENER[ct] = float64(eng) / float64(imp)
		}
	}
	searchTermAffinities := map[string]float64(nil)
	searchTopObjectAffinities := map[string]float64(nil)
	searchTermHeat := 0.0
	if SearchFeaturesFresh(raw) {
		searchTermAffinities = raw.SearchTermAffinities
		searchTopObjectAffinities = raw.SearchTopObjectAffinity
		searchTermHeat = raw.SearchTermHeat
	}

	vec := &rtrec.UserFeatureVector{
		TagAffinities:             tagAffinities,
		AuthorAffinities:          authorAffinities,
		TotalLikes:                raw.TotalLikes,
		TotalShares:               raw.TotalShares,
		TotalEvents:               raw.TotalEvents,
		EngagementRate:            engagementRate,
		LikeLevel:                 rtrec.MapCountToLevel(raw.TotalLikes),
		ShareLevel:                rtrec.MapCountToLevel(raw.TotalShares),
		EventLevel:                rtrec.MapCountToLevel(raw.TotalEvents),
		TopicAffinities:           raw.TopicAffinities,
		AudienceAffinities:        raw.AudienceAffinities,
		FormatAffinities:          raw.FormatAffinities,
		EntityAffinities:          raw.EntityAffinities,
		EntityInstanceAffinities:  raw.EntityInstanceAffinities,
		TypeENER:                  typeENER,
		AvgEngagementDepth:        avgEngagementDepth,
		DepthDistribution:         depthDist,
		SearchTermAffinities:      searchTermAffinities,
		SearchTopObjectAffinities: searchTopObjectAffinities,
		SearchTermHeat:            searchTermHeat,
		CircleTagAffinities:       raw.CircleTagAffinities,
		SocialInterestScore:       raw.SocialInterestScore,
		Segments:                  raw.Segments,
	}
	// 交集事实通道特征回流：由揭示偏好直方图派生 viewer 级事实交集特征，
	// 经 ModelPredictRequest.UserFeatures 单点注入精排模型（ranking-signal-fusion）。
	if len(raw.IntersectionKindCounts) > 0 {
		ix := DeriveIntersectionFeatures(raw.IntersectionKindCounts)
		vec.SharedFolloweesCount = ix.SharedFolloweesCount
		vec.SharedCircleCount = ix.SharedCircleCount
		vec.CoCommentedCount = ix.CoCommentedCount
		vec.CoVisitedEntityCount = ix.CoVisitedEntityCount
		vec.FolloweeInObjectActive = ix.FolloweeInObjectActive
		vec.FolloweeViewingActive = ix.FolloweeViewingActive
		vec.IntersectionSourceRefTop = ix.SourceRefTop
	}
	s.cache.put(userID, vec)
	return vec, nil
}

func SearchFeaturesFresh(raw *UserFeatures) bool {
	return raw != nil && !raw.SearchTermUpdatedAt.IsZero() && time.Since(raw.SearchTermUpdatedAt) <= SearchIntentTTL
}

// featureLRU is a simple TTL-based cache for UserFeatureVector.
type featureLRU struct {
	mu      sync.RWMutex
	entries map[string]featureCacheEntry
	maxSize int
	ttl     time.Duration
}

type featureCacheEntry struct {
	vec       *rtrec.UserFeatureVector
	expiresAt time.Time
}

func newFeatureLRU(maxSize int, ttl time.Duration) *featureLRU {
	return &featureLRU{
		entries: make(map[string]featureCacheEntry, maxSize),
		maxSize: maxSize,
		ttl:     ttl,
	}
}

func (c *featureLRU) get(userID string) (*rtrec.UserFeatureVector, bool) {
	c.mu.RLock()
	e, ok := c.entries[userID]
	c.mu.RUnlock()
	if !ok || time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.vec, true
}

func (c *featureLRU) put(userID string, vec *rtrec.UserFeatureVector) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if len(c.entries) >= c.maxSize {
		now := time.Now()
		for k, v := range c.entries {
			if now.After(v.expiresAt) {
				delete(c.entries, k)
			}
		}
		if len(c.entries) >= c.maxSize {
			for k := range c.entries {
				delete(c.entries, k)
				break
			}
		}
	}
	c.entries[userID] = featureCacheEntry{vec: vec, expiresAt: time.Now().Add(c.ttl)}
}

func (c *featureLRU) delete(userID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.entries, userID)
}
