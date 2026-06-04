package runtimemedia

import (
	"context"
	"fmt"
	"sync"
)

type InMemorySessionStore struct {
	mu       sync.RWMutex
	sessions map[string]*UploadSession
}

func NewInMemorySessionStore() *InMemorySessionStore {
	return &InMemorySessionStore{sessions: map[string]*UploadSession{}}
}

func (s *InMemorySessionStore) Create(_ context.Context, session *UploadSession) error {
	if session == nil || session.SessionID == "" {
		return fmt.Errorf("media session is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := *session
	s.sessions[session.SessionID] = &cp
	return nil
}

func (s *InMemorySessionStore) FindByID(_ context.Context, sessionID string) (*UploadSession, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return nil, fmt.Errorf("media session %s not found", sessionID)
	}
	cp := *session
	return &cp, nil
}

func (s *InMemorySessionStore) UpdateStatus(_ context.Context, sessionID string, status string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	session, ok := s.sessions[sessionID]
	if !ok {
		return fmt.Errorf("media session %s not found", sessionID)
	}
	cp := *session
	cp.Status = status
	s.sessions[sessionID] = &cp
	return nil
}

type InMemoryAssetStore struct {
	mu     sync.RWMutex
	assets map[string]*MediaAsset
}

func NewInMemoryAssetStore() *InMemoryAssetStore {
	return &InMemoryAssetStore{assets: map[string]*MediaAsset{}}
}

func (s *InMemoryAssetStore) Create(_ context.Context, asset *MediaAsset) error {
	if asset == nil || asset.AssetID == "" {
		return fmt.Errorf("media asset is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := *asset
	s.assets[asset.AssetID] = &cp
	return nil
}

func (s *InMemoryAssetStore) FindByID(_ context.Context, assetID string) (*MediaAsset, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	asset, ok := s.assets[assetID]
	if !ok {
		return nil, fmt.Errorf("media asset %s not found", assetID)
	}
	cp := *asset
	return &cp, nil
}
