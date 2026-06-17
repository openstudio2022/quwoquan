package recommendation

import (
	"context"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// MongoCollaborativeCandidateStore reads pre-materialized collaborative recall
// models. It intentionally does not compute item co-occurrence on the feed read
// path; offline jobs own itemCF/Swing/u2i materialization.
type MongoCollaborativeCandidateStore struct {
	i2iColl  *mongo.Collection
	u2iColl  *mongo.Collection
	feedColl *mongo.Collection
}

type collaborativeContentDoc struct {
	ContentID string `bson:"contentId"`
}

func NewMongoCollaborativeCandidateStore(db *mongo.Database) *MongoCollaborativeCandidateStore {
	return &MongoCollaborativeCandidateStore{
		i2iColl:  db.Collection("rm_collaborative_i2i"),
		u2iColl:  db.Collection("rm_collaborative_u2i"),
		feedColl: db.Collection("rm_discovery_feed"),
	}
}

func (s *MongoCollaborativeCandidateStore) GetI2ICandidates(ctx context.Context, seedContentIDs []string, limit int) ([]rtrec.ContentCandidate, error) {
	if limit <= 0 {
		return nil, nil
	}
	ids := normalizeIDs(seedContentIDs)
	if len(ids) == 0 {
		return nil, nil
	}
	cursor, err := s.i2iColl.Find(ctx,
		bson.M{"seedContentId": bson.M{"$in": ids}},
		options.Find().SetSort(bson.D{{Key: "score", Value: -1}}).SetLimit(int64(limit*2)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var docs []collaborativeContentDoc
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, err
	}
	return s.candidatesByIDs(ctx, contentIDsFromDocs(docs), limit, rtrec.RecallPathCollaborativeI2I)
}

func (s *MongoCollaborativeCandidateStore) GetU2ICandidates(ctx context.Context, userID string, limit int) ([]rtrec.ContentCandidate, error) {
	if limit <= 0 || strings.TrimSpace(userID) == "" {
		return nil, nil
	}
	cursor, err := s.u2iColl.Find(ctx,
		bson.M{"userId": userID},
		options.Find().SetSort(bson.D{{Key: "score", Value: -1}}).SetLimit(int64(limit*2)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var docs []collaborativeContentDoc
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, err
	}
	return s.candidatesByIDs(ctx, contentIDsFromDocs(docs), limit, rtrec.RecallPathCollaborativeU2I)
}

func (s *MongoCollaborativeCandidateStore) candidatesByIDs(ctx context.Context, ids []string, limit int, path string) ([]rtrec.ContentCandidate, error) {
	if len(ids) == 0 || limit <= 0 {
		return nil, nil
	}
	if len(ids) > limit*2 {
		ids = ids[:limit*2]
	}
	candidates, err := queryDiscoveryFeed(
		ctx,
		s.feedColl,
		bson.M{"postId": bson.M{"$in": ids}},
		options.Find().SetLimit(int64(limit*2)),
		path,
	)
	if err != nil {
		return nil, err
	}
	order := make(map[string]int, len(ids))
	for i, id := range ids {
		order[id] = i
	}
	sortCandidatesByMaterializedOrder(candidates, order)
	if len(candidates) > limit {
		candidates = candidates[:limit]
	}
	return candidates, nil
}

func normalizeIDs(ids []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(ids))
	for _, raw := range ids {
		id := strings.TrimSpace(raw)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	return out
}

func contentIDsFromDocs(docs []collaborativeContentDoc) []string {
	ids := make([]string, 0, len(docs))
	for _, doc := range docs {
		ids = append(ids, doc.ContentID)
	}
	return normalizeIDs(ids)
}

func sortCandidatesByMaterializedOrder(items []rtrec.ContentCandidate, order map[string]int) {
	for i := 1; i < len(items); i++ {
		for j := i; j > 0 && order[items[j].ContentID] < order[items[j-1].ContentID]; j-- {
			items[j], items[j-1] = items[j-1], items[j]
		}
	}
}
