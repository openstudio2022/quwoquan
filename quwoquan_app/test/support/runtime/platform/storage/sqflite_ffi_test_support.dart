import 'package:sqflite_common_ffi/sqflite_ffi.dart';

bool _sqfliteFfiInitialized = false;

/// VM/CI 单测使用 in-memory 或文件库时初始化 sqflite FFI。
void ensureSqfliteFfiInitialized() {
  if (_sqfliteFfiInitialized) {
    return;
  }
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;
  _sqfliteFfiInitialized = true;
}
