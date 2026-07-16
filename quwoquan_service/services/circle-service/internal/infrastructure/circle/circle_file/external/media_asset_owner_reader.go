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
	fileports "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/ports"
)

type MediaAssetOwnerReader struct {
	baseURL     *url.URL
	credentials rtauth.ServiceAuthorizationProvider
	client      *http.Client
}

func NewMediaAssetOwnerReader(
	rawBaseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
	client *http.Client,
) (*MediaAssetOwnerReader, error) {
	baseURL, err := url.Parse(strings.TrimSpace(rawBaseURL))
	if err != nil || baseURL.Scheme == "" || baseURL.Host == "" ||
		(baseURL.Scheme != "http" && baseURL.Scheme != "https") {
		return nil, fmt.Errorf("CONTENT_SERVICE_BASE_URL must be an absolute http(s) URL")
	}
	if credentials == nil {
		return nil, fmt.Errorf("content-service credentials are required")
	}
	if client == nil {
		client = &http.Client{Timeout: 2 * time.Second}
	}
	return &MediaAssetOwnerReader{baseURL: baseURL, credentials: credentials, client: client}, nil
}

func (reader *MediaAssetOwnerReader) ReadOwnedReadyAsset(ctx context.Context, assetID, ownerPersonaID string) (fileports.MediaAssetOwnerSlice, bool, error) {
	assetID, ownerPersonaID = strings.TrimSpace(assetID), strings.TrimSpace(ownerPersonaID)
	if assetID == "" || ownerPersonaID == "" {
		return fileports.MediaAssetOwnerSlice{}, false, fmt.Errorf("assetID and ownerPersonaID are required")
	}
	endpoint := *reader.baseURL
	endpoint.Path = strings.TrimRight(endpoint.Path, "/") + "/internal/v1/content/media/" + url.PathEscape(assetID) + ":reference"
	query := endpoint.Query()
	query.Set("ownerPersonaId", ownerPersonaID)
	endpoint.RawQuery = query.Encode()
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return fileports.MediaAssetOwnerSlice{}, false, err
	}
	authorization, err := reader.credentials.AuthorizationHeader(ctx)
	if err != nil {
		return fileports.MediaAssetOwnerSlice{}, false, fmt.Errorf("issue content-service credential: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := reader.client.Do(request)
	if err != nil {
		return fileports.MediaAssetOwnerSlice{}, false, err
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusNotFound || response.StatusCode == http.StatusForbidden {
		return fileports.MediaAssetOwnerSlice{}, false, nil
	}
	if response.StatusCode != http.StatusOK {
		var failure rterr.ErrorResponse
		decoder := json.NewDecoder(io.LimitReader(response.Body, 1<<20))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&failure); err != nil {
			return fileports.MediaAssetOwnerSlice{}, false, fmt.Errorf(
				"content-service MediaAsset reader returned %d with invalid RuntimeFailure: %w",
				response.StatusCode, err,
			)
		}
		code, err := rterr.ParseCode(failure.Code)
		if err != nil {
			return fileports.MediaAssetOwnerSlice{}, false, fmt.Errorf(
				"content-service MediaAsset reader returned invalid error code: %w", err,
			)
		}
		return fileports.MediaAssetOwnerSlice{}, false,
			rterr.NewAppError(code, failure.UserMessage, failure.DebugMessage).
				WithRecovery(failure.Recovery.Action, failure.Recovery.AfterSeconds)
	}
	var payload struct {
		AssetID          string `json:"assetId"`
		OwnerPersonaID   string `json:"ownerPersonaId"`
		ProcessingStatus string `json:"processingStatus"`
		ContentType      string `json:"contentType"`
		FileSize         int64  `json:"fileSize"`
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&payload); err != nil {
		return fileports.MediaAssetOwnerSlice{}, false, fmt.Errorf("decode content-service MediaAsset reference: %w", err)
	}
	if payload.AssetID != assetID || payload.OwnerPersonaID != ownerPersonaID ||
		payload.ProcessingStatus != "ready" || strings.TrimSpace(payload.ContentType) == "" || payload.FileSize <= 0 {
		return fileports.MediaAssetOwnerSlice{}, false, fmt.Errorf("content-service MediaAsset reference identity is invalid")
	}
	return fileports.MediaAssetOwnerSlice{
		AssetID: payload.AssetID, OwnerPersonaID: payload.OwnerPersonaID,
		ProcessingStatus: payload.ProcessingStatus, ContentType: payload.ContentType,
		FileSize: payload.FileSize,
	}, true, nil
}

var _ fileports.MediaAssetOwnerReader = (*MediaAssetOwnerReader)(nil)
