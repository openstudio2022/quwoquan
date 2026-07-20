package cache

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/rtc-service/internal/application"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

var _ application.CallStateCache = (*CallStateCache)(nil)

type CallStateCache struct {
	rdb rtredis.Client
}

func NewCallStateCache(rdb rtredis.Client) *CallStateCache {
	return &CallStateCache{rdb: rdb}
}

// callStateTTL 与 storage.yaml redis_cache["cache:rtc:call:{callId}"].ttl_seconds 同源。
const callStateTTL = 60 * time.Second

func callCacheKey(callID string) string {
	return fmt.Sprintf("cache:rtc:call:%s", callID)
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
