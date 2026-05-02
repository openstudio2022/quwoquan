package runtimemedia

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

type DerivedAvatarAsset struct {
	Ref           AssetRef       `json:"ref"`
	SourceHash    string         `json:"sourceHash"`
	LayoutVersion string         `json:"layoutVersion"`
	Contributors  []AvatarSource `json:"contributors"`
	CreatedAt     time.Time      `json:"createdAt"`
	UpdatedAt     time.Time      `json:"updatedAt"`
}

type AvatarSource struct {
	UserID        string `json:"userId"`
	AvatarAssetID string `json:"avatarAssetId"`
	AvatarVersion int64  `json:"avatarVersion"`
}

type RegisterGroupAvatarRequest struct {
	ConversationID   string
	SourceHash       string
	LayoutVersion    string
	Contributors     []AvatarSource
	MemberAvatarURLs []string
}

type GroupAvatarService struct {
	client         rtredis.Client
	cdnBaseURL     string
	localMediaRoot string
	httpClient     *http.Client
}

func NewGroupAvatarService(client rtredis.Client, cdnBaseURL, localMediaRoot string) *GroupAvatarService {
	return &GroupAvatarService{
		client:         client,
		cdnBaseURL:     NormalizeMediaCDNBase(cdnBaseURL),
		localMediaRoot: strings.TrimSpace(localMediaRoot),
		httpClient:     DefaultGroupAvatarHTTPClient(),
	}
}

func (s *GroupAvatarService) Register(
	ctx context.Context,
	req RegisterGroupAvatarRequest,
) (DerivedAvatarAsset, error) {
	if s == nil || s.client == nil {
		return DerivedAvatarAsset{}, fmt.Errorf("group avatar service is not configured")
	}
	conversationID := strings.TrimSpace(req.ConversationID)
	sourceHash := strings.TrimSpace(req.SourceHash)
	if conversationID == "" {
		return DerivedAvatarAsset{}, fmt.Errorf("conversationId is required")
	}
	if sourceHash == "" {
		return DerivedAvatarAsset{}, fmt.Errorf("sourceHash is required")
	}
	if len(req.Contributors) == 0 {
		return DerivedAvatarAsset{}, fmt.Errorf("contributors are required")
	}
	if strings.TrimSpace(s.cdnBaseURL) == "" {
		return DerivedAvatarAsset{}, fmt.Errorf("group avatar CDN base URL is not configured")
	}
	if !strings.Contains(s.cdnBaseURL, "://") {
		return DerivedAvatarAsset{}, fmt.Errorf("group avatar CDN base URL must include scheme")
	}
	if strings.TrimSpace(s.localMediaRoot) == "" {
		return DerivedAvatarAsset{}, fmt.Errorf("group avatar local media root is not configured")
	}

	lockKey := fmt.Sprintf("runtime:media:group-avatar:lock:%s", conversationID)
	acquired := false
	for i := 0; i < 20; i++ {
		ok, err := s.client.SetNX(ctx, lockKey, sourceHash, 2*time.Second)
		if err != nil {
			return DerivedAvatarAsset{}, fmt.Errorf("acquire group avatar lock: %w", err)
		}
		if ok {
			acquired = true
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if !acquired {
		return DerivedAvatarAsset{}, fmt.Errorf("group avatar register busy for %s", conversationID)
	}
	defer func() {
		_ = s.client.Del(ctx, lockKey)
	}()

	stateKey := fmt.Sprintf("runtime:media:group-avatar:%s", conversationID)
	state, _ := s.client.HGetAll(ctx, stateKey)
	if strings.TrimSpace(state["sourceHash"]) == sourceHash {
		version := parseInt64(state["version"])
		if version > 0 && strings.TrimSpace(state["assetId"]) != "" {
			return s.readAsset(ctx, conversationID, state["assetId"])
		}
	}

	nextVersion := parseInt64(state["version"]) + 1
	if nextVersion <= 0 {
		nextVersion = 1
	}
	assetID := fmt.Sprintf("ga_%s_v%d", conversationID, nextVersion)
	ref := BuildAvatarGroupAssetRef(
		conversationID,
		assetID,
		nextVersion,
		sourceHash,
		s.cdnBaseURL,
	)
	if strings.TrimSpace(ref.URL) == "" {
		return DerivedAvatarAsset{}, fmt.Errorf("derived group avatar public URL is empty")
	}

	urls := alignMemberAvatarURLs(req.MemberAvatarURLs, len(req.Contributors))
	pngBytes, err := RenderGroupAvatarPNG(ctx, s.httpClient, urls, groupAvatarCanvasSize)
	if err != nil {
		return DerivedAvatarAsset{}, fmt.Errorf("render group avatar: %w", err)
	}
	if err := WriteDerivedMediaFile(s.localMediaRoot, ref.ObjectKey, pngBytes); err != nil {
		return DerivedAvatarAsset{}, fmt.Errorf("persist group avatar png: %w", err)
	}

	now := time.Now().UTC()
	asset := DerivedAvatarAsset{
		Ref:           ref,
		SourceHash:    sourceHash,
		LayoutVersion: defaultLayoutVersion(req.LayoutVersion),
		Contributors:  append([]AvatarSource(nil), req.Contributors...),
		CreatedAt:     now,
		UpdatedAt:     now,
	}
	body, err := json.Marshal(asset)
	if err != nil {
		return DerivedAvatarAsset{}, fmt.Errorf("marshal media asset: %w", err)
	}
	assetKey := fmt.Sprintf("runtime:media:asset:%s", assetID)
	if err := s.client.SetBytes(ctx, assetKey, body, 0); err != nil {
		return DerivedAvatarAsset{}, fmt.Errorf("store media asset: %w", err)
	}
	if err := s.client.HSet(ctx, stateKey, "assetId", assetID); err != nil {
		return DerivedAvatarAsset{}, err
	}
	if err := s.client.HSet(ctx, stateKey, "version", fmt.Sprintf("%d", nextVersion)); err != nil {
		return DerivedAvatarAsset{}, err
	}
	if err := s.client.HSet(ctx, stateKey, "sourceHash", sourceHash); err != nil {
		return DerivedAvatarAsset{}, err
	}
	if err := s.client.HSet(ctx, stateKey, "objectKey", ref.ObjectKey); err != nil {
		return DerivedAvatarAsset{}, err
	}
	if err := s.client.HSet(ctx, stateKey, "updatedAt", now.Format(time.RFC3339Nano)); err != nil {
		return DerivedAvatarAsset{}, err
	}
	return asset, nil
}

func alignMemberAvatarURLs(urls []string, n int) []string {
	out := make([]string, 0, n)
	for i := 0; i < n; i++ {
		if i < len(urls) {
			out = append(out, urls[i])
		} else {
			out = append(out, "")
		}
	}
	return out
}

func (s *GroupAvatarService) readAsset(
	ctx context.Context,
	conversationID string,
	assetID string,
) (DerivedAvatarAsset, error) {
	raw, err := s.client.GetBytes(ctx, fmt.Sprintf("runtime:media:asset:%s", strings.TrimSpace(assetID)))
	if err != nil {
		return DerivedAvatarAsset{}, fmt.Errorf("read media asset %s for %s: %w", assetID, conversationID, err)
	}
	var asset DerivedAvatarAsset
	if err := json.Unmarshal(raw, &asset); err != nil {
		return DerivedAvatarAsset{}, fmt.Errorf("decode media asset %s: %w", assetID, err)
	}
	return asset, nil
}

func parseInt64(raw string) int64 {
	var value int64
	_, _ = fmt.Sscanf(strings.TrimSpace(raw), "%d", &value)
	return value
}

func defaultLayoutVersion(raw string) string {
	if strings.TrimSpace(raw) == "" {
		return "v1"
	}
	return strings.TrimSpace(raw)
}
