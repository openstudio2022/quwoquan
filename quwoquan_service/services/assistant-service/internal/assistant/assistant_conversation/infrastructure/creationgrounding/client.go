package creationgrounding

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/searchclient"
)

const getHomepageOperationID = "entity.homepage.GetHomepageDetail"

// Client 通过 search-service 与 entity-service 的正式 query operation 解析创作建议。
// 它不生成标签或主页；未命中时返回空集合。
type Client struct {
	search        *searchclient.Client
	entityBaseURL *url.URL
	entityHTTP    *http.Client
	homepagePath  string
}

type homepageWire struct {
	ID                string `json:"homepageId"`
	Title             string `json:"title"`
	HomepageType      string `json:"homepageType"`
	CanonicalEntityID string `json:"canonicalEntityId"`
	Status            string `json:"status"`
}

func New(
	search *searchclient.Client,
	entityBaseURL string,
	entityHTTP *http.Client,
) (*Client, error) {
	if search == nil {
		return nil, fmt.Errorf("creation grounding requires search client")
	}
	parsed, err := url.Parse(strings.TrimSpace(entityBaseURL))
	if err != nil {
		return nil, fmt.Errorf("parse entity-service base url: %w", err)
	}
	if parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("entity-service base url must be absolute")
	}
	if entityHTTP == nil {
		entityHTTP = &http.Client{Timeout: 3 * time.Second}
	}
	path, err := homepageOperationPath()
	if err != nil {
		return nil, err
	}
	return &Client{
		search:        search,
		entityBaseURL: parsed,
		entityHTTP:    entityHTTP,
		homepagePath:  path,
	}, nil
}

func (c *Client) ResolveTagRefs(ctx context.Context, hints []string) ([]string, error) {
	query := strings.Join(compactStrings(hints), " ")
	if query == "" {
		return []string{}, nil
	}
	response, err := c.search.Retrieve(
		ctx,
		query,
		[]string{"article", "photo", "video", "entity"},
		20,
	)
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	tagRefs := make([]string, 0)
	for _, hit := range response.Hits {
		for _, raw := range hit.MatchedTags {
			tagRef := strings.TrimSpace(raw)
			if tagRef == "" || seen[tagRef] {
				continue
			}
			seen[tagRef] = true
			tagRefs = append(tagRefs, tagRef)
			if len(tagRefs) == 8 {
				return tagRefs, nil
			}
		}
	}
	return tagRefs, nil
}

func (c *Client) ResolveHomepages(
	ctx context.Context,
	ids []string,
) ([]assistant.AssistantSuggestedHomepageView, error) {
	homepageIDs := compactStrings(ids)
	result := make([]assistant.AssistantSuggestedHomepageView, 0, len(homepageIDs))
	for _, homepageID := range homepageIDs {
		homepage, err := c.getHomepage(ctx, homepageID)
		if err != nil {
			return nil, err
		}
		if homepage.ID == "" || !strings.EqualFold(homepage.Status, "published") {
			continue
		}
		result = append(result, assistant.AssistantSuggestedHomepageView{
			ID:                homepage.ID,
			Type:              homepage.HomepageType,
			CanonicalEntityID: homepage.CanonicalEntityID,
			DisplayName:       homepage.Title,
			Reason:            "已作为主关联主页",
		})
	}
	return result, nil
}

func (c *Client) getHomepage(ctx context.Context, homepageID string) (homepageWire, error) {
	path := strings.ReplaceAll(c.homepagePath, "{homepageId}", url.PathEscape(homepageID))
	endpoint := c.entityBaseURL.ResolveReference(&url.URL{Path: path})
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return homepageWire{}, fmt.Errorf("build entity homepage request: %w", err)
	}
	response, err := c.entityHTTP.Do(request)
	if err != nil {
		return homepageWire{}, fmt.Errorf("call entity-service: %w", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 1<<20))
	if err != nil {
		return homepageWire{}, fmt.Errorf("read entity-service response: %w", err)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return homepageWire{}, fmt.Errorf(
			"entity-service status=%d body=%s",
			response.StatusCode,
			strings.TrimSpace(string(body)),
		)
	}
	var homepage homepageWire
	if err := json.Unmarshal(body, &homepage); err != nil {
		return homepageWire{}, fmt.Errorf("decode entity-service response: %w", err)
	}
	return homepage, nil
}

func homepageOperationPath() (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("entity") {
		if descriptor.CanonicalOperationID == getHomepageOperationID {
			return descriptor.PathTemplate, nil
		}
	}
	return "", fmt.Errorf("generated descriptor %q is missing", getHomepageOperationID)
}

func compactStrings(values []string) []string {
	seen := map[string]bool{}
	result := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	return result
}
