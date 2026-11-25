import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/index.css";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ background: "#090d14", color: "#f87171", padding: "2rem", fontFamily: "monospace", whiteSpace: "pre-wrap", height: "100vh" }}>
          <h2 style={{ color: "#ef4444", marginBottom: "1rem" }}>⚠ React Render Error</h2>
          <strong>{this.state.error.message}</strong>
          <br /><br />
          {this.state.error.stack}
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
