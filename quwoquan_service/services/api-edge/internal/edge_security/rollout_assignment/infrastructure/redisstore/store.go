package redisstore

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	redis "github.com/redis/go-redis/v9"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
)

type Store struct{ client redis.UniversalClient }

var _ application.AssignmentStore = (*Store)(nil)

func New(client redis.UniversalClient) (*Store, error) {
	if client == nil {
		return nil, errors.New("rollout Redis client is required")
	}
	return &Store{client: client}, nil
}

func (store *Store) IsCandidate(ctx context.Context, campaignID, subjectDigest string) (bool, error) {
	value, err := store.client.Get(ctx, assignmentKey(campaignID, subjectDigest)).Result()
	if errors.Is(err, redis.Nil) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if value != "candidate" {
		return false, errors.New("rollout assignment value is invalid")
	}
	return true, nil
}

func (store *Store) AssignCandidate(ctx context.Context, campaignID, subjectDigest string, ttl time.Duration) error {
	if ttl <= 0 {
		return errors.New("rollout assignment TTL must be positive")
	}
	created, err := store.client.SetNX(
		ctx, assignmentKey(campaignID, subjectDigest), "candidate", ttl,
	).Result()
	if err != nil {
		return err
	}
	if created {
		return nil
	}
	value, err := store.client.Get(ctx, assignmentKey(campaignID, subjectDigest)).Result()
	if err != nil {
		return err
	}
	if value != "candidate" {
		return errors.New("rollout assignment conflicts with candidate")
	}
	return nil
}

func (store *Store) Ping(ctx context.Context) error { return store.client.Ping(ctx).Err() }

func assignmentKey(campaignID, subjectDigest string) string {
	return fmt.Sprintf("edge:rollout:{%s}:%s", clean(campaignID), clean(subjectDigest))
}

func clean(value string) string {
	value = strings.TrimSpace(value)
	value = strings.ReplaceAll(value, "{", "")
	return strings.ReplaceAll(value, "}", "")
}
