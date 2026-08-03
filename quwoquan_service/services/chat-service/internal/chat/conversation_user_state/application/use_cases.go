package application

import (
	"context"
)

type MarkAsReadRequest struct {
	ConversationId string
	MessageId      string
	UserId         string
}

type UpdateSettingsRequest struct {
	UserId         string
	ConversationId string
	Muted          *bool
	Pinned         *bool
}

type ReadMarker interface {
	MarkAsRead(context.Context, MarkAsReadRequest) error
}
type SettingsUpdater interface {
	UpdateSettings(context.Context, UpdateSettingsRequest) error
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

func (s *UseCases) MarkAsRead(ctx context.Context, req MarkAsReadRequest) error {
	return s.reads.MarkAsRead(ctx, req)
}

func (s *UseCases) UpdateSettings(ctx context.Context, req UpdateSettingsRequest) error {
	return s.settings.UpdateSettings(ctx, req)
}
