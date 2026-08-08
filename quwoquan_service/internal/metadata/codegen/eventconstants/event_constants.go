// Package eventconstants renders event wire identities from the canonical
// ContractGraph. It owns language rendering only; physical Go output ownership
// stays with each business object's existing generator.
package eventconstants

import (
	"bytes"
	"fmt"
	"go/format"
	"sort"
	"strings"
	"text/template"
	"unicode"

	"quwoquan_service/internal/metadata/graph"
)

const TransactionalOutbox = "transactional_outbox"

// Definition is one object-owned event constant input. WireValue is the actual
// envelope identity; ClientWSType remains a separate realtime-client axis.
type Definition struct {
	ObjectID          string
	Name              string
	DeliverySemantics string
	WireValue         string
	ClientWSType      string
}

// WireValue returns the canonical constant value for one event. Only
// transactional outbox events may use wire_event_type; all other event
// constants retain their authored local name.
func WireValue(name, deliverySemantics, wireEventType string) (string, error) {
	name = strings.TrimSpace(name)
	deliverySemantics = strings.TrimSpace(deliverySemantics)
	wireEventType = strings.TrimSpace(wireEventType)
	if deliverySemantics != TransactionalOutbox {
		if wireEventType != "" {
			return "", fmt.Errorf(
				"non-outbox event %q must not declare wire_event_type %q",
				name,
				wireEventType,
			)
		}
		return name, nil
	}
	if wireEventType == "" {
		return "", fmt.Errorf(
			"transactional_outbox event %q requires wire_event_type",
			name,
		)
	}
	return wireEventType, nil
}

// DefinitionsForObject reads only the typed governance packet compiled by the
// metadata loader. Generators must not reparse events.yaml into a second model.
func DefinitionsForObject(
	contractGraph *graph.ContractGraph,
	objectID string,
) ([]Definition, error) {
	for _, packet := range contractGraph.Governance.Objects {
		if packet.ObjectID != objectID {
			continue
		}
		definitions := make([]Definition, 0, len(packet.Events))
		seenNames := map[string]struct{}{}
		for _, event := range packet.Events {
			name := strings.TrimSpace(event.Name)
			if _, duplicate := seenNames[name]; duplicate {
				return nil, fmt.Errorf(
					"object %q declares event constant %q more than once",
					objectID,
					name,
				)
			}
			seenNames[name] = struct{}{}
			wireValue, err := WireValue(
				name,
				event.DeliverySemantics,
				event.WireEventType,
			)
			if err != nil {
				return nil, fmt.Errorf("object %q: %w", objectID, err)
			}
			definitions = append(definitions, Definition{
				ObjectID:          objectID,
				Name:              name,
				DeliverySemantics: strings.TrimSpace(event.DeliverySemantics),
				WireValue:         wireValue,
				ClientWSType:      strings.TrimSpace(event.ClientWSType),
			})
		}
		sort.Slice(definitions, func(i, j int) bool {
			return definitions[i].Name < definitions[j].Name
		})
		return definitions, nil
	}
	return nil, fmt.Errorf("object %q has no governance packet", objectID)
}

type GoRenderOptions struct {
	Generator            string
	Package              string
	AggregateRoot        string
	IncludeClientWSTypes bool
}

// RenderGo renders one existing object-local Go event package. Callers choose
// the already-canonical physical owner path; this function never invents one.
func RenderGo(options GoRenderOptions, definitions []Definition) ([]byte, error) {
	if strings.TrimSpace(options.Package) == "" {
		return nil, fmt.Errorf("Go event package is required")
	}
	if strings.TrimSpace(options.Generator) == "" {
		return nil, fmt.Errorf("Go event generator identity is required")
	}
	var buffer bytes.Buffer
	if err := goTemplate.Execute(&buffer, struct {
		Generator            string
		Package              string
		AggregateRoot        string
		Definitions          []Definition
		IncludeClientWSTypes bool
	}{
		Generator:            options.Generator,
		Package:              options.Package,
		AggregateRoot:        options.AggregateRoot,
		Definitions:          definitions,
		IncludeClientWSTypes: options.IncludeClientWSTypes,
	}); err != nil {
		return nil, fmt.Errorf("render Go event constants: %w", err)
	}
	formatted, err := format.Source(buffer.Bytes())
	if err != nil {
		return nil, fmt.Errorf("format Go event constants: %w", err)
	}
	return formatted, nil
}

// RenderPython emits the single Python runtime surface. Symbols include the
// canonical object identity so future objects cannot collide on a local event
// name.
func RenderPython(definitions []Definition) ([]byte, error) {
	outbox := make([]pythonDefinition, 0, len(definitions))
	seenSymbols := map[string]string{}
	seenRefs := map[string]struct{}{}
	for _, event := range definitions {
		if event.DeliverySemantics != TransactionalOutbox {
			continue
		}
		ref := event.ObjectID + "." + event.Name
		symbol := PythonSymbol(event.ObjectID, event.Name)
		if previous, duplicate := seenSymbols[symbol]; duplicate {
			return nil, fmt.Errorf(
				"Python event symbol %q is shared by %q and %q",
				symbol,
				previous,
				ref,
			)
		}
		if _, duplicate := seenRefs[ref]; duplicate {
			return nil, fmt.Errorf("event_ref %q is declared more than once", ref)
		}
		seenSymbols[symbol] = ref
		seenRefs[ref] = struct{}{}
		outbox = append(outbox, pythonDefinition{
			Symbol: symbol,
			Ref:    ref,
			Value:  event.WireValue,
		})
	}
	sort.Slice(outbox, func(i, j int) bool { return outbox[i].Ref < outbox[j].Ref })
	var buffer bytes.Buffer
	if err := pythonTemplate.Execute(&buffer, outbox); err != nil {
		return nil, fmt.Errorf("render Python event constants: %w", err)
	}
	return buffer.Bytes(), nil
}

func PythonSymbol(objectID, eventName string) string {
	return upperSnake(objectID + "_" + eventName)
}

type pythonDefinition struct {
	Symbol string
	Ref    string
	Value  string
}

func upperSnake(value string) string {
	var result []rune
	var previous rune
	for index, current := range []rune(value) {
		if !unicode.IsLetter(current) && !unicode.IsDigit(current) {
			if len(result) > 0 && result[len(result)-1] != '_' {
				result = append(result, '_')
			}
			previous = current
			continue
		}
		if index > 0 && unicode.IsUpper(current) &&
			(unicode.IsLower(previous) || unicode.IsDigit(previous)) &&
			len(result) > 0 && result[len(result)-1] != '_' {
			result = append(result, '_')
		}
		result = append(result, unicode.ToUpper(current))
		previous = current
	}
	return strings.Trim(string(result), "_")
}

var goTemplate = template.Must(template.New("event-constants-go").Parse(`// Code generated by {{.Generator}}. DO NOT EDIT.
package {{.Package}}
{{if .Definitions}}
// Event type constants for {{.AggregateRoot}}.
const (
{{- range .Definitions}}
	{{.Name}} = {{printf "%q" .WireValue}}
{{- end}}
)
{{end}}{{if .IncludeClientWSTypes}}
// ClientRealtimeWireTypes contains only events explicitly exposed by
// client_ws_type. Server-only domain events never enter realtime client fanout.
var ClientRealtimeWireTypes = map[string]string{
{{- range .Definitions}}{{if .ClientWSType}}
	{{.Name}}: {{printf "%q" .ClientWSType}},
{{- end}}{{end}}
}
{{end}}`))

var pythonTemplate = template.Must(template.New("event-constants-python").Parse(`# Code generated by tools/codegen_event_constants. DO NOT EDIT.
"""Canonical transactional-outbox event wire identities."""

{{range .}}{{.Symbol}} = {{printf "%q" .Value}}
{{end}}
EVENT_TYPES_BY_REF = {
{{- range .}}
	{{printf "%q" .Ref}}: {{.Symbol}},
{{- end}}
}
`))
