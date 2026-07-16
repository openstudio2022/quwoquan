package cache

import (
	"context"
	"errors"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/application"
)

// ConversationCache provides Redis caching for the chat domain:
// - Conversation entity cache (TTL 300s)
// Message seq 与 ClientMsgId 幂等均由 Message aggregate 的 Mongo transaction
// 权威保证，不允许以 Redis key 充当写入真相源。
type ConversationCache struct {
	rdb rtredis.Client
}

var _ application.ConversationCache = (*ConversationCache)(nil)

func NewConversationCache(rdb rtredis.Client) *ConversationCache {
	return &ConversationCache{rdb: rdb}
}

const (
	convCacheTTL = 300 * time.Second
)

func convCacheKey(conversationId string) string {
	return fmt.Sprintf("cache:conversation:%s", conversationId)
}

// InvalidateConversation removes the conversation entity cache.
func (c *ConversationCache) InvalidateConversation(ctx context.Context, conversationId string) error {
	return c.rdb.Del(ctx, convCacheKey(conversationId))
}

// SetConversationCache stores a serialized conversation in cache.
func (c *ConversationCache) SetConversationCache(ctx context.Context, conversationId, data string) error {
	return c.rdb.Set(ctx, convCacheKey(conversationId), data, convCacheTTL)
}

// GetConversationCache returns the cached conversation data, or empty string if not found.
func (c *ConversationCache) GetConversationCache(ctx context.Context, conversationId string) (string, error) {
	val, err := c.rdb.Get(ctx, convCacheKey(conversationId))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return "", nil
	}
	return val, err
}
