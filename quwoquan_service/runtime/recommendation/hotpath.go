package recommendation

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"
)

// RedisClient abstracts Redis operations for the hot path.
type RedisClient interface {
	Get(ctx context.Context, key string) (string, error)
	Set(ctx context.Context, key string, value string, ttl time.Duration) error
	Del(ctx context.Context, keys ...string) error
	SAdd(ctx context.Context, key string, members ...string) error
	SMembers(ctx context.Context, key string) ([]string, error)
	SIsMember(ctx context.Context, key string, member string) (bool, error)
	HIncrByFloat(ctx context.Context, key, field string, incr float64) error
	HGetAll(ctx context.Context, key string) (map[string]string, error)
	Expire(ctx context.Context, key string, ttl time.Duration) error
}

// SessionReader reads session state for feed generation.
// Implemented by HotPath, SessionCache, etc.
type SessionReader interface {
	GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error)
}

// SignalProcessor writes behavior signals.
// Implemented by HotPath, BufferedHotPath, etc.
type SignalProcessor interface {
	ProcessSignal(ctx context.Context, signal BehaviorSignal) error
	ProcessSignalBatch(ctx context.Context, signals []BehaviorSignal) error
}

// Key patterns aligned with contracts/metadata/_shared/redis_keyspace.yaml:
//   rec:session_signals:{userId}:{sessionId}  → hash   TTL 1800s
//   rec:exposed:{userId}:{sessionId}          → set    TTL 1800s
//   rec:negative:{userId}:{sessionId}         → set    TTL 86400s
//   rec:realtime_interest:{userId}:{sessionId}→ string TTL 1800s
const (
	sessionTTL  = 30 * time.Minute
	negativeTTL = 24 * time.Hour

	signalKeyPrefix   = "rec:session_signals:"
	exposedKeyPrefix  = "rec:exposed:"
	negativeKeyPrefix = "rec:negative:"
	interestKeyPrefix = "rec:realtime_interest:"
)

// BehaviorSignal represents a user behavior event for hot path processing.
type BehaviorSignal struct {
	UserID    string    `json:"userId"`
	SessionID string    `json:"sessionId"`
	ContentID string    `json:"contentId"`
	Action    string    `json:"action"`
	Tags      []string  `json:"tags,omitempty"`
	Duration  float64   `json:"duration,omitempty"`
	Timestamp time.Time `json:"timestamp"`
}

// Signal weights per action type — tunable via runtime/experiments.
var SignalWeights = map[string]float64{
	"impression": 0.1,
	"click":      0.5,
	"dwell":      1.0,
	"like":       2.0,
	"favorite":   3.0,
	"share":      3.0,
	"dislike":    -5.0,
	"report":     -10.0,
}

// HotPath manages session-level recommendation state in Redis.
type HotPath struct {
	redis RedisClient
}

func NewHotPath(redis RedisClient) *HotPath {
	return &HotPath{redis: redis}
}

func sessionKey(userID, sessionID string) string {
	if sessionID == "" {
		sessionID = "default"
	}
	return userID + ":" + sessionID
}

// ProcessSignal updates session-level state from a behavior signal.
func (h *HotPath) ProcessSignal(ctx context.Context, signal BehaviorSignal) error {
	sk := sessionKey(signal.UserID, signal.SessionID)

	if err := h.addExposed(ctx, sk, signal.ContentID); err != nil {
		return err
	}

	weight := SignalWeights[signal.Action]
	if weight < 0 {
		if err := h.addNegative(ctx, sk, signal.ContentID); err != nil {
			return err
		}
	}

	if len(signal.Tags) > 0 {
		if err := h.updateTagWeights(ctx, sk, signal.Tags, weight); err != nil {
			return err
		}
	}

	return h.updateInterest(ctx, sk, signal)
}

// ProcessSignalBatch processes multiple signals concurrently.
// Groups by session key and processes groups in parallel.
func (h *HotPath) ProcessSignalBatch(ctx context.Context, signals []BehaviorSignal) error {
	if len(signals) <= 1 {
		for _, s := range signals {
			if err := h.ProcessSignal(ctx, s); err != nil {
				return err
			}
		}
		return nil
	}

	groups := make(map[string][]BehaviorSignal, len(signals)/2+1)
	for _, s := range signals {
		sk := sessionKey(s.UserID, s.SessionID)
		groups[sk] = append(groups[sk], s)
	}

	var (
		mu      sync.Mutex
		firstErr error
		wg      sync.WaitGroup
	)

	for _, sigs := range groups {
		wg.Add(1)
		go func(batch []BehaviorSignal) {
			defer wg.Done()
			for _, s := range batch {
				if err := h.ProcessSignal(ctx, s); err != nil {
					mu.Lock()
					if firstErr == nil {
						firstErr = err
					}
					mu.Unlock()
					return
				}
			}
		}(sigs)
	}

	wg.Wait()
	return firstErr
}

// GetSessionState returns the full session state for the recommendation engine.
// Reads all 3 Redis keys in parallel (1 RTT instead of 3).
func (h *HotPath) GetSessionState(ctx context.Context, userID, sessionID string) (*SessionState, error) {
	sk := sessionKey(userID, sessionID)

	var (
		tagWeights  map[string]float64
		exposed     []string
		negative    []string
		tagErr      error
		exposedErr  error
		negativeErr error
	)

	var wg sync.WaitGroup
	wg.Add(3)

	go func() {
		defer wg.Done()
		tagWeights, tagErr = h.getTagWeights(ctx, sk)
	}()
	go func() {
		defer wg.Done()
		exposed, exposedErr = h.getExposedSet(ctx, sk)
	}()
	go func() {
		defer wg.Done()
		negative, negativeErr = h.getNegativeSet(ctx, sk)
	}()

	wg.Wait()

	if tagErr != nil {
		return nil, tagErr
	}
	if exposedErr != nil {
		return nil, exposedErr
	}
	if negativeErr != nil {
		return nil, negativeErr
	}

	return &SessionState{
		UserID:      userID,
		SessionID:   sessionID,
		TagWeights:  tagWeights,
		ExposedIDs:  exposed,
		NegativeIDs: negative,
	}, nil
}

// IsExposed checks if a content ID has already been shown in this session.
func (h *HotPath) IsExposed(ctx context.Context, userID, sessionID, contentID string) (bool, error) {
	sk := sessionKey(userID, sessionID)
	return h.redis.SIsMember(ctx, exposedKeyPrefix+sk, contentID)
}

// SessionState holds the real-time session context for recommendations.
type SessionState struct {
	UserID      string
	SessionID   string
	TagWeights  map[string]float64
	ExposedIDs  []string
	NegativeIDs []string
}

func (h *HotPath) addExposed(ctx context.Context, sk, contentID string) error {
	key := exposedKeyPrefix + sk
	if err := h.redis.SAdd(ctx, key, contentID); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, sessionTTL)
}

func (h *HotPath) addNegative(ctx context.Context, sk, contentID string) error {
	key := negativeKeyPrefix + sk
	if err := h.redis.SAdd(ctx, key, contentID); err != nil {
		return err
	}
	return h.redis.Expire(ctx, key, negativeTTL)
}

func (h *HotPath) updateTagWeights(ctx context.Context, sk string, tags []string, weight float64) error {
	key := signalKeyPrefix + sk
	for _, tag := range tags {
		if err := h.redis.HIncrByFloat(ctx, key, tag, weight); err != nil {
			return err
		}
	}
	return h.redis.Expire(ctx, key, sessionTTL)
}

func (h *HotPath) updateInterest(ctx context.Context, sk string, signal BehaviorSignal) error {
	key := interestKeyPrefix + sk
	data, _ := json.Marshal(signal)
	return h.redis.Set(ctx, key, string(data), sessionTTL)
}

func (h *HotPath) getTagWeights(ctx context.Context, sk string) (map[string]float64, error) {
	key := signalKeyPrefix + sk
	raw, err := h.redis.HGetAll(ctx, key)
	if err != nil {
		return nil, err
	}
	weights := make(map[string]float64, len(raw))
	for k, v := range raw {
		var f float64
		fmt.Sscanf(v, "%f", &f)
		weights[k] = f
	}
	return weights, nil
}

func (h *HotPath) getExposedSet(ctx context.Context, sk string) ([]string, error) {
	return h.redis.SMembers(ctx, exposedKeyPrefix+sk)
}

func (h *HotPath) getNegativeSet(ctx context.Context, sk string) ([]string, error) {
	return h.redis.SMembers(ctx, negativeKeyPrefix+sk)
}
