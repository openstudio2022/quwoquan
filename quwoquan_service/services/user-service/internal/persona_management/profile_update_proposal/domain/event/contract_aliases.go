package event

import generated "quwoquan_service/services/user-service/generated/persona_management/profile_update_proposal/contract/persona/profile_update_proposal/event"

const (
	ProfileUpdateProposalCreated         = generated.ProfileUpdateProposalCreated
	ProfileUpdateProposalConfirmed       = generated.ProfileUpdateProposalConfirmed
	ProfileUpdateProposalApplyStarted    = generated.ProfileUpdateProposalApplyStarted
	ProfileUpdateProposalApplied         = generated.ProfileUpdateProposalApplied
	ProfileUpdateProposalRollbackStarted = generated.ProfileUpdateProposalRollbackStarted
	ProfileUpdateProposalRollbackAborted = generated.ProfileUpdateProposalRollbackAborted
	ProfileUpdateProposalRolledBack      = generated.ProfileUpdateProposalRolledBack
	ProfileUpdateProposalRejected        = generated.ProfileUpdateProposalRejected
	ProfileUpdateProposalExpired         = generated.ProfileUpdateProposalExpired
)
