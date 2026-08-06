package gathering

import (
	"strings"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
)

// MarkGatheringRoomReady 是独立于 Create/Publish 的幂等 owner transition。
func MarkGatheringRoomReady(
	current Gathering,
	conversationID string,
	occurredAt time.Time,
) (Gathering, error) {
	conversationID = strings.TrimSpace(conversationID)
	if conversationID == "" || occurredAt.IsZero() {
		return Gathering{}, ErrInvalidLifecycleArgument
	}
	if current.LifecycleStatus == contract.GatheringLifecycleStatusCancelled ||
		current.LifecycleStatus == contract.GatheringLifecycleStatusCompleted {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if current.RoomBindingStatus == contract.GatheringRoomBindingStatusReady {
		if strings.TrimSpace(current.ConversationID) == conversationID {
			return current, nil
		}
		return Gathering{}, gatheringerrors.ErrGatheringRoomProvisionFailed
	}
	if strings.TrimSpace(current.ConversationID) != "" &&
		strings.TrimSpace(current.ConversationID) != conversationID {
		return Gathering{}, gatheringerrors.ErrGatheringRoomProvisionFailed
	}
	next := current
	next.ConversationID = conversationID
	next.RoomBindingStatus = contract.GatheringRoomBindingStatusReady
	touchLifecycle(&next, occurredAt)
	return next, nil
}

// MarkGatheringRoomFailed 永不把 ready binding 降级；failed 可由 reconciler 持续重试。
func MarkGatheringRoomFailed(
	current Gathering,
	occurredAt time.Time,
) (Gathering, error) {
	if occurredAt.IsZero() {
		return Gathering{}, ErrInvalidLifecycleArgument
	}
	if current.LifecycleStatus == contract.GatheringLifecycleStatusCancelled ||
		current.LifecycleStatus == contract.GatheringLifecycleStatusCompleted {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	if current.RoomBindingStatus == contract.GatheringRoomBindingStatusReady ||
		current.RoomBindingStatus == contract.GatheringRoomBindingStatusFailed {
		return current, nil
	}
	if current.RoomBindingStatus != contract.GatheringRoomBindingStatusPending {
		return Gathering{}, gatheringerrors.ErrGatheringTransitionForbidden
	}
	next := current
	next.RoomBindingStatus = contract.GatheringRoomBindingStatusFailed
	touchLifecycle(&next, occurredAt)
	return next, nil
}
