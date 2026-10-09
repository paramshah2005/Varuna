import { Canvas } from "@react-three/fiber";
import { OrthographicCamera } from "@react-three/drei/core/OrthographicCamera.js";
function Geometry({ kind }: { kind: string }) {
  if (kind === "priority")
    return (
      <>
        <ambientLight intensity={2.1} />
        <directionalLight position={[3, 5, 5]} intensity={2} />
        <group rotation={[0.3, 0.5, -0.1]}>
          <mesh>
            <boxGeometry args={[1.2, 0.38, 0.38]} />
            <meshStandardMaterial color="#2764df" roughness={1} />
          </mesh>
          <mesh>
            <boxGeometry args={[0.38, 1.2, 0.38]} />
            <meshStandardMaterial color="#2764df" roughness={1} />
          </mesh>
          <mesh position={[0, -0.75, 0]}>
            <boxGeometry args={[1.25, 0.13, 0.7]} />
            <meshStandardMaterial color="#b7d7ff" roughness={1} />
          </mesh>
        </group>
      </>
    );
  if (kind === "stations")
    return (
      <>
        <ambientLight intensity={2.1} />
        <directionalLight position={[3, 5, 5]} intensity={2} />
        <group rotation={[0.25, 0.5, 0]}>
          <mesh position={[0, -0.15, 0]}>
            <boxGeometry args={[1, 0.7, 0.6]} />
            <meshStandardMaterial color="#80b8f8" roughness={1} />
          </mesh>
          <mesh position={[0, 0.4, 0]} rotation={[0, Math.PI / 4, 0]}>
            <coneGeometry args={[0.85, 0.45, 4]} />
            <meshStandardMaterial color="#2764df" roughness={1} />
          </mesh>
          <mesh position={[0, -0.25, 0.31]}>
            <boxGeometry args={[0.25, 0.45, 0.03]} />
            <meshStandardMaterial color="#eff5ff" roughness={1} />
          </mesh>
        </group>
      </>
    );
  const points =
    kind === "zones"
      ? [
          [-0.7, 0, 0],
          [0, 0.3, 0],
          [0.7, 0, 0],
        ]
      : kind === "reserve"
        ? [
            [-0.65, 0, 0],
            [0, 0, 0],
            [0.65, 0, 0],
          ]
        : [
            [-0.35, -0.15, 0],
            [0.35, 0.15, 0],
          ];
  return (
    <>
      <ambientLight intensity={2.1} />
      <directionalLight position={[3, 5, 5]} intensity={2} />
      {points.map((p, i) => (
        <mesh
          key={i}
          position={p as [number, number, number]}
          rotation={[0.3, 0.55, 0]}
        >
          <boxGeometry
            args={
              kind === "reserve" ? [0.4, 0.9 - i * 0.17, 0.4] : [0.5, 0.5, 0.5]
            }
          />
          <meshStandardMaterial
            color={["#2764df", "#80b8f8", "#b7d7ff"][i]}
            roughness={1}
          />
        </mesh>
      ))}
    </>
  );
}
export default function ThreeAccent({ kind }: { kind: string }) {
  return (
    <Canvas dpr={1} frameloop="demand" gl={{ antialias: false, alpha: true }}>
      <OrthographicCamera makeDefault position={[0, 0, 5]} zoom={35} />
      <Geometry kind={kind} />
    </Canvas>
  );
}
