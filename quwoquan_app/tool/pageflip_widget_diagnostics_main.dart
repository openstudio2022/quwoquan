import 'package:flutter/material.dart';
import '../test/support/runtime/pageflip/pageflip_diagnostics.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PageflipWidgetDiagnosticsApp());
}
