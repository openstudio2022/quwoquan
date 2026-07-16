package reliabletaskmongo

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/reliabletask"
)

func (s *Store) ClaimShardLease(
	ctx context.Context,
	req reliabletask.ClaimShardLeaseRequest,
) (*reliabletask.TaskLease, error) {
	now := req.Now.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	ttl := req.LeaseTTL
	if ttl <= 0 {
		ttl = 30 * time.Second
	}
	filter := bson.M{
		"env":     strings.TrimSpace(req.Env),
		"domain":  strings.TrimSpace(req.Domain),
		"module":  strings.TrimSpace(req.Module),
		"shardId": req.ShardID,
		"$or": bson.A{
			bson.M{"leaseUntil": bson.M{"$lte": now}},
			bson.M{"owner": strings.TrimSpace(req.Owner)},
			bson.M{"owner": bson.M{"$exists": false}},
		},
	}
	lease := reliabletask.TaskLease{
		Env:        strings.TrimSpace(req.Env),
		Domain:     strings.TrimSpace(req.Domain),
		Module:     strings.TrimSpace(req.Module),
		Owner:      strings.TrimSpace(req.Owner),
		Token:      reliabletask.NewRecordID("shard-lease"),
		ShardID:    req.ShardID,
		LeaseUntil: now.Add(ttl).UTC(),
		UpdatedAt:  now,
	}
	update := bson.M{
		"$set": lease,
		"$setOnInsert": bson.M{
			"_id": reliabletask.ShardLeaseID(req.Env, req.Domain, req.Module, req.ShardID),
		},
	}
	opts := options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)
	var claimed reliabletask.TaskLease
	if err := s.leases.FindOneAndUpdate(ctx, filter, update, opts).Decode(&claimed); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, nil
		}
		return nil, err
	}
	return &claimed, nil
}
