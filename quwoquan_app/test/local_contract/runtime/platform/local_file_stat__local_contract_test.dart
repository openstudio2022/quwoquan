import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/local_file_stat.dart';

void main() {
  test('local file stat reports canonical existence and byte length', () async {
    final directory = await Directory.systemTemp.createTemp('qwq-file-stat-');
    addTearDown(() => directory.delete(recursive: true));
    final file = File('${directory.path}/sample.bin');
    await file.writeAsBytes(<int>[1, 2, 3, 4]);

    final stat = await readLocalFileStat(file.path);

    expect(stat.exists, isTrue);
    expect(stat.length, 4);
  });

  test('local file stat returns a closed missing-file result', () async {
    final directory = await Directory.systemTemp.createTemp('qwq-file-stat-');
    addTearDown(() => directory.delete(recursive: true));

    final stat = await readLocalFileStat('${directory.path}/missing.bin');

    expect(stat.exists, isFalse);
    expect(stat.length, 0);
  });
}
