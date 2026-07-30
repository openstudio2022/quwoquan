package persona_relationship

import relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"

// RelationshipCapabilityView is the one public JSON shape for the capability
// domain value. Keep it aligned with RelationshipCapabilityWire metadata.
type RelationshipCapabilityView struct {
	ViewerPersonaID             string `json:"viewerPersonaId"`
	TargetPersonaID             string `json:"targetPersonaId"`
	RelationState               string `json:"relationState"`
	CanFollow                   bool   `json:"canFollow"`
	CanUnfollow                 bool   `json:"canUnfollow"`
	CanFollowBack               bool   `json:"canFollowBack"`
	CanGreet                    bool   `json:"canGreet"`
	CanOpenConversation         bool   `json:"canOpenConversation"`
	CanCreateDirectConversation bool   `json:"canCreateDirectConversation"`
	CanSendMessage              bool   `json:"canSendMessage"`
	HasPendingGreeting          bool   `json:"hasPendingGreeting"`
	HasFormalConversation       bool   `json:"hasFormalConversation"`
	CanStartVoiceCall           bool   `json:"canStartVoiceCall"`
	CanStartVideoCall           bool   `json:"canStartVideoCall"`
	IsBlocked                   bool   `json:"isBlocked"`
	IsBlockedBy                 bool   `json:"isBlockedBy"`
}

func NewRelationshipCapabilityView(
	facts relmodel.RelationshipCapabilityFacts,
) RelationshipCapabilityView {
	capability := relmodel.DeriveRelationshipCapability(facts)
	return RelationshipCapabilityView{
		ViewerPersonaID:             capability.ViewerPersonaID,
		TargetPersonaID:             capability.TargetPersonaID,
		RelationState:               capability.RelationState,
		CanFollow:                   capability.CanFollow,
		CanUnfollow:                 capability.CanUnfollow,
		CanFollowBack:               capability.CanFollowBack,
		CanGreet:                    capability.CanGreet,
		CanOpenConversation:         capability.CanOpenConversation,
		CanCreateDirectConversation: capability.CanCreateDirectConversation,
		CanSendMessage:              capability.CanSendMessage,
		HasPendingGreeting:          capability.HasPendingGreeting,
		HasFormalConversation:       capability.HasFormalConversation,
		CanStartVoiceCall:           capability.CanStartVoiceCall,
		CanStartVideoCall:           capability.CanStartVideoCall,
		IsBlocked:                   capability.IsBlocked,
		IsBlockedBy:                 capability.IsBlockedBy,
	}
}
