-- =============================================================================
-- Migration 40: advisee_roster_summary counts one row per course (DECISIONS.md #24)
-- The view summed every attempt, so a retake counted its credits twice and every
-- attempt went into the CGPA. It now mirrors backend/app/engine/grading.py:
--   CGPA    = compute_cgpa: among attempts that count in CGPA, the tenant's
--             repeat_policy picks one per course.
--   Credits = compute_completed_credits: a course counts once if any attempt is
--             a completing pass; repeat_policy picks which attempt's credits.
-- DO NOT APPLY UNTIL EXPLICITLY APPROVED. Staging first; apply after migration 39.
-- =============================================================================
BEGIN;

-- tenants has RLS and no SELECT policy, and this view runs as the caller, so it
-- cannot read tenants directly. This exposes only the policy value, not the row.
CREATE OR REPLACE FUNCTION tenant_repeat_policy(p_tenant_id TEXT)
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT repeat_policy FROM tenants WHERE id = p_tenant_id;
$$;

REVOKE ALL ON FUNCTION tenant_repeat_policy(TEXT) FROM public, anon;
GRANT EXECUTE ON FUNCTION tenant_repeat_policy(TEXT) TO authenticated, service_role;

CREATE OR REPLACE VIEW advisee_roster_summary
WITH (security_invoker = true) AS
WITH latest_audits AS (
    SELECT DISTINCT ON (matric_no)
        id AS latest_audit_id,
        matric_no,
        advisor_staff_id,
        total_credits_earned AS audit_credits_earned,
        traffic_light_status,
        unmet_prerequisites_count,
        failed_courses_count,
        audit_summary,
        created_at AS last_audited_at
    FROM degree_audits
    ORDER BY matric_no, created_at DESC
),
active_scales AS (
    -- Resolve effective grade scale definition per tenant and grade
    SELECT DISTINCT ON (tenant_id, UPPER(TRIM(grade)))
        tenant_id,
        UPPER(TRIM(grade)) AS grade,
        points,
        rank,
        is_pass,
        counts_in_cgpa,
        counts_as_completed
    FROM grade_scales
    WHERE (effective_to IS NULL OR effective_to >= CURRENT_DATE)
      AND effective_from <= CURRENT_DATE
    ORDER BY tenant_id, UPPER(TRIM(grade)), effective_from DESC
),
attempts AS (
    SELECT
        ar.id,
        ar.tenant_id,
        ar.matric_no,
        UPPER(REPLACE(ar.course_code, ' ', '')) AS course,
        ar.credits,
        CASE WHEN gs.grade IS NOT NULL THEN gs.is_pass AND gs.counts_as_completed
             ELSE ar.status IN ('Passed', 'Exempted') END AS completes,
        CASE WHEN gs.grade IS NOT NULL THEN gs.counts_in_cgpa
             ELSE ar.grade_point IS NOT NULL END AS in_cgpa,
        CASE WHEN gs.grade IS NOT NULL THEN COALESCE(gs.points, ar.grade_point, 0)
             ELSE ar.grade_point END AS points,
        COALESCE(gs.rank, 999) AS rank,
        tenant_repeat_policy(ar.tenant_id) AS policy,
        -- Same chronological key as grading._parse_semester_sort_key
        COALESCE(substring(ar.semester from '\d{4}')::INT, 0) AS sem_year,
        COALESCE(
            substring(ar.semester from '(?i)sem(?:ester)?\s*[:.]?\s*([1-4])')::INT,
            substring(ar.semester from '[-/\s]([1-4])$')::INT,
            0
        ) AS sem_num
    FROM academic_records ar
    LEFT JOIN active_scales gs
        ON ar.tenant_id = gs.tenant_id
       AND UPPER(TRIM(ar.grade)) = gs.grade
),
credit_attempts AS (
    SELECT DISTINCT ON (tenant_id, matric_no, course) tenant_id, matric_no, credits
    FROM attempts
    WHERE completes
    ORDER BY tenant_id, matric_no, course,
        CASE WHEN policy = 'best' THEN points END DESC NULLS LAST,
        CASE WHEN policy = 'best' THEN rank END ASC NULLS LAST,
        sem_year DESC, sem_num DESC, id DESC
),
cgpa_attempts AS (
    SELECT DISTINCT ON (tenant_id, matric_no, course) tenant_id, matric_no, credits, points
    FROM attempts
    WHERE in_cgpa
    ORDER BY tenant_id, matric_no, course,
        CASE WHEN policy = 'best' THEN points END DESC NULLS LAST,
        CASE WHEN policy = 'best' THEN rank END ASC NULLS LAST,
        sem_year DESC, sem_num DESC, id DESC
),
credit_totals AS (
    SELECT tenant_id, matric_no, SUM(credits)::INT AS earned_credits
    FROM credit_attempts
    GROUP BY tenant_id, matric_no
),
cgpa_totals AS (
    SELECT tenant_id, matric_no,
        ROUND(SUM(credits * points) / NULLIF(SUM(credits), 0), 2) AS calc_cgpa
    FROM cgpa_attempts
    GROUP BY tenant_id, matric_no
),
records_agg AS (
    SELECT
        ar.tenant_id,
        ar.matric_no,
        -- Failed courses count
        COUNT(
            CASE
                WHEN gs.is_pass = false THEN 1
                WHEN gs.grade IS NULL AND ar.status = 'Failed' THEN 1
            END
        )::INT AS failed_count,
        COUNT(CASE WHEN ar.prerequisite_met = false THEN 1 END)::INT AS unmet_prereq_count,
        BOOL_OR(ar.prerequisite_met = false) AS has_unmet_prereq
    FROM academic_records ar
    LEFT JOIN active_scales gs
        ON ar.tenant_id = gs.tenant_id
       AND UPPER(TRIM(ar.grade)) = gs.grade
    GROUP BY ar.tenant_id, ar.matric_no
),
records_full AS (
    SELECT
        ra.tenant_id,
        ra.matric_no,
        ra.failed_count,
        ra.unmet_prereq_count,
        ra.has_unmet_prereq,
        COALESCE(ct.earned_credits, 0) AS earned_credits_from_records,
        gt.calc_cgpa
    FROM records_agg ra
    LEFT JOIN credit_totals ct ON ct.tenant_id = ra.tenant_id AND ct.matric_no = ra.matric_no
    LEFT JOIN cgpa_totals gt ON gt.tenant_id = ra.tenant_id AND gt.matric_no = ra.matric_no
)
SELECT
    s.matric_no,
    s.name AS student_name,
    s.name,
    s.advisor_staff_id,
    c.cohort_code,
    c.cohort_name,
    s.cohort_id,
    s.program,
    s.syllabus_type,
    s.institutional_email,
    s.user_id,
    s.tenant_id,
    s.entry_semester,
    s.block_exempted_credits,
    COALESCE(s.cgpa, r.calc_cgpa, 0.00)::NUMERIC(3, 2) AS current_cgpa,
    COALESCE(s.cgpa, r.calc_cgpa, 0.00)::NUMERIC(3, 2) AS cgpa,
    (COALESCE(r.earned_credits_from_records, la.audit_credits_earned, 0) + COALESCE(s.block_exempted_credits, 0))::INT AS total_earned_credits,
    COALESCE(
        s.academic_status,
        CASE
            WHEN COALESCE(s.cgpa, r.calc_cgpa, 0.00) < 2.00 THEN 'Probation'
            WHEN COALESCE(s.cgpa, r.calc_cgpa, 0.00) < 2.50 THEN 'At-Risk'
            ELSE 'Good Standing'
        END
    ) AS academic_status,
    COALESCE(
        la.traffic_light_status,
        CASE
            WHEN r.has_unmet_prereq = true OR COALESCE(s.cgpa, r.calc_cgpa, 0.00) < 2.00 THEN 'RED'
            WHEN COALESCE(s.cgpa, r.calc_cgpa, 0.00) < 2.50 OR r.failed_count > 0 THEN 'YELLOW'
            ELSE 'GREEN'
        END
    ) AS traffic_light_status,
    COALESCE(
        la.traffic_light_status,
        CASE
            WHEN r.has_unmet_prereq = true OR COALESCE(s.cgpa, r.calc_cgpa, 0.00) < 2.00 THEN 'RED'
            WHEN COALESCE(s.cgpa, r.calc_cgpa, 0.00) < 2.50 OR r.failed_count > 0 THEN 'YELLOW'
            ELSE 'GREEN'
        END
    ) AS traffic_light,
    COALESCE(la.unmet_prerequisites_count, r.unmet_prereq_count, 0)::INT AS unmet_prerequisites_count,
    COALESCE(la.failed_courses_count, r.failed_count, 0)::INT AS failed_courses_count,
    la.audit_summary,
    la.latest_audit_id,
    la.last_audited_at,
    s.created_at
FROM students s
LEFT JOIN cohorts c ON s.cohort_id = c.id
LEFT JOIN latest_audits la ON s.matric_no = la.matric_no
LEFT JOIN records_full r ON s.matric_no = r.matric_no AND s.tenant_id = r.tenant_id;

COMMIT;

-- Verify (expect 0 rows): roster credits differ from one row per completed course.
-- Run as postgres/service role. Students with block credits are skipped.
-- WITH per_course AS (
--     SELECT DISTINCT ON (ar.tenant_id, ar.matric_no, UPPER(REPLACE(ar.course_code, ' ', '')))
--         ar.tenant_id, ar.matric_no, ar.credits
--     FROM academic_records ar
--     JOIN grade_scales gs ON gs.tenant_id = ar.tenant_id AND UPPER(TRIM(gs.grade)) = UPPER(TRIM(ar.grade))
--     WHERE gs.is_pass AND gs.counts_as_completed
--       AND gs.effective_from <= CURRENT_DATE AND (gs.effective_to IS NULL OR gs.effective_to >= CURRENT_DATE)
--     ORDER BY ar.tenant_id, ar.matric_no, UPPER(REPLACE(ar.course_code, ' ', '')), ar.semester DESC
-- )
-- SELECT v.matric_no, v.total_earned_credits, SUM(p.credits) AS expected
-- FROM advisee_roster_summary v
-- JOIN per_course p ON p.tenant_id = v.tenant_id AND p.matric_no = v.matric_no
-- WHERE COALESCE(v.block_exempted_credits, 0) = 0
-- GROUP BY v.matric_no, v.total_earned_credits
-- HAVING v.total_earned_credits <> SUM(p.credits);

-- Rollback: re-run the CREATE VIEW block of 28_advisee_roster_grade_scales.sql, then:
-- DROP FUNCTION IF EXISTS tenant_repeat_policy(TEXT);
