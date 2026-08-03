package application

import (
	"context"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_membership/domain/ports"
)

type MembershipSourceResolver interface {
	ValidateMembershipSource(context.Context, model.SourceRef, int64, string) error
}

type SourceAuthority struct {
	resolvers map[model.SourceKind]MembershipSourceResolver
}

func NewSourceAuthority(resolvers map[model.SourceKind]MembershipSourceResolver) *SourceAuthority {
	copyOfResolvers := make(map[model.SourceKind]MembershipSourceResolver, len(resolvers))
	for kind, resolver := range resolvers {
		if kind.Valid() && kind != model.SourceTripInvitation && resolver != nil {
			copyOfResolvers[kind] = resolver
		}
	}
	return &SourceAuthority{resolvers: copyOfResolvers}
}

func (authority *SourceAuthority) ValidateMembershipSource(
	ctx context.Context,
	kind model.SourceKind,
	ref *model.SourceRef,
	sourceVersion int64,
	personaID string,
) error {
	personaID = strings.TrimSpace(personaID)
	if !kind.Valid() || sourceVersion < 0 || personaID == "" {
		return model.ErrInvalidArgument
	}
	if kind == model.SourceTripInvitation {
		if ref != nil || sourceVersion != 0 {
			return model.ErrInvalidArgument
		}
		return nil
	}
	if sourceVersion <= 0 || ref == nil || strings.TrimSpace(ref.ObjectTypeRef) == "" || strings.TrimSpace(ref.ObjectID) == "" {
		return model.ErrInvalidArgument
	}
	resolver := authority.resolvers[kind]
	if resolver == nil {
		return ports.ErrSourceUnavailable
	}
	return resolver.ValidateMembershipSource(ctx, model.SourceRef{
		ObjectTypeRef: strings.TrimSpace(ref.ObjectTypeRef),
		ObjectID:      strings.TrimSpace(ref.ObjectID),
	}, sourceVersion, personaID)
}

var _ ports.SourceAuthority = (*SourceAuthority)(nil)
