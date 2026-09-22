import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import { ComponentGallery } from "./components/ComponentGallery";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {new URLSearchParams(location.search).has("components") ? (
      <ComponentGallery />
    ) : (
      <App />
    )}
  </StrictMode>,
);
