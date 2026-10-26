import React, { useState, useEffect } from "react";
import { useNavigate, Navigate } from "react-router";
import { useAuth } from "../../context/AuthContext";
import { supabase } from "../../lib/supabase";
import { warmUpBackend } from "../../lib/api";
import { toast } from "sonner";

import { LandingHeader } from "./landing/LandingHeader";
import { LandingHero } from "./landing/LandingHero";
import { HowItWorksSection } from "./landing/HowItWorksSection";
import { FeaturesSection } from "./landing/FeaturesSection";
import { AuthCard } from "./landing/AuthCard";
import { LandingFooter } from "./landing/LandingFooter";

export function LandingPage() {
  const navigate = useNavigate();
  const { user, role, signInWithEmail, signUpStudent, signUpAdvisor, authError, clearAuthError } = useAuth();

  // Navigation / View State: 'login' | 'register'
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  // Login Role Context: 'student' | 'advisor'
  const [loginRole, setLoginRole] = useState<"student" | "advisor">("student");

  // Registration Role State: 'student' | 'advisor'
  const [registrationRole, setRegistrationRole] = useState<"student" | "advisor">("student");

  // Login Form State
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Student Registration Form State
  const [studentFullName, setStudentFullName] = useState("");
  const [studentEmail, setStudentEmail] = useState("");
  const [studentPassword, setStudentPassword] = useState("");
  const [showStudentPassword, setShowStudentPassword] = useState(false);

  // Collision & Dispute Contest States
  const [isDuplicate, setIsDuplicate] = useState(false);
  const [isContesting, setIsContesting] = useState(false);
  const [contestEmail, setContestEmail] = useState("");
  const [contestProcessing, setContestProcessing] = useState(false);
  const [contestSuccess, setContestSuccess] = useState(false);
  const [contestErrorMessage, setContestErrorMessage] = useState<string | null>(null);

  // Advisor Registration Form State
  const [advisorFullName, setAdvisorFullName] = useState("");
  const [advisorEmail, setAdvisorEmail] = useState("");
  const [advisorPassword, setAdvisorPassword] = useState("");
  const [showAdvisorPassword, setShowAdvisorPassword] = useState(false);

  // UI Status State
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  // Warm up backend (one silent ping per page load)
  useEffect(() => {
    warmUpBackend();
  }, []);

  // Early returns strictly below all hook calls
  if (user && role === 'advisor') return <Navigate replace to="/advisor" />;
  if (user && role === 'student') return <Navigate replace to="/student" />;
  if (user && !role) return <Navigate replace to="/complete-registration" />;

  const resetFormFeedback = () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    setIsDuplicate(false);
    setIsContesting(false);
    setContestErrorMessage(null);
    setContestSuccess(false);
    clearAuthError();
  };

  const scrollToAuth = (mode?: "login" | "register", preselectedRole?: "student" | "advisor") => {
    if (mode) setAuthMode(mode);
    if (preselectedRole) {
      setRegistrationRole(preselectedRole);
      setLoginRole(preselectedRole);
    }
    resetFormFeedback();
    const el = document.getElementById("auth-card");
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    resetFormFeedback();

    const cleanEmail = loginEmail.trim().toLowerCase();
    if (!cleanEmail) {
      toast.error("Please enter your institutional email.");
      setErrorMessage("Please enter your institutional email.");
      return;
    }
    if (!loginPassword) {
      toast.error("Please enter your password.");
      setErrorMessage("Please enter your password.");
      return;
    }

    setProcessing(true);

    try {
      const { error, role: loggedInRole } = await signInWithEmail(cleanEmail, loginPassword);

      if (error) throw error;

      toast.success("Welcome back! Signing into your portal...");

      if (loggedInRole === "student") {
        navigate("/student");
      } else if (loggedInRole === "advisor") {
        navigate("/advisor");
      } else if (loggedInRole === "admin") {
        navigate("/admin");
      } else {
        navigate("/complete-registration");
      }
    } catch (err: any) {
      let friendlyError = "Invalid credentials. Please verify your credentials.";
      const rawMsg = (err.message || "").toLowerCase();
      if (rawMsg.includes("invalid login credentials") || rawMsg.includes("invalid grant")) {
        friendlyError = "Invalid email or password. Please verify your credentials.";
      } else if (rawMsg.includes("network") || rawMsg.includes("failed to fetch")) {
        friendlyError = "Network error: Unable to connect to authentication services. Please retry.";
      } else if (rawMsg.includes("email not confirmed")) {
        friendlyError = "Your email has not been confirmed yet. Please check your inbox.";
      } else if (err.message) {
        friendlyError = err.message;
      }

      toast.error(friendlyError);
      setErrorMessage(friendlyError);
    } finally {
      setProcessing(false);
    }
  };

  const handleRegistration = async (e: React.FormEvent) => {
    e.preventDefault();
    resetFormFeedback();

    if (registrationRole === "student") {
      const sanitizedFullName = studentFullName.trim();
      const sanitizedEmail = studentEmail.trim().toLowerCase();

      if (!sanitizedFullName) {
        toast.error("Please enter your full name.");
        setErrorMessage("Please enter your full name.");
        return;
      }
      if (!sanitizedEmail) {
        toast.error("Please enter your email address.");
        setErrorMessage("Please enter your email address.");
        return;
      }
      if (!studentPassword || studentPassword.length < 6) {
        toast.error("Password must be at least 6 characters.");
        setErrorMessage("Password must be at least 6 characters.");
        return;
      }

      setProcessing(true);

      try {
        const { error } = await signUpStudent({
          fullName: sanitizedFullName,
          institutionalEmail: sanitizedEmail,
          email: sanitizedEmail,
          password: studentPassword,
        });

        if (error) throw error;

        toast.success("Check your email to confirm.");
        setSuccessMessage("Check your email to confirm.");
        setStudentFullName("");
        setStudentEmail("");
        setStudentPassword("");
        setLoginEmail(sanitizedEmail);
        setLoginRole("student");
        setAuthMode("login");
        resetFormFeedback();
      } catch (err: any) {
        let friendlyError = err.message || "Student registration failed. Please verify your details.";
        toast.error(friendlyError);
        setErrorMessage(friendlyError);
      } finally {
        setProcessing(false);
      }
    } else {
      const sanitizedFullName = advisorFullName.trim();
      const sanitizedEmail = advisorEmail.trim().toLowerCase();

      if (!sanitizedFullName) {
        toast.error("Please enter your full name.");
        setErrorMessage("Please enter your full name.");
        return;
      }
      if (!sanitizedEmail) {
        toast.error("Please enter your email address.");
        setErrorMessage("Please enter your email address.");
        return;
      }
      if (!advisorPassword || advisorPassword.length < 6) {
        toast.error("Password must be at least 6 characters.");
        setErrorMessage("Password must be at least 6 characters.");
        return;
      }

      setProcessing(true);

      try {
        const { error } = await signUpAdvisor({
          fullName: sanitizedFullName,
          email: sanitizedEmail,
          password: advisorPassword,
        });

        if (error) throw error;

        toast.success("Check your email to confirm.");
        setSuccessMessage("Check your email to confirm.");
        setAdvisorFullName("");
        setAdvisorEmail("");
        setAdvisorPassword("");
        setLoginEmail(sanitizedEmail);
        setLoginRole("advisor");
        setAuthMode("login");
        resetFormFeedback();
      } catch (err: any) {
        let friendlyError = err.message || "Advisor registration failed. Please verify your details.";
        if (friendlyError.includes("already registered")) {
          friendlyError = "An account with this email already exists. Please sign in.";
        }
        toast.error(friendlyError);
        setErrorMessage(friendlyError);
      } finally {
        setProcessing(false);
      }
    }
  };

  const handleContestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setContestErrorMessage(null);

    const cleanEmail = contestEmail.trim().toLowerCase();
    if (!cleanEmail) {
      toast.error("Please enter your institutional email address.");
      setContestErrorMessage("Please enter your institutional email address.");
      return;
    }

    if (!/^[\w.-]+@[\w.-]+\.[a-zA-Z]{2,}$/.test(cleanEmail)) {
      toast.error("Please provide a valid institutional email.");
      setContestErrorMessage("Please provide a valid institutional email.");
      return;
    }

    setContestProcessing(true);
    try {
      const { error } = await supabase.from('registration_disputes').insert({
        disputed_by_email: cleanEmail,
      });

      if (error) throw error;

      toast.success("Contest filed successfully!");
      setContestSuccess(true);
    } catch (err: any) {
      console.error("Contest Registration Error:", err);
      const errMsg = err.message || "Failed to submit dispute. Please try again.";
      setContestErrorMessage(errMsg);
      toast.error(errMsg);
    } finally {
      setContestProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB] text-ink font-sans flex flex-col justify-between antialiased selection:bg-[#1E3A8A] selection:text-white">
      {/* 1. Header */}
      <LandingHeader
        onLoginClick={() => scrollToAuth("login")}
        onGetStartedClick={() => scrollToAuth("register")}
      />

      <main className="flex-1">
        {/* 2 & 6. Hero and Auth Card Layout */}
        <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10 sm:py-14 lg:py-20">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-start">
            {/* Left Column: Hero */}
            <div className="lg:col-span-7 pt-2">
              <LandingHero
                onSelectAdvisor={() => scrollToAuth("register", "advisor")}
                onSelectStudent={() => scrollToAuth("register", "student")}
              />
            </div>

            {/* Right Column: Auth Card */}
            <div id="auth-card" className="lg:col-span-5 scroll-mt-24 w-full">
              <AuthCard
                authMode={authMode}
                setAuthMode={setAuthMode}
                registrationRole={registrationRole}
                setRegistrationRole={setRegistrationRole}
                loginEmail={loginEmail}
                setLoginEmail={setLoginEmail}
                loginPassword={loginPassword}
                setLoginPassword={setLoginPassword}
                showLoginPassword={showLoginPassword}
                setShowLoginPassword={setShowLoginPassword}
                studentFullName={studentFullName}
                setStudentFullName={setStudentFullName}
                studentEmail={studentEmail}
                setStudentEmail={setStudentEmail}
                studentPassword={studentPassword}
                setStudentPassword={setStudentPassword}
                showStudentPassword={showStudentPassword}
                setShowStudentPassword={setShowStudentPassword}
                advisorFullName={advisorFullName}
                setAdvisorFullName={setAdvisorFullName}
                advisorEmail={advisorEmail}
                setAdvisorEmail={setAdvisorEmail}
                advisorPassword={advisorPassword}
                setAdvisorPassword={setAdvisorPassword}
                showAdvisorPassword={showAdvisorPassword}
                setShowAdvisorPassword={setShowAdvisorPassword}
                errorMessage={errorMessage}
                successMessage={successMessage}
                authError={authError}
                processing={processing}
                handleLogin={handleLogin}
                handleRegistration={handleRegistration}
                resetFormFeedback={resetFormFeedback}
                isDuplicate={isDuplicate}
                isContesting={isContesting}
                setIsContesting={setIsContesting}
                contestEmail={contestEmail}
                setContestEmail={setContestEmail}
                contestProcessing={contestProcessing}
                contestSuccess={contestSuccess}
                contestErrorMessage={contestErrorMessage}
                handleContestSubmit={handleContestSubmit}
              />
            </div>
          </div>
        </section>

        {/* 3. How It Works Section */}
        <HowItWorksSection />

        {/* 4. For Advisors / For Students Features Section */}
        <FeaturesSection />
      </main>

      {/* 7. Footer */}
      <LandingFooter />
    </div>
  );
}