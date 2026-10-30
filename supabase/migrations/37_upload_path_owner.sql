-- =============================================================================
-- Migration 37: uploaded_documents insert must point at the student's own slip
-- A student could insert a row whose file_path names another student's slip,
-- then have the backend read/purge it. The path must be slips/<own matric>_<ts>.<ext>
-- (the format StudentPortal.tsx and useDocumentIngestion.ts already write).
-- =============================================================================
BEGIN;

DROP POLICY IF EXISTS "uploaded_documents_student_insert" ON uploaded_documents;

CREATE POLICY "uploaded_documents_student_insert" ON uploaded_documents
FOR INSERT TO authenticated
WITH CHECK (
    matric_no IN (SELECT matric_no FROM my_matric_nos())
    AND split_part(file_path, '/', 1) = 'slips'
    AND split_part(split_part(file_path, '/', 2), '_', 1) = matric_no
);

COMMIT;

-- Verify:
-- SELECT policyname, cmd, with_check FROM pg_policies
--  WHERE tablename = 'uploaded_documents' AND policyname = 'uploaded_documents_student_insert';
-- Expected: with_check contains split_part(file_path, '/', 1) = 'slips' and the matric_no check.
-- As a student (staging): INSERT with file_path 'slips/<other_matric>_1.pdf' -> RLS violation;
--                         INSERT with file_path 'slips/<own_matric>_1.pdf'   -> succeeds.

/*
-- ROLLBACK (restores the migration 29 policy)
BEGIN;
DROP POLICY IF EXISTS "uploaded_documents_student_insert" ON uploaded_documents;
CREATE POLICY "uploaded_documents_student_insert" ON uploaded_documents
FOR INSERT TO authenticated
WITH CHECK (matric_no IN (SELECT matric_no FROM my_matric_nos()));
COMMIT;
*/
