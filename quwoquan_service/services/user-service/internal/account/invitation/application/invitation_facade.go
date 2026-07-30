package application

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"

	invitationgenerated "quwoquan_service/services/user-service/generated/account/invitation"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	invitationmodel "quwoquan_service/services/user-service/internal/account/invitation/domain/model"
	invitationports "quwoquan_service/services/user-service/internal/account/invitation/domain/ports"
)

const (
	invitationDailyLimit = 1000
	invitationTTL        = 7 * 24 * time.Hour
)

type Facade struct {
	store    invitationports.InvitationStore
	personas invitationports.PersonaOwnerReader
	clock    func() time.Time
}

func NewFacade(
	store invitationports.InvitationStore,
	personas invitationports.PersonaOwnerReader,
) (*Facade, error) {
	if store == nil || personas == nil {
		return nil, errors.New("invitation store and persona owner reader are required")
	}
	return &Facade{store: store, personas: personas, clock: time.Now}, nil
}

func (facade *Facade) Generate(
	ctx context.Context,
	actorAccountID string,
	inviterPersonaID string,
	channel string,
	inviteePhone string,
) (*invitationmodel.Invitation, error) {
	actorAccountID = strings.TrimSpace(actorAccountID)
	inviterPersonaID = strings.TrimSpace(inviterPersonaID)
	channel = strings.TrimSpace(channel)
	inviteePhone = strings.TrimSpace(inviteePhone)
	if actorAccountID == "" || inviterPersonaID == "" || !validChannel(channel) {
		return nil, usergenerated.AppErrorFromInvalidArgument("invalid invitation command")
	}
	ownerAccountID, found, err := facade.personas.ResolveOwnerAccountID(
		ctx,
		inviterPersonaID,
	)
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError("resolve invitation persona owner")
	}
	if !found || ownerAccountID != actorAccountID {
		return nil, usergenerated.AppErrorFromForbidden("invitation persona is not owned by actor")
	}
	now := facade.clock().UTC()
	linkCode, err := randomLinkCode()
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError("generate invitation link code")
	}
	candidate := &invitationmodel.Invitation{
		ID:                    uuid.NewString(),
		InviterPersonaID:      inviterPersonaID,
		InviterOwnerAccountID: ownerAccountID,
		Channel:               channel,
		LinkCode:              linkCode,
		InviteePhoneHash:      hashInviteePhone(inviteePhone),
		Status:                invitationmodel.StatusGenerated,
		ExpireAt:              now.Add(invitationTTL),
		GeneratedAt:           now,
	}
	if err := candidate.ValidateNew(); err != nil {
		return nil, usergenerated.AppErrorFromInvalidArgument("invalid invitation aggregate")
	}
	stored, _, err := facade.store.Generate(ctx, candidate, invitationDailyLimit)
	if errors.Is(err, invitationports.ErrDailyLimit) {
		return nil, invitationgenerated.AppErrorFromInvitationDailyLimitExceeded(err.Error())
	}
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError("persist invitation")
	}
	return stored, nil
}

func (facade *Facade) GetByCode(
	ctx context.Context,
	linkCode string,
) (*invitationmodel.Invitation, error) {
	linkCode = strings.TrimSpace(linkCode)
	if linkCode == "" {
		return nil, invitationgenerated.AppErrorFromInvitationNotFound("invitation code missing")
	}
	record, err := facade.store.MarkDelivered(ctx, linkCode, facade.clock().UTC())
	return record, mapStoreError(err)
}

func (facade *Facade) Accept(
	ctx context.Context,
	actorAccountID string,
	linkCode string,
) (*invitationmodel.Invitation, error) {
	if strings.TrimSpace(actorAccountID) == "" {
		return nil, usergenerated.AppErrorFromUnauthorized("authenticated account required")
	}
	linkCode = strings.TrimSpace(linkCode)
	if linkCode == "" {
		return nil, invitationgenerated.AppErrorFromInvitationNotFound("invitation code missing")
	}
	record, err := facade.store.Accept(ctx, linkCode, facade.clock().UTC())
	return record, mapStoreError(err)
}

func (facade *Facade) List(
	ctx context.Context,
	actorAccountID string,
	inviterPersonaID string,
	status string,
	limit int,
	offset int,
) ([]invitationmodel.Invitation, error) {
	actorAccountID = strings.TrimSpace(actorAccountID)
	inviterPersonaID = strings.TrimSpace(inviterPersonaID)
	if actorAccountID == "" || inviterPersonaID == "" {
		return nil, usergenerated.AppErrorFromInvalidArgument("invitation persona is required")
	}
	ownerAccountID, found, err := facade.personas.ResolveOwnerAccountID(ctx, inviterPersonaID)
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError("resolve invitation persona owner")
	}
	if !found || ownerAccountID != actorAccountID {
		return nil, usergenerated.AppErrorFromForbidden("invitation persona is not owned by actor")
	}
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	if offset < 0 {
		offset = 0
	}
	records, err := facade.store.ListByInviter(
		ctx,
		inviterPersonaID,
		strings.TrimSpace(status),
		limit,
		offset,
	)
	if err != nil {
		return nil, usergenerated.AppErrorFromInternalError("list invitations")
	}
	now := facade.clock().UTC()
	for index := range records {
		records[index].ProjectExpiry(now)
	}
	return records, nil
}

func mapStoreError(err error) error {
	switch {
	case err == nil:
		return nil
	case errors.Is(err, invitationports.ErrNotFound):
		return invitationgenerated.AppErrorFromInvitationNotFound(err.Error())
	case errors.Is(err, invitationmodel.ErrExpired):
		return invitationgenerated.AppErrorFromInvitationExpired(err.Error())
	case errors.Is(err, invitationmodel.ErrInvalidTransition):
		return invitationgenerated.AppErrorFromInvitationInvalidTransition(err.Error())
	default:
		return usergenerated.AppErrorFromInternalError("invitation persistence failure")
	}
}

func validChannel(channel string) bool {
	switch channel {
	case "link", "qrcode", "contact", "sms", "direct", "social":
		return true
	default:
		return false
	}
}

func randomLinkCode() (string, error) {
	random := make([]byte, 12)
	if _, err := rand.Read(random); err != nil {
		return "", err
	}
	return hex.EncodeToString(random), nil
}

func hashInviteePhone(value string) string {
	if value == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}
