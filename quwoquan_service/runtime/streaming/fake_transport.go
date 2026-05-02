package streaming

import "sync"

type FakeTransport struct {
	mu       sync.RWMutex
	messages map[string][]Envelope
}

func NewFakeTransport() *FakeTransport {
	return &FakeTransport{messages: map[string][]Envelope{}}
}

func (t *FakeTransport) Publish(streamID string, envelope Envelope) {
	t.mu.Lock()
	defer t.mu.Unlock()
	envelope.StreamID = streamID
	t.messages[streamID] = append(t.messages[streamID], envelope.Normalized())
}

func (t *FakeTransport) List(streamID string, afterSeq uint64) []Envelope {
	t.mu.RLock()
	defer t.mu.RUnlock()
	items := t.messages[streamID]
	out := make([]Envelope, 0, len(items))
	for _, item := range items {
		if item.Seq > afterSeq {
			out = append(out, item)
		}
	}
	return out
}

func (t *FakeTransport) Reset() {
	t.mu.Lock()
	defer t.mu.Unlock()
	t.messages = map[string][]Envelope{}
}
