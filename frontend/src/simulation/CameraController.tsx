import React, { useRef, useEffect } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { DroneState } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

export const CameraController: React.FC<{ drones: DroneState[]; worldSize: number }> = ({ drones, worldSize }) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const controlsRef = useRef<any>(null);
  const { camera } = useThree();
  const cameraMode = useSimStore((s) => s.cameraMode);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const focusPoint = useSimStore((s) => s.cameraFocusPoint);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);
  const activeState = useSimStore((s) => s.activeState);

  const half = worldSize / 2;
  const glideGoalCam = useRef<THREE.Vector3 | null>(null);
  const glideGoalTarget = useRef<THREE.Vector3 | null>(null);
  const keys = useRef<Record<string, boolean>>({});
  const forwardVec = useRef(new THREE.Vector3());
  const rightVec = useRef(new THREE.Vector3());
  const moveVec = useRef(new THREE.Vector3());

  useEffect(() => {
    const onDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      keys.current[e.code] = true;
    };
    const onUp = (e: KeyboardEvent) => {
      keys.current[e.code] = false;
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, []);

  useEffect(() => {
    if (cameraMode === "topdown") {
      glideGoalCam.current = new THREE.Vector3(half, worldSize * 0.85, half + 20);
      glideGoalTarget.current = new THREE.Vector3(half, 0, half);
    } else if (cameraMode === "orbit") {
      glideGoalCam.current = new THREE.Vector3(half * 0.28, worldSize * 0.24, worldSize * 0.88);
      glideGoalTarget.current = new THREE.Vector3(half, 30, half);
    } else if (cameraMode === "disaster_focus") {
      const activeDisasters = (activeState?.disasters || []).filter((d) => d.status !== "RESOLVED");
      const latest = activeDisasters[activeDisasters.length - 1];
      if (latest) {
        const { x, z } = latest.epicentre;
        glideGoalTarget.current = new THREE.Vector3(x, 20, z);
        glideGoalCam.current = new THREE.Vector3(x - 320, 290, z + 320);
      }
    }
  }, [cameraMode, half, worldSize, activeState?.disasters]);

  useEffect(() => {
    if (focusPoint) {
      glideGoalTarget.current = new THREE.Vector3(focusPoint[0], focusPoint[1], focusPoint[2]);
      glideGoalCam.current = new THREE.Vector3(focusPoint[0] - 260, focusPoint[1] + 240, focusPoint[2] + 260);
      setCameraFocusPoint(null);
    }
  }, [focusPoint, setCameraFocusPoint]);

  useFrame(({ clock }, delta) => {
    if (!controlsRef.current) return;

    // Subtle damped camera tremor when an active earthquake is shaking the city
    const activeQuake = (activeState?.disasters || []).find(
      (d) => d.type === "earthquake" && (d.status === "ACTIVE" || d.status === "INTENSIFYING" || d.status === "PROPAGATING")
    );
    if (activeQuake && activeQuake.elapsed_time < 40) {
      const t = clock.getElapsedTime();
      const amp = activeQuake.severity * 1.4;
      camera.position.x += Math.sin(t * 38) * amp;
      camera.position.y += Math.cos(t * 44) * amp * 0.5;
    }

    const k = keys.current;
    const fInput = (k["KeyW"] || k["ArrowUp"] ? 1 : 0) - (k["KeyS"] || k["ArrowDown"] ? 1 : 0);
    const rInput = (k["KeyD"] || k["ArrowRight"] ? 1 : 0) - (k["KeyA"] || k["ArrowLeft"] ? 1 : 0);
    const uInput = (k["KeyE"] ? 1 : 0) - (k["KeyQ"] ? 1 : 0);

    if (fInput !== 0 || rInput !== 0 || uInput !== 0) {
      glideGoalCam.current = null;
      glideGoalTarget.current = null;
      const boost = k["ShiftLeft"] || k["ShiftRight"] ? 2.4 : 1.0;
      const speed = Math.max(240, camera.position.y * 0.95) * boost * delta;

      camera.getWorldDirection(forwardVec.current);
      forwardVec.current.y = 0;
      if (forwardVec.current.lengthSq() > 1e-4) forwardVec.current.normalize();
      rightVec.current.crossVectors(forwardVec.current, camera.up).normalize();

      moveVec.current.set(0, 0, 0);
      moveVec.current.addScaledVector(forwardVec.current, fInput * speed);
      moveVec.current.addScaledVector(rightVec.current, rInput * speed);
      moveVec.current.y = uInput * speed * 0.7;

      camera.position.add(moveVec.current);
      camera.position.y = Math.max(35, Math.min(worldSize * 1.15, camera.position.y));
      controlsRef.current.target.add(new THREE.Vector3(moveVec.current.x, 0, moveVec.current.z));
      controlsRef.current.update();
      return;
    }

    if (cameraMode === "fpv" && selectedDroneId) {
      const d = drones.find((item) => item.id === selectedDroneId);
      if (d) {
        const fx = Math.sin(d.heading_rad);
        const fz = Math.cos(d.heading_rad);
        const camPos = new THREE.Vector3(d.position[0] + fx * 12, d.position[1] - 3.5, d.position[2] + fz * 12);
        const lookAt = new THREE.Vector3(d.position[0] + fx * 180, Math.max(0, d.position[1] - 42), d.position[2] + fz * 180);
        camera.position.lerp(camPos, 1 - Math.exp(-8.5 * delta));
        controlsRef.current.target.lerp(lookAt, 1 - Math.exp(-8.5 * delta));
        controlsRef.current.update();
      }
      return;
    }

    if (cameraMode === "follow" && selectedDroneId) {
      const d = drones.find((item) => item.id === selectedDroneId);
      if (d) {
        const target = new THREE.Vector3(d.position[0], d.position[1], d.position[2]);
        const desiredCam = new THREE.Vector3(d.position[0] - 130, d.position[1] + 85, d.position[2] + 130);
        camera.position.lerp(desiredCam, 1 - Math.exp(-4.5 * delta));
        controlsRef.current.target.lerp(target, 1 - Math.exp(-6.5 * delta));
        controlsRef.current.update();
      }
      return;
    }

    if (glideGoalCam.current && glideGoalTarget.current) {
      const alpha = 1 - Math.exp(-5.0 * delta);
      camera.position.lerp(glideGoalCam.current, alpha);
      controlsRef.current.target.lerp(glideGoalTarget.current, alpha);
      controlsRef.current.update();
      if (camera.position.distanceTo(glideGoalCam.current) < 4.0) {
        glideGoalCam.current = null;
        glideGoalTarget.current = null;
      }
    }
  });

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.07}
      maxPolarAngle={Math.PI / 2.04}
      minDistance={60}
      maxDistance={worldSize * 1.45}
      target={[half, 30, half]}
      onStart={() => {
        glideGoalCam.current = null;
        glideGoalTarget.current = null;
      }}
    />
  );
};
