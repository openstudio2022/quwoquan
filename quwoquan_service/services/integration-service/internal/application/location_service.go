package application

import (
	"context"
	"fmt"
	"log"
	"strings"

	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/generated"
)

type Service struct {
	primary   model.Provider
	secondary model.Provider
	clients   map[model.Provider]model.ProviderClient
	logger    *log.Logger
}

func NewService(
	primary model.Provider,
	secondary model.Provider,
	clients map[model.Provider]model.ProviderClient,
	logger *log.Logger,
) *Service {
	if logger == nil {
		logger = log.Default()
	}
	return &Service{
		primary:   primary,
		secondary: secondary,
		clients:   clients,
		logger:    logger,
	}
}

func (s *Service) Nearby(ctx context.Context, q model.NearbyQuery) ([]model.POI, error) {
	return s.withFallback(ctx, "nearby", func(client model.ProviderClient) ([]model.POI, error) {
		return client.Nearby(ctx, q)
	})
}

func (s *Service) Search(ctx context.Context, q model.SearchQuery) ([]model.POI, error) {
	return s.withFallback(ctx, "search", func(client model.ProviderClient) ([]model.POI, error) {
		return client.Search(ctx, q)
	})
}

func (s *Service) withFallback(
	ctx context.Context,
	scene string,
	call func(client model.ProviderClient) ([]model.POI, error),
) ([]model.POI, error) {
	_ = ctx
	providers := s.providerSequence()
	if len(providers) == 0 {
		return nil, generated.AppErrorFromLocationUnavailable("no location providers configured")
	}

	var lastErr error
	for idx, provider := range providers {
		client := s.clients[provider]
		if client == nil {
			continue
		}

		items, err := call(client)
		if err == nil {
			if idx == 1 {
				s.logger.Printf("integration-service %s provider fallback succeeded provider=%s items=%d", scene, provider, len(items))
			} else {
				s.logger.Printf("integration-service %s provider success provider=%s items=%d", scene, provider, len(items))
			}
			return items, nil
		}

		lastErr = err
		s.logger.Printf("integration-service %s provider failed provider=%s err=%v", scene, provider, err)
	}

	debugMessage := "location provider attempts exhausted"
	if lastErr != nil {
		debugMessage = fmt.Sprintf("location provider attempts exhausted: %v", lastErr)
	}
	if generated.IsTimeout(lastErr) {
		return nil, generated.AppErrorFromUpstreamTimeout(debugMessage)
	}
	return nil, generated.AppErrorFromInternalError(debugMessage)
}

func (s *Service) providerSequence() []model.Provider {
	seq := make([]model.Provider, 0, 2)
	push := func(p model.Provider) {
		if strings.TrimSpace(string(p)) == "" {
			return
		}
		for _, existing := range seq {
			if existing == p {
				return
			}
		}
		if _, ok := s.clients[p]; ok {
			seq = append(seq, p)
		}
	}
	push(s.primary)
	push(s.secondary)
	return seq
}
