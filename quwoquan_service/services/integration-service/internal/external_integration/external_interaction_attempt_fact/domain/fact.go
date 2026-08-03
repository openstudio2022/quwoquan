package domain

import (
	"fmt"
	"strings"
	"time"
)

// Fact 是一次 provider 调用的不可变审计事实。任何可重试任务状态或结果发布
// 状态都不属于该对象。
type Fact struct {
	AttemptID             string
	RequestID             string
	TaskID                string
	SubjectDigest         string
	Operation             string
	Provider              string
	ProviderRequestID     string
	ProviderRequestDigest string
	MaskedRecipient       string
	LatencyMS             int64
	Status                string
	NormalizedError       string
	Retryable             bool
	RecoveryAction        string
	Attributes            map[string]string
	CreatedAt             time.Time
}

func NewFact(fact Fact) (Fact, error) {
	fact.AttemptID = strings.TrimSpace(fact.AttemptID)
	fact.RequestID = strings.TrimSpace(fact.RequestID)
	fact.TaskID = strings.TrimSpace(fact.TaskID)
	fact.SubjectDigest = strings.TrimSpace(fact.SubjectDigest)
	fact.Operation = strings.TrimSpace(fact.Operation)
	fact.Provider = strings.TrimSpace(fact.Provider)
	fact.ProviderRequestID = strings.TrimSpace(fact.ProviderRequestID)
	fact.ProviderRequestDigest = strings.TrimSpace(fact.ProviderRequestDigest)
	fact.MaskedRecipient = strings.TrimSpace(fact.MaskedRecipient)
	fact.Status = strings.TrimSpace(fact.Status)
	fact.NormalizedError = strings.TrimSpace(fact.NormalizedError)
	fact.RecoveryAction = strings.TrimSpace(fact.RecoveryAction)
	fact.CreatedAt = fact.CreatedAt.UTC()

	if fact.AttemptID == "" || fact.RequestID == "" || fact.TaskID == "" {
		return Fact{}, fmt.Errorf("attemptId, requestId and taskId are required")
	}
	if fact.Operation == "" || fact.Provider == "" || fact.Status == "" {
		return Fact{}, fmt.Errorf("operation, provider and status are required")
	}
	if !strings.HasPrefix(fact.ProviderRequestDigest, "sha256:") ||
		len(fact.ProviderRequestDigest) != len("sha256:")+64 {
		return Fact{}, fmt.Errorf("providerRequestDigest must be canonical SHA-256")
	}
	if fact.LatencyMS < 0 {
		return Fact{}, fmt.Errorf("latencyMs cannot be negative")
	}
	if fact.RecoveryAction == "" || fact.CreatedAt.IsZero() {
		return Fact{}, fmt.Errorf("recoveryAction and createdAt are required")
	}
	if fact.Attributes == nil {
		fact.Attributes = map[string]string{}
	}
	return fact, nil
}
