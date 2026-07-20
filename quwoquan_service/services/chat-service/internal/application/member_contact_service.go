package application

import (
	"context"
	"log/slog"
	"strings"
)

func (s *MemberService) ListContacts(
	ctx context.Context,
	userID string,
	limit int,
	_ string,
) ([]map[string]any, error) {
	hits, err := s.combinedContactHits(ctx, userID, "", limit)
	if err != nil {
		return nil, err
	}
	return contactHitsToMaps(hits), nil
}

func (s *MemberService) ListContactHomeCircles(
	ctx context.Context,
	userID string,
	limit int,
) ([]ContactHomeCircleHit, error) {
	if s.circles == nil {
		return nil, nil
	}
	if limit <= 0 {
		limit = 50
	}
	return s.circles.ListCircles(ctx, userID, limit)
}

func (s *MemberService) ListGroupCandidates(
	ctx context.Context,
	userID string,
	conversationID string,
	limit int,
) ([]map[string]any, error) {
	limit = clampSearchLimit(limit, 100)
	locked := map[string]struct{}{strings.TrimSpace(userID): {}}
	if strings.TrimSpace(conversationID) != "" {
		members, err := s.members.ListMembers(ctx, conversationID, ListMembersQuery{
			Limit: 1000,
			Sort:  MemberListSortJoinedAsc,
		})
		if err != nil {
			return nil, err
		}
		for _, member := range members {
			if id := strings.TrimSpace(member.UserId); id != "" {
				locked[id] = struct{}{}
			}
		}
	}

	hits, err := s.combinedContactHits(ctx, userID, "", limit*3)
	if err != nil {
		return nil, err
	}
	items := make([]map[string]any, 0, limit)
	seen := map[string]struct{}{}
	for _, hit := range hits {
		contactID := strings.TrimSpace(hit.ContactID)
		if contactID == "" {
			continue
		}
		if _, ok := locked[contactID]; ok {
			continue
		}
		if _, ok := seen[contactID]; ok {
			continue
		}
		relationState, blocked := s.resolveCandidateRelation(ctx, userID, contactID, hit.RelationState)
		if blocked || relationState != "mutual" {
			continue
		}
		seen[contactID] = struct{}{}
		item := map[string]any{
			"contactId":       contactID,
			"userId":          contactID,
			"displayName":     hit.DisplayName,
			"avatarUrl":       hit.AvatarURL,
			"bio":             hit.Bio,
			"metFrom":         hit.MetFrom,
			"lastInteraction": hit.LastInteraction,
			"relationState":   relationState,
			"source":          hit.Source,
			"subtitle":        hit.Subtitle,
			"highlightText":   hit.HighlightText,
			"matchedField":    hit.MatchedField,
			"isStarred":       hit.IsStarred,
			"candidateSource": "server_group_candidates",
		}
		items = append(items, item)
		if len(items) >= limit {
			break
		}
	}
	return items, nil
}

// resolveCandidateRelation backfills authoritative relationship state for
// conversation-sourced candidates before the mutual-only filter runs.
func (s *MemberService) resolveCandidateRelation(
	ctx context.Context,
	viewerID string,
	contactID string,
	fallback string,
) (string, bool) {
	if s.relationships == nil {
		return normalizeRelationState(fallback), false
	}
	capability, err := s.relationships.GetCapability(ctx, viewerID, contactID)
	if err != nil {
		slog.Warn(
			"relationship gate check failed for group candidates",
			"err", err,
			"viewerID", viewerID,
			"contactID", contactID,
		)
		return normalizeRelationState(fallback), false
	}
	if capability.IsBlocked || capability.IsBlockedBy {
		return "blocked", true
	}
	if capability.IsMutual {
		return "mutual", false
	}
	return "not_mutual", false
}

func contactHitsToMaps(hits []ContactSearchHit) []map[string]any {
	items := make([]map[string]any, 0, len(hits))
	for _, hit := range hits {
		items = append(items, map[string]any{
			"contactId":        hit.ContactID,
			"displayName":      hit.DisplayName,
			"avatarUrl":        hit.AvatarURL,
			"bio":              hit.Bio,
			"metFrom":          hit.MetFrom,
			"lastInteraction":  hit.LastInteraction,
			"relationState":    hit.RelationState,
			"conversationId":   hit.ConversationID,
			"conversationType": hit.ConversationType,
			"subtitle":         hit.Subtitle,
			"highlightText":    hit.HighlightText,
			"matchedField":     hit.MatchedField,
			"source":           hit.Source,
			"isStarred":        hit.IsStarred,
		})
	}
	return items
}

func (s *MemberService) combinedContactHits(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]ContactSearchHit, error) {
	limit = clampSearchLimit(limit, 20)
	normalizedQuery := normalizeSearchQuery(query)
	results := make([]ContactSearchHit, 0, limit)
	indexByID := make(map[string]int, limit)

	conversationHits, err := s.conversationContactHits(ctx, userID, normalizedQuery, limit)
	if err != nil {
		return nil, err
	}
	for _, hit := range conversationHits {
		if !matchesContactQuery(hit, normalizedQuery) {
			continue
		}
		if !s.canExposeContact(ctx, userID, hit) {
			continue
		}
		indexByID[hit.ContactID] = len(results)
		results = append(results, hit)
		if len(results) >= limit {
			return results, nil
		}
	}

	socialHits, err := s.socialContactHits(ctx, userID, normalizedQuery, limit)
	if err != nil {
		slog.Warn("social contact resolution failed", "err", err, "userID", userID)
		socialHits = nil
	}
	for _, hit := range socialHits {
		if !matchesContactQuery(hit, normalizedQuery) {
			continue
		}
		if !s.canExposeContact(ctx, userID, hit) {
			continue
		}
		if idx, ok := indexByID[hit.ContactID]; ok {
			results[idx] = mergeContactSearchHit(results[idx], hit)
			continue
		}
		indexByID[hit.ContactID] = len(results)
		results = append(results, hit)
		if len(results) >= limit {
			break
		}
	}

	if len(results) > limit {
		results = results[:limit]
	}
	return results, nil
}

func (s *MemberService) canExposeContact(
	ctx context.Context,
	viewerID string,
	hit ContactSearchHit,
) bool {
	if s.relationships == nil {
		return true
	}
	contactID := strings.TrimSpace(hit.ContactID)
	if contactID == "" {
		return true
	}
	capability, err := s.relationships.GetCapability(ctx, viewerID, contactID)
	if err != nil {
		slog.Warn(
			"relationship gate check failed for contacts",
			"err",
			err,
			"viewerID",
			viewerID,
			"contactID",
			contactID,
		)
		return true
	}
	return !capability.IsBlocked && !capability.IsBlockedBy
}

func (s *MemberService) socialContactHits(
	ctx context.Context,
	userID string,
	query string,
	limit int,
) ([]ContactSearchHit, error) {
	if s.socialContacts == nil {
		return nil, nil
	}
	seeds, err := s.socialContacts.ListContacts(ctx, userID, limit)
	if err != nil {
		return nil, err
	}
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
		if query != "" && !matchesContactQuery(hit, query) {
			continue
		}
		if query != "" {
			hit.HighlightText = highlightContactHit(hit, query)
		}
		hits = append(hits, hit)
		if len(hits) >= limit {
			break
		}
	}
	return hits, nil
}

func socialSeedIDs(seeds []SocialContactSeed) []string {
	ids := make([]string, 0, len(seeds))
	seen := make(map[string]struct{}, len(seeds))
	for _, seed := range seeds {
		id := strings.TrimSpace(seed.UserID)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		ids = append(ids, id)
	}
	return ids
}

func socialSeedToHit(seed SocialContactSeed, profile ProfileSnapshot) ContactSearchHit {
	displayName := strings.TrimSpace(seed.DisplayName)
	avatarURL := strings.TrimSpace(seed.AvatarURL)
	bio := strings.TrimSpace(seed.Bio)
	if displayName == "" {
		displayName = strings.TrimSpace(profile.DisplayName)
	}
	if avatarURL == "" {
		avatarURL = strings.TrimSpace(profile.AvatarURL)
	}
	if bio == "" {
		bio = strings.TrimSpace(profile.Bio)
	}
	relationState := normalizeRelationState(seed.RelationState)
	source := normalizeContactSource(seed.Source)
	if source == "" {
		source = normalizeContactSource(seed.MetFrom)
	}
	if source == "" {
		source = "contact_discovery"
	}
	subtitle := firstNonEmpty(bio, seed.MetFrom, seed.LastInteraction)
	if subtitle == "" {
		subtitle = displayName
	}
	return ContactSearchHit{
		ContactID:       strings.TrimSpace(seed.UserID),
		DisplayName:     displayName,
		AvatarURL:       avatarURL,
		Bio:             bio,
		MetFrom:         strings.TrimSpace(seed.MetFrom),
		LastInteraction: strings.TrimSpace(seed.LastInteraction),
		RelationState:   relationState,
		Source:          source,
		Subtitle:        subtitle,
		HighlightText:   displayName,
		MatchedField:    "displayName",
		IsStarred:       seed.IsStarred,
	}
}

func mergeContactSearchHit(base, next ContactSearchHit) ContactSearchHit {
	if base.ContactID != next.ContactID {
		return base
	}
	if base.DisplayName == "" {
		base.DisplayName = next.DisplayName
	}
	if base.AvatarURL == "" {
		base.AvatarURL = next.AvatarURL
	}
	if base.Bio == "" {
		base.Bio = next.Bio
	}
	if base.MetFrom == "" {
		base.MetFrom = next.MetFrom
	}
	if base.LastInteraction == "" {
		base.LastInteraction = next.LastInteraction
	}
	base.RelationState = mergeRelationState(base.RelationState, next.RelationState)
	if base.Source == "" || contactSourcePriority(next.Source) < contactSourcePriority(base.Source) {
		base.Source = next.Source
	}
	if base.Subtitle == "" {
		base.Subtitle = next.Subtitle
	}
	if base.HighlightText == "" {
		base.HighlightText = next.HighlightText
	}
	if base.MatchedField == "" {
		base.MatchedField = next.MatchedField
	}
	base.IsStarred = base.IsStarred || next.IsStarred
	return base
}

func matchesContactQuery(hit ContactSearchHit, query string) bool {
	if query == "" {
		return true
	}
	matched, _ := containsQuery(
		[]string{
			hit.DisplayName,
			hit.ContactID,
			hit.Bio,
			hit.MetFrom,
			hit.LastInteraction,
			hit.Subtitle,
			hit.Source,
			hit.RelationState,
		},
		query,
	)
	return matched
}

func highlightContactHit(hit ContactSearchHit, query string) string {
	if query == "" {
		return hit.DisplayName
	}
	_, highlight := containsQuery(
		[]string{
			hit.DisplayName,
			hit.Bio,
			hit.MetFrom,
			hit.LastInteraction,
			hit.Subtitle,
			hit.Source,
			hit.RelationState,
		},
		query,
	)
	if highlight == "" {
		highlight = hit.DisplayName
	}
	return highlight
}

func mergeRelationState(existing, next string) string {
	existing = normalizeRelationState(existing)
	next = normalizeRelationState(next)
	if existing == "mutual" || next == "mutual" {
		return "mutual"
	}
	if (existing == "following" && next == "followed_by") || (existing == "followed_by" && next == "following") {
		return "mutual"
	}
	if existing == "following" || next == "following" {
		return "following"
	}
	if existing == "followed_by" || next == "followed_by" {
		return "followed_by"
	}
	return "not_following"
}

func normalizeRelationState(raw string) string {
	switch strings.TrimSpace(raw) {
	case "self", "mutual", "following", "followed_by", "not_following":
		return strings.TrimSpace(raw)
	default:
		return "not_following"
	}
}

func normalizeContactSource(raw string) string {
	switch strings.TrimSpace(raw) {
	case "mutual", "following", "conversation", "contact_discovery", "circle", "group":
		return strings.TrimSpace(raw)
	default:
		return ""
	}
}

func contactSourcePriority(source string) int {
	switch normalizeContactSource(source) {
	case "conversation":
		return 0
	case "mutual":
		return 1
	case "following":
		return 2
	case "contact_discovery":
		return 3
	case "circle":
		return 4
	case "group":
		return 5
	default:
		return 6
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
