package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

// NotificationAppMessageCommand is Assistant's typed outbound command to the
// Notification bounded context. It is not an Assistant aggregate or read
// model; lifecycle state, IDs, idempotency receipts and persistence remain
// owned by notification-service.
type NotificationAppMessageCommand struct {
	IdempotencyKey string
	UserID         string
	MessageType    string
	Source         string
	SourceID       string
	Destination    NotificationAppMessageDestination
	Title          string
	Summary        string
	Target         NotificationAppMessageTarget
	Provenance     NotificationAppMessageProvenance
}

type NotificationAppMessageDestination struct {
	Type string
	ID   string
}

type NotificationAppMessageTarget struct {
	TargetType string
	TargetID   string
	RouteID    string
	RoutePath  string
	Dimension  string
}

type NotificationAppMessageProvenance struct {
	Personalized    bool
	InterestTags    []string
	MatchedSegments []string
	LifecycleStage  string
}

type NotificationAppMessageReceipt struct {
	MessageID string
}

type NotificationAppMessageCommandWriter interface {
	CreateAppMessage(
		ctx context.Context,
		command NotificationAppMessageCommand,
	) (NotificationAppMessageReceipt, error)
}

func WithNotificationAppMessageCommandWriter(
	writer NotificationAppMessageCommandWriter,
) AssistantServiceOption {
	return func(s *AssistantService) { s.notificationMessages = writer }
}

func (s *AssistantService) publishNotificationAppMessage(
	ctx context.Context,
	command NotificationAppMessageCommand,
) (NotificationAppMessageReceipt, error) {
	if s.notificationMessages == nil {
		return NotificationAppMessageReceipt{}, rterr.NewUnavailable(
			rterr.ModuleAssistant,
			"应用消息通道不可用",
			"notification app message command writer is not configured",
		)
	}
	// 投递目的地防错发校验（P0 告警 AssistantWrongDestinationIncident）：
	// 主动投递必须携带非空 user 目的地且与命令 owner 一致；校验失败计入
	// wrong-destination 指标并拒绝投递，宁可漏发不可错发。
	destinationID := strings.TrimSpace(command.Destination.ID)
	ownerID := strings.TrimSpace(command.UserID)
	if destinationID == "" || ownerID == "" ||
		(command.Destination.Type == "user" && destinationID != ownerID) {
		RecordAssistantWrongDestinationIncident()
		return NotificationAppMessageReceipt{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"投递目的地校验失败",
			"proactive delivery destination mismatch: type="+command.Destination.Type,
		)
	}
	return s.notificationMessages.CreateAppMessage(ctx, command)
}
