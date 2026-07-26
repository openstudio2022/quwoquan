package recommendation

import (
	"context"
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
	if len(req.Tags) > 0 {
		filter["tagRefs"] = bson.M{"$in": req.Tags}
	}
	applyVerticalFilter(filter, req.Vertical)

	opts := options.Find().
		SetSort(bson.D{{Key: "recScore", Value: -1}, {Key: "publishedAt", Value: -1}}).
		SetLimit(int64(limit))

	if req.Cursor != "" {
		filter["_id"] = bson.M{"$lt": req.Cursor}
	}

	return queryDiscoveryFeed(ctx, s.coll, filter, opts, "mongo_discovery")
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
		IntersectionFactStrength:    doc.IntersectionFactStrength,
		IntersectionFreshness:       doc.IntersectionFreshness,
		AffinityIntersectionScore:   doc.AffinityIntersectionScore,
		IntersectionSourceRefTop:    doc.IntersectionSourceRefTop,
		IntersectionConfidenceLabel: doc.IntersectionConfidenceLabel,
		IntersectionClass:           doc.IntersectionClass,
	}
}
