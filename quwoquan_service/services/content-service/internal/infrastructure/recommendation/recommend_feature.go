package recommendation

import (
	"context"
	"log/slog"
	"math"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
	postevent "quwoquan_service/services/content-service/internal/domain/post/event"
)

// RecommendFeatureProjector maintains the rm_recommend_feature read model.
// Aligned with contracts/metadata/_projections/recommend_feature.yaml.
type RecommendFeatureProjector struct {
	coll              *mongo.Collection
	entityPropagation *rtrec.EntityInterestPropagation
	signalProcessor   rtrec.SignalProcessor
	interestAgg       *InterestProfileAggregator
}

func NewRecommendFeatureProjector(db *mongo.Database, opts ...RecommendFeatureProjectorOption) *RecommendFeatureProjector {
	p := &RecommendFeatureProjector{coll: db.Collection("rm_recommend_feature")}
	for _, opt := range opts {
		opt(p)
	}
	return p
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
	userID := strVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}
	normalizedQuery := strVal(event.Payload, "normalizedQuery")
	if normalizedQuery == "" {
		normalizedQuery = strVal(event.Payload, "query")
	}
	terms := append([]string{}, normalizedQuery)
	terms = append(terms, anySlice(event.Payload, "relatedTerms")...)
	objects := anySlice(event.Payload, "topClickedObjectIds")

	inc := bson.M{}
	for i, term := range uniqueNonEmpty(terms) {
		weight := 1.0
		if i > 0 {
			weight = 0.6 / float64(i+1)
		}
		inc["userFeatures.searchTermAffinity."+term] = weight
	}
	for i, objectID := range uniqueNonEmpty(objects) {
		inc["userFeatures.searchTopObjectAffinity."+objectID] = 1.0 / float64(i+1)
	}
	heat := math.Log1p(float64(intVal(event.Payload, "resultCount") + len(objects) + len(terms)))
	if heat > 0 {
		inc["userFeatures.searchTermHeat"] = heat
	}
	if len(inc) == 0 {
		return nil
	}

	now := time.Now().UTC()
	if !event.OccurredAt.IsZero() {
		now = event.OccurredAt.UTC()
	}
	update := bson.M{
		"$inc": inc,
		"$set": bson.M{
			"userId":                           userID,
			"userFeatures.searchTermUpdatedAt": now,
			"updatedAt":                        now,
		},
	}
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, options.UpdateOne().SetUpsert(true))
	if err != nil {
		return err
	}
	if p.interestAgg != nil {
		if rerr := p.interestAgg.Recompute(ctx, userID); rerr != nil {
			slog.Warn("interest profile recompute failed after search signal", "userId", userID, "err", rerr)
		}
	}
	return nil
}

func (p *RecommendFeatureProjector) onPostPublished(ctx context.Context, event ProjectorEvent) error {
	userID := strVal(event.Payload, "authorId")
	if userID == "" {
		userID = strVal(event.Payload, "userId")
	}
	if userID == "" {
		return nil
	}

	contentType := strVal(event.Payload, "contentType")
	tags := anySlice(event.Payload, "tagRefs")
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
	userID := strVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	events := behaviorPayloadEvents(event.Payload["events"])
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
	sourceDist := map[string]int{}
	depthSum := 0
	depthCount := 0

	typeImpressions := map[string]int{}
	typeEngagements := map[string]int{}

	// intersectionKindCounts 是 viewer 对各交集 kind（§5.4 标准名）的揭示偏好直方图：
	// 仅在「真正参与」（点击/互动/转化或深度≥2）的事件上累计，曝光本身不计入，
	// 使该特征反映「哪些交集 kind 驱动了用户行动」而非单纯被推送。WP-4 交集特征回流。
	intersectionKindCounts := map[string]int{}

	for _, ev := range events {
		tags := anySlice(ev, "tagRefs")
		for _, t := range tags {
			tagCounts[t]++
		}
		if authorID := strVal(ev, "authorId"); authorID != "" {
			authorCounts[authorID]++
		}

		depth := intVal(ev, "engagementDepth")
		source := strVal(ev, "referralSource")
		action := strVal(ev, "action")
		contentType := strVal(ev, "contentType")
		state := strVal(ev, "state")

		if kind := strVal(ev, "intersectionSourceRef"); kind != "" && isIntersectionEngagementAction(action, depth) {
			intersectionKindCounts[kind]++
		}

		if contentType != "" {
			// 七态漏斗：仅「真实曝光 impressed / 停留 dwell」计入 typeImpressions（served/impressed
			// 双轨的 impressed 侧）；弱可见 visible 不计入，避免稀释曝光分母与 CTR；未带 state 的上报按
			// impression 兜底。served（仅下发未可见）不会进入 behavior 事件，只在 HotPath 曝光过滤中记账。
			if state == "impressed" || state == "dwell" || action == "dwell" ||
				(state == "" && action == "impression") {
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

		entityRefs := anySlice(ev, "entityRefs")
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
		if source != "" {
			sourceKey := "userFeatures.sourceDistribution." + source
			sourceDist[sourceKey]++
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
	for k, v := range sourceDist {
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
		"userId":    userID,
		"updatedAt": time.Now().UTC(),
	}
	if depthCount > 0 {
		setFields["userFeatures.avgEngagementDepth"] = float64(depthSum) / float64(depthCount)
	}

	update := bson.M{
		"$inc": inc,
		"$set": setFields,
	}

	opts := options.UpdateOne().SetUpsert(true)
	if _, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts); err != nil {
		return err
	}
	// Derive the consumer-facing interest profile in place. Failure here must
	// not abort (and thus retry) the non-idempotent $inc projection above.
	if p.interestAgg != nil {
		if rerr := p.interestAgg.Recompute(ctx, userID); rerr != nil {
			slog.Warn("interest profile recompute failed", "userId", userID, "err", rerr)
		}
	}
	return nil
}

// intersectionEngagementActions are actions that signal the viewer actively
// engaged with intersection-driven content (vs mere exposure). They build the
// revealed intersection-kind preference histogram (WP-4 交集特征回流).
var intersectionEngagementActions = map[string]struct{}{
	"click": {}, "like": {}, "share": {}, "comment": {}, "favorite": {},
	"follow": {}, "join_circle": {}, "add_contact": {}, "open_object": {},
}

func isIntersectionEngagementAction(action string, depth int) bool {
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

// deriveIntersectionFeatures maps the revealed intersection-kind histogram
// (§5.4 standard kinds) to the viewer-level ranking fact features. SourceRefTop is
// the most-engaged kind (deterministic lexicographic tie-break).
func deriveIntersectionFeatures(kindCounts map[string]int) IntersectionFeatureValues {
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

func behaviorPayloadEvents(raw any) []map[string]any {
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

func intVal(m map[string]any, key string) int {
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
	userID := strVal(event.Payload, "sourcePersonaId")
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
	userID := strVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	circleTags := anySlice(event.Payload, "circleTags")
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
	coll  *mongo.Collection
	cache *featureLRU
}

func NewFeatureStore(db *mongo.Database) *FeatureStore {
	return &FeatureStore{
		coll:  db.Collection("rm_recommend_feature"),
		cache: newFeatureLRU(5000, 60*time.Second),
	}
}

// UserFeatures holds aggregated user-level features for scoring.
type UserFeatures struct {
	UserID                   string             `bson:"userId"`
	TagInteraction           map[string]int     `bson:"tagInteraction"`
	AuthorInteraction        map[string]int     `bson:"authorInteraction"`
	TotalEvents              int                `bson:"totalEvents"`
	TotalLikes               int                `bson:"totalLikes"`
	TotalShares              int                `bson:"totalShares"`
	TopicAffinities          map[string]float64 `bson:"topicAffinities"`
	AudienceAffinities       map[string]float64 `bson:"audienceAffinities"`
	FormatAffinities         map[string]float64 `bson:"formatAffinities"`
	EntityAffinities         map[string]float64 `bson:"entityAffinities"`
	AvgEngagementDepth       float64            `bson:"avgEngagementDepth"`
	DepthDistribution        map[string]int     `bson:"depthDistribution"`
	SourceDistribution       map[string]int     `bson:"sourceDistribution"`
	SearchTermAffinities     map[string]float64 `bson:"searchTermAffinity"`
	SearchTopObjectAffinity  map[string]float64 `bson:"searchTopObjectAffinity"`
	SearchTermHeat           float64            `bson:"searchTermHeat"`
	SearchTermUpdatedAt      time.Time          `bson:"searchTermUpdatedAt"`
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
			AuthorInteraction        map[string]int     `bson:"authorInteraction"`
			TotalEvents              int                `bson:"totalEvents"`
			TotalLikes               int                `bson:"totalLikes"`
			TotalShares              int                `bson:"totalShares"`
			TopicAffinities          map[string]float64 `bson:"topicAffinities"`
			AudienceAffinities       map[string]float64 `bson:"audienceAffinities"`
			FormatAffinities         map[string]float64 `bson:"formatAffinities"`
			EntityAffinities         map[string]float64 `bson:"entityAffinities"`
			AvgEngagementDepth       float64            `bson:"avgEngagementDepth"`
			DepthDistribution        map[string]int     `bson:"depthDistribution"`
			SourceDistribution       map[string]int     `bson:"sourceDistribution"`
			SearchTermAffinities     map[string]float64 `bson:"searchTermAffinity"`
			SearchTopObjectAffinity  map[string]float64 `bson:"searchTopObjectAffinity"`
			SearchTermHeat           float64            `bson:"searchTermHeat"`
			SearchTermUpdatedAt      time.Time          `bson:"searchTermUpdatedAt"`
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

	return &UserFeatures{
		UserID:                   doc.UserID,
		Segments:                 doc.Segments,
		IntersectionKindCounts:   doc.SocialFeatures.Intersection.KindCounts,
		TagInteraction:           doc.UserFeatures.TagInteraction,
		AuthorInteraction:        doc.UserFeatures.AuthorInteraction,
		TotalEvents:              doc.UserFeatures.TotalEvents,
		TotalLikes:               doc.UserFeatures.TotalLikes,
		TotalShares:              doc.UserFeatures.TotalShares,
		TopicAffinities:          doc.UserFeatures.TopicAffinities,
		AudienceAffinities:       doc.UserFeatures.AudienceAffinities,
		FormatAffinities:         doc.UserFeatures.FormatAffinities,
		EntityAffinities:         doc.UserFeatures.EntityAffinities,
		AvgEngagementDepth:       doc.UserFeatures.AvgEngagementDepth,
		DepthDistribution:        doc.UserFeatures.DepthDistribution,
		SourceDistribution:       doc.UserFeatures.SourceDistribution,
		SearchTermAffinities:     doc.UserFeatures.SearchTermAffinities,
		SearchTopObjectAffinity:  doc.UserFeatures.SearchTopObjectAffinity,
		SearchTermHeat:           doc.UserFeatures.SearchTermHeat,
		SearchTermUpdatedAt:      doc.UserFeatures.SearchTermUpdatedAt,
		CircleTagAffinities:      doc.UserFeatures.CircleTagAffinities,
		SocialInterestScore:      doc.UserFeatures.SocialInterestScore,
		EntityInstanceAffinities: doc.UserFeatures.EntityInstanceAffinities,
		TypeImpressions:          doc.UserFeatures.TypeImpressions,
		TypeEngagements:          doc.UserFeatures.TypeEngagements,
	}, nil
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

	authorAffinities := make(map[string]float64, len(raw.AuthorInteraction))
	for author, count := range raw.AuthorInteraction {
		authorAffinities[author] = float64(count)
	}

	var engagementRate float64
	if raw.TotalEvents > 0 {
		engagementRate = float64(raw.TotalLikes+raw.TotalShares) / float64(raw.TotalEvents)
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
	if searchFeaturesFresh(raw) {
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
		AvgEngagementDepth:        raw.AvgEngagementDepth,
		DepthDistribution:         depthDist,
		SourceDistribution:        raw.SourceDistribution,
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
		ix := deriveIntersectionFeatures(raw.IntersectionKindCounts)
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

func searchFeaturesFresh(raw *UserFeatures) bool {
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
