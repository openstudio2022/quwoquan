package api_integration

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

type accountClosureTestPublisher struct {
	following *followingapp.AccountClosureProjector
	visits    *visitapp.AccountClosureProjector
	creators  *creatorapp.AccountClosureProjector
}

func newAccountClosureTestPublisher(
	following followingapp.AccountClosureStore,
	visits visitapp.AccountClosureStore,
	creators creatorapp.AccountClosureStore,
) *accountClosureTestPublisher {
	return &accountClosureTestPublisher{
		following: followingapp.NewAccountClosureProjector(following),
		visits:    visitapp.NewAccountClosureProjector(visits),
		creators:  creatorapp.NewAccountClosureProjector(creators),
	}
}

func (p *accountClosureTestPublisher) PublishUserEvent(
	ctx context.Context,
	eventType string,
	accountID string,
	_ string,
	payload map[string]any,
) error {
	if eventType != userevent.UserAccountClosed {
		return nil
	}
	personaIDs := accountClosureTestPersonaIDs(payload)
	if strings.TrimSpace(accountID) == "" || len(personaIDs) == 0 {
		return nil
	}
	if err := p.following.Apply(ctx, followingapp.AccountClosedEvent{
		AccountID: accountID, PersonaIDs: personaIDs,
	}); err != nil {
		return fmt.Errorf("following closure: %w", err)
	}
	if err := p.visits.Apply(ctx, visitapp.AccountClosedEvent{
		AccountID: accountID, PersonaIDs: personaIDs,
	}); err != nil {
		return fmt.Errorf("visit closure: %w", err)
	}
	return p.creators.Apply(ctx, creatorapp.AccountClosedEvent{
		AccountID: accountID, PersonaIDs: personaIDs, ClosedAt: accountClosureTestTime(payload),
	})
}

func accountClosureTestPersonaIDs(payload map[string]any) []string {
	result := make([]string, 0)
	switch values := payload["personaIds"].(type) {
	case []string:
		result = append(result, values...)
	case []any:
		for _, value := range values {
			if text, ok := value.(string); ok && strings.TrimSpace(text) != "" {
				result = append(result, strings.TrimSpace(text))
			}
		}
	}
	return result
}

func accountClosureTestTime(payload map[string]any) time.Time {
	if raw, ok := payload["updatedAt"].(string); ok {
		if parsed, err := time.Parse(time.RFC3339Nano, raw); err == nil {
			return parsed.UTC()
		}
	}
	return time.Unix(0, 0).UTC()
}
