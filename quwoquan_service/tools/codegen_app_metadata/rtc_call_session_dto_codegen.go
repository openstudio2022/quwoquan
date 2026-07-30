package main

import (
	"fmt"
	"path/filepath"
)

// writeRtcCallSessionDtos generates CallParticipantDto + CallSessionDto from
// services/rtc-service/contracts/rtc/call_session/fields.yaml (entities CallParticipant, CallSession).
func writeRtcCallSessionDtos(appDir, metadataDir string) error {
	fieldsPath := filepath.Join(metadataDir, "rtc", "rtc", "call_session", "fields.yaml")
	ff, err := readFields(fieldsPath)
	if err != nil {
		return fmt.Errorf("rtc read fields: %w", err)
	}
	_, okS := ff.Entities["CallSession"]
	_, okP := ff.Entities["CallParticipant"]
	if !okS || !okP {
		return fmt.Errorf("rtc fields: missing CallSession or CallParticipant entity")
	}
	shared, err := readShared(filepath.Join(metadataDir, "_shared", "types.yaml"))
	if err != nil {
		return fmt.Errorf("rtc read shared enum catalog: %w", err)
	}
	out := renderRtcCallSessionDtosDartFromFields(
		metadataSourceLabel(fieldsPath),
		ff,
		shared.Enums,
	)
	outPath := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"rtc",
		"call_session_dtos.g.dart",
	)
	writeFile(outPath, out)
	return nil
}
