// Package cache owns the versioned Redis projection for UserAccount FullSnapshot.
package cache

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	rtredis "quwoquan_service/runtime/redis"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	"time"
)

const profileKeyTTL = 600 * time.Second

func profileKey(userID string) string { return fmt.Sprintf("cache:{%s}:user_profile", userID) }

const profileSnapshotField = "snapshot"

type profileCacheEnvelope struct {
	Generation      int64               `json:"generation"`
	ProfileVersion  int64               `json:"profileVersion"`
	SourceExpiresAt time.Time           `json:"sourceExpiresAt"`
	Snapshot        *model.FullSnapshot `json:"snapshot"`
}
type ProfileCache struct {
	client rtredis.Client
	now    func() time.Time
	ttl    time.Duration
}

func NewProfileCache(client rtredis.Client) *ProfileCache {
	return &ProfileCache{client: client, now: func() time.Time { return time.Now().UTC() }, ttl: profileKeyTTL}
}
func (c *ProfileCache) WithTTL(ttl time.Duration) *ProfileCache {
	if ttl > 0 {
		c.ttl = ttl
	}
	return c
}
func (c *ProfileCache) WithClock(now func() time.Time) *ProfileCache {
	if now != nil {
		c.now = now
	}
	return c
}
func (c *ProfileCache) Get(ctx context.Context, userID string) (*model.FullSnapshot, error) {
	return c.GetAtLeast(ctx, userID, 0)
}
func (c *ProfileCache) GetAtLeast(ctx context.Context, userID string, minVersion int64) (*model.FullSnapshot, error) {
	raw, err := c.client.HGet(ctx, profileKey(userID), profileSnapshotField)
	if err != nil || raw == "" {
		return nil, err
	}
	var envelope profileCacheEnvelope
	if json.Unmarshal([]byte(raw), &envelope) != nil || envelope.Snapshot == nil {
		return nil, errors.New("invalid profile cache envelope")
	}
	if !c.now().Before(envelope.SourceExpiresAt) || envelope.ProfileVersion < minVersion {
		return nil, nil
	}
	return envelope.Snapshot, nil
}
func (c *ProfileCache) Set(ctx context.Context, userID string, snapshot *model.FullSnapshot) error {
	if snapshot == nil || snapshot.Profile == nil {
		return errors.New("profile cache snapshot is incomplete")
	}
	version := int64(snapshot.Profile.ProfileVersion)
	key := profileKey(userID)
	for attempt := 0; attempt < 8; attempt++ {
		current, err := c.client.HGet(ctx, key, profileSnapshotField)
		if err != nil && !errors.Is(err, rtredis.ErrKeyNotFound) {
			return err
		}
		var expected *string
		generation := int64(1)
		if current != "" {
			var prior profileCacheEnvelope
			if json.Unmarshal([]byte(current), &prior) != nil {
				return errors.New("invalid profile cache envelope")
			}
			if prior.ProfileVersion > version {
				return nil
			}
			generation = prior.Generation + 1
			expected = &current
		}
		expires := c.now().Add(c.ttl)
		envelope := profileCacheEnvelope{Generation: generation, ProfileVersion: version, SourceExpiresAt: expires, Snapshot: snapshot}
		encoded, err := json.Marshal(envelope)
		if err != nil {
			return err
		}
		replacement := string(encoded)
		applied, err := rtredis.CompareAndSwapHashField(ctx, c.client, key, profileSnapshotField, expected, &replacement, c.ttl)
		if err != nil {
			return err
		}
		if applied {
			return nil
		}
	}
	return errors.New("profile cache CAS retry budget exhausted")
}
func (c *ProfileCache) Del(ctx context.Context, userID string) error {
	return c.client.Del(ctx, profileKey(userID))
}
