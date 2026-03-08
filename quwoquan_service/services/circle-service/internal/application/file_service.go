package application

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	model "quwoquan_service/services/circle-service/internal/domain/circle/model"
	"quwoquan_service/services/circle-service/internal/infrastructure/persistence"
)

// FileService encapsulates circle file/folder CRUD with quota enforcement.
type FileService struct {
	files   persistence.FileStore
	circles persistence.CircleStore
	events  EventPublisher
}

func NewFileService(files persistence.FileStore, circles persistence.CircleStore, opts ...CircleServiceOption) *FileService {
	s := &FileService{files: files, circles: circles, events: noopPublisher{}}
	for _, o := range opts {
		cs := &CircleService{events: s.events}
		o(cs)
		s.events = cs.events
	}
	return s
}

func (s *FileService) publishEvent(ctx context.Context, eventType string, aggregateID string, payload map[string]any) {
	s.events.Publish(ctx, repository.DomainEvent{
		Type:          eventType,
		AggregateType: "CircleFile",
		AggregateID:   aggregateID,
		Payload:       payload,
		OccurredAt:    time.Now().Format(time.RFC3339),
	})
}

type CreateFileRequest struct {
	CircleID       string
	ParentFolderID string `json:"parentFolderId"`
	Name           string `json:"name"`
	FileType       string `json:"fileType"`
	MimeType       string `json:"mimeType"`
	SizeBytes      int64  `json:"sizeBytes"`
	UploaderID     string
}

func (s *FileService) CreateFile(ctx context.Context, req CreateFileRequest) (*model.CircleFile, error) {
	if req.Name == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleCircle, "文件名不能为空", "missing file name")
	}

	c, ok := s.circles.FindByID(ctx, req.CircleID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"圈子不存在", "circle not found", false,
		)
	}

	fileType := model.CircleFileTypeFile
	if req.FileType == "folder" {
		fileType = model.CircleFileTypeFolder
	}

	if fileType == model.CircleFileTypeFile {
		if req.SizeBytes > 52428800 {
			return nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "validation_failed"),
				"文件大小超过限制（最大 50MB）", "file too large", false,
			)
		}
		if c.StorageUsedBytes+req.SizeBytes > c.StorageQuotaBytes {
			return nil, rterr.NewAppError(
				rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "quota_exceeded"),
				"存储空间已满，无法上传", "storage quota exceeded", false,
			)
		}
	}

	now := time.Now()
	file := &model.CircleFile{
		ID:             bson.NewObjectID().Hex(),
		CircleID:       req.CircleID,
		ParentFolderID: req.ParentFolderID,
		Name:           req.Name,
		FileType:       fileType,
		MimeType:       req.MimeType,
		SizeBytes:      req.SizeBytes,
		ObjectKey:      fmt.Sprintf("%s/%s/%s", req.CircleID, bson.NewObjectID().Hex(), req.Name),
		UploaderID:     req.UploaderID,
		Status:         model.CircleFileStatusUploading,
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	if fileType == model.CircleFileTypeFolder {
		file.Status = model.CircleFileStatusActive
		file.ObjectKey = ""
	}

	if err := s.files.Create(ctx, file); err != nil {
		return nil, fmt.Errorf("create file: %w", err)
	}

	if fileType == model.CircleFileTypeFolder {
		return file, nil
	}

	// For files, return presigned URL info (stub — production uses S3 SDK)
	return file, nil
}

func (s *FileService) GetFile(ctx context.Context, circleID, fileID string) (*model.CircleFile, error) {
	f, ok := s.files.FindByID(ctx, circleID, fileID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"文件不存在", "file not found", false,
		)
	}
	return f, nil
}

type UpdateFileRequest struct {
	Name   string `json:"name"`
	Status string `json:"status"`
}

func (s *FileService) UpdateFile(ctx context.Context, circleID, fileID string, req UpdateFileRequest) (*model.CircleFile, error) {
	f, ok := s.files.FindByID(ctx, circleID, fileID)
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"文件不存在", "file not found", false,
		)
	}

	if req.Name != "" {
		f.Name = req.Name
	}
	if req.Status == "active" && f.Status == model.CircleFileStatusUploading {
		f.Status = model.CircleFileStatusActive
		if err := s.circles.UpdateStorageUsed(ctx, circleID, f.SizeBytes); err != nil {
			return nil, fmt.Errorf("update storage used: %w", err)
		}
		s.publishEvent(ctx, "CircleFileUploaded", fileID, map[string]any{
			"circleId": circleID, "fileId": fileID, "name": f.Name,
			"uploaderId": f.UploaderID, "sizeBytes": f.SizeBytes,
		})
	}

	if !s.files.Update(ctx, circleID, fileID, f) {
		return nil, fmt.Errorf("update file failed")
	}
	return f, nil
}

func (s *FileService) DeleteFile(ctx context.Context, circleID, fileID string) error {
	f, ok := s.files.FindByID(ctx, circleID, fileID)
	if !ok {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleCircle, rterr.KindUser, "not_found"),
			"文件不存在", "file not found", false,
		)
	}

	if !s.files.Delete(ctx, circleID, fileID) {
		return fmt.Errorf("delete file failed")
	}

	if f.FileType == model.CircleFileTypeFile && f.Status == model.CircleFileStatusActive {
		_ = s.circles.UpdateStorageUsed(ctx, circleID, -f.SizeBytes)
	}

	s.publishEvent(ctx, "CircleFileDeleted", fileID, map[string]any{
		"circleId": circleID, "fileId": fileID, "name": f.Name, "uploaderId": f.UploaderID,
	})
	return nil
}

func (s *FileService) ListFiles(ctx context.Context, circleID string, opts persistence.ListFilesOpts) ([]model.CircleFile, string) {
	return s.files.ListByCircle(ctx, circleID, opts)
}
