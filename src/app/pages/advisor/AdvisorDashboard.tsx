import React, { useState, useEffect, useCallback } from "react";
import { PRODUCT } from "../../../config/product";
import { 
  Users, 
  AlertTriangle, 
  ClipboardCheck, 
  Percent, 
  Loader2, 
  Copy, 
  Check, 
  Download, 
  Upload, 
  FileSpreadsheet, 
  ExternalLink, 
  CheckCircle2, 
  FileUp, 
  X, 
  AlertCircle, 
  BookOpen, 
  RotateCw, 
  Lock, 
  Unlock, 
  KeyRound, 
  ShieldCheck, 
  ShieldAlert, 
  Trash2, 
  Plus, 
  RefreshCw, 
  GraduationCap 
} from "lucide-react";
import { toast } from "sonner";
import { db, supabase } from "../../../lib/supabase"; 
import { useAuth } from "../../../context/AuthContext";
import { api } from "../../../lib/api";
import { resolveUniName } from "../../../lib/tenants";
import { Switch } from "../../components/ui/switch";
import { TrafficLightGrid, CourseAuditItem } from "../../../components/advisor/TrafficLightGrid";

export function AdvisorDashboard() {
  const { profile, user } = useAuth();
  const [roster, setRoster] = useState<any[]>([]);
  const [queue, setQueue] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeStudent, setActiveStudent] = useState<any | null>(null);

  // Cohort Management State (Multi-Tenant Blueprint Architecture)
  interface AdvisorCohort {
    id: string;
    cohort_name: string;
    name?: string;
    cohort_code: string;
    is_locked: boolean;
    advisor_staff_id: string;
    template_id: string;
    degree_template_id?: string;
    degree_templates?: {
      program_code?: string;
      program_name?: string;
      syllabus_year?: string;
    } | {
      program_code?: string;
      program_name?: string;
      syllabus_year?: string;
    }[];
  }

  interface DegreeTemplate {
    id: string;
    university_name: string;
    program_code: string;
    program_name: string;
    syllabus_year: string;
    total_credits_required?: number;
  }

  const [cohorts, setCohorts] = useState<AdvisorCohort[]>([]);
  const [degreeTemplates, setDegreeTemplates] = useState<DegreeTemplate[]>([]);
  const [togglingCohortId, setTogglingCohortId] = useState<string | null>(null);
  const [deletingCohortId, setDeletingCohortId] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // Create Cohort Modal State
  const [isCreateCohortOpen, setIsCreateCohortOpen] = useState(false);
  const [cohortName, setCohortName] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [generatedCode, setGeneratedCode] = useState("");
  const [isCreatingCohort, setIsCreatingCohort] = useState(false);
  const [createdCohortResult, setCreatedCohortResult] = useState<AdvisorCohort | null>(null);
  const [copiedNewCode, setCopiedNewCode] = useState(false);

  // Recent Enrollments State (Loose Admission Safety Net)
  interface RecentEnrollment {
    matric_no: string;
    user_id: string | null;
    name: string;
    institutional_email: string;
    cohort_id: string | null;
    created_at?: string;
  }
  const [recentEnrollments, setRecentEnrollments] = useState<RecentEnrollment[]>([]);

  // Curriculum Upload Modal State
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [uploadMessage, setUploadMessage] = useState<string>("");
  const [templateName, setTemplateName] = useState<string>("");
  const [programCode, setProgramCode] = useState<string>("");
  const [syllabusYear, setSyllabusYear] = useState<string>("");
  const [totalCredits, setTotalCredits] = useState<string>("");

  const advisorStaffId = (profile as any)?.staff_id;
  const tenantId = (profile as any)?.tenant_id || (profile as any)?.university_id;
  
  // Helper: Generate random 6-character alphanumeric cohort_code (e.g. "SECJ99")
  const generateCohortCode = (programCode: string = "SECJ"): string => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    const prefix = programCode ? programCode.replace(/[^A-Za-z0-9]/g, "").toUpperCase().slice(0, 4) : "SECJ";
    const needed = Math.max(0, 6 - prefix.length);
    let suffix = "";
    for (let i = 0; i < needed; i++) {
      suffix += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return `${prefix}${suffix}`.slice(0, 6);
  };

  const fetchDashboardData = useCallback(async (isSilent = false) => {
    // Security Check: Guard to ensure advisor context is loaded before querying
    if (!advisorStaffId) {
      if (!isSilent) setIsLoading(false);
      return;
    }

    if (!isSilent) setIsLoading(true);
    try {
      // 1. Fetch degree templates strictly scoped by tenant_id
      let templatesData: DegreeTemplate[] = [];
      const cacheKey = `syngrad_degree_templates_${tenantId}`;
      const cachedTemplates = sessionStorage.getItem(cacheKey);

      if (cachedTemplates) {
        try {
          const parsed = JSON.parse(cachedTemplates);
          if (Array.isArray(parsed) && parsed.length > 0) {
            templatesData = parsed;
          } else {
            sessionStorage.removeItem(cacheKey);
          }
        } catch (parseErr) {
          sessionStorage.removeItem(cacheKey);
        }
      }

      // If sessionStorage is empty or invalid, trigger a fresh network request strictly scoped by tenant_id
      if (templatesData.length === 0) {
        let tmplQuery = db
          .from("degree_templates")
          .select("id, university_name, program_code, program_name, syllabus_year, total_credits_required, tenant_id");
        if (tenantId) {
          tmplQuery = tmplQuery.eq("tenant_id", tenantId);
        }
        const { data: tmplData, error: tmplError } = await tmplQuery.order("program_code", { ascending: true });

        if (!tmplError && tmplData && Array.isArray(tmplData)) {
          templatesData = tmplData;
          if (tmplData.length > 0) {
            sessionStorage.setItem(cacheKey, JSON.stringify(tmplData));
          }
        } else {
          templatesData = [];
        }
      }

      // 2. Fetch advisee roster summary — ALWAYS fetch fresh data
      const rosterCacheKey = `syngrad_advisee_roster_${advisorStaffId}`;
      let rawRosterData: any[] | null = null;

      sessionStorage.removeItem(rosterCacheKey);
      sessionStorage.removeItem(`luma_advisee_roster_${advisorStaffId}`);

      {
        const studentsRes = await db
          .from("advisee_roster_summary")
          .select("*")
          .eq("advisor_staff_id", advisorStaffId)
          .order("student_name", { ascending: true });

        if (!studentsRes.error && studentsRes.data && Array.isArray(studentsRes.data)) {
          rawRosterData = studentsRes.data;
          if (studentsRes.data.length > 0) {
            sessionStorage.setItem(rosterCacheKey, JSON.stringify(studentsRes.data));
          }
        } else {
          console.warn("[AdvisorDashboard] advisee_roster_summary query notice:", studentsRes.error?.message || "empty response");
          const fallbackRes = await db
            .from("students")
            .select("matric_no, user_id, name, institutional_email, cohort_id, cgpa, academic_status, program, advisor_staff_id")
            .eq("advisor_staff_id", advisorStaffId)
            .order("name", { ascending: true });
          rawRosterData = (fallbackRes.data && Array.isArray(fallbackRes.data)) ? fallbackRes.data : [];
        }
      }

      // 3. Fetch cohorts and correction requests in parallel strictly scoped by tenant_id
      let cohortsQuery = db
        .from("cohorts")
        .select(`
          id,
          cohort_name,
          cohort_code,
          is_locked,
          advisor_staff_id,
          template_id,
          degree_templates (
            program_code,
            program_name,
            syllabus_year
          )
        `)
        .eq("advisor_staff_id", advisorStaffId);

      if (tenantId) {
        cohortsQuery = cohortsQuery.eq("tenant_id", tenantId);
      }

      const queueQuery = db.from("correction_requests").select("*");

      const [cohortsRes, queueRes] = await Promise.all([
        cohortsQuery.order("created_at", { ascending: false }),
        queueQuery
      ]);

      // Bind roster
      if (rawRosterData && rawRosterData.length > 0) {
        const formatted = rawRosterData.map((s: any) => ({
          ...s,
          id: s.matric_no,
          name: s.student_name || s.name || s.matric_no,
          cgpa: Number(s.current_cgpa ?? s.cgpa ?? 0),
          traffic_light: (s.traffic_light_status || s.traffic_light || (Number(s.cgpa) < 2.0 ? "RED" : "GREEN")) as "RED" | "YELLOW" | "GREEN",
          traffic_light_status: s.traffic_light_status || s.traffic_light || "GREEN",
          total_earned_credits: Number(s.total_earned_credits ?? 0),
          academic_status: s.academic_status || "Good Standing",
          unmet_prereq_count: Number(s.unmet_prerequisites_count ?? 0),
          records: s.records || []
        }));
        setRoster(formatted);

        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);
        const recent = formatted.filter(s => s.created_at && new Date(s.created_at) >= sevenDaysAgo);
        setRecentEnrollments(recent as RecentEnrollment[]);
      } else {
        setRoster([]);
        setRecentEnrollments([]);
      }

      // Bind queues and cohorts
      setQueue((queueRes.data && Array.isArray(queueRes.data)) ? queueRes.data : []);
      setCohorts((cohortsRes.data && Array.isArray(cohortsRes.data)) ? (cohortsRes.data as AdvisorCohort[]) : []);

      // Bind degree templates
      if (templatesData && templatesData.length > 0) {
        setDegreeTemplates(templatesData);
        if (!selectedTemplateId) {
          const firstTmpl = templatesData[0];
          setSelectedTemplateId(firstTmpl.id);
          setGeneratedCode(generateCohortCode(firstTmpl.program_code));
          setCohortName(`${firstTmpl.program_code} ${firstTmpl.syllabus_year || "2024/2025"}`);
        }
      } else {
        setDegreeTemplates([]);
      }
    } catch (error) {
      console.error("Failed to load dashboard data:", error);
    } finally {
      if (!isSilent) setIsLoading(false);
    }
  }, [advisorStaffId, tenantId, selectedTemplateId]);

  useEffect(() => {
    fetchDashboardData();

    // Safety timer (2.5 seconds): unconditionally flips page-level loading state to false
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 2500);
    return () => clearTimeout(timer);
  }, [fetchDashboardData]);

  // Task 4: Wake-Up Data Refresh on window focus
  useEffect(() => {
    const handleFocus = () => {
      console.log("Tab regained focus. Refreshing dashboard data...");
      fetchDashboardData(true);
    };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [fetchDashboardData]);

  // Lock Toggle Handler: updates is_locked in cohorts table for specific cohort
  const handleToggleCohortLock = async (cohortId: string, currentStatus: boolean) => {
    const nextStatus = !currentStatus;
    setTogglingCohortId(cohortId);
    try {
      const { error } = await db
        .from("cohorts")
        .update({ is_locked: nextStatus, updated_at: new Date().toISOString() })
        .eq("id", cohortId);

      if (error) throw error;

      setCohorts((prev) =>
        prev.map((c) => (c.id === cohortId ? { ...c, is_locked: nextStatus } : c))
      );
      toast.success(
        nextStatus
          ? "Cohort registration locked. Advisees cannot join with this code."
          : "Cohort registration unlocked. Advisees can now join."
      );
    } catch (err: any) {
      console.error("Failed to update cohort lock:", err);
      toast.error(err.message || "Failed to update cohort lock status.");
    } finally {
      setTogglingCohortId(null);
    }
  };

  // Delete Cohort Handler: safely removes empty cohorts
  const handleDeleteCohort = async (cohortId: string, studentCount: number) => {
    // Step 3a (Validation Gate): If studentCount > 0, trigger an immediate UI block
    if (studentCount > 0) {
      alert("Cannot delete this cohort because it has active students assigned. Please reassign the students first.");
      return;
    }

    // Step 3b (Confirmation Gate)
    const confirm = window.confirm("Are you sure you want to delete this cohort? This action cannot be undone.");
    if (!confirm) return;

    setDeletingCohortId(cohortId);
    try {
      // Step 3c (Database Execution)
      const { error } = await db.from("cohorts").delete().eq("id", cohortId);

      // Step 3d (Error Handling)
      if (error) {
        console.error("Failed to delete cohort:", error);
        alert(error.message);
        return;
      }

      // Step 3e (Optimistic UI Update)
      setCohorts((prev) => prev.filter((c) => c.id !== cohortId));
      toast.success("Cohort deleted successfully.");
    } catch (err: any) {
      console.error("Unexpected error deleting cohort:", err);
      alert(err?.message || "Failed to delete cohort.");
    } finally {
      setDeletingCohortId(null);
    }
  };

  const handleInspectStudent = async (student: any) => {
    setActiveStudent(student);
    if (!student.records || student.records.length === 0) {
      try {
        const { data: recs } = await db
          .from("academic_records")
          .select("*")
          .eq("matric_no", student.matric_no)
          .order("semester", { ascending: true });
        if (recs && recs.length > 0) {
          const formattedRecords: CourseAuditItem[] = recs.map((r: any) => ({
            course_code: r.course_code,
            course_name: r.course_name || r.course_code,
            credits: r.credits || 3,
            grade: r.grade,
            grade_point: Number(r.grade_point) || 0.0,
            semester: r.semester || "Sem 1",
            status: r.status,
            traffic_light: (r.status === "Failed" || !r.prerequisite_met ? "RED" : (r.status === "In-Progress" ? "YELLOW" : "GREEN")),
            prerequisite_met: r.prerequisite_met,
            missing_prerequisites: r.missing_prerequisites || [],
            is_ai_parsed: r.is_ai_parsed
          }));
          setActiveStudent((prev: any) => prev && prev.matric_no === student.matric_no ? { ...prev, records: formattedRecords } : prev);
        }
      } catch (err) {
        console.warn("[AdvisorDashboard] Lazy fetch academic_records failed:", err);
      }
    }
  };

  // Copy specific cohort code handler
  const handleCopyCohortCode = async (code: string) => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      toast.success(`Cohort code "${code}" copied to clipboard!`);
      setTimeout(() => setCopiedCode(null), 2500);
    } catch (err) {
      console.error("Failed to copy code:", err);
      toast.error("Failed to copy code to clipboard.");
    }
  };

  // Open Create Cohort Modal
  const handleOpenCreateCohort = () => {
    setCreatedCohortResult(null);
    setCopiedNewCode(false);
    const tmpl = degreeTemplates.find((t) => t.id === selectedTemplateId) || degreeTemplates[0];
    if (tmpl) {
      setSelectedTemplateId(tmpl.id);
      setGeneratedCode(generateCohortCode(tmpl.program_code));
      setCohortName(`${tmpl.program_code} ${tmpl.syllabus_year || "2024/2025"}`);
    } else {
      setGeneratedCode(generateCohortCode("SECJ"));
      setCohortName("SECJ 2024/2025");
    }
    setIsCreateCohortOpen(true);
  };

  // Change Template selection
  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId);
    const tmpl = degreeTemplates.find((t) => t.id === templateId);
    if (tmpl) {
      const code = generateCohortCode(tmpl.program_code);
      setGeneratedCode(code);
      setCohortName(`${tmpl.program_code} ${tmpl.syllabus_year || "2024/2025"}`);
    }
  };

  // Create Cohort Handler: direct Supabase insert into cohorts table respecting RLS
  const handleCreateCohort = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!advisorStaffId) {
      toast.error("Advisor session error: staff_id missing. Please re-login.");
      return;
    }
    if (!selectedTemplateId) {
      toast.error("Please select a degree template.");
      return;
    }
    if (!cohortName.trim()) {
      toast.error("Please enter a cohort name.");
      return;
    }

    const codeToInsert = generatedCode || generateCohortCode();
    setIsCreatingCohort(true);

    try {
      const { data, error } = await db
        .from("cohorts")
        .insert({
          cohort_name: cohortName.trim(),
          advisor_staff_id: advisorStaffId,
          template_id: selectedTemplateId,
          cohort_code: codeToInsert,
          is_locked: false,
          tenant_id: tenantId,
        })
        .select(`
          id,
          cohort_name,
          cohort_code,
          is_locked,
          advisor_staff_id,
          template_id,
          degree_templates (
            program_code,
            program_name,
            syllabus_year
          )
        `)
        .single();

      if (error) throw error;

      const createdCohort = data as AdvisorCohort;

      // Update UI state immediately
      setCohorts((prev) => [createdCohort, ...prev]);
      setCreatedCohortResult(createdCohort);
      toast.success(`Cohort "${createdCohort.cohort_name}" created successfully!`);
    } catch (err: any) {
      console.error("Failed to insert cohort:", err);
      toast.error(err.message || "Failed to create cohort in Supabase.");
    } finally {
      setIsCreatingCohort(false);
    }
  };

  // Copy newly created cohort code
  const handleCopyNewCohortCode = async (code: string) => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopiedNewCode(true);
      toast.success(`Cohort code "${code}" copied to clipboard!`);
      setTimeout(() => setCopiedNewCode(false), 2500);
    } catch (err) {
      console.error("Failed to copy code:", err);
      toast.error("Failed to copy code to clipboard.");
    }
  };

  // Standard Template CSV Generator and Downloader
const handleDownloadTemplate = () => {
  // Must match backend/app/engine/parsers/csv_course_parser.py:
  // course_code, course_name, credits, category, prerequisites
  // - prerequisites: "CODE1 AND CODE2", "CODE1 OR CODE2", optional "min_grade: B", "min_credits: 80"
  // - elective slot: code with "XX" (wildcard) or "/" (alternatives); repeat the row once per slot
  const header = ["course_code", "course_name", "credits", "category", "prerequisites"];

  const rows: string[][] = [
    ["CS1013", "Introduction to Programming", "3", "Core", ""],
    ["CS1023", "Programming Techniques II", "3", "Core", "CS1013"],
    ["CS2013", "Data Structures and Algorithms", "3", "Core", "CS1023 min_grade: B"],
    ["CS2203", "Software Engineering", "3", "Core", "CS1023 AND CS2013"],
    ["CS3032", "Final Year Project 1", "2", "Core", "CS2203 min_credits: 80"],
    ["CSXXXX3", "Free Elective", "3", "Elective", ""],
    ["CSXXXX3", "Free Elective", "3", "Elective", ""],
    ["CS5XX3/IT5XX3", "Specialisation Elective (choose one)", "3", "Elective", ""],
    ["GEN1012", "Creative Thinking, Innovation and Society", "2", "University", ""],
  ];

  // Quote every field and escape quotes so commas in names don't break columns
  const toCsvLine = (fields: string[]) =>
    fields.map((f) => `"${String(f).replace(/"/g, '""')}"`).join(",");

  const csv = [toCsvLine(header), ...rows.map(toCsvLine)].join("\r\n");

  // UTF-8 BOM so Excel opens it with the correct encoding
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "syngrad_curriculum_template.csv";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

  // Handle Curriculum File Selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setUploadStatus("idle");
      setUploadMessage("");
    }
  };

  // Handle Curriculum Upload Submission
  const handleUploadSubmit = async (e?: React.FormEvent | any) => {
    if (e && e.preventDefault) e.preventDefault();
    
    if (!selectedFile) {
      setUploadStatus("error");
      setUploadMessage("Please select a curriculum CSV file to upload.");
      return;
    }
    if (!templateName.trim()) {
      setUploadStatus("error");
      setUploadMessage("Please enter the Degree Template Name.");
      return;
    }
    if (!programCode.trim()) {
      setUploadStatus("error");
      setUploadMessage("Please enter the Program Code.");
      return;
    }
    if (!syllabusYear.trim()) {
      setUploadStatus("error");
      setUploadMessage("Please enter the Syllabus Year (e.g. 2024/2025).");
      return;
    }
    if (!/^\d+$/.test(totalCredits) || Number(totalCredits) <= 0) {
      setUploadStatus("error");
      setUploadMessage("Please enter a valid total credits requirement.");
      return;
    }

    setUploadStatus("uploading");
    setUploadMessage("Uploading & ingesting curriculum via prerequisite engine...");

    try {
      const result = await api.uploadCoursesCSV(
        selectedFile,
        templateName.trim(),
        programCode.trim().toUpperCase(),
        Number(totalCredits),
        syllabusYear.trim()
      );
      const insertedCount = result.total_inserted ?? result.total_parsed ?? 0;

      // Invalidate sessionStorage cache after successful upload
      if (tenantId) {
        sessionStorage.removeItem(`syngrad_degree_templates_${tenantId}`);
      }
      sessionStorage.removeItem("syngrad_degree_templates");
      sessionStorage.removeItem("luma_degree_templates");

      // Refresh degree templates strictly filtered by tenant_id
      try {
        let refreshQuery = db
          .from("degree_templates")
          .select("id, university_name, program_code, program_name, syllabus_year, total_credits_required, tenant_id");
        if (tenantId) {
          refreshQuery = refreshQuery.eq("tenant_id", tenantId);
        }
        const { data: updatedTemplates } = await refreshQuery.order("program_code", { ascending: true });
        if (updatedTemplates) {
          if (tenantId) {
            sessionStorage.setItem(`syngrad_degree_templates_${tenantId}`, JSON.stringify(updatedTemplates));
          }
          setDegreeTemplates(updatedTemplates);
        }
      } catch (refreshErr) {
        console.warn("Could not refresh degree templates list:", refreshErr);
      }

      // Set success state and show feedback toast
      setUploadStatus("success");
      setUploadMessage(`Successfully parsed & ingested ${insertedCount} courses into degree template "${templateName.trim()}".`);
      toast.success(`Ingested ${insertedCount} courses and created template "${templateName.trim()}".`, {
        duration: 5000
      });

      // Call silent refresh so new templates appear in UI immediately
      fetchDashboardData(true);

      // Delay closing modal and resetting idle status so user can see success feedback
      setTimeout(() => {
        setIsUploadModalOpen(false);
        setSelectedFile(null);
        setTemplateName("");
        setProgramCode("");
        setSyllabusYear("");
        setTotalCredits("");
        setUploadMessage("");
        setUploadStatus("idle");
      }, 2500);

    } catch (err: any) {
      setUploadStatus("error");
      const detail = err?.response?.data?.detail || err?.message || "Failed to parse and upload course CSV.";
      setUploadMessage(typeof detail === "string" ? detail : JSON.stringify(detail));
      toast.error(`Upload failed: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`, {
        duration: 7000
      });
    } finally {
      // Ensure file input state is cleaned up so the same file can be re-uploaded if needed
      const fileInput = document.getElementById("curriculum-upload-input") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center p-24 text-gray-500 bg-white rounded-xl border border-gray-200 shadow-sm">
        <Loader2 className="animate-spin text-blue-900 w-8 h-8 mb-3" />
        <span className="text-xs font-mono uppercase tracking-wider">Syncing Cohort Diagnostics...</span>
      </div>
    );
  }

  // Calculate Metrics
  const totalStudents = roster.length;
  // Dynamic calculation for average credits
  const totalEarnedCredits = roster.reduce((sum, s) => sum + (Number(s.total_earned_credits) || 0), 0);
  const averageCredits = totalStudents > 0 ? Math.round(totalEarnedCredits / totalStudents) : 0;

  const atRiskStudents = roster.filter((s) => ["At-Risk", "Probation"].includes(s.academic_status) || Number(s.cgpa || 0) < 2.50);
  const pendingAudits = queue.filter((q) => q.status === "Pending").length;
  const totalCgpa = roster.reduce((sum, s) => sum + (Number(s.cgpa) || 0), 0);
  const averageCgpa = totalStudents > 0 ? totalCgpa / totalStudents : 0;

  // Prioritize At-Risk students at the top of the roster table
  const sortedRoster = [...roster].sort((a, b) => {
    const aAtRisk = ["At-Risk", "Probation"].includes(a.academic_status) || Number(a.cgpa || 0) < 2.50 ? 1 : 0;
    const bAtRisk = ["At-Risk", "Probation"].includes(b.academic_status) || Number(b.cgpa || 0) < 2.50 ? 1 : 0;
    return bAtRisk - aAtRisk;
  });

  return (
    <div className="space-y-6">
      {/* 1. COHORT MANAGEMENT CARD (Multi-Tenant Blueprint Architecture) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-gray-100">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-blue-50 text-blue-900 text-xs font-mono border border-blue-200 font-semibold">
                <KeyRound className="w-3.5 h-3.5" />
                Cohort Management
              </span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-gray-100 text-gray-700 text-xs font-mono font-medium">
                {cohorts.length} {cohorts.length === 1 ? "Cohort" : "Cohorts"} Active
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md bg-indigo-50 text-indigo-800 text-xs font-medium border border-indigo-200">
                <GraduationCap className="w-3.5 h-3.5 text-indigo-700" />
                {resolveUniName(tenantId)}
              </span>
            </div>
            <h3 className="text-xl font-bold tracking-tight text-gray-900">
              Advisor Cohort Gatekeeper
            </h3>
            <p className="text-sm text-gray-600 leading-relaxed max-w-2xl">
              Distribute cohort codes to your advisees. Students enter the code during registration to join your cohort roster with degree blueprints automatically assigned.
            </p>
          </div>

          {/* Header Action: Create Cohort Button (Rendered ONLY when cohorts exist) */}
          {cohorts.length > 0 && (
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                id="create-cohort-header-btn"
                onClick={handleOpenCreateCohort}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-900 hover:bg-blue-800 text-white text-xs font-semibold shadow-sm hover:shadow transition-all cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>Create Cohort</span>
              </button>
            </div>
          )}
        </div>

        {/* Cohorts List */}
        <div className="space-y-3">
          {cohorts.length === 0 ? (
            <div className="text-center py-12 px-6 bg-gradient-to-b from-blue-50/40 to-gray-50/60 rounded-xl border-2 border-dashed border-blue-200/80 flex flex-col items-center justify-center space-y-5">
              <div className="w-14 h-14 rounded-2xl bg-blue-900 text-white flex items-center justify-center shadow-md shadow-blue-900/10">
                <Users className="w-7 h-7" />
              </div>
              
              <div className="max-w-md text-center space-y-1.5">
                <h4 className="text-base font-bold text-gray-900">
                  Setup Your Advising Environment
                </h4>
                <p className="text-xs text-gray-600 leading-relaxed font-medium">
                  Follow these two steps to begin auditing student transcripts:
                </p>
              </div>

              {/* Two-Step Chronological Onboarding List */}
              <div className="w-full max-w-md bg-white border border-blue-100 rounded-xl p-4 text-left shadow-xs space-y-3">
                <div className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-900 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <span className="text-xs font-bold text-gray-900 block">
                      Upload Curriculum
                    </span>
                    <p className="text-[11px] text-gray-600 leading-relaxed mt-0.5">
                      Scroll down to 'Curriculum Management' and upload your course syllabus CSV to populate the prerequisite rules.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3 pt-2 border-t border-gray-100">
                  <div className="w-6 h-6 rounded-full bg-blue-900 text-white flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <span className="text-xs font-bold text-gray-900 block">
                      Create Cohort
                    </span>
                    <p className="text-[11px] text-gray-600 leading-relaxed mt-0.5">
                      Generate your 6-character cohort code to invite your students.
                    </p>
                  </div>
                </div>
              </div>

              <button
                type="button"
                id="create-cohort-empty-state-btn"
                onClick={handleOpenCreateCohort}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-900 hover:bg-blue-800 text-white text-xs font-semibold shadow-sm hover:shadow transition-all cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>Create Cohort</span>
              </button>
            </div>
          ) : (
            cohorts.map((cohort) => {
              const tmpl = Array.isArray(cohort.degree_templates)
                ? cohort.degree_templates[0]
                : cohort.degree_templates;
              const programCode = tmpl?.program_code || "Unassigned";
              const syllabusYear = tmpl?.syllabus_year || "2024/2025";
              const programName = tmpl?.program_name || "Degree Program";
              const isLocked = cohort.is_locked;
              const isToggling = togglingCohortId === cohort.id;
              const isDeleting = deletingCohortId === cohort.id;
              const isCopied = copiedCode === cohort.cohort_code;
              const studentCount = roster.filter((s) => s.cohort_id === cohort.id).length;

              return (
                <div
                  key={cohort.id}
                  className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 p-4 rounded-xl border border-gray-200 bg-gray-50/50 hover:bg-gray-50 transition-colors"
                >
                  {/* Cohort Meta */}
                  <div className="space-y-1.5 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="font-semibold text-gray-900 text-sm tracking-tight">
                        {cohort.cohort_name}
                      </h4>
                      <span className="inline-flex items-center px-2 py-0.5 rounded bg-blue-100/70 text-blue-800 text-[11px] font-mono font-semibold">
                        {programCode}
                      </span>
                      <span className="inline-flex items-center px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 text-[11px] font-mono">
                        {syllabusYear}
                      </span>
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px] font-mono font-medium">
                        <Users className="w-3 h-3 text-slate-500" />
                        {studentCount} {studentCount === 1 ? "student" : "students"}
                      </span>
                      {isLocked ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-50 text-rose-700 text-[11px] font-mono font-semibold border border-rose-200">
                          <Lock className="w-3 h-3" />
                          LOCKED
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[11px] font-mono font-semibold border border-emerald-200">
                          <Unlock className="w-3 h-3" />
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-500">
                      {programName} • Linked to institutional degree blueprint
                    </p>
                  </div>

                  {/* Cohort Code Display, Lock Switch & Delete Action */}
                  <div className="flex flex-col sm:flex-row sm:items-center gap-4 shrink-0">
                    {/* Code Display */}
                    <div className="flex items-center gap-2">
                      <div className="bg-white border border-gray-300 px-3.5 py-1.5 rounded-lg flex items-center gap-2 shadow-xs">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-wider">
                          Code:
                        </span>
                        <span className="font-mono text-xl font-bold tracking-wider text-blue-950">
                          {cohort.cohort_code}
                        </span>
                      </div>
                      <button
                        onClick={() => handleCopyCohortCode(cohort.cohort_code)}
                        type="button"
                        className={`inline-flex items-center justify-center p-2 rounded-lg text-xs font-semibold transition-colors cursor-pointer shadow-xs ${
                          isCopied
                            ? "bg-emerald-700 text-white hover:bg-emerald-800"
                            : "bg-blue-900 hover:bg-blue-800 text-white"
                        }`}
                        title="Copy Cohort Code"
                      >
                        {isCopied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                      </button>
                    </div>

                    {/* Lock Toggle */}
                    <div className="flex items-center gap-3 bg-white border border-gray-200 rounded-lg px-3 py-1.5">
                      <div className="text-right">
                        <span className="text-xs font-medium text-gray-700 block">
                          {isLocked ? "Registration Locked" : "Registration Open"}
                        </span>
                        <span className="text-[10px] text-gray-400 block">
                          {isLocked ? "Reject sign-ups" : "Accept sign-ups"}
                        </span>
                      </div>
                      <Switch
                        id={`cohort-lock-${cohort.id}`}
                        checked={isLocked}
                        disabled={isToggling}
                        onCheckedChange={() => handleToggleCohortLock(cohort.id, isLocked)}
                        className="data-[state=checked]:bg-rose-600 cursor-pointer"
                      />
                    </div>

                    {/* Delete Action Button */}
                    <button
                      onClick={() => handleDeleteCohort(cohort.id, studentCount)}
                      disabled={isDeleting}
                      type="button"
                      className="inline-flex items-center justify-center p-2 rounded-lg text-rose-500 hover:text-rose-700 hover:bg-rose-50 border border-gray-200 bg-white hover:border-rose-200 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shadow-xs"
                      title={studentCount > 0 ? "Cannot delete: Cohort has assigned students" : "Delete Cohort"}
                    >
                      {isDeleting ? (
                        <Loader2 className="w-4 h-4 animate-spin text-rose-600" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 2. POLISHED METRICS GRID */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <MetricCard
          title="Average Credits"
          value={averageCredits}
          icon={Users}
          description="Average earned credits"
          indicator="bg-blue-50 text-blue-900 border-blue-200"
          iconColor="text-blue-900"
        />
        <MetricCard
          title="Cohort CGPA"
          value={averageCgpa.toFixed(2)}
          icon={Percent}
          description="Average cumulative score"
          indicator="bg-emerald-50 text-emerald-800 border-emerald-200"
          iconColor="text-emerald-700"
        />
        <MetricCard
          title="Pending Audits"
          value={pendingAudits}
          icon={ClipboardCheck}
          description="Awaiting advisor sign-off"
          indicator="bg-indigo-50 text-indigo-900 border-indigo-200"
          iconColor="text-indigo-900"
        />
        <MetricCard
          title="At-Risk Alerts"
          value={atRiskStudents.length}
          icon={AlertTriangle}
          description="CGPA below 2.50 threshold"
          indicator={
            atRiskStudents.length > 0
              ? "bg-rose-50 text-rose-800 border-rose-200"
              : "bg-gray-50 text-gray-700 border-gray-200"
          }
          iconColor={atRiskStudents.length > 0 ? "text-rose-700" : "text-gray-400"}
        />
      </div>

      {/* 3. FUNCTIONAL ACTION PANELS: CURRICULUM MANAGEMENT */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 tracking-tight flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-blue-900" />
            <span>Curriculum Management &amp; Tools</span>
          </h3>
          <p className="text-sm text-gray-600 leading-relaxed mt-1">
            Operational resources for syllabus structuring, matrix uploads, and external advising petitions.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Action 1: Download Template (Secondary / Outline) */}
          <div className="bg-gray-50/60 border border-gray-200 rounded-xl p-6 flex flex-col justify-between hover:border-gray-300 transition-colors">
            <div className="space-y-2">
              <div className="w-9 h-9 rounded-lg bg-white border border-gray-200 text-blue-900 flex items-center justify-center shadow-xs">
                <FileSpreadsheet className="w-4 h-4" />
              </div>
              <h4 className="text-sm font-semibold text-gray-900">Download Template</h4>
              <p className="text-sm text-gray-600 leading-relaxed">
                Standard CSV/Excel course structure matrix template with pre-formatted columns for credits and prerequisites.
              </p>
            </div>
            <button
              onClick={handleDownloadTemplate}
              className="mt-6 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white border border-gray-300 text-xs font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors shadow-xs cursor-pointer"
            >
              <Download className="w-3.5 h-3.5 text-gray-500" />
              <span>Download CSV Template</span>
            </button>
          </div>

          {/* Action 2: Upload Course Structure (PRIMARY CHRONOLOGICAL ACTION) */}
          <div className="bg-blue-50/30 border-2 border-blue-200 rounded-xl p-6 flex flex-col justify-between hover:border-blue-300 transition-all shadow-xs relative">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-9 h-9 rounded-lg bg-blue-900 text-white flex items-center justify-center shadow-xs">
                  <Upload className="w-4 h-4" />
                </div>
                <span className="text-[10px] uppercase font-mono font-bold tracking-wider px-2 py-0.5 rounded-md bg-blue-100 text-blue-900 border border-blue-200">
                  Step 1 Action
                </span>
              </div>
              <h4 className="text-sm font-bold text-gray-900">Upload Course Structure</h4>
              <p className="text-sm text-gray-600 leading-relaxed">
                Import and ingest an updated curriculum syllabus matrix to sync prerequisite rules with the degree audit engine.
              </p>
            </div>
            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="mt-6 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-blue-900 text-xs font-bold text-white hover:bg-blue-800 shadow-md hover:shadow-lg transition-all cursor-pointer"
            >
              <FileUp className="w-3.5 h-3.5" />
              <span>Upload Syllabus Matrix</span>
            </button>
          </div>

          {/* Action 3: UAT feedback form — shown only when PRODUCT.feedbackFormUrl is set */}
          {PRODUCT.feedbackFormUrl && (
          <div className="bg-gray-50/60 border border-gray-200 rounded-xl p-6 flex flex-col justify-between hover:border-gray-300 transition-colors">
            <div className="space-y-2">
              <div className="w-9 h-9 rounded-lg bg-white border border-gray-200 text-emerald-700 flex items-center justify-center shadow-xs">
                <ExternalLink className="w-4 h-4" />
              </div>
              <h4 className="text-sm font-semibold text-gray-900">Feedback Form</h4>
              <p className="text-sm text-gray-600 leading-relaxed">
                Tell us what works and what does not. Share this form with your students too.
              </p>
            </div>
            <a
              href={PRODUCT.feedbackFormUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-6 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-white border border-gray-300 text-xs font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors shadow-xs cursor-pointer"
            >
              <ExternalLink className="w-3.5 h-3.5 text-gray-400" />
              <span>Open Feedback Form</span>
            </a>
          </div>
          )}
        </div>
      </div>

      {/* 4. ADVISEE ROSTER & URGENT ACADEMIC INTERVENTION TABLE */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="p-6 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
              <h3 className="text-lg font-semibold tracking-tight text-gray-900">
                Academic Intervention &amp; Advisee Roster
              </h3>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              Real-time monitoring of enrolled cohort students, CGPA progression, and intervention alerts.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-xs font-mono text-gray-600 bg-gray-50 px-2.5 py-1 rounded-md border border-gray-200">
              Total Advisees: {totalStudents}
            </span>
            {atRiskStudents.length > 0 ? (
              <span className="text-xs font-medium px-2.5 py-1 rounded-md bg-rose-50 text-rose-700 border border-rose-200">
                {atRiskStudents.length} At-Risk
              </span>
            ) : (
              <span className="text-xs font-medium px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
                All Good Standing
              </span>
            )}
          </div>
        </div>

        {totalStudents === 0 ? (
          /* 5. PREMIUM EMPTY STATE */
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <Users className="w-12 h-12 text-gray-300 mb-3" />
            <h4 className="text-lg font-medium text-gray-900">No advisees enrolled yet</h4>
            <p className="text-sm text-gray-500 max-w-sm mt-1 leading-relaxed">
              Provide your Lecturer Session Code to your cohort to begin tracking their progress.
            </p>
          </div>
        ) : (
          /* 4. THE ADVISEE TABLE (HOVER STATES & GEOMETRY) */
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-50/50 border-b border-gray-200">
                  <th className="py-3 px-6">Risk Tier</th>
                  <th className="py-3 px-6">Student Name</th>
                  <th className="py-3 px-6">Matric No</th>
                  <th className="py-3 px-6">Program</th>
                  <th className="py-3 px-6">Cumulative GPA</th>
                  <th className="py-3 px-6">Earned Credits</th>
                  <th className="py-3 px-6">Academic Status</th>
                  <th className="py-3 px-6 text-right">Audit Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {sortedRoster.map((student) => {
                  const isRed = student.traffic_light === "RED";
                  return (
                    <tr
                      key={student.matric_no}
                      onClick={() => handleInspectStudent(student)}
                      className={`hover:bg-gray-50 transition-colors duration-200 ease-in-out cursor-pointer ${
                        isRed ? "bg-rose-50/30 hover:bg-rose-50/60" : ""
                      }`}
                    >
                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-black border ${
                            isRed
                              ? "bg-rose-100 text-rose-800 border-rose-300"
                              : "bg-emerald-100 text-emerald-800 border-emerald-300"
                          }`}
                        >
                          <span
                            className={`w-2 h-2 rounded-full ${
                              isRed ? "bg-rose-600 animate-pulse" : "bg-emerald-600"
                            }`}
                          />
                          <span>{isRed ? "RED ALERT" : "GREEN"}</span>
                        </span>
                      </td>
                      <td className="py-4 px-6 text-sm font-semibold text-gray-900">
                        {student.name || "Student"}
                      </td>
                      <td className="py-4 px-6 text-sm font-mono text-gray-600">
                        {student.matric_no}
                      </td>
                      <td className="py-4 px-6 text-sm text-gray-600">
                        {student.program || "Unassigned"}
                      </td>
                      <td className="py-4 px-6 text-sm font-mono font-bold text-gray-900">
                        {Number(student.cgpa || 0).toFixed(2)}
                      </td>
                      <td className="py-4 px-6 text-sm font-mono text-gray-700">
                        {student.total_earned_credits} / 130
                      </td>
                      <td className="py-4 px-6 text-sm">
                        {isRed ? (
                          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
                            Unmet Prerequisite
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Good Standing
                          </span>
                        )}
                      </td>
                      <td className="py-4 px-6 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleInspectStudent(student);
                          }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold shadow-xs transition-colors cursor-pointer ${
                            isRed
                              ? "bg-rose-600 hover:bg-rose-700 text-white"
                              : "bg-gray-100 hover:bg-gray-200 text-gray-700 border border-gray-300"
                          }`}
                        >
                          Inspect Audit
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Student Audit Inspection Modal */}
      {activeStudent && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50 overflow-y-auto">
          <div className="bg-white rounded-3xl max-w-4xl w-full my-8 p-6 sm:p-8 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto space-y-6">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div
                  className={`p-3 rounded-2xl ${
                    activeStudent.traffic_light === "RED"
                      ? "bg-rose-100 text-rose-700"
                      : "bg-emerald-100 text-emerald-700"
                  }`}
                >
                  <GraduationCap className="w-7 h-7" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-black text-slate-900">{activeStudent.name}</h2>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-black ${
                        activeStudent.traffic_light === "RED"
                          ? "bg-rose-600 text-white"
                          : "bg-emerald-600 text-white"
                      }`}
                    >
                      {activeStudent.traffic_light} STATUS
                    </span>
                  </div>
                  <p className="font-mono text-xs text-slate-500 mt-0.5">
                    Matric: {activeStudent.matric_no} | Standing: {activeStudent.academic_status}
                  </p>
                </div>
              </div>

              <button
                onClick={() => setActiveStudent(null)}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Prerequisite Matrix & Traffic Light Grid */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-1.5">
                  <BookOpen className="w-4 h-4 text-blue-900" />
                  <span>Transcript Course Prerequisite Matrix</span>
                </h3>
              </div>

              <TrafficLightGrid
                records={activeStudent.records || []}
                canOverride={false}
              />
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end pt-4 border-t border-slate-100">
              <button
                onClick={() => setActiveStudent(null)}
                className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-black text-white font-bold text-xs shadow-md transition-all cursor-pointer"
              >
                Close Audit Inspection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. RECENT ENROLLMENTS SURVEILLANCE PANEL (Loose Admission Safety Net) */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="p-6 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-amber-600" />
              <h3 className="text-lg font-semibold tracking-tight text-gray-900">
                Recent Enrollments
              </h3>
              <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 text-[11px] font-mono border border-amber-200">
                Safety Net
              </span>
            </div>
            <p className="text-sm text-gray-600 leading-relaxed">
              Review self-registered students.
            </p>
          </div>
          <span className="text-xs font-mono text-gray-600 bg-gray-50 px-2.5 py-1 rounded-md border border-gray-200 shrink-0">
            {recentEnrollments.length} {recentEnrollments.length === 1 ? 'enrollment' : 'enrollments'}
          </span>
        </div>

        {recentEnrollments.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-10 text-center">
            <ShieldCheck className="w-10 h-10 text-emerald-300 mb-3" />
            <p className="text-sm font-medium text-gray-500">No enrollments to review.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-50/50 border-b border-gray-200">
                  <th className="py-3 px-6">Student Name</th>
                  <th className="py-3 px-6">Matric No</th>
                  <th className="py-3 px-6">Institutional Email</th>
                  <th className="py-3 px-6">Registered At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {recentEnrollments.map((enrollment) => {
                  const registeredAt = enrollment.created_at
                    ? `Joined: ${new Date(enrollment.created_at).toLocaleDateString('en-MY', {
                        dateStyle: 'medium'
                      })}`
                    : '—';

                  return (
                    <tr
                      key={enrollment.matric_no}
                      className="hover:bg-rose-50/30 transition-colors duration-150"
                    >
                      <td className="py-3.5 px-6 text-sm font-medium text-gray-900">
                        {enrollment.name || '—'}
                      </td>
                      <td className="py-3.5 px-6 text-sm font-mono text-gray-700">
                        {enrollment.matric_no}
                      </td>
                      <td className="py-3.5 px-6 text-sm text-gray-500">
                        {enrollment.institutional_email || '—'}
                      </td>
                      <td className="py-3.5 px-6 text-xs text-gray-500 font-mono">
                        {registeredAt}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 6. UPLOAD COURSE STRUCTURE MODAL */}
      {isUploadModalOpen && (
        <div className="fixed inset-0 bg-gray-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-6">
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm w-full max-w-lg overflow-hidden animate-in fade-in-50 zoom-in-95 duration-150">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50/50">
              <div className="flex items-center space-x-2">
                <FileUp className="w-5 h-5 text-blue-900" />
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">Upload Course Structure Matrix</h3>
                  <p className="text-[11px] text-gray-500 font-medium">{resolveUniName(tenantId)}</p>
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setIsUploadModalOpen(false)}
                  className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <details className="rounded-lg border border-blue-100 bg-blue-50/50 px-4 py-3 text-xs text-gray-700">
                <summary className="cursor-pointer font-semibold text-blue-900">How to fill the CSV (read before uploading)</summary>
                <div className="mt-3 space-y-2 leading-relaxed">
                  <p>Download the template, keep the header row, replace the example rows with your programme. One row = one requirement. Columns: <b>course_code, course_name, credits, category, prerequisites</b>.</p>
                  <ul className="list-disc pl-5 space-y-1">
                    <li><b>Core / fixed course:</b> the exact code, e.g. <code>ABC1013</code>.</li>
                    <li><b>Choose one from a list:</b> codes joined by <code>/</code>, e.g. <code>ABC3103/ABC3113</code>. Need 2 picks? Add the same row twice.</li>
                    <li><b>Any course matching a pattern:</b> use <code>XX</code> (2 or more X) for unknown characters, e.g. <code>ABC5XX3</code> = any code starting ABC5 ending 3.</li>
                    <li><b>Category:</b> required, your own words (Core, University, Program Elective, Free Elective…). Progress bars are grouped by it.</li>
                    <li><b>Prerequisites:</b> <code>None</code>, <code>ABC1013</code>, <code>ABC1013 AND ABC1023</code>, <code>ABC1013 OR ABC1023</code>, or with credits <code>"ABC2013, min_credits: 80"</code> (keep the quotes in CSV).</li>
                    <li><b>Total credits</b> below must equal the sum of the credits column — SynGrad warns if they differ.</li>
                  </ul>
                  <p>Mistakes can be fixed later in <b>Curriculum</b> without re-uploading.</p>
                </div>
              </details>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Degree Template Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={templateName}
                    onChange={(e) => setTemplateName(e.target.value)}
                    placeholder="e.g. Software Engineering 2024/2025"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                  />
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Program Code <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={programCode}
                      onChange={(e) => setProgramCode(e.target.value.toUpperCase())}
                      placeholder="e.g. SECJ"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm uppercase"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Syllabus Year <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={syllabusYear}
                      onChange={(e) => setSyllabusYear(e.target.value)}
                      placeholder="e.g. 2024/2025"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Total Credits <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      inputMode="numeric"
                      required
                      value={totalCredits}
                      onChange={(e) => setTotalCredits(e.target.value.replace(/\D/g, "").replace(/^0+/, ""))}
                      placeholder="e.g. 130"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm"
                    />
                  </div>
                </div>
              </div>

              <div className="border-2 border-dashed border-gray-200 hover:border-blue-300 rounded-xl p-6 text-center bg-gray-50/50 transition-colors">
                <input
                  type="file"
                  id="curriculum-upload-input"
                  accept=".csv, .xlsx, .json"
                  onChange={handleFileChange}
                  className="hidden"
                />
                <label
                  htmlFor="curriculum-upload-input"
                  className="cursor-pointer flex flex-col items-center space-y-2"
                >
                  <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-900 flex items-center justify-center border border-blue-100">
                    <Upload className="w-5 h-5" />
                  </div>
                  <span className="text-xs font-semibold text-blue-900 hover:underline">
                    {selectedFile ? selectedFile.name : "Click to select or drag and drop file"}
                  </span>
                  <span className="text-[10px] text-gray-400">CSV, XLSX up to 5MB</span>
                </label>
              </div>

              {uploadStatus === "uploading" && (
                <div className="flex items-center space-x-2 p-3 rounded-lg bg-blue-50 text-blue-900 text-xs border border-blue-200">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{uploadMessage}</span>
                </div>
              )}

              {uploadStatus === "success" && (
                <div className="space-y-1.5 p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs">
                  <div className="flex items-center space-x-2 font-semibold text-emerald-800">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                    <span>Curriculum Ingested Successfully</span>
                  </div>
                  <p className="text-[11px] text-emerald-700 leading-relaxed font-medium">
                    {uploadMessage}
                  </p>
                </div>
              )}

              {uploadStatus === "error" && (
                <div className="space-y-1.5 p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 text-xs">
                  <div className="flex items-center space-x-2 font-semibold text-rose-800">
                    <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                    <span>Upload Failed</span>
                  </div>
                  <p className="text-[11px] text-rose-700 leading-relaxed font-medium">
                    {uploadMessage}
                  </p>
                </div>
              )}

              <div className="flex items-center justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsUploadModalOpen(false)}
                  className="px-4 py-2.5 rounded-lg border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleUploadSubmit}
                  className="px-4 py-2.5 rounded-lg bg-blue-900 text-xs font-semibold text-white hover:bg-blue-800 shadow-sm transition-colors"
                >
                  Confirm &amp; Ingest
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 7. CREATE COHORT MODAL */}
      {isCreateCohortOpen && (
        <div className="fixed inset-0 bg-gray-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
          <div className="bg-white border border-gray-200 rounded-2xl shadow-xl w-full max-w-lg overflow-hidden animate-in fade-in-50 zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50/70">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-900 text-white flex items-center justify-center shadow-xs">
                  <KeyRound className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-gray-900">
                    {createdCohortResult ? "Cohort Ready!" : "Create Advisee Cohort"}
                  </h3>
                  <p className="text-[11px] text-gray-500">
                    {createdCohortResult ? "Invite code generated" : "Link cohort to institutional degree blueprint"}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsCreateCohortOpen(false);
                  setCreatedCohortResult(null);
                }}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {createdCohortResult ? (
              /* Success / Copy Code Screen */
              <div className="p-6 space-y-6">
                <div className="text-center space-y-2">
                  <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mx-auto">
                    <CheckCircle2 className="w-6 h-6" />
                  </div>
                  <h4 className="text-base font-bold text-gray-900">
                    Cohort Created Successfully
                  </h4>
                  <p className="text-xs text-gray-600 max-w-xs mx-auto">
                    "{createdCohortResult.cohort_name}" is now active in your dashboard.
                  </p>
                </div>

                {/* Prominent 6-Character Code Display */}
                <div className="bg-gradient-to-br from-blue-50/80 to-indigo-50/80 border border-blue-200 rounded-xl p-5 text-center space-y-3">
                  <span className="text-[10px] font-mono text-blue-900 uppercase font-semibold tracking-wider block">
                    Student Registration Code
                  </span>
                  <div className="font-mono text-3xl font-extrabold tracking-widest text-blue-950">
                    {createdCohortResult.cohort_code}
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCopyNewCohortCode(createdCohortResult.cohort_code)}
                    className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold shadow-xs transition-colors cursor-pointer mx-auto ${
                      copiedNewCode
                        ? "bg-emerald-700 text-white hover:bg-emerald-800"
                        : "bg-blue-900 hover:bg-blue-800 text-white"
                    }`}
                  >
                    {copiedNewCode ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                    <span>{copiedNewCode ? "Code Copied to Clipboard!" : "Copy Cohort Code"}</span>
                  </button>
                </div>

                <div className="bg-amber-50/80 border border-amber-200 rounded-lg p-3 text-xs text-amber-900 flex items-start space-x-2">
                  <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <p className="text-[11px] text-amber-800 leading-relaxed">
                    Distribute this 6-character code to your incoming students. Entering this code during registration will automatically bind them to your advisee roster with the selected degree blueprint.
                  </p>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreateCohortOpen(false);
                      setCreatedCohortResult(null);
                    }}
                    className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-blue-900 hover:bg-blue-800 text-white text-xs font-semibold shadow-sm transition-colors cursor-pointer"
                  >
                    Done &amp; View Cohort
                  </button>
                </div>
              </div>
            ) : (
              /* Creation Form */
              <form onSubmit={handleCreateCohort} className="p-6 space-y-5">
                {/* 1. Degree Template Selection */}
                <div className="space-y-1.5">
                  <label htmlFor="degree-template-select" className="text-xs font-semibold text-gray-800 flex items-center justify-between">
                    <span>Degree Template Blueprint *</span>
                    <span className="text-[10px] text-gray-400 font-normal">Institutional</span>
                  </label>
                  <select
                    id="degree-template-select"
                    value={selectedTemplateId}
                    onChange={(e) => handleTemplateChange(e.target.value)}
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl border border-gray-300 text-xs text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition-colors cursor-pointer"
                  >
                    {degreeTemplates.length === 0 ? (
                      <option value="">Loading templates...</option>
                    ) : (
                      degreeTemplates.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.university_name} — {t.program_code} ({t.program_name}, {t.syllabus_year})
                        </option>
                      ))
                    )}
                  </select>
                  <p className="text-[11px] text-gray-500">
                    Defines the core curriculum, required credits, and prerequisites for this intake.
                  </p>
                </div>

                {/* 2. Cohort Name Input */}
                <div className="space-y-1.5">
                  <label htmlFor="cohort-name-input" className="text-xs font-semibold text-gray-800 block">
                    Cohort Name *
                  </label>
                  <input
                    type="text"
                    id="cohort-name-input"
                    value={cohortName}
                    onChange={(e) => setCohortName(e.target.value)}
                    placeholder="e.g., SECJ 2024/2025"
                    required
                    className="w-full px-3.5 py-2.5 rounded-xl border border-gray-300 text-xs text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 transition-colors"
                  />
                  <p className="text-[11px] text-gray-500">
                    Human-readable label shown on student dashboards and reports.
                  </p>
                </div>

                {/* 3. Generated 6-Character Code Preview */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-gray-800 flex items-center justify-between">
                    <span>Generated 6-Character Cohort Code</span>
                    <button
                      type="button"
                      onClick={() => {
                        const currentTmpl = degreeTemplates.find(t => t.id === selectedTemplateId);
                        setGeneratedCode(generateCohortCode(currentTmpl?.program_code || "SECJ"));
                      }}
                      className="text-[11px] text-blue-900 hover:text-blue-700 flex items-center gap-1 cursor-pointer font-medium"
                    >
                      <RefreshCw className="w-3 h-3" />
                      <span>Re-roll Code</span>
                    </button>
                  </label>
                  <div className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-xl p-3">
                    <div className="font-mono text-xl font-bold tracking-widest text-blue-950 px-2 py-1 bg-white border border-gray-300 rounded-lg">
                      {generatedCode || "SECJ99"}
                    </div>
                    <span className="text-[11px] text-gray-500 leading-tight">
                      Random alphanumeric code assigned to advisees upon registration.
                    </span>
                  </div>
                </div>

                {/* Modal Actions */}
                <div className="flex items-center justify-end space-x-3 pt-3 border-t border-gray-100">
                  <button
                    type="button"
                    onClick={() => setIsCreateCohortOpen(false)}
                    className="px-4 py-2.5 rounded-xl border border-gray-200 text-xs font-semibold text-gray-700 hover:bg-gray-50 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isCreatingCohort || !selectedTemplateId || !cohortName.trim()}
                    className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-900 hover:bg-blue-800 text-white text-xs font-semibold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    {isCreatingCohort ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Plus className="w-4 h-4" />
                    )}
                    <span>{isCreatingCohort ? "Creating Cohort..." : "Create Cohort"}</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Reusable Metric Card Helper Component
interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  indicator: string;
  iconColor: string;
}

function MetricCard({
  title,
  value,
  icon: Icon,
  description,
  indicator,
  iconColor
}: MetricCardProps) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 flex flex-col justify-between hover:border-gray-300 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-500 uppercase tracking-wider">
          {title}
        </span>
        <div className={`p-2 rounded-lg border ${indicator}`}>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
      </div>
      <div className="mt-4">
        <div className="text-3xl font-bold text-gray-900">
          {value}
        </div>
        <p className="text-sm text-gray-600 leading-relaxed mt-1">
          {description}
        </p>
      </div>
    </div>
  );
}