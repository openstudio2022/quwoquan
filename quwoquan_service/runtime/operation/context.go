package operation

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

type ActorRequirement string

const (
	ActorNone            ActorRequirement = "none"
	ActorAccount         ActorRequirement = "account"
	ActorPersona         ActorRequirement = "persona"
	ActorDevice          ActorRequirement = "device"
	ActorPersonaOrDevice ActorRequirement = "persona_or_device"
)

// ActorContext 明确区分账号安全主体、公开业务主体与游客设备主体。
type ActorContext struct {
	AccountID     string `json:"accountId,omitempty"`
	PersonaID     string `json:"personaId,omitempty"`
	DeviceActorID string `json:"deviceActorId,omitempty"`
}

func (a ActorContext) Validate(requirement ActorRequirement) error {
	switch requirement {
	case ActorNone:
		return nil
	case ActorAccount:
		if strings.TrimSpace(a.AccountID) == "" {
			return errors.New("account actor is required")
		}
	case ActorPersona:
		if strings.TrimSpace(a.PersonaID) == "" {
			return errors.New("persona actor is required")
		}
	case ActorDevice:
		if strings.TrimSpace(a.DeviceActorID) == "" {
			return errors.New("device actor is required")
		}
	case ActorPersonaOrDevice:
		if strings.TrimSpace(a.PersonaID) == "" && strings.TrimSpace(a.DeviceActorID) == "" {
			return errors.New("persona or device actor is required")
		}
	default:
		return fmt.Errorf("unknown actor requirement %q", requirement)
	}
	return nil
}

// BusinessActorID 返回业务事实的唯一 actor。账号 ID 不得冒充公开业务主体。
func (a ActorContext) BusinessActorID() (string, bool) {
	if personaID := strings.TrimSpace(a.PersonaID); personaID != "" {
		return personaID, true
	}
	if deviceActorID := strings.TrimSpace(a.DeviceActorID); deviceActorID != "" {
		return deviceActorID, true
	}
	return "", false
}

// Context 是 HTTP、MQ、task 与 App operation 的统一归因脊柱。
// Attributes 只允许脱敏字符串，禁止放业务 DTO、token 或异常对象。
type Context struct {
	OperationID      string            `json:"operationId"`
	RequestID        string            `json:"requestId"`
	TraceID          string            `json:"traceId"`
	IdempotencyKey   string            `json:"idempotencyKey,omitempty"`
	SessionID        string            `json:"sessionId,omitempty"`
	ClientPageID     string            `json:"clientPageId,omitempty"`
	SurfaceID        string            `json:"surfaceId,omitempty"`
	RouteID          string            `json:"routeId,omitempty"`
	ReferralSource   string            `json:"referralSource,omitempty"`
	FeedRequestID    string            `json:"feedRequestId,omitempty"`
	ShareID          string            `json:"shareId,omitempty"`
	ModelID          string            `json:"modelId,omitempty"`
	ExperimentBucket string            `json:"experimentBucket,omitempty"`
	Actor            ActorContext      `json:"actor"`
	Attributes       map[string]string `json:"attributes,omitempty"`
}

func (c Context) Validate(requirement ActorRequirement) error {
	if strings.TrimSpace(c.OperationID) == "" {
		return errors.New("operationId is required")
	}
	if strings.TrimSpace(c.RequestID) == "" {
		return errors.New("requestId is required")
	}
	if strings.TrimSpace(c.TraceID) == "" {
		return errors.New("traceId is required")
	}
	return c.Actor.Validate(requirement)
}

type contextKey struct{}

func WithContext(parent context.Context, current Context) context.Context {
	return context.WithValue(parent, contextKey{}, current)
}

func FromContext(current context.Context) (Context, bool) {
	value, ok := current.Value(contextKey{}).(Context)
	return value, ok
}
