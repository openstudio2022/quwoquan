import 'dart:io';

import 'package:flutter/widgets.dart';

ImageProvider<Object> createLocalFileImageProvider(String path) {
  return FileImage(File(path));
}
