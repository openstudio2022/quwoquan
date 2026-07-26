package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
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

func (v *TagServiceProfileTagValidator) ValidateProfileTags(
	ctx context.Context,
	expectedTaxonomyReleaseID string,
	occupationTagRef string,
	interestTagRefs []string,
) error {
	if err := (application.PathProfileTagValidator{}).ValidateProfileTags(
		ctx,
		expectedTaxonomyReleaseID,
		occupationTagRef,
		interestTagRefs,
	); err != nil {
		return err
	}
	if v == nil || v.baseURL == "" {
		return fmt.Errorf("tag-service validator is unavailable")
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
	body, err := json.Marshal(struct {
		ExpectedTaxonomyReleaseID string   `json:"expectedTaxonomyReleaseId"`
		TagRefs                   []string `json:"tagRefs"`
	}{
		ExpectedTaxonomyReleaseID: strings.TrimSpace(expectedTaxonomyReleaseID),
		TagRefs:                   tagRefs,
	})
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
		TaxonomyReleaseID string   `json:"taxonomyReleaseId"`
		Invalid           []string `json:"invalid"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return err
	}
	if strings.TrimSpace(result.TaxonomyReleaseID) == "" {
		return fmt.Errorf("tag-service validate refs response missing taxonomyReleaseId")
	}
	if result.TaxonomyReleaseID != strings.TrimSpace(expectedTaxonomyReleaseID) {
		return fmt.Errorf(
			"%w: expected %s, active %s",
			application.ErrProfileTaxonomyReleaseConflict,
			strings.TrimSpace(expectedTaxonomyReleaseID),
			result.TaxonomyReleaseID,
		)
	}
	if len(result.Invalid) > 0 {
		return fmt.Errorf("invalid profile tag refs: %s", strings.Join(result.Invalid, ","))
	}
	return nil
}

var _ application.ProfileTagValidator = (*TagServiceProfileTagValidator)(nil)
