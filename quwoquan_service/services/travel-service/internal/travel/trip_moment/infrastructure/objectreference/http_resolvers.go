package objectreference

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"

	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/ports"
)

const maximumResponseBytes = 256 << 10

type AuthorizationProvider interface {
	AuthorizationHeader(context.Context) (string, error)
}

type ContentResolver struct {
	baseURL       *url.URL
	client        *http.Client
	authorization AuthorizationProvider
}

type HomepageResolver struct {
	baseURL *url.URL
	client  *http.Client
}

type mediaReference struct {
	AssetID          string `json:"assetId"`
	OwnerPersonaID   string `json:"ownerPersonaId"`
	ProcessingStatus string `json:"processingStatus"`
	MimeType         string `json:"mimeType"`
}

type publicPost struct {
	PostID     string `json:"postId"`
	Status     string `json:"status"`
	Visibility string `json:"visibility"`
}

type publicHomepage struct {
	HomepageID string `json:"homepageId"`
	Status     string `json:"status"`
}

func NewContentResolver(
	baseURL string,
	client *http.Client,
	authorization AuthorizationProvider,
) (*ContentResolver, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil {
		return nil, fmt.Errorf("invalid Content reference base URL")
	}
	if client == nil || authorization == nil {
		return nil, fmt.Errorf("Content reference client and authorization are required")
	}
	return &ContentResolver{baseURL: parsed, client: client, authorization: authorization}, nil
}

func NewHomepageResolver(baseURL string, client *http.Client) (*HomepageResolver, error) {
	parsed, err := parseBaseURL(baseURL)
	if err != nil {
		return nil, fmt.Errorf("invalid Entity public Homepage base URL")
	}
	if client == nil {
		return nil, fmt.Errorf("Entity public Homepage HTTP client is required")
	}
	return &HomepageResolver{baseURL: parsed, client: client}, nil
}

func (resolver *ContentResolver) ValidateObjectReference(
	ctx context.Context,
	ref model.ObjectRef,
	actorPersonaID string,
	kind model.Kind,
) error {
	switch strings.TrimSpace(ref.ObjectTypeRef) {
	case "content.MediaAsset":
		return resolver.validateMediaAsset(ctx, strings.TrimSpace(ref.ObjectID), strings.TrimSpace(actorPersonaID), kind)
	case "content.Post":
		return resolver.validatePublicPost(ctx, strings.TrimSpace(ref.ObjectID), kind)
	default:
		return model.ErrInvalidArgument
	}
}

func (resolver *ContentResolver) validateMediaAsset(
	ctx context.Context,
	assetID string,
	ownerPersonaID string,
	kind model.Kind,
) error {
	if resolver == nil || resolver.baseURL == nil || resolver.client == nil ||
		resolver.authorization == nil || assetID == "" || ownerPersonaID == "" {
		return ports.ErrReferenceUnavailable
	}
	expectedMIMEPrefix := ""
	switch kind {
	case model.KindPhoto:
		expectedMIMEPrefix = "image/"
	case model.KindVideo:
		expectedMIMEPrefix = "video/"
	case model.KindVoice:
		expectedMIMEPrefix = "audio/"
	default:
		return model.ErrInvalidArgument
	}
	referenceURL := resolver.baseURL.ResolveReference(&url.URL{
		Path: "internal/content/media/" + url.PathEscape(assetID) + ":reference",
	})
	query := referenceURL.Query()
	query.Set("ownerPersonaId", ownerPersonaID)
	referenceURL.RawQuery = query.Encode()
	authorization, err := resolver.authorization.AuthorizationHeader(ctx)
	if err != nil || strings.TrimSpace(authorization) == "" {
		return ports.ErrReferenceUnavailable
	}
	var result mediaReference
	if err := resolver.getJSON(ctx, referenceURL, authorization, &result); err != nil {
		return err
	}
	if strings.TrimSpace(result.AssetID) != assetID ||
		strings.TrimSpace(result.OwnerPersonaID) != ownerPersonaID ||
		strings.ToLower(strings.TrimSpace(result.ProcessingStatus)) != "ready" ||
		!strings.HasPrefix(strings.ToLower(strings.TrimSpace(result.MimeType)), expectedMIMEPrefix) {
		return ports.ErrReferenceUnavailable
	}
	return nil
}

func (resolver *ContentResolver) validatePublicPost(
	ctx context.Context,
	postID string,
	kind model.Kind,
) error {
	if resolver == nil || resolver.baseURL == nil || resolver.client == nil || postID == "" {
		return ports.ErrReferenceUnavailable
	}
	if kind != model.KindPostReference {
		return model.ErrInvalidArgument
	}
	postURL := resolver.baseURL.ResolveReference(&url.URL{
		Path: "content/posts/" + url.PathEscape(postID),
	})
	var result publicPost
	if err := resolver.getJSON(ctx, postURL, "", &result); err != nil {
		return err
	}
	if strings.TrimSpace(result.PostID) != postID ||
		strings.ToLower(strings.TrimSpace(result.Status)) != "published" ||
		strings.ToLower(strings.TrimSpace(result.Visibility)) != "public" {
		return ports.ErrReferenceUnavailable
	}
	return nil
}

func (resolver *HomepageResolver) ValidateObjectReference(
	ctx context.Context,
	ref model.ObjectRef,
	_ string,
	_ model.Kind,
) error {
	homepageID := strings.TrimSpace(ref.ObjectID)
	if resolver == nil || resolver.baseURL == nil || resolver.client == nil ||
		strings.TrimSpace(ref.ObjectTypeRef) != "entity.Homepage" || homepageID == "" {
		return ports.ErrReferenceUnavailable
	}
	homepageURL := resolver.baseURL.ResolveReference(&url.URL{
		Path: "homepages/" + url.PathEscape(homepageID),
	})
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, homepageURL.String(), nil)
	if err != nil {
		return ports.ErrReferenceUnavailable
	}
	request.Header.Set("Accept", "application/json")
	response, err := resolver.client.Do(request)
	if err != nil {
		return ports.ErrReferenceUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return ports.ErrReferenceUnavailable
	}
	var result publicHomepage
	if err := decodeBoundedJSONFromResponse(response, &result); err != nil {
		return ports.ErrReferenceUnavailable
	}
	if strings.TrimSpace(result.HomepageID) != homepageID ||
		strings.ToLower(strings.TrimSpace(result.Status)) != "published" {
		return ports.ErrReferenceUnavailable
	}
	return nil
}

func (resolver *ContentResolver) getJSON(
	ctx context.Context,
	target *url.URL,
	authorization string,
	destination any,
) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return ports.ErrReferenceUnavailable
	}
	request.Header.Set("Accept", "application/json")
	if strings.TrimSpace(authorization) != "" {
		request.Header.Set("Authorization", authorization)
	}
	response, err := resolver.client.Do(request)
	if err != nil {
		return ports.ErrReferenceUnavailable
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return ports.ErrReferenceUnavailable
	}
	if err := decodeBoundedJSONFromResponse(response, destination); err != nil {
		return ports.ErrReferenceUnavailable
	}
	return nil
}

func decodeBoundedJSONFromResponse(response *http.Response, destination any) error {
	return decodeBoundedJSON(response.Body, destination)
}

func decodeBoundedJSON(reader io.Reader, destination any) error {
	body, err := io.ReadAll(io.LimitReader(reader, maximumResponseBytes+1))
	if err != nil || len(body) == 0 || len(body) > maximumResponseBytes {
		return fmt.Errorf("invalid bounded response")
	}
	if err := json.Unmarshal(body, destination); err != nil {
		return fmt.Errorf("invalid JSON response")
	}
	return nil
}

func parseBaseURL(raw string) (*url.URL, error) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || parsed == nil || parsed.Host == "" ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.User != nil ||
		parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("invalid base URL")
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/"
	return parsed, nil
}
