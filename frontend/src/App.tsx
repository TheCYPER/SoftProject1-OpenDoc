import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import DocumentListPage from "./pages/DocumentListPage";
import EditorPage from "./pages/EditorPage";
import LoginPage from "./pages/LoginPage";

function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<LoginPage />} />
          <Route path="/documents" element={<DocumentListPage />} />
          <Route path="/documents/:documentId" element={<EditorPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </BrowserRouter>
    </ToastProvider>
  );
}

export default App;
