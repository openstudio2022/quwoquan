package tag_feedback_fact_test

import (
	"errors"
	"testing"
	"time"

	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/domain/tagfeedback/model"
)

func newFeedbackWithAction(t *testing.T, action string) (feedbackmodel.Feedback, error) {
	t.Helper()
	return feedbackmodel.NewFeedback(
		"feedback_1",
		"user_1",
		"persona",
		"Topic/摄影/器材/机身",
		action,
		"",
		"idem_1",
		time.Unix(1700000000, 0).UTC(),
	)
}

// 在 dislike 之前，标签只有正向与清除两种反馈，用户无法表达「不要再给我这个标签」。
func TestDislikeIsAnAcceptedFeedbackAction(t *testing.T) {
	feedback, err := newFeedbackWithAction(t, "dislike")
	if err != nil {
		t.Fatalf("dislike must be accepted, got %v", err)
	}
	if feedback.Action != "dislike" {
		t.Fatalf("action = %q, want dislike", feedback.Action)
	}
}

func TestEveryDeclaredFeedbackActionIsAccepted(t *testing.T) {
	for _, action := range []string{"click", "ignore", "correct", "dislike"} {
		if _, err := newFeedbackWithAction(t, action); err != nil {
			t.Fatalf("action %q must be accepted, got %v", action, err)
		}
	}
}

// 大小写与空白由域模型归一，是既定语义；只有真正未登记的取值才应被拒绝。
func TestFeedbackActionIsNormalizedBeforeAdmission(t *testing.T) {
	for _, action := range []string{"DISLIKE", " dislike ", "Dislike"} {
		feedback, err := newFeedbackWithAction(t, action)
		if err != nil {
			t.Fatalf("action %q must normalize to dislike, got %v", action, err)
		}
		if feedback.Action != "dislike" {
			t.Fatalf("action %q normalized to %q, want dislike", action, feedback.Action)
		}
	}
}

func TestUnknownFeedbackActionIsRejectedRatherThanCoerced(t *testing.T) {
	for _, action := range []string{"", "disliked", "hide", "not_interested"} {
		_, err := newFeedbackWithAction(t, action)
		if err == nil {
			t.Fatalf("action %q must be rejected", action)
		}
		if !errors.Is(err, feedbackmodel.ErrInvalidAction) &&
			!errors.Is(err, feedbackmodel.ErrInvalidArgument) {
			t.Fatalf("action %q returned an unexpected error: %v", action, err)
		}
	}
}
