import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import App from "@/App";
import "@/index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")).render(
  React.createElement(React.StrictMode, null,
    React.createElement(QueryClientProvider, { client: queryClient },
      React.createElement(App, null),
      React.createElement(Toaster, {
        position: "bottom-right",
        theme: "dark",
        richColors: true,
      })
    )
  )
);
