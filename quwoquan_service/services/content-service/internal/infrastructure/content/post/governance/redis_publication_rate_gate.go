package governance

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type RedisPublicationRateGate struct {
	client rtredis.Client
}

func NewRedisPublicationRateGate(
	client rtredis.Client,
) *RedisPublicationRateGate {
	if client == nil {
		panic("RedisPublicationRateGate requires Redis client")
	}
	return &RedisPublicationRateGate{client: client}
}

func (g *RedisPublicationRateGate) AdmitPublication(
	ctx context.Context,
	request postports.PublicationRateRequest,
) (postports.PublicationRateDecision, error) {
	if g == nil || g.client == nil {
		return postports.PublicationRateDecision{}, fmt.Errorf(
			"publication rate Redis client is not configured",
		)
	}
	personaID := strings.TrimSpace(request.PersonaID)
	intentID := strings.TrimSpace(request.PublishIntentID)
	if personaID == "" || intentID == "" {
		return postports.PublicationRateDecision{}, fmt.Errorf(
			"publication rate request identity is incomplete",
		)
	}
	now := request.OccurredAt.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	window := time.Duration(
		contentgenerated.PostPublicationPersonaRateWindowSeconds,
	) * time.Second
	bucket := now.Unix() / int64(window/time.Second)
	personaHash := digestKey(personaID)
	intentHash := digestKey(personaID + "\x00" + intentID)
	intentKey := fmt.Sprintf("content:publication-rate:intent:%s:%d", intentHash, bucket)
	acquired, err := g.client.SetNX(
		ctx,
		intentKey,
		"pending",
		window+10*time.Second,
	)
	if err != nil {
		return postports.PublicationRateDecision{}, err
	}
	if !acquired {
		state, getErr := g.client.Get(ctx, intentKey)
		if getErr != nil {
			return postports.PublicationRateDecision{}, getErr
		}
		switch state {
		case "allowed":
			return postports.PublicationRateDecision{Allowed: true}, nil
		case "limited":
			return postports.PublicationRateDecision{
				RetryAfter: retryAfterWindow(now, window),
			}, nil
		default:
			// 同一 intent 的首个裁决仍在执行。返回依赖错误让调用方安全重试，
			// 不能把 pending 当作 allow 绕过限流。
			return postports.PublicationRateDecision{}, fmt.Errorf(
				"publication rate decision is pending",
			)
		}
	}
	countKey := fmt.Sprintf(
		"content:publication-rate:persona:%s:%d",
		personaHash,
		bucket,
	)
	count, err := g.client.Incr(ctx, countKey)
	if err != nil {
		_ = g.client.Del(ctx, intentKey)
		return postports.PublicationRateDecision{}, err
	}
	if err := g.client.Expire(ctx, countKey, window+10*time.Second); err != nil {
		_ = g.client.Del(ctx, intentKey)
		return postports.PublicationRateDecision{}, err
	}
	if count > int64(contentgenerated.PostPublicationPersonaMaxPublications) {
		if err := g.client.Set(
			ctx,
			intentKey,
			"limited",
			window+10*time.Second,
		); err != nil {
			return postports.PublicationRateDecision{}, err
		}
		return postports.PublicationRateDecision{
			RetryAfter: retryAfterWindow(now, window),
		}, nil
	}
	if err := g.client.Set(
		ctx,
		intentKey,
		"allowed",
		window+10*time.Second,
	); err != nil {
		return postports.PublicationRateDecision{}, err
	}
	return postports.PublicationRateDecision{Allowed: true}, nil
}

func retryAfterWindow(now time.Time, window time.Duration) time.Duration {
	windowSeconds := int64(window / time.Second)
	next := time.Unix((now.Unix()/windowSeconds+1)*windowSeconds, 0).UTC()
	delay := next.Sub(now)
	if delay < time.Second {
		return time.Second
	}
	return delay
}

func digestKey(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:16])
}

var _ postports.PublicationRateGate = (*RedisPublicationRateGate)(nil)
