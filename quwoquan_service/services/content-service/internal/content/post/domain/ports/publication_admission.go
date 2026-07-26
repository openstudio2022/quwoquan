package ports

import (
	"context"
	"time"
)

type PublicationRateRequest struct {
	PersonaID       string
	PublishIntentID string
	OccurredAt      time.Time
}

type PublicationRateDecision struct {
	Allowed    bool
	RetryAfter time.Duration
}

// PublicationRateGate 是 Post 发布命令的 Persona 级原子频控端口。
// 存储与分布式原子性由 infrastructure adapter 负责；依赖错误必须 fail-closed。
type PublicationRateGate interface {
	AdmitPublication(
		context.Context,
		PublicationRateRequest,
	) (PublicationRateDecision, error)
}

type PublicationSafetyRequest struct {
	PostID               string
	PublishIntentID      string
	PersonaID            string
	ContentType          string
	Title                string
	Body                 string
	ArticleMarkdown      string
	SemanticMentionCount int
	ContentDigest        string
}

type PublicationSafetyDecision string

const (
	PublicationSafetyAllow       PublicationSafetyDecision = "allow"
	PublicationSafetyReview      PublicationSafetyDecision = "review"
	PublicationSafetyReject      PublicationSafetyDecision = "reject"
	PublicationSafetyUnavailable PublicationSafetyDecision = "unavailable"
)

type PublicationSafetyResult struct {
	Decision   PublicationSafetyDecision
	ReasonCode string
}

// PublicationSafetyGate 对不可变 Post revision 作发布前安全裁决。
// unavailable 不是 allow；application 必须降级为不可公开 pending_review。
type PublicationSafetyGate interface {
	EvaluatePublication(
		context.Context,
		PublicationSafetyRequest,
	) (PublicationSafetyResult, error)
}
