import axios from 'axios';
import { toast } from 'sonner';
import { supabase } from './supabase';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  // 75 s — covers Render free-tier cold start (up to 60 s) plus actual request time
  timeout: 75000,
});

// Render free tier sleeps when idle. Fire one silent GET per page load to start waking it.
// No retries, no auth, errors ignored.
let warmUpSent = false;
export function warmUpBackend(): void {
  if (warmUpSent) return;
  warmUpSent = true;
  fetch(`${API_BASE_URL}/api/v1/health`).catch(() => {});
}

// "Waking up" notice: shown once any request is still pending after 5 s, hidden when
// the last slow request finishes.
const SLOW_NOTICE_ID = 'server-waking';
const SLOW_NOTICE_MS = 5000;
let slowRequests = 0;

function startSlowTimer(config: any) {
  config._slowServerTimer = setTimeout(() => {
    config._slowShown = true;
    slowRequests += 1;
    toast('Waking up the server — first load can take up to a minute.', {
      id: SLOW_NOTICE_ID,
      duration: Infinity,
    });
  }, SLOW_NOTICE_MS);
}

function stopSlowTimer(config: any) {
  if (!config) return;
  if (config._slowServerTimer) clearTimeout(config._slowServerTimer);
  config._slowServerTimer = undefined;
  if (config._slowShown) {
    config._slowShown = false;
    slowRequests = Math.max(0, slowRequests - 1);
    if (slowRequests === 0) toast.dismiss(SLOW_NOTICE_ID);
  }
}

// Surface a clear message when the backend is cold-starting or unreachable
apiClient.interceptors.response.use(
  (response) => {
    stopSlowTimer(response?.config);
    return response;
  },
  (error) => {
    stopSlowTimer(error?.config);

    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      error.message =
        'The server took too long to respond. It may be starting up — please wait 30 seconds and try again.';
    } else if (!error.response) {
      error.message =
        'Cannot reach the backend server. Check your network or try again shortly.';
    }
    return Promise.reject(error);
  }
);

// Automatically attach Supabase JWT token to outgoing API requests.
// FIX #4: Use refreshSession() when the cached token is expired or near expiry
// to prevent the "upload fails until relogin" symptom caused by stale access tokens.
apiClient.interceptors.request.use(async (config) => {
  startSlowTimer(config);

  let { data: { session } } = await supabase.auth.getSession();

  if (session) {
    // Check if the access token is expired or within 60 seconds of expiry
    const expiresAt = session.expires_at ?? 0; // Unix timestamp (seconds)
    const nowSec = Math.floor(Date.now() / 1000);
    const isExpiredOrNearExpiry = expiresAt - nowSec < 60;

    if (isExpiredOrNearExpiry) {
      // Force a token refresh so we always send a valid JWT
      const refreshResult = await supabase.auth.refreshSession();
      if (refreshResult.data?.session) {
        session = refreshResult.data.session;
      }
    }
  }

  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
}, (error) => {
  stopSlowTimer(error?.config);
  return Promise.reject(error);
});

export interface StorageAuditPayload {
  storage_path: string;
  advisor_id: string;
  university_id: string;
  tenant_id?: string;
  matric_number?: string;
  curriculum_year?: string;
  program_code?: string;
}

export interface FinalizeApprovalPayload {
  document_id: string;
  matric_number: string;
  tenant_id?: string;
  student_name?: string;
  advisor_id?: string;
  university_id?: string;
  curriculum_year?: string;
  program_code?: string;
  academic_session?: string;
  semester?: string | number;
  pngk?: number;
  courses: Array<{
    course_code: string;
    course_name?: string;
    grade: string;
    credit_hour?: number;
    credits?: number;
    status?: string;
    warning?: string;
    session_semester?: string;
  }>;
}

export const api = {
  // Health check
  getHealth: async () => {
    const res = await apiClient.get('/api/v1/health');
    return res.data;
  },

  // Download Course CSV Starter Template
  downloadCourseTemplateCSV: async () => {
    const res = await apiClient.get('/api/v1/courses/template-csv', {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'course_curriculum_template.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
  },

  // Upload Course Structure CSV
  uploadCoursesCSV: async (
    file: File,
    templateName: string,
    programCode: string,
    totalCredits: number,
    syllabusYear: string
  ) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('template_name', templateName);
    formData.append('program_code', programCode);
    formData.append('total_credits', String(totalCredits));
    formData.append('syllabus_year', syllabusYear);

    const res = await apiClient.post('/api/v1/courses/upload-csv', formData);
    return res.data;
  },

  // Extract PDF from storage path
  extractTranscript: async (filePath: string, tenantId?: string) => {
    const res = await apiClient.post('/api/v1/audit/extract', {
      file_path: filePath,
      ...(tenantId ? { tenant_id: tenantId } : {})
    });
    return res.data;
  },

  // Student confirms extracted results; server compares against its stored copy
  submitVerification: async (documentId: string, courses: any[]) => {
    const res = await apiClient.post('/api/v1/audit/submit-verification', {
      document_id: documentId,
      courses,
    });
    return res.data;
  },

  // Finalize approval through Zero-Waste FastAPI engine
  finalizeApproval: async (payload: FinalizeApprovalPayload) => {
    const res = await apiClient.post('/api/v1/audit/finalize-approval', payload);
    return res.data;
  },


  // Reject uploaded document via service-role backend endpoint
  rejectDocument: async (documentId: string, rejectionReason?: string) => {
    const res = await apiClient.post('/api/v1/audit/reject-document', {
      document_id: documentId,
      rejection_reason: rejectionReason || "Document rejected by advisor",
    });
    return res.data;
  },

  // Validate Cohort
  validateCohort: async (code: string) => {
    const res = await apiClient.get(`/api/v1/register/validate-cohort/${code}`);
    return res.data;
  },

  // Register Student
  registerStudent: async (payload: { cohort_code: string; matric_no: string; full_name: string }) => {
    const res = await apiClient.post('/api/v1/register/student', payload);
    return res.data;
  },

  // Register Advisor
  registerAdvisor: async (payload: { invite_code: string; full_name: string; staff_id: string; department: string }) => {
    const res = await apiClient.post('/api/v1/register/advisor', payload);
    return res.data;
  },

  // Notify Student of Advising Note
  notifyAdvisingLog: async (logId: string): Promise<{ sent: boolean; reason?: string; notified_at?: string }> => {
    const res = await apiClient.post(`/api/v1/advising-logs/${logId}/notify`);
    return res.data;
  },

  // Update Student Exemptions, Entry Semester, and EX/CT Course Records
  patchStudentExemptions: async (
    matricNo: string,
    payload: {
      entry_semester?: number;
      block_exempted_credits?: number;
      course_actions?: Array<{
        action: 'add' | 'remove';
        course_code: string;
        grade?: string;
        credits?: number;
        course_name?: string;
        semester?: string;
      }>;
    }
  ): Promise<{
    success: boolean;
    matric_no: string;
    entry_semester: number;
    block_exempted_credits: number;
    audits_written: number;
    detail: string;
  }> => {
    const res = await apiClient.patch(`/api/v1/students/${encodeURIComponent(matricNo)}/exemptions`, payload);
    return res.data;
  },

  getProgress: async (matricNo: string): Promise<{
    matric_no: string;
    rows: Array<{
      template_course_id: string;
      code: string;
      name: string;
      category: string;
      credits: number;
      is_slot: boolean;
      slot_no: number | null;
      status: 'done' | 'in_progress' | 'missing';
      satisfied_by: { course_code: string; grade: string | null; semester: string | null } | null;
      source: 'exact' | 'pattern' | 'override' | null;
      override?: {
        kind: 'assign' | 'exclude';
        note: string | null;
        assigned_by_staff_id: string | null;
      } | null;
    }>;
    categories: Array<{ category: string; required: number; earned: number }>;
    unassigned: Array<{
      course_code: string;
      course_name: string;
      grade: string | null;
      credits: number;
      semester: string | null;
      excluded?: boolean;
      override?: {
        kind: 'assign' | 'exclude';
        note: string | null;
        assigned_by_staff_id: string | null;
      } | null;
    }>;
    totals: { required: number; earned: number };
    warnings: string[];
  }> => {
    const res = await apiClient.get(`/api/v1/audit/progress/${encodeURIComponent(matricNo)}`);
    return res.data;
  },

  setProgressOverride: async (
    matricNo: string,
    body: {
      kind: 'assign' | 'exclude';
      course_code: string;
      template_course_id?: string | null;
      note?: string | null;
    }
  ): Promise<{ status: string; override: any }> => {
    const res = await apiClient.put(
      `/api/v1/audit/progress/${encodeURIComponent(matricNo)}/overrides`,
      body
    );
    return res.data;
  },

  deleteProgressOverride: async (
    matricNo: string,
    courseCode: string
  ): Promise<{ status: string; message: string }> => {
    const res = await apiClient.delete(
      `/api/v1/audit/progress/${encodeURIComponent(matricNo)}/overrides/${encodeURIComponent(courseCode)}`
    );
    return res.data;
  },

  // Curriculum Template Editor (SynGrad Roadmap 4C)
  getTemplates: async (): Promise<Array<{
    id: string;
    program_code: string;
    program_name: string;
    syllabus_year: string;
    total_credits_required: number;
    owner_staff_id: string | null;
    can_edit: boolean;
  }>> => {
    const res = await apiClient.get('/api/v1/courses/templates');
    return res.data;
  },

  getTemplateDetail: async (templateId: string): Promise<{
    id: string;
    program_code: string;
    program_name: string;
    syllabus_year: string;
    total_credits_required: number;
    owner_staff_id: string | null;
    can_edit: boolean;
    rows: Array<{
      id: string;
      template_id: string;
      course_code: string;
      course_name: string;
      credit_hour: number;
      category: string;
      is_core_requirement: boolean;
      is_elective_slot: boolean;
      slot_no: number | null;
      match_patterns: string[] | null;
      prerequisites: any;
      created_at?: string;
      updated_at?: string;
    }>;
  }> => {
    const res = await apiClient.get(`/api/v1/courses/templates/${encodeURIComponent(templateId)}`);
    return res.data;
  },

  updateTemplate: async (
    templateId: string,
    payload: { program_name?: string; total_credits_required?: number }
  ): Promise<any> => {
    const res = await apiClient.patch(`/api/v1/courses/templates/${encodeURIComponent(templateId)}`, payload);
    return res.data;
  },

  addTemplateRow: async (
    templateId: string,
    payload: {
      course_code: string;
      course_name: string;
      credit_hour: number;
      category: string;
      prerequisites?: any;
    }
  ): Promise<any> => {
    const res = await apiClient.post(`/api/v1/courses/templates/${encodeURIComponent(templateId)}/rows`, payload);
    return res.data;
  },

  updateTemplateRow: async (
    templateId: string,
    rowId: string,
    payload: {
      course_code?: string;
      course_name?: string;
      credit_hour?: number;
      category?: string;
      prerequisites?: any;
    }
  ): Promise<any> => {
    const res = await apiClient.patch(
      `/api/v1/courses/templates/${encodeURIComponent(templateId)}/rows/${encodeURIComponent(rowId)}`,
      payload
    );
    return res.data;
  },

  deleteTemplateRow: async (
    templateId: string,
    rowId: string
  ): Promise<{ deleted: boolean; row_id: string; cascaded_overrides_count: number }> => {
    const res = await apiClient.delete(
      `/api/v1/courses/templates/${encodeURIComponent(templateId)}/rows/${encodeURIComponent(rowId)}`
    );
    return res.data;
  },

  getTemplateRowImpact: async (
    templateId: string,
    rowId: string
  ): Promise<{ overrides_count: number; cohorts_using_template: number }> => {
    const res = await apiClient.get(
      `/api/v1/courses/templates/${encodeURIComponent(templateId)}/rows/${encodeURIComponent(rowId)}/impact`
    );
    return res.data;
  },
};



