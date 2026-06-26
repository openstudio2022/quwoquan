package recommendation

import (
	"context"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

const (
	PremiumPoolRecallPath        = "premium_pool"
	PremiumPoolProjectionVersion = "premium_pool_projection_v1"
	PremiumPoolQualityThreshold  = 0.75
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
		"projectionVersion": PremiumPoolProjectionVersion,
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
	ActivePremiumCandidates(ctx context.Context, now time.Time, limit int) ([]rtrec.ContentCandidate, error)
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

func (s *PremiumPoolSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if s == nil || s.reader == nil || !premiumPoolRoute(req) {
		return nil, nil
	}
	limit := req.Limit
	if limit <= 0 {
		limit = 30
	}
	items, err := s.reader.ActivePremiumCandidates(ctx, s.now(), limit)
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
	poolColl *mongo.Collection
	feedColl *mongo.Collection
}

func NewMongoPremiumPoolCandidateReader(db *mongo.Database) *MongoPremiumPoolCandidateReader {
	return &MongoPremiumPoolCandidateReader{
		poolColl: db.Collection("rm_premium_pool"),
		feedColl: db.Collection("rm_discovery_feed"),
	}
}

func (r *MongoPremiumPoolCandidateReader) ActivePremiumCandidates(ctx context.Context, now time.Time, limit int) ([]rtrec.ContentCandidate, error) {
	if r == nil || r.poolColl == nil || r.feedColl == nil || limit <= 0 {
		return nil, nil
	}
	cursor, err := r.poolColl.Find(ctx,
		bson.M{
			"scope":            "global",
			"status":           "active",
			"eligibilityState": "eligible",
			"qualityAdmission": "approved",
			"qualityScore":     bson.M{"$gte": PremiumPoolQualityThreshold},
			"expiresAt":        bson.M{"$gt": now.UTC()},
			"takedownEjected":  bson.M{"$ne": true},
		},
		options.Find().
			SetSort(bson.D{{Key: "qualityScore", Value: -1}, {Key: "featuredAt", Value: -1}}).
			SetLimit(int64(limit*2)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var entries []premiumPoolReadDoc
	if err := cursor.All(ctx, &entries); err != nil {
		return nil, err
	}
	if len(entries) == 0 {
		return nil, nil
	}
	return r.candidatesForEntries(ctx, entries, limit)
}

type premiumPoolReadDoc struct {
	ContentID    string  `bson:"contentId"`
	QualityScore float64 `bson:"qualityScore"`
	SupplySource string  `bson:"supplySource"`
}

func (r *MongoPremiumPoolCandidateReader) candidatesForEntries(ctx context.Context, entries []premiumPoolReadDoc, limit int) ([]rtrec.ContentCandidate, error) {
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
	candidates, err := queryDiscoveryFeed(
		ctx,
		r.feedColl,
		bson.M{"postId": bson.M{"$in": ids}},
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
