package circlebehaviorfact

import "errors"

var (
	ErrInvalidFact         = errors.New("invalid CircleBehaviorFact")
	ErrIdempotencyConflict = errors.New("CircleBehaviorFact idempotency conflict")
)

func IsValidBehaviorEventType(value BehaviorEventType) bool {
	switch value {
	case BehaviorEventTypeImpression, BehaviorEventTypeClick, BehaviorEventTypeDwell,
		BehaviorEventTypeLike, BehaviorEventTypeDislike, BehaviorEventTypeHideAuthor,
		BehaviorEventTypeHideContentType, BehaviorEventTypeReport, BehaviorEventTypeShare,
		BehaviorEventTypeComment, BehaviorEventTypeIntersectionExpand, BehaviorEventTypeIntersectionFeedback,
		BehaviorEventTypeWishlistAdd, BehaviorEventTypeWishlistRemove, BehaviorEventTypeSkip,
		BehaviorEventTypeFollow, BehaviorEventTypeJoinCircle, BehaviorEventTypeAddContact,
		BehaviorEventTypeAuthorView, BehaviorEventTypeTagClick, BehaviorEventTypeContentDepth,
		BehaviorEventTypePlayProgress, BehaviorEventTypeAssistantInterest:
		return true
	default:
		return false
	}
}
