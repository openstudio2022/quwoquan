package integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"

	followingapp "quwoquan_service/services/user-service/internal/profile_projection/following_subject/application"
)

// EntityHomepageDisplayClient 消费 entity-service 的公开只读主页壳层合同，
// 为 following_subjects 投影的 homepage 行提供展示信息。它是防腐适配器：
// 解析失败由调用方降级为标识占位，不阻塞关注频道列表。
type EntityHomepageDisplayClient struct {
	baseURL string
	client  *http.Client
}

var _ followingapp.SubjectDisplayResolver = (*EntityHomepageDisplayClient)(nil)

func NewEntityHomepageDisplayClient(baseURL string, client *http.Client) *EntityHomepageDisplayClient {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &EntityHomepageDisplayClient{baseURL: baseURL, client: client}
}

type homepageShellEnvelope struct {
	Name        string `json:"name"`
	DisplayName string `json:"displayName"`
	AvatarURL   string `json:"avatarUrl"`
	CoverURL    string `json:"coverUrl"`
	Category    string `json:"category"`
	City        string `json:"city"`
}

func (c *EntityHomepageDisplayClient) ResolveHomepages(
	ctx context.Context,
	homepageIDs []string,
) (map[string]followingapp.SubjectDisplay, error) {
	if c == nil || c.baseURL == "" {
		return nil, fmt.Errorf("entity homepage display client unavailable")
	}
	result := make(map[string]followingapp.SubjectDisplay, len(homepageIDs))
	for _, homepageID := range homepageIDs {
		homepageID = strings.TrimSpace(homepageID)
		if homepageID == "" {
			continue
		}
		display, err := c.resolveOne(ctx, homepageID)
		if err != nil {
			// 单个主页解析失败不放弃整批；缺失行由调用方占位。
			continue
		}
		result[homepageID] = display
	}
	return result, nil
}

func (c *EntityHomepageDisplayClient) resolveOne(
	ctx context.Context,
	homepageID string,
) (followingapp.SubjectDisplay, error) {
	endpoint := c.baseURL + "/homepages/" + url.PathEscape(homepageID) + "/shell"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return followingapp.SubjectDisplay{}, err
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return followingapp.SubjectDisplay{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return followingapp.SubjectDisplay{}, fmt.Errorf("homepage shell status %d", resp.StatusCode)
	}
	var envelope homepageShellEnvelope
	if err := json.NewDecoder(resp.Body).Decode(&envelope); err != nil {
		return followingapp.SubjectDisplay{}, err
	}
	displayName := envelope.DisplayName
	if displayName == "" {
		displayName = envelope.Name
	}
	subtitle := envelope.Category
	if subtitle == "" {
		subtitle = envelope.City
	}
	return followingapp.SubjectDisplay{
		DisplayName: displayName,
		AvatarURL:   envelope.AvatarURL,
		CoverURL:    envelope.CoverURL,
		Subtitle:    subtitle,
	}, nil
}
