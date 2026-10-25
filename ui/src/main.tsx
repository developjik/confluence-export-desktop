import ReactDOM from "react-dom/client";
import App from "./App";
import { AppProvider } from "./store";
import "./styles/global.css";

// StrictMode is intentionally omitted: its development double-mount duplicates
// one-shot effects like run_job invocations.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <AppProvider>
    <App />
  </AppProvider>,
);
