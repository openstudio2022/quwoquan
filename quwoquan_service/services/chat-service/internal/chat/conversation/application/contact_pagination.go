package application

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

var ErrInvalidContactCursor = errors.New("invalid contact cursor")

type ContactPage struct {
	Items      []map[string]any
	NextCursor string
}

type contactPageCursor struct {
	Source              string `json:"s"`
	AfterConversationID string `json:"c,omitempty"`
	SocialCursor        string `json:"r,omitempty"`
}

func (s *MemberService) ListContacts(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) (ContactPage, error) {
	limit = clampSearchLimit(limit, 100)
	decoded, err := decodeContactPageCursor(cursor)
	if err != nil {
		return ContactPage{}, err
	}

	if decoded.Source == "conversation" {
		page, nextAfterConversationID, err := s.listConversationContactPage(
			ctx,
			userID,
			limit,
			decoded.AfterConversationID,
		)
		if err != nil {
			return ContactPage{}, err
		}
		if nextAfterConversationID != "" {
			return ContactPage{
				Items: page,
				NextCursor: encodeContactPageCursor(contactPageCursor{
					Source:              "conversation",
					AfterConversationID: nextAfterConversationID,
				}),
			}, nil
		}
		if len(page) > 0 {
			return ContactPage{
				Items: page,
				NextCursor: encodeContactPageCursor(contactPageCursor{
					Source: "social",
				}),
			}, nil
		}
		decoded = contactPageCursor{Source: "social"}
	}

	hits, nextSocialCursor, err := s.socialContactPageHits(
		ctx,
		userID,
		limit,
		decoded.SocialCursor,
	)
	if err != nil {
		return ContactPage{}, err
	}
	return ContactPage{
		Items:      contactHitsToMaps(hits),
		NextCursor: nextSocialContactPageCursor(nextSocialCursor),
	}, nil
}

func (s *MemberService) listConversationContactPage(
	ctx context.Context,
	userID string,
	limit int,
	afterConversationID string,
) ([]map[string]any, string, error) {
	states, err := s.userStates.ListUserStatesByConversationID(
		ctx,
		userID,
		limit+1,
		afterConversationID,
	)
	if err != nil {
		return nil, "", err
	}
	hasMore := len(states) > limit
	if hasMore {
		states = states[:limit]
	}
	hits := make([]ContactSearchHit, 0, len(states))
	for _, state := range states {
		conversationID := strings.TrimSpace(state.ConversationId)
		if conversationID == "" {
			continue
		}
		conversation, err := s.conversations.FindConversationByID(ctx, conversationID)
		if err != nil || conversation == nil || conversation.Type != "direct" {
			continue
		}
		hit, ok := s.contactHitForConversation(ctx, userID, *conversation)
		if !ok {
			continue
		}
		exposable, err := s.canExposeContact(ctx, userID, hit)
		if err != nil {
			return nil, "", err
		}
		if !exposable {
			continue
		}
		hits = append(hits, hit)
	}
	nextAfterConversationID := ""
	if hasMore && len(states) > 0 {
		nextAfterConversationID = strings.TrimSpace(
			states[len(states)-1].ConversationId,
		)
	}
	return contactHitsToMaps(hits), nextAfterConversationID, nil
}

func (s *MemberService) socialContactSeedsToHits(
	ctx context.Context,
	userID string,
	seeds []SocialContactSeed,
) ([]ContactSearchHit, error) {
	if len(seeds) == 0 {
		return nil, nil
	}
	profiles, err := s.profiles.ResolveMany(ctx, socialSeedIDs(seeds))
	if err != nil {
		profiles = map[string]ProfileSnapshot{}
	}
	hits := make([]ContactSearchHit, 0, len(seeds))
	for _, seed := range seeds {
		hit := socialSeedToHit(seed, profiles[seed.UserID])
		if hit.ContactID == "" {
			continue
		}
		exposable, err := s.canExposeContact(ctx, userID, hit)
		if err != nil {
			return nil, err
		}
		if !exposable {
			continue
		}
		hits = append(hits, hit)
	}
	return hits, nil
}

func (s *MemberService) socialContactPageHits(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) ([]ContactSearchHit, string, error) {
	hitsByID := make(map[string]ContactSearchHit, limit)
	order := make([]string, 0, limit)
	seenCursors := make(map[string]struct{})
	for pageReads := 0; pageReads < 3; pageReads += 1 {
		if cursor != "" {
			if _, exists := seenCursors[cursor]; exists {
				return nil, "", fmt.Errorf("%w: repeated social continuation", ErrInvalidContactCursor)
			}
			seenCursors[cursor] = struct{}{}
		}
		page, err := s.socialContacts.ListContactPage(
			ctx,
			userID,
			limit-len(order),
			cursor,
		)
		if err != nil {
			return nil, "", err
		}
		pageHits, err := s.socialContactSeedsToHits(ctx, userID, page.Items)
		if err != nil {
			return nil, "", err
		}
		for _, hit := range pageHits {
			if existing, ok := hitsByID[hit.ContactID]; ok {
				hitsByID[hit.ContactID] = mergeContactSearchHit(existing, hit)
				continue
			}
			if len(order) >= limit {
				break
			}
			hitsByID[hit.ContactID] = hit
			order = append(order, hit.ContactID)
		}
		nextCursor := strings.TrimSpace(page.NextCursor)
		if nextCursor == "" {
			return orderedContactHits(order, hitsByID), "", nil
		}
		if len(order) >= limit {
			return orderedContactHits(order, hitsByID), nextCursor, nil
		}
		if pageReads == 2 {
			return orderedContactHits(order, hitsByID), nextCursor, nil
		}
		cursor = nextCursor
	}
	return orderedContactHits(order, hitsByID), "", nil
}

func orderedContactHits(
	order []string,
	hitsByID map[string]ContactSearchHit,
) []ContactSearchHit {
	hits := make([]ContactSearchHit, 0, len(order))
	for _, contactID := range order {
		hits = append(hits, hitsByID[contactID])
	}
	return hits
}

func decodeContactPageCursor(raw string) (contactPageCursor, error) {
	if strings.TrimSpace(raw) == "" {
		return contactPageCursor{Source: "conversation"}, nil
	}
	decoded, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return contactPageCursor{}, fmt.Errorf("%w: %v", ErrInvalidContactCursor, err)
	}
	var cursor contactPageCursor
	if err := json.Unmarshal(decoded, &cursor); err != nil {
		return contactPageCursor{}, fmt.Errorf("%w: %v", ErrInvalidContactCursor, err)
	}
	switch cursor.Source {
	case "conversation":
		if strings.TrimSpace(cursor.AfterConversationID) == "" {
			return contactPageCursor{}, fmt.Errorf("%w: missing conversation position", ErrInvalidContactCursor)
		}
	case "social":
	default:
		return contactPageCursor{}, fmt.Errorf("%w: unsupported source", ErrInvalidContactCursor)
	}
	return cursor, nil
}

func encodeContactPageCursor(cursor contactPageCursor) string {
	payload, _ := json.Marshal(cursor)
	return base64.RawURLEncoding.EncodeToString(payload)
}

func nextSocialContactPageCursor(socialCursor string) string {
	if strings.TrimSpace(socialCursor) == "" {
		return ""
	}
	return encodeContactPageCursor(contactPageCursor{
		Source:       "social",
		SocialCursor: socialCursor,
	})
}
