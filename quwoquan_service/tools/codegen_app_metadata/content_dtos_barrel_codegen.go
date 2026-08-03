package main

import "strings"

// Barrel: App-owned post presentation plus generated metadata helpers.
// Cloud wire models are exported only by quwoquan_cloud_contracts.
func renderContentDtosBarrelDart() string {
	var b strings.Builder
	b.WriteString(`// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: tools/codegen_app_metadata/content_dtos_barrel_codegen.go
// Regenerate: make codegen-app (from quwoquan_service)

export 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
export 'report_create_request_wire.g.dart';
export 'post_read_surface_id.g.dart';
export 'article_detail_wire_keys.g.dart';
export 'content_post_immersive_wire_keys.g.dart';
export 'content_app_config_client_dto.g.dart';
export 'post_read_presentation.g.dart';
`)
	return b.String()
}
