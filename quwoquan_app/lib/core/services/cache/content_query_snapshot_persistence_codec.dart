part of 'content_cache_services.dart';

String? _encodePersistableSnapshotPayload({
  required Iterable<Iterable<ContentQuerySnapshot>> snapshotChains,
  required int maxPersistedBytes,
}) {
  const prefix = '{"snapshots":[';
  const suffix = ']}';
  final prefixBytes = _utf8WireLength(prefix);
  final suffixBytes = _utf8WireLength(suffix);
  if (maxPersistedBytes < prefixBytes + suffixBytes) {
    return null;
  }

  final buffer = StringBuffer(prefix);
  var payloadBytesWithoutSuffix = prefixBytes;
  var hasSnapshot = false;
  for (final chain in snapshotChains) {
    for (final snapshot in chain) {
      // 单个 snapshot 是最小持久化原子。先以无输出的有界 writer 做精确
      // UTF-8 预检，再逐字段、逐 item 写入最终 payload；不会先物化整页 Map/List
      // 与局部 JSON String，也不会截断 items 后保留跳跃 cursor。
      final separatorBytes = hasSnapshot ? 1 : 0;
      final remainingSnapshotBytes =
          maxPersistedBytes -
          payloadBytesWithoutSuffix -
          separatorBytes -
          suffixBytes;
      final snapshotBytes = _measureSnapshotWireBytes(
        snapshot,
        maxBytes: remainingSnapshotBytes,
      );
      if (snapshotBytes == null) {
        break;
      }
      if (hasSnapshot) {
        buffer.write(',');
        payloadBytesWithoutSuffix += separatorBytes;
      }
      final writer = _BoundedJsonWriter(
        maxBytes: snapshotBytes,
        output: buffer,
      );
      _writeSnapshotJson(writer, snapshot);
      payloadBytesWithoutSuffix += snapshotBytes;
      hasSnapshot = true;
    }
  }
  buffer.write(suffix);
  return buffer.toString();
}

int? _measureSnapshotWireBytes(
  ContentQuerySnapshot snapshot, {
  required int maxBytes,
}) {
  if (maxBytes < 0) {
    return null;
  }
  final writer = _BoundedJsonWriter(maxBytes: maxBytes);
  try {
    _writeSnapshotJson(writer, snapshot);
    return writer.byteLength;
  } on _JsonWireBudgetExceeded {
    return null;
  } on _PostSnapshotFieldBudgetExceeded {
    return null;
  }
}

void _writeSnapshotJson(
  _BoundedJsonWriter writer,
  ContentQuerySnapshot snapshot,
) {
  writer.writeRaw('{');
  _writeJsonField(writer, 'key', snapshot.key);
  writer.writeRaw(',');
  writer.writeString('items');
  writer.writeRaw(':[');
  var hasItem = false;
  for (final post in snapshot.items) {
    if (hasItem) {
      writer.writeRaw(',');
    }
    final postMap = _postSnapshotMap(post);
    _validatePostSnapshotFieldByteLimits(postMap);
    writer.writeValue(postMap);
    hasItem = true;
  }
  writer.writeRaw(']');
  writer.writeRaw(',');
  _writeJsonField(writer, 'nextCursor', snapshot.nextCursor);
  writer.writeRaw(',');
  _writeJsonField(writer, 'previousCursor', snapshot.previousCursor);
  writer.writeRaw(',');
  _writeJsonField(
    writer,
    'paginationExpiresAt',
    snapshot.paginationExpiresAt?.toUtc().toIso8601String(),
  );
  writer.writeRaw(',');
  _writeJsonField(writer, 'paginationSessionId', snapshot.paginationSessionId);
  writer.writeRaw(',');
  _writeJsonField(
    writer,
    'fetchedAt',
    snapshot.fetchedAt.toUtc().toIso8601String(),
  );
  writer.writeRaw(',');
  _writeJsonField(writer, 'feedRequestId', snapshot.feedRequestId);
  writer.writeRaw(',');
  _writeJsonField(writer, 'policyDigest', snapshot.policyDigest);
  writer.writeRaw(',');
  _writeJsonField(writer, 'outcome', snapshot.outcome.name);
  writer.writeRaw(',');
  _writeJsonField(
    writer,
    'emptyReason',
    _feedEmptyReasonToWire(snapshot.emptyReason),
  );
  writer.writeRaw('}');
}

void _writeJsonField(_BoundedJsonWriter writer, String key, Object? value) {
  writer.writeString(key);
  writer.writeRaw(':');
  writer.writeValue(value);
}

final class _JsonWireBudgetExceeded implements Exception {
  const _JsonWireBudgetExceeded();
}

final class _PostSnapshotFieldBudgetExceeded implements Exception {
  const _PostSnapshotFieldBudgetExceeded();
}

void _validatePostSnapshotFieldByteLimits(Map<String, dynamic> post) {
  for (final entry
      in GeneratedPostRuntimeMetadata.postSnapshotFieldByteLimits.entries) {
    final value = post[entry.key];
    if (value is String &&
        _utf8WireLength(value, stopAfter: entry.value) > entry.value) {
      throw const _PostSnapshotFieldBudgetExceeded();
    }
  }
}

final class _BoundedJsonWriter {
  _BoundedJsonWriter({required this.maxBytes, this.output});

  final int maxBytes;
  final StringBuffer? output;
  final Set<Object> _activeContainers = HashSet<Object>.identity();
  int _byteLength = 0;

  int get byteLength => _byteLength;

  void writeValue(Object? value) {
    if (value == null) {
      writeRaw('null');
      return;
    }
    if (value is String) {
      writeString(value);
      return;
    }
    if (value is bool) {
      writeRaw(value ? 'true' : 'false');
      return;
    }
    if (value is num) {
      if (value is double && !value.isFinite) {
        throw FormatException('Non-finite JSON number: $value');
      }
      writeRaw(value.toString());
      return;
    }
    if (value is DateTime) {
      writeString(value.toUtc().toIso8601String());
      return;
    }
    if (value is Map) {
      _withCycleGuard(value, () => _writeMap(value));
      return;
    }
    if (value is Iterable) {
      _withCycleGuard(value, () => _writeIterable(value));
      return;
    }
    _withCycleGuard(value, () {
      final dynamic structuredValue = value;
      final Object? converted = structuredValue.toMap();
      if (identical(converted, value)) {
        throw FormatException(
          'JSON structured value returned itself: ${value.runtimeType}',
        );
      }
      writeValue(converted);
    });
  }

  void writeString(String value) {
    writeRaw('"');
    var segmentStart = 0;
    for (var index = 0; index < value.length; index += 1) {
      final codeUnit = value.codeUnitAt(index);
      String? escape;
      switch (codeUnit) {
        case 0x08:
          escape = r'\b';
        case 0x09:
          escape = r'\t';
        case 0x0a:
          escape = r'\n';
        case 0x0c:
          escape = r'\f';
        case 0x0d:
          escape = r'\r';
        case 0x22:
          escape = r'\"';
        case 0x5c:
          escape = r'\\';
        default:
          if (codeUnit < 0x20 || _isUnpairedSurrogate(value, index)) {
            escape = '\\u${codeUnit.toRadixString(16).padLeft(4, '0')}';
          } else if (_isLeadingSurrogate(codeUnit)) {
            index += 1;
          }
      }
      if (escape == null) {
        if (index - segmentStart + 1 >= _maxStringChunkCodeUnits) {
          writeRaw(value.substring(segmentStart, index + 1));
          segmentStart = index + 1;
        }
        continue;
      }
      if (segmentStart < index) {
        writeRaw(value.substring(segmentStart, index));
      }
      writeRaw(escape);
      segmentStart = index + 1;
    }
    if (segmentStart < value.length) {
      writeRaw(value.substring(segmentStart));
    }
    writeRaw('"');
  }

  void writeRaw(String value) {
    final nextLength = _byteLength + _utf8WireLength(value);
    if (nextLength > maxBytes) {
      throw const _JsonWireBudgetExceeded();
    }
    output?.write(value);
    _byteLength = nextLength;
  }

  void _writeMap(Map<dynamic, dynamic> value) {
    writeRaw('{');
    var hasEntry = false;
    for (final entry in value.entries) {
      if (hasEntry) {
        writeRaw(',');
      }
      writeString(entry.key.toString());
      writeRaw(':');
      writeValue(entry.value);
      hasEntry = true;
    }
    writeRaw('}');
  }

  void _writeIterable(Iterable<dynamic> value) {
    writeRaw('[');
    var hasItem = false;
    for (final item in value) {
      if (hasItem) {
        writeRaw(',');
      }
      writeValue(item);
      hasItem = true;
    }
    writeRaw(']');
  }

  void _withCycleGuard(Object value, void Function() write) {
    if (!_activeContainers.add(value)) {
      throw FormatException('Cyclic JSON value: ${value.runtimeType}');
    }
    try {
      write();
    } finally {
      _activeContainers.remove(value);
    }
  }
}

// JSON 处理分块只控制编码临时对象峰值，不是业务字段或持久化预算。
const int _maxStringChunkCodeUnits = 1024;

bool _isLeadingSurrogate(int codeUnit) {
  return codeUnit >= 0xd800 && codeUnit <= 0xdbff;
}

bool _isTrailingSurrogate(int codeUnit) {
  return codeUnit >= 0xdc00 && codeUnit <= 0xdfff;
}

bool _isUnpairedSurrogate(String value, int index) {
  final codeUnit = value.codeUnitAt(index);
  if (_isLeadingSurrogate(codeUnit)) {
    return index + 1 >= value.length ||
        !_isTrailingSurrogate(value.codeUnitAt(index + 1));
  }
  if (_isTrailingSurrogate(codeUnit)) {
    return index == 0 || !_isLeadingSurrogate(value.codeUnitAt(index - 1));
  }
  return false;
}

int _utf8WireLength(String value, {int? stopAfter}) {
  var byteLength = 0;
  for (var index = 0; index < value.length; index += 1) {
    final codeUnit = value.codeUnitAt(index);
    if (codeUnit <= 0x7f) {
      byteLength += 1;
    } else if (codeUnit <= 0x7ff) {
      byteLength += 2;
    } else if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      if (index + 1 < value.length) {
        final nextCodeUnit = value.codeUnitAt(index + 1);
        if (nextCodeUnit >= 0xdc00 && nextCodeUnit <= 0xdfff) {
          byteLength += 4;
          index += 1;
        } else {
          byteLength += 3;
        }
      } else {
        byteLength += 3;
      }
    } else {
      byteLength += 3;
    }
    if (stopAfter != null && byteLength > stopAfter) {
      return byteLength;
    }
  }
  return byteLength;
}
