package assistant

import (
	"context"
	"fmt"

	rctx "quwoquan_service/runtime/context"
	rtredis "quwoquan_service/runtime/redis"
)

// SuggestedActionsRequest identifies the page + object to generate suggestions for.
type SuggestedActionsRequest struct {
	UserID    string       `json:"userId"`
	SessionID string       `json:"sessionId"`
	PageType  rctx.PageType `json:"pageType"`
	ObjectID  string       `json:"objectId"`
}

// SuggestedActionsResponse returns actions and optional summaries.
type SuggestedActionsResponse struct {
	Actions        []SuggestedAction `json:"actions"`
	CommentSummary *CommentSummary   `json:"commentSummary,omitempty"`
	ChatSummary    *ChatSummary      `json:"chatSummary,omitempty"`
	CircleInsight  *CircleInsight    `json:"circleInsight,omitempty"`
}

type SuggestedAction struct {
	Type    string         `json:"type"`
	Label   string         `json:"label"`
	Icon    string         `json:"icon"`
	Payload map[string]any `json:"payload,omitempty"`
}

type CommentSummary struct {
	Total     int               `json:"total"`
	Sentiment map[string]int    `json:"sentiment"`
	TopViews  []string          `json:"topViews"`
}

type ChatSummary struct {
	MessageCount int      `json:"messageCount"`
	TopTopics    []string `json:"topTopics"`
	Summary      string   `json:"summary"`
}

type CircleInsight struct {
	MemberCount    int      `json:"memberCount"`
	RecentActivity int      `json:"recentActivity"`
	RelatedCircles []string `json:"relatedCircles"`
}

// ContentAnalyzer analyzes content using LLM (interface for mocking).
type ContentAnalyzer interface {
	AnalyzePost(ctx context.Context, post *rctx.PostSnapshot) (*ContentAnalysis, error)
	SummarizeComments(ctx context.Context, comments []rctx.CommentBrief) (*CommentSummary, error)
	SummarizeChat(ctx context.Context, messages []rctx.MessageBrief) (*ChatSummary, error)
}

type ContentAnalysis struct {
	Summary    string   `json:"summary"`
	Keywords   []string `json:"keywords"`
	Entities   []Entity `json:"entities"`
	Sentiment  string   `json:"sentiment"`
}

type Entity struct {
	Type  string `json:"type"`
	Value string `json:"value"`
}

// CacheableAnalyzer wraps a ContentAnalyzer with Redis caching.
type CacheableAnalyzer struct {
	inner ContentAnalyzer
	cache rtredis.Client
	ttl   string
}

func NewCacheableAnalyzer(inner ContentAnalyzer, cache rtredis.Client) *CacheableAnalyzer {
	return &CacheableAnalyzer{inner: inner, cache: cache, ttl: "24h"}
}

// SuggestedActionsGenerator produces page-appropriate suggested actions.
type SuggestedActionsGenerator struct {
	assembler *rctx.ContextAssembler
	analyzer  ContentAnalyzer
}

func NewSuggestedActionsGenerator(assembler *rctx.ContextAssembler, analyzer ContentAnalyzer) *SuggestedActionsGenerator {
	return &SuggestedActionsGenerator{assembler: assembler, analyzer: analyzer}
}

func (g *SuggestedActionsGenerator) Generate(ctx context.Context, req SuggestedActionsRequest) (*SuggestedActionsResponse, error) {
	assistCtx, err := g.assembler.Assemble(ctx, req.UserID, req.SessionID)
	if err != nil {
		return nil, fmt.Errorf("assemble context: %w", err)
	}

	resp := &SuggestedActionsResponse{}

	switch req.PageType {
	case rctx.PageContentDetail:
		resp.Actions = g.contentDetailActions(assistCtx)
		if assistCtx.PageContext != nil && assistCtx.PageContext.Objects.Post != nil {
			post := assistCtx.PageContext.Objects.Post
			if g.analyzer != nil && len(post.Comments) > 0 {
				summary, _ := g.analyzer.SummarizeComments(ctx, post.Comments)
				resp.CommentSummary = summary
			}
		}

	case rctx.PageChat, rctx.PageGroupChat:
		resp.Actions = g.chatActions(assistCtx)
		if assistCtx.PageContext != nil && assistCtx.PageContext.Objects.Conversation != nil {
			conv := assistCtx.PageContext.Objects.Conversation
			if g.analyzer != nil && len(conv.RecentMessages) > 0 {
				summary, _ := g.analyzer.SummarizeChat(ctx, conv.RecentMessages)
				resp.ChatSummary = summary
			}
		}

	case rctx.PageCircle:
		resp.Actions = g.circleActions(assistCtx)

	case rctx.PageSearch:
		resp.Actions = g.searchActions(assistCtx)

	case rctx.PageFeed:
		resp.Actions = g.feedActions(assistCtx)

	case rctx.PageUserProfile:
		resp.Actions = g.profileActions(assistCtx)

	default:
		resp.Actions = g.defaultActions()
	}

	return resp, nil
}

func (g *SuggestedActionsGenerator) contentDetailActions(ac *rctx.AssistantContext) []SuggestedAction {
	actions := []SuggestedAction{
		{Type: "summary", Label: "帮你总结这篇内容", Icon: "summarize"},
	}
	if ac.PageContext != nil && ac.PageContext.Objects.Post != nil {
		post := ac.PageContext.Objects.Post
		switch post.ContentType {
		case "image":
			actions = append(actions,
				SuggestedAction{Type: "question", Label: "这张图是在哪拍的？", Icon: "location", Payload: map[string]any{"intent": "location_identify"}},
				SuggestedAction{Type: "search", Label: "搜索类似图片", Icon: "search", Payload: map[string]any{"intent": "similar_search"}},
			)
		case "article":
			actions = append(actions,
				SuggestedAction{Type: "question", Label: "这篇文章的要点是什么？", Icon: "key_points"},
			)
			if post.Location != nil {
				actions = append(actions,
					SuggestedAction{Type: "plan", Label: "帮我规划出行", Icon: "travel", Payload: map[string]any{"intent": "travel_plan", "location": post.Location}},
				)
			}
		case "video":
			actions = append(actions,
				SuggestedAction{Type: "summary", Label: "视频关键时刻", Icon: "highlights"},
			)
		}
		if len(post.Comments) > 5 {
			actions = append(actions,
				SuggestedAction{Type: "summary", Label: "评论总结", Icon: "comment_summary"},
			)
		}
	}
	return actions
}

func (g *SuggestedActionsGenerator) chatActions(ac *rctx.AssistantContext) []SuggestedAction {
	actions := []SuggestedAction{
		{Type: "summary", Label: "总结这段对话", Icon: "chat_summary"},
		{Type: "reply", Label: "帮我生成回复", Icon: "auto_reply"},
	}
	return actions
}

func (g *SuggestedActionsGenerator) circleActions(ac *rctx.AssistantContext) []SuggestedAction {
	return []SuggestedAction{
		{Type: "summary", Label: "圈子动态总结", Icon: "circle_summary"},
		{Type: "recommend", Label: "推荐关联圈子", Icon: "circle_related"},
		{Type: "recommend", Label: "推荐圈内好友", Icon: "friend_suggest"},
	}
}

func (g *SuggestedActionsGenerator) searchActions(ac *rctx.AssistantContext) []SuggestedAction {
	actions := []SuggestedAction{
		{Type: "search", Label: "用自然语言搜索", Icon: "nl_search"},
	}
	if ac.PageContext != nil && ac.PageContext.Objects.SearchQuery != "" {
		actions = append(actions,
			SuggestedAction{Type: "search", Label: "帮你找类似内容", Icon: "similar", Payload: map[string]any{"query": ac.PageContext.Objects.SearchQuery}},
		)
	}
	return actions
}

func (g *SuggestedActionsGenerator) feedActions(_ *rctx.AssistantContext) []SuggestedAction {
	return []SuggestedAction{
		{Type: "question", Label: "问问小趣", Icon: "ask"},
	}
}

func (g *SuggestedActionsGenerator) profileActions(_ *rctx.AssistantContext) []SuggestedAction {
	return []SuggestedAction{
		{Type: "summary", Label: "查看兴趣画像", Icon: "profile_insight"},
	}
}

func (g *SuggestedActionsGenerator) defaultActions() []SuggestedAction {
	return []SuggestedAction{
		{Type: "question", Label: "有什么可以帮你？", Icon: "help"},
	}
}
