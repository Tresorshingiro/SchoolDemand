import { useEffect } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AdminLayout from './AdminLayout';
import ActivityPage from './ActivityPage';
import UsersPage from './UsersPage';
import DataSourcesPage from './DataSourcesPage';
import HistoryPage from './HistoryPage';
import ImportPage from './ImportPage';

/** The admin portal (administrators only, see RequireAdmin in main.tsx). */
export default function AdminApp() {
  useEffect(() => {
    const previous = document.title;
    document.title = 'Admin — School Demand & Demographics';
    return () => {
      document.title = previous;
    };
  }, []);
  return (
    <AdminLayout>
      <Routes>
        <Route index element={<Navigate to="users" replace />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="data" element={<DataSourcesPage />} />
        <Route path="data/history" element={<HistoryPage />} />
        <Route path="data/imports/:id" element={<ImportPage />} />
        <Route path="*" element={<Navigate to="users" replace />} />
      </Routes>
    </AdminLayout>
  );
}
