package moderation

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	moderationmodel "quwoquan_service/services/content-service/internal/domain/moderation/model"
	moderationports "quwoquan_service/services/content-service/internal/domain/moderation/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const moderationReceiptTTL = 24 * time.Hour

type ModerationService struct {
	data  DataPorts
	now   func() time.Time
	newID func(string) (string, error)
}

type ModerationServiceOption func(*ModerationService)

func WithClock(now func() time.Time) ModerationServiceOption {
	return func(service *ModerationService) {
		if now != nil {
			service.now = now
		}
	}
}

func WithIdentifierGenerator(
	newID func(prefix string) (string, error),
) ModerationServiceOption {
	return func(service *ModerationService) {
		if newID != nil {
			service.newID = newID
		}
	}
}

func NewModerationService(
	data DataPorts,
	options ...ModerationServiceOption,
) *ModerationService {
	if data.Aggregate == nil || data.Eligibility == nil {
		panic("ModerationService requires aggregate and eligibility data ports")
	}
	service := &ModerationService{
		data:  data,
		now:   time.Now,
		newID: newModerationIdentifier,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

func (s *ModerationService) OpenPostModerationCase(
	ctx context.Context,
	command OpenPostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	commandDigest := moderationCommandDigest("OpenPostModerationCase", encoded)
	if replayed, found, err := s.replay(
		ctx,
		"OpenPostModerationCase",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	now := s.now().UTC()
	caseID, err := s.newID("pmc")
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	caseItem, err := moderationmodel.Open(moderationmodel.OpenParams{
		ID:            caseID,
		PostID:        command.PostID,
		PostVersion:   command.PostVersion,
		ContentDigest: command.ContentDigest,
		Now:           now,
	})
	if err != nil {
		return PostModerationCaseCommandResult{}, mapModerationDomainError(err)
	}
	payload, err := json.Marshal(postModerationOpenedPayload{
		CaseID:        caseItem.ID(),
		PostID:        caseItem.PostID(),
		PostVersion:   caseItem.PostVersion(),
		ContentDigest: caseItem.ContentDigest(),
	})
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	return s.commit(
		ctx,
		caseItem,
		0,
		"OpenPostModerationCase",
		commandDigest,
		moderationports.AuditActionOpened,
		"",
		"content.post_moderation_case.opened",
		payload,
		now,
	)
}

func (s *ModerationService) ReviewPostModerationCase(
	ctx context.Context,
	command ReviewPostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	commandDigest := moderationCommandDigest("ReviewPostModerationCase", encoded)
	if replayed, found, err := s.replay(
		ctx,
		"ReviewPostModerationCase",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	caseItem, found, err := s.load(ctx, command.CaseID)
	if err != nil {
		return PostModerationCaseCommandResult{}, err
	}
	if !found {
		return PostModerationCaseCommandResult{}, moderationCaseNotFound(command.CaseID)
	}
	expectedVersion := caseItem.Version()
	now := s.now().UTC()
	if err := caseItem.Review(command.ReviewerID, now); err != nil {
		return PostModerationCaseCommandResult{}, mapModerationDomainError(err)
	}
	payload, err := json.Marshal(postModerationReviewedPayload{
		CaseID:     caseItem.ID(),
		ReviewerID: caseItem.ReviewerID(),
	})
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	return s.commit(
		ctx,
		caseItem,
		expectedVersion,
		"ReviewPostModerationCase",
		commandDigest,
		moderationports.AuditActionReviewed,
		"",
		"content.post_moderation_case.reviewed",
		payload,
		now,
	)
}

func (s *ModerationService) DecidePostModerationCase(
	ctx context.Context,
	command DecidePostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	commandDigest := moderationCommandDigest("DecidePostModerationCase", encoded)
	if replayed, found, err := s.replay(
		ctx,
		"DecidePostModerationCase",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	caseItem, found, err := s.load(ctx, command.CaseID)
	if err != nil {
		return PostModerationCaseCommandResult{}, err
	}
	if !found {
		return PostModerationCaseCommandResult{}, moderationCaseNotFound(command.CaseID)
	}
	expectedVersion := caseItem.Version()
	now := s.now().UTC()
	if err := caseItem.Decide(
		command.ReviewerID,
		command.Decision,
		command.DecisionReason,
		now,
	); err != nil {
		return PostModerationCaseCommandResult{}, mapModerationDomainError(err)
	}
	action := moderationports.AuditActionRejected
	if caseItem.Status() == moderationmodel.StatusApproved {
		action = moderationports.AuditActionApproved
	}
	payload, err := json.Marshal(postModerationDecidedPayload{
		CaseID:        caseItem.ID(),
		PostID:        caseItem.PostID(),
		PostVersion:   caseItem.PostVersion(),
		ContentDigest: caseItem.ContentDigest(),
		ReviewerID:    caseItem.ReviewerID(),
		Status:        caseItem.Status(),
	})
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	return s.commit(
		ctx,
		caseItem,
		expectedVersion,
		"DecidePostModerationCase",
		commandDigest,
		action,
		command.DecisionReason,
		"content.post_moderation_case.decided",
		payload,
		now,
	)
}

func (s *ModerationService) SupersedePostModerationCase(
	ctx context.Context,
	command SupersedePostModerationCaseCommand,
) (PostModerationCaseCommandResult, error) {
	encoded, err := json.Marshal(command)
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	commandDigest := moderationCommandDigest("SupersedePostModerationCase", encoded)
	if replayed, found, err := s.replay(
		ctx,
		"SupersedePostModerationCase",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	caseItem, found, err := s.load(ctx, command.CaseID)
	if err != nil {
		return PostModerationCaseCommandResult{}, err
	}
	if !found {
		return PostModerationCaseCommandResult{}, moderationCaseNotFound(command.CaseID)
	}
	expectedVersion := caseItem.Version()
	now := s.now().UTC()
	if err := caseItem.Supersede(now); err != nil {
		return PostModerationCaseCommandResult{}, mapModerationDomainError(err)
	}
	payload, err := json.Marshal(postModerationSupersededPayload{
		CaseID:      caseItem.ID(),
		PostID:      caseItem.PostID(),
		PostVersion: caseItem.PostVersion(),
	})
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	return s.commit(
		ctx,
		caseItem,
		expectedVersion,
		"SupersedePostModerationCase",
		commandDigest,
		moderationports.AuditActionSuperseded,
		"",
		"content.post_moderation_case.superseded",
		payload,
		now,
	)
}

func (s *ModerationService) GetPostPublicationEligibility(
	ctx context.Context,
	query GetPostPublicationEligibilityQuery,
) (PublicationEligibilitySlice, error) {
	eligibility, err := s.data.Eligibility.GetPublicationEligibility(
		ctx,
		moderationports.PublicationEligibilityQuery{
			PostID:        strings.TrimSpace(query.PostID),
			PostVersion:   query.PostVersion,
			ContentDigest: strings.TrimSpace(query.ContentDigest),
		},
	)
	if err != nil {
		return PublicationEligibilitySlice{}, unavailable(err)
	}
	return PublicationEligibilitySlice{
		Eligible:      eligibility.Eligible,
		CaseID:        eligibility.CaseID,
		CaseVersion:   eligibility.CaseVersion,
		Moderation:    eligibility.Moderation,
		CheckedAt:     eligibility.CheckedAt,
		DecisionAt:    cloneTime(eligibility.DecisionAt),
		FailureReason: eligibility.FailureReason,
	}, nil
}

func (s *ModerationService) replay(
	ctx context.Context,
	commandName string,
	commandDigest string,
) (PostModerationCaseCommandResult, bool, error) {
	idempotencyKey, err := requireModerationIdempotencyKey(ctx)
	if err != nil {
		return PostModerationCaseCommandResult{}, false, err
	}
	result, found, err := s.data.Aggregate.FindReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return PostModerationCaseCommandResult{}, false, unavailable(err)
	}
	if !found {
		return PostModerationCaseCommandResult{}, false, nil
	}
	if result.Aggregate == nil {
		return PostModerationCaseCommandResult{}, false, unavailable(errors.New("moderation receipt has no case"))
	}
	return moderationResult(result.Aggregate, true), true, nil
}

func (s *ModerationService) load(
	ctx context.Context,
	caseID string,
) (*moderationmodel.PostModerationCase, bool, error) {
	caseItem, found, err := s.data.Aggregate.Load(ctx, strings.TrimSpace(caseID))
	if err != nil {
		return nil, false, unavailable(err)
	}
	return caseItem, found, nil
}

func (s *ModerationService) commit(
	ctx context.Context,
	caseItem *moderationmodel.PostModerationCase,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	auditAction moderationports.AuditAction,
	decisionReason string,
	eventType string,
	eventPayload []byte,
	now time.Time,
) (PostModerationCaseCommandResult, error) {
	idempotencyKey, err := requireModerationIdempotencyKey(ctx)
	if err != nil {
		return PostModerationCaseCommandResult{}, err
	}
	eventID, err := s.newID("evt")
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	result, err := s.data.Aggregate.Commit(ctx, moderationports.Commit{
		Aggregate:        caseItem,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.Add(moderationReceiptTTL),
		Audit: moderationports.AuditEntry{
			CaseID:         caseItem.ID(),
			CaseVersion:    caseItem.Version(),
			PostID:         caseItem.PostID(),
			PostVersion:    caseItem.PostVersion(),
			ContentDigest:  caseItem.ContentDigest(),
			ReviewerID:     caseItem.ReviewerID(),
			Action:         auditAction,
			DecisionReason: strings.TrimSpace(decisionReason),
			OccurredAt:     now,
		},
		Events: []moderationports.OutboxEvent{{
			EventID:          eventID,
			EventType:        eventType,
			AggregateID:      caseItem.ID(),
			AggregateVersion: caseItem.Version(),
			Payload:          eventPayload,
			OccurredAt:       now,
		}},
	})
	if err != nil {
		return PostModerationCaseCommandResult{}, unavailable(err)
	}
	return moderationResult(result.Aggregate, result.Replayed), nil
}

func moderationResult(
	caseItem *moderationmodel.PostModerationCase,
	replayed bool,
) PostModerationCaseCommandResult {
	if caseItem == nil {
		return PostModerationCaseCommandResult{Replayed: replayed}
	}
	return PostModerationCaseCommandResult{
		CaseID:   caseItem.ID(),
		Version:  caseItem.Version(),
		Status:   caseItem.Status(),
		Replayed: replayed,
	}
}

func requireModerationIdempotencyKey(ctx context.Context) (string, error) {
	key := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if key == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			"post moderation command requires idempotencyKey",
		)
	}
	return key, nil
}

func moderationCommandDigest(commandName string, encoded []byte) string {
	hasher := sha256.New()
	_, _ = hasher.Write([]byte(commandName))
	_, _ = hasher.Write([]byte{0})
	_, _ = hasher.Write(encoded)
	return hex.EncodeToString(hasher.Sum(nil))
}

func mapModerationDomainError(err error) error {
	switch {
	case errors.Is(err, moderationmodel.ErrReviewerForbidden):
		return contentgenerated.AppErrorFromUnauthorized(err.Error())
	case errors.Is(err, moderationmodel.ErrInvalidPostModerationCase),
		errors.Is(err, moderationmodel.ErrInvalidPostModerationCaseTransition):
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"审核状态或参数不合法",
			err.Error(),
		)
	default:
		return err
	}
}

func moderationCaseNotFound(caseID string) error {
	return contentgenerated.AppErrorFromMediaNotFound(
		fmt.Sprintf("post moderation case %s not found", strings.TrimSpace(caseID)),
	)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return rterr.NewUnavailable(
		rterr.ModuleContent,
		"审核服务暂时不可用",
		err.Error(),
	)
}

func newModerationIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}

type postModerationOpenedPayload struct {
	CaseID        string `json:"caseId"`
	PostID        string `json:"postId"`
	PostVersion   int64  `json:"postVersion"`
	ContentDigest string `json:"contentDigest"`
}

type postModerationReviewedPayload struct {
	CaseID     string `json:"caseId"`
	ReviewerID string `json:"reviewerId"`
}

type postModerationDecidedPayload struct {
	CaseID        string                 `json:"caseId"`
	PostID        string                 `json:"postId"`
	PostVersion   int64                  `json:"postVersion"`
	ContentDigest string                 `json:"contentDigest"`
	ReviewerID    string                 `json:"reviewerId"`
	Status        moderationmodel.Status `json:"status"`
}

type postModerationSupersededPayload struct {
	CaseID      string `json:"caseId"`
	PostID      string `json:"postId"`
	PostVersion int64  `json:"postVersion"`
}
