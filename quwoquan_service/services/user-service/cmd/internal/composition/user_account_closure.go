package composition

import (
	"context"
	"fmt"
	"strings"
	"time"

	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
	creatorapp "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
	visitapp "quwoquan_service/services/user-service/internal/relationship/followed_subject_visit_state/application"
)

type followingAccountClosure interface {
	Apply(context.Context, followingapp.AccountClosedEvent) error
}

type visitAccountClosure interface {
	Apply(context.Context, visitapp.AccountClosedEvent) error
}

type creatorAccountClosure interface {
	Apply(context.Context, creatorapp.AccountClosedEvent) error
}

// UserAccountClosurePublisher is composition glue only: it translates the
// committed UserAccount event into each consumer object's typed subscription.
type UserAccountClosurePublisher struct {
	following followingAccountClosure
	visits    visitAccountClosure
	creators  creatorAccountClosure
}

func NewUserAccountClosurePublisher(
	following followingAccountClosure,
	visits visitAccountClosure,
	creators creatorAccountClosure,
) *UserAccountClosurePublisher {
	if following == nil || visits == nil || creators == nil {
		panic("UserAccount closure consumers are required")
	}
	return &UserAccountClosurePublisher{
		following: following,
		visits:    visits,
		creators:  creators,
	}
}

func (p *UserAccountClosurePublisher) PublishUserEvent(
	ctx context.Context,
	eventType string,
	accountID string,
	_ string,
	payload map[string]any,
) error {
	if eventType != userevent.UserAccountClosed {
		return nil
	}
	accountID = strings.TrimSpace(accountID)
	personaIDs := closurePersonaIDs(payload)
	if accountID == "" || len(personaIDs) == 0 {
		return nil
	}
	if err := p.following.Apply(ctx, followingapp.AccountClosedEvent{
		AccountID: accountID, PersonaIDs: personaIDs,
	}); err != nil {
		return fmt.Errorf("apply FollowingSubject account closure: %w", err)
	}
	if err := p.visits.Apply(ctx, visitapp.AccountClosedEvent{
		AccountID: accountID, PersonaIDs: personaIDs,
	}); err != nil {
		return fmt.Errorf("apply FollowedSubjectVisitState account closure: %w", err)
	}
	if err := p.creators.Apply(ctx, creatorapp.AccountClosedEvent{
		AccountID: accountID, PersonaIDs: personaIDs, ClosedAt: closureEventTime(payload),
	}); err != nil {
		return fmt.Errorf("apply CreatorRuntimeProfile account closure: %w", err)
	}
	return nil
}

func closurePersonaIDs(payload map[string]any) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0)
	appendID := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, exists := seen[value]; exists {
			return
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	switch values := payload["personaIds"].(type) {
	case []string:
		for _, value := range values {
			appendID(value)
		}
	case []any:
		for _, value := range values {
			if text, ok := value.(string); ok {
				appendID(text)
			}
		}
	}
	return result
}

func closureEventTime(payload map[string]any) time.Time {
	if raw, ok := payload["updatedAt"].(string); ok {
		if parsed, err := time.Parse(time.RFC3339Nano, raw); err == nil {
			return parsed.UTC()
		}
	}
	return time.Unix(0, 0).UTC()
}
