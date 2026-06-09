package application

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"
)

type MemoryOtpChallengeStore struct {
	mu         sync.Mutex
	challenges map[string]OtpChallenge
}

func NewMemoryOtpChallengeStore() *MemoryOtpChallengeStore {
	return &MemoryOtpChallengeStore{challenges: map[string]OtpChallenge{}}
}

func (s *MemoryOtpChallengeStore) CreateChallenge(ctx context.Context, challenge OtpChallenge) (OtpChallenge, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now().UTC()
	if challenge.CreatedAt.IsZero() {
		challenge.CreatedAt = now
	}
	challenge.UpdatedAt = now
	for _, existing := range s.challenges {
		if existing.IdempotencyKey == challenge.IdempotencyKey {
			return existing, nil
		}
	}
	s.challenges[challenge.ChallengeID] = challenge
	return challenge, nil
}

func (s *MemoryOtpChallengeStore) FindLatestChallenge(ctx context.Context, phone string, now time.Time) (*OtpChallenge, error) {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	items := make([]OtpChallenge, 0)
	for _, challenge := range s.challenges {
		if challenge.Phone == strings.TrimSpace(phone) && challenge.ExpiresAt.After(now) && challenge.ConsumedAt == nil {
			items = append(items, challenge)
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if len(items) == 0 {
		return nil, nil
	}
	return &items[0], nil
}

func (s *MemoryOtpChallengeStore) MarkChallengeDelivered(ctx context.Context, requestID string, status string) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	for id, challenge := range s.challenges {
		if challenge.RequestID == requestID && challenge.ConsumedAt == nil {
			challenge.Status = status
			challenge.UpdatedAt = time.Now().UTC()
			s.challenges[id] = challenge
		}
	}
	return nil
}

func (s *MemoryOtpChallengeStore) MarkChallengeFailed(ctx context.Context, requestID string, reason string) error {
	_ = reason
	return s.MarkChallengeDelivered(ctx, requestID, OtpChallengeStatusFailed)
}

func (s *MemoryOtpChallengeStore) ConsumeChallenge(ctx context.Context, challengeID string, now time.Time) error {
	_ = ctx
	s.mu.Lock()
	defer s.mu.Unlock()
	challenge := s.challenges[challengeID]
	consumedAt := now.UTC()
	challenge.Status = OtpChallengeStatusConsumed
	challenge.ConsumedAt = &consumedAt
	challenge.UpdatedAt = consumedAt
	s.challenges[challengeID] = challenge
	return nil
}
