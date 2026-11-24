import React, { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

const INTRO_STORAGE_KEY = "qr_intro_seen";
const INTRO_DURATION_S = 2.5;
const HIGH_ORBIT_START = new THREE.Vector3(0, 2600, 3200);
const HIGH_ORBIT_TARGET = new THREE.Vector3(0, 0, 0);

export interface IntroCameraRigProps {
  anchor: { x: number; z: number };
  controlsRef: React.RefObject<any>;
  introActiveRef: React.MutableRefObject<boolean>;
  transitioningRef: React.MutableRefObject<boolean>;
  quality: "high" | "low";
  prefersReducedMotion: boolean;
}

function markIntroSeen(): void {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(INTRO_STORAGE_KEY, "1");
    }
  } catch {
    // Ignore storage quota / privacy mode errors
  }
}

function hasSeenIntro(): boolean {
  try {
    return (
      typeof window !== "undefined" &&
      window.localStorage?.getItem(INTRO_STORAGE_KEY) === "1"
    );
  } catch {
    return false;
  }
}

/**
 * On first mount of World Command, if localStorage.getItem("qr_intro_seen") !== "1"
 * and neither quality === "low" nor prefers-reduced-motion is active, runs a smooth
 * 2.5s camera glide from high orbit [0, 2600, 3200] down to the active country,
 * then marks qr_intro_seen = "1" and yields control to OrbitControls.
 * Zero setState inside useFrame.
 */
export const IntroCameraRig: React.FC<IntroCameraRigProps> = ({
  anchor,
  controlsRef,
  introActiveRef,
  transitioningRef,
  quality,
  prefersReducedMotion,
}) => {
  const { camera } = useThree();
  const initializedRef = useRef(false);
  const elapsedRef = useRef(0);

  const endPos = useMemo(
    () => new THREE.Vector3(anchor.x + 640, 480, anchor.z + 780),
    [anchor.x, anchor.z]
  );
  const endTarget = useMemo(
    () => new THREE.Vector3(anchor.x, 12, anchor.z),
    [anchor.x, anchor.z]
  );

  // Run once on initial mount
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (hasSeenIntro() || quality === "low" || prefersReducedMotion) {
      introActiveRef.current = false;
      return;
    }

    // Start smooth high-orbit glide and pause CameraFlyRig until completion
    introActiveRef.current = true;
    transitioningRef.current = false;
    elapsedRef.current = 0;

    camera.position.copy(HIGH_ORBIT_START);
    if (controlsRef.current) {
      controlsRef.current.target.copy(HIGH_ORBIT_TARGET);
      controlsRef.current.update();
    } else {
      camera.lookAt(HIGH_ORBIT_TARGET);
    }
  }, [camera, controlsRef, introActiveRef, transitioningRef, quality, prefersReducedMotion]);

  // If user manually grabs OrbitControls during the intro glide, yield immediately
  useEffect(() => {
    const ctrl = controlsRef.current;
    if (!ctrl) return;
    const handleUserInteract = () => {
      if (introActiveRef.current) {
        introActiveRef.current = false;
        markIntroSeen();
      }
    };
    ctrl.addEventListener("start", handleUserInteract);
    return () => ctrl.removeEventListener("start", handleUserInteract);
  }, [controlsRef, introActiveRef]);

  useFrame((_, rawDelta) => {
    if (!introActiveRef.current) return;

    const dt = Math.min(rawDelta, 0.05);
    elapsedRef.current += dt;
    const t = Math.min(1, elapsedRef.current / INTRO_DURATION_S);

    // Smooth cubic ease-in-out
    const eased =
      t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

    camera.position.lerpVectors(HIGH_ORBIT_START, endPos, eased);

    if (controlsRef.current) {
      controlsRef.current.target.lerpVectors(HIGH_ORBIT_TARGET, endTarget, eased);
      controlsRef.current.update();
    } else {
      camera.lookAt(endTarget);
    }

    if (t >= 1) {
      introActiveRef.current = false;
      markIntroSeen();
    }
  });

  return null;
};
