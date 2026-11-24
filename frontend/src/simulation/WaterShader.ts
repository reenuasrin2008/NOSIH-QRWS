import * as THREE from "three";

const WATER_VERTEX = `
  uniform float uTime;
  uniform float uWaveScale;
  varying vec3 vWorldPos;
  varying vec2 vUv;

  void main() {
    vUv = uv;
    vec4 wp = modelMatrix * vec4(position, 1.0);
    // Subtle physical vertical wave displacement
    float w1 = sin(wp.x * 0.018 + uTime * 1.45) * cos(wp.z * 0.014 + uTime * 1.1);
    float w2 = sin(wp.x * 0.042 - uTime * 2.1 + wp.z * 0.031) * 0.45;
    wp.y += (w1 + w2) * uWaveScale;
    vWorldPos = wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const WATER_FRAGMENT = `
  uniform float uTime;
  uniform vec3 uDeepColor;
  uniform vec3 uShallowColor;
  uniform vec3 uSkyColor;
  uniform vec3 uSunDir;
  uniform vec3 uSunColor;
  uniform float uOpacity;
  varying vec3 vWorldPos;
  varying vec2 vUv;

  // Procedural multi-octave wave normal perturbation
  vec3 getWaveNormal(vec2 p, float t) {
    float e = 0.35;
    float h0 = sin(p.x * 0.035 + t * 1.6) * cos(p.y * 0.028 + t * 1.2)
             + sin(p.x * 0.085 - t * 2.3 + p.y * 0.062) * 0.45
             + cos(p.x * 0.16 + p.y * 0.19 - t * 3.1) * 0.18;
    float hx = sin((p.x + e) * 0.035 + t * 1.6) * cos(p.y * 0.028 + t * 1.2)
             + sin((p.x + e) * 0.085 - t * 2.3 + p.y * 0.062) * 0.45
             + cos((p.x + e) * 0.16 + p.y * 0.19 - t * 3.1) * 0.18;
    float hz = sin(p.x * 0.035 + t * 1.6) * cos((p.y + e) * 0.028 + t * 1.2)
             + sin(p.x * 0.085 - t * 2.3 + (p.y + e) * 0.062) * 0.45
             + cos(p.x * 0.16 + (p.y + e) * 0.19 - t * 3.1) * 0.18;
    vec3 n = normalize(vec3((h0 - hx) * 1.35, 1.0, (h0 - hz) * 1.35));
    return n;
  }

  void main() {
    vec3 N = getWaveNormal(vWorldPos.xz, uTime);
    vec3 V = normalize(cameraPosition - vWorldPos);
    vec3 L = normalize(uSunDir);

    // Schlick Fresnel sky reflection
    float fresnel = pow(1.0 - max(dot(N, V), 0.0), 3.6);
    fresnel = clamp(0.12 + fresnel * 0.78, 0.0, 0.92);

    // Base water depth gradient
    float waveCrest = clamp(N.x * 0.5 + N.z * 0.5 + 0.5, 0.0, 1.0);
    vec3 baseWater = mix(uDeepColor, uShallowColor, waveCrest * 0.55);

    // Sunlit specular glints on ripples
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(N, H), 0.0), 96.0);
    float broadSpec = pow(max(dot(N, H), 0.0), 18.0) * 0.18;

    // Subtle animated foam streaks near edges
    float edgeMask = smoothstep(0.0, 0.08, vUv.x) * smoothstep(0.0, 0.08, 1.0 - vUv.x)
                   * smoothstep(0.0, 0.08, vUv.y) * smoothstep(0.0, 0.08, 1.0 - vUv.y);
    float foamNoise = sin(vWorldPos.x * 0.09 + uTime * 2.2) * cos(vWorldPos.z * 0.09 - uTime * 1.7);
    float foam = (1.0 - edgeMask) * smoothstep(0.15, 0.75, foamNoise * 0.5 + 0.5) * 0.45;

    vec3 color = mix(baseWater, uSkyColor, fresnel * 0.62);
    color += uSunColor * (spec * 1.35 + broadSpec);
    color = mix(color, vec3(0.88, 0.93, 0.97), foam);

    gl_FragColor = vec4(color, uOpacity);
  }
`;

export function createRealisticWaterMaterial(dayMode: boolean, waveScale = 0.75, opacity = 0.96): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: WATER_VERTEX,
    fragmentShader: WATER_FRAGMENT,
    transparent: opacity < 0.99,
    uniforms: {
      uTime: { value: 0 },
      uWaveScale: { value: waveScale },
      uDeepColor: { value: new THREE.Color(dayMode ? "#0e3b5c" : "#061524") },
      uShallowColor: { value: new THREE.Color(dayMode ? "#1f6a8c" : "#0e2942") },
      uSkyColor: { value: new THREE.Color(dayMode ? "#9ec4e2" : "#1a2840") },
      uSunDir: { value: new THREE.Vector3(0.55, dayMode ? 0.65 : 0.42, -0.52).normalize() },
      uSunColor: { value: new THREE.Color(dayMode ? "#fff4d6" : "#8ab4f8") },
      uOpacity: { value: opacity },
    },
  });
}
