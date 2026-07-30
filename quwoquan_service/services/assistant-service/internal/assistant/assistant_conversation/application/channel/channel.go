// Package channel defines the policy boundary between the assistant core and
// each delivery surface. A channel only declares identity, context window,
// answer boundary, and memory scope; orchestration remains channel-agnostic.
package channel

import (
	"fmt"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

type ID string

const (
	IDPersonal       ID = "personal_fullscreen"
	IDGroupMention   ID = "group_mention"
	IDProactive      ID = "proactive_delivery"
	IDCommentMention ID = "comment_mention"
)

type MemoryScope string

const (
	MemoryScopePrivateLongTerm MemoryScope = "private_long_term"
	MemoryScopeChannelOnly     MemoryScope = "channel_only"
)

type IdentityInput struct {
	ActorID   string
	PersonaID string
}

type Identity struct {
	ActorID   string
	PersonaID string
}

type ContextWindowPolicy struct {
	HistoryReadLimit int
	RecentTurnLimit  int
	MessageLimit     int
}

type AnswerBoundaryPolicy struct {
	Public         bool
	MaxAnswerRunes int
	PromptRule     string
}

type AssistantChannel interface {
	ID() ID
	ResolveIdentity(IdentityInput) (Identity, error)
	ContextWindow() ContextWindowPolicy
	AnswerBoundary() AnswerBoundaryPolicy
	MemoryScope() MemoryScope
}

type definition struct {
	id             ID
	contextWindow  ContextWindowPolicy
	answerBoundary AnswerBoundaryPolicy
	memoryScope    MemoryScope
}

func (d definition) ID() ID {
	return d.id
}

func (d definition) ResolveIdentity(input IdentityInput) (Identity, error) {
	actorID := strings.TrimSpace(input.ActorID)
	personaID := strings.TrimSpace(input.PersonaID)
	if actorID == "" || personaID == "" {
		return Identity{}, fmt.Errorf("assistant channel %s requires actor and persona identity", d.id)
	}
	return Identity{ActorID: actorID, PersonaID: personaID}, nil
}

func (d definition) ContextWindow() ContextWindowPolicy {
	return d.contextWindow
}

func (d definition) AnswerBoundary() AnswerBoundaryPolicy {
	return d.answerBoundary
}

func (d definition) MemoryScope() MemoryScope {
	return d.memoryScope
}

func Personal() AssistantChannel {
	return definition{
		id: IDPersonal,
		contextWindow: ContextWindowPolicy{
			HistoryReadLimit: 40,
			RecentTurnLimit:  6,
		},
		answerBoundary: AnswerBoundaryPolicy{
			MaxAnswerRunes: 12000,
			PromptRule:     "这是私人会话；可使用该会话内已授权上下文，但不得越过用户授权范围。",
		},
		memoryScope: MemoryScopePrivateLongTerm,
	}
}

func GroupMention() AssistantChannel {
	return definition{
		id: IDGroupMention,
		contextWindow: ContextWindowPolicy{
			HistoryReadLimit: 1,
			RecentTurnLimit:  1,
			MessageLimit:     20,
		},
		answerBoundary: AnswerBoundaryPolicy{
			Public:         true,
			MaxAnswerRunes: 2400,
			PromptRule:     "这是公开群聊回答；只可使用该群当前可见上下文，禁止使用或暗示提问者的私人长期记忆。",
		},
		memoryScope: MemoryScopeChannelOnly,
	}
}

func Proactive() AssistantChannel {
	return definition{
		id: IDProactive,
		contextWindow: ContextWindowPolicy{
			HistoryReadLimit: 20,
			RecentTurnLimit:  3,
		},
		answerBoundary: AnswerBoundaryPolicy{
			MaxAnswerRunes: 1600,
			PromptRule:     "这是主动投递；先给结论与变化，再给用户可执行的下一步。",
		},
		memoryScope: MemoryScopePrivateLongTerm,
	}
}

// CommentMention reserves the public comment boundary for M2. It is usable
// without changing orchestration, skill selection, or tool execution.
func CommentMention() AssistantChannel {
	return definition{
		id: IDCommentMention,
		contextWindow: ContextWindowPolicy{
			HistoryReadLimit: 1,
			RecentTurnLimit:  1,
			MessageLimit:     12,
		},
		answerBoundary: AnswerBoundaryPolicy{
			Public:         true,
			MaxAnswerRunes: 1200,
			PromptRule:     "这是公开评论区回答；只可使用评论线程公开可见事实，禁止使用私人长期记忆。",
		},
		memoryScope: MemoryScopeChannelOnly,
	}
}

func Resolve(turnType string, trigger assistant.AssistantTurnTrigger) AssistantChannel {
	switch strings.TrimSpace(trigger.Type) {
	case "chat_assistant_mentioned":
		return GroupMention()
	case "comment_assistant_mentioned":
		return CommentMention()
	case "cron", "subscription", "proactive_delivery":
		return Proactive()
	}
	if strings.TrimSpace(turnType) == "proactive" {
		return Proactive()
	}
	return Personal()
}
