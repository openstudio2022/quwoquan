package orchestration

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

func WithNotificationAppMessageCommandWriter(
	writer ports.NotificationAppMessageCommandWriter,
) AssistantServiceOption {
	return func(s *AssistantService) { s.notificationMessages = writer }
}

func (s *AssistantService) publishNotificationAppMessage(
	ctx context.Context,
	command ports.NotificationAppMessageCommand,
) (ports.NotificationAppMessageReceipt, error) {
	if s.notificationMessages == nil {
		return ports.NotificationAppMessageReceipt{}, rterr.NewUnavailable(
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
		return ports.NotificationAppMessageReceipt{}, rterr.NewInvalidArgument(
			rterr.ModuleAssistant,
			"投递目的地校验失败",
			"proactive delivery destination mismatch: type="+command.Destination.Type,
		)
	}
	return s.notificationMessages.CreateAppMessage(ctx, command)
}
