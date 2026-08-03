package model

import (
	"errors"
	"strings"
	"time"
)

const (
	ProjectionTTL = 120 * time.Second
	StaleAfter    = 60 * time.Second
)

// Device is the current projection for one canonical persona/device pair.
// Sequence is the Connection fencing token and is the only ordering source.
type Device struct {
	AccountID       string    `json:"accountId"`
	PersonaID       string    `json:"personaId"`
	DeviceID        string    `json:"deviceId"`
	ConnectionID    string    `json:"connId"`
	NodeID          string    `json:"nodeId"`
	Transport       string    `json:"transport"`
	LastHeartbeatAt time.Time `json:"lastHeartbeatAt"`
	ExpiresAt       time.Time `json:"expiresAt"`
	Sequence        int64     `json:"sequence"`
}

func NewDevice(
	accountID string,
	personaID string,
	deviceID string,
	connectionID string,
	nodeID string,
	transport string,
	observedAt time.Time,
	sequence int64,
) (Device, error) {
	device := Device{
		AccountID:       strings.TrimSpace(accountID),
		PersonaID:       strings.TrimSpace(personaID),
		DeviceID:        strings.TrimSpace(deviceID),
		ConnectionID:    strings.TrimSpace(connectionID),
		NodeID:          strings.TrimSpace(nodeID),
		Transport:       strings.TrimSpace(transport),
		LastHeartbeatAt: observedAt.UTC(),
		ExpiresAt:       observedAt.UTC().Add(ProjectionTTL),
		Sequence:        sequence,
	}
	if err := device.Validate(); err != nil {
		return Device{}, err
	}
	return device, nil
}

func (device Device) Validate() error {
	if strings.TrimSpace(device.AccountID) == "" ||
		strings.TrimSpace(device.PersonaID) == "" ||
		strings.TrimSpace(device.DeviceID) == "" ||
		strings.TrimSpace(device.ConnectionID) == "" ||
		strings.TrimSpace(device.NodeID) == "" ||
		strings.TrimSpace(device.Transport) == "" ||
		device.LastHeartbeatAt.IsZero() ||
		!device.ExpiresAt.After(device.LastHeartbeatAt) ||
		device.Sequence <= 0 {
		return errors.New("presence device projection is invalid")
	}
	return nil
}

type View struct {
	PersonaID string   `json:"personaId"`
	Devices   []Device `json:"devices"`
}
