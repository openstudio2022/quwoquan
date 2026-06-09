package http

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/chat-service/internal/application"
)

type UserSocialContactResolver struct {
	baseURL string
	client  *http.Client
}

type socialContactPage struct {
	Items  []socialContactItem `json:"items"`
	Cursor string              `json:"cursor"`
}

type socialContactItem struct {
	SubAccountID  string `json:"subAccountId"`
	DisplayName   string `json:"displayName"`
	AvatarURL     string `json:"avatarUrl"`
	FollowedAt    string `json:"followedAt"`
	RelationState string `json:"relationState"`
}

type contactDiscoveryResponse struct {
	MatchedSubAccountIds []string   `json:"matchedSubAccountIds"`
	Status               string     `json:"status"`
	CreatedAt            time.Time  `json:"createdAt"`
	CompletedAt          *time.Time `json:"completedAt"`
}

func NewUserSocialContactResolver(baseURL string, client *http.Client) *UserSocialContactResolver {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &UserSocialContactResolver{baseURL: baseURL, client: client}
}

func (r *UserSocialContactResolver) ListContacts(
	ctx context.Context,
	userID string,
	limit int,
) ([]application.SocialContactSeed, error) {
	if r == nil || r.client == nil || r.baseURL == "" {
		return nil, nil
	}
	if limit <= 0 {
		limit = 20
	}

	merged := map[string]application.SocialContactSeed{}
	if err := r.collectFollowContacts(ctx, userID, "following", limit, merged); err != nil {
		return nil, err
	}
	if err := r.collectFollowContacts(ctx, userID, "followers", limit, merged); err != nil {
		return nil, err
	}
	if err := r.collectDiscoveryContacts(ctx, userID, merged); err != nil {
		return nil, err
	}

	out := make([]application.SocialContactSeed, 0, len(merged))
	for _, seed := range merged {
		out = append(out, seed)
	}
	sort.SliceStable(out, func(i, j int) bool {
		pi := socialContactPriority(out[i])
		pj := socialContactPriority(out[j])
		if pi != pj {
			return pi < pj
		}
		ti := out[i].LastInteraction
		tj := out[j].LastInteraction
		if ti != tj {
			return ti > tj
		}
		if out[i].DisplayName != out[j].DisplayName {
			return out[i].DisplayName < out[j].DisplayName
		}
		return out[i].UserID < out[j].UserID
	})
	if len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

func (r *UserSocialContactResolver) collectFollowContacts(
	ctx context.Context,
	userID string,
	mode string,
	limit int,
	merged map[string]application.SocialContactSeed,
) error {
	cursor := ""
	for len(merged) < limit {
		page, err := r.fetchFollowPage(ctx, userID, mode, cursor, limit)
		if err != nil {
			return err
		}
		if len(page.Items) == 0 {
			break
		}
		for _, item := range page.Items {
			id := strings.TrimSpace(item.SubAccountID)
			if id == "" {
				continue
			}
			seed := application.SocialContactSeed{
				UserID:          id,
				DisplayName:     strings.TrimSpace(item.DisplayName),
				AvatarURL:       strings.TrimSpace(item.AvatarURL),
				MetFrom:         "关注",
				LastInteraction: strings.TrimSpace(item.FollowedAt),
				RelationState:   normalizeSocialRelationState(item.RelationState),
				Source:          socialContactSource(item.RelationState),
			}
			mergeSocialContactSeed(merged, seed)
		}
		cursor = strings.TrimSpace(page.Cursor)
		if cursor == "" {
			break
		}
	}
	return nil
}

func (r *UserSocialContactResolver) fetchFollowPage(
	ctx context.Context,
	userID, mode, cursor string,
	limit int,
) (*socialContactPage, error) {
	path := fmt.Sprintf("%s/v1/user/sub-accounts/%s/%s", r.baseURL, url.PathEscape(userID), mode)
	reqURL, err := url.Parse(path)
	if err != nil {
		return nil, err
	}
	q := reqURL.Query()
	if cursor != "" {
		q.Set("cursor", cursor)
	}
	q.Set("limit", fmt.Sprintf("%d", limit))
	reqURL.RawQuery = q.Encode()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, reqURL.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Client-User-Id", strings.TrimSpace(userID))
	resp, err := r.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("list social contacts (%s): status %d", mode, resp.StatusCode)
	}
	var page socialContactPage
	if err := json.NewDecoder(resp.Body).Decode(&page); err != nil {
		return nil, err
	}
	return &page, nil
}

func (r *UserSocialContactResolver) collectDiscoveryContacts(
	ctx context.Context,
	userID string,
	merged map[string]application.SocialContactSeed,
) error {
	requestURL := fmt.Sprintf("%s/v1/user/contact-discovery/latest", r.baseURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("X-Client-User-Id", strings.TrimSpace(userID))
	resp, err := r.client.Do(req)
	if err != nil {
		// Contact discovery is best-effort; absence should not block contacts.
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("get latest contact discovery: status %d", resp.StatusCode)
	}
	var payload contactDiscoveryResponse
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return err
	}
	lastInteraction := ""
	if payload.CompletedAt != nil {
		lastInteraction = payload.CompletedAt.UTC().Format(time.RFC3339)
	} else if !payload.CreatedAt.IsZero() {
		lastInteraction = payload.CreatedAt.UTC().Format(time.RFC3339)
	}
	for _, rawID := range payload.MatchedSubAccountIds {
		id := strings.TrimSpace(rawID)
		if id == "" {
			continue
		}
		mergeSocialContactSeed(merged, application.SocialContactSeed{
			UserID:          id,
			MetFrom:         "通讯录匹配",
			LastInteraction: lastInteraction,
			RelationState:   "not_following",
			Source:          "contact_discovery",
		})
	}
	return nil
}

func mergeSocialContactSeed(
	merged map[string]application.SocialContactSeed,
	next application.SocialContactSeed,
) {
	id := strings.TrimSpace(next.UserID)
	if id == "" {
		return
	}
	next.UserID = id
	next.RelationState = normalizeSocialRelationState(next.RelationState)
	next.Source = normalizeSocialSource(next.Source)
	if next.Source == "" {
		next.Source = normalizeSocialSource(next.MetFrom)
	}
	if existing, ok := merged[id]; ok {
		merged[id] = mergeSocialContactSeedValues(existing, next)
		return
	}
	merged[id] = next
}

func mergeSocialContactSeedValues(
	base, next application.SocialContactSeed,
) application.SocialContactSeed {
	if strings.TrimSpace(base.DisplayName) == "" {
		base.DisplayName = next.DisplayName
	}
	if strings.TrimSpace(base.AvatarURL) == "" {
		base.AvatarURL = next.AvatarURL
	}
	if strings.TrimSpace(base.Bio) == "" {
		base.Bio = next.Bio
	}
	if strings.TrimSpace(base.MetFrom) == "" {
		base.MetFrom = next.MetFrom
	}
	if strings.TrimSpace(base.LastInteraction) == "" {
		base.LastInteraction = next.LastInteraction
	}
	if socialContactPriority(next) < socialContactPriority(base) {
		base.Source = next.Source
	}
	base.RelationState = mergeSocialRelationState(base.RelationState, next.RelationState)
	if base.RelationState == "mutual" {
		base.Source = "mutual"
	} else if base.Source == "" {
		base.Source = next.Source
	}
	return base
}

func mergeSocialRelationState(existing, next string) string {
	existing = normalizeSocialRelationState(existing)
	next = normalizeSocialRelationState(next)
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

func normalizeSocialRelationState(raw string) string {
	switch strings.TrimSpace(raw) {
	case "mutual", "following", "followed_by", "not_following":
		return strings.TrimSpace(raw)
	default:
		return "not_following"
	}
}

func normalizeSocialSource(raw string) string {
	switch strings.TrimSpace(raw) {
	case "mutual", "following", "conversation", "contact_discovery", "circle", "group":
		return strings.TrimSpace(raw)
	default:
		return ""
	}
}

func socialContactSource(relationState string) string {
	switch normalizeSocialRelationState(relationState) {
	case "mutual":
		return "mutual"
	case "following", "followed_by":
		return "following"
	default:
		return "contact_discovery"
	}
}

func socialContactPriority(seed application.SocialContactSeed) int {
	switch normalizeSocialSource(seed.Source) {
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
