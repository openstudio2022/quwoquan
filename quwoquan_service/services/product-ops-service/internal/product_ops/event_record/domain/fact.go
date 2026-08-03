package domain

import (
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
)

// Input is the contract-generated EventRecord wire value. The domain owns its
// catalog, identity, timestamp and extension invariants before persistence.
type EventRecordInput = generated.EventRecordInput
type Input = EventRecordInput

type Fact struct {
	EventRecordInput
	BatchKey   string    `json:"-"`
	BatchIndex int       `json:"-"`
	IngestedAt time.Time `json:"-"`
}

func NewFact(input Input, batchKey string, batchIndex int, ingestedAt time.Time) (Fact, error) {
	if strings.TrimSpace(batchKey) == "" || batchIndex < 0 || ingestedAt.IsZero() {
		return Fact{}, fmt.Errorf("event record persistence identity is invalid")
	}
	if err := ValidateInput(input, ingestedAt.UTC()); err != nil {
		return Fact{}, err
	}
	occurredAt, _ := time.Parse(time.RFC3339Nano, input.OccurredAt)
	input.OccurredAt = occurredAt.UTC().Format(time.RFC3339Nano)
	return Fact{
		EventRecordInput: input, BatchKey: batchKey, BatchIndex: batchIndex, IngestedAt: ingestedAt.UTC(),
	}, nil
}

func ValidateInput(input Input, now time.Time) error {
	definition, ok := generated.EventCatalog[input.EventType]
	if !ok || input.LogType != definition.LogType {
		return fmt.Errorf("unknown eventType/logType")
	}
	if _, ok := generated.EventNetworkClasses[input.NetworkClass]; !ok {
		return fmt.Errorf("unknown networkClass")
	}
	devicePlatformDefinition := generated.EventExtensionFields["devicePlatform"]
	if _, ok := devicePlatformDefinition.AllowedValues[input.DevicePlatform]; !ok {
		return fmt.Errorf("unknown devicePlatform")
	}
	if _, ok := generated.AppPageNames[input.PageName]; !ok {
		return fmt.Errorf("unknown pageName")
	}
	for name, value := range map[string]string{
		"sessionId": input.SessionID, "pageName": input.PageName, "occurredAt": input.OccurredAt,
		"deviceManufacturer": input.DeviceManufacturer, "deviceModel": input.DeviceModel,
		"appVersion": input.AppVersion, "networkClass": input.NetworkClass,
	} {
		if strings.TrimSpace(value) == "" || !utf8.ValidString(value) || utf8.RuneCountInString(value) > 256 {
			return fmt.Errorf("%s is invalid", name)
		}
	}
	if err := ValidateSessionID(input.SessionID); err != nil {
		return err
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, input.OccurredAt)
	if err != nil || occurredAt.Before(now.Add(-72*time.Hour)) || occurredAt.After(now.Add(5*time.Minute)) {
		return fmt.Errorf("occurredAt outside accepted window")
	}
	extensions := input.ExtensionValues()
	extensions["devicePlatform"] = input.DevicePlatform
	for required := range definition.RequiredExtensions {
		if _, ok := extensions[required]; !ok {
			return fmt.Errorf("missing extension %s", required)
		}
	}
	for name, value := range extensions {
		if _, ok := definition.RequiredExtensions[name]; !ok {
			if _, ok := definition.OptionalExtensions[name]; !ok {
				if _, ok := generated.EventContextExtensions[name]; !ok {
					return fmt.Errorf("unknown extension %s", name)
				}
			}
		}
		if err := validateExtension(name, value); err != nil {
			return err
		}
	}
	return nil
}

func ValidateSessionID(value string) error {
	if !strings.HasPrefix(value, "s.") {
		return fmt.Errorf("sessionId prefix invalid")
	}
	separator := strings.LastIndex(value, ".")
	if separator <= 2 || separator == len(value)-1 {
		return fmt.Errorf("sessionId shape invalid")
	}
	if _, err := strconv.ParseInt(value[separator+1:], 10, 64); err != nil {
		return fmt.Errorf("sessionId timestamp invalid")
	}
	if _, err := base64.RawURLEncoding.DecodeString(value[2:separator]); err != nil {
		return fmt.Errorf("sessionId actor invalid")
	}
	return nil
}

func validateExtension(name string, value any) error {
	definition, ok := generated.EventExtensionFields[name]
	if !ok {
		return fmt.Errorf("unknown extension %s", name)
	}
	switch definition.Type {
	case "int":
		integer, ok := value.(int)
		if !ok {
			return fmt.Errorf("%s must be int", name)
		}
		if definition.Minimum != nil && integer < *definition.Minimum {
			return fmt.Errorf("%s below minimum", name)
		}
		if definition.Maximum != nil && integer > *definition.Maximum {
			return fmt.Errorf("%s above maximum", name)
		}
	case "string":
		text, ok := value.(string)
		if !ok || strings.TrimSpace(text) == "" || (definition.MaxLength > 0 && utf8.RuneCountInString(text) > definition.MaxLength) {
			return fmt.Errorf("%s is invalid", name)
		}
		if len(definition.AllowedValues) > 0 {
			if _, allowed := definition.AllowedValues[text]; !allowed {
				return fmt.Errorf("%s is not an allowed value", name)
			}
		}
	case "bool":
		if _, ok := value.(bool); !ok {
			return fmt.Errorf("%s must be bool", name)
		}
	case "string_list":
		values, ok := value.([]string)
		if !ok || len(values) == 0 || len(values) > definition.MaxItems {
			return fmt.Errorf("%s is invalid", name)
		}
		for _, text := range values {
			if strings.TrimSpace(text) == "" || utf8.RuneCountInString(text) > definition.ItemMaxLength {
				return fmt.Errorf("%s item is invalid", name)
			}
		}
	default:
		return fmt.Errorf("unsupported extension type")
	}
	return nil
}
