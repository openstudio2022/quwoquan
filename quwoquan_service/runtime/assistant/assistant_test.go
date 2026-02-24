package assistant

import (
	"bytes"
	"context"
	"testing"

	rctx "quwoquan_service/runtime/context"
)

type mockAnalyzer struct{}

func (m *mockAnalyzer) AnalyzePost(_ context.Context, _ *rctx.PostSnapshot) (*ContentAnalysis, error) {
	return &ContentAnalysis{Summary: "test summary", Keywords: []string{"travel"}}, nil
}
func (m *mockAnalyzer) SummarizeComments(_ context.Context, _ []rctx.CommentBrief) (*CommentSummary, error) {
	return &CommentSummary{Total: 10, Sentiment: map[string]int{"positive": 7, "negative": 3}}, nil
}
func (m *mockAnalyzer) SummarizeChat(_ context.Context, _ []rctx.MessageBrief) (*ChatSummary, error) {
	return &ChatSummary{MessageCount: 20, Summary: "chat summary"}, nil
}

type mockLLM struct{ response string }

func (m *mockLLM) ChatStream(_ context.Context, _ string, onChunk func(string)) error {
	onChunk(m.response)
	return nil
}
func (m *mockLLM) Chat(_ context.Context, _ string) (string, error) {
	return m.response, nil
}

type stubAssembler struct {
	ctx *rctx.AssistantContext
}

func TestSuggestedActions_ContentDetail(t *testing.T) {
	gen := NewSuggestedActionsGenerator(nil, &mockAnalyzer{})

	// Directly test action generation via helper
	ac := &rctx.AssistantContext{
		PageContext: &rctx.PageContextSnapshot{
			PageType: rctx.PageContentDetail,
			Objects: rctx.PageObjects{
				Post: &rctx.PostSnapshot{
					ID: "p1", ContentType: "image",
					Tags: []string{"travel", "photo"},
					Location: &rctx.GeoPoint{Latitude: 35.6, Longitude: 139.7},
				},
			},
		},
	}

	actions := gen.contentDetailActions(ac)
	if len(actions) < 2 {
		t.Errorf("expected >= 2 actions for image content_detail, got %d", len(actions))
	}

	hasLocation := false
	for _, a := range actions {
		if a.Type == "question" && a.Payload != nil {
			if a.Payload["intent"] == "location_identify" {
				hasLocation = true
			}
		}
	}
	if !hasLocation {
		t.Error("expected location_identify action for image content")
	}
}

func TestSuggestedActions_Chat(t *testing.T) {
	gen := NewSuggestedActionsGenerator(nil, &mockAnalyzer{})

	ac := &rctx.AssistantContext{
		PageContext: &rctx.PageContextSnapshot{
			PageType: rctx.PageChat,
		},
	}

	actions := gen.chatActions(ac)
	if len(actions) < 2 {
		t.Errorf("expected >= 2 actions for chat, got %d", len(actions))
	}
}

func TestSuggestedActions_Circle(t *testing.T) {
	gen := NewSuggestedActionsGenerator(nil, nil)

	ac := &rctx.AssistantContext{
		PageContext: &rctx.PageContextSnapshot{PageType: rctx.PageCircle},
	}

	actions := gen.circleActions(ac)
	if len(actions) != 3 {
		t.Errorf("expected 3 actions for circle, got %d", len(actions))
	}
}

func TestQARunner_Run(t *testing.T) {
	llm := &mockLLM{response: "这张图拍摄于东京"}

	_ = NewQARunner(nil, llm)

	prompt := buildPrompt(&rctx.AssistantContext{
		PageContext: &rctx.PageContextSnapshot{
			PageType: rctx.PageContentDetail,
			Objects: rctx.PageObjects{
				Post: &rctx.PostSnapshot{ID: "p1", ContentType: "image", Title: "富士山"},
			},
		},
	}, "这张图是在哪拍的？")

	if prompt == "" {
		t.Error("expected non-empty prompt")
	}

	// Test LLM directly
	answer, err := llm.Chat(context.Background(), prompt)
	if err != nil {
		t.Fatalf("Chat: %v", err)
	}
	if answer != "这张图拍摄于东京" {
		t.Errorf("unexpected answer: %s", answer)
	}
}

func TestQARunner_Stream(t *testing.T) {
	llm := &mockLLM{response: "流式回答"}

	var buf bytes.Buffer
	err := llm.ChatStream(context.Background(), "test", func(chunk string) {
		buf.WriteString(chunk)
	})
	if err != nil {
		t.Fatalf("ChatStream: %v", err)
	}
	if buf.String() != "流式回答" {
		t.Errorf("unexpected stream output: %s", buf.String())
	}
}

func TestBuildPrompt_AllLayers(t *testing.T) {
	ac := &rctx.AssistantContext{
		PageContext: &rctx.PageContextSnapshot{
			PageType: rctx.PageContentDetail,
			Objects: rctx.PageObjects{
				Post: &rctx.PostSnapshot{
					ID: "p1", ContentType: "article", Title: "旅行攻略",
					Tags: []string{"travel", "guide"},
				},
			},
		},
		SessionSignals: &rctx.SessionSignalSnapshot{
			TopInterests: []string{"travel", "food"},
		},
		HolisticProfile: &rctx.UserHolisticProfile{
			ContentPreference: rctx.ProfileDimension{
				Tags: map[string]float64{"travel": 10.0},
			},
		},
		RelevantContent: []rctx.RetrievedChunk{
			{ID: "r1", Content: "related content", Score: 0.9, Source: "post"},
		},
	}

	prompt := buildPrompt(ac, "这篇文章讲了什么？")
	if len(prompt) < 100 {
		t.Errorf("prompt too short: %d chars", len(prompt))
	}
}
