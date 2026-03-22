import { Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { UploadProvider } from './context/UploadContext';
import Navbar from './components/Navbar';
import UploadStatusBar from './components/UploadStatusBar';
import ProtectedRoute from './components/ProtectedRoute';
import Home from './pages/Home';
import Login from './pages/Login';
import Register from './pages/Register';
import TestList from './pages/TestList';
import TestTaking from './pages/TestTaking';
import TestResults from './pages/TestResults';
import AdminDashboard from './pages/admin/AdminDashboard';
import QuestionManager from './pages/admin/QuestionManager';
import TestCreator from './pages/admin/TestCreator';
import PdfUpload from './pages/admin/PdfUpload';
import './App.css';

export default function App() {
  return (
    <AuthProvider>
    <UploadProvider>
      <UploadStatusBar />
      <Routes>
        {/* Test taking is full-screen, no navbar */}
        <Route
          path="/tests/:testId/take"
          element={
            <ProtectedRoute>
              <TestTaking />
            </ProtectedRoute>
          }
        />

        {/* All other routes have navbar */}
        <Route
          path="*"
          element={
            <>
              <Navbar />
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route
                  path="/tests"
                  element={<ProtectedRoute><TestList /></ProtectedRoute>}
                />
                <Route
                  path="/tests/:testId/results/:attemptId"
                  element={<ProtectedRoute><TestResults /></ProtectedRoute>}
                />
                <Route
                  path="/admin"
                  element={<ProtectedRoute adminOnly><AdminDashboard /></ProtectedRoute>}
                />
                <Route
                  path="/admin/questions"
                  element={<ProtectedRoute adminOnly><QuestionManager /></ProtectedRoute>}
                />
                <Route
                  path="/admin/tests/create"
                  element={<ProtectedRoute adminOnly><TestCreator /></ProtectedRoute>}
                />
                <Route
                  path="/admin/upload-pdf"
                  element={<ProtectedRoute adminOnly><PdfUpload /></ProtectedRoute>}
                />
              </Routes>
            </>
          }
        />
      </Routes>
    </UploadProvider>
    </AuthProvider>
  );
}
