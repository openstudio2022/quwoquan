package cache

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

type CallStateCache struct {
	rdb rtredis.Client
}

func NewCallStateCache(rdb rtredis.Client) *CallStateCache {
	return &CallStateCache{rdb: rdb}
}

const (
	callStateTTL      = 3600 * time.Second
	activeCallTTL     = 3600 * time.Second
	callTimeoutTTL    = 120 * time.Second
)

func callCacheKey(callID string) string {
	return fmt.Sprintf("cache:rtc:call:%s", callID)
}

func activeCallKey(userID string) string {
	return fmt.Sprintf("rtc:active_call:user:%s", userID)
}

func callTimeoutKey(callID string) string {
	return fmt.Sprintf("rtc:call_timeout:%s", callID)
}

func (c *CallStateCache) SetCallState(ctx context.Context, session *model.CallSession) error {
	data, err := json.Marshal(session)
	if err != nil {
		return fmt.Errorf("marshal call state: %w", err)
	}
	return c.rdb.Set(ctx, callCacheKey(session.ID), string(data), callStateTTL)
}

func (c *CallStateCache) GetCallState(ctx context.Context, callID string) (*model.CallSession, error) {
	val, err := c.rdb.Get(ctx, callCacheKey(callID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var session model.CallSession
	if err := json.Unmarshal([]byte(val), &session); err != nil {
		return nil, fmt.Errorf("unmarshal call state: %w", err)
	}
	return &session, nil
}

func (c *CallStateCache) InvalidateCallState(ctx context.Context, callID string) error {
	return c.rdb.Del(ctx, callCacheKey(callID))
}

func (c *CallStateCache) SetActiveCallForUser(ctx context.Context, userID, callID string) error {
	return c.rdb.Set(ctx, activeCallKey(userID), callID, activeCallTTL)
}

func (c *CallStateCache) GetActiveCallForUser(ctx context.Context, userID string) (string, error) {
	val, err := c.rdb.Get(ctx, activeCallKey(userID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return "", nil
	}
	return val, err
}

func (c *CallStateCache) DeleteActiveCallForUser(ctx context.Context, userID string) error {
	return c.rdb.Del(ctx, activeCallKey(userID))
}

func (c *CallStateCache) SetCallTimeout(ctx context.Context, callID string, timeout time.Duration) error {
	ttl := callTimeoutTTL
	if timeout > 0 {
		ttl = timeout
	}
	return c.rdb.Set(ctx, callTimeoutKey(callID), "1", ttl)
}

func (c *CallStateCache) GetCallTimeout(ctx context.Context, callID string) (bool, error) {
	_, err := c.rdb.Get(ctx, callTimeoutKey(callID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func (c *CallStateCache) DeleteCallTimeout(ctx context.Context, callID string) error {
	return c.rdb.Del(ctx, callTimeoutKey(callID))
}
