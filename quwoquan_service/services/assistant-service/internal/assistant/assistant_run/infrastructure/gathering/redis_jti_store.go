package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rtredis "quwoquan_service/runtime/redis"
)

const delegatedGrantJTIKeyPrefix = "assistant:gathering:delegated-command-jti:"

type RedisDelegatedGrantJTIStore struct {
	client rtredis.Client
	now    func() time.Time
}

var _ rtauth.DelegatedGrantJTIStore = (*RedisDelegatedGrantJTIStore)(nil)

func NewRedisDelegatedGrantJTIStore(client rtredis.Client) (*RedisDelegatedGrantJTIStore, error) {
	if client == nil {
		return nil, errors.New("gathering delegated grant Redis client is required")
	}
	return &RedisDelegatedGrantJTIStore{client: client, now: time.Now}, nil
}

func (s *RedisDelegatedGrantJTIStore) Consume(
	ctx context.Context,
	jti string,
	expiresAt time.Time,
) (bool, error) {
	jti = strings.TrimSpace(jti)
	if jti == "" {
		return false, errors.New("delegated command grant JTI is required")
	}
	ttl := expiresAt.UTC().Sub(s.now().UTC())
	if ttl <= 0 {
		return false, errors.New("delegated command grant JTI is already expired")
	}
	digest := sha256.Sum256([]byte(jti))
	return s.client.SetNX(
		ctx,
		delegatedGrantJTIKeyPrefix+hex.EncodeToString(digest[:]),
		"consumed",
		ttl,
	)
}
