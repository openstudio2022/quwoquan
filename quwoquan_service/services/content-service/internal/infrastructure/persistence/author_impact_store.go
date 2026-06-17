package persistence

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const authorImpactCollection = "rm_author_impact"

const (
	AuthorImpactHelpRelationship = "relationship"
	AuthorImpactHelpCommunity    = "community"
	AuthorImpactHelpDecision     = "decision"
	AuthorImpactHelpKnowledge    = "knowledge"
	AuthorImpactHelpSpread       = "spread"
	AuthorImpactHelpAudience     = "audience"
)

// AuthorImpactEvent is the normalized reverse-aggregation event for creator
// explainability. It uses the same action and intersection attribution fields
// as the consumer-side behavior pipeline.
type AuthorImpactEvent struct {
	AuthorID              string
	Action                string
	HelpType              string
	IntersectionDimension string
	IntersectionTagRefs   []string
	Source                string
	OccurredAt            time.Time
}

// AuthorImpactSummary is a compact read model returned to app surfaces.
type AuthorImpactSummary struct {
	AuthorID string             `json:"authorId" bson:"authorId"`
	Total    int64              `json:"total" bson:"total"`
	Items    []AuthorImpactItem `json:"items" bson:"items"`
}

type AuthorImpactItem struct {
	HelpType              string    `json:"helpType" bson:"helpType"`
	Action                string    `json:"action" bson:"action"`
	IntersectionDimension string    `json:"intersectionDimension" bson:"intersectionDimension"`
	TagRef                string    `json:"tagRef" bson:"tagRef"`
	Source                string    `json:"source" bson:"source"`
	Count                 int64     `json:"count" bson:"count"`
	PrimaryText           string    `json:"primaryText" bson:"-"` // 云侧按 viewer 视角产出的影响结论句（端只读直出）
	UpdatedAt             time.Time `json:"updatedAt" bson:"updatedAt"`
}

// AuthorImpactStore maintains rm_author_impact for producer-side explainability.
type AuthorImpactStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewAuthorImpactStore(db *mongo.Database, logger *slog.Logger) *AuthorImpactStore {
	s := &AuthorImpactStore{
		coll:   db.Collection(authorImpactCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *AuthorImpactStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	indexes := []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "helpType", Value: 1},
				{Key: "action", Value: 1},
				{Key: "intersectionDimension", Value: 1},
				{Key: "tagRef", Value: 1},
				{Key: "source", Value: 1},
			},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "authorId", Value: 1}, {Key: "count", Value: -1}},
		},
	}
	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("author_impact: index creation failed", slog.String("error", err.Error()))
		}
	}
}

func (s *AuthorImpactStore) Record(ctx context.Context, event AuthorImpactEvent) error {
	authorID := strings.TrimSpace(event.AuthorID)
	action := strings.TrimSpace(event.Action)
	helpType := strings.TrimSpace(event.HelpType)
	if authorID == "" || action == "" || helpType == "" {
		return nil
	}
	now := event.OccurredAt
	if now.IsZero() {
		now = time.Now().UTC()
	}
	tagRefs := normalizeImpactTags(event.IntersectionTagRefs)
	if len(tagRefs) == 0 {
		tagRefs = []string{""}
	}
	source := strings.TrimSpace(event.Source)
	if source == "" {
		source = "behavior"
	}
	for _, tagRef := range tagRefs {
		filter := bson.M{
			"authorId":              authorID,
			"helpType":              helpType,
			"action":                action,
			"intersectionDimension": strings.TrimSpace(event.IntersectionDimension),
			"tagRef":                tagRef,
			"source":                source,
		}
		update := bson.M{
			"$setOnInsert": bson.M{
				"authorId":              authorID,
				"helpType":              helpType,
				"action":                action,
				"intersectionDimension": strings.TrimSpace(event.IntersectionDimension),
				"tagRef":                tagRef,
				"source":                source,
				"createdAt":             now,
			},
			"$set": bson.M{"updatedAt": now},
			"$inc": bson.M{"count": int64(1)},
		}
		if _, err := s.coll.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true)); err != nil {
			s.logger.Error("author_impact: record failed",
				slog.String("error", err.Error()),
				slog.String("authorId", authorID),
				slog.String("action", action),
			)
			return err
		}
	}
	return nil
}

func (s *AuthorImpactStore) GetSummary(ctx context.Context, authorID string, limit int64) (AuthorImpactSummary, error) {
	if limit <= 0 {
		limit = 12
	}
	summary := AuthorImpactSummary{AuthorID: strings.TrimSpace(authorID)}
	if summary.AuthorID == "" {
		return summary, nil
	}
	cursor, err := s.coll.Find(
		ctx,
		bson.M{"authorId": summary.AuthorID},
		options.Find().SetSort(bson.D{{Key: "count", Value: -1}, {Key: "updatedAt", Value: -1}}).SetLimit(limit),
	)
	if err != nil {
		return summary, err
	}
	defer cursor.Close(ctx)

	for cursor.Next(ctx) {
		var doc struct {
			HelpType              string    `bson:"helpType"`
			Action                string    `bson:"action"`
			IntersectionDimension string    `bson:"intersectionDimension"`
			TagRef                string    `bson:"tagRef"`
			Source                string    `bson:"source"`
			Count                 int64     `bson:"count"`
			UpdatedAt             time.Time `bson:"updatedAt"`
		}
		if err := cursor.Decode(&doc); err != nil {
			return summary, err
		}
		summary.Total += doc.Count
		summary.Items = append(summary.Items, AuthorImpactItem{
			HelpType:              doc.HelpType,
			Action:                doc.Action,
			IntersectionDimension: doc.IntersectionDimension,
			TagRef:                doc.TagRef,
			Source:                doc.Source,
			Count:                 doc.Count,
			UpdatedAt:             doc.UpdatedAt,
		})
	}
	return summary, cursor.Err()
}

func normalizeImpactTags(tags []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(tags))
	for _, tag := range tags {
		trimmed := strings.TrimSpace(tag)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
	}
	return out
}
