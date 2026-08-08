package main

import (
	"fmt"
	"os"
	"path"
	"path/filepath"

	"quwoquan_service/internal/metadata/codegen/eventconstants"
	"quwoquan_service/internal/metadata/graph"
)

type eventDef struct {
	Name              string `yaml:"name"`
	DeliverySemantics string `yaml:"delivery_semantics"`
	WireEventType     string `yaml:"wire_event_type"`
}

func (event eventDef) ConstantValue() (string, error) {
	return eventconstants.WireValue(
		event.Name,
		event.DeliverySemantics,
		event.WireEventType,
	)
}

// generateMergedEventConstants merges events.yaml from all sources sharing the same
// domain_pkg and writes a single events.g.go per package. This prevents overwriting
// when multiple metadata sources map to the same Go package.
func generateMergedEventConstants(
	manifest *Manifest,
	contractGraph *graph.ContractGraph,
) error {
	for _, src := range manifest.Sources {
		eventsPath := filepath.ToSlash(filepath.Join(src.Metadata, "events.yaml"))
		if !contractGraph.HasDocument(eventsPath) {
			continue
		}
		objectID, aggregateRoot, err := eventObjectForMetadataPath(
			contractGraph,
			src.Metadata,
		)
		if err != nil {
			return err
		}
		definitions, err := eventconstants.DefinitionsForObject(contractGraph, objectID)
		if err != nil {
			return fmt.Errorf("event constants for %s: %w", objectID, err)
		}
		dir := filepath.Join(
			manifest.OutputDir,
			src.ObjectPath,
			"contract",
			src.domainPath(),
			"event",
		)
		if err := os.MkdirAll(dir, 0755); err != nil {
			return err
		}
		generated, err := eventconstants.RenderGo(
			eventconstants.GoRenderOptions{
				Generator:     "codegen_storage",
				Package:       src.DomainPkg,
				AggregateRoot: aggregateRoot,
			},
			definitions,
		)
		if err != nil {
			return fmt.Errorf("render events for %s: %w", objectID, err)
		}
		path := filepath.Join(dir, "events.g.go")
		fmt.Printf("  events: %s/events.g.go\n", src.ObjectPath)
		if err := os.WriteFile(path, generated, 0644); err != nil {
			return err
		}
	}
	return nil
}

func eventObjectForMetadataPath(
	contractGraph *graph.ContractGraph,
	metadataPath string,
) (string, string, error) {
	metadataPath = path.Clean(filepath.ToSlash(metadataPath))
	for _, object := range contractGraph.Objects {
		if path.Dir(object.SourcePath) == metadataPath {
			return object.ID, object.Name, nil
		}
	}
	return "", "", fmt.Errorf(
		"event metadata path %q has no canonical object",
		metadataPath,
	)
}
