package contentsource

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	rt "quwoquan_service/runtime/search"
	generated "quwoquan_service/services/product-ops-service/generated/product_ops/premium_pool_entry/contract/model"
	"strings"
	"time"
)

// Reader只调用Content公开候选query；签名credential由composition注入，不跨库。
type Reader struct {
	Endpoint   string
	Client     *http.Client
	Credential func(context.Context) (string, error)
}

func (r *Reader) VerifyCandidateSource(ctx context.Context, source generated.ReleaseCandidateObjectIdentity) error {
	if r == nil || r.Client == nil || r.Credential == nil || strings.TrimSpace(r.Endpoint) == "" {
		return fmt.Errorf("Content candidate source reader unavailable")
	}
	ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	raw, _ := json.Marshal(map[string]any{"release": source.Release})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(r.Endpoint, "/")+"/internal/content/release-candidates:query", bytes.NewReader(raw))
	if err != nil {
		return err
	}
	token, err := r.Credential(ctx)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	response, err := r.Client.Do(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("Content candidate query status %d", response.StatusCode)
	}
	var snapshot rt.ReleasePostCandidateSnapshot
	if err := rt.DecodeCreatorValue(response.Body, &snapshot); err != nil {
		return err
	}
	if err := snapshot.Validate(); err != nil {
		return err
	}
	for _, post := range snapshot.Posts {
		encoded, _ := json.Marshal(post.Identity)
		var actual generated.ReleaseCandidateObjectIdentity
		if json.Unmarshal(encoded, &actual) != nil {
			return fmt.Errorf("candidate identity decode failed")
		}
		if actual == source {
			return nil
		}
	}
	return fmt.Errorf("Content candidate exact source/version/digest mismatch")
}
