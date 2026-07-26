package external

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

type MediaAssetDeliveryReader struct {
	baseURL     *url.URL
	credentials rtauth.ServiceAuthorizationProvider
	client      *http.Client
}

func NewMediaAssetDeliveryReader(
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	client *http.Client,
) (*MediaAssetDeliveryReader, error) {
	baseURL, err := url.Parse(strings.TrimSpace(rawBaseURL))
	if err != nil || baseURL.Scheme == "" || baseURL.Host == "" ||
		(baseURL.Scheme != "http" && baseURL.Scheme != "https") ||
		baseURL.User != nil || baseURL.RawQuery != "" || baseURL.Fragment != "" {
		return nil, fmt.Errorf("CONTENT_SERVICE_BASE_URL must be an absolute http(s) origin")
	}
	if credentials == nil {
		return nil, fmt.Errorf("content-service delivery credentials are required")
	}
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &MediaAssetDeliveryReader{
		baseURL: baseURL, credentials: credentials, client: client,
	}, nil
}

func (reader *MediaAssetDeliveryReader) ReadOwnedReadyAsset(
	ctx context.Context,
	assetID string,
	ownerPersonaID string,
) (messageports.MediaAssetDeliverySlice, bool, error) {
	assetID, ownerPersonaID = strings.TrimSpace(assetID), strings.TrimSpace(ownerPersonaID)
	if assetID == "" || ownerPersonaID == "" {
		return messageports.MediaAssetDeliverySlice{}, false, fmt.Errorf("assetID and ownerPersonaID are required")
	}
	endpoint := *reader.baseURL
	endpoint.Path = strings.TrimRight(endpoint.Path, "/") + "/internal/content/media/" +
		url.PathEscape(assetID) + ":delivery-reference"
	query := endpoint.Query()
	query.Set("ownerPersonaId", ownerPersonaID)
	endpoint.RawQuery = query.Encode()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return messageports.MediaAssetDeliverySlice{}, false, err
	}
	authorization, err := reader.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return messageports.MediaAssetDeliverySlice{}, false, fmt.Errorf("issue content-service credential: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := reader.client.Do(request)
	if err != nil {
		return messageports.MediaAssetDeliverySlice{}, false, err
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotFound || response.StatusCode == http.StatusForbidden {
		return messageports.MediaAssetDeliverySlice{}, false, nil
	}
	if response.StatusCode != http.StatusOK {
		return messageports.MediaAssetDeliverySlice{}, false, decodeRuntimeFailure(response)
	}
	var payload struct {
		AssetID          string `json:"assetId"`
		OwnerPersonaID   string `json:"ownerPersonaId"`
		ProcessingStatus string `json:"processingStatus"`
		MediaType        string `json:"mediaType"`
		ContentType      string `json:"contentType"`
		FileSize         int64  `json:"fileSize"`
		DeliveryURL      string `json:"cdnUrl"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return messageports.MediaAssetDeliverySlice{}, false, fmt.Errorf("decode content-service MediaAsset delivery reference: %w", err)
	}
	if payload.AssetID != assetID || payload.OwnerPersonaID != ownerPersonaID ||
		payload.ProcessingStatus != "ready" || strings.TrimSpace(payload.MediaType) == "" ||
		strings.TrimSpace(payload.ContentType) == "" || payload.FileSize <= 0 ||
		strings.TrimSpace(payload.DeliveryURL) == "" {
		return messageports.MediaAssetDeliverySlice{}, false, fmt.Errorf("content-service MediaAsset delivery identity is invalid")
	}
	return messageports.MediaAssetDeliverySlice{
		AssetID: payload.AssetID, OwnerPersonaID: payload.OwnerPersonaID,
		ProcessingStatus: payload.ProcessingStatus, MediaType: payload.MediaType,
		ContentType: payload.ContentType, FileSize: payload.FileSize,
		DeliveryURL: payload.DeliveryURL,
	}, true, nil
}

func decodeRuntimeFailure(response *http.Response) error {
	var failure rterr.ErrorResponse
	decoder := json.NewDecoder(io.LimitReader(response.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&failure); err != nil {
		return fmt.Errorf("content-service MediaAsset reader returned %d with invalid RuntimeFailure: %w", response.StatusCode, err)
	}
	code, err := rterr.ParseCode(failure.Code)
	if err != nil {
		return fmt.Errorf("content-service MediaAsset reader returned invalid error code: %w", err)
	}
	return rterr.NewAppError(code, failure.UserMessage, failure.DebugMessage).
		WithRecovery(failure.Recovery.Action, failure.Recovery.AfterSeconds)
}

var _ messageports.MediaAssetDeliveryReader = (*MediaAssetDeliveryReader)(nil)
