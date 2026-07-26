package realtime

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

const presenceResponseLimit = 1 << 20

type PresenceClientConfig struct {
	BaseURL     string
	Credentials rtauth.ServiceAuthorizationProvider
	Timeout     time.Duration
}

type PresenceClient struct {
	baseURL     string
	credentials rtauth.ServiceAuthorizationProvider
	timeout     time.Duration
	client      *http.Client
}

func NewPresenceClient(
	config PresenceClientConfig,
	client *http.Client,
) (*PresenceClient, error) {
	baseURL := strings.TrimRight(strings.TrimSpace(config.BaseURL), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil {
		return nil, errors.New(
			"notification realtime base URL must be absolute http or https",
		)
	}
	if config.Credentials == nil {
		return nil, errors.New(
			"notification realtime credentials are required",
		)
	}
	if config.Timeout <= 0 || client == nil {
		return nil, errors.New(
			"notification realtime timeout and observed client are required",
		)
	}
	return &PresenceClient{
		baseURL:     baseURL,
		credentials: config.Credentials,
		timeout:     config.Timeout,
		client:      client,
	}, nil
}

func (c *PresenceClient) GetPersonaPresence(
	ctx context.Context,
	personaID string,
) (application.PersonaPresenceView, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return application.PersonaPresenceView{},
			errors.New("personaId is required")
	}
	path := strings.ReplaceAll(
		serviceclients.RealtimePersonaPresencePathTemplate,
		"{personaId}",
		url.PathEscape(personaID),
	)
	requestCtx, cancel := context.WithTimeout(ctx, c.timeout)
	defer cancel()
	authorization, err := c.credentials.AuthorizationHeader(requestCtx)
	if err != nil {
		return application.PersonaPresenceView{},
			fmt.Errorf("issue realtime service credential: %w", err)
	}
	request, err := http.NewRequestWithContext(
		requestCtx,
		http.MethodGet,
		c.baseURL+path,
		nil,
	)
	if err != nil {
		return application.PersonaPresenceView{}, err
	}
	request.Header.Set("Authorization", authorization)
	response, err := c.client.Do(request)
	if err != nil {
		return application.PersonaPresenceView{}, err
	}
	defer response.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(response.Body, presenceResponseLimit))
	if err != nil {
		return application.PersonaPresenceView{}, err
	}
	if response.StatusCode != http.StatusOK {
		return application.PersonaPresenceView{}, fmt.Errorf(
			"realtime presence status=%d",
			response.StatusCode,
		)
	}
	var body struct {
		PersonaID string `json:"personaId"`
		Devices   []struct {
			AccountID string `json:"accountId"`
			PersonaID string `json:"personaId"`
			DeviceID  string `json:"deviceId"`
		} `json:"devices"`
	}
	if err := json.Unmarshal(raw, &body); err != nil {
		return application.PersonaPresenceView{}, err
	}
	if strings.TrimSpace(body.PersonaID) != personaID {
		return application.PersonaPresenceView{},
			errors.New("realtime presence personaId mismatch")
	}
	view := application.PersonaPresenceView{
		PersonaID: body.PersonaID,
		Devices: make(
			[]application.PersonaPresenceDevice,
			0,
			len(body.Devices),
		),
	}
	for _, device := range body.Devices {
		view.Devices = append(view.Devices, application.PersonaPresenceDevice{
			AccountID: device.AccountID,
			PersonaID: device.PersonaID,
			DeviceID:  device.DeviceID,
			Online:    true,
		})
	}
	return view, nil
}
