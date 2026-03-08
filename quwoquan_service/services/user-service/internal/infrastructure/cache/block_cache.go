package cache

import (
	"context"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const blockSetTTL = 3600 * time.Second

type BlockCache struct {
	client rtredis.Client
}

func NewBlockCache(client rtredis.Client) *BlockCache {
	return &BlockCache{client: client}
}

func blockSetKey(blockerID string) string {
	return fmt.Sprintf("blocked_set:%s", blockerID)
}

func (c *BlockCache) IsMember(ctx context.Context, blockerID, blockedID string) (bool, error) {
	return c.client.SIsMember(ctx, blockSetKey(blockerID), blockedID)
}

func (c *BlockCache) Add(ctx context.Context, blockerID, blockedID string) error {
	key := blockSetKey(blockerID)
	if err := c.client.SAdd(ctx, key, blockedID); err != nil {
		return err
	}
	return c.client.Expire(ctx, key, blockSetTTL)
}

// Remove invalidates the entire blocked_set for this user.
// The set will be lazily re-populated from DB on next CheckBlocked.
// runtime/redis.Client does not expose SRem, so full invalidation is used.
func (c *BlockCache) Remove(ctx context.Context, blockerID, _ string) error {
	return c.client.Del(ctx, blockSetKey(blockerID))
}

func (c *BlockCache) Exists(ctx context.Context, blockerID string) (bool, error) {
	members, err := c.client.SMembers(ctx, blockSetKey(blockerID))
	if err != nil {
		return false, err
	}
	return len(members) > 0, nil
}

func (c *BlockCache) LoadFromDB(ctx context.Context, blockerID string, blockedIDs []string) error {
	if len(blockedIDs) == 0 {
		return nil
	}
	k := blockSetKey(blockerID)
	if err := c.client.SAdd(ctx, k, blockedIDs...); err != nil {
		return fmt.Errorf("sadd blocked_set: %w", err)
	}
	return c.client.Expire(ctx, k, blockSetTTL)
}
