package id

import (
	"fmt"
	"regexp"
	"sort"
	"sync"
)

type Prefix string

const (
	PrefixAssistantConversation Prefix = "acv_"
	PrefixAssistantTurn         Prefix = "atn_"
	PrefixSkillSubscription     Prefix = "sub_"
	PrefixDeviceContext         Prefix = "dcx_"
	PrefixToolUse               Prefix = "tu_"
	PrefixAppMessage            Prefix = "msg_"
)

var prefixPattern = regexp.MustCompile(`^[a-z][a-z0-9]{1,15}_$`)

type Registry struct {
	mu       sync.RWMutex
	prefixes map[Prefix]string
}

func NewRegistry() *Registry {
	return &Registry{prefixes: map[Prefix]string{}}
}

func (r *Registry) Register(prefix Prefix, owner string) error {
	if !prefixPattern.MatchString(string(prefix)) {
		return fmt.Errorf("runtime/id: invalid prefix %q", prefix)
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	if existing, ok := r.prefixes[prefix]; ok && existing != owner {
		return fmt.Errorf("runtime/id: prefix %q already registered for %q", prefix, existing)
	}
	r.prefixes[prefix] = owner
	return nil
}

func (r *Registry) MustRegister(prefix Prefix, owner string) {
	if err := r.Register(prefix, owner); err != nil {
		panic(err)
	}
}

func (r *Registry) Contains(prefix Prefix) bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	_, ok := r.prefixes[prefix]
	return ok
}

func (r *Registry) Owner(prefix Prefix) (string, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	owner, ok := r.prefixes[prefix]
	return owner, ok
}

func (r *Registry) Prefixes() []Prefix {
	r.mu.RLock()
	defer r.mu.RUnlock()
	prefixes := make([]Prefix, 0, len(r.prefixes))
	for prefix := range r.prefixes {
		prefixes = append(prefixes, prefix)
	}
	sort.Slice(prefixes, func(i, j int) bool {
		return prefixes[i] < prefixes[j]
	})
	return prefixes
}

var DefaultRegistry = NewRegistry()

func init() {
	DefaultRegistry.MustRegister(PrefixAssistantConversation, "AssistantConversation")
	DefaultRegistry.MustRegister(PrefixAssistantTurn, "AssistantTurn")
	DefaultRegistry.MustRegister(PrefixSkillSubscription, "SkillSubscription")
	DefaultRegistry.MustRegister(PrefixDeviceContext, "DeviceContext")
	DefaultRegistry.MustRegister(PrefixToolUse, "ToolUse")
	DefaultRegistry.MustRegister(PrefixAppMessage, "AppMessage")
}
