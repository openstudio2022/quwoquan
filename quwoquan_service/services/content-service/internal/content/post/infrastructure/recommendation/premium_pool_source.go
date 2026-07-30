package recommendation

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

const (
	PremiumPoolRecallPath       = "premium_pool"
	PremiumPoolProjectionID     = "premium_pool_projection"
	PremiumPoolQualityThreshold = 0.75
)

// PremiumPoolProjectionInput is the content-service projection input for a
// product-ops global premium entry. It mirrors only the recommendation-readable
// fields and deliberately excludes control-plane-only data.
type PremiumPoolProjectionInput struct {
	ContentID        string
	Scope            string
	Status           string
	QualityAdmission string
	QualityScore     float64
	SupplySource     string
	SourceTaskID     string
	AuditID          string
	RollbackToken    string
	FeaturedAt       time.Time
	ExpiresAt        time.Time
	TakedownEjected  bool
	UpdatedAt        time.Time
}

// BuildPremiumPoolProjectionFields projects product-ops premium entries into a
// fail-closed read model. The read path only admits eligibilityState=eligible.
func BuildPremiumPoolProjectionFields(in PremiumPoolProjectionInput, now time.Time) bson.M {
	if now.IsZero() {
		now = time.Now().UTC()
	}
	featuredAt := in.FeaturedAt
	if featuredAt.IsZero() {
		featuredAt = now
	}
	updatedAt := in.UpdatedAt
	if updatedAt.IsZero() {
		updatedAt = now
	}
	scope := normalizePremiumPoolToken(in.Scope)
	if scope == "" {
		scope = "global"
	}
	status := normalizePremiumPoolToken(in.Status)
	if status == "" {
		status = "active"
	}
	admission := normalizePremiumPoolToken(in.QualityAdmission)
	reasons := premiumPoolIneligibleReasons(in, scope, status, admission, now)
	eligibility := "eligible"
	if len(reasons) > 0 {
		eligibility = "ineligible"
	}
	return bson.M{
		"contentId":         strings.TrimSpace(in.ContentID),
		"scope":             scope,
		"status":            status,
		"eligibilityState":  eligibility,
		"ineligibleReasons": reasons,
		"qualityAdmission":  admission,
		"qualityScore":      in.QualityScore,
		"supplySource":      strings.TrimSpace(in.SupplySource),
		"sourceTaskId":      strings.TrimSpace(in.SourceTaskID),
		"auditId":           strings.TrimSpace(in.AuditID),
		"rollbackToken":     strings.TrimSpace(in.RollbackToken),
		"featuredAt":        featuredAt.UTC(),
		"expiresAt":         in.ExpiresAt.UTC(),
		"takedownEjected":   in.TakedownEjected,
		"projectionId":      PremiumPoolProjectionID,
		"updatedAt":         updatedAt.UTC(),
	}
}

func premiumPoolIneligibleReasons(in PremiumPoolProjectionInput, scope, status, admission string, now time.Time) []string {
	var reasons []string
	if strings.TrimSpace(in.ContentID) == "" {
		reasons = append(reasons, "missing_content_id")
	}
	if scope != "global" {
		reasons = append(reasons, "non_global_scope")
	}
	if status != "active" {
		reasons = append(reasons, "inactive_status")
	}
	if admission != "approved" {
		reasons = append(reasons, "quality_admission_not_approved")
	}
	if in.QualityScore < PremiumPoolQualityThreshold {
		reasons = append(reasons, "quality_score_below_threshold")
	}
	if in.ExpiresAt.IsZero() || !in.ExpiresAt.After(now) {
		reasons = append(reasons, "expired")
	}
	if in.TakedownEjected {
		reasons = append(reasons, "takedown_ejected")
	}
	return reasons
}

func normalizePremiumPoolToken(raw string) string {
	return strings.TrimSpace(strings.ToLower(raw))
}

// PremiumPoolCandidateReader reads an already-materialized premium pool. It is
// intentionally a content-service read-model boundary, not a product-ops client.
type PremiumPoolCandidateReader interface {
	ActivePremiumCandidates(
		ctx context.Context,
		now time.Time,
		activeReleaseID string,
		activeManifestDigest string,
		limit int,
	) ([]rtrec.ContentCandidate, error)
}

type premiumStreamGateSource struct {
	source       rtrec.CandidateSource
	allowPremium bool
}

// GatePremiumStreamSource 保持精品流 fail-closed：当 feed route 解析为
// premium_stream 时，只有 PremiumPoolSource 能贡献候选；其他 feed 仍按原源召回。
func GatePremiumStreamSource(source rtrec.CandidateSource) rtrec.CandidateSource {
	if source == nil {
		return nil
	}
	_, allowPremium := source.(*PremiumPoolSource)
	return premiumStreamGateSource{source: source, allowPremium: allowPremium}
}

func (s premiumStreamGateSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if premiumPoolRoute(req) && !s.allowPremium {
		rtrec.RecordFeedGateFiltered("premium_stream", 1)
		return nil, rtrec.SkipRecall("source is not applicable to premium stream")
	}
	return s.source.Recall(ctx, req)
}

type PremiumPoolSource struct {
	reader PremiumPoolCandidateReader
	now    func() time.Time
}

func NewPremiumPoolSource(reader PremiumPoolCandidateReader) *PremiumPoolSource {
	return &PremiumPoolSource{
		reader: reader,
		now:    func() time.Time { return time.Now().UTC() },
	}
}

func (s *PremiumPoolSource) SetNow(now func() time.Time) {
	if s == nil || now == nil {
		return
	}
	s.now = now
}

func (s *PremiumPoolSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if s == nil || !premiumPoolRoute(req) {
		return nil, rtrec.SkipRecall("premium pool is not applicable to this route")
	}
	if s.reader == nil {
		return nil, fmt.Errorf("premium pool candidate reader is unavailable")
	}
	activeReleaseID := strings.TrimSpace(req.ActiveReleaseID)
	activeManifestDigest := strings.TrimSpace(req.ActiveManifestDigest)
	if activeReleaseID == "" || activeManifestDigest == "" {
		return nil, fmt.Errorf("premium pool recall requires active release id and manifest digest")
	}
	limit := req.Limit
	if limit <= 0 {
		limit = 30
	}
	items, err := s.reader.ActivePremiumCandidates(
		ctx,
		s.now(),
		activeReleaseID,
		activeManifestDigest,
		limit,
	)
	if err != nil {
		return nil, err
	}
	for i := range items {
		items[i].RecallPath = PremiumPoolRecallPath
	}
	return items, nil
}

func premiumPoolRoute(req rtrec.RecallRequest) bool {
	switch strings.TrimSpace(strings.ToLower(req.Surface)) {
	case "premium_stream":
		return true
	}
	return req.FeedType == rtrec.FeedSimilar
}

type MongoPremiumPoolCandidateReader struct {
	poolColl  *mongo.Collection
	feedColl  *mongo.Collection
	postsColl *mongo.Collection
}

func NewMongoPremiumPoolCandidateReader(db *mongo.Database) *MongoPremiumPoolCandidateReader {
	if db == nil {
		return nil
	}
	return &MongoPremiumPoolCandidateReader{
		poolColl:  db.Collection("rm_premium_pool"),
		feedColl:  db.Collection("rm_discovery_feed"),
		postsColl: db.Collection("posts"),
	}
}

func (r *MongoPremiumPoolCandidateReader) ActivePremiumCandidates(
	ctx context.Context,
	now time.Time,
	activeReleaseID string,
	activeManifestDigest string,
	limit int,
) ([]rtrec.ContentCandidate, error) {
	if r == nil || r.poolColl == nil || r.feedColl == nil || limit <= 0 {
		return nil, nil
	}
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	activeManifestDigest = strings.TrimSpace(activeManifestDigest)
	if activeReleaseID == "" || activeManifestDigest == "" {
		return nil, fmt.Errorf("premium pool candidate read requires active release id and manifest digest")
	}
	entries, err := r.activePremiumEntries(
		ctx,
		now,
		activeReleaseID,
		activeManifestDigest,
		limit*2,
	)
	if err != nil {
		return nil, err
	}
	if len(entries) == 0 {
		return nil, nil
	}
	return r.candidatesForEntries(
		ctx,
		entries,
		activeReleaseID,
		activeManifestDigest,
		limit,
	)
}

func activePremiumPoolFilter(now time.Time) bson.M {
	if now.IsZero() {
		now = time.Now().UTC()
	}
	return bson.M{
		"scope":            "global",
		"status":           "active",
		"eligibilityState": "eligible",
		"qualityAdmission": "approved",
		"qualityScore":     bson.M{"$gte": PremiumPoolQualityThreshold},
		"expiresAt":        bson.M{"$gt": now.UTC()},
		"takedownEjected":  bson.M{"$ne": true},
	}
}

func (r *MongoPremiumPoolCandidateReader) activePremiumEntries(
	ctx context.Context,
	now time.Time,
	activeReleaseID string,
	activeManifestDigest string,
	limit int,
) ([]premiumPoolReadDoc, error) {
	pipeline := mongo.Pipeline{
		bson.D{{Key: "$match", Value: activePremiumPoolFilter(now)}},
		bson.D{{Key: "$lookup", Value: bson.M{
			"from": "rm_discovery_feed",
			"let":  bson.M{"premiumContentId": "$contentId"},
			"pipeline": mongo.Pipeline{
				bson.D{{Key: "$match", Value: bson.M{
					"$expr":             bson.M{"$eq": bson.A{"$postId", "$$premiumContentId"}},
					"sourceOwner":       "qwq_data",
					"releaseId":         activeReleaseID,
					"manifestDigest":    activeManifestDigest,
					"lifecycleStatus":   "active",
					"status":            "published",
					"visibility":        "public",
					"accountRestricted": bson.M{"$ne": true},
				}}},
				bson.D{{Key: "$project", Value: bson.M{"_id": 1}}},
			},
			"as": "activeReleaseFeed",
		}}},
		bson.D{{Key: "$match", Value: bson.M{
			"activeReleaseFeed.0": bson.M{"$exists": true},
		}}},
		bson.D{{Key: "$sort", Value: bson.D{
			{Key: "qualityScore", Value: -1},
			{Key: "featuredAt", Value: -1},
			{Key: "contentId", Value: -1},
		}}},
	}
	if limit > 0 {
		pipeline = append(pipeline, bson.D{{Key: "$limit", Value: int64(limit)}})
	}
	pipeline = append(pipeline, bson.D{{Key: "$project", Value: bson.M{
		"contentId": 1, "qualityScore": 1, "supplySource": 1,
	}}})
	cursor, err := r.poolColl.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var entries []premiumPoolReadDoc
	if err := cursor.All(ctx, &entries); err != nil {
		return nil, err
	}
	return entries, nil
}

type premiumPoolReadDoc struct {
	ContentID    string  `bson:"contentId"`
	QualityScore float64 `bson:"qualityScore"`
	SupplySource string  `bson:"supplySource"`
}

// CountActiveReleasePlayableVideos reuses the exact premium eligibility
// predicate used by recall, then proves that every counted id joins to both an
// active discovery projection and a playable hydrated Post in the requested
// canonical release.
func (r *MongoPremiumPoolCandidateReader) CountActiveReleasePlayableVideos(
	ctx context.Context,
	activeReleaseID string,
	manifestDigest string,
) (int64, error) {
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	manifestDigest = strings.TrimSpace(manifestDigest)
	if r == nil || r.poolColl == nil || r.feedColl == nil || r.postsColl == nil {
		return 0, fmt.Errorf("premium playable supply collections are unavailable")
	}
	if activeReleaseID == "" || manifestDigest == "" {
		return 0, nil
	}
	cursor, err := r.poolColl.Aggregate(ctx, mongo.Pipeline{
		bson.D{{Key: "$match", Value: activePremiumPoolFilter(time.Now().UTC())}},
		bson.D{{Key: "$group", Value: bson.M{"_id": "$contentId"}}},
		bson.D{{Key: "$lookup", Value: bson.M{
			"from": "rm_discovery_feed", "localField": "_id", "foreignField": "postId", "as": "feed",
		}}},
		bson.D{{Key: "$unwind", Value: "$feed"}},
		bson.D{{Key: "$match", Value: bson.M{
			"feed.sourceOwner": "qwq_data", "feed.releaseId": activeReleaseID,
			"feed.manifestDigest":  manifestDigest,
			"feed.lifecycleStatus": "active", "feed.status": "published",
			"feed.visibility": "public", "feed.accountRestricted": bson.M{"$ne": true},
			"feed.contentIdentity": "work", "feed.contentType": "video",
		}}},
		bson.D{{Key: "$lookup", Value: bson.M{
			"from": "posts", "localField": "_id", "foreignField": "_id", "as": "post",
		}}},
		bson.D{{Key: "$unwind", Value: "$post"}},
		bson.D{{Key: "$match", Value: bson.M{
			"post.sourceOwner": "qwq_data", "post.releaseId": activeReleaseID,
			"post.manifestDigest":  manifestDigest,
			"post.lifecycleStatus": "active", "post.status": "published",
			"post.visibility": "public", "post.moderationStatus": "approved",
			"post.accountRestricted": bson.M{"$ne": true},
			"post.contentIdentity":   "work", "post.contentType": "video",
			"post.videoUrl":   bson.M{"$type": "string", "$ne": ""},
			"post.durationMs": bson.M{"$gt": 0},
		}}},
		bson.D{{Key: "$count", Value: "count"}},
	})
	if err != nil {
		return 0, err
	}
	defer cursor.Close(ctx)
	var result struct {
		Count int64 `bson:"count"`
	}
	if !cursor.Next(ctx) {
		if err := cursor.Err(); err != nil {
			return 0, err
		}
		return 0, nil
	}
	if err := cursor.Decode(&result); err != nil {
		return 0, err
	}
	return result.Count, nil
}

func (r *MongoPremiumPoolCandidateReader) candidatesForEntries(
	ctx context.Context,
	entries []premiumPoolReadDoc,
	activeReleaseID string,
	activeManifestDigest string,
	limit int,
) ([]rtrec.ContentCandidate, error) {
	ids := make([]string, 0, len(entries))
	byID := make(map[string]premiumPoolReadDoc, len(entries))
	for _, entry := range entries {
		id := strings.TrimSpace(entry.ContentID)
		if id == "" {
			continue
		}
		if _, ok := byID[id]; ok {
			continue
		}
		byID[id] = entry
		ids = append(ids, id)
	}
	if len(ids) == 0 {
		return nil, nil
	}
	filter := bson.M{"postId": bson.M{"$in": ids}}
	applyCanonicalReleaseFilter(filter, activeReleaseID, activeManifestDigest)
	candidates, err := queryDiscoveryFeed(
		ctx,
		r.feedColl,
		filter,
		options.Find().SetLimit(int64(limit*2)),
		PremiumPoolRecallPath,
	)
	if err != nil {
		return nil, err
	}
	order := make(map[string]int, len(ids))
	for i, id := range ids {
		order[id] = i
	}
	sortCandidatesByMaterializedOrder(candidates, order)
	for i := range candidates {
		entry := byID[candidates[i].ContentID]
		candidates[i].RecallPath = PremiumPoolRecallPath
		if candidates[i].QualityScore <= 0 {
			candidates[i].QualityScore = entry.QualityScore
		}
		if strings.TrimSpace(candidates[i].SupplySource) == "" {
			candidates[i].SupplySource = entry.SupplySource
		}
	}
	if len(candidates) > limit {
		candidates = candidates[:limit]
	}
	return candidates, nil
}
