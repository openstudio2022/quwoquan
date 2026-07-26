package circlebehaviorfact

import "errors"

var (
	ErrInvalidFact         = errors.New("invalid CircleBehaviorFact")
	ErrIdempotencyConflict = errors.New("CircleBehaviorFact idempotency conflict")
)

func IsValidBehaviorEventType(value BehaviorEventType) bool {
	switch value {
	case BehaviorEventTypeImpression, BehaviorEventTypeClick, BehaviorEventTypeDwell,
		BehaviorEventTypeLike, BehaviorEventTypeDislike, BehaviorEventTypeUndoDislike,
		BehaviorEventTypeHideAuthor,
		BehaviorEventTypeHideContentType, BehaviorEventTypeReport, BehaviorEventTypeShare,
		BehaviorEventTypeComment, BehaviorEventTypeIntersectionExpand, BehaviorEventTypeIntersectionFeedback,
		BehaviorEventTypeWishlistAdd, BehaviorEventTypeWishlistRemove, BehaviorEventTypeSkip,
		BehaviorEventTypeFollow, BehaviorEventTypeJoinCircle, BehaviorEventTypeLeaveCircle,
		BehaviorEventTypeAddContact, BehaviorEventTypeAuthorView, BehaviorEventTypeEntityPageView,
		BehaviorEventTypeTagClick, BehaviorEventTypeContentDepth, BehaviorEventTypePlayProgress,
		BehaviorEventTypeEffectivePlay, BehaviorEventTypeAssistantInterest,
		BehaviorEventTypeOnboardingInterest:
		return true
	default:
		return false
	}
}
