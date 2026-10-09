import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Box } from "lucide-react";
const ThreeAccent = lazy(() => import("./ThreeAccent"));
class AccentBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="accent-fallback">
        <i />
        <i />
        <i />
      </div>
    ) : (
      this.props.children
    );
  }
}
export function Accent({ kind }: { kind: string }) {
  const root = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [supported, setSupported] = useState(false);
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    if (!visible || !supported) return;
    if ("requestIdleCallback" in window) {
      const handle = window.requestIdleCallback(() => setIdle(true), {
        timeout: 2000,
      });
      return () => window.cancelIdleCallback(handle);
    }
    const handle = setTimeout(() => setIdle(true), 500);
    return () => clearTimeout(handle);
  }, [visible, supported]);
  useEffect(() => {
    try {
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("webgl2") || canvas.getContext("webgl");
      setSupported(Boolean(context));
      context?.getExtension("WEBGL_lose_context")?.loseContext();
    } catch {
      setSupported(false);
    }
    const observer = new IntersectionObserver((entries) =>
      setVisible(entries[0].isIntersecting),
    );
    if (root.current) observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  return (
    <div ref={root} className="accent" aria-hidden="true">
      {visible && supported && idle ? (
        <AccentBoundary>
          <Suspense fallback={<Box />}>
            <ThreeAccent kind={kind} />
          </Suspense>
        </AccentBoundary>
      ) : (
        <div className="accent-fallback">
          <i />
          <i />
          <i />
        </div>
      )}
    </div>
  );
}
