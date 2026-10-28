import React, { useState, useEffect } from 'react';
import { supabase } from '../../../lib/supabase';
import { apiClient } from '../../../lib/api';
import { toast } from 'sonner';
import {
  FlaskConical,
  Upload,
  AlertTriangle,
  Clock,
  Sparkles,
  Cpu,
  FileText,
  Loader2,
  ChevronDown,
  CheckCircle,
  HelpCircle,
} from 'lucide-react';

interface Tenant {
  id: string;
  name?: string;
}

interface CourseItem {
  course_code: string;
  course_name: string;
  grade: string;
  credit_hour?: number;
  credits?: number;
  status: string;
  session_semester?: string;
  is_ai_parsed?: boolean;
}

interface ExtractResult {
  source: string;
  model: string | null;
  semesters: any[];
  courses: CourseItem[];
  warnings: string[];
  needs_review: boolean;
  timing: number | any;
  matric_number?: string | null;
  student_name?: string | null;
  fraud_flag?: boolean;
  gpa?: number | null;
  cgpa?: number | null;
}

export function SlipLab() {
  const [isUnavailable, setIsUnavailable] = useState<boolean>(false);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [selectedTenant, setSelectedTenant] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [isLoadingTenants, setIsLoadingTenants] = useState<boolean>(true);
  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    async function loadTenants() {
      setIsLoadingTenants(true);
      try {
        const { data, error } = await supabase
          .from('tenants_public')
          .select('id, name')
          .order('id');
        if (error) {
          console.error('[SlipLab] Failed to load tenants:', error);
          toast.error('Could not load tenants list.');
        } else if (data) {
          setTenants(data);
          if (data.length > 0) {
            setSelectedTenant(data[0].id);
          }
        }
      } catch (err) {
        console.error('[SlipLab] Error:', err);
      } finally {
        setIsLoadingTenants(false);
      }
    }
    loadTenants();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const selected = e.target.files[0];
      if (!selected.name.toLowerCase().endsWith('.pdf')) {
        toast.error('Please upload a PDF document.');
        return;
      }
      setFile(selected);
      setResult(null);
      setErrorMsg(null);
    }
  };

  const handleRunExtract = async () => {
    if (!file) {
      toast.error('Please select a PDF slip to extract.');
      return;
    }
    if (!selectedTenant) {
      toast.error('Please select a tenant.');
      return;
    }

    setIsExtracting(true);
    setErrorMsg(null);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('tenant_id', selectedTenant);

      const res = await apiClient.post('/api/v1/lab/extract', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setResult(res.data);
      toast.success('Extraction completed without persistence.');
    } catch (err: any) {
      console.error('[SlipLab] Extraction failed:', err);
      const status = err.response?.status;
      if (status === 404 || status === 403) {
        setIsUnavailable(true);
        return;
      }
      const detail =
        err.response?.data?.detail ||
        err.message ||
        'Extraction failed. Please check backend logs.';
      setErrorMsg(detail);
      toast.error(`Extraction Error: ${detail}`);
    } finally {
      setIsExtracting(false);
    }
  };

  const formatTiming = (timing: any): string => {
    if (typeof timing === 'number') {
      return `${timing}s`;
    }
    if (timing && typeof timing === 'object') {
      if (timing.elapsed_seconds !== undefined) return `${timing.elapsed_seconds}s`;
      if (timing.total_seconds !== undefined) return `${timing.total_seconds}s`;
      if (timing.ms !== undefined) return `${timing.ms}ms`;
    }
    return String(timing || 'N/A');
  };

  if (isUnavailable) {
    return (
      <div className="min-h-screen bg-[#F9FAFB] flex items-center justify-center text-sm text-gray-600">
        Slip Lab is not available here.
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9FAFB] text-gray-900 pb-16">
      {/* Top Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-blue-950 flex items-center justify-center text-white shadow-sm">
              <FlaskConical className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold text-gray-900 tracking-tight">SynGrad Slip Lab</h1>
                <span className="text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded uppercase tracking-wider">
                  Staging Sandbox
                </span>
              </div>
              <p className="text-xs text-gray-500">
                Zero-Persistence Transcript Slip Extraction Diagnostic & Parser Testbed
              </p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-xs text-gray-400 font-mono">POST /lab/extract</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-6xl mx-auto px-6 mt-6 space-y-6">
        {/* Controls Card */}
        <section className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-end">
            {/* Tenant Selector */}
            <div>
              <label htmlFor="tenant-select" className="block text-xs font-semibold uppercase tracking-wider text-gray-700 mb-2">
                Select Tenant
              </label>
              <select
                id="tenant-select"
                value={selectedTenant}
                onChange={(e) => setSelectedTenant(e.target.value)}
                disabled={isLoadingTenants || isExtracting}
                className="w-full bg-white border border-gray-300 rounded-lg px-3.5 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent font-medium"
              >
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.id} {t.name ? `(${t.name})` : ''}
                  </option>
                ))}
              </select>
            </div>

            {/* File Upload Selector */}
            <div>
              <label htmlFor="slip-file" className="block text-xs font-semibold uppercase tracking-wider text-gray-700 mb-2">
                Upload PDF Slip
              </label>
              <input
                id="slip-file"
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
                disabled={isExtracting}
                className="block w-full text-xs text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-950 hover:file:bg-blue-100 cursor-pointer border border-gray-300 rounded-lg p-1"
              />
            </div>
          </div>

          <div className="mt-6 flex items-center justify-between pt-4 border-t border-gray-100">
            <div className="text-xs text-gray-500 flex items-center gap-1.5">
              <HelpCircle className="w-3.5 h-3.5 text-gray-400" />
              <span>Nothing is written to database or storage bucket. Safe for test audits.</span>
            </div>
            <button
              id="run-extract-btn"
              onClick={handleRunExtract}
              disabled={!file || !selectedTenant || isExtracting}
              className="inline-flex items-center gap-2 bg-blue-950 hover:bg-blue-900 text-white px-5 py-2 rounded-lg text-xs font-semibold tracking-wide shadow-sm disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isExtracting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Extracting Pipeline...</span>
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4" />
                  <span>Run Extraction</span>
                </>
              )}
            </button>
          </div>
        </section>

        {/* Error Notification */}
        {errorMsg && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 text-xs p-4 rounded-xl flex items-start gap-3">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold block">Extraction Error (No Data Extracted)</span>
              <span>{errorMsg}</span>
            </div>
          </div>
        )}

        {/* Results Area */}
        {result && (
          <div className="space-y-6">
            {/* Metadata / Badges Bar */}
            <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Pipeline Path:</span>
                  <span
                    className={`text-xs px-2.5 py-1 rounded-md font-bold uppercase tracking-wider ${
                      result.source === 'rules'
                        ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                        : result.source === 'ai_scan'
                        ? 'bg-purple-50 text-purple-800 border border-purple-200'
                        : 'bg-blue-50 text-blue-900 border border-blue-200'
                    }`}
                  >
                    {result.source}
                  </span>
                </div>

                <div className="flex items-center gap-4 text-xs font-medium text-gray-600">
                  <div className="flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-gray-400" />
                    <span>Model: <strong className="text-gray-900 font-mono">{result.model || 'Deterministic (Regex)'}</strong></span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                    <span>Timing: <strong className="text-gray-900 font-mono">{formatTiming(result.timing)}</strong></span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <CheckCircle className={`w-3.5 h-3.5 ${result.needs_review ? 'text-amber-500' : 'text-emerald-500'}`} />
                    <span>Review Required: <strong className={result.needs_review ? 'text-amber-700' : 'text-emerald-700'}>{result.needs_review ? 'Yes' : 'No'}</strong></span>
                  </div>
                </div>
              </div>

              {/* Mode Specific Banners */}
              {result.source === 'ai' && (
                <div className="bg-blue-50 border border-blue-200 text-blue-900 text-xs p-3.5 rounded-lg flex items-center font-medium">
                  <Sparkles className="w-4 h-4 mr-2.5 shrink-0 text-blue-800" />
                  <span>Read by AI — please check every row carefully</span>
                </div>
              )}
              {result.source === 'ai_scan' && (
                <div className="bg-purple-50 border border-purple-200 text-purple-900 text-xs p-3.5 rounded-lg flex items-center font-medium">
                  <Sparkles className="w-4 h-4 mr-2.5 shrink-0 text-purple-800" />
                  <span>Read from a scanned slip by AI — scans can be misread, please check every row carefully.</span>
                </div>
              )}

              {/* Warnings List */}
              {result.warnings && result.warnings.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-gray-100">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-amber-900 block">
                    Extraction Warnings ({result.warnings.length}):
                  </span>
                  {result.warnings.map((w, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-center gap-2"
                    >
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                      <span>{w}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Courses Table */}
            <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <div className="px-6 py-3.5 border-b border-gray-200 flex justify-between items-center bg-gray-50">
                <h2 className="text-xs font-bold uppercase tracking-wider text-gray-700">
                  Extracted Courses ({result.courses?.length || 0})
                </h2>
                {result.matric_number && (
                  <span className="text-xs text-gray-500 font-mono">
                    Matric: <strong className="text-gray-900">{result.matric_number}</strong>
                  </span>
                )}
              </div>

              {result.courses && result.courses.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-gray-200 bg-[#F9FAFB] text-gray-500 font-semibold uppercase tracking-wider">
                        <th className="py-2.5 px-4">Semester</th>
                        <th className="py-2.5 px-4">Course Code</th>
                        <th className="py-2.5 px-4">Course Name</th>
                        <th className="py-2.5 px-4 text-center">Credits</th>
                        <th className="py-2.5 px-4 text-center">Grade</th>
                        <th className="py-2.5 px-4">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {result.courses.map((c, i) => (
                        <tr key={i} className="hover:bg-gray-50/80 transition-colors">
                          <td className="py-2.5 px-4 font-mono text-gray-600">
                            {c.session_semester || '—'}
                          </td>
                          <td className="py-2.5 px-4 font-mono font-bold text-gray-900">
                            {c.course_code}
                          </td>
                          <td className="py-2.5 px-4 text-gray-800">{c.course_name}</td>
                          <td className="py-2.5 px-4 text-center font-mono text-gray-700">
                            {c.credits ?? c.credit_hour ?? 3}
                          </td>
                          <td className="py-2.5 px-4 text-center font-mono font-bold text-gray-900">
                            {c.grade}
                          </td>
                          <td className="py-2.5 px-4">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-semibold ${
                                c.status === 'Passed'
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : c.status === 'Exempted'
                                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                  : c.status === 'In-Progress'
                                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                  : 'bg-rose-50 text-rose-700 border border-rose-200'
                              }`}
                            >
                              {c.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="p-8 text-center text-xs text-gray-500">
                  No course records were found on this slip.
                </div>
              )}
            </div>

            {/* Collapsible Raw JSON Viewer */}
            <details className="group bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
              <summary className="px-6 py-3.5 cursor-pointer text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center justify-between select-none hover:bg-gray-50 transition-colors">
                <span className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-gray-500" />
                  <span>Raw Pipeline JSON Output</span>
                </span>
                <ChevronDown className="w-4 h-4 text-gray-400 group-open:rotate-180 transition-transform" />
              </summary>
              <div className="p-4 bg-gray-950 border-t border-gray-200">
                <pre className="text-emerald-400 font-mono text-xs overflow-x-auto max-h-96 leading-relaxed">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            </details>
          </div>
        )}
      </main>
    </div>
  );
}
