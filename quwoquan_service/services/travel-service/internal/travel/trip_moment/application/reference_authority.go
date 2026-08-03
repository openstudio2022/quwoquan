package application

import (
	"context"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
)

const (
	mediaAssetObjectType = "content.MediaAsset"
	postObjectType       = "content.Post"
	placeObjectType      = "entity.Homepage"
)

type ObjectReferenceResolver interface {
	ValidateObjectReference(context.Context, model.ObjectRef, string, model.Kind) error
}

type ReferenceAuthority struct {
	resolvers map[string]ObjectReferenceResolver
}

func NewReferenceAuthority(resolvers map[string]ObjectReferenceResolver) *ReferenceAuthority {
	copyOfResolvers := make(map[string]ObjectReferenceResolver, len(resolvers))
	for objectType, resolver := range resolvers {
		objectType = strings.TrimSpace(objectType)
		if objectType != "" && resolver != nil {
			copyOfResolvers[objectType] = resolver
		}
	}
	return &ReferenceAuthority{resolvers: copyOfResolvers}
}

func (authority *ReferenceAuthority) ValidateMomentReferences(
	ctx context.Context,
	kind model.Kind,
	contentRef *model.ObjectRef,
	placeRef *model.ObjectRef,
	actorPersonaID string,
) error {
	actorPersonaID = strings.TrimSpace(actorPersonaID)
	if actorPersonaID == "" || !kind.Valid() {
		return model.ErrInvalidArgument
	}
	expectedContentType := ""
	switch kind {
	case model.KindPhoto, model.KindVideo, model.KindVoice:
		expectedContentType = mediaAssetObjectType
	case model.KindPostReference:
		expectedContentType = postObjectType
	case model.KindText, model.KindCheckIn:
	default:
		return model.ErrInvalidArgument
	}
	if expectedContentType == "" && contentRef != nil ||
		expectedContentType != "" && (contentRef == nil || strings.TrimSpace(contentRef.ObjectTypeRef) != expectedContentType) {
		return model.ErrInvalidArgument
	}
	if contentRef != nil {
		if err := authority.validate(ctx, *contentRef, actorPersonaID, kind); err != nil {
			return err
		}
	}
	if placeRef != nil {
		if strings.TrimSpace(placeRef.ObjectTypeRef) != placeObjectType {
			return model.ErrInvalidArgument
		}
		if err := authority.validate(ctx, *placeRef, actorPersonaID, kind); err != nil {
			return err
		}
	}
	return nil
}

func (authority *ReferenceAuthority) validate(
	ctx context.Context,
	ref model.ObjectRef,
	actorPersonaID string,
	kind model.Kind,
) error {
	ref.ObjectTypeRef = strings.TrimSpace(ref.ObjectTypeRef)
	ref.ObjectID = strings.TrimSpace(ref.ObjectID)
	if ref.ObjectTypeRef == "" || ref.ObjectID == "" {
		return model.ErrInvalidArgument
	}
	resolver := authority.resolvers[ref.ObjectTypeRef]
	if resolver == nil {
		return ports.ErrReferenceUnavailable
	}
	return resolver.ValidateObjectReference(ctx, ref, actorPersonaID, kind)
}

var _ ports.ReferenceAuthority = (*ReferenceAuthority)(nil)
