import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

const String kHslAxisHue = 'hue';
const String kHslAxisSaturation = 'saturation';
const String kHslAxisLuminance = 'luminance';

class ImageEditorHslChannel {
  const ImageEditorHslChannel({
    required this.key,
    required this.label,
    required this.color,
    required this.hueMin,
    required this.hueMax,
  });

  final String key;
  final String label;
  final Color color;
  final double hueMin;
  final double hueMax;

  bool containsHue(double hue) {
    final normalized = ((hue % 360) + 360) % 360;
    if (hueMin <= hueMax) {
      return normalized >= hueMin && normalized < hueMax;
    }
    return normalized >= hueMin || normalized < hueMax;
  }
}

const List<ImageEditorHslChannel> kImageEditorHslChannels = [
  ImageEditorHslChannel(
    key: 'red',
    label: UITextConstants.imageEditorProChannelRed,
    color: Color(0xFFE85656),
    hueMin: 345,
    hueMax: 15,
  ),
  ImageEditorHslChannel(
    key: 'orange',
    label: UITextConstants.imageEditorProChannelOrange,
    color: Color(0xFFE79A4B),
    hueMin: 15,
    hueMax: 45,
  ),
  ImageEditorHslChannel(
    key: 'yellow',
    label: UITextConstants.imageEditorProChannelYellow,
    color: Color(0xFFDED95A),
    hueMin: 45,
    hueMax: 75,
  ),
  ImageEditorHslChannel(
    key: 'green',
    label: UITextConstants.imageEditorProChannelGreen,
    color: Color(0xFF70D85C),
    hueMin: 75,
    hueMax: 165,
  ),
  ImageEditorHslChannel(
    key: 'cyan',
    label: UITextConstants.imageEditorProChannelCyan,
    color: Color(0xFF4DCFD2),
    hueMin: 165,
    hueMax: 195,
  ),
  ImageEditorHslChannel(
    key: 'blue',
    label: UITextConstants.imageEditorProChannelBlue,
    color: Color(0xFF4D73DE),
    hueMin: 195,
    hueMax: 255,
  ),
  ImageEditorHslChannel(
    key: 'purple',
    label: UITextConstants.imageEditorProChannelPurple,
    color: Color(0xFF9B57D8),
    hueMin: 255,
    hueMax: 315,
  ),
  ImageEditorHslChannel(
    key: 'magenta',
    label: UITextConstants.imageEditorProChannelMagenta,
    color: Color(0xFFD84FC7),
    hueMin: 315,
    hueMax: 345,
  ),
];

Map<String, Map<String, double>> createDefaultHslValues() => {
      for (final channel in kImageEditorHslChannels)
        channel.key: {
          kHslAxisHue: 0,
          kHslAxisSaturation: 0,
          kHslAxisLuminance: 0,
        },
    };

Map<String, Map<String, double>> cloneHslValues(
  Map<String, Map<String, double>> source,
) {
  return {
    for (final entry in source.entries)
      entry.key: {
        for (final axis in entry.value.entries) axis.key: axis.value,
      },
  };
}

String hslChannelKeyFromHue(double hue) {
  for (final channel in kImageEditorHslChannels) {
    if (channel.containsHue(hue)) return channel.key;
  }
  return kImageEditorHslChannels.first.key;
}
