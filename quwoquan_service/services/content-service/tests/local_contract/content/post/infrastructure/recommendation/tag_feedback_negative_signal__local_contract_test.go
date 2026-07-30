package recommendation_test

import (
	"testing"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

// 标签反馈必须是双向通道：只有正向权重时，用户无法把推错的标签压下去。
func TestDislikeWritesANegativeAffinityWeight(t *testing.T) {
	delta, err := ResolveTagFeedbackFeatureDelta("dislike")
	if err != nil {
		t.Fatalf("dislike must resolve, got %v", err)
	}
	if delta.Unchanged || delta.Clears {
		t.Fatalf("dislike must write a weight, got %+v", delta)
	}
	if delta.Weight >= 0 {
		t.Fatalf("dislike weight = %v, want negative", delta.Weight)
	}
}

// dislike 与 ignore 的区别是本次改动的核心：清除偏好不等于负偏好。
func TestIgnoreClearsWhileDislikeSuppresses(t *testing.T) {
	ignore, err := ResolveTagFeedbackFeatureDelta("ignore")
	if err != nil {
		t.Fatalf("ignore must resolve, got %v", err)
	}
	if !ignore.Clears {
		t.Fatalf("ignore must clear the affinity, got %+v", ignore)
	}
	if ignore.Weight != 0 {
		t.Fatalf("ignore must not carry a weight, got %v", ignore.Weight)
	}

	dislike, err := ResolveTagFeedbackFeatureDelta("dislike")
	if err != nil {
		t.Fatalf("dislike must resolve, got %v", err)
	}
	if dislike.Clears {
		t.Fatalf("dislike must persist a negative weight rather than clear")
	}
}

func TestClickAndDislikeAreSymmetricAroundNeutral(t *testing.T) {
	click, err := ResolveTagFeedbackFeatureDelta("click")
	if err != nil {
		t.Fatalf("click must resolve, got %v", err)
	}
	dislike, err := ResolveTagFeedbackFeatureDelta("dislike")
	if err != nil {
		t.Fatalf("dislike must resolve, got %v", err)
	}
	if click.Weight+dislike.Weight != 0 {
		t.Fatalf(
			"click %v and dislike %v must cancel out; an asymmetric pair silently biases the feed",
			click.Weight, dislike.Weight,
		)
	}
}

func TestCorrectLeavesFeaturesUntouched(t *testing.T) {
	delta, err := ResolveTagFeedbackFeatureDelta("correct")
	if err != nil {
		t.Fatalf("correct must resolve, got %v", err)
	}
	if !delta.Unchanged {
		t.Fatalf("correct must not change features, got %+v", delta)
	}
}

func TestUnsupportedActionFailsInsteadOfDegradingToNeutral(t *testing.T) {
	for _, action := range []string{"", "DISLIKE", "hide", "not_interested"} {
		delta, err := ResolveTagFeedbackFeatureDelta(action)
		if err == nil {
			t.Fatalf("action %q must be rejected, got %+v", action, delta)
		}
	}
}
