package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/application"
)

type TagServiceProfileTagValidator struct {
	baseURL string
	client  *http.Client
}

func NewTagServiceProfileTagValidator(baseURL string, client *http.Client) *TagServiceProfileTagValidator {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &TagServiceProfileTagValidator{baseURL: baseURL, client: client}
}

func (v *TagServiceProfileTagValidator) ValidateProfileTags(ctx context.Context, occupationTagRef string, interestTagRefs []string) error {
	if err := (application.PathProfileTagValidator{}).ValidateProfileTags(ctx, occupationTagRef, interestTagRefs); err != nil {
		return err
	}
	if v == nil || v.baseURL == "" {
		return nil
	}
	tagRefs := make([]string, 0, len(interestTagRefs)+1)
	if occupation := strings.TrimSpace(occupationTagRef); occupation != "" {
		tagRefs = append(tagRefs, occupation)
	}
	for _, tagRef := range interestTagRefs {
		if trimmed := strings.TrimSpace(tagRef); trimmed != "" {
			tagRefs = append(tagRefs, trimmed)
		}
	}
	if len(tagRefs) == 0 {
		return nil
	}
	body, err := json.Marshal(map[string]any{"tagRefs": tagRefs})
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, v.baseURL+"/tag/validate", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Service", "user-service")

	resp, err := v.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("tag-service validate refs: status %d", resp.StatusCode)
	}
	var result struct {
		Invalid []string `json:"invalid"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return err
	}
	if len(result.Invalid) > 0 {
		return fmt.Errorf("invalid profile tag refs: %s", strings.Join(result.Invalid, ","))
	}
	return nil
}

var _ application.ProfileTagValidator = (*TagServiceProfileTagValidator)(nil)
