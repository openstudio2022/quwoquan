package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

func (h *ContentHandler) handleInitMediaUpload(w http.ResponseWriter, r *http.Request) {
	var body struct {
		MediaType      string `json:"mediaType"`
		ContentType    string `json:"contentType"`
		FileSize       int64  `json:"fileSize"`
		ExpectedSHA256 string `json:"expectedSha256"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if h.mediaService == nil {
		writeHTTPError(w, r, rterr.NewUnavailable(rterr.ModuleContent, "媒体服务未配置", "Media Facade is required"))
		return
	}
	result, err := h.mediaService.InitMediaUpload(r.Context(), mediaapp.InitMediaUploadCommand{
		OwnerID: operationActorID(r), MediaType: body.MediaType, ContentType: body.ContentType,
		FileSize: body.FileSize, ExpectedSHA256: body.ExpectedSHA256,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaUploadSessionResponse{
		SessionID: result.SessionID, Status: string(result.Status), ObjectKey: result.ObjectKey,
		UploadURL: result.UploadURL, PresignURL: result.UploadURL, ExpiresAt: result.ExpiresAt,
		Replayed: result.Replayed,
	})
}

func (h *ContentHandler) handleCompleteMediaUpload(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/content/media/uploads/", ":complete")
	if h.mediaService == nil {
		writeHTTPError(w, r, rterr.NewUnavailable(rterr.ModuleContent, "媒体服务未配置", "Media Facade is required"))
		return
	}
	var body struct {
		AccessPolicy mediamodel.AccessPolicy `json:"accessPolicy"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if body.AccessPolicy == "" {
		body.AccessPolicy = mediamodel.AccessPolicyOwnerOnly
	}
	result, err := h.mediaService.CompleteMediaUpload(r.Context(), mediaapp.CompleteMediaUploadCommand{
		SessionID: sessionID, OwnerID: operationActorID(r), AccessPolicy: body.AccessPolicy,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaUploadSessionResponse{
		SessionID: result.SessionID, AssetID: result.AssetID, Status: string(result.Status),
		ObjectKey: result.ObjectKey, CDNURL: result.DeliveryURL, ExpiresAt: result.ExpiresAt,
		Replayed: result.Replayed,
	})
}

func (h *ContentHandler) handleAbortMediaUpload(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/content/media/uploads/", ":abort")
	if h.mediaService == nil {
		writeHTTPError(w, r, rterr.NewUnavailable(rterr.ModuleContent, "媒体服务未配置", "Media Facade is required"))
		return
	}
	result, err := h.mediaService.AbortMediaUpload(r.Context(), mediaapp.AbortMediaUploadCommand{
		SessionID: sessionID, OwnerID: operationActorID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaUploadSessionResponse{
		SessionID: result.SessionID, Status: string(result.Status), ObjectKey: result.ObjectKey,
		ExpiresAt: result.ExpiresAt, Replayed: result.Replayed,
	})
}

func (h *ContentHandler) handleGetMediaAsset(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/content/media/", "")
	if idx := strings.Index(mediaID, "/"); idx > 0 {
		mediaID = mediaID[:idx]
	}
	if h.mediaService == nil {
		writeHTTPError(w, r, rterr.NewUnavailable(rterr.ModuleContent, "媒体服务未配置", "Media Facade is required"))
		return
	}
	asset, err := h.mediaService.GetPublicMediaAsset(r.Context(), mediaapp.GetPublicMediaAssetQuery{AssetID: mediaID})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaAssetHTTPResponseFromSlice(asset))
}

func (h *ContentHandler) handleGetOwnedMediaAsset(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/internal/content/media/", "")
	asset, err := h.mediaService.GetMediaAsset(r.Context(), mediaapp.GetMediaAssetQuery{AssetID: mediaID, OwnerID: operationActorID(r)})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaAssetHTTPResponseFromSlice(asset))
}

func (h *ContentHandler) handleGetMediaAssetReference(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/internal/content/media/", ":reference")
	ownerPersonaID := strings.TrimSpace(r.URL.Query().Get("ownerPersonaId"))
	if mediaID == "" || ownerPersonaID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求参数无效", "mediaId and ownerPersonaId are required"))
		return
	}
	asset, err := h.mediaService.GetOwnedReadyMediaAssetReference(r.Context(), mediaapp.GetMediaAssetQuery{
		AssetID: mediaID, OwnerID: ownerPersonaID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleGetMediaAssetDeliveryReference(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/internal/content/media/", ":delivery-reference")
	ownerPersonaID := strings.TrimSpace(r.URL.Query().Get("ownerPersonaId"))
	if mediaID == "" || ownerPersonaID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求参数无效", "mediaId and ownerPersonaId are required"))
		return
	}
	asset, err := h.mediaService.GetOwnedReadyMediaAssetDeliveryReference(r.Context(), mediaapp.GetMediaAssetQuery{
		AssetID: mediaID, OwnerID: ownerPersonaID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *ContentHandler) handleGetMediaUploadSession(w http.ResponseWriter, r *http.Request) {
	sessionID := pathParamAfter(r.URL.Path, "/content/media/uploads/", "")
	session, err := h.mediaService.GetMediaUploadSession(r.Context(), mediaapp.GetMediaUploadSessionQuery{SessionID: sessionID, OwnerID: operationActorID(r)})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *ContentHandler) handleRecordMediaProcessingResult(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/internal/content/media/", ":processing-result")
	var body struct {
		Processing                   mediamodel.ProcessingStatus `json:"processingStatus"`
		FailureReason                string                      `json:"failureReason"`
		ProcessorProfile             string                      `json:"processorProfile"`
		ImageWidth                   int                         `json:"imageWidth"`
		ImageHeight                  int                         `json:"imageHeight"`
		ImageDeliveryContentType     string                      `json:"imageDeliveryContentType"`
		ImageNormalizedObjectKey     string                      `json:"imageNormalizedObjectKey"`
		ImagePublicSliceKey          string                      `json:"imagePublicSliceKey"`
		VerifiedDurationMs           int64                       `json:"verifiedDurationMs"`
		VideoWidth                   int                         `json:"videoWidth"`
		VideoHeight                  int                         `json:"videoHeight"`
		VideoCodec                   string                      `json:"videoCodec"`
		VideoContainer               string                      `json:"videoContainer"`
		VideoAudioCodec              string                      `json:"videoAudioCodec"`
		VideoKeyframeIntervalMs      int                         `json:"videoKeyframeIntervalMs"`
		VideoFastStart               bool                        `json:"videoFastStart"`
		VideoPublicSliceKey          string                      `json:"videoPublicSliceKey"`
		CoverPublicSliceKey          string                      `json:"coverPublicSliceKey"`
		PreviewTrackVersion          int                         `json:"previewTrackVersion"`
		PreviewTrackManifestSliceKey string                      `json:"previewTrackManifestSliceKey"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	descriptor := mediamodel.MediaProcessingDescriptor{}
	if body.ImageWidth != 0 ||
		body.ImageHeight != 0 ||
		strings.TrimSpace(body.ImageDeliveryContentType) != "" ||
		strings.TrimSpace(body.ImageNormalizedObjectKey) != "" ||
		strings.TrimSpace(body.ImagePublicSliceKey) != "" {
		descriptor.Image = mediamodel.ImageProcessingDescriptor{
			ProcessorProfile:         body.ProcessorProfile,
			ImageWidth:               body.ImageWidth,
			ImageHeight:              body.ImageHeight,
			ImageDeliveryContentType: body.ImageDeliveryContentType,
			ImageNormalizedObjectKey: body.ImageNormalizedObjectKey,
			ImagePublicSliceKey:      body.ImagePublicSliceKey,
		}
	}
	if body.VerifiedDurationMs != 0 ||
		body.VideoWidth != 0 ||
		body.VideoHeight != 0 ||
		strings.TrimSpace(body.VideoCodec) != "" ||
		strings.TrimSpace(body.VideoContainer) != "" ||
		strings.TrimSpace(body.VideoAudioCodec) != "" ||
		body.VideoKeyframeIntervalMs != 0 ||
		body.VideoFastStart ||
		strings.TrimSpace(body.VideoPublicSliceKey) != "" ||
		strings.TrimSpace(body.CoverPublicSliceKey) != "" ||
		body.PreviewTrackVersion != 0 ||
		strings.TrimSpace(body.PreviewTrackManifestSliceKey) != "" {
		descriptor.Video = mediamodel.VideoProcessingDescriptor{
			ProcessorProfile:             body.ProcessorProfile,
			VerifiedDurationMs:           body.VerifiedDurationMs,
			VideoWidth:                   body.VideoWidth,
			VideoHeight:                  body.VideoHeight,
			VideoCodec:                   body.VideoCodec,
			VideoContainer:               body.VideoContainer,
			VideoAudioCodec:              body.VideoAudioCodec,
			VideoKeyframeIntervalMs:      body.VideoKeyframeIntervalMs,
			VideoFastStart:               body.VideoFastStart,
			VideoPublicSliceKey:          body.VideoPublicSliceKey,
			CoverPublicSliceKey:          body.CoverPublicSliceKey,
			PreviewTrackVersion:          body.PreviewTrackVersion,
			PreviewTrackManifestSliceKey: body.PreviewTrackManifestSliceKey,
		}
	}
	result, err := h.mediaService.RecordMediaProcessingResult(r.Context(), mediaapp.RecordMediaProcessingResultCommand{
		AssetID: mediaID, Processing: body.Processing, FailureReason: body.FailureReason,
		Descriptor: descriptor,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleUpdateMediaAssetAccessPolicy(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/internal/content/media/", ":access-policy")
	var body struct {
		AccessPolicy mediamodel.AccessPolicy `json:"accessPolicy"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	result, err := h.mediaService.UpdateMediaAssetAccessPolicy(r.Context(), mediaapp.UpdateMediaAssetAccessPolicyCommand{
		AssetID: mediaID, OwnerID: operationActorID(r), AccessPolicy: body.AccessPolicy,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

type mediaUploadSessionResponse struct {
	SessionID  string    `json:"sessionId"`
	AssetID    string    `json:"assetId,omitempty"`
	Status     string    `json:"status"`
	ObjectKey  string    `json:"objectKey,omitempty"`
	UploadURL  string    `json:"uploadUrl,omitempty"`
	PresignURL string    `json:"presignUrl,omitempty"`
	CDNURL     string    `json:"cdnUrl,omitempty"`
	ExpiresAt  time.Time `json:"expiresAt"`
	Replayed   bool      `json:"replayed"`
}

type mediaAssetHTTPResponse struct {
	AssetID      string                      `json:"assetId"`
	Version      int64                       `json:"version"`
	MediaType    string                      `json:"mediaType"`
	ContentType  string                      `json:"contentType"`
	FileSize     int64                       `json:"fileSize"`
	Status       mediamodel.ProcessingStatus `json:"status"`
	AccessPolicy mediamodel.AccessPolicy     `json:"accessPolicy"`
	CDNURL       string                      `json:"cdnUrl"`
}

func mediaAssetHTTPResponseFromSlice(asset mediaapp.MediaAssetSlice) mediaAssetHTTPResponse {
	return mediaAssetHTTPResponse{
		AssetID: asset.AssetID, Version: asset.Version, MediaType: asset.MediaType,
		ContentType: asset.ContentType, FileSize: asset.FileSize, Status: asset.ProcessingStatus,
		AccessPolicy: asset.AccessPolicy, CDNURL: asset.DeliveryURL,
	}
}

func (h *ContentHandler) handleRequestOriginalImageAccess(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/content/media/", "/original:access")
	if strings.TrimSpace(mediaID) == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "mediaId 不能为空", "missing mediaId"))
		return
	}
	var body struct {
		Purpose string `json:"purpose"`
	}
	if r.Body != nil {
		defer r.Body.Close()
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
			return
		}
	}
	purpose := strings.TrimSpace(body.Purpose)
	if purpose == "" {
		purpose = "view"
	}
	resp, err := h.mediaService.RequestOriginalMediaAccess(r.Context(), mediaapp.RequestOriginalMediaAccessCommand{
		AssetID: mediaID, Purpose: purpose, ViewerID: operationActorID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *ContentHandler) handleSelectAutoVideoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/content/media/", "/cover:auto")
	result, err := h.mediaService.SelectAutoMediaCover(r.Context(), mediaapp.SelectAutoMediaCoverCommand{
		AssetID: mediaID, OwnerID: operationActorID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaCoverSelectionResponse(result))
}

func (h *ContentHandler) handleSelectManualVideoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := pathParamAfter(r.URL.Path, "/content/media/", "/cover:manual")
	var body struct {
		CoverAssetID     string `json:"coverAssetId"`
		CoverFrameTimeMs int64  `json:"coverFrameTimeMs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	result, err := h.mediaService.SelectManualMediaCover(r.Context(), mediaapp.SelectManualMediaCoverCommand{
		AssetID: mediaID, OwnerID: operationActorID(r), CoverAssetID: body.CoverAssetID,
		CoverFrameTimeMs: body.CoverFrameTimeMs,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaCoverSelectionResponse(result))
}

type mediaCoverSelectionHTTPResponse struct {
	MediaID            string `json:"mediaId"`
	CoverStrategy      string `json:"coverStrategy"`
	ManualCoverAssetID string `json:"manualCoverAssetId,omitempty"`
	CoverFrameTimeMs   int64  `json:"coverFrameTimeMs"`
	ThumbnailURL       string `json:"thumbnailUrl"`
	CoverURL           string `json:"coverUrl"`
}

func mediaCoverSelectionResponse(result mediaapp.MediaAssetCommandResult) mediaCoverSelectionHTTPResponse {
	return mediaCoverSelectionHTTPResponse{
		MediaID: result.AssetID, CoverStrategy: result.CoverStrategy,
		ManualCoverAssetID: result.ManualCoverAssetID, CoverFrameTimeMs: result.CoverFrameTimeMs,
		ThumbnailURL: result.CoverURL, CoverURL: result.CoverURL,
	}
}

func (h *ContentHandler) handleGenerateArticleSummary(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Title string `json:"title"`
		Body  string `json:"body"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	summary := h.postService.GenerateArticleSummary(body.Title, body.Body)
	writeJSON(w, http.StatusOK, map[string]any{"summary": summary})
}
