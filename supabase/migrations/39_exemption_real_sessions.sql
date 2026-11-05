-- =============================================================================
-- Migration 39: exemption rows get a real session (DECISIONS.md #24)
-- Old exemptions were saved as "Sem N". normalize_semester() rejects that label,
-- so approving any later slip for the student failed.
-- Converts them to "SEM 1 <student's template syllabus_year>".
-- Fails (nothing changed) if a row has no template, a bad syllabus_year, or the
-- course already has a row in that session. Fix those by hand, then re-run.
-- DO NOT APPLY UNTIL EXPLICITLY APPROVED. Staging first.
-- =============================================================================
BEGIN;

UPDATE academic_records ar
SET semester = normalize_semester('SEM 1 ' || t.syllabus_year)
FROM students s
JOIN cohorts c ON c.id = s.cohort_id
JOIN degree_templates t ON t.id = c.template_id
WHERE s.tenant_id = ar.tenant_id
  AND s.matric_no = ar.matric_no
  AND UPPER(TRIM(ar.grade)) IN ('EX', 'CT')
  AND ar.semester ~* '^\s*sem\s*[0-9]+\s*$';

DO $$
DECLARE v_left INT;
BEGIN
    SELECT COUNT(*) INTO v_left FROM academic_records
    WHERE UPPER(TRIM(grade)) IN ('EX', 'CT') AND semester ~* '^\s*sem\s*[0-9]+\s*$';
    IF v_left > 0 THEN
        RAISE EXCEPTION '% exemption row(s) still "Sem N": student has no degree template', v_left;
    END IF;
END $$;

COMMIT;

-- Before applying: save this output, it is the only record of the old labels.
-- SELECT id, tenant_id, matric_no, course_code, grade, semester FROM academic_records
-- WHERE UPPER(TRIM(grade)) IN ('EX', 'CT') AND semester ~* '^\s*sem\s*[0-9]+\s*$';

-- Verify (expect 0 rows): exemption rows not in canonical form.
-- SELECT id, matric_no, course_code, semester FROM academic_records
-- WHERE UPPER(TRIM(grade)) IN ('EX', 'CT') AND semester !~ '^SEM [1-4] [0-9]{4}/[0-9]{4}$';

-- Rollback: restore the saved labels by id. This brings back the slip approval failure.
-- BEGIN;
-- UPDATE academic_records ar SET semester = b.semester
-- FROM (VALUES ('<id>'::uuid, 'Sem 1')) AS b(id, semester)
-- WHERE ar.id = b.id;
-- COMMIT;
