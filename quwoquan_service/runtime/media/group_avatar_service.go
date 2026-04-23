package runtimemedia

import (
	"context"
	"encoding/json"
	"fmt"
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
	ConversationID string
	SourceHash     string
	LayoutVersion  string
	Contributors   []AvatarSource
}

type GroupAvatarService struct {
	client    rtredis.Client
	cdnDomain string
}

func NewGroupAvatarService(client rtredis.Client, cdnDomain string) *GroupAvatarService {
	return &GroupAvatarService{
		client:    client,
		cdnDomain: strings.TrimSpace(cdnDomain),
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
		s.cdnDomain,
	)
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
