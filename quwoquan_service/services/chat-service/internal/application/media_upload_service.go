package application

import (
	"context"
	"strings"

	runtimemedia "quwoquan_service/runtime/media"
)

type ChatMediaUploadService struct {
	mediaStore runtimemedia.MediaStore
}

type ChatMediaUploadServiceOption func(*ChatMediaUploadService)

type ChatMediaInitUploadResponse struct {
	SessionID          string `json:"sessionId"`
	MediaID            string `json:"mediaId"`
	UploadURL          string `json:"uploadUrl"`
	PresignURL         string `json:"presignUrl"`
	ObjectKey          string `json:"objectKey"`
	TemporaryObjectKey string `json:"temporaryObjectKey"`
	UploaderID         string `json:"uploaderId"`
	AssetScope         string `json:"assetScope"`
	SourceKind         string `json:"sourceKind"`
	MediaType          string `json:"mediaType"`
	FileName           string `json:"fileName"`
	ContentType        string `json:"contentType"`
	FileSize           int64  `json:"fileSize"`
}

type ChatMediaCompleteUploadResponse struct {
	SessionID          string `json:"sessionId"`
	Status             string `json:"status"`
	CDNURL             string `json:"cdnUrl"`
	AssetID            string `json:"assetId"`
	MediaID            string `json:"mediaId"`
	ObjectKey          string `json:"objectKey"`
	TemporaryObjectKey string `json:"temporaryObjectKey"`
	MediaType          string `json:"mediaType"`
	FileName           string `json:"fileName"`
	ContentType        string `json:"contentType"`
	FileSize           int64  `json:"fileSize"`
}

func NewChatMediaUploadService(opts ...ChatMediaUploadServiceOption) *ChatMediaUploadService {
	svc := &ChatMediaUploadService{mediaStore: runtimemedia.NewMockMediaStore()}
	for _, opt := range opts {
		if opt != nil {
			opt(svc)
		}
	}
	if svc.mediaStore == nil {
		svc.mediaStore = runtimemedia.NewMockMediaStore()
	}
	return svc
}

func WithChatMediaStore(store runtimemedia.MediaStore) ChatMediaUploadServiceOption {
	return func(s *ChatMediaUploadService) {
		s.mediaStore = store
	}
}

func (s *ChatMediaUploadService) InitUpload(
	ctx context.Context,
	ownerID, mediaType, assetScope, sourceKind, fileName, contentType string,
	fileSize int64,
) (ChatMediaInitUploadResponse, error) {
	normalizedMediaType := normalizeChatMediaType(mediaType)
	if ownerID = strings.TrimSpace(ownerID); ownerID == "" {
		ownerID = "anonymous"
	}
	if assetScope = strings.TrimSpace(assetScope); assetScope == "" {
		assetScope = "draft"
	}
	if sourceKind = strings.TrimSpace(sourceKind); sourceKind == "" {
		sourceKind = "chat_attachment"
	}
	if fileName = strings.TrimSpace(fileName); fileName == "" {
		fileName = normalizedMediaType
	}
	if contentType = strings.TrimSpace(contentType); contentType == "" {
		contentType = defaultChatContentType(normalizedMediaType)
	}
	session, err := s.mediaStore.InitUpload(ctx, runtimemedia.InitUploadOpts{
		Category:    chatMediaCategory(normalizedMediaType),
		OwnerID:     ownerID,
		FileName:    fileName,
		ContentType: contentType,
		FileSize:    fileSize,
	})
	if err != nil {
		return ChatMediaInitUploadResponse{}, err
	}
	return ChatMediaInitUploadResponse{
		SessionID:          session.SessionID,
		MediaID:            session.SessionID,
		UploadURL:          session.PresignURL,
		PresignURL:         session.PresignURL,
		ObjectKey:          session.OSSKey,
		TemporaryObjectKey: session.TemporaryOSSKey,
		UploaderID:         ownerID,
		AssetScope:         assetScope,
		SourceKind:         sourceKind,
		MediaType:          normalizedMediaType,
		FileName:           fileName,
		ContentType:        contentType,
		FileSize:           fileSize,
	}, nil
}

func (s *ChatMediaUploadService) CompleteUpload(
	ctx context.Context,
	sessionID string,
) (ChatMediaCompleteUploadResponse, error) {
	asset, err := s.mediaStore.CompleteUpload(ctx, strings.TrimSpace(sessionID), runtimemedia.CompleteUploadOpts{})
	if err != nil {
		return ChatMediaCompleteUploadResponse{}, err
	}
	return ChatMediaCompleteUploadResponse{
		SessionID:          asset.SessionID,
		Status:             "ready",
		CDNURL:             asset.CDNURL,
		AssetID:            asset.AssetID,
		MediaID:            asset.AssetID,
		ObjectKey:          asset.OSSKey,
		TemporaryObjectKey: asset.TemporaryOSSKey,
		MediaType:          string(asset.Category),
		FileName:           asset.FileName,
		ContentType:        asset.ContentType,
		FileSize:           asset.FileSize,
	}, nil
}

func (s *ChatMediaUploadService) AbortUpload(ctx context.Context, sessionID string) error {
	return s.mediaStore.AbortUpload(ctx, strings.TrimSpace(sessionID))
}

func normalizeChatMediaType(raw string) string {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "chatvoice", "voice", "audio":
		return "audio"
	case "chatvideo", "video":
		return "video"
	case "chatfile", "file", "document":
		return "file"
	case "chatimage", "image", "photo":
		return "image"
	default:
		return "image"
	}
}

func chatMediaCategory(mediaType string) runtimemedia.MediaCategory {
	switch normalizeChatMediaType(mediaType) {
	case "audio":
		return runtimemedia.CategoryChatVoice
	case "video":
		return runtimemedia.CategoryChatVideo
	case "file":
		return runtimemedia.CategoryChatFile
	default:
		return runtimemedia.CategoryChatImage
	}
}

func defaultChatContentType(mediaType string) string {
	switch normalizeChatMediaType(mediaType) {
	case "audio":
		return "audio/mp4"
	case "video":
		return "video/mp4"
	case "file":
		return "application/octet-stream"
	default:
		return "image/jpeg"
	}
}
