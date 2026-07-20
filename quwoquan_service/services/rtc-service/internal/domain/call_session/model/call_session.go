// CallSession 聚合根模型。字段与 contracts/metadata/rtc/call_session/fields.yaml
// 对齐；Version 是服务端内部乐观并发 CAS 版本（不进公开请求，只随响应下发）。
package model

import "time"

type CallSession struct {
	ID                  string        `json:"callId" bson:"_id"`
	Version             int64         `json:"version" bson:"version"`
	CallType            string        `json:"callType" bson:"callType"`
	Status              string        `json:"status" bson:"status"`
	InitiatorID         string        `json:"initiatorId" bson:"initiatorId"`
	InitiatorRingtoneID string        `json:"initiatorRingtoneId,omitempty" bson:"initiatorRingtoneId,omitempty"`
	ConversationID      string        `json:"conversationId,omitempty" bson:"conversationId,omitempty"`
	CircleID            string        `json:"circleId,omitempty" bson:"circleId,omitempty"`
	RoomID              string        `json:"roomId" bson:"roomId"`
	MaxParticipants     int           `json:"maxParticipants" bson:"maxParticipants"`
	ParticipantCount    int           `json:"participantCount" bson:"participantCount"`
	Participants        []Participant `json:"participants" bson:"participants"`
	IsScreenSharing     bool          `json:"isScreenSharing" bson:"isScreenSharing"`
	ScreenShareUserID   string        `json:"screenShareUserId,omitempty" bson:"screenShareUserId,omitempty"`
	EndReason           string        `json:"endReason,omitempty" bson:"endReason,omitempty"`
	DurationMs          int64         `json:"durationMs,omitempty" bson:"durationMs,omitempty"`
	StartedAt           *time.Time    `json:"startedAt,omitempty" bson:"startedAt,omitempty"`
	EndedAt             *time.Time    `json:"endedAt,omitempty" bson:"endedAt,omitempty"`
	CreatedAt           time.Time     `json:"createdAt" bson:"createdAt"`
	UpdatedAt           time.Time     `json:"updatedAt" bson:"updatedAt"`
}

const (
	CallTypeAudio = "audio"
	CallTypeVideo = "video"

	StatusInitiated  = "initiated"
	StatusRinging    = "ringing"
	StatusConnecting = "connecting"
	StatusInCall     = "in_call"
	StatusEnded      = "ended"

	EndReasonNormal    = "normal"
	EndReasonCancelled = "cancelled"
	EndReasonRejected  = "rejected"
	EndReasonNoAnswer  = "no_answer"
	EndReasonError     = "error"
	EndReasonTimeout   = "timeout"
	EndReasonLastLeave = "last_leave"

	MaxParticipants1v1   = 2
	MaxParticipantsGroup = 32
)
