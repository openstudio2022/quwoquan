package persistence

import (
	"context"
	"encoding/json"
	"errors"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

type RedisStore struct {
	client rtredis.Client
}

func NewRedisStore(client rtredis.Client) *RedisStore {
	return &RedisStore{client: client}
}

func (s *RedisStore) Put(ctx context.Context, pageContext model.PageContext) error {
	if s == nil || s.client == nil {
		return errors.New("page context redis client is unavailable")
	}
	payload, err := json.Marshal(pageContext)
	if err != nil {
		return err
	}
	return s.client.Set(ctx, model.StorageKey(pageContext.AccountID), string(payload), model.TTL)
}

func (s *RedisStore) Get(ctx context.Context, accountID string) (*model.PageContext, error) {
	if s == nil || s.client == nil {
		return nil, errors.New("page context redis client is unavailable")
	}
	payload, err := s.client.Get(ctx, model.StorageKey(accountID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var pageContext model.PageContext
	if err := json.Unmarshal([]byte(payload), &pageContext); err != nil {
		return nil, err
	}
	return &pageContext, nil
}
