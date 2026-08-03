// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package assistant_run_test

import (
	"errors"
	"testing"

	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
)

func TestAssistantRunIntentIsOneTaggedUnion(t *testing.T) {
	tests := []struct {
		name   string
		intent rundomain.Intent
		want   string
	}{
		{name: "answer", intent: rundomain.Intent{Kind: "answer", Answer: &rundomain.AnswerIntent{Text: " 回答 "}}, want: "回答"},
		{name: "search", intent: rundomain.Intent{Kind: "search", Search: &rundomain.SearchIntent{Query: " 西湖 "}}, want: "西湖"},
		{name: "creation", intent: rundomain.Intent{Kind: "creation_assistance", CreationAssistance: &rundomain.CreationAssistanceIntent{DraftTitle: "标题", DraftSummary: "摘要"}}, want: "标题\n摘要"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			got, err := test.intent.PrimaryText()
			if err != nil || got != test.want {
				t.Fatalf("text=%q err=%v", got, err)
			}
		})
	}
}

func TestAssistantRunIntentRejectsMixedOrEmptyPayload(t *testing.T) {
	for _, intent := range []rundomain.Intent{
		{Kind: "answer", Answer: &rundomain.AnswerIntent{Text: "a"}, Search: &rundomain.SearchIntent{Query: "b"}},
		{Kind: "search", Search: &rundomain.SearchIntent{}},
		{Kind: "creation_assistance", CreationAssistance: &rundomain.CreationAssistanceIntent{}},
		{Kind: "unknown"},
	} {
		if _, err := intent.PrimaryText(); !errors.Is(err, rundomain.ErrInvalidIntent) {
			t.Fatalf("intent=%+v err=%v", intent, err)
		}
	}
}
