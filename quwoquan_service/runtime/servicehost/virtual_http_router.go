package servicehost

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"sort"
	"strings"
	"sync/atomic"
)

// VirtualHTTPRoute preserves a logical service hostname and port while
// forwarding to a process-local module listener.
type VirtualHTTPRoute struct {
	Host       string
	PublicAddr string
	Upstream   string
}

// VirtualHTTPRouter resolves hostname-disambiguated services that historically
// shared a container-local port. It remains closed until every service module
// has reached aggregate readiness.
type VirtualHTTPRouter struct {
	groups    []*virtualHTTPGroup
	admission atomic.Bool
}

type virtualHTTPGroup struct {
	addr       string
	server     *http.Server
	listener   net.Listener
	serveError chan error
}

// NewVirtualHTTPRouter validates and groups routes by public listener.
func NewVirtualHTTPRouter(routes ...VirtualHTTPRoute) (*VirtualHTTPRouter, error) {
	if len(routes) == 0 {
		return nil, errors.New("virtual HTTP router requires at least one route")
	}
	targetsByAddr := make(map[string]map[string]*httputil.ReverseProxy)
	for _, route := range routes {
		host := normalizeHTTPHost(route.Host)
		if host == "" {
			return nil, errors.New("virtual HTTP route host must not be empty")
		}
		if strings.TrimSpace(route.PublicAddr) == "" {
			return nil, fmt.Errorf(
				"virtual HTTP route %q public address must not be empty",
				host,
			)
		}
		target, err := url.Parse(route.Upstream)
		if err != nil ||
			target.Scheme != "http" ||
			target.Hostname() != "127.0.0.1" ||
			target.Port() == "" ||
			target.Path != "" ||
			target.RawQuery != "" ||
			target.Fragment != "" {
			return nil, fmt.Errorf(
				"virtual HTTP route %q upstream must be an exact loopback HTTP origin",
				host,
			)
		}
		targets := targetsByAddr[route.PublicAddr]
		if targets == nil {
			targets = make(map[string]*httputil.ReverseProxy)
			targetsByAddr[route.PublicAddr] = targets
		}
		if _, exists := targets[host]; exists {
			return nil, fmt.Errorf(
				"virtual HTTP route %q is duplicated on %q",
				host,
				route.PublicAddr,
			)
		}
		proxy := httputil.NewSingleHostReverseProxy(target)
		proxy.ErrorHandler = func(writer http.ResponseWriter, _ *http.Request, _ error) {
			http.Error(
				writer,
				`{"status":"unavailable"}`,
				http.StatusBadGateway,
			)
		}
		targets[host] = proxy
	}

	addresses := make([]string, 0, len(targetsByAddr))
	for address := range targetsByAddr {
		addresses = append(addresses, address)
	}
	sort.Strings(addresses)
	router := &VirtualHTTPRouter{}
	for _, address := range addresses {
		targets := targetsByAddr[address]
		group := &virtualHTTPGroup{
			addr:       address,
			serveError: make(chan error, 1),
		}
		group.server = &http.Server{
			Addr: address,
			Handler: http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
				if !router.admission.Load() &&
					request.URL.Path != "/healthz" &&
					request.URL.Path != "/internal/user/account-security/health" {
					http.Error(
						writer,
						`{"status":"unavailable"}`,
						http.StatusServiceUnavailable,
					)
					return
				}
				host := normalizeHTTPHost(request.Host)
				proxy := targets[host]
				if proxy == nil {
					http.Error(
						writer,
						`{"status":"misdirected_request"}`,
						http.StatusMisdirectedRequest,
					)
					return
				}
				proxy.ServeHTTP(writer, request)
			}),
		}
		router.groups = append(router.groups, group)
	}
	return router, nil
}

// Bind reserves all public addresses while admission remains closed.
func (router *VirtualHTTPRouter) Bind(context.Context) error {
	for _, group := range router.groups {
		listener, err := net.Listen("tcp", group.addr)
		if err != nil {
			_ = router.Shutdown(context.Background())
			return fmt.Errorf("virtual HTTP router bind %q: %w", group.addr, err)
		}
		group.listener = listener
	}
	return nil
}

// Start begins serving closed-admission listeners.
func (router *VirtualHTTPRouter) Start(context.Context) error {
	for _, group := range router.groups {
		if group.listener == nil {
			return fmt.Errorf("virtual HTTP router %q is not bound", group.addr)
		}
		go func(group *virtualHTTPGroup) {
			if err := group.server.Serve(group.listener); err != nil &&
				!errors.Is(err, http.ErrServerClosed) {
				group.serveError <- err
			}
		}(group)
	}
	return nil
}

// Ready verifies every router listener remains healthy.
func (router *VirtualHTTPRouter) Ready(context.Context) error {
	for _, group := range router.groups {
		select {
		case err := <-group.serveError:
			return fmt.Errorf("virtual HTTP router %q failed: %w", group.addr, err)
		default:
		}
	}
	return nil
}

// OpenAdmission exposes logical service endpoints after aggregate readiness.
func (router *VirtualHTTPRouter) OpenAdmission() {
	router.admission.Store(true)
}

// CloseAdmission immediately stops new logical service traffic.
func (router *VirtualHTTPRouter) CloseAdmission() {
	router.admission.Store(false)
}

// Shutdown closes every public router listener.
func (router *VirtualHTTPRouter) Shutdown(ctx context.Context) error {
	router.CloseAdmission()
	var result error
	for index := len(router.groups) - 1; index >= 0; index-- {
		group := router.groups[index]
		if group.server != nil {
			result = errors.Join(result, group.server.Shutdown(ctx))
		}
		if group.listener != nil {
			if err := group.listener.Close(); err != nil && !errors.Is(err, net.ErrClosed) {
				result = errors.Join(result, err)
			}
			group.listener = nil
		}
	}
	return result
}

func normalizeHTTPHost(raw string) string {
	host := strings.TrimSpace(strings.ToLower(raw))
	if parsed, _, err := net.SplitHostPort(host); err == nil {
		host = parsed
	}
	return strings.TrimSuffix(host, ".")
}
