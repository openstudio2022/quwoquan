package recommendation

import (
	"context"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// RecommendFeatureProjector maintains the rm_recommend_feature read model.
// Aligned with contracts/metadata/_projections/recommend_feature.yaml.
type RecommendFeatureProjector struct {
	coll              *mongo.Collection
	entityPropagation *rtrec.EntityInterestPropagation
	signalProcessor   rtrec.SignalProcessor
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

func (p *RecommendFeatureProjector) Name() string { return "RecommendFeatureProjector" }

func (p *RecommendFeatureProjector) EventTypes() []string {
	return []string{
		"PostCreated", "ContentReacted", "BehaviorBatchReported",
		"UserFollowed", "CircleMemberJoined",
	}
}

func (p *RecommendFeatureProjector) Project(ctx context.Context, event ProjectorEvent) error {
	switch event.Type {
	case "PostCreated":
		return p.onPostCreated(ctx, event)
	case "BehaviorBatchReported":
		return p.onBehaviorBatch(ctx, event)
	case "ContentReacted":
		return p.onContentReacted(ctx, event)
	case "UserFollowed":
		return p.onUserFollowed(ctx, event)
	case "CircleMemberJoined":
		return p.onCircleMemberJoined(ctx, event)
	default:
		return nil
	}
}

func (p *RecommendFeatureProjector) onPostCreated(ctx context.Context, event ProjectorEvent) error {
	userID := strVal(event.Payload, "authorId")
	if userID == "" {
		userID = strVal(event.Payload, "userId")
	}
	if userID == "" {
		return nil
	}

	contentType := strVal(event.Payload, "contentType")
	tags := anySlice(event.Payload, "tags")
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

	events, ok := event.Payload["events"].([]any)
	if !ok || len(events) == 0 {
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

	for _, raw := range events {
		ev, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		tags := anySlice(ev, "tags")
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

		if contentType != "" {
			if action == "impression" || action == "dwell" {
				typeImpressions[contentType]++
			}
			if depth >= 2 || action == "like" || action == "share" || action == "comment" {
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
	_, err := p.coll.UpdateOne(ctx, bson.M{"userId": userID}, update, opts)
	return err
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

func (p *RecommendFeatureProjector) onContentReacted(ctx context.Context, event ProjectorEvent) error {
	userID := strVal(event.Payload, "userId")
	if userID == "" {
		return nil
	}

	contentID := strVal(event.Payload, "contentId")
	tags := anySlice(event.Payload, "tags")

	inc := bson.M{}
	if boolVal(event.Payload, "liked") {
		inc["userFeatures.totalLikes"] = 1
		p.injectSignal(ctx, userID, contentID, "like", tags)
	}
	if boolVal(event.Payload, "favorited") {
		inc["userFeatures.totalFavorites"] = 1
		p.injectSignal(ctx, userID, contentID, "favorite", tags)
	}
	if boolVal(event.Payload, "shared") {
		inc["userFeatures.totalShares"] = 1
		p.injectSignal(ctx, userID, contentID, "share", tags)
	}

	if len(inc) == 0 {
		return nil
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

func (p *RecommendFeatureProjector) onUserFollowed(ctx context.Context, event ProjectorEvent) error {
	userID := strVal(event.Payload, "followerId")
	if userID == "" {
		userID = strVal(event.Payload, "userId")
	}
	if userID == "" {
		return nil
	}

	update := bson.M{
		"$inc": bson.M{
			"userFeatures.socialInterestScore": 0.1,
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
	UserID             string                `bson:"userId"`
	TagInteraction     map[string]int        `bson:"tagInteraction"`
	AuthorInteraction  map[string]int        `bson:"authorInteraction"`
	TotalEvents        int                   `bson:"totalEvents"`
	TotalLikes         int                   `bson:"totalLikes"`
	TotalFavorites     int                   `bson:"totalFavorites"`
	TotalShares        int                   `bson:"totalShares"`
	TopicAffinities    map[string]float64    `bson:"topicAffinities"`
	AudienceAffinities map[string]float64    `bson:"audienceAffinities"`
	FormatAffinities   map[string]float64    `bson:"formatAffinities"`
	EntityAffinities   map[string]float64    `bson:"entityAffinities"`
	AvgEngagementDepth float64               `bson:"avgEngagementDepth"`
	DepthDistribution  map[string]int        `bson:"depthDistribution"`
	SourceDistribution map[string]int        `bson:"sourceDistribution"`
	CircleTagAffinities map[string]float64   `bson:"circleTagAffinities"`
	SocialInterestScore float64              `bson:"socialInterestScore"`
	EntityInstanceAffinities map[string]float64 `bson:"entityInstanceAffinities"`
	TypeImpressions    map[string]int        `bson:"typeImpressions"`
	TypeEngagements    map[string]int        `bson:"typeEngagements"`
}

func (s *FeatureStore) GetUserFeatures(ctx context.Context, userID string) (*UserFeatures, error) {
	var doc struct {
		UserID       string `bson:"userId"`
		UserFeatures struct {
			TagInteraction     map[string]int     `bson:"tagInteraction"`
			AuthorInteraction  map[string]int     `bson:"authorInteraction"`
			TotalEvents        int                `bson:"totalEvents"`
			TotalLikes         int                `bson:"totalLikes"`
			TotalFavorites     int                `bson:"totalFavorites"`
			TotalShares        int                `bson:"totalShares"`
			TopicAffinities    map[string]float64 `bson:"topicAffinities"`
			AudienceAffinities map[string]float64 `bson:"audienceAffinities"`
			FormatAffinities   map[string]float64 `bson:"formatAffinities"`
			EntityAffinities   map[string]float64 `bson:"entityAffinities"`
			AvgEngagementDepth float64            `bson:"avgEngagementDepth"`
			DepthDistribution  map[string]int     `bson:"depthDistribution"`
			SourceDistribution map[string]int     `bson:"sourceDistribution"`
			CircleTagAffinities  map[string]float64 `bson:"circleTagAffinities"`
			SocialInterestScore  float64            `bson:"socialInterestScore"`
			EntityInstanceAffinities map[string]float64 `bson:"entityInstanceAffinities"`
			TypeImpressions    map[string]int `bson:"typeImpressions"`
			TypeEngagements    map[string]int `bson:"typeEngagements"`
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
		TagInteraction:           doc.UserFeatures.TagInteraction,
		AuthorInteraction:        doc.UserFeatures.AuthorInteraction,
		TotalEvents:              doc.UserFeatures.TotalEvents,
		TotalLikes:               doc.UserFeatures.TotalLikes,
		TotalFavorites:           doc.UserFeatures.TotalFavorites,
		TotalShares:              doc.UserFeatures.TotalShares,
		TopicAffinities:          doc.UserFeatures.TopicAffinities,
		AudienceAffinities:       doc.UserFeatures.AudienceAffinities,
		FormatAffinities:         doc.UserFeatures.FormatAffinities,
		EntityAffinities:         doc.UserFeatures.EntityAffinities,
		AvgEngagementDepth:       doc.UserFeatures.AvgEngagementDepth,
		DepthDistribution:        doc.UserFeatures.DepthDistribution,
		SourceDistribution:       doc.UserFeatures.SourceDistribution,
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
		engagementRate = float64(raw.TotalLikes+raw.TotalFavorites+raw.TotalShares) / float64(raw.TotalEvents)
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

	vec := &rtrec.UserFeatureVector{
		TagAffinities:            tagAffinities,
		AuthorAffinities:         authorAffinities,
		TotalLikes:               raw.TotalLikes,
		TotalFavorites:           raw.TotalFavorites,
		TotalShares:              raw.TotalShares,
		TotalEvents:              raw.TotalEvents,
		EngagementRate:           engagementRate,
		LikeLevel:                rtrec.MapCountToLevel(raw.TotalLikes),
		FavoriteLevel:            rtrec.MapCountToLevel(raw.TotalFavorites),
		ShareLevel:               rtrec.MapCountToLevel(raw.TotalShares),
		EventLevel:               rtrec.MapCountToLevel(raw.TotalEvents),
		TopicAffinities:          raw.TopicAffinities,
		AudienceAffinities:       raw.AudienceAffinities,
		FormatAffinities:         raw.FormatAffinities,
		EntityAffinities:         raw.EntityAffinities,
		EntityInstanceAffinities: raw.EntityInstanceAffinities,
		TypeENER:                 typeENER,
		AvgEngagementDepth:       raw.AvgEngagementDepth,
		DepthDistribution:        depthDist,
		SourceDistribution:       raw.SourceDistribution,
		CircleTagAffinities:      raw.CircleTagAffinities,
		SocialInterestScore:      raw.SocialInterestScore,
	}
	s.cache.put(userID, vec)
	return vec, nil
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
