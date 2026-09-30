/** The admin portal's API calls (backend/app/routers/admin.py). */
import { API_URL, getJson, sendForm, sendJson } from '../api';

export type Role = 'admin' | 'viewer';

export interface AdminUser {
  id: number;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuditEntry {
  id: number;
  at: string;
  user_id: number | null;
  user_email: string | null;
  user_name: string | null;
  action: string;
  target: string;
  detail: Record<string, unknown> | null;
}

export const listUsers = () => getJson<AdminUser[]>('/admin/users');

export const createUser = (body: { email: string; full_name: string | null; role: Role; password: string }) =>
  sendJson<AdminUser>('POST', '/admin/users', body);

export const updateUser = (id: number, body: { full_name?: string | null; role?: Role; is_active?: boolean }) =>
  sendJson<AdminUser>('PATCH', `/admin/users/${id}`, body);

export const resetPassword = (id: number, password: string) =>
  sendJson<void>('POST', `/admin/users/${id}/password`, { password });

export function listAudit(p: { before?: number; userId?: number; action?: string; limit?: number } = {}) {
  const q = new URLSearchParams({ limit: String(p.limit ?? 50) });
  if (p.before !== undefined) q.set('before', String(p.before));
  if (p.userId !== undefined) q.set('user_id', String(p.userId));
  if (p.action) q.set('action', p.action);
  return getJson<AuditEntry[]>(`/admin/audit?${q}`);
}

/* ------------------------------------------------------------------ data sources (backend/app/routers/data_admin.py) */

export type DataKind = 'school_data' | 'catchment' | 'nisr_population';
export const KIND_LABEL: Record<DataKind, string> = {
  school_data: 'School data (MINEDUC)',
  catchment: 'Catchment (GIS)',
  nisr_population: 'NISR population (age 3, district)',
};

export interface ImportRun {
  id: number;
  kind: DataKind;
  label: string;
  academic_year: number | null;
  file_name: string | null;
  file_size: number | null;
  status: string;
  progress: number;
  is_live: boolean;
  uploaded_by: string | null;
  uploaded_at: string;
  published_by: string | null;
  published_at: string | null;
  error: string | null;
}

export interface Problem {
  code: string;
  message: string;
  count: number;
  rows: Record<string, unknown>[];
}

export interface LevelChange {
  level: string;
  students: [number, number];
  class_groups: [number, number];
  rooms: [number, number];
  required: [number, number];
  gap: [number, number];
}

export interface Report {
  errors: Problem[];
  warnings: Problem[];
  changes: {
    against: number;
    replaces: boolean;
    schools: [number, number];
    schools_added: number;
    schools_removed: number;
    levels: LevelChange[];
  } | null;
  summary: Record<string, unknown>;
}

export interface ImportDetail extends ImportRun {
  report: Report | null;
  can_publish: boolean;
  consequence: string | null;
}

export interface SourceCard {
  kind: DataKind;
  label: string;
  live: ImportRun[];
  connector: string | null;
}

const DATA = '/admin/data';
export const BUSY = ['uploaded', 'checking', 'publishing', 'withdrawing'];
export const STATUS_LABEL: Record<string, string> = {
  uploaded: 'Waiting for the check', checking: 'Checking…', ready: 'Checked', failed: 'Failed',
  publishing: 'Publishing…', published: 'Live', superseded: 'Replaced', discarded: 'Discarded',
  withdrawing: 'Withdrawing…', withdrawn: 'Withdrawn',
};

export const listSources = () => getJson<SourceCard[]>(`${DATA}/sources`);
export const listImports = (kind?: DataKind) => getJson<ImportRun[]>(`${DATA}/imports${kind ? `?kind=${kind}` : ''}`);
export const getImport = (id: number) => getJson<ImportDetail>(`${DATA}/imports/${id}`);
export const importAction = (id: number, action: 'publish' | 'discard' | 'recheck' | 'withdraw') =>
  sendJson<ImportDetail>('POST', `${DATA}/imports/${id}/${action}`);
export function uploadFile(kind: DataKind, file: File, year?: number) {
  const form = new FormData();
  form.set('kind', kind);
  form.set('file', file);
  if (year !== undefined) form.set('academic_year', String(year));
  return sendForm<ImportDetail>(`${DATA}/uploads`, form);
}
export const templateUrl = (kind: DataKind) => `${API_URL}${DATA}/templates/${kind}`;
export const fileUrl = (id: number) => `${API_URL}${DATA}/imports/${id}/file`;
export const issuesUrl = (id: number) => `${API_URL}${DATA}/imports/${id}/issues.csv`;
