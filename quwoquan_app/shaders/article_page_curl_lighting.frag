#include <flutter/runtime_effect.glsl>

precision mediump float;

uniform vec2 uSize;
uniform float uProgress;
uniform float uDirection;
uniform float uFold;
uniform float uLift;
uniform float uTunnelStrength;
uniform float uHighlightStrength;
uniform float uShadowStrength;
uniform vec4 uShadowColor;
uniform vec4 uHighlightColor;
uniform vec4 uAmbientColor;
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
  float tunnelWidth = mix(16.0, 34.0, clamp(uLift, 0.0, 1.0));
  float tunnel = exp(-foldDistance * tunnelWidth) * uTunnelStrength;
  float rim = exp(-foldDistance * 92.0) * uHighlightStrength;
  float ambient = smoothstep(0.0, 0.62, edge) * uShadowStrength;
  float verticalAttenuation = mix(0.62, 1.0, 1.0 - abs(pageUv.y - 0.5) * 1.3);
  vec4 color = vec4(0.0);
  color += uShadowColor * tunnel * verticalAttenuation;
  color += uHighlightColor * rim;
  color += uAmbientColor * ambient * 0.36;
  fragColor = color;
}
