package call_session

import (
	"errors"
	"time"

	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

type CallSessionService struct{}

func NewCallSessionService() *CallSessionService {
	return &CallSessionService{}
}

func (s *CallSessionService) InitiateCall(initiatorID, callType, conversationID, circleID string, inviteeIDs []string) (*model.CallSession, error) {
	if initiatorID == "" {
		return nil, errors.New("initiator ID required")
	}
	if callType != model.CallTypeAudio && callType != model.CallTypeVideo {
		return nil, errors.New("invalid call type")
	}

	maxP := model.MaxParticipantsGroup
	if len(inviteeIDs) == 1 && circleID == "" {
		maxP = model.MaxParticipants1v1
	}

	now := time.Now()
	session := &model.CallSession{
		CallType:        callType,
		Status:          model.StatusInitiated,
		InitiatorID:     initiatorID,
		ConversationID:  conversationID,
		CircleID:        circleID,
		MaxParticipants: maxP,
		CreatedAt:       now,
		UpdatedAt:       now,
	}

	session.Participants = []model.Participant{
		{
			UserID:   initiatorID,
			Role:     model.RoleInitiator,
			Status:   model.ParticipantConnecting,
			JoinedAt: &now,
		},
	}
	for _, id := range inviteeIDs {
		session.Participants = append(session.Participants, model.Participant{
			UserID: id,
			Role:   model.RoleInvitee,
			Status: model.ParticipantInvited,
		})
	}
	session.ParticipantCount = len(session.Participants)
	return session, nil
}

func (s *CallSessionService) SetRinging(session *model.CallSession) {
	if session.Status == model.StatusInitiated {
		session.Status = model.StatusRinging
		for i := range session.Participants {
			if session.Participants[i].Status == model.ParticipantInvited {
				session.Participants[i].Status = model.ParticipantRinging
			}
		}
		session.UpdatedAt = time.Now()
	}
}

func (s *CallSessionService) AnswerCall(session *model.CallSession, userID string) error {
	if session.Status != model.StatusRinging &&
		session.Status != model.StatusInitiated &&
		session.Status != model.StatusConnecting &&
		session.Status != model.StatusInCall {
		return errors.New("can only answer a ringing call")
	}
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	if p.Status != model.ParticipantRinging && p.Status != model.ParticipantInvited {
		return errors.New("participant cannot answer in current state")
	}
	now := time.Now()
	p.Status = model.ParticipantConnecting
	p.JoinedAt = &now
	session.Status = model.StatusConnecting
	session.UpdatedAt = now
	return nil
}

func (s *CallSessionService) RejectCall(session *model.CallSession, userID string) error {
	if session.Status != model.StatusRinging && session.Status != model.StatusInitiated {
		return errors.New("can only reject a ringing/initiated call")
	}
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	now := time.Now()
	p.Status = model.ParticipantLeft
	p.LeftAt = &now

	if session.MaxParticipants <= model.MaxParticipants1v1 {
		session.Status = model.StatusEnded
		session.EndReason = model.EndReasonRejected
		session.EndedAt = &now
		if session.StartedAt != nil {
			session.DurationMs = now.Sub(*session.StartedAt).Milliseconds()
		}
	}
	session.UpdatedAt = now
	return nil
}

func (s *CallSessionService) CancelCall(session *model.CallSession, userID string) error {
	if session.Status != model.StatusInitiated && session.Status != model.StatusRinging {
		return errors.New("can only cancel an initiated or ringing call")
	}
	if session.InitiatorID != userID {
		return errors.New("only initiator can cancel")
	}
	now := time.Now()
	session.Status = model.StatusEnded
	session.EndReason = model.EndReasonCancelled
	session.EndedAt = &now
	session.UpdatedAt = now
	return nil
}

func (s *CallSessionService) HangupCall(session *model.CallSession, userID string) error {
	if session.Status != model.StatusInCall && session.Status != model.StatusConnecting {
		return errors.New("can only hangup an active call")
	}
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	now := time.Now()
	p.Status = model.ParticipantLeft
	p.LeftAt = &now

	if countActiveParticipants(session) <= 1 {
		session.Status = model.StatusEnded
		session.EndReason = model.EndReasonNormal
		session.EndedAt = &now
		if session.StartedAt != nil {
			session.DurationMs = now.Sub(*session.StartedAt).Milliseconds()
		}
	}
	session.UpdatedAt = now
	return nil
}

func (s *CallSessionService) JoinCall(session *model.CallSession, userID string) error {
	if session.Status == model.StatusEnded {
		return errors.New("cannot join an ended call")
	}

	now := time.Now()
	p := findParticipant(session, userID)
	if p == nil && countActiveParticipants(session) >= session.MaxParticipants {
		return errors.New("call is full")
	}
	if p != nil {
		p.Status = model.ParticipantConnected
		p.JoinedAt = &now
		p.LeftAt = nil
	} else {
		session.Participants = append(session.Participants, model.Participant{
			UserID:   userID,
			Role:     model.RoleInvitee,
			Status:   model.ParticipantConnected,
			JoinedAt: &now,
		})
	}
	session.ParticipantCount = countActiveParticipants(session)

	if session.Status == model.StatusConnecting || session.Status == model.StatusRinging || session.Status == model.StatusInitiated {
		session.Status = model.StatusInCall
		session.StartedAt = &now
	}
	session.UpdatedAt = now
	return nil
}

func (s *CallSessionService) LeaveCall(session *model.CallSession, userID string) error {
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	now := time.Now()
	p.Status = model.ParticipantLeft
	p.LeftAt = &now
	session.ParticipantCount = countActiveParticipants(session)

	if session.ParticipantCount <= 1 && session.Status != model.StatusEnded {
		session.Status = model.StatusEnded
		session.EndReason = model.EndReasonLastLeave
		session.EndedAt = &now
		if session.StartedAt != nil {
			session.DurationMs = now.Sub(*session.StartedAt).Milliseconds()
		}
	}
	session.UpdatedAt = now
	return nil
}

func (s *CallSessionService) InviteToCall(session *model.CallSession, inviteeIDs []string) error {
	if session.Status == model.StatusEnded {
		return errors.New("cannot invite to an ended call")
	}
	active := countActiveParticipants(session)
	if active+len(inviteeIDs) > session.MaxParticipants {
		return errors.New("exceeds max participants")
	}
	now := time.Now()
	for _, id := range inviteeIDs {
		existing := findParticipant(session, id)
		if existing != nil && existing.Status != model.ParticipantLeft {
			continue
		}
		session.Participants = append(session.Participants, model.Participant{
			UserID: id,
			Role:   model.RoleInvitee,
			Status: model.ParticipantInvited,
		})
	}
	session.ParticipantCount = countActiveParticipants(session)
	session.UpdatedAt = now
	return nil
}

// RingTimeout 返回该会话的振铃超时阈值（1v1 30s / 群 60s），
// 与 storage.yaml lifecycle_timers.ring_timeout 同源。
func (s *CallSessionService) RingTimeout(session *model.CallSession) time.Duration {
	if session.MaxParticipants > model.MaxParticipants1v1 {
		return 60 * time.Second
	}
	return 30 * time.Second
}

// HandleTimeout checks whether the call has reached the ring timeout
// (30s for 1v1, 60s for group). Returns true if the call was timed out.
// 振铃期无人接听的终态是 no_answer（对齐 contract.yaml call_no_answer_timeout
// 与「未接来电」读模型语义）；now 由 application 注入，保证边界可确定测试。
func (s *CallSessionService) HandleTimeout(session *model.CallSession, now time.Time) (bool, error) {
	if session.Status != model.StatusRinging && session.Status != model.StatusInitiated {
		return false, nil
	}
	now = now.UTC()
	if now.Sub(session.CreatedAt.UTC()) < s.RingTimeout(session) {
		return false, nil
	}
	for i := range session.Participants {
		if session.Participants[i].Status == model.ParticipantInvited || session.Participants[i].Status == model.ParticipantRinging {
			session.Participants[i].Status = model.ParticipantTimeout
		}
	}
	session.Status = model.StatusEnded
	session.EndReason = model.EndReasonNoAnswer
	session.EndedAt = &now
	session.UpdatedAt = now
	return true, nil
}

func (s *CallSessionService) ToggleMute(session *model.CallSession, userID string, muted bool) error {
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	if p.Status != model.ParticipantConnected && p.Status != model.ParticipantConnecting {
		return errors.New("participant not connected")
	}
	p.IsMuted = muted
	session.UpdatedAt = time.Now()
	return nil
}

func (s *CallSessionService) ToggleCamera(session *model.CallSession, userID string, cameraOn bool) error {
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	if p.Status != model.ParticipantConnected && p.Status != model.ParticipantConnecting {
		return errors.New("participant not connected")
	}
	p.IsCameraOn = cameraOn
	session.UpdatedAt = time.Now()
	return nil
}

func (s *CallSessionService) StartScreenShare(session *model.CallSession, userID string) error {
	if session.Status != model.StatusInCall {
		return errors.New("can only screen share in active calls")
	}
	if session.IsScreenSharing {
		return errors.New("someone is already sharing screen")
	}
	p := findParticipant(session, userID)
	if p == nil || (p.Status != model.ParticipantConnected && p.Status != model.ParticipantConnecting) {
		return errors.New("participant not connected")
	}
	session.IsScreenSharing = true
	session.ScreenShareUserID = userID
	session.UpdatedAt = time.Now()
	return nil
}

func (s *CallSessionService) StopScreenShare(session *model.CallSession, userID string) error {
	if !session.IsScreenSharing {
		return errors.New("not sharing screen")
	}
	if session.ScreenShareUserID != userID {
		return errors.New("only the sharer can stop sharing")
	}
	session.IsScreenSharing = false
	session.ScreenShareUserID = ""
	session.UpdatedAt = time.Now()
	return nil
}

// SetConnected 记录参与者媒体建连事实（ReportMediaConnected 命令的领域行为）：
// 仅 connecting 参与者可首次进入 connected；≥2 人 connected 时会话进入
// in_call 并只写一次 startedAt。now 由 application 注入。
func (s *CallSessionService) SetConnected(session *model.CallSession, userID string, now time.Time) error {
	if session.Status == model.StatusEnded {
		return errors.New("cannot report connected on an ended call")
	}
	p := findParticipant(session, userID)
	if p == nil {
		return errors.New("user not in call")
	}
	if p.Status == model.ParticipantConnected {
		return nil
	}
	if p.Status != model.ParticipantConnecting {
		return errors.New("participant cannot report connected in current state")
	}
	now = now.UTC()
	p.Status = model.ParticipantConnected
	p.JoinedAt = &now
	connectedCount := 0
	for _, pp := range session.Participants {
		if pp.Status == model.ParticipantConnected {
			connectedCount++
		}
	}
	if connectedCount >= 2 && session.Status != model.StatusInCall {
		session.Status = model.StatusInCall
		if session.StartedAt == nil {
			session.StartedAt = &now
		}
	}
	session.UpdatedAt = now
	return nil
}

func findParticipant(session *model.CallSession, userID string) *model.Participant {
	for i := range session.Participants {
		if session.Participants[i].UserID == userID {
			return &session.Participants[i]
		}
	}
	return nil
}

func countActiveParticipants(session *model.CallSession) int {
	count := 0
	for _, p := range session.Participants {
		if p.Status != model.ParticipantLeft && p.Status != model.ParticipantTimeout {
			count++
		}
	}
	return count
}
