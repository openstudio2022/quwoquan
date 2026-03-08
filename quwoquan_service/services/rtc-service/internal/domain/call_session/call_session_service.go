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
	if session.Status != model.StatusRinging && session.Status != model.StatusInitiated {
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
	if countActiveParticipants(session) >= session.MaxParticipants {
		return errors.New("call is full")
	}

	now := time.Now()
	p := findParticipant(session, userID)
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

// HandleTimeout checks whether the call has exceeded the ring timeout
// (30s for 1v1, 60s for group). Returns true if the call was timed out.
func (s *CallSessionService) HandleTimeout(session *model.CallSession) (bool, error) {
	if session.Status != model.StatusRinging && session.Status != model.StatusInitiated {
		return false, nil
	}
	timeoutDuration := 30 * time.Second
	if session.MaxParticipants > model.MaxParticipants1v1 {
		timeoutDuration = 60 * time.Second
	}
	if time.Since(session.CreatedAt) < timeoutDuration {
		return false, nil
	}
	now := time.Now()
	for i := range session.Participants {
		if session.Participants[i].Status == model.ParticipantInvited || session.Participants[i].Status == model.ParticipantRinging {
			session.Participants[i].Status = model.ParticipantTimeout
		}
	}
	session.Status = model.StatusEnded
	session.EndReason = model.EndReasonTimeout
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

func (s *CallSessionService) StartRecording(session *model.CallSession, userID string) error {
	if session.Status != model.StatusInCall {
		return errors.New("can only record active calls")
	}
	if session.InitiatorID != userID {
		return errors.New("only initiator can start recording")
	}
	if session.IsRecording {
		return errors.New("already recording")
	}
	session.IsRecording = true
	session.UpdatedAt = time.Now()
	return nil
}

func (s *CallSessionService) StopRecording(session *model.CallSession, userID string) error {
	if !session.IsRecording {
		return errors.New("not recording")
	}
	if session.InitiatorID != userID {
		return errors.New("only initiator can stop recording")
	}
	session.IsRecording = false
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

func (s *CallSessionService) SetConnected(session *model.CallSession, userID string) {
	p := findParticipant(session, userID)
	if p != nil && (p.Status == model.ParticipantConnecting || p.Status == model.ParticipantRinging) {
		now := time.Now()
		p.Status = model.ParticipantConnected
		p.JoinedAt = &now
	}
	connectedCount := 0
	for _, pp := range session.Participants {
		if pp.Status == model.ParticipantConnected {
			connectedCount++
		}
	}
	if connectedCount >= 2 && session.Status == model.StatusConnecting {
		now := time.Now()
		session.Status = model.StatusInCall
		session.StartedAt = &now
	}
	session.UpdatedAt = time.Now()
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
