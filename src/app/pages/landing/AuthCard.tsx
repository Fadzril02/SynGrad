import React from "react";
import { 
  GraduationCap, 
  Users, 
  Eye, 
  EyeOff, 
  AlertCircle, 
  CheckCircle2, 
  ArrowRight, 
  Mail, 
  Lock, 
  User, 
  Loader2 
} from "lucide-react";

interface AuthCardProps {
  authMode: "login" | "register";
  setAuthMode: (mode: "login" | "register") => void;
  registrationRole: "student" | "advisor";
  setRegistrationRole: (role: "student" | "advisor") => void;
  loginEmail: string;
  setLoginEmail: (val: string) => void;
  loginPassword: string;
  setLoginPassword: (val: string) => void;
  showLoginPassword: boolean;
  setShowLoginPassword: (val: boolean) => void;
  studentFullName: string;
  setStudentFullName: (val: string) => void;
  studentEmail: string;
  setStudentEmail: (val: string) => void;
  studentPassword: string;
  setStudentPassword: (val: string) => void;
  showStudentPassword: boolean;
  setShowStudentPassword: (val: boolean) => void;
  advisorFullName: string;
  setAdvisorFullName: (val: string) => void;
  advisorEmail: string;
  setAdvisorEmail: (val: string) => void;
  advisorPassword: string;
  setAdvisorPassword: (val: string) => void;
  showAdvisorPassword: boolean;
  setShowAdvisorPassword: (val: boolean) => void;
  errorMessage: string | null;
  successMessage: string | null;
  authError: string | null;
  processing: boolean;
  handleLogin: (e: React.FormEvent) => void;
  handleRegistration: (e: React.FormEvent) => void;
  resetFormFeedback: () => void;
}

export function AuthCard({
  authMode,
  setAuthMode,
  registrationRole,
  setRegistrationRole,
  loginEmail,
  setLoginEmail,
  loginPassword,
  setLoginPassword,
  showLoginPassword,
  setShowLoginPassword,
  studentFullName,
  setStudentFullName,
  studentEmail,
  setStudentEmail,
  studentPassword,
  setStudentPassword,
  showStudentPassword,
  setShowStudentPassword,
  advisorFullName,
  setAdvisorFullName,
  advisorEmail,
  setAdvisorEmail,
  advisorPassword,
  setAdvisorPassword,
  showAdvisorPassword,
  setShowAdvisorPassword,
  errorMessage,
  successMessage,
  authError,
  processing,
  handleLogin,
  handleRegistration,
  resetFormFeedback,
}: AuthCardProps) {
  return (
    <div className="w-full max-w-md mx-auto bg-white rounded-2xl border border-[#E5E7EB] shadow-sm p-6 sm:p-8">
      {/* Tab Switcher: Log In | Create Account */}
      <div className="grid grid-cols-2 p-1 bg-[#F9FAFB] rounded-xl mb-6 border border-[#E5E7EB]">
        <button
          type="button"
          onClick={() => {
            setAuthMode("login");
            resetFormFeedback();
          }}
          className={`py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] ${
            authMode === "login"
              ? "bg-white text-[#1E3A8A] shadow-xs font-bold"
              : "text-ink-muted hover:text-[#1E3A8A]"
          }`}
        >
          Log in
        </button>
        <button
          type="button"
          onClick={() => {
            setAuthMode("register");
            resetFormFeedback();
          }}
          className={`py-2 text-xs font-semibold rounded-lg transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] ${
            authMode === "register"
              ? "bg-white text-[#1E3A8A] shadow-xs font-bold"
              : "text-ink-muted hover:text-[#1E3A8A]"
          }`}
        >
          Create account
        </button>
      </div>

      {/* Form Heading & Subtext */}
      <div className="mb-6">
        <h2 className="font-serif text-xl sm:text-2xl font-bold tracking-tight text-[#1E3A8A]">
          {authMode === "login"
            ? "Welcome back"
            : "Create your account"}
        </h2>
        <p className="text-xs text-ink mt-1.5 leading-relaxed font-normal">
          {authMode === "login"
            ? "Sign in with your institutional credentials to access your advising portal."
            : "Choose your role below to get started with curriculum & degree audit tools."}
        </p>
      </div>

      {/* Inline Feedback Alerts */}
      {(errorMessage || authError) && (
        <div className="mb-5 p-3.5 rounded-xl bg-[#FEF2F2] border border-[#FECACA] text-xs font-medium text-[#B91C1C] leading-relaxed space-y-2">
          <div className="flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 shrink-0 text-[#DC2626] mt-0.5" />
            <span>{errorMessage || authError}</span>
          </div>
        </div>
      )}

      {successMessage && (
        <div className="mb-5 p-3.5 rounded-xl bg-[#ECFDF5] border border-[#A7F3D0] text-xs font-medium text-[#047857] leading-relaxed flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-[#059669]" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Dynamic Form Area */}
      {authMode === "login" ? (
        /* Login Form */
        <form onSubmit={handleLogin} className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="loginEmail" className="block text-xs font-semibold text-[#1E3A8A]">
              Institutional Email
            </label>
            <div className="relative">
              <Mail className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="loginEmail"
                type="email"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="e.g. name@university.edu"
                required
                className="w-full pl-9 pr-3 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="loginPassword" className="block text-xs font-semibold text-[#1E3A8A]">
              Password
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="loginPassword"
                type={showLoginPassword ? "text" : "password"}
                autoComplete="current-password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="w-full pl-9 pr-10 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowLoginPassword(!showLoginPassword)}
                aria-label={showLoginPassword ? "Hide password" : "Show password"}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-[#1E3A8A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] rounded-sm p-1 cursor-pointer"
              >
                {showLoginPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={processing}
            className="w-full py-3 px-4 mt-2 bg-[#1E3A8A] hover:bg-[#1E40AF] active:bg-[#1E40AF] text-white text-xs font-semibold rounded-xl shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {processing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Signing in...</span>
              </>
            ) : (
              <>
                <span>Sign in to portal</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      ) : (
        /* Registration Form */
        <form onSubmit={handleRegistration} className="space-y-4">
          {/* Role Toggle */}
          <div className="space-y-1.5">
            <span className="block text-xs font-semibold text-[#1E3A8A]">
              Select Your Role
            </span>
            <div className="grid grid-cols-2 p-1 bg-[#F9FAFB] rounded-xl border border-[#E5E7EB]">
              <button
                type="button"
                onClick={() => {
                  setRegistrationRole("student");
                  resetFormFeedback();
                }}
                className={`py-2 text-xs rounded-lg transition-all cursor-pointer flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] ${
                  registrationRole === "student"
                    ? "bg-white text-[#1E3A8A] font-bold shadow-xs border border-[#E5E7EB]"
                    : "text-ink-muted hover:text-[#1E3A8A] font-medium"
                }`}
              >
                <GraduationCap className="w-4 h-4" />
                <span>Student</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setRegistrationRole("advisor");
                  resetFormFeedback();
                }}
                className={`py-2 text-xs rounded-lg transition-all cursor-pointer flex items-center justify-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] ${
                  registrationRole === "advisor"
                    ? "bg-white text-[#1E3A8A] font-bold shadow-xs border border-[#E5E7EB]"
                    : "text-ink-muted hover:text-[#1E3A8A] font-medium"
                }`}
              >
                <Users className="w-4 h-4" />
                <span>Advisor</span>
              </button>
            </div>
          </div>

          {/* Role-Specific Fields */}
          {registrationRole === "student" ? (
            <>
              <div className="space-y-1.5">
                <label htmlFor="studentFullName" className="block text-xs font-semibold text-[#1E3A8A]">
                  Full Name
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="studentFullName"
                    type="text"
                    value={studentFullName}
                    onChange={(e) => setStudentFullName(e.target.value)}
                    placeholder="e.g. Alex Tan"
                    required
                    className="w-full pl-9 pr-3 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="studentEmail" className="block text-xs font-semibold text-[#1E3A8A]">
                  Institutional Email Address
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="studentEmail"
                    type="email"
                    value={studentEmail}
                    onChange={(e) => setStudentEmail(e.target.value)}
                    placeholder="e.g. alex@university.edu.my"
                    required
                    className="w-full pl-9 pr-3 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="studentPassword" className="block text-xs font-semibold text-[#1E3A8A]">
                  Password (min. 6 characters)
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="studentPassword"
                    type={showStudentPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={studentPassword}
                    onChange={(e) => setStudentPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="w-full pl-9 pr-10 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => setShowStudentPassword(!showStudentPassword)}
                    aria-label={showStudentPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-[#1E3A8A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] rounded-sm p-1 cursor-pointer"
                  >
                    {showStudentPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <label htmlFor="advisorFullName" className="block text-xs font-semibold text-[#1E3A8A]">
                  Full Name &amp; Title
                </label>
                <div className="relative">
                  <User className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="advisorFullName"
                    type="text"
                    value={advisorFullName}
                    onChange={(e) => setAdvisorFullName(e.target.value)}
                    placeholder="e.g. Dr. Jane Doe"
                    required
                    className="w-full pl-9 pr-3 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="advisorEmail" className="block text-xs font-semibold text-[#1E3A8A]">
                  Institutional Email Address
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="advisorEmail"
                    type="email"
                    value={advisorEmail}
                    onChange={(e) => setAdvisorEmail(e.target.value)}
                    placeholder="e.g. advisor@university.edu"
                    required
                    className="w-full pl-9 pr-3 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="advisorPassword" className="block text-xs font-semibold text-[#1E3A8A]">
                  Password (min. 6 characters)
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-ink-muted absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                  <input
                    id="advisorPassword"
                    type={showAdvisorPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={advisorPassword}
                    onChange={(e) => setAdvisorPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="w-full pl-9 pr-10 py-2.5 text-xs bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#1E3A8A] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#1E3A8A] transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAdvisorPassword(!showAdvisorPassword)}
                    aria-label={showAdvisorPassword ? "Hide password" : "Show password"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-[#1E3A8A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1E3A8A] rounded-sm p-1 cursor-pointer"
                  >
                    {showAdvisorPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </>
          )}

          <button
            type="submit"
            disabled={processing}
            className="w-full py-3 px-4 mt-2 bg-[#1E3A8A] hover:bg-[#1E40AF] active:bg-[#1E40AF] text-white text-xs font-semibold rounded-xl shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {processing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Creating account...</span>
              </>
            ) : (
              <>
                <span>
                  {registrationRole === "student" ? "Register as student" : "Register as advisor"}
                </span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>
      )}

      {/* Switch Mode Prompt */}
      <div className="mt-6 pt-5 border-t border-[#E5E7EB] text-center">
        <button
          type="button"
          onClick={() => {
            setAuthMode(authMode === "login" ? "register" : "login");
            resetFormFeedback();
          }}
          className="text-xs text-ink hover:text-[#1E3A8A] font-medium transition-colors cursor-pointer"
        >
          {authMode === "login"
            ? "Don't have an account yet? Create one"
            : "Already registered? Sign in instead"}
        </button>
      </div>
    </div>
  );
}
