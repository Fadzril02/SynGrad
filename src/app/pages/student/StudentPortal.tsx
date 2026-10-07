import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { motion, AnimatePresence } from "motion/react";
import { 
  GraduationCap, Upload, FileText, LogOut, Menu, X, 
  FileUp, BarChart, CheckCircle, Target, Edit3, AlertTriangle, Clock,
  Loader2, CheckCircle2, ShieldAlert, MessageSquare, Sparkles
} from "lucide-react";
import { toast } from "sonner";
import { Button, Input } from "../../components/ui";
import { useAuth } from "../../../context/AuthContext";
import { db } from "../../../lib/supabase";
import { api } from "../../../lib/api";

import { StudentDashboardView } from "./StudentDashboardView";
import { AcademicHistoryView } from "./AcademicHistoryView";
import { DegreeAuditView } from "./DegreeAuditView";
import { CgpaCalculatorView } from "./CgpaCalculatorView";
import { AdvisingNotesView } from "./AdvisingNotesView";

export function StudentPortal() {
  const navigate = useNavigate();
  const { profile, logout, user } = useAuth();
  
  const [activeTab, setActiveTab] = useState("dashboard");
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isVerificationModalOpen, setIsVerificationModalOpen] = useState(false);
  const [isLockedOut, setIsLockedOut] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  const [courseHistory, setCourseHistory] = useState<any[]>([]);
  const [creditProgress, setCreditProgress] = useState<any[]>([]);
  const [stats, setStats] = useState<{
    cgpa: string;
    earned: number | null;
    required: number | null;
    progressError?: string | null;
  }>({
    cgpa: "0.00",
    earned: null,
    required: null,
    progressError: null,
  });
  const [progressData, setProgressData] = useState<any>(null);
  const [progressLoading, setProgressLoading] = useState<boolean>(true);
  const [progressError, setProgressError] = useState<string | null>(null);
  const fetchedMatricRef = React.useRef<string | null>(null);
  const inFlightRef = React.useRef<boolean>(false);
  const [hasUnseenNotes, setHasUnseenNotes] = useState(false);
  const [loadingData, setLoadingData] = useState(true);

  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatusMsg, setUploadStatusMsg] = useState("");
  const [stagedData, setStagedData] = useState<any>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);

  const studentName = (profile as any)?.name || (profile as any)?.full_name || "Student";
  const isStudent = profile?.role === "student";
  const studentMatric = isStudent ? profile.matric_no : "";

  // Guard: If profile is not linked to a real student row, block rendering completely
  if (!profile || profile.role !== "student" || !profile.matric_no) {
    return (
      <div className="min-h-screen bg-[#F8F9FA] flex flex-col items-center justify-center p-6 text-center">
        <div className="max-w-md bg-white p-8 rounded-2xl shadow-sm border border-red-200 space-y-4">
          <div className="w-12 h-12 rounded-full bg-red-50 border border-red-100 flex items-center justify-center mx-auto text-red-600">
            <ShieldAlert size={28} />
          </div>
          <h2 className="text-base font-bold text-gray-900">Record Not Linked</h2>
          <p className="text-xs text-gray-600 leading-relaxed">
            Your account exists but is not linked to a valid student record. Please contact your advisor.
          </p>
          <Button onClick={logout} className="w-full bg-blue-900 hover:bg-blue-800 text-white text-xs py-2 rounded-lg cursor-pointer">
            Sign Out Platform
          </Button>
        </div>
      </div>
    );
  }

  // Prevent tab close or navigation during active cold-start transcript extraction
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isProcessing) {
        e.preventDefault();
        e.returnValue = "Document processing is underway. Leaving now may cause duplicate or corrupt uploads.";
        return e.returnValue;
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isProcessing]);

  useEffect(() => {
    // Profile must be loaded before we can fetch student data
    if (!profile?.matric_no) {
      setLoadingData(false);
      setProgressLoading(false);
      return;
    }

    const fetchDashboardData = async (force = false) => {
      if (!profile?.matric_no) {
        setLoadingData(false);
        setProgressLoading(false);
        return;
      }
      if (!force && (inFlightRef.current || fetchedMatricRef.current === profile.matric_no)) {
        return;
      }
      inFlightRef.current = true;
      setLoadingData(true);
      setProgressLoading(true);

      try {
        // ── Pending upload lockout check ────────────────────────────────────
        try {
          const { data: pendingDoc } = await db
            .from('uploaded_documents')
            .select('id')
            .eq('matric_no', profile.matric_no)
            .eq('processing_status', 'Pending_Advisor_Approval')
            .maybeSingle();
          if (pendingDoc) setIsLockedOut(true);
        } catch {
          // uploaded_documents table may not exist; lockout defaults to false
        }

        // ── Query students table for cgpa ──
        let studentCgpa: string = "0.00";

        try {
          const { data: studentRecord } = await db
            .from("students")
            .select("cgpa")
            .eq("matric_no", profile.matric_no)
            .maybeSingle();

          if (studentRecord && studentRecord.cgpa !== null && studentRecord.cgpa !== undefined) {
            studentCgpa = Number(studentRecord.cgpa).toFixed(2);
          }
        } catch (creditErr) {
          console.warn("[StudentPortal] Student record fetch warning:", creditErr);
        }

        // ── Query academic_records ──────────────────────────────────────────
        const { data: resultsData, error: resultsError } = await db
          .from("academic_records")
          .select(
            "course_code, course_name, credits, grade, grade_point, semester, status"
          )
          .eq("matric_no", profile.matric_no)
          .order("semester", { ascending: true });

        if (resultsError) {
          console.error("[StudentPortal] academic_records fetch error:", resultsError.message, resultsError.details);
        }

        const historyMapped = (resultsData || []).map((row: any) => ({
          code: row.course_code,
          name: row.course_name || "Unknown Module",
          credits: Number(row.credits) || 0,
          grade: row.grade || "N/A",
          status: row.status,
          pointValue: Number(row.grade_point) || 0,
          session_semester: row.semester,
        }));

        setCourseHistory(historyMapped);

        // ── Single source of truth for totals & progress: api.getProgress() ────
        let liveEarned: number | null = null;
        let dynamicRequiredCredits: number | null = null;
        let progressErrorMsg: string | null = null;

        setProgressError(null);
        try {
          const pData = await api.getProgress(profile.matric_no);
          setProgressData(pData);
          if (pData?.totals) {
            liveEarned = pData.totals.earned;
            dynamicRequiredCredits = pData.totals.required;
          }
        } catch (progErr: any) {
          progressErrorMsg = progErr?.response?.data?.detail || progErr?.message || "Failed to load progress";
          const formattedMsg = progErr?.response?.status === 409 ? `ℹ️ ${progressErrorMsg}` : progressErrorMsg;
          setProgressError(formattedMsg);
          console.warn("[StudentPortal] Progress fetch warning:", progressErrorMsg);
        } finally {
          setProgressLoading(false);
        }

        const liveCgpa = studentCgpa && Number(studentCgpa) > 0 ? studentCgpa : "0.00";

        setStats({
          cgpa: liveCgpa,
          earned: liveEarned,
          required: dynamicRequiredCredits,
          progressError: progressErrorMsg,
        });

        if (liveEarned !== null && dynamicRequiredCredits !== null) {
          const coreCredits = historyMapped
            .filter((c) => /^(SCSE|SECJ|SCS|SE|CS|SEC)/i.test(c.code) && (c.status === "Passed" || c.status === "Pass" || c.status === "Pass/Approved" || c.status === "Approved"))
            .reduce((sum, c) => sum + (c.credits || 0), 0);

          setCreditProgress([
            { name: "Syllabus Total", earned: liveEarned, total: dynamicRequiredCredits },
            {
              name: "Core Modules",
              earned: coreCredits,
              total: Math.round(dynamicRequiredCredits * 0.65),
            },
          ]);
        } else {
          setCreditProgress([]);
        }

        // ── Check for unseen shared advising notes ─────────────────────────
        try {
          const { data: unseenLogs } = await db
            .from("advising_logs")
            .select("id")
            .is("student_seen_at", null)
            .limit(1);
          if (unseenLogs && unseenLogs.length > 0) {
            setHasUnseenNotes(true);
          } else {
            setHasUnseenNotes(false);
          }
        } catch (notesErr) {
          console.warn("[StudentPortal] Check unseen notes warning:", notesErr);
        }
      } catch (err) {
        console.error("[StudentPortal] Dashboard load error:", err);
      } finally {
        inFlightRef.current = false;
        fetchedMatricRef.current = profile.matric_no;
        setLoadingData(false);
        setProgressLoading(false);
      }
    };

    fetchDashboardData();
  }, [profile?.matric_no]);

  // On opening the Advising Notes tab, set student_seen_at = now() for unseen logs
  useEffect(() => {
    if (activeTab === "advising") {
      const markSeen = async () => {
        try {
          const nowIso = new Date().toISOString();
          const { error } = await db
            .from("advising_logs")
            .update({ student_seen_at: nowIso })
            .is("student_seen_at", null);
          if (!error) {
            setHasUnseenNotes(false);
          }
        } catch (err) {
          console.warn("[StudentPortal] Failed to mark advising notes as seen:", err);
        }
      };
      markSeen();
    }
  }, [activeTab]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (isProcessing) return;
    const file = e.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error("Please upload an official PDF academic slip (.pdf only).");
        return;
      }
      setSelectedFile(file);
      setUploadStatusMsg("");
      setUploadProgress(0);
    }
  };

  const handleUploadTranscript = async () => {
    if (isProcessing) return;
    if (!selectedFile) {
      toast.error("Please select a transcript PDF file first.");
      return;
    }
    if (!profile?.matric_no) {
      toast.error("Student profile not found. Please log in again.");
      return;
    }

    setIsProcessing(true);
    setUploadProgress(15);
    setUploadStatusMsg("Uploading to secure vault...");

    let createdDocId: string | null = null;

    try {
      const extension = selectedFile.name.split(".").pop() || "pdf";
      const fileName = `${profile.matric_no}_${Date.now()}.${extension}`;
      const filePath = `slips/${fileName}`;

      setUploadProgress(35);
      const { error: uploadErr } = await db.storage.from("academic-slips").upload(filePath, selectedFile);
      if (uploadErr) throw uploadErr;

      setUploadProgress(50);
      setUploadStatusMsg("Registering audit document entry...");

      const { data: docData, error: docErr } = await db.from("uploaded_documents").insert([{
        matric_no: profile.matric_no,
        file_name: selectedFile.name,
        file_path: filePath,
        processing_status: 'Pending_Student_Verification'
      }]).select().single();
      
      if (docErr) throw docErr;
      createdDocId = docData.id;
      setActiveDocumentId(docData.id);

      setUploadProgress(70);
      setUploadStatusMsg("Analyzing Academic Data via AI (May take up to 60s)...");

      // Idempotency Safeguard: 75-second timeout limit against cold-start hangs
      const timeoutSafeguard = new Promise((_, reject) =>
        setTimeout(
          () =>
            reject(
              new Error(
                "Document extraction timed out after 75 seconds. The server cold-start took too long. Please retry."
              )
            ),
          75000
        )
      );

      const tenantId = (profile as any)?.tenant_id || (profile as any)?.university_id;
      const result = (await Promise.race([
        api.extractTranscript(filePath, tenantId),
        timeoutSafeguard
      ])) as any;

      setUploadProgress(100);
      setUploadStatusMsg("Extraction Complete! Review required.");
      toast.success("Transcript parsed successfully! Review extracted courses.");

      setTimeout(() => {
        setStagedData(result.data);
        setIsUploadModalOpen(false);
        setSelectedFile(null);
        setUploadProgress(0);
        setIsVerificationModalOpen(true);
      }, 700);

    } catch (err: any) {
      console.error("Upload error:", err);

      // Failure status is recorded server-side by /audit/extract (students cannot write it).

      let friendlyError = "Failed to process document. Please try again.";
      if (err.message?.includes("timed out") || err.message?.includes("75 seconds")) {
        friendlyError = "Upload timeout (75s limit reached). Backend cold-start took too long. Please retry in a moment.";
      } else if (err.response?.data?.detail) {
        friendlyError = `Extraction failed: ${err.response.data.detail}`;
      } else if (err.message) {
        friendlyError = err.message;
      }
      toast.error(friendlyError);
      setUploadStatusMsg(`Error: ${friendlyError}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleStagedDataChange = (index: number, field: string, value: string) => {
    const newData = { ...stagedData };
    if (!newData.courses || !newData.courses[index]) return;

    // Grade and Course Code Provenance Tracking (Anti-Tampering)
    if (!newData.courses[index].ai_grade && field === "grade") {
      newData.courses[index].ai_grade = newData.courses[index].grade; // Store original AI grade before overwriting
    }
    if (!newData.courses[index].ai_course_code && field === "course_code") {
      newData.courses[index].ai_course_code = newData.courses[index].course_code; // Store original AI course code
    }

    newData.courses[index].is_altered = true;
    newData.courses[index][field] = value.toUpperCase();
    setStagedData(newData);
  };

  const handleConfirmAndSave = async () => {
    if (!profile?.matric_no || !activeDocumentId) return;
    setIsSaving(true);
    try {
      // Server compares these rows with its stored extraction and flags any changes for the advisor
      await api.submitVerification(activeDocumentId, stagedData?.courses || []);

      setIsVerificationModalOpen(false);
      setIsLockedOut(true);
      fetchedMatricRef.current = null;
      toast.success("Slip verified and sent to your Advisor for official approval!");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to submit ticket. Please try again.");
      console.error("Upload error:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const NavItem = ({ 
    id, 
    icon: Icon, 
    label, 
    badge 
  }: { 
    id: string; 
    icon: any; 
    label: string; 
    badge?: React.ReactNode 
  }) => (
    <button 
      onClick={() => { setActiveTab(id); setIsMobileMenuOpen(false); }} 
      className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg transition-all tracking-tight cursor-pointer ${
        activeTab === id 
          ? "bg-blue-50 text-blue-900 font-semibold border border-blue-100 shadow-sm" 
          : "text-gray-600 hover:bg-gray-50 hover:text-gray-900 border border-transparent font-medium"
      }`}
    >
      <div className="flex items-center space-x-3">
        <Icon className={`w-4 h-4 shrink-0 ${activeTab === id ? "text-blue-900" : "text-gray-500"}`} />
        <span className="text-xs">{label}</span>
      </div>
      {badge}
    </button>
  );

  if (loadingData) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[#F9FAFB] text-blue-900 font-mono tracking-widest text-xs uppercase">
        <Loader2 className="w-5 h-5 mr-2 animate-spin text-blue-900" />
        INITIALIZING STUDENT PORTAL...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F9FAFB] flex font-sans text-gray-900 antialiased">
      {/* Mobile Drawer Backdrop */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-gray-900/40 backdrop-blur-xs z-40 lg:hidden transition-opacity"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Academic Minimalist Light Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 transform transition-transform duration-200 ease-in-out flex flex-col ${
        isMobileMenuOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      }`}>
        {/* Brand Header */}
        <div className="p-6 border-b border-gray-200 flex items-center space-x-3">
          <div className="w-10 h-10 rounded-lg bg-blue-900 flex items-center justify-center text-white shadow-sm">
            <GraduationCap className="w-5 h-5" />
          </div>
          <div>
            <span className="font-extrabold text-lg text-blue-900 tracking-tight leading-none block">SynGrad</span>
            <span className="text-[11px] text-gray-500 font-medium">Student Advising</span>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 p-4 space-y-1.5 overflow-y-auto">
          <NavItem id="dashboard" icon={BarChart} label="Dashboard Snapshot" />
          <NavItem id="history" icon={FileText} label="Academic Timeline" />
          <NavItem id="audit" icon={CheckCircle} label="Degree Audit" />
          <NavItem id="whatif" icon={Target} label="Grade Predictor" />
          <NavItem 
            id="advising" 
            icon={MessageSquare} 
            label="Advising Notes" 
            badge={hasUnseenNotes ? (
              <span className="px-1.5 py-0.5 text-[10px] font-bold bg-amber-500 text-white rounded-full leading-none shadow-2xs">
                New
              </span>
            ) : null}
          />
        </nav>

        {/* Student Profile Card & Sign Out */}
        <div className="p-4 border-t border-gray-200 bg-gray-50/50">
          <div className="flex items-center space-x-3 mb-3 p-2.5 rounded-lg bg-white border border-gray-200 shadow-sm">
            <div className="w-9 h-9 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center font-bold text-xs text-blue-900 shrink-0">
              {studentName ? studentName.slice(0, 2).toUpperCase() : "ST"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-semibold text-gray-900 truncate">{studentName}</div>
              <div className="text-[11px] font-mono text-gray-500 truncate">{studentMatric}</div>
            </div>
          </div>

          <button 
            onClick={logout} 
            className="w-full flex items-center justify-center space-x-2 px-3 py-2 rounded-lg text-xs font-medium text-gray-600 hover:bg-red-50 hover:text-red-700 hover:border-red-200 border border-transparent transition-colors cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out Platform</span>
          </button>
        </div>
      </aside>

      {/* Main Viewport */}
      <div className="flex-1 flex flex-col min-h-screen overflow-hidden">
        {/* Top Header Bar */}
        <header className="bg-white border-b border-gray-200 px-6 py-3.5 flex items-center justify-between sticky top-0 z-30">
          <div className="flex items-center space-x-3">
            <button 
              className="lg:hidden p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 transition-colors cursor-pointer" 
              onClick={() => setIsMobileMenuOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <div className="text-xs text-gray-500 font-medium">Student Advising Portal</div>
              <h1 className="text-lg font-bold text-gray-900 tracking-tight">
                {activeTab === "dashboard" && "Dashboard Snapshot"}
                {activeTab === "history" && "Academic Timeline"}
                {activeTab === "audit" && "Degree Audit"}
                {activeTab === "whatif" && "Grade Predictor"}
                {activeTab === "advising" && "Advising Notes"}
              </h1>
            </div>
          </div>
          
          <div className="flex items-center space-x-3">
            {isLockedOut ? (
              <div className="bg-amber-50 border border-amber-200 px-3.5 py-1.5 rounded-lg flex items-center text-amber-700 text-xs font-medium shadow-sm">
                <Clock className="w-4 h-4 mr-1.5 text-amber-600 shrink-0" />
                Under Advisor Review
              </div>
            ) : (
              <Button 
                onClick={() => setIsUploadModalOpen(true)} 
                disabled={isProcessing}
                className="bg-blue-900 hover:bg-blue-800 text-white font-medium rounded-lg shadow-sm transition-colors text-xs px-3.5 py-2 disabled:opacity-50 cursor-pointer"
              >
                <Upload className="w-4 h-4 mr-1.5" />
                Upload Transcript
              </Button>
            )}
          </div>
        </header>

        {/* Content Body Viewport */}
        <main className="flex-1 overflow-auto p-6 md:p-8 bg-[#F9FAFB]">
          <AnimatePresence mode="wait">
            <motion.div 
              key={activeTab} 
              initial={{ opacity: 0, y: 8 }} 
              animate={{ opacity: 1, y: 0 }} 
              exit={{ opacity: 0, y: -8 }} 
              className="max-w-6xl mx-auto space-y-6"
            >
              {activeTab === "dashboard" && <StudentDashboardView stats={stats} creditProgress={creditProgress} />}
              {activeTab === "history" && <AcademicHistoryView courseHistory={courseHistory} />}
              {activeTab === "audit" && (
                <DegreeAuditView 
                  cgpa={stats.cgpa} 
                  earnedCredits={stats.earned} 
                  totalRequiredCredits={stats.required} 
                  courses={courseHistory} 
                  matricNo={studentMatric}
                  progressData={progressData}
                  progressLoading={progressLoading}
                  progressError={progressError}
                />
              )}
              {activeTab === "whatif" && (
                <CgpaCalculatorView 
                  currentCgpa={Number(stats.cgpa || 0)} 
                  earnedCredits={Number(stats.earned || 0)} 
                  currentCredits={Number(stats.earned || 0)}
                  matricNo={studentMatric}
                />
              )}
              {activeTab === "advising" && <AdvisingNotesView />}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      {/* PDF Upload Modal */}
      <AnimatePresence>
        {isUploadModalOpen && (
          <div 
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/40 backdrop-blur-xs"
            onClick={() => {
              if (!isProcessing) setIsUploadModalOpen(false);
            }}
          >
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }} 
              animate={{ opacity: 1, scale: 1 }} 
              exit={{ opacity: 0, scale: 0.95 }} 
              className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-md overflow-hidden"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center bg-gray-50/50">
                <div className="flex items-center space-x-2">
                  <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-900">
                    <FileUp className="w-4 h-4" />
                  </div>
                  <h3 className="text-base font-bold text-gray-900">Upload Academic Slip</h3>
                </div>
                <button 
                  disabled={isProcessing}
                  onClick={() => setIsUploadModalOpen(false)}
                  className="p-1 rounded-md text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-6 space-y-5">
                {/* Cold-start idempotency notice banner */}
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700 flex items-start space-x-2">
                  <Clock className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <p className="leading-relaxed">
                    <strong className="font-semibold text-amber-900">Cold Start Notice:</strong> Extraction service spins down when idle. First document upload may take 30–60s. Please keep this tab open.
                  </p>
                </div>

                {/* PDF Upload Dropzone */}
                <div className={`border-2 border-dashed rounded-xl p-6 text-center transition-all relative ${
                  isProcessing 
                    ? "border-gray-200 bg-gray-50/50 cursor-not-allowed" 
                    : selectedFile 
                      ? "border-emerald-300 bg-emerald-50/20" 
                      : "border-gray-200 bg-gray-50 hover:border-blue-900/40 hover:bg-blue-50/20"
                }`}>
                  <FileUp className={`w-10 h-10 mx-auto mb-3 ${isProcessing ? "text-gray-300" : selectedFile ? "text-emerald-600" : "text-gray-400"}`} />
                  
                  <input 
                    type="file" 
                    className="hidden" 
                    id="file-uploader" 
                    accept=".pdf" 
                    disabled={isProcessing}
                    onChange={handleFileSelect} 
                  />

                  {selectedFile ? (
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-gray-900 truncate max-w-xs mx-auto">
                        {selectedFile.name}
                      </p>
                      <p className="text-xs text-gray-500">
                        {(selectedFile.size / 1024).toFixed(1)} KB • PDF Document
                      </p>
                      {!isProcessing && (
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedFile(null);
                            const input = document.getElementById("file-uploader") as HTMLInputElement | null;
                            if (input) input.value = "";
                          }}
                          className="text-xs text-rose-600 hover:underline pt-1 inline-block cursor-pointer font-medium"
                        >
                          Choose different file
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-xs text-gray-600">Select your official academic transcript or slip</p>
                      <Button 
                        type="button"
                        disabled={isProcessing}
                        className="bg-blue-900 hover:bg-blue-800 text-white font-medium rounded-lg shadow-sm transition-colors text-xs py-2 px-4 cursor-pointer" 
                        onClick={() => document.getElementById("file-uploader")?.click()}
                      >
                        Browse PDF Files
                      </Button>
                    </div>
                  )}
                </div>

                {/* Progress Indicator */}
                {uploadProgress > 0 && (
                  <div className="space-y-2 pt-1">
                    <div className="flex justify-between text-xs font-mono font-semibold">
                      <span className="text-gray-600 truncate mr-2">{uploadStatusMsg}</span>
                      <span className="text-blue-900 shrink-0">{uploadProgress}%</span>
                    </div>
                    <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden">
                      <div 
                        className="bg-blue-900 h-full transition-all duration-500" 
                        style={{ width: `${uploadProgress}%` }} 
                      />
                    </div>
                  </div>
                )}

                {/* Submit Action Button */}
                <div className="pt-2">
                  <Button
                    type="button"
                    disabled={!selectedFile || isProcessing}
                    onClick={handleUploadTranscript}
                    className="w-full bg-blue-900 hover:bg-blue-800 text-white py-2.5 font-medium rounded-lg shadow-sm transition-colors text-sm disabled:opacity-50 cursor-pointer"
                  >
                    {isProcessing ? (
                      <span className="flex items-center justify-center">
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Processing Document (May take up to 60s)...
                      </span>
                    ) : (
                      <span className="flex items-center justify-center">
                        <Upload className="w-4 h-4 mr-2" />
                        Upload Transcript
                      </span>
                    )}
                  </Button>
                </div>
              </div>
            </motion.div>
          </div>
        )}

        {/* Verification Modal */}
        {isVerificationModalOpen && stagedData && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-gray-900/40 backdrop-blur-xs">
            <motion.div 
              initial={{ opacity: 0, y: 20 }} 
              animate={{ opacity: 1, y: 0 }} 
              className="bg-white rounded-xl shadow-sm border border-gray-200 w-full max-w-2xl overflow-hidden flex flex-col max-h-[90vh]"
            >
              <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center bg-gray-50">
                <div className="flex items-center space-x-2">
                  <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-900">
                    <Edit3 className="w-4 h-4" />
                  </div>
                  <h3 className="text-base font-bold text-gray-900">Verify AI Extraction</h3>
                </div>
              </div>
              
              <div className="p-6 overflow-y-auto flex-1 space-y-4">
                {stagedData?.source === "ai" && (
                  <div className="bg-blue-50 border border-blue-200 text-blue-900 text-xs p-3.5 rounded-lg flex items-center font-medium">
                    <Sparkles className="w-4 h-4 mr-2.5 shrink-0 text-blue-800" />
                    <span>Read by AI — please check every row carefully</span>
                  </div>
                )}

                {stagedData?.warnings && stagedData.warnings.length > 0 && (
                  <div className="space-y-2">
                    {stagedData.warnings.map((w: string, idx: number) => {
                      const isMatricMismatch = w.toLowerCase().includes("someone else");
                      return (
                        <div
                          key={idx}
                          className={`p-3 rounded-lg border text-xs flex items-start ${
                            isMatricMismatch
                              ? "bg-rose-50 border-rose-300 text-rose-900 font-semibold"
                              : "bg-amber-50 border-amber-300 text-amber-900"
                          }`}
                        >
                          <AlertTriangle className={`w-4 h-4 mr-2 shrink-0 mt-0.5 ${isMatricMismatch ? "text-rose-600" : "text-amber-600"}`} />
                          <div>
                            <span className="font-bold block">{isMatricMismatch ? "Matric Mismatch Alert (Submission Blocked)" : "Transcript Warning"}</span>
                            <span>{w}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="bg-blue-50/60 border border-blue-100 text-blue-900 text-xs p-3.5 rounded-lg flex items-start">
                  <AlertTriangle className="w-4 h-4 mr-2.5 shrink-0 mt-0.5 text-blue-800" />
                  <p className="leading-relaxed">
                    Check the extracted course codes and grades. Correct any discrepancies before submitting to your academic advisor for formal approval.
                  </p>
                </div>

                {(() => {
                  const isMultiSem = Boolean(
                    (stagedData?.semesters && stagedData.semesters.length > 1) ||
                    (stagedData?.courses && new Set(stagedData.courses.map((c: any) => c.session_semester).filter(Boolean)).size > 1)
                  );
                  return (
                    <div className="border border-gray-200 rounded-lg overflow-hidden">
                      <table className="w-full text-left">
                        <thead className="bg-gray-50 border-b border-gray-200">
                          <tr>
                            {isMultiSem && (
                              <th className="px-4 py-2.5 text-xs font-semibold text-gray-600 uppercase">Semester</th>
                            )}
                            <th className="px-4 py-2.5 text-xs font-semibold text-gray-600 uppercase">Course Code</th>
                            <th className="px-4 py-2.5 text-xs font-semibold text-gray-600 uppercase">Grade</th>
                            <th className="px-4 py-2.5 text-xs font-semibold text-gray-600 uppercase">Credits</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {(stagedData?.courses || []).map((course: any, index: number) => (
                            <tr key={index} className="hover:bg-gray-50/50">
                              {isMultiSem && (
                                <td className="px-4 py-2 font-mono text-xs text-gray-700">
                                  {course?.session_semester || "—"}
                                </td>
                              )}
                              <td className="px-4 py-2">
                                <Input 
                                  value={course?.course_code || ""} 
                                  onChange={(e) => handleStagedDataChange(index, "course_code", e.target.value)} 
                                  className="font-mono text-sm max-w-[140px] bg-gray-50 border-gray-200 focus:ring-2 focus:ring-blue-900 focus:border-transparent text-gray-900" 
                                />
                              </td>
                              <td className="px-4 py-2">
                                <Input 
                                  value={course?.grade || ""} 
                                  onChange={(e) => handleStagedDataChange(index, "grade", e.target.value)} 
                                  className="font-bold text-sm max-w-[80px] bg-gray-50 border-gray-200 focus:ring-2 focus:ring-blue-900 focus:border-transparent text-gray-900 uppercase" 
                                />
                              </td>
                              <td className="px-4 py-2 font-mono text-sm text-gray-700">{course?.credit_hour ?? course?.credits ?? 0}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })()}
              </div>

              <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end space-x-3">
                {(() => {
                  const hasMatricMismatch = Boolean(
                    (stagedData?.warnings || []).some((w: string) =>
                      w.toLowerCase().includes("someone else")
                    )
                  );
                  return (
                    <Button 
                      onClick={handleConfirmAndSave} 
                      disabled={isSaving || hasMatricMismatch} 
                      className="bg-blue-900 hover:bg-blue-800 text-white font-medium rounded-lg shadow-sm transition-colors text-sm px-4 py-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isSaving ? (
                        "Submitting..."
                      ) : hasMatricMismatch ? (
                        "Submission Blocked (Matric Mismatch)"
                      ) : (
                        <>
                          <CheckCircle className="w-4 h-4 mr-2" />
                          Confirm &amp; Submit
                        </>
                      )}
                    </Button>
                  );
                })()}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}