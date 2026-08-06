// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
// readiness_case: report-tag-feedback-local
package tag_feedback_fact_test

import (
	"context"
	"testing"

	tagfeedback "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/application/tagfeedback"
	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback_fact/domain/tagfeedback/model"
)

func TestTagFeedbackFacadeAppendsCanonicalFact(t *testing.T) {
	sink := &readinessFeedbackSink{}
	facade, err := tagfeedback.NewFacade(sink, readinessTagRefValidator{})
	if err != nil {
		t.Fatalf("NewFacade() error = %v", err)
	}
	result, err := facade.Append(context.Background(), tagfeedback.AppendCommand{
		ActorID:        "persona-readiness",
		ActorKind:      "persona",
		TagRef:         "Topic/旅行",
		Action:         "click",
		Context:        "search-result",
		IdempotencyKey: "tag-feedback-readiness-1",
	})
	if err != nil {
		t.Fatalf("Append() error = %v", err)
	}
	if !result.Accepted || result.Replayed || len(sink.facts) != 1 {
		t.Fatalf("result=%+v facts=%+v", result, sink.facts)
	}
	if got := sink.facts[0]; got.TagRef != "Topic/旅行" || got.Action != "click" {
		t.Fatalf("canonical fact = %+v", got)
	}
}

type readinessFeedbackSink struct {
	facts []feedbackmodel.Feedback
}

func (sink *readinessFeedbackSink) Append(
	_ context.Context,
	fact feedbackmodel.Feedback,
) (feedbackmodel.Feedback, bool, error) {
	sink.facts = append(sink.facts, fact)
	return fact, false, nil
}

type readinessTagRefValidator struct{}

func (readinessTagRefValidator) TagRefExists(context.Context, string) (bool, error) {
	return true, nil
}
