import 'dart:convert';

import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/app_cloud_operation_telemetry_sink.dart';
import 'package:quwoquan_app/runtime/observability/app_log_paths.dart';
import 'package:quwoquan_app/runtime/observability/app_log_policy.dart';
import 'package:quwoquan_app/runtime/observability/app_log_service.dart';
import 'package:quwoquan_app/runtime/observability/app_log_writer.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_text_file_storage_gateway.dart';

/// Reads the real production cloud-operation access log emitted by an API
/// contract runner.
///
/// This support does not implement [CloudOperationTelemetrySink] and does not
/// synthesize events. It composes [AppCloudOperationTelemetrySink] with the
/// production [AppLogService], [AppLogWriter] and platform file gateway, then
/// parses the isolated append-only `access.log` written by that pipeline.
final class ProductionCloudOperationTelemetryEvidence {
  ProductionCloudOperationTelemetryEvidence._({
    required this.sink,
    required this._storage,
    required this._paths,
    required this._rootPath,
    required this._startedAt,
  });

  static int _sequence = 0;

  final AppCloudOperationTelemetrySink sink;
  final LocalTextFileStorageGateway _storage;
  final AppLogPaths _paths;
  final String _rootPath;
  final DateTime _startedAt;

  static Future<ProductionCloudOperationTelemetryEvidence> start({
    required CloudClientContextProvider clientContextProvider,
  }) async {
    final storage = requireLocalTextFileStorageGateway(
      createFileStorageGateway(),
    );
    final suffix =
        '${DateTime.now().toUtc().microsecondsSinceEpoch}'
        '_${_sequence++}';
    final paths = AppLogPaths(
      storageGateway: storage,
      rootDirName: 'quwoquan_api_contract_telemetry/$suffix',
    );
    final root = await paths.rootDirectory();
    final writer = AppLogWriter(paths: paths, storageGateway: storage);
    final service = AppLogService.forTesting(
      writer: writer,
      policy: AppLogPolicy(isRelease: false),
    );
    return ProductionCloudOperationTelemetryEvidence._(
      sink: AppCloudOperationTelemetrySink(
        clientContextProvider: clientContextProvider,
        logService: service,
      ),
      storage: storage,
      paths: paths,
      rootPath: root.path,
      startedAt: DateTime.now(),
    );
  }

  Future<List<ProductionCloudOperationTelemetryEvent>> waitForEvents({
    required int minimumCount,
    Duration timeout = const Duration(seconds: 5),
    Duration quietPeriod = const Duration(milliseconds: 100),
  }) async {
    final deadline = DateTime.now().add(timeout);
    var events = const <ProductionCloudOperationTelemetryEvent>[];
    var observedCount = -1;
    DateTime? unchangedSince;
    while (DateTime.now().isBefore(deadline)) {
      events = await _readEvents();
      final now = DateTime.now();
      if (events.length != observedCount) {
        observedCount = events.length;
        unchangedSince = now;
      } else if (events.length >= minimumCount &&
          unchangedSince != null &&
          now.difference(unchangedSince) >= quietPeriod) {
        return events;
      }
      await Future<void>.delayed(const Duration(milliseconds: 25));
    }
    events = await _readEvents();
    if (events.length < minimumCount) {
      throw StateError(
        'production cloud-operation access.log emitted ${events.length} '
        'events; expected at least $minimumCount before $timeout',
      );
    }
    return events;
  }

  Future<void> dispose() async {
    if (await _storage.directoryExists(_rootPath)) {
      await _storage.deleteDirectory(_rootPath, recursive: true);
    }
  }

  Future<List<ProductionCloudOperationTelemetryEvent>> _readEvents() async {
    final now = DateTime.now();
    final days = <DateTime>{
      DateTime(_startedAt.year, _startedAt.month, _startedAt.day),
      DateTime(now.year, now.month, now.day),
    };
    final events = <ProductionCloudOperationTelemetryEvent>[];
    for (final day in days) {
      final directory = await _paths.dayDirectory(day);
      final path = _storage.joinPath(
        _storage.joinPath(directory.path, 'app'),
        'access.log',
      );
      if (!await _storage.exists(path)) {
        continue;
      }
      final text = await _storage.readAsString(path);
      for (final line in const LineSplitter().convert(text)) {
        final event = ProductionCloudOperationTelemetryEvent.tryParse(line);
        if (event != null) {
          events.add(event);
        }
      }
    }
    return events;
  }
}

final class ProductionCloudOperationTelemetryEvent {
  const ProductionCloudOperationTelemetryEvent({
    required this.canonicalOperationId,
    required this.succeeded,
    required this.requestId,
    required this.traceId,
    required this.statusCode,
  });

  final String canonicalOperationId;
  final bool succeeded;
  final String requestId;
  final String traceId;
  final int? statusCode;

  static ProductionCloudOperationTelemetryEvent? tryParse(String line) {
    final fields = line.split(',');
    if (fields.length < 9) {
      return null;
    }
    final message = fields.sublist(8).join(',');
    final attributesOffset = message.indexOf(' attrs=');
    if (attributesOffset < 0) {
      return null;
    }
    final attributesText = message.substring(attributesOffset + 7);
    final decoded = jsonDecode(attributesText);
    if (decoded is! Map<String, dynamic>) {
      return null;
    }
    final operationId = decoded['operationId'];
    if (operationId is! String || operationId.isEmpty) {
      return null;
    }
    return ProductionCloudOperationTelemetryEvent(
      canonicalOperationId: operationId,
      succeeded: fields[1] != 'ERROR',
      requestId: fields[6],
      traceId: fields[7],
      statusCode: int.tryParse(fields[4]),
    );
  }
}
