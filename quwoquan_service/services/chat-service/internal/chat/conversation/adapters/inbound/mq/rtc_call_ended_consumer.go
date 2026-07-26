package mq

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

const (
	rtcCallEndedStream = "events.rtc.call_ended"
	rtcCallLogGroup    = "chat-rtc-call-log"
	rtcCallEndedDLQ    = "events.rtc.call_ended-dlq"
)

type rtcCallLogWriter interface {
	AppendRtcCallLog(context.Context, application.RtcCallEndedFact) error
}

// RtcCallEndedConsumer 把 durable RTC CallEnded 事实投影为 chat
// system_call_log Message。Redis Stream message 仅在投影成功后 ACK。
type RtcCallEndedConsumer struct {
	client   rtredis.Client
	writer   rtcCallLogWriter
	consumer string
}

func NewRtcCallEndedConsumer(
	client rtredis.Client,
	writer rtcCallLogWriter,
	consumer string,
) *RtcCallEndedConsumer {
	return &RtcCallEndedConsumer{
		client:   client,
		writer:   writer,
		consumer: strings.TrimSpace(consumer),
	}
}

func (c *RtcCallEndedConsumer) Run(ctx context.Context) error {
	if c.client == nil || c.writer == nil || c.consumer == "" {
		return fmt.Errorf("rtc call ended consumer is not fully configured")
	}
	if err := c.client.XGroupCreateMkStream(
		ctx,
		rtcCallEndedStream,
		rtcCallLogGroup,
		"0",
	); err != nil {
		return err
	}
	for {
		claimed, _, err := c.client.XAutoClaim(
			ctx,
			rtcCallEndedStream,
			rtcCallLogGroup,
			c.consumer,
			30*time.Second,
			"0-0",
			50,
		)
		if err != nil {
			return err
		}
		if err := c.processMessages(ctx, claimed); err != nil {
			return err
		}
		messages, err := c.client.XReadGroup(
			ctx,
			rtcCallLogGroup,
			c.consumer,
			map[string]string{rtcCallEndedStream: ">"},
			50,
			time.Second,
		)
		if err != nil {
			return err
		}
		if err := c.processMessages(ctx, messages); err != nil {
			return err
		}
		select {
		case <-ctx.Done():
			return nil
		default:
		}
	}
}

func (c *RtcCallEndedConsumer) processMessages(
	ctx context.Context,
	messages []rtredis.StreamMessage,
) error {
	for _, message := range messages {
		fact, err := decodeRtcCallEndedFact(message.Values)
		if err != nil {
			if _, dlqErr := c.client.XAdd(ctx, rtcCallEndedDLQ, map[string]string{
				"sourceMessageId": message.ID,
				"eventId":         message.Values["eventId"],
				"reason":          "invalid_contract",
			}); dlqErr != nil {
				return fmt.Errorf(
					"dead-letter rtc CallEnded %s: %w",
					message.ID,
					dlqErr,
				)
			}
			if ackErr := c.client.XAck(
				ctx,
				rtcCallEndedStream,
				rtcCallLogGroup,
				message.ID,
			); ackErr != nil {
				return ackErr
			}
			continue
		}
		if err := c.writer.AppendRtcCallLog(ctx, fact); err != nil {
			return fmt.Errorf("project rtc CallEnded %s: %w", message.ID, err)
		}
		if err := c.client.XAck(
			ctx,
			rtcCallEndedStream,
			rtcCallLogGroup,
			message.ID,
		); err != nil {
			return err
		}
	}
	return nil
}

type rtcCallEndedEnvelope struct {
	CallID  string `json:"callId"`
	ActorID string `json:"actorId"`
	Payload struct {
		CallType       string `json:"callType"`
		InitiatorID    string `json:"initiatorId"`
		ConversationID string `json:"conversationId"`
		EndReason      string `json:"endReason"`
		DurationMs     int64  `json:"durationMs"`
		StartedAt      string `json:"startedAt"`
		EndedAt        string `json:"endedAt"`
	} `json:"payload"`
}

func decodeRtcCallEndedFact(
	values map[string]string,
) (application.RtcCallEndedFact, error) {
	var envelope rtcCallEndedEnvelope
	if err := json.Unmarshal([]byte(values["payloadJson"]), &envelope); err != nil {
		return application.RtcCallEndedFact{}, err
	}
	eventID := strings.TrimSpace(values["eventId"])
	if eventID == "" || strings.TrimSpace(envelope.CallID) == "" {
		return application.RtcCallEndedFact{}, fmt.Errorf(
			"eventId and callId are required",
		)
	}
	duration := envelope.Payload.DurationMs
	if raw := strings.TrimSpace(values["durationMs"]); raw != "" {
		if parsed, err := strconv.ParseInt(raw, 10, 64); err == nil {
			duration = parsed
		}
	}
	return application.RtcCallEndedFact{
		EventID:        eventID,
		CallID:         envelope.CallID,
		CallType:       envelope.Payload.CallType,
		InitiatorID:    envelope.Payload.InitiatorID,
		ConversationID: envelope.Payload.ConversationID,
		EndReason:      envelope.Payload.EndReason,
		DurationMs:     duration,
		StartedAt:      parseOptionalTime(envelope.Payload.StartedAt),
		EndedAt:        parseOptionalTime(envelope.Payload.EndedAt),
	}, nil
}

func parseOptionalTime(raw string) time.Time {
	value, _ := time.Parse(time.RFC3339Nano, strings.TrimSpace(raw))
	return value
}
