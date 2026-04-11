package main

import (
	"fmt"
	"path/filepath"
)

// writeRtcCallSessionDtos generates CallParticipantDto + CallSessionDto from
// contracts/metadata/rtc/call_session/fields.yaml (entities CallParticipant, CallSession).
func writeRtcCallSessionDtos(appDir, metadataDir string) error {
	fieldsPath := filepath.Join(metadataDir, "rtc", "call_session", "fields.yaml")
	ff, err := readFields(fieldsPath)
	if err != nil {
		return fmt.Errorf("rtc read fields: %w", err)
	}
	_, okS := ff.Entities["CallSession"]
	_, okP := ff.Entities["CallParticipant"]
	if !okS || !okP {
		return fmt.Errorf("rtc fields: missing CallSession or CallParticipant entity")
	}
	out := renderRtcCallSessionDtosDartFromFields(fieldsPath, ff)
	outPath := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "rtc", "call_session_dtos.g.dart")
	writeFile(outPath, out)
	return nil
}
