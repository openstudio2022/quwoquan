package creatorsearch

import (
	"context"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	"time"
)

// 独立推荐owner query，不创建window/session，不复制或签发推荐准入。
type RecommendationProofClient struct {
	client     *Client
	baseURL    string
	credential auth.ServiceAuthorizationProvider
}

func NewRecommendationProofClient(client *Client, baseURL string, credential auth.ServiceAuthorizationProvider) *RecommendationProofClient {
	return &RecommendationProofClient{client, baseURL, credential}
}
func (c *RecommendationProofClient) ReadRecommendationProof(ctx context.Context, b rt.ReleaseQueryPreparationBinding, digest string) (rt.ReleaseQueryReadinessProof, error) {
	var proof rt.ReleaseQueryReadinessProof
	err := c.client.call(ctx, c.baseURL, "recommendation", "recommendation.ranked_recommendation_window.ReadRecommendationReleaseReadiness", c.credential, 2*time.Second, struct {
		Binding        rt.ReleaseQueryPreparationBinding `json:"binding"`
		SnapshotDigest string                            `json:"snapshotDigest"`
	}{b, digest}, &proof, "")
	return proof, err
}
