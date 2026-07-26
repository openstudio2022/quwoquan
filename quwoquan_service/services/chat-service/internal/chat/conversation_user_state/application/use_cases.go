package application

import (
	"context"

	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type ReadMarker interface {
	MarkAsRead(context.Context, conversationapp.MarkAsReadRequest) error
}
type SettingsUpdater interface {
	UpdateSettings(context.Context, conversationapp.UpdateSettingsRequest) error
}

type UseCases struct {
	reads    ReadMarker
	settings SettingsUpdater
}

func NewUseCases(reads ReadMarker, settings SettingsUpdater) *UseCases {
	if reads == nil || settings == nil {
		panic("conversation user-state dependencies are required")
	}
	return &UseCases{reads: reads, settings: settings}
}

func (s *UseCases) MarkAsRead(ctx context.Context, req conversationapp.MarkAsReadRequest) error {
	return s.reads.MarkAsRead(ctx, req)
}

func (s *UseCases) UpdateSettings(ctx context.Context, req conversationapp.UpdateSettingsRequest) error {
	return s.settings.UpdateSettings(ctx, req)
}
