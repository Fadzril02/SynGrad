import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  ArrowLeft,
  GraduationCap,
  Calendar,
  CheckSquare,
  AlertCircle,
  Save,
  Hash,
  Info,
  CheckCircle,
  CheckCircle2,
  AlertTriangle,
  BookOpen,
  Mail,
  Sliders,
  Plus,
  Trash2,
  History,
  RotateCcw,
  Edit3,
} from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle, Badge, Button, Input } from "../../components/ui";
import { db } from "../../../lib/supabase";
import { api } from "../../../lib/api";
import { useAuth } from "../../../context/AuthContext";
import { CourseLedger, CourseLedgerRecord, LedgerColumn } from "../../../components/shared/CourseLedger";
import {
  fetchGradeScale,
  findGradeDefinition,
  GradeScaleRow,
} from "../../../lib/gradeScale";

interface StudentViewProps {
  student: any;
  onBack: () => void;
}

export function StudentView({ student, onBack }: StudentViewProps) {
  const { profile } = useAuth();
  const [sessionDate, setSessionDate] = useState(() => new Date().toISOString().split("T")[0]);
  const [notes, setNotes] = useState("");
  const [actionItem, setActionItem] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [visibility, setVisibility] = useState<"shared" | "private">("shared");
  const [notifyStudent, setNotifyStudent] = useState(true);
  const [notificationStatus, setNotificationStatus] = useState<string | null>(null);
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pastLogs, setPastLogs] = useState<any[]>([]);
  const [fetchedRecords, setFetchedRecords] = useState<any[]>([]);

  // Grade scale and Credits & Exemptions state
  const [gradeScale, setGradeScale] = useState<GradeScaleRow[]>([]);
  const [entrySemester, setEntrySemester] = useState<number>(Number(student?.entry_semester || 1));
  const [blockExemptedCredits, setBlockExemptedCredits] = useState<number>(Number(student?.block_exempted_credits || 0));
  const [savedEntrySemester, setSavedEntrySemester] = useState<number>(Number(student?.entry_semester || 1));
  const [savedBlockCredits, setSavedBlockCredits] = useState<number>(Number(student?.block_exempted_credits || 0));
  const [templateCourses, setTemplateCourses] = useState<any[]>([]);
  const [selectedTemplateCourse, setSelectedTemplateCourse] = useState<string>("");
  const [selectedExemptionGrade, setSelectedExemptionGrade] = useState<"EX" | "CT">("EX");
  const [exemptionAuditHistory, setExemptionAuditHistory] = useState<any[]>([]);
  const [isExemptionsSaving, setIsExemptionsSaving] = useState<boolean>(false);
  const [exemptionsFeedback, setExemptionsFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [showAuditHistory, setShowAuditHistory] = useState<boolean>(false);

  // Degree audit progress state (SynGrad 4A & 4B)
  const [progressCategories, setProgressCategories] = useState<Array<{ category: string; required: number; earned: number }>>([]);
  const [progressRows, setProgressRows] = useState<any[]>([]);
  const [progressUnassigned, setProgressUnassigned] = useState<any[]>([]);
  const [progressWarnings, setProgressWarnings] = useState<string[]>([]);
  const [progressTotals, setProgressTotals] = useState<{ required: number; earned: number } | null>(null);
  const [progressLoading, setProgressLoading] = useState(false);
  const [progressError, setProgressError] = useState<string | null>(null);

  // 4B: Elective override state
  const [editingSlotId, setEditingSlotId] = useState<string | null>(null);
  const [selectedOverrideCourse, setSelectedOverrideCourse] = useState<string>("");
  const [overrideNote, setOverrideNote] = useState<string>("");
  const [overrideSaving, setOverrideSaving] = useState<boolean>(false);

  // Exclusion state
  const [excludingCourseCode, setExcludingCourseCode] = useState<string | null>(null);
  const [excludeNote, setExcludeNote] = useState<string>("");
  const [excludeSaving, setExcludeSaving] = useState<boolean>(false);

  const progressFetchedMatricRef = useRef<string | null>(null);
  const progressInFlightRef = useRef<boolean>(false);

  const refreshProgress = useCallback(async (force = false) => {
    if (!student?.matric_no) return;
    if (!force && (progressInFlightRef.current || progressFetchedMatricRef.current === student.matric_no)) {
      return;
    }
    progressInFlightRef.current = true;
    setProgressLoading(true);
    setProgressError(null);
    try {
      const data = await api.getProgress(student.matric_no);
      progressFetchedMatricRef.current = student.matric_no;
      setProgressCategories(data.categories || []);
      setProgressRows(data.rows || []);
      setProgressUnassigned(data.unassigned || []);
      setProgressWarnings(data.warnings || []);
      setProgressTotals(data.totals || null);
    } catch (err: any) {
      setProgressTotals(null);
      const msg = err?.response?.data?.detail || err?.message || "Could not load progress data.";
      if (err?.response?.status === 409) {
        setProgressError(`ℹ️ ${msg}`);
      } else {
        setProgressError(msg);
      }
    } finally {
      progressInFlightRef.current = false;
      setProgressLoading(false);
    }
  }, [student?.matric_no]);

  useEffect(() => {
    refreshProgress();
  }, [refreshProgress]);

  // Candidates for elective slot dropdown: passing courses not used by core rows
  const availableElectiveCandidates = useMemo(() => {
    const coreCodes = new Set(
      progressRows
        .filter((r) => !r.is_slot)
        .map((r) => (r.code || "").toUpperCase())
    );

    const map = new Map<string, { course_code: string; course_name: string; grade: string | null; credits: number }>();

    // 1. From fetchedRecords
    (fetchedRecords || []).forEach((rec: any) => {
      const code = (rec.course_code || "").trim().toUpperCase();
      if (!code || coreCodes.has(code)) return;
      const g = (rec.grade || "").trim().toUpperCase();
      const def = findGradeDefinition(g, gradeScale);
      const isPass = def ? (def.is_pass || def.counts_as_completed) : (g && !["E", "F", "TD", "U"].includes(g));
      if (isPass) {
        map.set(code, {
          course_code: code,
          course_name: rec.course_name || code,
          grade: g || null,
          credits: Number(rec.credits) || 3,
        });
      }
    });

    // 2. From progressUnassigned (guaranteed counted passing courses)
    (progressUnassigned || []).forEach((u: any) => {
      const code = (u.course_code || "").trim().toUpperCase();
      if (!code || coreCodes.has(code)) return;
      if (!map.has(code)) {
        map.set(code, {
          course_code: code,
          course_name: u.course_name || code,
          grade: u.grade || null,
          credits: Number(u.credits) || 3,
        });
      }
    });

    // 3. From progressRows slot satisfied courses
    (progressRows || []).forEach((r: any) => {
      if (r.is_slot && r.satisfied_by?.course_code) {
        const code = (r.satisfied_by.course_code || "").trim().toUpperCase();
        if (!code || coreCodes.has(code)) return;
        if (!map.has(code)) {
          map.set(code, {
            course_code: code,
            course_name: r.name || code,
            grade: r.satisfied_by.grade || null,
            credits: Number(r.credits) || 3,
          });
        }
      }
    });

    return Array.from(map.values()).sort((a, b) => a.course_code.localeCompare(b.course_code));
  }, [progressRows, fetchedRecords, gradeScale, progressUnassigned]);

  const handleSaveSlotOverride = async (templateCourseId: string) => {
    if (!student?.matric_no || !selectedOverrideCourse) return;
    setOverrideSaving(true);
    try {
      await api.setProgressOverride(student.matric_no, {
        kind: "assign",
        course_code: selectedOverrideCourse,
        template_course_id: templateCourseId,
        note: overrideNote.trim() || null,
      });
      toast.success(`Override saved: assigned ${selectedOverrideCourse}`);
      setEditingSlotId(null);
      setSelectedOverrideCourse("");
      setOverrideNote("");
      await refreshProgress(true);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to save override";
      toast.error(msg);
    } finally {
      setOverrideSaving(false);
    }
  };

  const handleResetSlotOverride = async (courseCode: string) => {
    if (!student?.matric_no || !courseCode) return;
    try {
      await api.deleteProgressOverride(student.matric_no, courseCode);
      toast.success(`Reset override for ${courseCode} back to auto`);
      await refreshProgress(true);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to reset override";
      toast.error(msg);
    }
  };

  const handleExcludeCourse = async (courseCode: string) => {
    if (!student?.matric_no || !courseCode) return;
    setExcludeSaving(true);
    try {
      await api.setProgressOverride(student.matric_no, {
        kind: "exclude",
        course_code: courseCode,
        note: excludeNote.trim() || null,
      });
      toast.success(`Excluded course ${courseCode}`);
      setExcludingCourseCode(null);
      setExcludeNote("");
      await refreshProgress(true);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to exclude course";
      toast.error(msg);
    } finally {
      setExcludeSaving(false);
    }
  };

  const handleIncludeCourse = async (courseCode: string) => {
    if (!student?.matric_no || !courseCode) return;
    try {
      await api.deleteProgressOverride(student.matric_no, courseCode);
      toast.success(`Included ${courseCode} back into requirements`);
      await refreshProgress(true);
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to include course";
      toast.error(msg);
    }
  };

  // Diagnostic Hook: Robust try/catch blocks with explicit MODAL_CRASH_DUMP logs
  // Placed unconditionally before any early returns to strictly follow the Rules of Hooks
  useEffect(() => {
    let isMounted = true;

    const fetchModalData = async () => {
      try {
        if (!student?.matric_no) {
          if (student) {
            console.error("MODAL_CRASH_DUMP: Student object is missing matric_no identifier:", student);
          }
          return;
        }

        // 1. Fetch Advising Logs
        try {
          const { data: logsData, error: logsError } = await db
            .from("advising_logs")
            .select("*")
            .eq("student_matric_no", student.matric_no)
            .order("session_date", { ascending: false });

          if (logsError) {
            console.error("MODAL_CRASH_DUMP: Error fetching advising_logs table:", logsError);
          } else if (logsData && isMounted) {
            setPastLogs(logsData);
          }
        } catch (logsCatchErr) {
          console.error("MODAL_CRASH_DUMP: Exception during advising_logs query:", logsCatchErr);
        }

        // 2. Fetch Academic Records
        try {
          const { data: recData, error: recError } = await db
            .from("academic_records")
            .select("*")
            .eq("matric_no", student.matric_no)
            .order("semester", { ascending: true });

          if (recError) {
            console.error("MODAL_CRASH_DUMP: Error fetching academic_records table:", recError);
          } else if (recData && isMounted) {
            setFetchedRecords(recData);
          }
        } catch (recCatchErr) {
          console.error("MODAL_CRASH_DUMP: Exception during academic_records query:", recCatchErr);
        }

        // 3. Fetch Tenant Grade Scale
        fetchGradeScale().then((scale) => {
          if (isMounted && scale.length > 0) setGradeScale(scale);
        });

        // 4. Fetch Student Progression & Exemption Configuration
        try {
          const { data: stuProgData } = await db
            .from("students")
            .select("entry_semester, block_exempted_credits, cohort_id")
            .eq("matric_no", student.matric_no)
            .maybeSingle();

          if (stuProgData && isMounted) {
            const es = Number(stuProgData.entry_semester || 1);
            const bec = Number(stuProgData.block_exempted_credits || 0);
            setEntrySemester(es);
            setSavedEntrySemester(es);
            setBlockExemptedCredits(bec);
            setSavedBlockCredits(bec);

            // Fetch template courses for the student's cohort
            const cohortId = stuProgData.cohort_id || student.cohort_id;
            if (cohortId) {
              const { data: cohortRow } = await db
                .from("cohorts")
                .select("template_id")
                .eq("id", cohortId)
                .maybeSingle();

              const tmplId = cohortRow?.template_id;
              if (tmplId) {
                const { data: tc } = await db
                  .from("template_courses")
                  .select("course_code, course_name, credit_hour")
                  .eq("template_id", tmplId)
                  .order("course_code", { ascending: true });

                if (tc && tc.length > 0 && isMounted) {
                  setTemplateCourses(tc);
                  setSelectedTemplateCourse(tc[0].course_code);
                } else {
                  const { data: dtc } = await db
                    .from("degree_template_courses")
                    .select("course_code, course_name, credit_hour")
                    .eq("template_id", tmplId)
                    .order("course_code", { ascending: true });
                  if (dtc && isMounted) {
                    setTemplateCourses(dtc);
                    if (dtc.length > 0) setSelectedTemplateCourse(dtc[0].course_code);
                  }
                }
              }
            }
          }
        } catch (progErr) {
          console.warn("[StudentView] Exception during student progression query:", progErr);
        }

        // 5. Fetch Exemption Audit History
        try {
          const { data: audits } = await db
            .from("exemption_audit")
            .select("*")
            .eq("matric_no", student.matric_no)
            .order("created_at", { ascending: false });

          if (audits && isMounted) {
            setExemptionAuditHistory(audits);
          }
        } catch (auditErr) {
          console.warn("[StudentView] Exception during exemption_audit query:", auditErr);
        }
      } catch (fatalError) {
        console.error("MODAL_CRASH_DUMP: Fatal error in modal data fetch:", fatalError);
      }
    };

    fetchModalData();

    return () => {
      isMounted = false;
    };
  }, [student?.matric_no]);

  // Handlers for Credits & Exemptions card
  const handleSaveProgression = async () => {
    if (entrySemester < 1 || entrySemester > 8) {
      setExemptionsFeedback({ type: "error", message: "Entry semester must be between 1 and 8." });
      return;
    }
    if (blockExemptedCredits < 0 || blockExemptedCredits > 200) {
      setExemptionsFeedback({ type: "error", message: "Block exempted credits must be between 0 and 200." });
      return;
    }

    setIsExemptionsSaving(true);
    setExemptionsFeedback(null);
    try {
      const res = await api.patchStudentExemptions(student.matric_no, {
        entry_semester: entrySemester,
        block_exempted_credits: blockExemptedCredits,
      });

      setSavedEntrySemester(res.entry_semester);
      setSavedBlockCredits(res.block_exempted_credits);
      setExemptionsFeedback({
        type: "success",
        message: "Entry semester and block exempted credits updated successfully.",
      });

      // Refresh audits
      const { data: audits } = await db
        .from("exemption_audit")
        .select("*")
        .eq("matric_no", student.matric_no)
        .order("created_at", { ascending: false });
      if (audits) setExemptionAuditHistory(audits);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || "Failed to update progression settings.";
      setExemptionsFeedback({ type: "error", message: msg });
    } finally {
      setIsExemptionsSaving(false);
    }
  };

  const handleAddExemptionCourse = async () => {
    if (!selectedTemplateCourse) return;
    const cleanCode = selectedTemplateCourse.replace(/\s+/g, "").toUpperCase();
    const courseObj = templateCourses.find(
      (c) => c.course_code.replace(/\s+/g, "").toUpperCase() === cleanCode
    );

    setIsExemptionsSaving(true);
    setExemptionsFeedback(null);
    try {
      await api.patchStudentExemptions(student.matric_no, {
        course_actions: [
          {
            action: "add",
            course_code: cleanCode,
            grade: selectedExemptionGrade,
            credits: Number(courseObj?.credit_hour || 3),
            course_name: courseObj?.course_name || cleanCode,
          },
        ],
      });

      setExemptionsFeedback({
        type: "success",
        message: `Course exemption for ${cleanCode} (${selectedExemptionGrade}) recorded.`,
      });

      // Refetch academic records to refresh course ledger & exemption list
      const { data: recData } = await db
        .from("academic_records")
        .select("*")
        .eq("matric_no", student.matric_no)
        .order("semester", { ascending: true });
      if (recData) setFetchedRecords(recData);

      // Refetch audits
      const { data: audits } = await db
        .from("exemption_audit")
        .select("*")
        .eq("matric_no", student.matric_no)
        .order("created_at", { ascending: false });
      if (audits) setExemptionAuditHistory(audits);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || "Failed to add course exemption.";
      setExemptionsFeedback({ type: "error", message: msg });
    } finally {
      setIsExemptionsSaving(false);
    }
  };

  const handleRemoveExemptionCourse = async (courseCode: string, grade: string) => {
    const cleanCode = courseCode.replace(/\s+/g, "").toUpperCase();
    if (!window.confirm(`Are you sure you want to remove exemption for ${cleanCode}?`)) {
      return;
    }

    setIsExemptionsSaving(true);
    setExemptionsFeedback(null);
    try {
      await api.patchStudentExemptions(student.matric_no, {
        course_actions: [
          {
            action: "remove",
            course_code: cleanCode,
            grade: grade || "EX",
          },
        ],
      });

      setExemptionsFeedback({
        type: "success",
        message: `Exemption for ${cleanCode} removed.`,
      });

      // Refetch academic records
      const { data: recData } = await db
        .from("academic_records")
        .select("*")
        .eq("matric_no", student.matric_no)
        .order("semester", { ascending: true });
      if (recData) setFetchedRecords(recData);

      // Refetch audits
      const { data: audits } = await db
        .from("exemption_audit")
        .select("*")
        .eq("matric_no", student.matric_no)
        .order("created_at", { ascending: false });
      if (audits) setExemptionAuditHistory(audits);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || "Failed to remove course exemption.";
      setExemptionsFeedback({ type: "error", message: msg });
    } finally {
      setIsExemptionsSaving(false);
    }
  };


  // Guard against null/undefined student prop rendering blankly (safely called AFTER all hooks)
  if (!student) {
    console.error("MODAL_CRASH_DUMP: StudentView rendered with missing/null student prop:", student);
    return (
      <div className="p-8 text-center text-rose-600 bg-rose-50 rounded-xl border border-rose-200">
        <p className="font-bold">Error loading student profile.</p>
        <button onClick={onBack} className="mt-3 text-xs underline text-blue-900 cursor-pointer">
          Return to Advisee List
        </button>
      </div>
    );
  }

  // Extract real metrics safely passed downwards or fetched from academic_records
  const recordsSource = (fetchedRecords.length > 0 ? fetchedRecords : (student?.rawResults || student?.records || []));
  const courseResults: CourseLedgerRecord[] = (Array.isArray(recordsSource) ? recordsSource : []).filter(Boolean).map((r: any) => ({
    code: r.course_code || r.code || "",
    name: r.course_name || r.name || "Unknown Module",
    credits: Number(r.credits) || 0,
    grade: r.grade || "N/A",
    grade_point: Number(r.grade_point ?? r.pointValue) || undefined,
    semester: r.semester || r.session_semester || r.semester_id || "—",
    status: r.status || "N/A",
    prerequisite_met: r.prerequisite_met,
    missing_prerequisites: r.missing_prerequisites,
    is_ai_parsed: r.is_ai_parsed,
  }));

  // Single source of truth for totals: api.getProgress().totals (no hardcoded fallback)
  const totalRequiredCredits = progressTotals?.required ?? null;
  const currentCredits = progressTotals?.earned ?? null;
  const creditProgressPercentage =
    totalRequiredCredits && totalRequiredCredits > 0 && currentCredits !== null
      ? Math.min((currentCredits / totalRequiredCredits) * 100, 100)
      : 0;

  const handleSaveNotes = async () => {
    if (!notes.trim()) return;
    setIsSaving(true);
    setInlineError(null);
    setNotificationStatus(null);
    const advisorStaffId = (profile as any)?.staff_id;
    
    try {
      if (!student?.matric_no) {
        throw new Error("Cannot save advising log: student.matric_no is missing");
      }
      const { data, error } = await db.from("advising_logs").insert([{
        student_matric_no: student.matric_no,
        advisor_staff_id: advisorStaffId,
        session_date: sessionDate ? new Date(sessionDate).toISOString() : new Date().toISOString(),
        notes: notes.trim(),
        action_item: actionItem.trim() || null,
        follow_up_date: followUpDate || null,
        visibility: visibility,
      }]).select();

      if (error) {
        console.error("MODAL_CRASH_DUMP: Error saving advising log:", error);
        throw error;
      }
      
      if (data && data.length > 0) {
        const savedLog = data[0];
        setPastLogs([savedLog, ...pastLogs]);
        setNotes("");
        setActionItem("");
        setFollowUpDate("");

        // If shared and notifyStudent is checked, trigger email notification
        if (visibility === "shared" && notifyStudent) {
          try {
            const notifRes = await api.notifyAdvisingLog(savedLog.id);
            if (notifRes.sent) {
              setNotificationStatus("Student notified");
            } else if (notifRes.reason) {
              setNotificationStatus(`Notification skipped: ${notifRes.reason}`);
            } else {
              setNotificationStatus("Notification skipped");
            }
          } catch (notifErr: any) {
            console.error("Failed to notify student:", notifErr);
            const detailMsg = notifErr.response?.data?.detail || notifErr.message || "Failed to send email notification";
            setNotificationStatus(`Notification failed: ${detailMsg}`);
          }
        }

        setVisibility("shared");
      }
    } catch (err: any) {
      console.error("MODAL_CRASH_DUMP: Exception in handleSaveNotes:", err);
      setInlineError(err.message || "Failed to save advising log.");
    } finally {
      setIsSaving(false);
    }
  };

  // Strictly decoupled advisor column configuration
  const advisorColumns: LedgerColumn<CourseLedgerRecord>[] = [
    {
      key: "code",
      header: (
        <div className="flex items-center gap-1.5">
          <Hash size={11} /> Code
        </div>
      ),
      headerClassName: "whitespace-nowrap",
      cellClassName: "font-mono font-bold text-gray-900 whitespace-nowrap",
      render: (c) => c.code,
    },
    {
      key: "name",
      header: "Course Title",
      cellClassName: "text-gray-700 font-medium max-w-[220px] truncate",
      render: (c) => <span title={c.name}>{c.name}</span>,
    },
    {
      key: "credits",
      header: "Cr",
      headerClassName: "text-center whitespace-nowrap",
      cellClassName: "text-center font-mono text-gray-600 whitespace-nowrap",
      render: (c) => c.credits,
    },
    {
      key: "semester",
      header: (
        <div className="flex items-center justify-center gap-1.5">
          <Calendar size={11} /> Sem
        </div>
      ),
      headerClassName: "text-center whitespace-nowrap",
      cellClassName: "text-center font-mono text-gray-500 whitespace-nowrap",
      render: (c) => c.semester || "—",
    },
    {
      key: "grade_point",
      header: "GP",
      headerClassName: "text-center whitespace-nowrap",
      cellClassName: "text-center font-mono text-gray-600 whitespace-nowrap",
      render: (c) => {
        const gradeStr = String(c.grade || "").trim().toUpperCase();
        const defn = findGradeDefinition(gradeStr, gradeScale);
        if (defn && !defn.counts_in_cgpa && defn.is_pass) return <span className="text-blue-600 font-semibold">—</span>;
        if (!defn && gradeStr) return <span className="text-amber-600 font-semibold text-xs">Unknown</span>;
        const gp = defn?.points !== null && defn?.points !== undefined ? Number(defn.points) : Number(c.grade_point);
        const hasGp = !isNaN(gp);
        return (
          <span className={`font-bold ${(hasGp ? gp : 0) < 2.0 ? "text-rose-600" : "text-gray-800"}`}>
            {hasGp ? gp.toFixed(2) : "—"}
          </span>
        );
      },
    },
    {
      key: "prereq",
      header: (
        <div className="flex items-center justify-center gap-1.5">
          <Info size={11} /> Prereq
        </div>
      ),
      headerClassName: "text-center whitespace-nowrap",
      cellClassName: "text-center whitespace-nowrap",
      render: (c) => {
        if (c.prerequisite_met === false) {
          const missing = Array.isArray(c.missing_prerequisites)
            ? c.missing_prerequisites.join(", ")
            : String(c.missing_prerequisites || "");
          return (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200"
              title={missing}
            >
              <AlertTriangle size={9} /> UNMET
            </span>
          );
        }
        return <CheckCircle2 size={14} className="mx-auto text-emerald-500" />;
      },
    },
    {
      key: "ai_flag",
      header: "AI",
      headerClassName: "text-center whitespace-nowrap",
      cellClassName: "text-center whitespace-nowrap",
      render: (c) => (
        c.is_ai_parsed ? (
          <span className="text-[10px] font-bold text-amber-600 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">AI</span>
        ) : (
          <span className="text-[10px] text-gray-400">—</span>
        )
      ),
    },
    {
      key: "status",
      header: "Status",
      headerClassName: "text-right whitespace-nowrap",
      cellClassName: "text-right whitespace-nowrap",
      render: (c) => {
        const gradeStr = String(c.grade || "").trim().toUpperCase();
        const statusStr = String(c.status || "");
        const defn = findGradeDefinition(gradeStr, gradeScale);

        if (!defn && gradeStr) {
          return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-300">
              <AlertTriangle size={10} /> Unknown grade {gradeStr}
            </span>
          );
        }

        const isExempted = statusStr === "Exempted" || (defn ? (defn.is_pass && !defn.counts_in_cgpa && (gradeStr === "EX" || gradeStr === "CT")) : false);
        const isNeutral = defn ? (defn.is_pass && !defn.counts_in_cgpa) : false;
        const isPassed = defn ? defn.is_pass : ["Passed", "Pass", "Pass/Approved", "Approved"].includes(statusStr);
        const isFailed = defn ? !defn.is_pass : ["Failed", "Fail"].includes(statusStr);

        if (isExempted) {
          return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
              EXEMPT ({gradeStr || "N/A"})
            </span>
          );
        }
        if (isNeutral) {
          return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              PASSED ({gradeStr})
            </span>
          );
        }
        if (isPassed) {
          return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              PASSED ({gradeStr || "N/A"})
            </span>
          );
        }
        if (isFailed) {
          return (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
              <AlertTriangle size={10} /> FAILED ({gradeStr || "N/A"})
            </span>
          );
        }
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-gray-100 text-gray-600 border border-gray-200">
            {statusStr || "—"}
          </span>
        );
      },
    },
  ];

  return (
    <div className="space-y-6">
      {/* 🔙 TOP HEADER TRACK WITH ACTION CONTROLS */}
      <div className="flex items-center justify-between">
        <button 
          onClick={onBack} 
          className="flex items-center text-sm font-medium text-gray-500 hover:text-[#990033] transition-colors gap-2 cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" /> Return to Advisee List
        </button>
        <Badge variant={student.academic_status === 'Good Standing' ? 'success' : 'danger'} className="text-sm px-3 py-1">
          Account Status: {student.academic_status || 'Good Standing'}
        </Badge>
      </div>

      {/* 👤 CHASSIS TOP SUMMARY DETAILS SCREEN */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 bg-white border border-gray-200">
          <CardContent className="p-6 flex flex-col justify-between h-full space-y-4">
            <div>
              <span className="text-xs font-bold font-mono text-blue-900 tracking-widest uppercase">STUDENT PROFILE</span>
              <h2 className="text-2xl font-bold text-gray-900 mt-1">{student.name}</h2>
              <p className="text-sm font-mono text-gray-500 mt-0.5">Matric No: {student.matric_no || student.id}</p>
            </div>
            
            {/* Degree Credit Milestones Tracker bar code display */}
            <div className="space-y-2 pt-4 border-t border-gray-100">
              <div className="flex justify-between text-sm font-medium">
                <span className="text-gray-600">Total Program Credit Progress</span>
                {progressLoading ? (
                  <span className="text-xs text-gray-400 animate-pulse font-mono">Loading…</span>
                ) : progressError ? (
                  <span className="text-xs text-rose-600 font-semibold">{progressError}</span>
                ) : currentCredits !== null && totalRequiredCredits !== null ? (
                  <span className="text-gray-900 font-bold font-mono">
                    {currentCredits} / {totalRequiredCredits} Credits ({Math.round(creditProgressPercentage)}%)
                  </span>
                ) : (
                  <span className="text-xs text-gray-400 font-mono">—</span>
                )}
              </div>
              {progressLoading && (
                <div className="w-full bg-gray-100 h-3 rounded-full overflow-hidden animate-pulse">
                  <div className="bg-gray-300 h-full rounded-full w-1/3" />
                </div>
              )}
              {!progressLoading && !progressError && currentCredits !== null && totalRequiredCredits !== null && (
                <div className="w-full bg-gray-100 h-3 rounded-full overflow-hidden">
                  <div 
                    className="bg-emerald-500 h-full rounded-full transition-all duration-500" 
                    style={{ width: `${creditProgressPercentage}%` }}
                  />
                </div>
              )}
              <p className="text-xs text-gray-400">Completion threshold calculated against degree program blueprint.</p>
            </div>
          </CardContent>
        </Card>

        {/* Dynamic score summary blocks */}
        <Card className="bg-gradient-to-br from-slate-900 to-slate-800 text-white border-0">
          <CardContent className="p-6 flex flex-col justify-between h-full">
            <div>
              <GraduationCap className="w-8 h-8 text-[#FFCC00] mb-2" />
              <p className="text-sm text-slate-400 font-medium">Calculated Cumulative Performance</p>
              <p className="text-5xl font-black text-white mt-1 font-mono tracking-tight">{Number(student.cgpa || 0).toFixed(2)}</p>
            </div>
            <div className="pt-4 border-t border-slate-700 text-xs text-slate-400 flex items-center justify-between">
              <span>Status Standing:</span>
              <span className={`font-bold uppercase ${Number(student.cgpa || 0) < 2.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                {Number(student.cgpa || 0) < 2.5 ? 'At Risk' : 'Satisfactory'}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 🎓 CREDITS & EXEMPTIONS CARD */}
      <Card className="bg-white border border-gray-200 shadow-sm">
        <CardHeader className="pb-3 border-b border-gray-100">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-[#990033]/10 text-[#990033]">
                <Sliders size={18} />
              </div>
              <div>
                <CardTitle className="text-base font-bold text-gray-900">Credits & Exemptions</CardTitle>
                <p className="text-xs text-gray-500 mt-0.5">
                  Manage direct entry semesters, block transfer credits, and individual course exemptions.
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowAuditHistory(!showAuditHistory)}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-600 hover:text-[#990033] bg-gray-50 hover:bg-gray-100 px-3 py-1.5 rounded-md border border-gray-200 transition-colors"
            >
              <History size={13} />
              {showAuditHistory ? "Hide Change History" : "View Change History"}
              <span className="ml-1 px-1.5 py-0.2 bg-gray-200 text-gray-700 rounded-full text-[10px]">
                {exemptionAuditHistory.length}
              </span>
            </button>
          </div>
          <div className="mt-3 p-3 bg-blue-50/70 border border-blue-200 rounded-lg text-xs text-blue-900 flex items-start gap-2">
            <Info size={16} className="text-blue-700 flex-shrink-0 mt-0.5" />
            <span>For diploma/credit-transfer students. Exempted courses count toward graduation but not CGPA.</span>
          </div>
          {exemptionsFeedback && (
            <div
              className={`mt-2 p-3 rounded-lg text-xs font-medium border flex items-center justify-between ${
                exemptionsFeedback.type === "success"
                  ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                  : "bg-rose-50 text-rose-800 border-rose-200"
              }`}
            >
              <div className="flex items-center gap-2">
                {exemptionsFeedback.type === "success" ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                <span>{exemptionsFeedback.message}</span>
              </div>
              <button
                onClick={() => setExemptionsFeedback(null)}
                className="text-xs opacity-60 hover:opacity-100"
              >
                ✕
              </button>
            </div>
          )}
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Progression & Block Credit Inputs */}
            <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700">Progression & Block Credits</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Entry Semester (1–8)
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={8}
                    value={entrySemester}
                    onChange={(e) => setEntrySemester(Math.max(1, Math.min(8, parseInt(e.target.value) || 1)))}
                    className="w-full text-sm font-mono px-3 py-2 bg-white border border-gray-300 rounded-md focus:ring-2 focus:ring-[#990033] focus:border-transparent outline-none"
                  />
                  <p className="text-[11px] text-gray-500 mt-1">Starting academic semester of student</p>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Block Exempted Credits (0–200)
                  </label>
                  <input
                    type="number"
                    min={0}
                    max={200}
                    value={blockExemptedCredits}
                    onChange={(e) => setBlockExemptedCredits(Math.max(0, Math.min(200, parseInt(e.target.value) || 0)))}
                    className="w-full text-sm font-mono px-3 py-2 bg-white border border-gray-300 rounded-md focus:ring-2 focus:ring-[#990033] focus:border-transparent outline-none"
                  />
                  <p className="text-[11px] text-gray-500 mt-1">Direct lump-sum credits (e.g. diploma waiver)</p>
                </div>
              </div>
              <div className="flex justify-end pt-1">
                <Button
                  size="sm"
                  onClick={handleSaveProgression}
                  disabled={isExemptionsSaving || (entrySemester === savedEntrySemester && blockExemptedCredits === savedBlockCredits)}
                  className="gap-1.5"
                >
                  <Save size={13} />
                  {isExemptionsSaving ? "Saving..." : "Save Progression"}
                </Button>
              </div>
            </div>

            {/* Right: Add Course Exemption Form */}
            <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-4">
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700">Add Course Exemption</h4>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Template Course
                  </label>
                  <select
                    value={selectedTemplateCourse}
                    onChange={(e) => setSelectedTemplateCourse(e.target.value)}
                    className="w-full text-xs px-2.5 py-2 bg-white border border-gray-300 rounded-md focus:ring-2 focus:ring-[#990033] focus:border-transparent outline-none truncate"
                  >
                    {templateCourses.length === 0 ? (
                      <option value="">No template courses available</option>
                    ) : (
                      templateCourses.map((tc) => (
                        <option key={tc.course_code} value={tc.course_code}>
                          {tc.course_code} — {tc.course_name} ({tc.credit_hour} cr)
                        </option>
                      ))
                    )}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 mb-1">
                    Exemption Type
                  </label>
                  <select
                    value={selectedExemptionGrade}
                    onChange={(e) => setSelectedExemptionGrade(e.target.value as "EX" | "CT")}
                    className="w-full text-xs font-semibold px-2.5 py-2 bg-white border border-gray-300 rounded-md focus:ring-2 focus:ring-[#990033] focus:border-transparent outline-none"
                  >
                    <option value="EX">EX (Exemption)</option>
                    <option value="CT">CT (Credit Transfer)</option>
                  </select>
                </div>
              </div>
              <div className="flex justify-end pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleAddExemptionCourse}
                  disabled={isExemptionsSaving || !selectedTemplateCourse}
                  className="gap-1.5"
                >
                  <Plus size={13} />
                  Add Course Exemption
                </Button>
              </div>
            </div>
          </div>

          {/* List of current course exemptions */}
          <div className="border border-gray-200 rounded-lg overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-gray-700">
                Active Course Exemptions ({courseResults.filter((c) => {
                  const g = String(c.grade || "").trim().toUpperCase();
                  return g === "EX" || g === "CT" || c.status === "Exempted";
                }).length})
              </span>
              <span className="text-xs text-gray-500">
                Applied toward graduation requirements
              </span>
            </div>
            {courseResults.filter((c) => {
              const g = String(c.grade || "").trim().toUpperCase();
              return g === "EX" || g === "CT" || c.status === "Exempted";
            }).length === 0 ? (
              <div className="p-4 text-center text-xs text-gray-500">
                No individual course exemptions recorded for this student.
              </div>
            ) : (
              <div className="divide-y divide-gray-100 max-h-56 overflow-y-auto">
                {courseResults
                  .filter((c) => {
                    const g = String(c.grade || "").trim().toUpperCase();
                    return g === "EX" || g === "CT" || c.status === "Exempted";
                  })
                  .map((c, idx) => (
                    <div key={`${c.code}-${idx}`} className="px-4 py-2.5 flex items-center justify-between hover:bg-gray-50 text-xs">
                      <div className="flex items-center gap-3">
                        <span className="font-mono font-bold text-gray-900">{c.code}</span>
                        <span className="text-gray-700 font-medium">{c.name}</span>
                        <span className="text-gray-400 font-mono">({c.credits} Cr)</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                          {c.grade || "EX"}
                        </span>
                      </div>
                      <button
                        onClick={() => handleRemoveExemptionCourse(c.code, c.grade)}
                        disabled={isExemptionsSaving}
                        className="inline-flex items-center gap-1 text-xs text-rose-600 hover:text-rose-800 hover:bg-rose-50 px-2 py-1 rounded transition-colors"
                        title="Remove Exemption"
                      >
                        <Trash2 size={13} />
                        Remove
                      </button>
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* Change History Audit Drawer / Collapsible */}
          {showAuditHistory && (
            <div className="border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
              <div className="px-4 py-3 bg-gray-100 border-b border-gray-200 flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
                  <History size={13} className="text-gray-500" />
                  Exemption Change History (exemption_audit)
                </span>
                <span className="text-xs text-gray-500">
                  {exemptionAuditHistory.length} recorded events
                </span>
              </div>
              {exemptionAuditHistory.length === 0 ? (
                <div className="p-4 text-center text-xs text-gray-500">
                  No exemption audit history recorded yet.
                </div>
              ) : (
                <div className="divide-y divide-gray-200 max-h-60 overflow-y-auto">
                  {exemptionAuditHistory.map((audit) => (
                    <div key={audit.id} className="p-3 text-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 hover:bg-white transition-colors">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-gray-900">{audit.field}</span>
                          <span className="text-[11px] text-gray-400 font-mono">
                            {new Date(audit.created_at).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 font-mono text-[11px]">
                          <span className="text-rose-600 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-200">
                            {audit.old_value !== null && audit.old_value !== undefined ? String(audit.old_value) : "—"}
                          </span>
                          <span className="text-gray-400">→</span>
                          <span className="text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            {audit.new_value !== null && audit.new_value !== undefined ? String(audit.new_value) : "—"}
                          </span>
                        </div>
                      </div>
                      <div className="text-[11px] text-gray-500 font-mono">
                        By: <span className="font-bold text-gray-700">{audit.changed_by_staff_id || "Staff"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 📊 DEGREE AUDIT PROGRESS & REQUIREMENT MATCHING (SynGrad 4A) */}
      <Card className="bg-white border border-gray-200 shadow-sm">
        <CardHeader className="pb-3 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-blue-900/10 text-blue-900">
              <GraduationCap size={18} />
            </div>
            <div>
              <CardTitle className="text-base font-bold text-gray-900">Degree Requirement Progress</CardTitle>
              <p className="text-xs text-gray-500 mt-0.5">
                Automated requirement matching engine progress against degree syllabus (read-only)
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-6 space-y-6">
          {/* Skeleton while progress is loading */}
          {progressLoading && (
            <div className="space-y-6 animate-pulse">
              <div>
                <div className="h-3.5 bg-gray-200 rounded w-1/4 mb-3" />
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex justify-between">
                        <div className="h-3 bg-gray-200 rounded w-1/3" />
                        <div className="h-3 bg-gray-200 rounded w-16" />
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-2">
                        <div className="bg-gray-200 h-2 rounded-full w-1/2" />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border border-gray-200 rounded-lg overflow-hidden p-4 space-y-3">
                <div className="h-3.5 bg-gray-200 rounded w-1/4 mb-4" />
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="flex items-center gap-4 py-2 border-b border-gray-100">
                    <div className="h-4 bg-gray-200 rounded w-16" />
                    <div className="h-4 bg-gray-100 rounded flex-1" />
                    <div className="h-4 bg-gray-200 rounded w-8" />
                    <div className="h-4 bg-gray-100 rounded w-20" />
                    <div className="h-4 bg-gray-100 rounded w-24" />
                    <div className="h-4 bg-gray-200 rounded w-16" />
                  </div>
                ))}
              </div>
            </div>
          )}
          {!progressLoading && progressError && (
            <div className="flex items-start gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3">
              <Info size={14} className="shrink-0 mt-0.5" />
              <span>{progressError}</span>
            </div>
          )}

          {/* Module Classification Categories */}
          {!progressLoading && progressCategories.length > 0 && (
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-gray-700 mb-3">Module Classification</h4>
              <div className="space-y-3">
                {progressCategories.map((cat, idx) => {
                  const percent = cat.required > 0 ? Math.min(100, Math.round((cat.earned / cat.required) * 100)) : 0;
                  const color = ["bg-blue-900", "bg-blue-700", "bg-blue-500", "bg-blue-400", "bg-blue-300"][idx % 5];
                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex justify-between text-xs font-medium">
                        <span className="text-gray-700">{cat.category}</span>
                        <span className="text-gray-500 font-mono">
                          {cat.earned} / {cat.required} cr ({percent}%)
                        </span>
                      </div>
                      <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full ${color} rounded-full transition-all duration-300`}
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Template Requirement Match Table */}
          {!progressLoading && progressRows.length > 0 && (
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
                  <CheckCircle2 size={14} className="text-blue-900" />
                  Template Requirement Match
                </span>
                <span className="text-xs text-gray-500">
                  {progressRows.filter((r) => r.status === "done").length} / {progressRows.length} rows satisfied
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead className="bg-gray-50 border-b border-gray-100">
                    <tr>
                      <th className="text-left px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider">Code</th>
                      <th className="text-left px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider">Course Name</th>
                      <th className="text-center px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider">Cr</th>
                      <th className="text-left px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider">Category</th>
                      <th className="text-left px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider">Satisfied By</th>
                      <th className="text-center px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider">Status</th>
                      <th className="text-right px-4 py-2.5 font-bold text-gray-500 uppercase tracking-wider sticky right-0 bg-gray-50 z-10 shadow-[-6px_0_6px_-6px_rgba(0,0,0,0.15)]">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {progressRows.map((row, i) => (
                      <React.Fragment key={row.template_course_id || i}>
                        <tr className={row.status === 'done' ? '' : 'bg-gray-50/60'}>
                          <td className="px-4 py-2.5 font-mono font-bold text-gray-900 whitespace-nowrap">
                            {row.code}
                            {row.is_slot && (
                              <span className="ml-1.5 text-[10px] bg-blue-100 text-blue-800 font-semibold px-1.5 py-0.5 rounded">SLOT</span>
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-gray-700 max-w-[200px] truncate" title={row.name}>{row.name}</td>
                          <td className="px-4 py-2.5 text-center font-mono text-gray-600">{row.credits}</td>
                          <td className="px-4 py-2.5 text-gray-500">{row.category}</td>
                          <td className="px-4 py-2.5 font-mono text-gray-700">
                            {row.satisfied_by ? (
                              <div>
                                <div>
                                  <span className="font-bold">{row.satisfied_by.course_code}</span>
                                  {row.satisfied_by.grade && <span className="ml-1 text-gray-500">({row.satisfied_by.grade})</span>}
                                  {row.satisfied_by.semester && <span className="ml-1 text-gray-400 text-[10px]">{row.satisfied_by.semester}</span>}
                                </div>
                                {(row.source === 'override' || row.override) && (
                                  <div className="mt-0.5">
                                    <span className="inline-flex items-center gap-1 text-[10px] font-sans font-semibold bg-blue-50 text-blue-900 border border-blue-200 px-1.5 py-0.2 rounded">
                                      Set by advisor
                                    </span>
                                    {row.override?.note && (
                                      <p className="text-[10px] text-gray-500 font-sans italic mt-0.5">{row.override.note}</p>
                                    )}
                                  </div>
                                )}
                              </div>
                            ) : <span className="text-gray-300">—</span>}
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            {row.status === 'done' && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                <CheckCircle size={10} /> Done
                              </span>
                            )}
                            {row.status === 'in_progress' && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                                In Progress
                              </span>
                            )}
                            {row.status === 'missing' && (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-gray-100 text-gray-500 border border-gray-200">
                                Missing
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2.5 text-right whitespace-nowrap sticky right-0 bg-white z-10 shadow-[-6px_0_6px_-6px_rgba(0,0,0,0.15)]">
                            {row.is_slot ? (
                              <div className="flex items-center justify-end gap-1.5">
                                {(row.source === 'override' || row.override) && row.satisfied_by?.course_code && (
                                  <button
                                    onClick={() => handleResetSlotOverride(row.satisfied_by.course_code)}
                                    className="inline-flex items-center gap-1 text-[11px] font-medium text-gray-600 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 border border-gray-200 px-2 py-1 rounded transition-colors"
                                    title="Reset override to auto-matching"
                                  >
                                    <RotateCcw size={11} /> Reset to auto
                                  </button>
                                )}
                                <button
                                  onClick={() => {
                                    if (editingSlotId === row.template_course_id) {
                                      setEditingSlotId(null);
                                    } else {
                                      setEditingSlotId(row.template_course_id);
                                      setSelectedOverrideCourse(row.satisfied_by?.course_code || "");
                                      setOverrideNote(row.override?.note || "");
                                    }
                                  }}
                                  className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-900 hover:text-blue-800 bg-blue-50 hover:bg-blue-100 border border-blue-200 px-2 py-1 rounded transition-colors"
                                >
                                  <Edit3 size={11} /> Change
                                </button>
                              </div>
                            ) : (
                              <span className="text-gray-300 text-[11px]">—</span>
                            )}
                          </td>
                        </tr>

                        {row.is_slot && editingSlotId === row.template_course_id && (
                          <tr key={`edit-${row.template_course_id}`} className="bg-blue-50/60 border-b border-blue-200">
                            <td colSpan={7} className="px-4 py-3">
                              <div className="flex flex-wrap items-center gap-3">
                                <span className="text-xs font-bold text-blue-950 flex items-center gap-1">
                                  <Edit3 size={12} className="text-blue-900" />
                                  Override Slot {row.code}:
                                </span>
                                <select
                                  value={selectedOverrideCourse}
                                  onChange={(e) => setSelectedOverrideCourse(e.target.value)}
                                  className="text-xs font-mono border border-gray-300 rounded-md px-2.5 py-1.5 bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-blue-900"
                                >
                                  <option value="">-- Select passing course ({availableElectiveCandidates.length} eligible) --</option>
                                  {availableElectiveCandidates.map((c) => (
                                    <option key={c.course_code} value={c.course_code}>
                                      {c.course_code} — {c.course_name} ({c.grade || "Pass"}, {c.credits}cr)
                                    </option>
                                  ))}
                                </select>
                                <input
                                  type="text"
                                  placeholder="Advisor note (optional)..."
                                  value={overrideNote}
                                  onChange={(e) => setOverrideNote(e.target.value)}
                                  className="text-xs border border-gray-300 rounded-md px-2.5 py-1.5 bg-white text-gray-900 flex-1 min-w-[200px] focus:outline-none focus:ring-1 focus:ring-blue-900"
                                />
                                <div className="flex items-center gap-1.5">
                                  <Button
                                    size="sm"
                                    disabled={!selectedOverrideCourse || overrideSaving}
                                    onClick={() => handleSaveSlotOverride(row.template_course_id)}
                                    className="h-8 text-xs bg-blue-900 hover:bg-blue-800 text-white font-medium"
                                  >
                                    {overrideSaving ? "Saving..." : "Save"}
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={overrideSaving}
                                    onClick={() => {
                                      setEditingSlotId(null);
                                      setSelectedOverrideCourse("");
                                      setOverrideNote("");
                                    }}
                                    className="h-8 text-xs text-gray-600 hover:text-gray-900"
                                  >
                                    Cancel
                                  </Button>
                                </div>
                              </div>
                              {availableElectiveCandidates.length === 0 && (
                                <p className="text-[11px] text-amber-700 mt-1.5">
                                  No passing courses available outside core requirements to assign to this slot.
                                </p>
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Engine Warnings */}
          {progressWarnings.length > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-1">
              <div className="flex items-center gap-2 mb-1">
                <AlertTriangle size={14} className="text-amber-700" />
                <span className="text-xs font-bold text-amber-800">Progress Engine Warnings</span>
              </div>
              {progressWarnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-700 ml-5">{w}</p>
              ))}
            </div>
          )}

          {/* Unassigned Courses */}
          {progressUnassigned.length > 0 && (
            <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Info size={14} className="text-blue-700" />
                  <span className="text-xs font-bold uppercase tracking-wider text-gray-700">Courses Not Matched to Template</span>
                </div>
                <span className="text-xs text-gray-500">
                  {progressUnassigned.length} course{progressUnassigned.length === 1 ? "" : "s"}
                </span>
              </div>
              <p className="text-xs text-gray-500">
                These passing courses are recorded but do not map to any row in the student's degree template. You can exclude them from requirements or include them back.
              </p>
              <div className="flex flex-col gap-2 pt-1">
                {progressUnassigned.map((u) => {
                  const isExcluded = Boolean(u.excluded || u.override?.kind === "exclude");
                  const isPromptingExclude = excludingCourseCode === u.course_code;
                  return (
                    <div
                      key={u.course_code}
                      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-lg border text-xs transition-colors ${
                        isExcluded
                          ? "bg-amber-50/70 border-amber-200 text-amber-950"
                          : "bg-white border-gray-200 text-gray-800"
                      }`}
                    >
                      <div className="flex flex-col gap-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold">{u.course_code}</span>
                          <span className="text-gray-500">— {u.course_name}</span>
                          {u.grade && <span className="text-gray-500 font-mono">({u.grade})</span>}
                          {u.credits && <span className="text-gray-400 font-mono">{u.credits}cr</span>}
                          {isExcluded && (
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-200 text-amber-900">
                              Excluded
                            </span>
                          )}
                        </div>
                        {isExcluded && u.override?.note && (
                          <p className="text-[11px] text-amber-800 italic mt-0.5">Note: "{u.override.note}"</p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {isExcluded ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleIncludeCourse(u.course_code)}
                            className="h-7 text-xs bg-white hover:bg-emerald-50 text-emerald-800 border-emerald-300 hover:border-emerald-400 font-medium"
                          >
                            Include in Requirements
                          </Button>
                        ) : isPromptingExclude ? (
                          <div className="flex items-center gap-1.5 w-full sm:w-auto">
                            <input
                              type="text"
                              placeholder="Reason / note (optional)..."
                              value={excludeNote}
                              onChange={(e) => setExcludeNote(e.target.value)}
                              className="text-xs border border-gray-300 rounded px-2 py-1 bg-white text-gray-900 w-48 focus:outline-none focus:ring-1 focus:ring-amber-500"
                            />
                            <Button
                              size="sm"
                              disabled={excludeSaving}
                              onClick={() => handleExcludeCourse(u.course_code)}
                              className="h-7 text-xs bg-amber-800 hover:bg-amber-900 text-white font-medium"
                            >
                              {excludeSaving ? "Saving..." : "Confirm Exclude"}
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={excludeSaving}
                              onClick={() => {
                                setExcludingCourseCode(null);
                                setExcludeNote("");
                              }}
                              className="h-7 text-xs"
                            >
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setExcludingCourseCode(u.course_code);
                              setExcludeNote("");
                            }}
                            className="h-7 text-xs text-amber-800 hover:bg-amber-50 border-amber-300 hover:border-amber-400 font-medium"
                          >
                            Exclude
                          </Button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 🛠️ CORE COMPONENT DEEP GRID SYSTEM */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Side: Full Academic History Ledger — decoupled advisor columns */}
        <div className="lg:col-span-2 max-h-[500px] overflow-y-auto">
          <CourseLedger
            records={courseResults}
            columns={advisorColumns}
            title="Academic History Ledger"
            subtitle={`${courseResults.length} Courses`}
            icon={<BookOpen size={16} className="text-blue-900" />}
            emptyMessage="No academic records are attached to this student profile yet."
            getRowClassName={(c) => (c.prerequisite_met === false ? "bg-rose-50/40 hover:bg-rose-50/60" : "")}
          />
        </div>

        {/* Right Side: Proactive Advising Note Hub */}
        <Card className="flex flex-col h-full border border-gray-200">
          <div className="flex-1 overflow-y-auto">
            <CardHeader className="border-b border-gray-100 bg-gray-50/50 sticky top-0 z-10 pb-3">
              <CardTitle className="text-base font-bold text-gray-800 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-amber-500" /> Advising Logs
              </CardTitle>
              <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                Your record of each advising meeting: what was discussed and the next steps agreed. Shared notes are visible to the student; private notes are visible only to you.
              </p>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1">
                    Session Date
                  </label>
                  <Input
                    type="date"
                    value={sessionDate}
                    onChange={(e) => setSessionDate(e.target.value)}
                    className="h-9 text-xs"
                  />
                </div>

                <div>
                  <div className="flex justify-between items-center mb-1">
                    <label className="text-xs font-semibold text-gray-700">
                      Notes <span className="text-rose-500">*</span>
                    </label>
                    <span className="text-[10px] text-gray-400">Required</span>
                  </div>
                  <textarea
                    className="w-full min-h-[100px] p-3 text-sm text-gray-800 border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-900 bg-white resize-none shadow-sm"
                    placeholder="Notes (e.g., student advised to repeat Operating Systems)..."
                    value={notes}
                    onChange={(e) => {
                      setNotes(e.target.value);
                      if (inlineError) setInlineError(null);
                    }}
                    required
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1">
                    Action Item
                  </label>
                  <div className="relative">
                    <CheckSquare className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 transform -translate-y-1/2" />
                    <Input
                      placeholder="Action Item (Optional)"
                      value={actionItem}
                      onChange={(e) => setActionItem(e.target.value)}
                      className="pl-9 h-9 text-xs"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1">
                    Follow-up Date
                  </label>
                  <Input
                    type="date"
                    value={followUpDate}
                    onChange={(e) => setFollowUpDate(e.target.value)}
                    className="h-9 text-xs"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-gray-700 block mb-1">
                    Visibility
                  </label>
                  <div className="inline-flex rounded-lg border border-gray-200 bg-gray-100 p-1 w-full text-xs">
                    <button
                      type="button"
                      onClick={() => setVisibility("shared")}
                      className={`flex-1 py-1.5 rounded-md font-medium transition-all text-center cursor-pointer ${
                        visibility === "shared"
                          ? "bg-white text-gray-900 shadow-sm font-semibold"
                          : "text-gray-500 hover:text-gray-700"
                      }`}
                    >
                      Shared
                    </button>
                    <button
                      type="button"
                      onClick={() => setVisibility("private")}
                      className={`flex-1 py-1.5 rounded-md font-medium transition-all text-center cursor-pointer ${
                        visibility === "private"
                          ? "bg-white text-gray-900 shadow-sm font-semibold"
                          : "text-gray-500 hover:text-gray-700"
                      }`}
                    >
                      Private
                    </button>
                  </div>
                </div>

                {visibility === "shared" && (
                  <div className="flex items-center gap-2 pt-0.5">
                    <input
                      type="checkbox"
                      id="notifyStudent"
                      checked={notifyStudent}
                      onChange={(e) => setNotifyStudent(e.target.checked)}
                      className="w-4 h-4 text-blue-900 rounded border-gray-300 focus:ring-blue-900 cursor-pointer"
                    />
                    <label htmlFor="notifyStudent" className="text-xs font-medium text-gray-700 cursor-pointer select-none">
                      Notify student by email
                    </label>
                  </div>
                )}

                {notificationStatus && (
                  <div className={`p-2.5 text-xs rounded-lg flex items-center gap-2 ${
                    notificationStatus === "Student notified"
                      ? "text-emerald-800 bg-emerald-50 border border-emerald-200"
                      : "text-amber-800 bg-amber-50 border border-amber-200"
                  }`}>
                    <Info className="w-4 h-4 shrink-0" />
                    <span>{notificationStatus}</span>
                  </div>
                )}

                {inlineError && (
                  <div className="p-2.5 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0 text-rose-500" />
                    <span>{inlineError}</span>
                  </div>
                )}

                <Button 
                  className="w-full bg-blue-900 hover:bg-blue-800 text-white font-medium flex items-center justify-center gap-2 cursor-pointer"
                  onClick={handleSaveNotes}
                  disabled={isSaving || !notes.trim()}
                >
                  <Save className="w-4 h-4" /> {isSaving ? "Saving..." : "Commit Log"}
                </Button>
              </div>

              {pastLogs.length > 0 && (
                <div className="pt-4 border-t border-gray-100 space-y-3 mt-4">
                  <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Past Sessions</h4>
                  <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
                    {pastLogs.map((log) => {
                      const studentEmail = student?.institutional_email || student?.email || "";
                      const formattedDate = new Date(log.session_date).toLocaleDateString();
                      const mailSubject = encodeURIComponent(`Advising note – ${formattedDate}`);
                      const mailBody = encodeURIComponent(
                        log.action_item ? `${log.notes}\n\nNext step: ${log.action_item}` : log.notes
                      );
                      const mailtoUrl = `mailto:${studentEmail}?subject=${mailSubject}&body=${mailBody}`;

                      return (
                        <div key={log.id} className="bg-gray-50 p-3 rounded-lg border border-gray-100 text-sm">
                          <div className="flex items-center justify-between gap-2 text-xs text-gray-500 mb-1.5 font-medium">
                            <div className="flex items-center gap-1.5">
                              <Calendar className="w-3.5 h-3.5 text-gray-400" />
                              <span>{formattedDate}</span>
                            </div>
                            {log.visibility === "private" ? (
                              <Badge variant="outline" className="text-[10px] bg-amber-50 text-amber-800 border-amber-200 font-bold px-1.5 py-0">
                                Private
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700 border-blue-200 font-medium px-1.5 py-0">
                                Shared
                              </Badge>
                            )}
                          </div>
                          <p className="text-gray-800 whitespace-pre-wrap">{log.notes}</p>
                          {log.action_item && (
                            <div className="mt-2 text-xs font-medium text-amber-700 bg-amber-50 p-1.5 rounded-md flex items-start gap-1.5 border border-amber-100">
                              <CheckSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-600" />
                              <span>Action: {log.action_item}</span>
                            </div>
                          )}
                          {log.follow_up_date && (
                            <div className="mt-1.5 text-[11px] text-gray-500 flex items-center gap-1">
                              <Calendar className="w-3 h-3 text-gray-400" />
                              <span>Follow-up: {new Date(log.follow_up_date).toLocaleDateString()}</span>
                            </div>
                          )}
                          {log.visibility !== "private" && (
                            <div className="mt-2.5 pt-2 border-t border-gray-200/60 flex items-center justify-end">
                              <a
                                href={mailtoUrl}
                                className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-medium text-blue-900 bg-white hover:bg-blue-50 border border-gray-200 hover:border-blue-200 rounded-md shadow-2xs transition-colors cursor-pointer"
                                title="Draft email in default email client"
                              >
                                <Mail className="w-3 h-3 text-blue-800" />
                                <span>Draft email</span>
                              </a>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </div>
        </Card>

      </div>
    </div>
  );
}