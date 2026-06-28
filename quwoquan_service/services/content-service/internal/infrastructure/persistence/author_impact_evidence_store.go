package persistence

import (
	"context"
	"crypto/sha1"
	"encoding/base64"
	"encoding/hex"
	"log/slog"
	"strings"
	"time"

	"quwoquan_service/services/content-service/internal/application/ports"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const authorImpactEvidenceCollection = "rm_author_impact_evidence"

// StableImpactID derives a stable drill-down anchor from the AuthorImpactItem
// aggregation key (authorId|helpType|action|dimension|tagRef|source). The app
// passes this id back to ListAuthorImpactEvidence to page the underlying facts.
func StableImpactID(authorID, helpType, action, dimension, tagRef, source string) string {
	raw := strings.Join([]string{
		strings.TrimSpace(authorID),
		strings.TrimSpace(helpType),
		strings.TrimSpace(action),
		strings.TrimSpace(dimension),
		strings.TrimSpace(tagRef),
		strings.TrimSpace(source),
	}, "|")
	sum := sha1.Sum([]byte(raw))
	return hex.EncodeToString(sum[:])[:20]
}

type AuthorImpactEvidenceRecord = ports.AuthorImpactEvidenceRecord
type AuthorImpactEvidenceRaw = ports.AuthorImpactEvidenceRaw

// AuthorImpactEvidenceStore maintains rm_author_impact_evidence: the paginated,
// idempotent detail behind each rm_author_impact summary row.
type AuthorImpactEvidenceStore struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewAuthorImpactEvidenceStore(db *mongo.Database, logger *slog.Logger) *AuthorImpactEvidenceStore {
	s := &AuthorImpactEvidenceStore{
		coll:   db.Collection(authorImpactEvidenceCollection),
		logger: logger,
	}
	s.ensureIndexes()
	return s
}

func (s *AuthorImpactEvidenceStore) ensureIndexes() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	indexes := []mongo.IndexModel{
		{
			// 分页主索引：按 author + impact 维度，occurredAt 倒序游标分页。
			Keys: bson.D{
				{Key: "authorId", Value: 1},
				{Key: "impactId", Value: 1},
				{Key: "occurredAt", Value: -1},
				{Key: "_id", Value: -1},
			},
		},
		{
			// 幂等唯一键：同一来源行为事件只物化一条 evidence。
			Keys:    bson.D{{Key: "sourceEventId", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
	}
	for _, idx := range indexes {
		if _, err := s.coll.Indexes().CreateOne(ctx, idx); err != nil {
			s.logger.Warn("author_impact_evidence: index creation failed", slog.String("error", err.Error()))
		}
	}
}

// Record idempotently materializes one impact evidence fact. The sourceEventId
// unique key guarantees replayed behavior batches do not double-count.
func (s *AuthorImpactEvidenceStore) Record(ctx context.Context, rec AuthorImpactEvidenceRecord) error {
	authorID := strings.TrimSpace(rec.AuthorID)
	impactID := strings.TrimSpace(rec.ImpactID)
	if authorID == "" || impactID == "" {
		return nil
	}
	now := rec.OccurredAt
	if now.IsZero() {
		now = time.Now().UTC()
	}
	sourceEventID := strings.TrimSpace(rec.SourceEventID)
	if sourceEventID == "" {
		// Deterministic fallback id so the unique key still dedupes replays.
		seed := strings.Join([]string{
			authorID, impactID, strings.TrimSpace(rec.ActorID),
			strings.TrimSpace(rec.ContentID), strings.TrimSpace(rec.Action),
			now.UTC().Format(time.RFC3339Nano),
		}, "|")
		sum := sha1.Sum([]byte(seed))
		sourceEventID = "syn_" + hex.EncodeToString(sum[:])[:24]
	}
	filter := bson.M{"sourceEventId": sourceEventID}
	update := bson.M{
		"$setOnInsert": bson.M{
			"authorId":              authorID,
			"impactId":              impactID,
			"sourceEventId":         sourceEventID,
			"actorId":               strings.TrimSpace(rec.ActorID),
			"contentId":             strings.TrimSpace(rec.ContentID),
			"contentType":           strings.TrimSpace(rec.ContentType),
			"helpType":              strings.TrimSpace(rec.HelpType),
			"action":                strings.TrimSpace(rec.Action),
			"intersectionDimension": strings.TrimSpace(rec.IntersectionDimension),
			"tagRef":                strings.TrimSpace(rec.TagRef),
			"source":                strings.TrimSpace(rec.Source),
			"occurredAt":            now.UTC(),
			"createdAt":             time.Now().UTC(),
		},
	}
	if _, err := s.coll.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true)); err != nil {
		// Duplicate key on the unique sourceEventId is the idempotent happy path.
		if mongo.IsDuplicateKeyError(err) {
			return nil
		}
		s.logger.Error("author_impact_evidence: record failed",
			slog.String("error", err.Error()),
			slog.String("authorId", authorID),
			slog.String("impactId", impactID),
		)
		return err
	}
	return nil
}

// CountByImpact returns the absolute number of evidence facts behind an impact.
func (s *AuthorImpactEvidenceStore) CountByImpact(ctx context.Context, authorID, impactID string) (int64, error) {
	authorID = strings.TrimSpace(authorID)
	impactID = strings.TrimSpace(impactID)
	if authorID == "" || impactID == "" {
		return 0, nil
	}
	return s.coll.CountDocuments(ctx, bson.M{"authorId": authorID, "impactId": impactID})
}

// ListPageWithTotal returns evidence rows and totalCount in one aggregate query
// to avoid the List + Count read amplification on impact drill-down pages.
func (s *AuthorImpactEvidenceStore) ListPageWithTotal(ctx context.Context, authorID, impactID, cursor string, limit int64) ([]AuthorImpactEvidenceRaw, string, bool, int64, error) {
	authorID = strings.TrimSpace(authorID)
	impactID = strings.TrimSpace(impactID)
	if authorID == "" || impactID == "" {
		return nil, "", false, 0, nil
	}
	if limit <= 0 || limit > 50 {
		limit = 20
	}
	filter := bson.M{"authorId": authorID, "impactId": impactID}
	if before, beforeID, ok := decodeEvidenceCursor(cursor); ok {
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$lt": before}},
			bson.M{"occurredAt": before, "_id": bson.M{"$lt": beforeID}},
		}
	}
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: filter}},
		{{Key: "$sort", Value: bson.D{{Key: "occurredAt", Value: -1}, {Key: "_id", Value: -1}}}},
		{{Key: "$facet", Value: bson.M{
			"items": bson.A{bson.M{"$limit": limit + 1}},
			"total": bson.A{bson.M{"$count": "count"}},
		}}},
	}
	cur, err := s.coll.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, "", false, 0, err
	}
	defer cur.Close(ctx)

	type totalDoc struct {
		Count int64 `bson:"count"`
	}
	type evidenceDoc struct {
		ID                    bson.ObjectID `bson:"_id"`
		ImpactID              string        `bson:"impactId"`
		SourceEventID         string        `bson:"sourceEventId"`
		ContentID             string        `bson:"contentId"`
		ContentType           string        `bson:"contentType"`
		HelpType              string        `bson:"helpType"`
		Action                string        `bson:"action"`
		IntersectionDimension string        `bson:"intersectionDimension"`
		OccurredAt            time.Time     `bson:"occurredAt"`
	}
	type facetResult struct {
		Items []evidenceDoc `bson:"items"`
		Total []totalDoc    `bson:"total"`
	}
	if !cur.Next(ctx) {
		if err := cur.Err(); err != nil {
			return nil, "", false, 0, err
		}
		return nil, "", false, 0, nil
	}
	var facet facetResult
	if err := cur.Decode(&facet); err != nil {
		return nil, "", false, 0, err
	}
	total := int64(0)
	if len(facet.Total) > 0 {
		total = facet.Total[0].Count
	}
	hasMore := int64(len(facet.Items)) > limit
	if hasMore {
		facet.Items = facet.Items[:limit]
	}
	raws := make([]AuthorImpactEvidenceRaw, 0, len(facet.Items))
	var lastDoc evidenceDoc
	for _, doc := range facet.Items {
		lastDoc = doc
		evidenceID := strings.TrimSpace(doc.SourceEventID)
		if evidenceID == "" {
			evidenceID = doc.ID.Hex()
		}
		raws = append(raws, AuthorImpactEvidenceRaw{
			EvidenceID:            evidenceID,
			ImpactID:              doc.ImpactID,
			ContentID:             doc.ContentID,
			ContentType:           doc.ContentType,
			HelpType:              doc.HelpType,
			Action:                doc.Action,
			IntersectionDimension: doc.IntersectionDimension,
			OccurredAt:            doc.OccurredAt,
		})
	}
	nextCursor := ""
	if hasMore && len(raws) > 0 {
		nextCursor = encodeEvidenceCursor(lastDoc.OccurredAt, lastDoc.ID)
	}
	return raws, nextCursor, hasMore, total, nil
}

// ListPage returns one cursor page of evidence facts ordered by occurredAt
// descending. The returned nextCursor is opaque (base64 of occurredAt|_id).
func (s *AuthorImpactEvidenceStore) ListPage(ctx context.Context, authorID, impactID, cursor string, limit int64) ([]AuthorImpactEvidenceRaw, string, bool, error) {
	authorID = strings.TrimSpace(authorID)
	impactID = strings.TrimSpace(impactID)
	if authorID == "" || impactID == "" {
		return nil, "", false, nil
	}
	if limit <= 0 || limit > 50 {
		limit = 20
	}
	filter := bson.M{"authorId": authorID, "impactId": impactID}
	if before, beforeID, ok := decodeEvidenceCursor(cursor); ok {
		filter["$or"] = bson.A{
			bson.M{"occurredAt": bson.M{"$lt": before}},
			bson.M{"occurredAt": before, "_id": bson.M{"$lt": beforeID}},
		}
	}
	findOpts := options.Find().
		SetSort(bson.D{{Key: "occurredAt", Value: -1}, {Key: "_id", Value: -1}}).
		SetLimit(limit + 1)
	cur, err := s.coll.Find(ctx, filter, findOpts)
	if err != nil {
		return nil, "", false, err
	}
	defer cur.Close(ctx)

	type evidenceDoc struct {
		ID                    bson.ObjectID `bson:"_id"`
		ImpactID              string        `bson:"impactId"`
		SourceEventID         string        `bson:"sourceEventId"`
		ContentID             string        `bson:"contentId"`
		ContentType           string        `bson:"contentType"`
		HelpType              string        `bson:"helpType"`
		Action                string        `bson:"action"`
		IntersectionDimension string        `bson:"intersectionDimension"`
		OccurredAt            time.Time     `bson:"occurredAt"`
	}
	raws := make([]AuthorImpactEvidenceRaw, 0, limit)
	var lastDoc evidenceDoc
	count := int64(0)
	hasMore := false
	for cur.Next(ctx) {
		var doc evidenceDoc
		if err := cur.Decode(&doc); err != nil {
			return nil, "", false, err
		}
		count++
		if count > limit {
			hasMore = true
			break
		}
		lastDoc = doc
		evidenceID := strings.TrimSpace(doc.SourceEventID)
		if evidenceID == "" {
			evidenceID = doc.ID.Hex()
		}
		raws = append(raws, AuthorImpactEvidenceRaw{
			EvidenceID:            evidenceID,
			ImpactID:              doc.ImpactID,
			ContentID:             doc.ContentID,
			ContentType:           doc.ContentType,
			HelpType:              doc.HelpType,
			Action:                doc.Action,
			IntersectionDimension: doc.IntersectionDimension,
			OccurredAt:            doc.OccurredAt,
		})
	}
	if err := cur.Err(); err != nil {
		return nil, "", false, err
	}
	nextCursor := ""
	if hasMore && len(raws) > 0 {
		nextCursor = encodeEvidenceCursor(lastDoc.OccurredAt, lastDoc.ID)
	}
	return raws, nextCursor, hasMore, nil
}

func encodeEvidenceCursor(occurredAt time.Time, id bson.ObjectID) string {
	raw := occurredAt.UTC().Format(time.RFC3339Nano) + "|" + id.Hex()
	return base64.RawURLEncoding.EncodeToString([]byte(raw))
}

func decodeEvidenceCursor(cursor string) (time.Time, bson.ObjectID, bool) {
	cursor = strings.TrimSpace(cursor)
	if cursor == "" {
		return time.Time{}, bson.NilObjectID, false
	}
	decoded, err := base64.RawURLEncoding.DecodeString(cursor)
	if err != nil {
		return time.Time{}, bson.NilObjectID, false
	}
	parts := strings.SplitN(string(decoded), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, bson.NilObjectID, false
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return time.Time{}, bson.NilObjectID, false
	}
	id, err := bson.ObjectIDFromHex(parts[1])
	if err != nil {
		return time.Time{}, bson.NilObjectID, false
	}
	return occurredAt, id, true
}
