package assistant

import (
	"context"
	"fmt"
	"io"

	rctx "quwoquan_service/runtime/context"
)

// LLMClient abstracts LLM inference calls.
type LLMClient interface {
	ChatStream(ctx context.Context, prompt string, onChunk func(chunk string)) error
	Chat(ctx context.Context, prompt string) (string, error)
}

// QARequest is the user's natural language question.
type QARequest struct {
	UserID    string `json:"userId"`
	SessionID string `json:"sessionId"`
	Question  string `json:"question"`
}

// QARunner executes user questions against the three-layer context via LLM.
type QARunner struct {
	assembler *rctx.ContextAssembler
	llm       LLMClient
}

func NewQARunner(assembler *rctx.ContextAssembler, llm LLMClient) *QARunner {
	return &QARunner{assembler: assembler, llm: llm}
}

// RunStream assembles context, builds prompt, and streams the LLM answer.
func (r *QARunner) RunStream(ctx context.Context, req QARequest, writer io.Writer) error {
	assistCtx, err := r.assembler.Assemble(ctx, req.UserID, req.SessionID)
	if err != nil {
		return fmt.Errorf("assemble context: %w", err)
	}

	prompt := buildPrompt(assistCtx, req.Question)

	return r.llm.ChatStream(ctx, prompt, func(chunk string) {
		fmt.Fprintf(writer, "data: %s\n\n", chunk)
	})
}

// Run assembles context and returns a full answer (non-streaming).
func (r *QARunner) Run(ctx context.Context, req QARequest) (string, error) {
	assistCtx, err := r.assembler.Assemble(ctx, req.UserID, req.SessionID)
	if err != nil {
		return "", fmt.Errorf("assemble context: %w", err)
	}

	prompt := buildPrompt(assistCtx, req.Question)
	return r.llm.Chat(ctx, prompt)
}

// buildPrompt assembles a structured prompt from the three-layer context.
// Priority: PageContext > Session > Profile > RAG, with token budget awareness.
func buildPrompt(ac *rctx.AssistantContext, question string) string {
	var prompt string

	// System instruction
	prompt += "你是小趣助手，一个智能私人助手。请根据以下上下文回答用户的问题。\n\n"

	// Layer 1: PageContext (highest priority)
	if ac.PageContext != nil {
		prompt += "## 当前页面上下文\n"
		prompt += fmt.Sprintf("页面类型: %s\n", ac.PageContext.PageType)
		if ac.PageContext.Objects.Post != nil {
			p := ac.PageContext.Objects.Post
			prompt += fmt.Sprintf("正在查看的内容: [%s] %s\n", p.ContentType, p.Title)
			if p.Body != "" {
				body := p.Body
				if len(body) > 500 {
					body = body[:500] + "..."
				}
				prompt += fmt.Sprintf("内容摘要: %s\n", body)
			}
			if len(p.Tags) > 0 {
				prompt += fmt.Sprintf("标签: %v\n", p.Tags)
			}
			if p.Location != nil {
				prompt += fmt.Sprintf("位置: %.4f, %.4f\n", p.Location.Latitude, p.Location.Longitude)
			}
		}
		if ac.PageContext.Objects.Conversation != nil {
			c := ac.PageContext.Objects.Conversation
			prompt += fmt.Sprintf("当前对话: %s (%s)\n", c.ConversationID, c.Type)
		}
		if ac.PageContext.Objects.Circle != nil {
			ci := ac.PageContext.Objects.Circle
			prompt += fmt.Sprintf("当前圈子: %s\n", ci.Name)
		}
		if ac.PageContext.Objects.SearchQuery != "" {
			prompt += fmt.Sprintf("搜索词: %s\n", ac.PageContext.Objects.SearchQuery)
		}
		prompt += "\n"
	}

	// Layer 2: Session signals
	if ac.SessionSignals != nil && len(ac.SessionSignals.TopInterests) > 0 {
		prompt += "## 本次会话兴趣\n"
		prompt += fmt.Sprintf("实时兴趣标签: %v\n\n", ac.SessionSignals.TopInterests)
	}

	// Layer 3: Long-term profile
	if ac.HolisticProfile != nil {
		prompt += "## 用户画像\n"
		dims := map[string]rctx.ProfileDimension{
			"内容偏好": ac.HolisticProfile.ContentPreference,
			"社交":   ac.HolisticProfile.SocialGraph,
			"圈子":   ac.HolisticProfile.CircleActivity,
		}
		for name, dim := range dims {
			if len(dim.Tags) > 0 {
				prompt += fmt.Sprintf("- %s: ", name)
				count := 0
				for tag, weight := range dim.Tags {
					if count >= 5 {
						break
					}
					prompt += fmt.Sprintf("%s(%.1f) ", tag, weight)
					count++
				}
				prompt += "\n"
			}
		}
		prompt += "\n"
	}

	// RAG content
	if len(ac.RelevantContent) > 0 {
		prompt += "## 相关参考内容\n"
		for _, c := range ac.RelevantContent {
			text := c.Content
			if len(text) > 200 {
				text = text[:200] + "..."
			}
			prompt += fmt.Sprintf("- [%s] %s\n", c.Source, text)
		}
		prompt += "\n"
	}

	prompt += "## 用户问题\n" + question + "\n"

	return prompt
}
