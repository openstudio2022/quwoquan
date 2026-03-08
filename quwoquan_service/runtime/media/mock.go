package runtimemedia

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// MockMediaStore is an in-memory MediaStore for unit tests and dev environments.
type MockMediaStore struct {
	mu       sync.RWMutex
	sessions map[string]*UploadSession
	assets   map[string]*MediaAsset
	counter  int64
}

// NewMockMediaStore creates an empty in-memory MediaStore.
func NewMockMediaStore() *MockMediaStore {
	return &MockMediaStore{
		sessions: make(map[string]*UploadSession),
		assets:   make(map[string]*MediaAsset),
	}
}

func (m *MockMediaStore) InitUpload(_ context.Context, opts InitUploadOpts) (*UploadSession, error) {
	if err := ValidateUpload(opts); err != nil {
		return nil, err
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	m.counter++
	now := time.Now()
	sessionID := fmt.Sprintf("mock_us_%d", m.counter)
	ossKey := buildOSSKey(opts.Category, opts.OwnerID, sessionID, opts.FileName)

	session := &UploadSession{
		SessionID:   sessionID,
		Category:    opts.Category,
		OwnerID:     opts.OwnerID,
		FileName:    opts.FileName,
		ContentType: opts.ContentType,
		FileSize:    opts.FileSize,
		PresignURL:  fmt.Sprintf("https://mock-oss.example.com/%s?upload=true", ossKey),
		OSSKey:      ossKey,
		Status:      "pending",
		CreatedAt:   now,
		ExpiresAt:   now.Add(15 * time.Minute),
	}

	m.sessions[sessionID] = session
	return session, nil
}

func (m *MockMediaStore) CompleteUpload(_ context.Context, sessionID string, opts CompleteUploadOpts) (*MediaAsset, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	session, ok := m.sessions[sessionID]
	if !ok {
		return nil, fmt.Errorf("session %s not found", sessionID)
	}
	if session.Status != "pending" {
		return nil, fmt.Errorf("session %s status is %s", sessionID, session.Status)
	}

	session.Status = "completed"
	m.counter++

	asset := &MediaAsset{
		AssetID:     fmt.Sprintf("mock_ma_%d", m.counter),
		SessionID:   sessionID,
		Category:    session.Category,
		OwnerID:     session.OwnerID,
		FileName:    session.FileName,
		ContentType: session.ContentType,
		FileSize:    session.FileSize,
		OSSKey:      session.OSSKey,
		CDNURL:      fmt.Sprintf("https://mock-cdn.example.com/%s", session.OSSKey),
		DurationMs:  opts.DurationMs,
		Width:       opts.Width,
		Height:      opts.Height,
		Metadata:    opts.Metadata,
		CreatedAt:   time.Now(),
	}

	m.assets[asset.AssetID] = asset
	return asset, nil
}

func (m *MockMediaStore) AbortUpload(_ context.Context, sessionID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	session, ok := m.sessions[sessionID]
	if !ok {
		return nil
	}
	if session.Status == "pending" {
		session.Status = "aborted"
	}
	return nil
}

func (m *MockMediaStore) GetAsset(_ context.Context, assetID string) (*MediaAsset, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()

	asset, ok := m.assets[assetID]
	if !ok {
		return nil, fmt.Errorf("asset %s not found", assetID)
	}
	return asset, nil
}

func (m *MockMediaStore) SignURL(_ context.Context, ossKey string, _ time.Duration) (string, error) {
	return fmt.Sprintf("https://mock-cdn.example.com/%s?signed=true", ossKey), nil
}

// Reset clears all stored sessions and assets (for test teardown).
func (m *MockMediaStore) Reset() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sessions = make(map[string]*UploadSession)
	m.assets = make(map[string]*MediaAsset)
	m.counter = 0
}

// SessionCount returns the number of stored sessions.
func (m *MockMediaStore) SessionCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.sessions)
}

// AssetCount returns the number of stored assets.
func (m *MockMediaStore) AssetCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.assets)
}
