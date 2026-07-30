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

// MongoCandidateSource reads candidates from the rm_discovery_feed projection.
// Aligned with contracts/metadata/_projections/discovery_feed.yaml.
type MongoCandidateSource struct {
	coll *mongo.Collection
}

func NewMongoCandidateSource(db *mongo.Database) *MongoCandidateSource {
	return &MongoCandidateSource{coll: db.Collection("rm_discovery_feed")}
}

func (s *MongoCandidateSource) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 60
	}

	filter := bson.M{}
	applyReleaseServingEligibility(filter, req.ActiveReleaseID, req.ActiveManifestDigest)
	if len(req.Tags) > 0 {
		filter["tagRefs"] = bson.M{"$in": req.Tags}
	}
	applyVerticalFilter(filter, req.Vertical)

	opts := options.Find().
		SetSort(bson.D{
			{Key: "recScore", Value: -1},
			{Key: "publishedAt", Value: -1},
			{Key: "postId", Value: -1},
		}).
		SetLimit(int64(limit))

	candidates, err := queryDiscoveryFeed(ctx, s.coll, filter, opts, "mongo_discovery")
	if err != nil || strings.TrimSpace(req.ActiveReleaseID) == "" {
		return candidates, err
	}

	// The blended query deliberately preserves UGC. Its limit can therefore be
	// filled by high-scoring UGC before any canonical item is seen. Fetch one
	// exact release+digest anchor independently, before source quota/pre-rank,
	// so the engine can reserve a first-page slot without making the whole feed
	// canonical-only.
	anchorFilter := bson.M{}
	applyCanonicalReleaseFilter(
		anchorFilter,
		req.ActiveReleaseID,
		req.ActiveManifestDigest,
	)
	applyVerticalFilter(anchorFilter, req.Vertical)
	anchors, anchorErr := queryDiscoveryFeed(
		ctx,
		s.coll,
		anchorFilter,
		options.Find().
			SetSort(bson.D{
				{Key: "recScore", Value: -1},
				{Key: "publishedAt", Value: -1},
				{Key: "postId", Value: -1},
			}).
			SetLimit(1),
		"mongo_discovery",
	)
	if anchorErr != nil {
		return nil, anchorErr
	}
	if len(anchors) == 0 || containsCandidateID(candidates, anchors[0].ContentID) {
		return candidates, nil
	}
	return append(candidates, anchors[0]), nil
}

func applyReleaseServingEligibility(
	filter bson.M,
	activeReleaseID string,
	activeManifestDigest string,
) {
	filter["status"] = "published"
	filter["visibility"] = "public"
	filter["accountRestricted"] = bson.M{"$ne": true}
	activeReleaseID = strings.TrimSpace(activeReleaseID)
	if activeReleaseID == "" {
		return
	}
	canonical := canonicalReleasePredicate(activeReleaseID, activeManifestDigest)
	filter["$or"] = bson.A{
		bson.M{"$and": bson.A{
			bson.M{"sourceOwner": bson.M{"$ne": "qwq_data"}},
			bson.M{"supplySource": bson.M{"$ne": "data_engineering"}},
		}},
		canonical,
	}
}

func applyCanonicalReleaseFilter(
	filter bson.M,
	activeReleaseID string,
	activeManifestDigest string,
) {
	for key, value := range canonicalReleasePredicate(activeReleaseID, activeManifestDigest) {
		filter[key] = value
	}
	filter["status"] = "published"
	filter["visibility"] = "public"
	filter["accountRestricted"] = bson.M{"$ne": true}
}

func canonicalReleasePredicate(activeReleaseID, activeManifestDigest string) bson.M {
	predicate := bson.M{
		"sourceOwner":     "qwq_data",
		"releaseId":       strings.TrimSpace(activeReleaseID),
		"lifecycleStatus": "active",
	}
	if activeManifestDigest = strings.TrimSpace(activeManifestDigest); activeManifestDigest != "" {
		predicate["manifestDigest"] = activeManifestDigest
	}
	return predicate
}

func containsCandidateID(candidates []rtrec.ContentCandidate, contentID string) bool {
	contentID = strings.TrimSpace(contentID)
	for _, candidate := range candidates {
		if strings.TrimSpace(candidate.ContentID) == contentID {
			return true
		}
	}
	return false
}

type discoveryFeedDoc struct {
	PostID                      string    `bson:"postId"`
	ContentType                 string    `bson:"contentType"`
	AuthorID                    string    `bson:"authorId"`
	Title                       string    `bson:"title"`
	Tags                        []string  `bson:"tagRefs"`
	EntityRefs                  []string  `bson:"entityRefs"`
	CoverURL                    string    `bson:"coverUrl"`
	LikeCount                   int64     `bson:"likeCount"`
	CommentCount                int64     `bson:"commentCount"`
	ShareCount                  int64     `bson:"shareCount"`
	ViewCount                   int64     `bson:"viewCount"`
	PublishedAt                 time.Time `bson:"publishedAt"`
	RecScore                    float64   `bson:"recScore"`
	QualityScore                float64   `bson:"qualityScore"`
	ContentVertical             string    `bson:"contentVertical"`
	SupplySource                string    `bson:"supplySource"`
	SourceOwner                 string    `bson:"sourceOwner"`
	ReleaseID                   string    `bson:"releaseId"`
	ManifestDigest              string    `bson:"manifestDigest"`
	LifecycleStatus             string    `bson:"lifecycleStatus"`
	IntersectionFactStrength    float64   `bson:"intersectionFactStrength"`
	IntersectionFreshness       float64   `bson:"intersectionFreshness"`
	AffinityIntersectionScore   float64   `bson:"affinityIntersectionScore"`
	IntersectionSourceRefTop    string    `bson:"intersectionSourceRefTop"`
	IntersectionConfidenceLabel string    `bson:"intersectionConfidenceLabel"`
	IntersectionClass           string    `bson:"intersectionClass"`
}

func candidateFromDiscoveryDoc(doc discoveryFeedDoc, recallPath string) rtrec.ContentCandidate {
	qualityScore := doc.QualityScore
	if qualityScore <= 0 {
		qualityScore = doc.RecScore
	}
	return rtrec.ContentCandidate{
		ContentID:                   doc.PostID,
		ContentType:                 doc.ContentType,
		AuthorID:                    doc.AuthorID,
		Title:                       doc.Title,
		Tags:                        doc.Tags,
		EntityRefs:                  doc.EntityRefs,
		PublishedAt:                 doc.PublishedAt,
		ViewCount:                   doc.ViewCount,
		LikeCount:                   doc.LikeCount,
		CommentCount:                doc.CommentCount,
		ShareCount:                  doc.ShareCount,
		RecallPath:                  recallPath,
		QualityScore:                qualityScore,
		ContentVertical:             doc.ContentVertical,
		SupplySource:                doc.SupplySource,
		SourceOwner:                 doc.SourceOwner,
		ReleaseID:                   doc.ReleaseID,
		ManifestDigest:              doc.ManifestDigest,
		LifecycleStatus:             doc.LifecycleStatus,
		IntersectionFactStrength:    doc.IntersectionFactStrength,
		IntersectionFreshness:       doc.IntersectionFreshness,
		AffinityIntersectionScore:   doc.AffinityIntersectionScore,
		IntersectionSourceRefTop:    doc.IntersectionSourceRefTop,
		IntersectionConfidenceLabel: doc.IntersectionConfidenceLabel,
		IntersectionClass:           doc.IntersectionClass,
	}
}
