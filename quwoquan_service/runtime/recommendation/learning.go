package recommendation

import (
	"context"
	"fmt"
	"strconv"
	"time"

	learning "quwoquan_service/runtime/learning"
)

const scoreKeyPrefix = "rec:imp_score:"
const scoreTTL = 2 * time.Hour

// FeedbackRecorder records recommendation outcomes for offline learning.
// It also caches impression scores so that RecordEngagement can recover
// the original recommendation score for a content item.
type FeedbackRecorder struct {
	recorder   learning.Recorder
	scoreCache RedisClient
}

func NewFeedbackRecorder(recorder learning.Recorder, opts ...FeedbackRecorderOption) *FeedbackRecorder {
	f := &FeedbackRecorder{recorder: recorder}
	for _, opt := range opts {
		opt(f)
	}
	return f
}

type FeedbackRecorderOption func(*FeedbackRecorder)

func WithScoreCache(rc RedisClient) FeedbackRecorderOption {
	return func(f *FeedbackRecorder) { f.scoreCache = rc }
}

func (f *FeedbackRecorder) cacheImpressionScore(ctx context.Context, userID, contentID string, score float64) {
	if f.scoreCache == nil {
		return
	}
	key := scoreKeyPrefix + userID + ":" + contentID
	_ = f.scoreCache.Set(ctx, key, strconv.FormatFloat(score, 'f', 6, 64), scoreTTL)
}

func (f *FeedbackRecorder) lookupImpressionScore(ctx context.Context, userID, contentID string) float64 {
	if f.scoreCache == nil {
		return 0
	}
	key := scoreKeyPrefix + userID + ":" + contentID
	val, err := f.scoreCache.Get(ctx, key)
	if err != nil || val == "" {
		return 0
	}
	score, _ := strconv.ParseFloat(val, 64)
	return score
}

// recImpressionContext builds a typed context map for rec_impression events.
func recImpressionContext(score float64, authorID string, tags []string) map[string]any {
	return map[string]any{
		"score":    score,
		"authorId": authorID,
		"tags":     tags,
	}
}

// recEngagementContext builds a typed context map for rec_engagement events.
func recEngagementContext(duration float64, recScore float64, tags []string, feedRequestID string, referralSource string, contentType string, authorID string) map[string]any {
	return map[string]any{
		"duration":       duration,
		"recScore":       recScore,
		"tags":           tags,
		"feedRequestId":  feedRequestID,
		"referralSource": referralSource,
		"contentType":    contentType,
		"authorId":       authorID,
	}
}

// RecordImpression records that a feed item was shown to the user.
// Also caches the recommendation score per content for later engagement lookups.
func (f *FeedbackRecorder) RecordImpression(ctx context.Context, userID, sessionID string, items []FeedItem) error {
	if f.recorder == nil {
		return nil
	}
	for _, item := range items {
		f.cacheImpressionScore(ctx, userID, item.ContentID, item.Score)
		_ = f.recorder.RecordEvent(ctx, learning.Event{
			EventID:    fmt.Sprintf("rec_imp_%s_%s_%d", userID, item.ContentID, time.Now().UnixNano()),
			EventType:  "rec_impression",
			Scenario:   "content_feed",
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
			UserID:     userID,
			TargetID:   item.ContentID,
			Labels: map[string]string{
				"sessionId":   sessionID,
				"contentType": item.ContentType,
				"recallPath":  item.RecallPath,
			},
			Context: recImpressionContext(item.Score, item.AuthorID, item.Tags),
		})
	}
	return nil
}

// RecordEngagement records a user engagement event on a recommended item.
// If recScore is 0, it attempts to recover the original score from the impression cache.
func (f *FeedbackRecorder) RecordEngagement(ctx context.Context, signal BehaviorSignal, recScore float64) error {
	if f.recorder == nil {
		return nil
	}
	if recScore == 0 {
		recScore = f.lookupImpressionScore(ctx, signal.UserID, signal.ContentID)
	}
	return f.recorder.RecordEvent(ctx, learning.Event{
		EventID:    fmt.Sprintf("rec_eng_%s_%s_%d", signal.UserID, signal.ContentID, time.Now().UnixNano()),
		EventType:  "rec_engagement",
		Scenario:   "content_feed",
		OccurredAt: time.Now().UTC().Format(time.RFC3339),
		UserID:     signal.UserID,
		TargetID:   signal.ContentID,
		Labels: map[string]string{
			"sessionId":     signal.EffectiveSessionID(),
			"feedSessionId": signal.FeedSessionID,
			"action":        signal.Action,
		},
		Context: recEngagementContext(signal.Duration, recScore, signal.Tags, signal.FeedRequestID, signal.ReferralSource, signal.ContentType, signal.AuthorID),
	})
}

// RecordScorecard records an aggregate scoring metric for model evaluation.
func (f *FeedbackRecorder) RecordScorecard(ctx context.Context, userID, bucket string, dwellMs float64, interacted bool) error {
	if f.recorder == nil {
		return nil
	}
	score := dwellMs
	if interacted {
		score += 1000
	}
	comment := fmt.Sprintf("bucket=%s dwell=%.0fms interacted=%v", bucket, dwellMs, interacted)
	return f.recorder.RecordScorecard(ctx, learning.Scorecard{
		ScorecardID: fmt.Sprintf("rec_sc_%s_%d", userID, time.Now().UnixNano()),
		RunID:       bucket,
		Score:       score,
		Comment:     comment,
		Version:     "v1",
	})
}
