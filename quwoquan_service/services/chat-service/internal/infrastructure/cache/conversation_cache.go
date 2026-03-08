package cache

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

// ConversationCache provides Redis caching for the chat domain:
// - Conversation entity cache (TTL 300s)
// - Per-conversation seq counter (INCR, no expiry)
// - ClientMsgId dedup (SET NX, TTL 300s)
type ConversationCache struct {
	rdb rtredis.Client
}

func NewConversationCache(rdb rtredis.Client) *ConversationCache {
	return &ConversationCache{rdb: rdb}
}

const (
	convCacheTTL = 300 * time.Second
	dedupTTL     = 300 * time.Second
)

func convCacheKey(conversationId string) string {
	return fmt.Sprintf("cache:conversation:%s", conversationId)
}

func seqKey(conversationId string) string {
	return fmt.Sprintf("seq:conversation:{%s}", conversationId)
}

func dedupKey(conversationId, clientMsgId string) string {
	return fmt.Sprintf("dedup:msg:{%s}:%s", conversationId, clientMsgId)
}

// NextSeq atomically increments and returns the next seq for a conversation.
func (c *ConversationCache) NextSeq(ctx context.Context, conversationId string) (int64, error) {
	return c.rdb.Incr(ctx, seqKey(conversationId))
}

// InitSeq sets the seq counter if it does not exist yet (used during conversation creation).
func (c *ConversationCache) InitSeq(ctx context.Context, conversationId string, initialSeq int64) error {
	_, err := c.rdb.SetNX(ctx, seqKey(conversationId), strconv.FormatInt(initialSeq, 10), 0)
	return err
}

// TryDedup attempts to set a dedup key. Returns true if the key was newly set
// (first occurrence), false if the key already existed (duplicate).
func (c *ConversationCache) TryDedup(ctx context.Context, conversationId, clientMsgId string) (bool, error) {
	return c.rdb.SetNX(ctx, dedupKey(conversationId, clientMsgId), "1", dedupTTL)
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
