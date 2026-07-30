package behavior

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/content/post/application/ports"
)

func wishlistEventFromInput(
	input BehaviorEventInput,
	userID, contentID, action string,
	occurredAt time.Time,
) ports.WishlistEvent {
	status := "active"
	if action == "wishlist_remove" {
		status = "removed"
	}
	entityID := strings.TrimSpace(firstNonEmptyLocal(
		input.ObjectID,
		firstString(input.EntityRefs),
		contentID,
	))
	objectType := strings.TrimSpace(firstNonEmptyLocal(input.ObjectKind, input.ContentType))
	return ports.WishlistEvent{
		UserID:         userID,
		EntityID:       entityID,
		ObjectType:     objectType,
		DisplayName:    strings.TrimSpace(input.DisplayName),
		Status:         status,
		SourceSurface:  strings.TrimSpace(input.SourceSurface),
		ReferralSource: strings.TrimSpace(input.ReferralSource),
		FeedRequestID:  strings.TrimSpace(input.FeedRequestID),
		SessionID:      strings.TrimSpace(input.SessionID),
		ClientEventID:  strings.TrimSpace(input.ClientEventID),
		CreatedAt:      occurredAt,
		UpdatedAt:      occurredAt,
	}
}

// EntityWishlistState 是当前用户对 canonical object 的私有「想去」读模型。
type EntityWishlistState struct {
	ObjectID   string `json:"objectId"`
	ObjectKind string `json:"objectKind"`
	Wishlisted bool   `json:"wishlisted"`
}

// GetEntityWishlistState 读取与 wishlist_add / wishlist_remove 同源的状态。
func (s *BehaviorService) GetEntityWishlistState(
	ctx context.Context,
	userID string,
	objectID string,
	objectKind string,
) (EntityWishlistState, error) {
	userID = strings.TrimSpace(userID)
	objectID = strings.TrimSpace(objectID)
	objectKind = strings.TrimSpace(objectKind)
	if userID == "" {
		return EntityWishlistState{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"需要登录",
			"entity wishlist state requires authenticated user",
		)
	}
	if objectID == "" || objectKind == "" {
		return EntityWishlistState{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"对象参数不完整",
			"entity wishlist state requires objectId and objectKind",
		)
	}
	if s.wishlistReader == nil {
		return EntityWishlistState{}, rterr.NewUnavailable(
			rterr.ModuleContent,
			"想去状态暂不可用",
			"wishlist state reader is not configured",
		)
	}
	wishlisted, err := s.wishlistReader.IsWishlisted(
		ctx,
		userID,
		objectID,
		objectKind,
	)
	if err != nil {
		return EntityWishlistState{}, err
	}
	return EntityWishlistState{
		ObjectID:   objectID,
		ObjectKind: objectKind,
		Wishlisted: wishlisted,
	}, nil
}
