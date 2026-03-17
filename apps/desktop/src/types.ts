export type PatientSummary = {
  id: string;
  legacy_patient_id: number | null;
  first_name: string;
  last_name: string;
  display_name: string;
  date_of_birth: string;
  gender_text: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RetinalImage = {
  id: string;
  session_id: string;
  patient_id: string;
  laterality: string;
  image_type: string;
  captured_at: string | null;
  imported_at: string;
  original_filename: string;
  stored_filename: string;
  file_size_bytes: number;
  width_px: number | null;
  height_px: number | null;
  thumbnail_width_px: number | null;
  thumbnail_height_px: number | null;
  notes: string | null;
  legacy_visit_id: number | null;
  thumbnail_relpath?: string | null;
};

export type StudySession = {
  id: string;
  patient_id: string;
  session_date: string;
  captured_at: string | null;
  operator_name: string | null;
  status: string;
  source: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  images: RetinalImage[];
};

export type PatientDetail = PatientSummary & {
  sessions: StudySession[];
};
