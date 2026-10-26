import { supabase } from '../../lib/supabase';
import React, { useState, useEffect } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { api, warmUpBackend } from '../../lib/api';
import { LoadingScreen } from '../../components/shared/LoadingScreen';
import { 
  GraduationCap, 
  Briefcase, 
  UserCheck, 
  AlertCircle, 
  Loader2, 
  ArrowRight, 
  LogOut,
  Hash,
  Key,
  Building2,
  User,
  CheckCircle2
} from 'lucide-react';

export function CompleteRegistration() {
  const navigate = useNavigate();
  const { user, profile, role, loading, signOut } = useAuth();

  const [roleType, setRoleType] = useState<'student' | 'advisor'>('student');

  // Student form state
  const [cohortCode, setCohortCode] = useState('');
  const [matricNo, setMatricNo] = useState('');
  const [studentFullName, setStudentFullName] = useState('');

  // Advisor form state
  const [inviteCode, setInviteCode] = useState('');
  const [staffId, setStaffId] = useState('');
  const [advisorFullName, setAdvisorFullName] = useState('');
  const [department, setDepartment] = useState('');

  // Status & error state
  const [inlineError, setInlineError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  // Warm up backend (one silent ping per page load)
  useEffect(() => {
    warmUpBackend();
  }, []);

  // Auto-fill full name from Supabase user_metadata if available
  useEffect(() => {
    const metaName = user?.user_metadata?.full_name;
    if (metaName) {
      setStudentFullName((prev) => prev || metaName);
      setAdvisorFullName((prev) => prev || metaName);
    }
  }, [user]);

  // If user already has a profile, redirect to their dashboard
  useEffect(() => {
    if (!loading && user && profile) {
      if (role === 'advisor') {
        navigate('/advisor', { replace: true });
      } else if (role === 'student') {
        navigate('/student', { replace: true });
      }
    }
  }, [loading, user, profile, role, navigate]);

  if (loading) {
    return <LoadingScreen />;
  }

  // If unauthenticated, redirect to login
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  const parseBackendError = (err: any): string => {
    const detail = err.response?.data?.detail;
    if (detail) {
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) {
        return detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
      }
      return JSON.stringify(detail);
    }
    return (
      err.response?.data?.message ||
      err.message ||
      'Registration failed. Please check your inputs and try again.'
    );
  };

  const handleStudentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setInlineError(null);

    const cleanCohort = cohortCode.trim().toUpperCase();
    const cleanMatric = matricNo.trim().toUpperCase();
    const cleanName = studentFullName.trim();

    if (!cleanCohort) {
      setInlineError('Please enter your Cohort Code.');
      return;
    }
    if (!cleanMatric) {
      setInlineError('Please enter your Matric Number.');
      return;
    }
    if (!cleanName) {
      setInlineError('Please enter your Full Name.');
      return;
    }

    setIsSubmitting(true);
    try {
      await api.registerStudent({
        cohort_code: cleanCohort,
        matric_no: cleanMatric,
        full_name: cleanName,
      });

      // Role + tenant were just written to app_metadata server-side; refresh so the
      // next API call carries them (stale token -> 'Tenant ID cannot be securely verified').
      await supabase.auth.refreshSession();
      setIsSuccess(true);
      window.location.assign('/student');
    } catch (err: any) {
      console.error('[CompleteRegistration] Student registration error:', err);
      setInlineError(parseBackendError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAdvisorSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setInlineError(null);

    const cleanInvite = inviteCode.trim();
    const cleanStaff = staffId.trim().toUpperCase();
    const cleanName = advisorFullName.trim();
    const cleanDept = department.trim();

    if (!cleanInvite) {
      setInlineError('Please enter your Advisor Invite Code.');
      return;
    }
    if (!cleanStaff) {
      setInlineError('Please enter your Staff ID.');
      return;
    }
    if (!cleanName) {
      setInlineError('Please enter your Full Name.');
      return;
    }
    if (!cleanDept) {
      setInlineError('Department is required. Please specify your department.');
      return;
    }

    setIsSubmitting(true);
    try {
      await api.registerAdvisor({
        invite_code: cleanInvite,
        staff_id: cleanStaff,
        full_name: cleanName,
        department: cleanDept,
      });

      // Role + tenant were just written to app_metadata server-side; refresh so the
      // next API call carries them (stale token -> 'Tenant ID cannot be securely verified').
      await supabase.auth.refreshSession();
      setIsSuccess(true);
      window.location.assign('/advisor');
    } catch (err: any) {
      console.error('[CompleteRegistration] Advisor registration error:', err);
      setInlineError(parseBackendError(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <div className="h-12 w-12 rounded-xl bg-blue-900 flex items-center justify-center text-white shadow-md">
            <UserCheck className="w-6 h-6" />
          </div>
        </div>
        <h2 className="mt-4 text-center text-2xl font-bold tracking-tight text-slate-900">
          Complete Your Registration
        </h2>
        <p className="mt-1.5 text-center text-sm text-slate-600">
          Your account is verified. Connect your institutional profile to continue.
        </p>

        {/* User Identity Banner */}
        <div className="mt-3 flex items-center justify-center gap-1.5 text-xs text-slate-500 font-mono bg-slate-100 py-1 px-3 rounded-full border border-slate-200 mx-auto w-fit">
          <span>Logged in as</span>
          <span className="font-semibold text-slate-700">{user.email}</span>
        </div>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-lg">
        <div className="bg-white py-8 px-6 shadow-sm border border-slate-200 sm:rounded-2xl sm:px-10">
          
          {/* Role Selection Tabs */}
          <div className="mb-6 grid grid-cols-2 gap-3 p-1 bg-slate-100 rounded-xl">
            <button
              type="button"
              onClick={() => {
                setRoleType('student');
                setInlineError(null);
              }}
              className={`flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-medium text-xs sm:text-sm transition-all ${
                roleType === 'student'
                  ? 'bg-white text-blue-900 shadow-sm border border-slate-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <GraduationCap className="w-4 h-4" />
              <span>Student</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setRoleType('advisor');
                setInlineError(null);
              }}
              className={`flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-medium text-xs sm:text-sm transition-all ${
                roleType === 'advisor'
                  ? 'bg-white text-blue-900 shadow-sm border border-slate-200'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Briefcase className="w-4 h-4" />
              <span>Academic Advisor</span>
            </button>
          </div>

          {/* Inline Backend Error Alert */}
          {inlineError && (
            <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-sm text-red-800 flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <span className="font-semibold block mb-0.5">Registration Error</span>
                <span className="text-xs leading-relaxed">{inlineError}</span>
              </div>
            </div>
          )}

          {/* Success Alert */}
          {isSuccess && (
            <div className="mb-6 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-800 flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
              <span className="text-xs font-medium">Profile linked successfully! Routing to portal...</span>
            </div>
          )}

          {/* Student Form */}
          {roleType === 'student' && (
            <form onSubmit={handleStudentSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Cohort Code <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Key className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={cohortCode}
                    onChange={(e) => setCohortCode(e.target.value.toUpperCase())}
                    placeholder="e.g. 6-character code"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 font-mono placeholder:font-sans focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent uppercase"
                  />
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Provided by your academic advisor or department.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Matric Number <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Hash className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={matricNo}
                    onChange={(e) => setMatricNo(e.target.value.toUpperCase())}
                    placeholder="e.g. A22EC0123"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 font-mono placeholder:font-sans focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent uppercase"
                  />
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Must match your institution's matric format.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Full Name <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={studentFullName}
                    onChange={(e) => setStudentFullName(e.target.value)}
                    placeholder="e.g. Ahmad Albab"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting || isSuccess}
                className="w-full mt-2 py-2.5 px-4 bg-blue-900 hover:bg-blue-800 disabled:bg-blue-300 text-white text-sm font-semibold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Registering Student...</span>
                  </>
                ) : (
                  <>
                    <span>Complete Registration</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Advisor Form */}
          {roleType === 'advisor' && (
            <form onSubmit={handleAdvisorSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Advisor Invite Code <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Key className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value)}
                    placeholder="Enter your invite code"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 font-mono placeholder:font-sans focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent"
                  />
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Supplied by your institutional administrator.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Staff ID <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Hash className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={staffId}
                    onChange={(e) => setStaffId(e.target.value.toUpperCase())}
                    placeholder="e.g. STF-1029"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 font-mono placeholder:font-sans focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent uppercase"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Full Name <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={advisorFullName}
                    onChange={(e) => setAdvisorFullName(e.target.value)}
                    placeholder="e.g. Dr. John Doe"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Department <span className="text-red-500">*</span>
                </label>
                <div className="relative">
                  <Building2 className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    placeholder="e.g. Software Engineering"
                    required
                    className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-900 focus:border-transparent"
                  />
                </div>
                <p className="mt-1 text-[11px] text-slate-500">
                  Department is required with no default.
                </p>
              </div>

              <button
                type="submit"
                disabled={isSubmitting || isSuccess}
                className="w-full mt-2 py-2.5 px-4 bg-blue-900 hover:bg-blue-800 disabled:bg-blue-300 text-white text-sm font-semibold rounded-lg shadow-sm transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Registering Advisor...</span>
                  </>
                ) : (
                  <>
                    <span>Complete Registration</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Account Switcher Footer */}
          <div className="mt-8 pt-5 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Wrong account?</span>
            <button
              type="button"
              onClick={() => signOut()}
              className="inline-flex items-center gap-1.5 text-red-600 hover:text-red-700 font-medium cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default CompleteRegistration;
