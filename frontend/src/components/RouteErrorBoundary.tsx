import { Component, type ErrorInfo, type ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";

// Wraps each routed screen so one broken screen shows an error message
// instead of blanking the whole app. Keyed by pathname at the call site so
// navigating elsewhere clears the error.
export class RouteErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Screen crashed", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={() => window.location.reload()}>
              Reload
            </Button>
          }
        >
          Something went wrong on this screen. Reload the page to try again.
        </Alert>
      );
    }
    return this.props.children;
  }
}
