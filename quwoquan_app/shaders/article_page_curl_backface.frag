#include <flutter/runtime_effect.glsl>

precision mediump float;

uniform vec2 uSize;
uniform float uProgress;
uniform float uDirection;
uniform float uFold;
uniform float uTintStrength;
uniform float uOcclusionStrength;
uniform vec4 uPaperTint;
uniform vec4 uOcclusionColor;
uniform vec4 uPageRect;

out vec4 fragColor;

void main() {
  vec2 safePageSize = max(uPageRect.zw, vec2(1.0));
  vec2 pageUv = clamp(
    (FlutterFragCoord().xy - uPageRect.xy) / safePageSize,
    vec2(0.0),
    vec2(1.0)
  );
  float edge = uDirection > 0.5 ? 1.0 - pageUv.x : pageUv.x;
  float foldDistance = abs(pageUv.x - uFold);
  float tint = mix(0.035, 0.12, clamp(uProgress, 0.0, 1.0)) * uTintStrength;
  float occlusion = exp(-foldDistance * 18.0) * min(uOcclusionStrength, 0.36);
  float paperWash = mix(0.9, 1.0, pageUv.y);
  float readabilityFloor = 0.008 + 0.014 * (1.0 - smoothstep(0.0, 0.28, foldDistance));
  vec4 color = vec4(0.0);
  color += vec4(1.0, 1.0, 1.0, readabilityFloor * uTintStrength);
  color += uPaperTint * tint * paperWash;
  color += uOcclusionColor * min(0.12, occlusion * 0.28);
  color += uOcclusionColor * min(0.018, edge * 0.018);
  fragColor = color;
}
