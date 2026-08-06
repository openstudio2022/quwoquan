package model_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	gatheringclient "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/client"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

var scopeBNow = time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestR6ClosedParticipationRetriesSameRowWithMonotonicAttemptAndVersion(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	joined, err := model.JoinOpen(current, scopeBParticipationInput(current, "persona-2", 0, scopeBNow))
	if err != nil {
		t.Fatalf("JoinOpen: %v", err)
	}
	participation := scopeBParticipation(t, joined, "persona-2")
	if participation.AttemptNo != 1 || participation.Version != 1 ||
		participation.State != model.ParticipationStateActive ||
		participation.JoinedAt.IsZero() {
		t.Fatalf("first attempt = %+v", participation)
	}

	left, err := model.LeaveParticipation(
		joined,
		scopeBParticipationInput(joined, "persona-2", participation.Version, scopeBNow.Add(time.Minute)),
	)
	if err != nil {
		t.Fatalf("LeaveParticipation: %v", err)
	}
	closed := scopeBParticipation(t, left, "persona-2")
	rejoined, err := model.JoinOpen(
		left,
		scopeBParticipationInput(left, "persona-2", closed.Version, scopeBNow.Add(2*time.Minute)),
	)
	if err != nil {
		t.Fatalf("JoinOpen retry: %v", err)
	}
	retry := scopeBParticipation(t, rejoined, "persona-2")
	if len(rejoined.Participations) != 1 || retry.AttemptNo != 2 ||
		retry.Version != closed.Version+1 || retry.State != model.ParticipationStateActive {
		t.Fatalf("retry created a second identity or reset CAS: %+v", rejoined.Participations)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
func TestR7SafetyRemovedParticipationCannotRetryOrReinstate(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	joined, err := model.JoinOpen(current, scopeBParticipationInput(current, "persona-2", 0, scopeBNow))
	if err != nil {
		t.Fatalf("JoinOpen: %v", err)
	}
	active := scopeBParticipation(t, joined, "persona-2")
	removed, err := model.SafetyRemoveParticipation(joined, model.CloseParticipationInput{
		ParticipationCommandInput: model.ParticipationCommandInput{
			ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
			ExpectedGatheringVersion:     joined.Version,
			ExpectedParticipationVersion: active.Version,
			OccurredAt:                   scopeBNow.Add(time.Minute),
		},
		ReasonRef: "safety-case-1",
	})
	if err != nil {
		t.Fatalf("SafetyRemoveParticipation: %v", err)
	}
	safetyClosed := scopeBParticipation(t, removed, "persona-2")
	if safetyClosed.ClosedReason != model.ClosedReasonSafetyRemoved {
		t.Fatalf("closed reason = %q", safetyClosed.ClosedReason)
	}
	if _, err := model.JoinOpen(
		removed,
		scopeBParticipationInput(
			removed,
			"persona-2",
			safetyClosed.Version,
			scopeBNow.Add(2*time.Minute),
		),
	); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("safety retry error = %v", err)
	}
	reinstateInput := scopeBParticipationInput(
		removed,
		"persona-2",
		safetyClosed.Version,
		scopeBNow.Add(2*time.Minute),
	)
	reinstateInput.ActorPersonaID = "persona-owner"
	if _, err := model.ReinstateParticipation(removed, model.CloseParticipationInput{
		ParticipationCommandInput: reinstateInput,
	}); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("safety reinstate error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestR9ApplicationQuestionsAndDigestFollowTypedContract(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyApproval, 3)
	current.PolicySet.ApplicationQuestions = []contract.GatheringApplicationQuestion{
		{
			QuestionID: "experience", Prompt: "经验", Required: true,
			Kind:    contract.GatheringApplicationQuestionKindText,
			Options: []contract.GatheringApplicationQuestionOption{},
		},
		{
			QuestionID: "gear", Prompt: "装备", Required: true,
			Kind: contract.GatheringApplicationQuestionKindMultiSelect,
			Options: []contract.GatheringApplicationQuestionOption{
				{OptionID: "tent", Label: "帐篷"},
				{OptionID: "lamp", Label: "头灯"},
			},
		},
	}
	left := []model.GatheringApplicationAnswer{
		{QuestionID: "gear", SelectedOptionIds: []string{"tent", "lamp"}},
		{QuestionID: "experience", AnswerText: "  两次高海拔徒步  "},
	}
	right := []model.GatheringApplicationAnswer{
		{QuestionID: "experience", AnswerText: "两次高海拔徒步"},
		{QuestionID: "gear", SelectedOptionIds: []string{"lamp", "tent"}},
	}
	leftDigest, err := model.ApplicationAnswersDigest(current.PolicySet.ApplicationQuestions, left)
	if err != nil {
		t.Fatalf("left digest: %v", err)
	}
	rightDigest, err := model.ApplicationAnswersDigest(current.PolicySet.ApplicationQuestions, right)
	if err != nil || leftDigest != rightDigest || !strings.HasPrefix(leftDigest, "sha256:") {
		t.Fatalf("canonical digests left=%q right=%q err=%v", leftDigest, rightDigest, err)
	}
	applied, err := model.Apply(current, model.ApplyParticipationInput{
		ParticipationCommandInput: scopeBParticipationInput(current, "persona-2", 0, scopeBNow),
		Answers:                   left,
	})
	if err != nil {
		t.Fatalf("Apply: %v", err)
	}
	pending := scopeBParticipation(t, applied, "persona-2")
	if pending.State != model.ParticipationStateApplicationPending ||
		len(pending.ApplicationAnswers) != 2 ||
		model.CapacityAt(applied, scopeBNow).OccupiedSeats != 0 {
		t.Fatalf("application pending drift: %+v", pending)
	}

	tooLong := strings.Repeat("界", 161) // 483 UTF-8 bytes.
	if _, err := model.ApplicationAnswersDigest(
		current.PolicySet.ApplicationQuestions,
		[]model.GatheringApplicationAnswer{
			{QuestionID: "experience", AnswerText: tooLong},
			{QuestionID: "gear", SelectedOptionIds: []string{"tent"}},
		},
	); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("oversized answer error = %v", err)
	}
	tooManyQuestions := make([]contract.GatheringApplicationQuestion, 6)
	for index := range tooManyQuestions {
		tooManyQuestions[index] = contract.GatheringApplicationQuestion{
			QuestionID: string(rune('a' + index)),
			Prompt:     "问题",
			Kind:       contract.GatheringApplicationQuestionKindText,
			Options:    []contract.GatheringApplicationQuestionOption{},
		}
	}
	if _, err := model.ApplicationAnswersDigest(
		tooManyQuestions,
		[]model.GatheringApplicationAnswer{},
	); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("question count error = %v", err)
	}
	tooManyOptions := make([]contract.GatheringApplicationQuestionOption, 11)
	for index := range tooManyOptions {
		tooManyOptions[index] = contract.GatheringApplicationQuestionOption{
			OptionID: string(rune('a' + index)),
			Label:    "选项",
		}
	}
	if _, err := model.ApplicationAnswersDigest(
		[]contract.GatheringApplicationQuestion{{
			QuestionID: "gear",
			Prompt:     "装备",
			Kind:       contract.GatheringApplicationQuestionKindMultiSelect,
			Options:    tooManyOptions,
		}},
		[]model.GatheringApplicationAnswer{},
	); !errors.Is(err, gatheringerrors.ErrGatheringTransitionForbidden) {
		t.Fatalf("option count error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestParticipationRejectsStaleRootChildVersionsAndDuplicateIdentity(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 3)
	impersonated := scopeBParticipationInput(current, "persona-2", 0, scopeBNow)
	impersonated.ActorPersonaID = "persona-intruder"
	if _, err := model.JoinOpen(current, impersonated); !errors.Is(
		err,
		gatheringerrors.ErrGatheringPermissionDenied,
	) {
		t.Fatalf("impersonated self operation error = %v", err)
	}
	if _, err := model.JoinOpen(
		current,
		scopeBParticipationInput(current, "persona-2", 1, scopeBNow),
	); !errors.Is(err, gatheringerrors.ErrGatheringParticipationConflict) {
		t.Fatalf("missing row with nonzero child version error = %v", err)
	}
	stale := scopeBParticipationInput(current, "persona-2", 0, scopeBNow)
	stale.ExpectedGatheringVersion--
	if _, err := model.JoinOpen(current, stale); !errors.Is(err, gatheringerrors.ErrGatheringVersionConflict) {
		t.Fatalf("stale root version error = %v", err)
	}

	current.Participations = []model.GatheringParticipation{
		{GatheringID: current.ID, PersonaID: "persona-2", State: model.ParticipationStateClosed, Version: 1, AttemptNo: 1},
		{GatheringID: current.ID, PersonaID: "persona-2", State: model.ParticipationStateClosed, Version: 1, AttemptNo: 1},
	}
	if _, err := model.JoinOpen(
		current,
		scopeBParticipationInput(current, "persona-2", 1, scopeBNow),
	); !errors.Is(err, gatheringerrors.ErrGatheringParticipationConflict) {
		t.Fatalf("duplicate identity error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestApplicationInvitationAndRemovalTransitionsKeepCanonicalReasons(t *testing.T) {
	t.Run("application approve and withdraw", func(t *testing.T) {
		current := scopeBGathering(contract.GatheringAdmissionPolicyApproval, 2)
		applied, err := model.Apply(current, model.ApplyParticipationInput{
			ParticipationCommandInput: scopeBParticipationInput(current, "persona-2", 0, scopeBNow),
			Answers:                   []model.GatheringApplicationAnswer{},
		})
		if err != nil {
			t.Fatalf("Apply: %v", err)
		}
		pending := scopeBParticipation(t, applied, "persona-2")
		approved, err := model.ReviewApplication(applied, model.ReviewParticipationInput{
			ParticipationCommandInput: model.ParticipationCommandInput{
				ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
				ExpectedGatheringVersion:     applied.Version,
				ExpectedParticipationVersion: pending.Version,
				OccurredAt:                   scopeBNow.Add(time.Minute),
			},
			Decision: gatheringclient.GatheringApplicationReviewDecisionApprove,
		})
		if err != nil {
			t.Fatalf("ReviewApplication approve: %v", err)
		}
		if active := scopeBParticipation(t, approved, "persona-2"); active.State != model.ParticipationStateActive {
			t.Fatalf("approved participation = %+v", active)
		}

		other := scopeBGathering(contract.GatheringAdmissionPolicyApproval, 2)
		applied, err = model.Apply(other, model.ApplyParticipationInput{
			ParticipationCommandInput: scopeBParticipationInput(other, "persona-3", 0, scopeBNow),
			Answers:                   []model.GatheringApplicationAnswer{},
		})
		if err != nil {
			t.Fatalf("Apply for withdraw: %v", err)
		}
		pending = scopeBParticipation(t, applied, "persona-3")
		withdrawn, err := model.WithdrawApplication(
			applied,
			scopeBParticipationInput(applied, "persona-3", pending.Version, scopeBNow.Add(time.Minute)),
		)
		if err != nil {
			t.Fatalf("WithdrawApplication: %v", err)
		}
		if closed := scopeBParticipation(t, withdrawn, "persona-3"); closed.ClosedReason != model.ClosedReasonWithdrawn {
			t.Fatalf("withdrawn participation = %+v", closed)
		}
	})

	t.Run("invitation accept decline and revoke", func(t *testing.T) {
		for name, transition := range map[string]func(
			model.Gathering,
			model.GatheringParticipation,
		) (model.Gathering, error){
			"accept": func(value model.Gathering, pending model.GatheringParticipation) (model.Gathering, error) {
				return model.AcceptInvitation(
					value,
					scopeBParticipationInput(value, "persona-2", pending.Version, scopeBNow.Add(time.Minute)),
				)
			},
			"decline": func(value model.Gathering, pending model.GatheringParticipation) (model.Gathering, error) {
				return model.DeclineInvitation(
					value,
					scopeBParticipationInput(value, "persona-2", pending.Version, scopeBNow.Add(time.Minute)),
				)
			},
			"revoke": func(value model.Gathering, pending model.GatheringParticipation) (model.Gathering, error) {
				return model.RevokeInvitation(value, model.CloseParticipationInput{
					ParticipationCommandInput: model.ParticipationCommandInput{
						ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
						ExpectedGatheringVersion:     value.Version,
						ExpectedParticipationVersion: pending.Version,
						OccurredAt:                   scopeBNow.Add(time.Minute),
					},
					ReasonRef: "invite-changed",
				})
			},
		} {
			name, transition := name, transition
			t.Run(name, func(t *testing.T) {
				current := scopeBGathering(contract.GatheringAdmissionPolicyInviteOnly, 1)
				invited, err := model.Invite(current, model.InviteParticipationInput{
					ParticipationCommandInput: model.ParticipationCommandInput{
						ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
						ExpectedGatheringVersion:     current.Version,
						ExpectedParticipationVersion: 0,
						OccurredAt:                   scopeBNow,
					},
					SeatHoldUntil: scopeBNow.Add(time.Hour),
				})
				if err != nil {
					t.Fatalf("Invite: %v", err)
				}
				pending := scopeBParticipation(t, invited, "persona-2")
				if pending.InvitedByPersonaID != "persona-owner" {
					t.Fatalf("invitation owner = %q", pending.InvitedByPersonaID)
				}
				next, err := transition(invited, pending)
				if err != nil {
					t.Fatalf("%s: %v", name, err)
				}
				result := scopeBParticipation(t, next, "persona-2")
				switch name {
				case "accept":
					if result.State != model.ParticipationStateActive ||
						model.CapacityAt(next, scopeBNow.Add(time.Minute)).OccupiedSeats != 1 {
						t.Fatalf("accepted participation = %+v", result)
					}
				case "decline":
					if result.ClosedReason != model.ClosedReasonDeclined {
						t.Fatalf("declined participation = %+v", result)
					}
				case "revoke":
					if result.ClosedReason != model.ClosedReasonRevoked {
						t.Fatalf("revoked participation = %+v", result)
					}
				}
			})
		}
	})

	t.Run("remove and explicit reinstate", func(t *testing.T) {
		current := scopeBGathering(contract.GatheringAdmissionPolicyOpen, 2)
		joined, err := model.JoinOpen(current, scopeBParticipationInput(current, "persona-2", 0, scopeBNow))
		if err != nil {
			t.Fatalf("JoinOpen: %v", err)
		}
		active := scopeBParticipation(t, joined, "persona-2")
		removed, err := model.RemoveParticipation(joined, model.CloseParticipationInput{
			ParticipationCommandInput: model.ParticipationCommandInput{
				ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
				ExpectedGatheringVersion:     joined.Version,
				ExpectedParticipationVersion: active.Version,
				OccurredAt:                   scopeBNow.Add(time.Minute),
			},
			ReasonRef: "host-policy-1",
		})
		if err != nil {
			t.Fatalf("RemoveParticipation: %v", err)
		}
		closed := scopeBParticipation(t, removed, "persona-2")
		if closed.ClosedReason != model.ClosedReasonRemoved {
			t.Fatalf("removed participation = %+v", closed)
		}
		reinstated, err := model.ReinstateParticipation(removed, model.CloseParticipationInput{
			ParticipationCommandInput: model.ParticipationCommandInput{
				ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
				ExpectedGatheringVersion:     removed.Version,
				ExpectedParticipationVersion: closed.Version,
				OccurredAt:                   scopeBNow.Add(2 * time.Minute),
			},
			ReasonRef: "appeal-approved",
		})
		if err != nil {
			t.Fatalf("ReinstateParticipation: %v", err)
		}
		active = scopeBParticipation(t, reinstated, "persona-2")
		if active.State != model.ParticipationStateActive ||
			active.AttemptNo != closed.AttemptNo+1 ||
			active.Version != closed.Version+1 {
			t.Fatalf("reinstated participation = %+v", active)
		}
	})
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-006
func TestInvitationActionRejectsWrongRecipientAndCancelledGathering(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyInviteOnly, 1)
	invited, err := model.Invite(current, model.InviteParticipationInput{
		ParticipationCommandInput: model.ParticipationCommandInput{
			ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
			ExpectedGatheringVersion:     current.Version,
			ExpectedParticipationVersion: 0,
			OccurredAt:                   scopeBNow,
		},
		SeatHoldUntil: scopeBNow.Add(time.Hour),
	})
	if err != nil {
		t.Fatalf("Invite: %v", err)
	}
	if _, err := model.AcceptInvitation(
		invited,
		scopeBParticipationInput(invited, "persona-other", 0, scopeBNow.Add(time.Minute)),
	); !errors.Is(err, gatheringerrors.ErrGatheringInvitationRecipientMismatch) {
		t.Fatalf("wrong recipient error = %v", err)
	}
	pending := scopeBParticipation(t, invited, "persona-2")
	cancelled := invited
	cancelled.Version++
	cancelled.LifecycleStatus = contract.GatheringLifecycleStatusCancelled
	if _, err := model.AcceptInvitation(
		cancelled,
		scopeBParticipationInput(
			cancelled,
			"persona-2",
			pending.Version,
			scopeBNow.Add(time.Minute),
		),
	); !errors.Is(err, gatheringerrors.ErrGatheringInvitationInactive) {
		t.Fatalf("cancelled invitation error = %v", err)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestInvitationExpirationBoundaryRejectsAcceptAndDecline(t *testing.T) {
	current := scopeBGathering(contract.GatheringAdmissionPolicyInviteOnly, 1)
	invited, err := model.Invite(current, model.InviteParticipationInput{
		ParticipationCommandInput: model.ParticipationCommandInput{
			ActorPersonaID: "persona-owner", ParticipantPersonaID: "persona-2",
			ExpectedGatheringVersion:     current.Version,
			ExpectedParticipationVersion: 0,
			OccurredAt:                   scopeBNow,
		},
		SeatHoldUntil: scopeBNow.Add(time.Minute),
	})
	if err != nil {
		t.Fatalf("Invite: %v", err)
	}
	pending := scopeBParticipation(t, invited, "persona-2")
	atExpiry := scopeBParticipationInput(
		invited,
		"persona-2",
		pending.Version,
		pending.SeatHoldUntil,
	)
	if _, err := model.AcceptInvitation(invited, atExpiry); !errors.Is(
		err,
		gatheringerrors.ErrGatheringSeatHoldExpired,
	) {
		t.Fatalf("accept at expiry error = %v", err)
	}
	if _, err := model.DeclineInvitation(invited, atExpiry); !errors.Is(
		err,
		gatheringerrors.ErrGatheringInvitationExpired,
	) {
		t.Fatalf("decline at expiry error = %v", err)
	}
	if capacity := model.CapacityAt(invited, pending.SeatHoldUntil); capacity.OccupiedSeats != 0 {
		t.Fatalf("expired invitation still occupied capacity: %+v", capacity)
	}
}

func scopeBGathering(
	admissionPolicy contract.GatheringAdmissionPolicy,
	maxParticipants int64,
) model.Gathering {
	return model.Gathering{
		ID:                 "gathering-scope-b",
		Version:            7,
		CreatedByPersonaID: "persona-owner",
		HostBinding: contract.HostBinding{
			HostSubjectKind:      contract.GatheringHostSubjectKindPersona,
			HostSubjectID:        "persona-owner",
			AuthorityEvidenceRef: "authority-1",
			AuthorityVersion:     1,
		},
		OrganizerAssignments: []contract.OrganizerAssignment{
			{
				PersonaID:            "persona-owner",
				Role:                 contract.GatheringOrganizerRolePrimaryOrganizer,
				AuthorityEvidenceRef: "authority-1",
				AuthorityVersion:     1,
				AssignedAt:           scopeBNow.Add(-time.Hour),
				Version:              1,
			},
		},
		Purpose: contract.GatheringPurpose{
			Title:            "贡嘎日落同行",
			Summary:          "一起完成安全、公开的徒步活动。",
			TopicRefs:        []string{},
			RequirementRefs:  []string{},
			SourceObjectRefs: []contract.GatheringSourceRef{},
			CostNotice:       contract.GatheringCostNoticeFree,
		},
		Schedule: contract.GatheringSchedule{
			Timezone:          "Asia/Shanghai",
			StartAt:           scopeBNow.Add(2 * time.Hour),
			EndAt:             scopeBNow.Add(4 * time.Hour),
			AdmissionClosesAt: scopeBNow.Add(time.Hour),
		},
		Place: contract.GatheringPlace{
			Mode:              contract.GatheringPlaceModeOnline,
			OnlineLocationRef: "room://gathering-scope-b",
		},
		PolicySet: contract.GatheringPolicySet{
			AudiencePolicy:  contract.GatheringAudiencePolicyPublic,
			AdmissionPolicy: admissionPolicy,
			CapacityPolicy:  contract.GatheringCapacityPolicy{MaxParticipants: maxParticipants},
			DisclosurePolicy: contract.GatheringDisclosurePolicy{
				TimeDisclosure:   contract.GatheringTimeDisclosureExact,
				PlaceDisclosure:  contract.GatheringPlaceDisclosureExact,
				RosterDisclosure: contract.GatheringRosterDisclosureCountOnly,
			},
			ApplicationQuestions: []contract.GatheringApplicationQuestion{},
			RiskControlPolicyRef: "risk-policy-1",
			PolicyDecisionRef:    "policy-decision-1",
			PolicyDigest:         "sha256:9b8c6a7ea7c98367bf0245ab77cc7285738c28fe15856ae9c37f132223460052",
			ObligationDigest:     "obligation-digest-1",
		},
		AdmissionControl: contract.GatheringAdmissionControl{
			Status:  contract.GatheringAdmissionControlStatusOpen,
			Version: 1,
		},
		LifecycleStatus:     contract.GatheringLifecycleStatusPublished,
		RoomBindingStatus:   contract.GatheringRoomBindingStatusReady,
		Participations:      []model.GatheringParticipation{},
		Revisions:           []contract.GatheringRevision{},
		AvailabilityWatches: []contract.GatheringAvailabilityWatch{},
		CreatedAt:           scopeBNow.Add(-time.Hour),
		UpdatedAt:           scopeBNow.Add(-time.Hour),
	}
}

func scopeBParticipationInput(
	current model.Gathering,
	personaID string,
	expectedParticipationVersion int64,
	occurredAt time.Time,
) model.ParticipationCommandInput {
	return model.ParticipationCommandInput{
		ActorPersonaID:               personaID,
		ParticipantPersonaID:         personaID,
		ExpectedGatheringVersion:     current.Version,
		ExpectedParticipationVersion: expectedParticipationVersion,
		OccurredAt:                   occurredAt,
	}
}

func scopeBParticipation(
	t *testing.T,
	current model.Gathering,
	personaID string,
) model.GatheringParticipation {
	t.Helper()
	participation, found := model.FindParticipation(current, personaID)
	if !found {
		t.Fatalf("Participation %q not found in %+v", personaID, current.Participations)
	}
	return participation
}
