package model

import "strings"

// RelationshipCapabilityFacts are the authoritative inputs needed to derive
// the viewer-scoped relationship action matrix. Transport handlers may collect
// the facts, but must not reimplement the policy.
type RelationshipCapabilityFacts struct {
	ViewerPersonaID       string
	TargetPersonaID       string
	Relationship          RelationshipState
	IsBlocked             bool
	IsBlockedBy           bool
	HasPendingGreeting    bool
	HasFormalConversation bool
}

// RelationshipCapability is the pure domain value behind every public
// capability projection. It deliberately has no JSON or storage annotations.
type RelationshipCapability struct {
	ViewerPersonaID             string
	TargetPersonaID             string
	RelationState               string
	CanFollow                   bool
	CanUnfollow                 bool
	CanFollowBack               bool
	CanGreet                    bool
	CanOpenConversation         bool
	CanCreateDirectConversation bool
	CanSendMessage              bool
	HasPendingGreeting          bool
	HasFormalConversation       bool
	CanStartVoiceCall           bool
	CanStartVideoCall           bool
	IsBlocked                   bool
	IsBlockedBy                 bool
}

func DeriveRelationshipCapability(facts RelationshipCapabilityFacts) RelationshipCapability {
	viewerPersonaID := strings.TrimSpace(facts.ViewerPersonaID)
	targetPersonaID := strings.TrimSpace(facts.TargetPersonaID)
	relationState := facts.Relationship.RelationState(viewerPersonaID, targetPersonaID)
	capability := RelationshipCapability{
		ViewerPersonaID:       viewerPersonaID,
		TargetPersonaID:       targetPersonaID,
		RelationState:         relationState,
		CanFollow:             true,
		CanGreet:              true,
		HasPendingGreeting:    facts.HasPendingGreeting,
		HasFormalConversation: facts.HasFormalConversation,
		IsBlocked:             facts.IsBlocked,
		IsBlockedBy:           facts.IsBlockedBy,
	}

	switch relationState {
	case "self":
		capability.CanFollow = false
		capability.CanGreet = false
	case "mutual":
		capability.CanFollow = false
		capability.CanUnfollow = true
		capability.CanGreet = false
		capability.CanCreateDirectConversation = true
		capability.CanSendMessage = true
		capability.CanStartVoiceCall = true
		capability.CanStartVideoCall = true
	case "following":
		capability.CanFollow = false
		capability.CanUnfollow = true
	case "followed_by":
		capability.CanFollowBack = true
	}

	if facts.HasFormalConversation {
		capability.CanSendMessage = true
		capability.CanGreet = false
	}
	if facts.HasPendingGreeting {
		capability.CanGreet = false
	}
	capability.CanOpenConversation =
		capability.CanCreateDirectConversation || facts.HasFormalConversation

	if relationState == "self" || facts.IsBlocked || facts.IsBlockedBy {
		capability.CanFollow = false
		capability.CanUnfollow = false
		capability.CanFollowBack = false
		capability.CanGreet = false
		capability.CanOpenConversation = false
		capability.CanCreateDirectConversation = false
		capability.CanSendMessage = false
		capability.CanStartVoiceCall = false
		capability.CanStartVideoCall = false
	}
	return capability
}
