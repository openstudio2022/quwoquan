package recommendation

import (
	"context"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtrec "quwoquan_service/runtime/recommendation"
)

// VectorRecallSource retrieves semantically similar content via Atlas Vector Search.
// Aligned with contracts/metadata/_vectors/content_embedding.yaml.
//
// Requires the Atlas search index "vector_posts_embedding" on the posts collection:
//
//	{
//	  "fields": [{"type":"vector","path":"embedding","numDimensions":1536,"similarity":"cosine"}]
//	}
type VectorRecallSource struct {
	coll      *mongo.Collection
	indexName string
}

func NewVectorRecallSource(db *mongo.Database) *VectorRecallSource {
	return &VectorRecallSource{
		coll:      db.Collection("posts"),
		indexName: "vector_posts_embedding",
	}
}

// EmbeddingProvider generates vector embeddings for text input.
type EmbeddingProvider interface {
	Embed(ctx context.Context, text string) ([]float64, error)
}

// VectorRecallWithEmbedding pairs VectorRecallSource with an embedding provider.
type VectorRecallWithEmbedding struct {
	source   *VectorRecallSource
	embedder EmbeddingProvider
}

func NewVectorRecallWithEmbedding(db *mongo.Database, embedder EmbeddingProvider) *VectorRecallWithEmbedding {
	return &VectorRecallWithEmbedding{
		source:   NewVectorRecallSource(db),
		embedder: embedder,
	}
}

func (v *VectorRecallWithEmbedding) Recall(ctx context.Context, req rtrec.RecallRequest) ([]rtrec.ContentCandidate, error) {
	if v.embedder == nil || len(req.Tags) == 0 {
		return nil, nil
	}

	queryText := ""
	for _, t := range req.Tags {
		if queryText != "" {
			queryText += " "
		}
		queryText += t
	}

	embedding, err := v.embedder.Embed(ctx, queryText)
	if err != nil {
		return nil, nil
	}

	return v.source.RecallByVector(ctx, embedding, req.Limit)
}

// RecallByVector performs Atlas Vector Search with a pre-computed query vector.
func (s *VectorRecallSource) RecallByVector(ctx context.Context, queryVector []float64, limit int) ([]rtrec.ContentCandidate, error) {
	if limit <= 0 {
		limit = 20
	}

	pipeline := bson.A{
		bson.M{
			"$vectorSearch": bson.M{
				"index":         s.indexName,
				"path":          "embedding",
				"queryVector":   queryVector,
				"numCandidates": limit * 5,
				"limit":         limit,
			},
		},
		bson.M{
			"$project": bson.M{
				"_id":          1,
				"authorId":     1,
				"contentType":  1,
				"title":        1,
				"tags":         1,
				"entityRefs":   1,
				"publishedAt":  1,
				"viewCount":    1,
				"likeCount":    1,
				"commentCount": 1,
				"shareCount":   1,
				"score":        bson.M{"$meta": "vectorSearchScore"},
			},
		},
	}

	cursor, err := s.coll.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	type vectorDoc struct {
		ID           string    `bson:"_id"`
		AuthorID     string    `bson:"authorId"`
		ContentType  string    `bson:"contentType"`
		Title        string    `bson:"title"`
		Tags         []string  `bson:"tags"`
		EntityRefs   []string  `bson:"entityRefs"`
		PublishedAt  time.Time `bson:"publishedAt"`
		ViewCount    int64     `bson:"viewCount"`
		LikeCount    int64     `bson:"likeCount"`
		CommentCount int64     `bson:"commentCount"`
		ShareCount   int64     `bson:"shareCount"`
		Score        float64   `bson:"score"`
	}

	var docs []vectorDoc
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, err
	}

	out := make([]rtrec.ContentCandidate, 0, len(docs))
	for _, doc := range docs {
		out = append(out, rtrec.ContentCandidate{
			ContentID:    doc.ID,
			ContentType:  doc.ContentType,
			AuthorID:     doc.AuthorID,
			Title:        doc.Title,
			Tags:         doc.Tags,
			EntityRefs:   doc.EntityRefs,
			PublishedAt:  doc.PublishedAt,
			ViewCount:    doc.ViewCount,
			LikeCount:    doc.LikeCount,
			CommentCount: doc.CommentCount,
			ShareCount:   doc.ShareCount,
			RecallPath:   "vector_recall",
		})
	}
	return out, nil
}
