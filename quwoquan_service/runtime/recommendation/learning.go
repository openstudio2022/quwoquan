package recommendation

import (
	"context"
	"fmt"
	"time"

	learning "quwoquan_service/runtime/learning"
)

// FeedbackRecorder records recommendation outcomes for offline learning.
type FeedbackRecorder struct {
	recorder learning.Recorder
}

func NewFeedbackRecorder(recorder learning.Recorder) *FeedbackRecorder {
	return &FeedbackRecorder{recorder: recorder}
}

// RecordImpression records that a feed item was shown to the user.
func (f *FeedbackRecorder) RecordImpression(ctx context.Context, userID, sessionID string, items []FeedItem) error {
	if f.recorder == nil {
		return nil
	}
	for _, item := range items {
		_ = f.recorder.RecordEvent(ctx, learning.Event{
			EventID:   fmt.Sprintf("rec_imp_%s_%s_%d", userID, item.ContentID, time.Now().UnixNano()),
			EventType: "rec_impression",
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
			UserID:    userID,
			TargetID:  item.ContentID,
			Labels: map[string]string{
				"sessionId":   sessionID,
				"contentType": item.ContentType,
				"recallPath":  item.RecallPath,
			},
			Context: map[string]any{
				"score":    item.Score,
				"authorId": item.AuthorID,
				"tags":     item.Tags,
			},
		})
	}
	return nil
}

// RecordEngagement records a user engagement event on a recommended item.
func (f *FeedbackRecorder) RecordEngagement(ctx context.Context, signal BehaviorSignal, recScore float64) error {
	if f.recorder == nil {
		return nil
	}
	return f.recorder.RecordEvent(ctx, learning.Event{
		EventID:    fmt.Sprintf("rec_eng_%s_%s_%d", signal.UserID, signal.ContentID, time.Now().UnixNano()),
		EventType:  "rec_engagement",
		OccurredAt: time.Now().UTC().Format(time.RFC3339),
		UserID:     signal.UserID,
		TargetID:   signal.ContentID,
		Labels: map[string]string{
			"sessionId": signal.SessionID,
			"action":    signal.Action,
		},
		Context: map[string]any{
			"duration": signal.Duration,
			"recScore": recScore,
			"tags":     signal.Tags,
		},
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
