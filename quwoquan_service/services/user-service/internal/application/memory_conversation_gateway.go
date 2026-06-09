package application

import (
	"context"
	"sync"
)

// MemoryConversationGateway is a test double for greeting reply promotion.
type MemoryConversationGateway struct {
	mu            sync.Mutex
	conversations map[string]string
}

func NewMemoryConversationGateway() *MemoryConversationGateway {
	return &MemoryConversationGateway{
		conversations: make(map[string]string),
	}
}

func (g *MemoryConversationGateway) pairKey(a, b string) string {
	if a > b {
		a, b = b, a
	}
	return a + ":" + b
}

func (g *MemoryConversationGateway) CreateOrReuseDirect(_ context.Context, creatorID, peerID string) (string, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	key := g.pairKey(creatorID, peerID)
	if id, ok := g.conversations[key]; ok {
		return id, nil
	}
	id := "conv_" + key
	g.conversations[key] = id
	return id, nil
}

func (g *MemoryConversationGateway) HasDirectBetween(_ context.Context, subAccountA, subAccountB string) (bool, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	_, ok := g.conversations[g.pairKey(subAccountA, subAccountB)]
	return ok, nil
}
