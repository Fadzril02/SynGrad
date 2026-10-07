import React, { useState, useEffect } from "react";
import { Check, XCircle, Clock, CheckCircle2, FileText, Calendar, Eye, X, Plus, Trash2, AlertTriangle, Sparkles } from "lucide-react";
import { db } from "../../../lib/supabase";
import { api } from "../../../lib/api";
import { useAuth } from "../../../context/AuthContext";
import { Card, CardContent, Button } from "../../components/ui";
import {
  fetchGradeScale,
  gradesForDropdown,
  isPass,
  GradeScaleRow,
} from "../../../lib/gradeScale";

interface CorrectionsQueueProps {
  queue: any[];
  roster: any[];
  onApproved?: () => void; // callback so parent can refetch queue after approval
  onRefresh?: () => void;  // callback alias for parent view refresh
}

export function CorrectionsQueue({ queue, roster, onApproved, onRefresh }: CorrectionsQueueProps) {
  const { profile, user } = useAuth();
  const [liveQueue, setLiveQueue] = useState<any[]>(queue);
  const [filterStatus, setFilterStatus] = useState<string>("Pending_Advisor_Approval"); 

  const [activeAuditDoc, setActiveAuditDoc] = useState<any>(null);
  const [pdfUrl, setPdfUrl] = useState<string>("");
  const [isSaving, setIsSaving] = useState(false);
  const [gradeScale, setGradeScale] = useState<GradeScaleRow[]>([]);

  // Staged courses with manual fallback support
  const [stagedCourses, setStagedCourses] = useState<any[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [manualCode, setManualCode] = useState("");
  const [manualName, setManualName] = useState("");
  const [manualGrade, setManualGrade] = useState("A");
  const [manualCredits, setManualCredits] = useState(3);
  const [selectedSemester, setSelectedSemester] = useState<string>("");
  const [selectedSession, setSelectedSession] = useState<string>("");

  useEffect(() => { setLiveQueue(queue); }, [queue]);

  useEffect(() => {
    let isMounted = true;
    fetchGradeScale().then((scale) => {
      if (isMounted && scale.length > 0) {
        setGradeScale(scale);
        const firstGrade = scale.find((s) => s.counts_in_cgpa && s.points !== null) || scale[0];
        if (firstGrade) {
          setManualGrade(firstGrade.grade);
        }
      }
    });
    return () => {
      isMounted = false;
    };
  }, []);


  const pendingCount = liveQueue.filter((item) => item.processing_status === "Pending_Advisor_Approval").length;
  const approvedCount = liveQueue.filter((item) => item.processing_status === "Approved").length;

  const handleOpenAudit = async (doc: any) => {
    if (!doc) return;
    // Security: Use signed URL (1-hour expiry) instead of public URL.
    // Advisor boundary is enforced upstream — AdvisorPortal.tsx filters the queue
    // to only include documents whose matric_no belongs to this advisor's students.
    const { data, error } = await db.storage.from("academic-slips").createSignedUrl(doc.file_path, 3600);
    if (error || !data?.signedUrl) {
      console.error("Failed to create signed URL:", error);
      alert("Unable to load document. The file may not exist or you may not have access.");
      return;
    }
    setPdfUrl(data.signedUrl);
    setActiveAuditDoc(doc);
    const courses = Array.isArray(doc.extracted_data?.courses) ? doc.extracted_data.courses : [];
    setStagedCourses([...courses.filter(Boolean)]);
    setShowAddForm(false);
    setManualCode("");
    setManualName("");
    setManualGrade("A");
    setManualCredits(3);
    const ext = doc.extracted_data || {};
    const firstSem = Array.isArray(ext.semesters) && ext.semesters.length > 0 ? ext.semesters[0] : null;
    setSelectedSemester(ext.semester ? String(ext.semester) : (firstSem?.semester_no ? String(firstSem.semester_no) : ""));
    setSelectedSession(ext.academic_session || firstSem?.session || "");
  };

  const handleAddManualCourse = () => {
    const trimmed = manualCode.trim().toUpperCase();
    if (!trimmed) {
      alert("Please enter a valid Course Code (e.g. SECJ1013).");
      return;
    }
    const newCourse = {
      course_code: trimmed,
      course_name: manualName.trim() || trimmed,
      grade: manualGrade.trim().toUpperCase(),
      credit_hour: Number(manualCredits) || 3,
      credits: Number(manualCredits) || 3,
      status: isPass(manualGrade, gradeScale) ? "Passed" : "Failed",
      session_semester: selectedSemester && selectedSession.trim() ? `SEM ${selectedSemester} ${selectedSession.trim()}` : undefined,
    };
    setStagedCourses(prev => [...prev, newCourse]);
    setManualCode("");
    setManualName("");
    setShowAddForm(false);
  };

  const handleRemoveCourse = (index: number) => {
    setStagedCourses(prev => prev.filter((_, i) => i !== index));
  };

  const handleReject = async () => {
    if (!activeAuditDoc) return;
    const confirmReject = window.confirm(
      "Are you sure you want to reject this document? (e.g. unreadable file, wrong document uploaded, or incorrect student)"
    );
    if (!confirmReject) return;

    setIsSaving(true);
    const docId = activeAuditDoc.id;

    try {
      // Rejection is done by the backend only (it verifies you are this student's advisor)
      try {
        await api.rejectDocument(docId, "Document rejected by advisor");
      } catch (apiErr: any) {
        const detail = apiErr?.response?.data?.detail || apiErr?.message || "Please try again.";
        console.error("[CorrectionsQueue] reject-document failed:", apiErr);
        alert(`Rejection failed: ${detail}`);
        return;
      }

      // 3. Clear UI state immediately on success
      setActiveAuditDoc(null);
      setLiveQueue(prev => (prev || []).filter(item => item?.id !== docId));
      if (onApproved) {
        onApproved();
      }
      if (onRefresh) {
        onRefresh();
      }
    } catch (err: any) {
      console.error("[CorrectionsQueue] Unhandled exception in handleReject:", err);
      alert(`Unexpected error rejecting document: ${err?.message || "Please try again."}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleApprove = async () => {
    if (!activeAuditDoc) return;
    if (!stagedCourses || stagedCourses.length === 0) {
      alert("No course records provided for approval. Please add courses manually before approving.");
      return;
    }

    if (!selectedSemester || !selectedSession.trim()) {
      alert("Please select Semester (1-4) and enter Academic Session (e.g. 2024/2025) before approving.");
      return;
    }

    // Capture doc reference before async gap to prevent stale-closure crash
    // if user closes the modal while the API call is in-flight.
    const docId = activeAuditDoc.id;
    const docMatricNo = activeAuditDoc.matric_no;
    const studentData = activeAuditDoc.extracted_data || {};

    setIsSaving(true);
    
    try {
      const matchingStudent = roster?.find((s) => s?.id === docMatricNo || s?.matric_no === docMatricNo);
      
      // Route through FastAPI Zero-Waste engine for DAG verification & persistence into academic_records.
      // Note: advisor_id is strictly derived from the verified JWT payload on the backend.
      const tenantId = (profile as any)?.tenant_id || (profile as any)?.university_id;
      await api.finalizeApproval({
        document_id: docId,
        matric_number: docMatricNo,
        tenant_id: tenantId,
        student_name: matchingStudent ? matchingStudent.name : (studentData.student_name || docMatricNo),
        academic_session: selectedSession.trim(),
        semester: Number(selectedSemester),
        pngk: studentData.pngk ?? studentData.cgpa,
        courses: stagedCourses.filter(Boolean).map(c => ({
          course_code: String(c.course_code || "").replace(/\s+/g, "").toUpperCase() || "UNKNOWN",
          course_name: String(c.course_name || c.course_code || "Unknown Course"),
          grade: String(c.grade || "N/A").trim().toUpperCase(),
          credit_hour: Number(c.credit_hour ?? c.credits ?? 3) || 3,
          credits: Number(c.credits ?? c.credit_hour ?? 3) || 3,
          status: c.status || "Pass",
          warning: c.warning,
          session_semester: c.session_semester,
        }))
      });

      // FIX #3: Optimistically remove from local state immediately so the UI
      // reflects the approval without waiting for a parent refetch.
      // Then call onApproved() so the parent (AdvisorPortal) also refetches
      // fresh queue data from the server, keeping everything in sync.
      setLiveQueue(prev => (prev || []).filter(item => item?.id !== docId));
      setActiveAuditDoc(null);

      // Notify parent to refetch — console.log here is intentional for verification;
      // remove once you've confirmed it fires in DevTools.
      console.log('[CorrectionsQueue] Approval committed for docId:', docId, '— triggering parent refetch via onApproved()');
      if (onApproved) onApproved();

    } catch (err: any) {
      console.error("Save failed:", err);
      const errMsg = err?.response?.data?.detail || err?.message || "Failed to commit verified records.";
      alert(`Approval Failed: ${errMsg}`);
    } finally {
      // Ensure loading spinner is disabled so the UI never permanently hangs
      setIsSaving(false);
    }
  };

  const displayQueue = liveQueue.filter((item) => item.processing_status === filterStatus);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4">
        <button onClick={() => setFilterStatus("Pending_Advisor_Approval")} className={`text-left transition-all ${filterStatus === "Pending_Advisor_Approval" ? "scale-[1.02]" : "opacity-75"}`}>
          <Card className={`border-l-4 p-1 ${filterStatus === "Pending_Advisor_Approval" ? "border-l-[#FFCC00] bg-amber-50/20" : "border-l-gray-300"}`}>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Awaiting Audit</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{pendingCount}</p>
              </div>
              <Clock className="w-6 h-6 text-[#997a00]" />
            </CardContent>
          </Card>
        </button>

        <button onClick={() => setFilterStatus("Approved")} className={`text-left transition-all ${filterStatus === "Approved" ? "scale-[1.02]" : "opacity-75"}`}>
          <Card className={`border-l-4 p-1 ${filterStatus === "Approved" ? "border-l-emerald-500 bg-emerald-50/10" : "border-l-gray-300"}`}>
            <CardContent className="p-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Verified Records</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{approvedCount}</p>
              </div>
              <CheckCircle2 className="w-6 h-6 text-emerald-600" />
            </CardContent>
          </Card>
        </button>
      </div>

      <div className="space-y-4">
        {displayQueue.length === 0 ? (
          <div className="p-8 text-center bg-white rounded-lg border border-dashed text-gray-500">All caught up! No pending documents.</div>
        ) : (
          displayQueue.map((req) => {
            const matchingStudent = roster.find((s) => s.id === req.matric_no);
            const studentName = matchingStudent ? matchingStudent.name : req.matric_no;

            return (
              <Card key={req.id} className="hover:border-gray-300 transition-colors">
                <CardContent className="p-6 flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-gray-900 text-lg">{studentName}</h3>
                    <p className="text-sm text-gray-500">{req.file_name} • Uploaded {new Date(req.uploaded_at || Date.now()).toLocaleDateString()}</p>
                  </div>
                  {req.processing_status === "Pending_Advisor_Approval" && (
                    <Button onClick={() => handleOpenAudit(req)} className="bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm">
                      <Eye className="w-4 h-4 mr-2" /> Audit Document
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {activeAuditDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-7xl h-[90vh] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-slate-50">
              <div>
                <h3 className="text-lg font-bold text-gray-900">Document Audit</h3>
                <p className="text-sm text-gray-500">Student: {activeAuditDoc.matric_no}</p>
              </div>
              <button onClick={() => !isSaving && setActiveAuditDoc(null)} disabled={isSaving}><X className={`w-6 h-6 ${isSaving ? "text-gray-300 cursor-not-allowed" : "text-gray-500 hover:text-gray-800"}`} /></button>
            </div>
            
            {/* THE MASSIVE FRAUD ALERT BANNER */}
            {activeAuditDoc.fraud_flag && (
              <div className="bg-[#990033] text-white px-6 py-3 flex items-center justify-center font-bold tracking-widest text-sm shadow-inner uppercase">
                ⚠️ System Alert: Metadata Anomaly Detected. Suspected Digital Forgery. ⚠️
              </div>
            )}

            <div className="flex-1 flex overflow-hidden">
              <div className="w-1/2 border-r border-gray-200 bg-gray-100 p-4">
                <h4 className="text-xs font-bold text-gray-500 uppercase mb-2">Original Document</h4>
                <iframe src={pdfUrl} className="w-full h-full rounded shadow-sm border border-gray-300 bg-white" />
              </div>

              <div className="w-1/2 p-6 overflow-y-auto bg-white flex flex-col justify-between">
                <div>
                  {/* AI Banner */}
                  {activeAuditDoc?.extracted_data?.source === "ai" && (
                    <div className="mb-4 p-3.5 bg-blue-50 border border-blue-200 text-blue-900 rounded-lg flex items-center gap-2.5 text-xs font-medium">
                      <Sparkles className="w-4 h-4 text-blue-800 shrink-0" />
                      <span>Read by AI — please check every row carefully</span>
                    </div>
                  )}

                  {/* Warnings above the table */}
                  {activeAuditDoc?.extracted_data?.warnings && activeAuditDoc.extracted_data.warnings.length > 0 && (
                    <div className="mb-4 space-y-2">
                      {activeAuditDoc.extracted_data.warnings.map((w: string, idx: number) => {
                        const isMatricMismatch = w.toLowerCase().includes("someone else");
                        return (
                          <div
                            key={idx}
                            className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 ${
                              isMatricMismatch
                                ? "bg-rose-50 border-rose-300 text-rose-900 font-semibold"
                                : "bg-amber-50 border-amber-300 text-amber-900"
                            }`}
                          >
                            <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${isMatricMismatch ? "text-rose-600" : "text-amber-600"}`} />
                            <div>
                              <span className="font-bold block">{isMatricMismatch ? "Matric Mismatch Alert (Approval Blocked)" : "Transcript Verification Warning"}</span>
                              <span>{w}</span>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Required Semester & Academic Session per Document */}
                  <div className="mb-5 p-3.5 bg-slate-50 border border-slate-200 rounded-lg space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold uppercase tracking-wider text-gray-700 flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-indigo-600" />
                        Semester & Academic Session *
                      </span>
                      {(!selectedSemester || !selectedSession.trim()) && (
                        <span className="text-[11px] font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                          Required for approval
                        </span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-[11px] font-medium text-gray-600 block mb-1">Semester (1–4) *</label>
                        <select
                          value={selectedSemester}
                          onChange={(e) => setSelectedSemester(e.target.value)}
                          className="w-full text-xs font-semibold px-2.5 py-1.5 border border-gray-300 rounded bg-white focus:outline-indigo-500"
                        >
                          <option value="">-- Select Semester --</option>
                          <option value="1">Semester 1</option>
                          <option value="2">Semester 2</option>
                          <option value="3">Semester 3</option>
                          <option value="4">Semester 4</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-[11px] font-medium text-gray-600 block mb-1">Session (YYYY/YYYY) *</label>
                        <input
                          type="text"
                          placeholder="e.g. 2024/2025"
                          value={selectedSession}
                          onChange={(e) => setSelectedSession(e.target.value)}
                          className="w-full text-xs font-mono px-2.5 py-1.5 border border-gray-300 rounded bg-white focus:outline-indigo-500"
                        />
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h4 className="text-xs font-bold text-gray-500 uppercase">Student Submitted Data</h4>
                      <p className="text-xs text-gray-400">{stagedCourses.length} course{stagedCourses.length === 1 ? "" : "s"} staged for audit</p>
                    </div>
                    <Button
                      onClick={() => setShowAddForm(!showAddForm)}
                      variant="outline"
                      size="sm"
                      className="text-xs font-semibold text-indigo-600 border-indigo-200 hover:bg-indigo-50"
                    >
                      <Plus className="w-3.5 h-3.5 mr-1" />
                      Add Course Manually
                    </Button>
                  </div>

                  {/* Manual Course Input Form */}
                  {showAddForm && (
                    <div className="mb-4 p-4 border border-indigo-100 bg-indigo-50/50 rounded-lg space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-indigo-900">Add Course Entry</span>
                        <button onClick={() => setShowAddForm(false)} className="text-gray-400 hover:text-gray-600 text-xs">Cancel</button>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="text-[11px] font-medium text-gray-600 block mb-1">Course Code *</label>
                          <input
                            type="text"
                            placeholder="e.g. SECJ1013"
                            value={manualCode}
                            onChange={(e) => setManualCode(e.target.value.toUpperCase())}
                            className="w-full text-xs font-mono px-2.5 py-1.5 border border-gray-300 rounded bg-white focus:outline-indigo-500"
                          />
                        </div>
                        <div>
                          <label className="text-[11px] font-medium text-gray-600 block mb-1">Course Name</label>
                          <input
                            type="text"
                            placeholder="e.g. Programming Technique I"
                            value={manualName}
                            onChange={(e) => setManualName(e.target.value)}
                            className="w-full text-xs px-2.5 py-1.5 border border-gray-300 rounded bg-white focus:outline-indigo-500"
                          />
                        </div>
                        <div>
                          <label className="text-[11px] font-medium text-gray-600 block mb-1">Grade *</label>
                          <select
                            value={manualGrade}
                            onChange={(e) => setManualGrade(e.target.value)}
                            className="w-full text-xs font-bold px-2.5 py-1.5 border border-gray-300 rounded bg-white focus:outline-indigo-500"
                          >
                            {gradeScale.length > 0 ? (
                              gradesForDropdown(gradeScale).map((g) => (
                                <option key={g.grade} value={g.grade}>
                                  {g.grade}{g.achievement_label ? ` (${g.achievement_label})` : ""}
                                </option>
                              ))
                            ) : (
                              <option value={manualGrade}>{manualGrade}</option>
                            )}
                          </select>
                        </div>
                        <div>
                          <label className="text-[11px] font-medium text-gray-600 block mb-1">Credits</label>
                          <input
                            type="number"
                            min="1"
                            max="12"
                            value={manualCredits}
                            onChange={(e) => setManualCredits(Number(e.target.value))}
                            className="w-full text-xs font-mono px-2.5 py-1.5 border border-gray-300 rounded bg-white focus:outline-indigo-500"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end">
                        <Button
                          size="sm"
                          onClick={handleAddManualCourse}
                          className="text-xs bg-indigo-600 hover:bg-indigo-700 text-white"
                        >
                          <Plus className="w-3 h-3 mr-1" /> Add to List
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Course Table or Empty Fallback */}
                  {(() => {
                    const isMultiSem = Boolean(
                      (activeAuditDoc?.extracted_data?.semesters && activeAuditDoc.extracted_data.semesters.length > 1) ||
                      (stagedCourses && new Set(stagedCourses.map((c: any) => c.session_semester).filter(Boolean)).size > 1)
                    );
                    return stagedCourses.length === 0 ? (
                      <div className="p-8 text-center border-2 border-dashed border-amber-300 rounded-lg bg-amber-50/40">
                        <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto mb-2" />
                        <p className="text-sm font-semibold text-gray-800">No courses extracted automatically</p>
                        <p className="text-xs text-gray-500 mt-1 mb-4">
                          PDF extraction found 0 course rows. Add courses manually using the button below to bypass PDF extraction failure.
                        </p>
                        <Button
                          onClick={() => setShowAddForm(true)}
                          className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold"
                        >
                          <Plus className="w-4 h-4 mr-1.5" /> Add Course Manually
                        </Button>
                      </div>
                    ) : (
                      <div className="border border-gray-200 rounded-lg overflow-hidden">
                        <table className="w-full text-left">
                          <thead className="bg-gray-50 border-b">
                            <tr>
                              {isMultiSem && (
                                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Semester</th>
                              )}
                              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Course Code</th>
                              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Course Name</th>
                              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Grade</th>
                              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Credits</th>
                              <th className="px-2 py-3 text-xs font-semibold text-gray-500 uppercase text-center">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y text-xs">
                            {stagedCourses.filter(Boolean).map((course: any, idx: number) => (
                              <tr key={idx} className="hover:bg-slate-50/50">
                                {isMultiSem && (
                                  <td className="px-4 py-2.5 font-mono text-xs text-gray-700">
                                    {course.session_semester || "—"}
                                  </td>
                                )}
                                <td className="px-4 py-2.5 font-mono font-bold text-gray-900">
                                  <div>{course.course_code || "—"}</div>
                                  {course.warning && (
                                    <div className="mt-1 flex items-start gap-1 text-[10px] font-sans font-normal text-amber-800 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5 max-w-[200px] leading-tight">
                                      <AlertTriangle className="w-3 h-3 text-amber-600 shrink-0 mt-0.5" />
                                      <span>{course.warning}</span>
                                    </div>
                                  )}
                                </td>
                                <td className="px-4 py-2.5 text-gray-600 truncate max-w-[140px]">{course.course_name || course.course_code || "—"}</td>
                                <td className="px-4 py-2.5 font-bold text-[#990033]">{course.grade || "N/A"}</td>
                                <td className="px-4 py-2.5 font-mono">{course.credit_hour ?? course.credits ?? "—"}</td>
                                <td className="px-2 py-2.5 text-center">
                                  <button
                                    onClick={() => handleRemoveCourse(idx)}
                                    className="text-gray-400 hover:text-rose-600 p-1 cursor-pointer"
                                    title="Remove Course"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    );
                  })()}
                </div>

                <div className="mt-8 pt-4 border-t border-gray-100 flex space-x-4">
                  <Button
                    onClick={handleReject}
                    disabled={isSaving}
                    variant="outline"
                    className="flex-1 text-rose-600 border-rose-200 hover:bg-rose-50 disabled:opacity-50"
                  >
                    <XCircle className="w-4 h-4 mr-2" /> {isSaving ? "Rejecting..." : "Reject Document"}
                  </Button>
                  {(() => {
                    const hasMatricMismatch = Boolean(
                      (activeAuditDoc?.extracted_data?.warnings || []).some((w: string) =>
                        w.toLowerCase().includes("someone else")
                      )
                    );
                    return (
                      <Button
                        onClick={handleApprove}
                        disabled={isSaving || stagedCourses.length === 0 || !selectedSemester || !selectedSession.trim() || hasMatricMismatch}
                        className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white shadow-md disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-4 h-4 mr-2" />
                        {isSaving ? "Saving..." : hasMatricMismatch ? "Blocked (Matric Mismatch)" : `Approve & Commit (${stagedCourses.length})`}
                      </Button>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}