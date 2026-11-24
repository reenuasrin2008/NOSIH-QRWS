import React, { useRef, useEffect } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { DroneState } from "../types/simulation";
import { useSimStore } from "../state/simulationStore";

/** Frame-rate-independent 3D vector damping powered by THREE.MathUtils.damp. */
function damp3(
  current: THREE.Vector3,
  target: THREE.Vector3,
  lambda: number,
  delta: number
): void {
  if (
    !Number.isFinite(target.x) ||
    !Number.isFinite(target.y) ||
    !Number.isFinite(target.z) ||
    !Number.isFinite(delta)
  ) {
    return;
  }
  current.x = THREE.MathUtils.damp(current.x, target.x, lambda, delta);
  current.y = THREE.MathUtils.damp(current.y, target.y, lambda, delta);
  current.z = THREE.MathUtils.damp(current.z, target.z, lambda, delta);
}

export const CameraController: React.FC<{ drones: DroneState[]; worldSize: number }> = ({
  drones,
  worldSize,
}) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const controlsRef = useRef<any>(null);
  const { camera } = useThree();
  const cameraMode = useSimStore((s) => s.cameraMode);
  const selectedDroneId = useSimStore((s) => s.selectedDroneId);
  const focusPoint = useSimStore((s) => s.cameraFocusPoint);
  const cameraTransition = useSimStore((s) => s.cameraTransition);
  const setCameraFocusPoint = useSimStore((s) => s.setCameraFocusPoint);

  const half = worldSize / 2;
  const glideGoalCam = useRef<THREE.Vector3 | null>(null);
  const glideGoalTarget = useRef<THREE.Vector3 | null>(null);
  const instantSnapRef = useRef(false);
  const keys = useRef<Record<string, boolean>>({});
  const forwardVec = useRef(new THREE.Vector3());
  const rightVec = useRef(new THREE.Vector3());
  const moveVec = useRef(new THREE.Vector3());
  const tmpCamVec = useRef(new THREE.Vector3());
  const tmpTargetVec = useRef(new THREE.Vector3());
  const tmpPanTarget = useRef(new THREE.Vector3());

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
      instantSnapRef.current = false;
    } else if (cameraMode === "orbit") {
      glideGoalCam.current = new THREE.Vector3(half * 0.28, worldSize * 0.24, worldSize * 0.88);
      glideGoalTarget.current = new THREE.Vector3(half, 30, half);
      instantSnapRef.current = false;
    }
  }, [cameraMode, half, worldSize]);

  useEffect(() => {
    if (focusPoint) {
      glideGoalTarget.current = new THREE.Vector3(focusPoint[0], focusPoint[1], focusPoint[2]);
      glideGoalCam.current = new THREE.Vector3(
        focusPoint[0] - 260,
        focusPoint[1] + 240,
        focusPoint[2] + 260
      );
      instantSnapRef.current = cameraTransition === "instant";
      setCameraFocusPoint(null);
    }
  }, [focusPoint, cameraTransition, setCameraFocusPoint]);

  useFrame((_, delta) => {
    if (!controlsRef.current) return;
    const dt = Math.min(delta, 0.05);

    // WASD / Arrow camera-relative panning + Q/E altitude (Shift boosts 2.4x)
    const k = keys.current;
    const fInput = (k["KeyW"] || k["ArrowUp"] ? 1 : 0) - (k["KeyS"] || k["ArrowDown"] ? 1 : 0);
    const rInput = (k["KeyD"] || k["ArrowRight"] ? 1 : 0) - (k["KeyA"] || k["ArrowLeft"] ? 1 : 0);
    const uInput = (k["KeyE"] ? 1 : 0) - (k["KeyQ"] ? 1 : 0);

    if (fInput !== 0 || rInput !== 0 || uInput !== 0) {
      glideGoalCam.current = null;
      glideGoalTarget.current = null;
      instantSnapRef.current = false;
      const boost = k["ShiftLeft"] || k["ShiftRight"] ? 2.4 : 1.0;
      const speed = Math.max(240, camera.position.y * 0.95) * boost * dt;

      camera.getWorldDirection(forwardVec.current);
      forwardVec.current.y = 0;
      if (forwardVec.current.lengthSq() > 1e-4) {
        forwardVec.current.normalize();
      } else {
        forwardVec.current.set(0, 0, -1);
      }
      rightVec.current.crossVectors(forwardVec.current, camera.up);
      if (rightVec.current.lengthSq() > 1e-4) {
        rightVec.current.normalize();
      } else {
        rightVec.current.set(1, 0, 0);
      }

      moveVec.current.set(0, 0, 0);
      moveVec.current.addScaledVector(forwardVec.current, fInput * speed);
      moveVec.current.addScaledVector(rightVec.current, rInput * speed);
      moveVec.current.y = uInput * speed * 0.7;

      camera.position.add(moveVec.current);
      camera.position.y = Math.max(35, Math.min(worldSize * 1.15, camera.position.y));
      tmpPanTarget.current.set(moveVec.current.x, 0, moveVec.current.z);
      controlsRef.current.target.add(tmpPanTarget.current);
      controlsRef.current.update();
      return;
    }

    if (cameraMode === "fpv" && selectedDroneId) {
      const d = drones.find((item) => item.id === selectedDroneId);
      if (d) {
        const fx = Math.sin(d.heading_rad);
        const fz = Math.cos(d.heading_rad);
        tmpCamVec.current.set(d.position[0] + fx * 12, d.position[1] - 3.5, d.position[2] + fz * 12);
        tmpTargetVec.current.set(
          d.position[0] + fx * 180,
          Math.max(0, d.position[1] - 42),
          d.position[2] + fz * 180
        );
        damp3(camera.position, tmpCamVec.current, 8.5, dt);
        damp3(controlsRef.current.target, tmpTargetVec.current, 8.5, dt);
        controlsRef.current.update();
      }
      return;
    }

    if (cameraMode === "follow" && selectedDroneId) {
      const d = drones.find((item) => item.id === selectedDroneId);
      if (d) {
        tmpTargetVec.current.set(d.position[0], d.position[1], d.position[2]);
        tmpCamVec.current.set(d.position[0] - 130, d.position[1] + 85, d.position[2] + 130);
        damp3(camera.position, tmpCamVec.current, 4.5, dt);
        damp3(controlsRef.current.target, tmpTargetVec.current, 6.5, dt);
        controlsRef.current.update();
      }
      return;
    }

    if (glideGoalCam.current && glideGoalTarget.current) {
      if (instantSnapRef.current) {
        camera.position.copy(glideGoalCam.current);
        controlsRef.current.target.copy(glideGoalTarget.current);
        controlsRef.current.update();
        glideGoalCam.current = null;
        glideGoalTarget.current = null;
        instantSnapRef.current = false;
      } else {
        damp3(camera.position, glideGoalCam.current, 5.0, dt);
        damp3(controlsRef.current.target, glideGoalTarget.current, 5.0, dt);
        controlsRef.current.update();
        if (camera.position.distanceTo(glideGoalCam.current) < 4.0) {
          glideGoalCam.current = null;
          glideGoalTarget.current = null;
        }
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
        instantSnapRef.current = false;
      }}
    />
  );
};
