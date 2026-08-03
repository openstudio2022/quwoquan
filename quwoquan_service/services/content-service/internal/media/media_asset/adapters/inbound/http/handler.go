package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

type Handler struct{ service *mediaapp.Facades }

func NewHandler(service *mediaapp.Facades) *Handler {
	if service == nil {
		panic("MediaAsset HTTP handler requires facades")
	}
	return &Handler{service: service}
}

func (h *Handler) GetPublic(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	if idx := strings.Index(mediaID, "/"); idx > 0 {
		mediaID = mediaID[:idx]
	}
	asset, err := h.service.GetPublicMediaAsset(r.Context(), mediaapp.GetPublicMediaAssetQuery{AssetID: mediaID})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaAssetHTTPResponseFromSlice(asset))
}

func (h *Handler) Discard(
	w http.ResponseWriter,
	r *http.Request,
) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	result, err := h.service.DiscardMediaAsset(
		r.Context(),
		mediaapp.DiscardMediaAssetCommand{
			AssetID: mediaID,
			OwnerID: operationActorID(r),
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) GetOwned(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	asset, err := h.service.GetMediaAsset(r.Context(), mediaapp.GetMediaAssetQuery{AssetID: mediaID, OwnerID: operationActorID(r)})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaAssetHTTPResponseFromSlice(asset))
}

func (h *Handler) GetReference(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	ownerPersonaID := strings.TrimSpace(r.URL.Query().Get("ownerPersonaId"))
	if mediaID == "" || ownerPersonaID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求参数无效", "mediaId and ownerPersonaId are required"))
		return
	}
	asset, err := h.service.GetOwnedReadyMediaAssetReference(r.Context(), mediaapp.GetMediaAssetQuery{
		AssetID: mediaID, OwnerID: ownerPersonaID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *Handler) GetDeliveryReference(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	ownerPersonaID := strings.TrimSpace(r.URL.Query().Get("ownerPersonaId"))
	if mediaID == "" || ownerPersonaID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求参数无效", "mediaId and ownerPersonaId are required"))
		return
	}
	asset, err := h.service.GetOwnedReadyMediaAssetDeliveryReference(r.Context(), mediaapp.GetMediaAssetQuery{
		AssetID: mediaID, OwnerID: ownerPersonaID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, asset)
}

func (h *Handler) RecordProcessingResult(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	var body struct {
		Processing                    mediamodel.ProcessingStatus `json:"processingStatus"`
		FailureReason                 string                      `json:"failureReason"`
		ProcessorProfile              string                      `json:"processorProfile"`
		ImageWidth                    int                         `json:"imageWidth"`
		ImageHeight                   int                         `json:"imageHeight"`
		ImageDeliveryMimeType         string                      `json:"imageDeliveryMimeType"`
		ImageNormalizedObjectKey      string                      `json:"imageNormalizedObjectKey"`
		ImagePublicSliceKey           string                      `json:"imagePublicSliceKey"`
		ImageDominantColor            string                      `json:"imageDominantColor"`
		ImageLQIP                     string                      `json:"imageLqip"`
		ImageContentProfile           string                      `json:"imageContentProfile"`
		ImageDerivativePolicyVersion  int                         `json:"imageDerivativePolicyVersion"`
		VerifiedDurationMs            int64                       `json:"verifiedDurationMs"`
		VideoWidth                    int                         `json:"videoWidth"`
		VideoHeight                   int                         `json:"videoHeight"`
		VideoCodec                    mediamodel.VideoCodec       `json:"videoCodec"`
		VideoContainer                mediamodel.MediaContainer   `json:"videoContainer"`
		VideoAudioCodec               mediamodel.AudioCodec       `json:"videoAudioCodec"`
		VideoKeyframeIntervalMs       int                         `json:"videoKeyframeIntervalMs"`
		VideoFastStart                bool                        `json:"videoFastStart"`
		VideoPublicSliceKey           string                      `json:"videoPublicSliceKey"`
		CoverPublicSliceKey           string                      `json:"coverPublicSliceKey"`
		PreviewTrackVersion           int                         `json:"previewTrackVersion"`
		PreviewTrackManifestSliceKey  string                      `json:"previewTrackManifestSliceKey"`
		HLSCMAFDescriptorVersion      int                         `json:"hlsCmafDescriptorVersion"`
		HLSCMAFDescriptorSliceKey     string                      `json:"hlsCmafDescriptorSliceKey"`
		HLSCMAFMasterManifestSliceKey string                      `json:"hlsCmafMasterManifestSliceKey"`
		HLSCMAFRenditionCount         int                         `json:"hlsCmafRenditionCount"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	descriptor := mediamodel.MediaProcessingDescriptor{}
	if body.ImageWidth != 0 ||
		body.ImageHeight != 0 ||
		strings.TrimSpace(body.ImageDeliveryMimeType) != "" ||
		strings.TrimSpace(body.ImageNormalizedObjectKey) != "" ||
		strings.TrimSpace(body.ImagePublicSliceKey) != "" ||
		strings.TrimSpace(body.ImageDominantColor) != "" ||
		strings.TrimSpace(body.ImageLQIP) != "" ||
		strings.TrimSpace(body.ImageContentProfile) != "" ||
		body.ImageDerivativePolicyVersion != 0 {
		descriptor.Image = mediamodel.ImageProcessingDescriptor{
			ProcessorProfile:         body.ProcessorProfile,
			ImageWidth:               body.ImageWidth,
			ImageHeight:              body.ImageHeight,
			ImageDeliveryMimeType:    body.ImageDeliveryMimeType,
			ImageNormalizedObjectKey: body.ImageNormalizedObjectKey,
			ImagePublicSliceKey:      body.ImagePublicSliceKey,
			ImageDominantColor:       body.ImageDominantColor,
			ImageLQIP:                body.ImageLQIP,
			ImageContentProfile:      body.ImageContentProfile,
			DerivativePolicyVersion:  body.ImageDerivativePolicyVersion,
		}
	}
	if body.VerifiedDurationMs != 0 ||
		body.VideoWidth != 0 ||
		body.VideoHeight != 0 ||
		body.VideoCodec != "" ||
		body.VideoContainer != "" ||
		body.VideoAudioCodec != "" ||
		body.VideoKeyframeIntervalMs != 0 ||
		body.VideoFastStart ||
		strings.TrimSpace(body.VideoPublicSliceKey) != "" ||
		strings.TrimSpace(body.CoverPublicSliceKey) != "" ||
		body.PreviewTrackVersion != 0 ||
		strings.TrimSpace(body.PreviewTrackManifestSliceKey) != "" ||
		body.HLSCMAFDescriptorVersion != 0 ||
		strings.TrimSpace(body.HLSCMAFDescriptorSliceKey) != "" ||
		strings.TrimSpace(body.HLSCMAFMasterManifestSliceKey) != "" ||
		body.HLSCMAFRenditionCount != 0 {
		descriptor.Video = mediamodel.VideoProcessingDescriptor{
			ProcessorProfile:              body.ProcessorProfile,
			VerifiedDurationMs:            body.VerifiedDurationMs,
			VideoWidth:                    body.VideoWidth,
			VideoHeight:                   body.VideoHeight,
			VideoCodec:                    body.VideoCodec,
			VideoContainer:                body.VideoContainer,
			VideoAudioCodec:               body.VideoAudioCodec,
			VideoKeyframeIntervalMs:       body.VideoKeyframeIntervalMs,
			VideoFastStart:                body.VideoFastStart,
			VideoPublicSliceKey:           body.VideoPublicSliceKey,
			CoverPublicSliceKey:           body.CoverPublicSliceKey,
			PreviewTrackVersion:           body.PreviewTrackVersion,
			PreviewTrackManifestSliceKey:  body.PreviewTrackManifestSliceKey,
			HLSCMAFDescriptorVersion:      body.HLSCMAFDescriptorVersion,
			HLSCMAFDescriptorSliceKey:     body.HLSCMAFDescriptorSliceKey,
			HLSCMAFMasterManifestSliceKey: body.HLSCMAFMasterManifestSliceKey,
			HLSCMAFRenditionCount:         body.HLSCMAFRenditionCount,
		}
	}
	result, err := h.service.RecordMediaProcessingResult(r.Context(), mediaapp.RecordMediaProcessingResultCommand{
		AssetID: mediaID, Processing: body.Processing, FailureReason: body.FailureReason,
		Descriptor: descriptor,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) UpdateAccessPolicy(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	var body struct {
		AccessPolicy mediamodel.AccessPolicy `json:"accessPolicy"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	result, err := h.service.UpdateMediaAssetAccessPolicy(r.Context(), mediaapp.UpdateMediaAssetAccessPolicyCommand{
		AssetID: mediaID, OwnerID: operationActorID(r), AccessPolicy: body.AccessPolicy,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

type mediaAssetHTTPResponse struct {
	AssetID                      string                      `json:"assetId"`
	Version                      int64                       `json:"version"`
	MediaType                    string                      `json:"mediaType"`
	MimeType                     string                      `json:"mimeType"`
	FileSize                     int64                       `json:"fileSize"`
	Status                       mediamodel.ProcessingStatus `json:"status"`
	AccessPolicy                 mediamodel.AccessPolicy     `json:"accessPolicy"`
	CDNURL                       string                      `json:"cdnUrl"`
	ImageWidth                   int                         `json:"imageWidth,omitempty"`
	ImageHeight                  int                         `json:"imageHeight,omitempty"`
	ImageDeliveryMimeType        string                      `json:"imageDeliveryMimeType,omitempty"`
	ImageDominantColor           string                      `json:"imageDominantColor,omitempty"`
	ImageLQIP                    string                      `json:"imageLqip,omitempty"`
	ImageContentProfile          string                      `json:"imageContentProfile,omitempty"`
	ImageDerivativePolicyVersion int                         `json:"imageDerivativePolicyVersion,omitempty"`
}

func mediaAssetHTTPResponseFromSlice(asset mediaapp.MediaAssetSlice) mediaAssetHTTPResponse {
	return mediaAssetHTTPResponse{
		AssetID: asset.AssetID, Version: asset.Version, MediaType: asset.MediaType,
		MimeType: asset.MimeType, FileSize: asset.FileSize, Status: asset.ProcessingStatus,
		AccessPolicy: asset.AccessPolicy, CDNURL: asset.DeliveryURL,
		ImageWidth: asset.ImageWidth, ImageHeight: asset.ImageHeight,
		ImageDeliveryMimeType: asset.ImageDeliveryMimeType,
		ImageDominantColor:    asset.ImageDominantColor, ImageLQIP: asset.ImageLQIP,
		ImageContentProfile:          asset.ImageContentProfile,
		ImageDerivativePolicyVersion: asset.ImageDerivativePolicyVersion,
	}
}

func (h *Handler) SelectAutoCover(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	result, err := h.service.SelectAutoMediaCover(r.Context(), mediaapp.SelectAutoMediaCoverCommand{
		AssetID: mediaID, OwnerID: operationActorID(r),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, mediaCoverSelectionResponse(result))
}

func (h *Handler) SelectManualCover(w http.ResponseWriter, r *http.Request) {
	mediaID := strings.TrimSpace(r.PathValue("mediaId"))
	var body struct {
		CoverAssetID     string `json:"coverAssetId"`
		CoverFrameTimeMs int64  `json:"coverFrameTimeMs"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil && err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	result, err := h.service.SelectManualMediaCover(r.Context(), mediaapp.SelectManualMediaCoverCommand{
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

func operationActorID(request *http.Request) string {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		return ""
	}
	actorID, _ := principal.Actor.BusinessActorID()
	return strings.TrimSpace(actorID)
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	httpcodec.WriteJSON(writer, status, value, "media_asset")
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
